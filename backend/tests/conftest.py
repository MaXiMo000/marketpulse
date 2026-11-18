import os

# Tests must not depend on a developer's local .env (environment variables take priority over it).
os.environ["APP_ENV"] = "development"
os.environ["API_TOKEN"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def env():
    """(TestClient, engine) wired to a fresh in-memory database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = override
    yield TestClient(app), engine
    app.dependency_overrides.clear()
