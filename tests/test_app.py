import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import Base, get_async_session
from main import app


@pytest.fixture
def run_with_app_database(tmp_path):
    def run(test):
        async def execute():
            engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)

            async def override_session():
                async with session_factory() as session:
                    yield session

            previous_overrides = app.dependency_overrides.copy()
            app.dependency_overrides[get_async_session] = override_session
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    return await test(client)
            finally:
                app.dependency_overrides.clear()
                app.dependency_overrides.update(previous_overrides)
                await engine.dispose()

        return asyncio.run(execute())

    return run


def test_full_app_registers_user_authenticates_and_protects_health(
    run_with_app_database,
):
    async def exercise(client):
        unauthenticated = await client.get("/api/v1/health")
        assert unauthenticated.status_code == 401

        email = "integration@example.com"
        password = "Strong-test-password-2026"
        registration = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert registration.status_code == 201
        assert registration.json()["email"] == email

        login = await client.post(
            "/api/v1/auth/jwt/login",
            data={"username": email, "password": password},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        health = await client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert health.status_code == 200
        assert health.json() == {"status": "healthy"}

    run_with_app_database(exercise)
