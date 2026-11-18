from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


def test_health_reports_ok_when_the_database_answers(env):
    client, _ = env
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_health_is_503_when_the_database_is_unreachable():
    class BrokenSession:
        def execute(self, *_a, **_k):
            raise ConnectionError("connection refused")

    def broken():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken
    try:
        r = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert "refused" not in r.text  # no internal details leak to an unauthenticated caller
