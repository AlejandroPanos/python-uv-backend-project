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

from schemas import GetIssuesCommentsResponse, CommentSchemaForList

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
