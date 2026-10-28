import asyncio
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import Base, User
from models import Label, Project, ProjectMember
from routers import labels as labels_router


@pytest.fixture
def run_with_database(tmp_path):
    def run(test):
        async def execute():
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{tmp_path / 'labels.db'}"
            )
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
                                user_id=member.id,
                                role="reporter",
                            ),
                        ]
                    )

                    alpha_label = Label(
                        project_id=project.id,
                        name="alpha",
                        color="#112233",
                    )
                    zeta_label = Label(
                        project_id=project.id,
                        name="zeta",
                        color="#445566",
                    )
                    other_project_label = Label(
                        project_id=other_project.id,
                        name="private",
                        color="#778899",
                    )
                    session.add_all([alpha_label, zeta_label, other_project_label])
                    await session.commit()

                    app = FastAPI()
                    app.include_router(labels_router.router)
                    current_user = [owner]

                    async def override_user():
                        return current_user[0]

                    async def override_session():
                        yield session

                    app.dependency_overrides[labels_router.current_active_user] = (
                        override_user
                    )
                    app.dependency_overrides[labels_router.get_async_session] = (
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
                            other_project,
                            alpha_label,
                            zeta_label,
                            other_project_label,
                        )
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    return run


def test_list_labels_is_sorted_and_project_scoped(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        other_project,
        alpha_label,
        zeta_label,
        other_project_label,
    ):
        current_user[0] = member
        response = await client.get(f"/api/v1/projects/{project.id}/labels")

        assert response.status_code == 200
        payload = response.json()
        assert [label["name"] for label in payload] == ["alpha", "zeta"]
        assert [label["color"] for label in payload] == ["#112233", "#445566"]

    run_with_database(exercise)


def test_list_labels_requires_project_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        other_project,
        alpha_label,
        zeta_label,
        other_project_label,
    ):
        current_user[0] = outsider
        response = await client.get(f"/api/v1/projects/{project.id}/labels")

        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found."

    run_with_database(exercise)


def test_create_label_trims_fields_and_rejects_duplicates(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        other_project,
        alpha_label,
        zeta_label,
        other_project_label,
    ):
        current_user[0] = member
        response = await client.post(
            f"/api/v1/projects/{project.id}/labels",
            json={"name": "  triage  ", "color": "#A1B2C3"},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["name"] == "triage"
        assert payload["color"] == "#A1B2C3"
        assert await session.get(Label, uuid.UUID(payload["id"])) is not None

        duplicate = await client.post(
            f"/api/v1/projects/{project.id}/labels",
            json={"name": "triage", "color": "#010203"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "Label already exists."

    run_with_database(exercise)


def test_create_label_validates_input_and_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        other_project,
        alpha_label,
        zeta_label,
        other_project_label,
    ):
        invalid_name = await client.post(
            f"/api/v1/projects/{project.id}/labels",
            json={"name": "   ", "color": "#112233"},
        )
        assert invalid_name.status_code == 422

        invalid_color = await client.post(
            f"/api/v1/projects/{project.id}/labels",
            json={"name": "valid", "color": "red"},
        )
        assert invalid_color.status_code == 422

        current_user[0] = outsider
        forbidden = await client.post(
            f"/api/v1/projects/{project.id}/labels",
            json={"name": "forbidden", "color": "#112233"},
        )
        assert forbidden.status_code == 404

    run_with_database(exercise)


def test_update_label_changes_fields_and_checks_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        other_project,
        alpha_label,
        zeta_label,
        other_project_label,
    ):
        current_user[0] = member
        zeta_label_id = zeta_label.id
        outsider_id = outsider.id
        response = await client.patch(
            f"/api/v1/labels/{alpha_label.id}",
            json={"name": "  priority  ", "color": "#ABCDEF"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "priority"
        assert response.json()["color"] == "#ABCDEF"

        duplicate = await client.patch(
            f"/api/v1/labels/{alpha_label.id}",
            json={"name": "zeta"},
        )
        assert duplicate.status_code == 409

        missing = await client.patch(
            f"/api/v1/labels/{uuid.uuid4()}", json={"name": "missing"}
        )
        assert missing.status_code == 404

        current_user[0] = await session.get(User, outsider_id)
        forbidden = await client.patch(
            f"/api/v1/labels/{zeta_label_id}", json={"name": "forbidden"}
        )
        assert forbidden.status_code == 404

    run_with_database(exercise)


def test_delete_label_removes_label_and_checks_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        member,
        outsider,
        project,
        other_project,
        alpha_label,
        zeta_label,
        other_project_label,
    ):
        current_user[0] = member
        response = await client.delete(f"/api/v1/labels/{alpha_label.id}")

        assert response.status_code == 204
        assert await session.get(Label, alpha_label.id) is None

        missing = await client.delete(f"/api/v1/labels/{alpha_label.id}")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Label not found."

        current_user[0] = outsider
        forbidden = await client.delete(f"/api/v1/labels/{zeta_label.id}")
        assert forbidden.status_code == 404
        assert forbidden.json()["detail"] == "Project not found."

    run_with_database(exercise)
