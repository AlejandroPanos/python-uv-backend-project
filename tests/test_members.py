import asyncio
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import Base, User
from models import Project, ProjectMember
from routers import members as members_router


@pytest.fixture
def run_with_database(tmp_path):
    def run(test):
        async def execute():
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{tmp_path / 'members.db'}"
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            try:
                session_factory = async_sessionmaker(engine, expire_on_commit=False)
                async with session_factory() as session:
                    owner = User(email="owner@example.com", hashed_password="password")
                    maintainer = User(
                        email="maintainer@example.com", hashed_password="password"
                    )
                    reporter = User(
                        email="reporter@example.com", hashed_password="password"
                    )
                    invitee = User(
                        email="invitee@example.com", hashed_password="password"
                    )
                    outsider = User(
                        email="outsider@example.com", hashed_password="password"
                    )
                    session.add_all([owner, maintainer, reporter, invitee, outsider])
                    await session.flush()

                    project = Project(owner_id=owner.id, name="Project")
                    other_project = Project(owner_id=owner.id, name="Other project")
                    session.add_all([project, other_project])
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
                                user_id=maintainer.id,
                                role="maintainer",
                            ),
                            ProjectMember(
                                project_id=project.id,
                                user_id=reporter.id,
                                role="reporter",
                            ),
                        ]
                    )
                    await session.commit()

                    app = FastAPI()
                    app.include_router(members_router.router)
                    current_user = [owner]

                    async def override_user():
                        return current_user[0]

                    async def override_session():
                        yield session

                    app.dependency_overrides[members_router.current_active_user] = (
                        override_user
                    )
                    app.dependency_overrides[members_router.get_async_session] = (
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
                            maintainer,
                            reporter,
                            invitee,
                            outsider,
                            project,
                            other_project,
                        )
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    return run


def test_list_project_members_returns_members(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        invitee,
        outsider,
        project,
        other_project,
    ):
        current_user[0] = maintainer
        response = await client.get(f"/api/v1/projects/{project.id}/members")

        assert response.status_code == 200
        members = response.json()
        assert len(members) == 3
        assert {member["role"] for member in members} == {
            "owner",
            "maintainer",
            "reporter",
        }
        assert all(member["project_id"] == str(project.id) for member in members)

    run_with_database(exercise)


def test_list_project_members_requires_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        invitee,
        outsider,
        project,
        other_project,
    ):
        current_user[0] = outsider
        response = await client.get(f"/api/v1/projects/{project.id}/members")

        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found."

    run_with_database(exercise)


def test_create_member_allows_maintainer_and_normalizes_email(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        invitee,
        outsider,
        project,
        other_project,
    ):
        current_user[0] = maintainer
        response = await client.post(
            f"/api/v1/projects/{project.id}/members",
            json={"email": "INVITEE@example.com", "role": "reporter"},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["project_id"] == str(project.id)
        assert payload["user_id"] == str(invitee.id)
        assert payload["role"] == "reporter"
        membership = await session.get(
            ProjectMember,
            {"project_id": project.id, "user_id": invitee.id},
        )
        assert membership is not None

    run_with_database(exercise)


def test_create_member_rejects_non_maintainers_and_unknown_users(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        invitee,
        outsider,
        project,
        other_project,
    ):
        current_user[0] = outsider
        forbidden = await client.post(
            f"/api/v1/projects/{project.id}/members",
            json={"email": "invitee@example.com"},
        )
        assert forbidden.status_code == 403

        current_user[0] = maintainer
        missing_invitee = await client.post(
            f"/api/v1/projects/{project.id}/members",
            json={"email": "missing@example.com"},
        )
        assert missing_invitee.status_code == 404
        assert missing_invitee.json()["detail"] == "Invitee not found"

        missing_project = await client.post(
            f"/api/v1/projects/{uuid.uuid4()}/members",
            json={"email": "invitee@example.com"},
        )
        assert missing_project.status_code == 404
        assert missing_project.json()["detail"] == "Project not found"

    run_with_database(exercise)


def test_create_member_rejects_duplicate_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        invitee,
        outsider,
        project,
        other_project,
    ):
        current_user[0] = maintainer
        duplicate = await client.post(
            f"/api/v1/projects/{project.id}/members",
            json={"email": "reporter@example.com", "role": "reporter"},
        )

        assert duplicate.status_code == 409
        assert duplicate.json()["detail"].startswith("Failed to add member:")

    run_with_database(exercise)


def test_update_member_role_checks_permissions_and_member_exists(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        invitee,
        outsider,
        project,
        other_project,
    ):
        response = await client.post(
            f"/api/v1/projects/{project.id}/members/{reporter.id}",
            json={"role": "maintainer"},
        )
        assert response.status_code == 201
        assert response.json()["role"] == "maintainer"

        current_user[0] = outsider
        forbidden = await client.post(
            f"/api/v1/projects/{project.id}/members/{invitee.id}",
            json={"role": "reporter"},
        )
        assert forbidden.status_code == 403

        current_user[0] = maintainer
        missing = await client.post(
            f"/api/v1/projects/{project.id}/members/{uuid.uuid4()}",
            json={"role": "reporter"},
        )
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Member not found"

    run_with_database(exercise)


def test_remove_member_checks_permissions_and_removes_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        invitee,
        outsider,
        project,
        other_project,
    ):
        current_user[0] = reporter
        forbidden = await client.delete(
            f"/api/v1/projects/{project.id}/members/{maintainer.id}"
        )
        assert forbidden.status_code == 403

        current_user[0] = maintainer
        removed = await client.delete(
            f"/api/v1/projects/{project.id}/members/{reporter.id}"
        )
        assert removed.status_code == 204
        assert (
            await session.get(
                ProjectMember,
                {"project_id": project.id, "user_id": reporter.id},
            )
            is None
        )

        missing = await client.delete(
            f"/api/v1/projects/{project.id}/members/{reporter.id}"
        )
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Member not found"

    run_with_database(exercise)
