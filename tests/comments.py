import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import Base, User
from models import Comment, Issue, Project, ProjectMember
from routers.comments import (
    create_comment_for_issue,
    delete_comment,
    get_comments_for_issue,
    update_comment,
)
from schemas import PatchCommentRequest, PostCommentRequest


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

                    return await test(
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
    async def exercise(session, author, _, __, project, issue, ___):
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

        response = await get_comments_for_issue(
            issue.id, project.id, author, session, limit=2, offset=1
        )

        assert response.total == 3
        assert response.limit == 2
        assert response.offset == 1
        assert [comment.body for comment in response.items] == [
            "Comment 2",
            "Comment 3",
        ]

    run_with_database(exercise)


def test_list_comments_requires_project_membership(run_with_database):
    async def exercise(session, _, __, non_member, project, issue, ___):
        with pytest.raises(HTTPException) as error:
            await get_comments_for_issue(issue.id, project.id, non_member, session)

        assert error.value.status_code == 404

    run_with_database(exercise)


def test_create_comment_persists_for_issue_in_project(run_with_database):
    async def exercise(session, author, _, __, project, issue, other_issue):
        response = await create_comment_for_issue(
            issue.id,
            project.id,
            PostCommentRequest(body="  A useful note  "),
            author,
            session,
        )

        assert response.issue_id == issue.id
        assert response.body == "A useful note"
        assert response.author.id == author.id
        assert await session.get(Comment, response.id) is not None

        with pytest.raises(HTTPException) as error:
            await create_comment_for_issue(
                other_issue.id,
                project.id,
                PostCommentRequest(body="Wrong project"),
                author,
                session,
            )
        assert error.value.status_code == 404

    run_with_database(exercise)


def test_update_comment_requires_author_and_existing_comment(run_with_database):
    async def exercise(session, author, member, _, project, issue, ___):
        comment = Comment(
            issue_id=issue.id,
            author_id=author.id,
            body="Original",
        )
        session.add(comment)
        await session.commit()

        response = await update_comment(
            project.id,
            comment.id,
            PatchCommentRequest(body="  Updated  "),
            author,
            session,
        )
        assert response.body == "Updated"

        with pytest.raises(HTTPException) as forbidden:
            await update_comment(
                project.id,
                comment.id,
                PatchCommentRequest(body="Not allowed"),
                member,
                session,
            )
        assert forbidden.value.status_code == 403

        with pytest.raises(HTTPException) as missing:
            await update_comment(
                project.id,
                uuid.uuid4(),
                PatchCommentRequest(body="Missing"),
                author,
                session,
            )
        assert missing.value.status_code == 404

    run_with_database(exercise)


def test_delete_comment_requires_author_and_removes_comment(run_with_database):
    async def exercise(session, author, member, _, project, issue, ___):
        comment = Comment(
            issue_id=issue.id,
            author_id=author.id,
            body="Delete me",
        )
        session.add(comment)
        await session.commit()

        with pytest.raises(HTTPException) as forbidden:
            await delete_comment(project.id, comment.id, member, session)
        assert forbidden.value.status_code == 403

        await delete_comment(project.id, comment.id, author, session)
        assert await session.get(Comment, comment.id) is None

        with pytest.raises(HTTPException) as missing:
            await delete_comment(project.id, comment.id, author, session)
        assert missing.value.status_code == 404

    run_with_database(exercise)
