import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.clients import twelvedata
from app.config import settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "twelvedata_api_key", "test-key")
    monkeypatch.setattr(settings, "twelvedata_min_interval_s", 0)


def client_returning(fixture: str, status: int = 200, seen: list | None = None) -> httpx.Client:
    body = (FIXTURES / fixture).read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, content=body, headers={"content-type": "application/json"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parses_real_response_oldest_first():
    raw = json.loads((FIXTURES / "twelvedata_nvda_1day.json").read_text())
    rows = twelvedata.fetch_daily_closes("NVDA", client=client_returning("twelvedata_nvda_1day.json"))
    assert len(rows) == len(raw["values"])
    assert [d for d, _ in rows] == sorted(d for d, _ in rows)
    newest = raw["values"][0]
    assert rows[-1] == (date.fromisoformat(newest["datetime"]), float(newest["close"]))


def test_key_is_sent_in_header_never_in_url():
    seen: list[httpx.Request] = []
    twelvedata.fetch_daily_closes("NVDA", client=client_returning("twelvedata_nvda_1day.json", seen=seen))
    [req] = seen
    assert req.headers["authorization"] == "apikey test-key"
    assert "test-key" not in str(req.url)


def test_provider_error_surfaces_its_message():
    client = client_returning("twelvedata_bad_symbol.json", status=404)
    with pytest.raises(RuntimeError, match="missing or invalid"):
        twelvedata.fetch_daily_closes("NOTATICKERXYZ", client=client)


def test_missing_key_fails_before_any_request(monkeypatch):
    monkeypatch.setattr(settings, "twelvedata_api_key", "")
    with pytest.raises(RuntimeError, match="TWELVEDATA_API_KEY"):
        twelvedata.fetch_daily_closes("NVDA")
