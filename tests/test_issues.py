import asyncio
import uuid

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import Base, User
from models import Comment, Issue, IssueLabel, Label, Project, ProjectMember
from routers import issues as issues_router


@pytest.fixture
def run_with_database(tmp_path):
    def run(test):
        async def execute():
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{tmp_path / 'issues.db'}"
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
                    outsider = User(
                        email="outsider@example.com", hashed_password="password"
                    )
                    session.add_all([owner, maintainer, reporter, outsider])
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

                    issue = Issue(
                        project_id=project.id,
                        reporter_id=owner.id,
                        title="Crash on save",
                        body="Saving fails",
                        status="open",
                        priority="high",
                    )
                    other_issue = Issue(
                        project_id=project.id,
                        reporter_id=owner.id,
                        title="Minor visual issue",
                        status="resolved",
                        priority="low",
                    )
                    issue_in_other_project = Issue(
                        project_id=other_project.id,
                        reporter_id=owner.id,
                        title="Private issue",
                    )
                    label = Label(
                        project_id=project.id,
                        name="bug",
                        color="#FF0000",
                    )
                    session.add_all([issue, other_issue, issue_in_other_project, label])
                    await session.flush()
                    session.add_all(
                        [
                            IssueLabel(issue_id=issue.id, label_id=label.id),
                            Comment(
                                issue_id=issue.id,
                                author_id=owner.id,
                                body="First comment",
                            ),
                            Comment(
                                issue_id=issue.id,
                                author_id=reporter.id,
                                body="Second comment",
                            ),
                        ]
                    )
                    await session.commit()

                    app = FastAPI()
                    app.include_router(issues_router.router)
                    current_user = [owner]

                    async def override_user():
                        return current_user[0]

                    async def override_session():
                        yield session

                    app.dependency_overrides[issues_router.current_active_user] = (
                        override_user
                    )
                    app.dependency_overrides[issues_router.get_async_session] = (
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
                            outsider,
                            project,
                            issue,
                            other_issue,
                            issue_in_other_project,
                            label,
                        )
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    return run


def test_list_issues_applies_filters_and_includes_related_data(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        outsider,
        project,
        issue,
        other_issue,
        issue_in_other_project,
        label,
    ):
        current_user[0] = reporter
        response = await client.get(
            f"/api/v1/projects/{project.id}/issues",
            params={
                "status": "open",
                "priority": "high",
                "label": str(label.id),
                "q": "Crash",
                "limit": 20,
                "offset": 0,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        listed_issue = payload["items"][0]
        assert listed_issue["id"] == str(issue.id)
        assert listed_issue["comment_count"] == 2
        assert [item["name"] for item in listed_issue["labels"]] == ["bug"]

    run_with_database(exercise)


def test_list_issues_requires_project_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        outsider,
        project,
        issue,
        other_issue,
        issue_in_other_project,
        label,
    ):
        current_user[0] = outsider
        response = await client.get(f"/api/v1/projects/{project.id}/issues")

        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found."

    run_with_database(exercise)


def test_create_issue_allows_maintainer_and_validates_assignee(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        outsider,
        project,
        issue,
        other_issue,
        issue_in_other_project,
        label,
    ):
        current_user[0] = maintainer
        response = await client.post(
            f"/api/v1/projects/{project.id}/issues",
            json={
                "title": "New issue",
                "body": "Details",
                "priority": "urgent",
                "assignee_id": str(reporter.id),
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["title"] == "New issue"
        assert payload["priority"] == "urgent"
        assert payload["reporter"]["id"] == str(maintainer.id)
        assert payload["assignee"]["id"] == str(reporter.id)
        assert payload["my_role"] == "maintainer"
        assert await session.get(Issue, uuid.UUID(payload["id"])) is not None

        invalid_assignee = await client.post(
            f"/api/v1/projects/{project.id}/issues",
            json={"title": "Invalid assignee", "assignee_id": str(outsider.id)},
        )
        assert invalid_assignee.status_code == 400

        current_user[0] = reporter
        reporter_forbidden = await client.post(
            f"/api/v1/projects/{project.id}/issues",
            json={"title": "Reporter cannot create"},
        )
        assert reporter_forbidden.status_code == 401

    run_with_database(exercise)


def test_get_issue_returns_issue_for_maintainer(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        outsider,
        project,
        issue,
        other_issue,
        issue_in_other_project,
        label,
    ):
        current_user[0] = maintainer
        response = await client.get(
            f"/api/v1/issues/{issue.id}", params={"project_id": str(project.id)}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(issue.id)
        assert payload["title"] == "Crash on save"
        assert payload["my_role"] == "maintainer"
        assert [item["name"] for item in payload["labels"]] == [label.name]

        current_user[0] = reporter
        reporter_forbidden = await client.get(
            f"/api/v1/issues/{issue.id}", params={"project_id": str(project.id)}
        )
        assert reporter_forbidden.status_code == 401

    run_with_database(exercise)


def test_patch_issue_updates_fields_and_enforces_role(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        outsider,
        project,
        issue,
        other_issue,
        issue_in_other_project,
        label,
    ):
        current_user[0] = maintainer
        response = await client.patch(
            f"/api/v1/issues/{issue.id}",
            params={"project_id": str(project.id)},
            json={
                "title": "Updated title",
                "status": "in_progress",
                "priority": "urgent",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "Updated title"
        assert payload["status"] == "in_progress"
        assert payload["priority"] == "urgent"
        assert payload["my_role"] == "maintainer"
        saved_issue = await session.get(Issue, issue.id)
        assert saved_issue.title == "Updated title"

        current_user[0] = reporter
        forbidden = await client.patch(
            f"/api/v1/issues/{issue.id}",
            params={"project_id": str(project.id)},
            json={"title": "Not allowed"},
        )
        assert forbidden.status_code == 401

        current_user[0] = maintainer
        missing = await client.patch(
            f"/api/v1/issues/{uuid.uuid4()}",
            params={"project_id": str(project.id)},
            json={"title": "Missing"},
        )
        assert missing.status_code == 404

    run_with_database(exercise)


def test_delete_issue_removes_issue_and_enforces_role(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        owner,
        maintainer,
        reporter,
        outsider,
        project,
        issue,
        other_issue,
        issue_in_other_project,
        label,
    ):
        current_user[0] = reporter
        reporter_forbidden = await client.delete(
            f"/api/v1/issue/{issue.id}",
            params={"project_id": str(project.id)},
        )
        assert reporter_forbidden.status_code == 401

        current_user[0] = maintainer
        response = await client.delete(
            f"/api/v1/issue/{issue.id}",
            params={"project_id": str(project.id)},
        )
        assert response.status_code == 204
        assert await session.get(Issue, issue.id) is None

        missing = await client.delete(
            f"/api/v1/issue/{issue.id}",
            params={"project_id": str(project.id)},
        )
        assert missing.status_code == 404

        current_user[0] = outsider
        non_member = await client.delete(
            f"/api/v1/issue/{uuid.uuid4()}",
            params={"project_id": str(project.id)},
        )
        assert non_member.status_code == 404

    run_with_database(exercise)
