from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Response, Query, HTTPException
from datetime import datetime
from starlette import status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from db import User, get_async_session, AsyncSession
from models import Comment, IssueLabel, ProjectMember, Issue
from users import current_active_user
from schemas import IssueSchemaForList, IssueListResponse

router = APIRouter(prefix="/api/v1", tags=["issues"])

SORT_COLUMNS = {
    "created_at": Issue.created_at,
    "updated_at": Issue.updated_at,
    "priority": Issue.priority,
}


@router.get(
    "/projects/{project_id}/issues",
    response_model=IssueListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_issues(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    status_filter: Literal["open", "in_progress", "resolved", "closed"] | None = Query(
        None, alias="status"
    ),
    priority: Literal["low", "medium", "high", "urgent"] | None = None,
    assignee: uuid.UUID | None = None,
    label: uuid.UUID | None = None,
    q: str | None = None,
    sort: Literal["created_at", "updated_at", "priority"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Endpoint to list all issues for a specific project for the authenticated user.
    """
    is_member = session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )

    if not is_member:
        raise HTTPException(status_code=404, detail="Project not found.")

    comment_count = (
        select(func.count(Comment.id))
        .where(Comment.issue_id == Issue.id)
        .correlate(Issue)
        .scalar_subquery()
    )

    stmt = (
        select(Issue, comment_count.label("comment_count"))
        .options(
            joinedload(Issue.reporter),
            joinedload(Issue.assignee),
            selectinload(Issue.labels),
        )
        .where(Issue.project_id == project_id)
    )

    if status_filter:
        stmt = stmt.where(Issue.status == status_filter)
    if priority:
        stmt = stmt.where(Issue.priority == priority)
    if assignee:
        stmt = stmt.where(Issue.assignee_id == assignee)
    if label:
        issues_with_label = select(IssueLabel.issue_id).where(
            IssueLabel.label_id == label
        )
        stmt = stmt.where(Issue.id.in_(issues_with_label))
    if q:
        stmt = stmt.where(Issue.title.ilike(f"%{q}%"))

    column = SORT_COLUMNS[sort]
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc(), Issue.id)
    stmt = stmt.limit(limit).offset(offset)

    rows = (await session.execute(stmt)).all()

    items = [
        IssueSchemaForList.model_validate(issue).model_copy(
            update={"comment_count": count}
        )
        for issue, count in rows
    ]

    return IssueListResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
    )
