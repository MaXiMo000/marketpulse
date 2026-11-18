import pytest
from starlette.requests import Request

from app.config import settings
from app.security import client_ip


def request(forwarded: str | None, peer: str | None = "10.0.0.9") -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234) if peer else None})


@pytest.fixture(autouse=True)
def hops(monkeypatch):
    def set_hops(n):
        monkeypatch.setattr(settings, "proxy_hops", n)

    return set_hops


def test_without_a_trusted_proxy_the_header_is_ignored_so_it_cannot_be_spoofed(hops):
    hops(0)
    assert client_ip(request("6.6.6.6")) == "10.0.0.9"


def test_with_one_trusted_proxy_the_last_entry_is_the_client(hops):
    hops(1)
    # the proxy appends the address it saw; anything to its left was supplied by the client and cannot be trusted
    assert client_ip(request("9.9.9.9, 1.2.3.4")) == "1.2.3.4"


def test_with_two_trusted_proxies_the_second_from_last_entry_is_the_client(hops):
    hops(2)
    assert client_ip(request("6.6.6.6, 1.2.3.4, 10.0.0.1")) == "1.2.3.4"


def test_a_forged_prefix_never_changes_the_answer(hops):
    hops(1)
    assert client_ip(request("1.1.1.1, 2.2.2.2, 1.2.3.4")) == client_ip(request("8.8.8.8, 1.2.3.4")) == "1.2.3.4"


def test_missing_or_too_short_header_falls_back_to_the_connection_address(hops):
    hops(1)
    assert client_ip(request(None)) == "10.0.0.9"
    hops(3)
    assert client_ip(request("1.2.3.4")) == "10.0.0.9"


def test_no_peer_information_at_all_is_still_a_usable_key(hops):
    hops(0)
    assert client_ip(request(None, peer=None)) == "unknown"
