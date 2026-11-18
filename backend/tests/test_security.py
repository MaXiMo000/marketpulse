import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import security
from app.config import settings
from app.db import get_db
from app.main import create_app
from app.models import Base
from app.security import RateLimiter, validate_settings

TOKEN = "t" * 40


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def memory_db(app):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    return app


@pytest.fixture
def secured(monkeypatch):
    """An app instance configured like production, with fresh rate limiters."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "api_token", TOKEN)
    monkeypatch.setattr(settings, "cors_origins", "https://app.example.test")
    monkeypatch.setattr(security, "auth_failures", RateLimiter(5, 60))
    monkeypatch.setattr(security, "requests", RateLimiter(1000, 60))
    return TestClient(memory_db(create_app()))


# ---------- rate limiter ----------

def test_limiter_blocks_at_the_limit_and_reports_retry_after():
    clock = Clock()
    limiter = RateLimiter(3, 60, clock=clock)
    for _ in range(3):
        assert limiter.retry_after("ip") is None
        limiter.record("ip")
    assert limiter.retry_after("ip") == pytest.approx(60)
    clock.now += 20
    assert limiter.retry_after("ip") == pytest.approx(40)


def test_limiter_recovers_after_the_window_and_keys_are_independent():
    clock = Clock()
    limiter = RateLimiter(1, 60, clock=clock)
    limiter.record("a")
    assert limiter.retry_after("a") is not None
    assert limiter.retry_after("b") is None
    clock.now += 61
    assert limiter.retry_after("a") is None


def test_limiter_forgets_idle_keys_so_memory_stays_bounded():
    clock = Clock()
    limiter = RateLimiter(1, 60, clock=clock, max_keys=10)
    for i in range(50):
        limiter.record(f"ip{i}")
        clock.now += 61
    assert len(limiter._hits) <= 11


# ---------- authentication ----------

def test_health_is_open_but_every_other_route_needs_the_token(secured):
    assert secured.get("/health").status_code == 200
    assert secured.get("/v1/watchlist").status_code == 401


def test_every_v1_route_is_protected(secured, monkeypatch):
    """Fails if a new /v1 route is added without authentication."""
    monkeypatch.setattr(security, "auth_failures", RateLimiter(1000, 60))  # this test makes many bad attempts on purpose
    # the OpenAPI schema lists every path and method, even with the docs routes disabled
    paths = {p: m for p, m in secured.app.openapi()["paths"].items() if p.startswith("/v1")}
    assert len(paths) >= 8, "expected the /v1 routes to be enumerated"
    for template, methods in paths.items():
        path = re.sub(r"\{[^}]+\}", "1", template)
        for method in methods:
            r = secured.request(method.upper(), path, json={} if method == "post" else None)
            assert r.status_code == 401, f"{method.upper()} {template} is not protected"


@pytest.mark.parametrize(
    "header",
    [None, "", "Bearer", "Bearer ", "Basic abc", f"Token {TOKEN}", "Bearer wrong", "Bearer " + TOKEN + "x"],
)
def test_bad_credentials_are_rejected_with_a_challenge(secured, header):
    headers = {"Authorization": header} if header is not None else {}
    r = secured.get("/v1/watchlist", headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert TOKEN not in r.text


def test_correct_token_is_accepted_case_insensitive_scheme(secured):
    assert secured.get("/v1/watchlist", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    assert secured.get("/v1/watchlist", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


def test_repeated_failures_lock_the_client_out_even_for_the_right_token(secured):
    for _ in range(5):
        assert secured.get("/v1/watchlist", headers={"Authorization": "Bearer nope"}).status_code == 401
    r = secured.get("/v1/watchlist", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_general_request_limit(monkeypatch, secured):
    monkeypatch.setattr(security, "requests", RateLimiter(3, 60))
    ok = {"Authorization": f"Bearer {TOKEN}"}
    codes = [secured.get("/v1/watchlist", headers=ok).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


# ---------- startup configuration ----------

@pytest.mark.parametrize(
    "env,token,cors,ok",
    [
        ("development", "", "http://localhost:5173", True),
        ("production", TOKEN, "https://app.example.test", True),
        ("production", "", "https://app.example.test", False),        # no token
        ("production", "short", "https://app.example.test", False),    # weak token
        ("production", TOKEN, "*", False),                             # wildcard CORS
        ("production", TOKEN, "https://a.test, *", False),
    ],
)
def test_production_config_fails_closed(monkeypatch, env, token, cors, ok):
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(settings, "api_token", token)
    monkeypatch.setattr(settings, "cors_origins", cors)
    if ok:
        validate_settings(settings)
    else:
        with pytest.raises(RuntimeError):
            validate_settings(settings)


def test_the_app_refuses_to_start_misconfigured_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "api_token", "")
    with pytest.raises(RuntimeError):
        create_app()


# ---------- hardening ----------

def test_security_headers_and_no_docs_in_production(secured):
    r = secured.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "max-age" in r.headers["strict-transport-security"]
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert secured.get(path).status_code == 404


def test_oversized_bodies_are_rejected_before_authentication(secured):
    r = secured.post("/v1/portfolios", content=b"x" * 20_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_chunked_bodies_without_a_length_are_refused(secured):
    r = secured.post("/v1/portfolios", content=iter([b"{}"]), headers={"Content-Type": "application/json"})
    assert r.status_code == 411


def test_cors_only_allows_the_configured_origin_and_the_auth_header(secured):
    preflight = secured.options(
        "/v1/watchlist",
        headers={"Origin": "https://app.example.test", "Access-Control-Request-Method": "GET",
                 "Access-Control-Request-Headers": "authorization"},
    )
    assert preflight.headers["access-control-allow-origin"] == "https://app.example.test"
    assert "authorization" in preflight.headers["access-control-allow-headers"].lower()
    evil = secured.options(
        "/v1/watchlist",
        headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in evil.headers


def test_development_mode_without_a_token_stays_open_for_local_use(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "api_token", "")
    client = TestClient(memory_db(create_app()))
    assert client.get("/v1/watchlist").status_code == 200
    assert client.get("/docs").status_code == 200
