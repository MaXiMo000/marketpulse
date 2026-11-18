"""Twelve Data daily time series. Free tier allows 8 requests/minute, so calls are spaced out."""
import threading
import time
from datetime import date

import httpx

from app.config import settings

BASE_URL = "https://api.twelvedata.com/time_series"
_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    with _lock:
        wait = settings.twelvedata_min_interval_s - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def fetch_daily_closes(symbol: str, outputsize: int = 170, client: httpx.Client | None = None) -> list[tuple[date, float]]:
    """Daily closes, oldest first."""
    if not settings.twelvedata_api_key:
        raise RuntimeError("TWELVEDATA_API_KEY is not set")
    _throttle()
    params = {"symbol": symbol, "interval": "1day", "outputsize": outputsize}
    # key goes in a header so it never appears in request URLs or logs
    headers = {"Authorization": f"apikey {settings.twelvedata_api_key}"}
    resp = (client or httpx).get(BASE_URL, params=params, headers=headers, timeout=20)
    is_json = resp.headers.get("content-type", "").startswith("application/json")
    body = resp.json() if is_json else {}
    # Errors (bad symbol, rate limit) carry a message in the body, sometimes with HTTP 200, sometimes 4xx
    if body.get("status") == "error":
        raise RuntimeError(f"twelvedata {symbol}: {body.get('message', 'unknown error')}")
    resp.raise_for_status()
    if "values" not in body:
        raise RuntimeError(f"twelvedata {symbol}: unexpected response")
    rows = [(date.fromisoformat(v["datetime"][:10]), float(v["close"])) for v in body["values"]]
    return sorted(rows)
