import uuid

from fastapi import APIRouter, Depends, Response, Query, HTTPException
from datetime import datetime
from starlette import status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from db import User, get_async_session, AsyncSession
from models import Comment, IssueLabel, ProjectMember, Issue
from helpers.helpers import check_project_membership, get_project_member_role
from users import current_active_user

from schemas import (
    GetIssuesCommentsResponse,
    CommentSchemaForList,
    PostCommentRequest,
    PatchCommentRequest,
)

router = APIRouter(prefix="/api/v1", tags=["comments"])


@router.get(
    "/issues/{issue_id}/comments",
    response_model=GetIssuesCommentsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_comments_for_issue(
    issue_id: uuid.UUID,
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List comments for an issue. Any project member can read them."""
    is_member = await check_project_membership(project_id, user, session)
    if not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    # Comment must belong to this issue, and the issue to this project
    filters = (Comment.issue_id == issue_id, Issue.project_id == project_id)

    total = await session.scalar(
        select(func.count(Comment.id))
        .join(Issue, Comment.issue_id == Issue.id)
        .where(*filters)
    )

    stmt = (
        select(Comment)
        .join(Issue, Comment.issue_id == Issue.id)
        .where(*filters)
        .options(joinedload(Comment.author))
        .order_by(Comment.created_at.asc(), Comment.id)
        .limit(limit)
        .offset(offset)
    )
    comments = (await session.scalars(stmt)).all()

    return GetIssuesCommentsResponse(
        items=[CommentSchemaForList.model_validate(c) for c in comments],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/issues/{issue_id}/comments",
    response_model=CommentSchemaForList,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment_for_issue(
    issue_id: uuid.UUID,
    project_id: uuid.UUID,
    comment: PostCommentRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    is_member = await check_project_membership(project_id, user, session)
    if not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    issue = await session.get(Issue, issue_id)
    if not issue or issue.project_id != project_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Issue not found in this project."
        )

    new_comment = Comment(
        issue_id=issue_id,
        body=comment.body,
        author_id=user.id,
    )
    session.add(new_comment)
    await session.commit()

    # Reload with the author eagerly loaded so serialization doesn't lazy-load
    saved = await session.scalar(
        select(Comment)
        .options(joinedload(Comment.author))
        .where(Comment.id == new_comment.id)
    )
    return CommentSchemaForList.model_validate(saved)


@router.patch(
    "/comments/{comment_id}",
    response_model=CommentSchemaForList,
    status_code=status.HTTP_200_OK,
)
async def update_comment(
    project_id: uuid.UUID,
    comment_id: uuid.UUID,
    comment: PatchCommentRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    is_member = await check_project_membership(project_id, user, session)
    if not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    comment_obj = await session.get(Comment, comment_id)
    if not comment_obj:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Comment not found in this project."
        )

    if comment_obj.author_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You do not have permission to edit this comment.",
        )

    if comment.body is not None:
        comment_obj.body = comment.body

    session.add(comment_obj)
    await session.commit()

    saved = await session.scalar(
        select(Comment)
        .options(joinedload(Comment.author))
        .where(Comment.id == comment_obj.id)
    )
    return CommentSchemaForList.model_validate(saved)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    project_id: uuid.UUID,
    comment_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    is_member = await check_project_membership(project_id, user, session)
    if not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    comment_obj = await session.get(Comment, comment_id)
    if not comment_obj:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Comment not found in this project."
        )

    if comment_obj.author_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You do not have permission to delete this comment.",
        )

    await session.delete(comment_obj)
    await session.commit()
