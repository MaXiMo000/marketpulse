from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
