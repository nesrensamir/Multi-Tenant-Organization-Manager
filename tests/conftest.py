import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.main import app
from app.api.dependencies import get_db
from app.models.base import Base

# 1. Spin up the Postgres Testcontainer (Synchronous, Session-scoped)
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres

# 2. Setup the Async Database Engine connected to the Testcontainer
@pytest_asyncio.fixture(scope="session")
async def test_engine(postgres_container):
    # Convert standard psycopg2 URL to asyncpg URL for async queries
    db_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    
    engine = create_async_engine(db_url, echo=False)
    
    # Create tables in the test database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Manually create the FTS trigger for the test DB (bypassing Alembic for test speed)
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION users_search_vector_trigger() RETURNS trigger AS $$
            begin
              new.search_vector :=
                setweight(to_tsvector('pg_catalog.english', coalesce(new.full_name,'')), 'A') ||
                setweight(to_tsvector('pg_catalog.simple', coalesce(new.email,'')), 'B');
              return new;
            end
            $$ LANGUAGE plpgsql;
        """))
        await conn.execute(text("""
            CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
            ON users FOR EACH ROW EXECUTE FUNCTION users_search_vector_trigger();
        """))
        
    yield engine
    
    # Clean up tables after the test session completes
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

# 3. Provide a database session for each individual test
@pytest_asyncio.fixture
async def db_session(test_engine):
    TestingSessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with TestingSessionLocal() as session:
        yield session
        # Rollback after each test to keep the database perfectly clean for the next one
        await session.rollback()

# 4. Override FastAPI's get_db dependency to use our test session
@pytest_asyncio.fixture
async def async_client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    # Use ASGITransport for testing FastAPI directly without needing a real server running
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
        
    app.dependency_overrides.clear()