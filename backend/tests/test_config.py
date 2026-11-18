import pytest

from app.config import Settings, normalize_database_url


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),            # Heroku-style scheme
        ("postgresql://u:p@h/d", "postgresql+psycopg://u:p@h/d"),                    # what Render provides
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),            # already explicit
        ("sqlite:///./marketpulse.db", "sqlite:///./marketpulse.db"),
        ("postgresql://u:p%40ss@h/d?sslmode=require", "postgresql+psycopg://u:p%40ss@h/d?sslmode=require"),
    ],
)
def test_database_urls_are_normalized_for_the_installed_driver(raw, expected):
    assert normalize_database_url(raw) == expected


def test_settings_apply_the_normalization(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@h/d"


def test_proxy_hops_defaults_to_trusting_no_forwarded_headers():
    assert Settings(_env_file=None).proxy_hops == 0
