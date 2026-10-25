import asyncio
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import Base, User
from models import Project, ProjectMember
from routers import projects as projects_router


@pytest.fixture
def run_with_database(tmp_path):
    def run(test):
        async def execute():
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{tmp_path / 'projects.db'}"
            )

            @event.listens_for(engine.sync_engine, "connect")
            def enable_foreign_keys(connection, _):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            try:
                session_factory = async_sessionmaker(engine, expire_on_commit=False)
                async with session_factory() as session:
                    owner = User(email="owner@example.com", hashed_password="password")
                    member = User(
                        email="member@example.com", hashed_password="password"
                    )
                    outsider = User(
                        email="outsider@example.com", hashed_password="password"
                    )
                    session.add_all([owner, member, outsider])
                    await session.flush()

                    project = Project(
                        owner_id=owner.id, name="Atlas", description="First"
                    )
                    second_project = Project(
                        owner_id=owner.id, name="Beacon", description="Second"
                    )
                    session.add_all([project, second_project])
                    await session.flush()
                    session.add_all(
                        [
                            ProjectMember(
                                project_id=project.id,
                                user_id=owner.id,
                                role="owner",
                            ),
                            ProjectMember(
                                project_id=project.id,
                                user_id=member.id,
                                role="reporter",
                            ),
                            ProjectMember(
                                project_id=second_project.id,
                                user_id=owner.id,
                                role="owner",
                            ),
                        ]
                    )
                    await session.commit()

                    app = FastAPI()
                    app.include_router(projects_router.router)
                    current_user = [owner]

                    async def override_user():
                        return current_user[0]

                    async def override_session():
                        yield session

                    app.dependency_overrides[projects_router.current_active_user] = (
                        override_user
                    )
                    app.dependency_overrides[projects_router.get_async_session] = (
                        override_session
                    )

                    async with AsyncClient(
                        transport=ASGITransport(app=app),
                        base_url="http://test",
                    ) as client:
                        return await test(
                            client,
                            current_user,
                            session,
                            owner,
                            member,
                            outsider,
                            project,
                            second_project,
                        )
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    return run


def test_list_projects_paginates_and_reports_member_counts(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        second_project,
    ):
        response = await client.get(
            "/api/v1/projects", params={"limit": 1, "offset": 1}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert payload["limit"] == 1
        assert payload["offset"] == 1
        assert len(payload["items"]) == 1
        listed_project = payload["items"][0]
        assert listed_project["owner_id"] == str(owner.id)
        assert listed_project["my_role"] == "owner"
        assert listed_project["member_count"] == 1

    run_with_database(exercise)


def test_list_projects_only_includes_projects_for_current_member(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        second_project,
    ):
        current_user[0] = member
        response = await client.get("/api/v1/projects")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["id"] == str(project.id)
        assert payload["items"][0]["my_role"] == "reporter"
        assert payload["items"][0]["member_count"] == 2

    run_with_database(exercise)


def test_create_project_adds_owner_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        second_project,
    ):
        response = await client.post(
            "/api/v1/projects",
            json={"name": "New project", "description": "Created through API"},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["name"] == "New project"
        assert payload["description"] == "Created through API"
        assert payload["owner_id"] == str(owner.id)
        assert payload["my_role"] == "owner"
        assert payload["member_count"] == 1

        membership = await session.get(
            ProjectMember,
            {
                "project_id": uuid.UUID(payload["id"]),
                "user_id": owner.id,
            },
        )
        assert membership is not None
        assert membership.role == "owner"

    run_with_database(exercise)


def test_get_project_returns_member_view_or_not_found_detail(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        second_project,
    ):
        current_user[0] = member
        response = await client.get(f"/api/v1/projects/{project.id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(project.id)
        assert payload["name"] == "Atlas"
        assert payload["my_role"] == "reporter"
        assert payload["member_count"] == 2

        current_user[0] = outsider
        not_found = await client.get(f"/api/v1/projects/{project.id}")
        assert not_found.status_code == 200
        assert not_found.json() == {"detail": "Project not found"}

    run_with_database(exercise)


def test_update_project_is_owner_only(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        second_project,
    ):
        response = await client.patch(
            f"/api/v1/projects/{project.id}",
            json={"name": "Atlas updated", "description": "Revised"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "Atlas updated"
        assert payload["description"] == "Revised"
        assert payload["my_role"] == "owner"
        saved_project = await session.get(Project, project.id)
        assert saved_project.name == "Atlas updated"

        current_user[0] = member
        forbidden = await client.patch(
            f"/api/v1/projects/{project.id}",
            json={"name": "Not allowed"},
        )
        assert forbidden.status_code == 200
        assert forbidden.json() == {"detail": "Project not found"}

        missing = await client.patch(
            f"/api/v1/projects/{uuid.uuid4()}",
            json={"name": "Missing"},
        )
        assert missing.status_code == 200
        assert missing.json() == {"detail": "Project not found"}

    run_with_database(exercise)


def test_delete_project_removes_owned_project(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        second_project,
    ):
        response = await client.delete(f"/api/v1/projects/{second_project.id}")

        assert response.status_code == 204
        assert await session.get(Project, second_project.id) is None

        remaining = await client.get("/api/v1/projects")
        assert remaining.status_code == 200
        assert remaining.json()["total"] == 1
        assert remaining.json()["items"][0]["id"] == str(project.id)

    run_with_database(exercise)
