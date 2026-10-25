import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from routers import health as health_router


def test_health_check_returns_healthy_for_authenticated_user():
    async def exercise():
        app = FastAPI()
        app.include_router(health_router.router)

        async def override_current_active_user():
            return object()

        app.dependency_overrides[health_router.current_active_user] = (
            override_current_active_user
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    asyncio.run(exercise())
