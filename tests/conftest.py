import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.database import Base


# Session-scoped Postgres container — started once per test session when DB tests run
@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(postgres):
    engine = create_engine(postgres.get_connection_url())
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    session_factory = sessionmaker(bind=db_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session):
    """Test client with DB session override (for tests that need the DB)."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.headers.update({"X-API-Key": settings.api_key})
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_db():
    """Test client without any DB override (for health/no-DB endpoints)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def unauthenticated_client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
