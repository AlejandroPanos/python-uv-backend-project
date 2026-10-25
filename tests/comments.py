import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import Base, User
from models import Comment, Issue, Project, ProjectMember
from routers import comments as comments_router


@pytest.fixture
def run_with_database(tmp_path):
    def run(test):
        async def execute():
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{tmp_path / 'comments.db'}"
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            try:
                async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
                async with async_session_maker() as session:
                    author = User(
                        email="author@example.com", hashed_password="password"
                    )
                    member = User(
                        email="member@example.com", hashed_password="password"
                    )
                    non_member = User(
                        email="outsider@example.com", hashed_password="password"
                    )
                    session.add_all([author, member, non_member])
                    await session.flush()

                    project = Project(owner_id=author.id, name="Project")
                    other_project = Project(owner_id=author.id, name="Other project")
                    session.add_all([project, other_project])
                    await session.flush()
                    session.add_all(
                        [
                            ProjectMember(
                                project_id=project.id,
                                user_id=author.id,
                                role="owner",
                            ),
                            ProjectMember(
                                project_id=project.id,
                                user_id=member.id,
                                role="reporter",
                            ),
                        ]
                    )

                    issue = Issue(
                        project_id=project.id,
                        reporter_id=author.id,
                        title="Issue",
                    )
                    issue_in_other_project = Issue(
                        project_id=other_project.id,
                        reporter_id=author.id,
                        title="Other issue",
                    )
                    session.add_all([issue, issue_in_other_project])
                    await session.commit()

                    app = FastAPI()
                    app.include_router(comments_router.router)
                    current_user = [author]

                    async def override_user():
                        return current_user[0]

                    async def override_session():
                        yield session

                    app.dependency_overrides[comments_router.current_active_user] = (
                        override_user
                    )
                    app.dependency_overrides[comments_router.get_async_session] = (
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
                            author,
                            member,
                            non_member,
                            project,
                            issue,
                            issue_in_other_project,
                        )
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    return run


def test_list_comments_is_ordered_and_paginated(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        author,
        member,
        non_member,
        project,
        issue,
        other_issue,
    ):
        comments = [
            Comment(
                id=uuid.UUID(int=comment_id),
                issue_id=issue.id,
                author_id=author.id,
                body=f"Comment {comment_id}",
                created_at=datetime(2025, 1, 1, 0, 0, comment_id, tzinfo=timezone.utc),
            )
            for comment_id in (1, 2, 3)
        ]
        session.add_all(comments)
        await session.commit()

        response = await client.get(
            f"/api/v1/issues/{issue.id}/comments",
            params={"project_id": str(project.id), "limit": 2, "offset": 1},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 3
        assert payload["limit"] == 2
        assert payload["offset"] == 1
        assert [comment["body"] for comment in payload["items"]] == [
            "Comment 2",
            "Comment 3",
        ]

    run_with_database(exercise)


def test_list_comments_requires_project_membership(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        author,
        member,
        non_member,
        project,
        issue,
        other_issue,
    ):
        current_user[0] = non_member
        response = await client.get(
            f"/api/v1/issues/{issue.id}/comments",
            params={"project_id": str(project.id)},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found."

    run_with_database(exercise)


def test_create_comment_persists_for_issue_in_project(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        author,
        member,
        non_member,
        project,
        issue,
        other_issue,
    ):
        response = await client.post(
            f"/api/v1/issues/{issue.id}/comments",
            params={"project_id": str(project.id)},
            json={"body": "  A useful note  "},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["issue_id"] == str(issue.id)
        assert payload["body"] == "A useful note"
        assert payload["author"]["id"] == str(author.id)
        assert await session.get(Comment, uuid.UUID(payload["id"])) is not None

        wrong_project = await client.post(
            f"/api/v1/issues/{other_issue.id}/comments",
            params={"project_id": str(project.id)},
            json={"body": "Wrong project"},
        )
        assert wrong_project.status_code == 404

    run_with_database(exercise)


def test_update_comment_requires_author_and_existing_comment(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        author,
        member,
        non_member,
        project,
        issue,
        other_issue,
    ):
        comment = Comment(
            issue_id=issue.id,
            author_id=author.id,
            body="Original",
        )
        session.add(comment)
        await session.commit()

        response = await client.patch(
            f"/api/v1/comments/{comment.id}",
            params={"project_id": str(project.id)},
            json={"body": "  Updated  "},
        )
        assert response.status_code == 200
        assert response.json()["body"] == "Updated"

        current_user[0] = member
        forbidden = await client.patch(
            f"/api/v1/comments/{comment.id}",
            params={"project_id": str(project.id)},
            json={"body": "Not allowed"},
        )
        assert forbidden.status_code == 403

        current_user[0] = author
        missing = await client.patch(
            f"/api/v1/comments/{uuid.uuid4()}",
            params={"project_id": str(project.id)},
            json={"body": "Missing"},
        )
        assert missing.status_code == 404

    run_with_database(exercise)


def test_delete_comment_requires_author_and_removes_comment(run_with_database):
    async def exercise(
        client,
        current_user,
        session,
        author,
        member,
        non_member,
        project,
        issue,
        other_issue,
    ):
        comment = Comment(
            issue_id=issue.id,
            author_id=author.id,
            body="Delete me",
        )
        session.add(comment)
        await session.commit()

        current_user[0] = member
        forbidden = await client.delete(
            f"/api/v1/comments/{comment.id}",
            params={"project_id": str(project.id)},
        )
        assert forbidden.status_code == 403

        current_user[0] = author
        deleted = await client.delete(
            f"/api/v1/comments/{comment.id}",
            params={"project_id": str(project.id)},
        )
        assert deleted.status_code == 204
        assert await session.get(Comment, comment.id) is None

        missing = await client.delete(
            f"/api/v1/comments/{comment.id}",
            params={"project_id": str(project.id)},
        )
        assert missing.status_code == 404

    run_with_database(exercise)
