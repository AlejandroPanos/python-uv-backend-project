import uuid

from fastapi import APIRouter, Depends, Query, HTTPException
from starlette import status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from db import User, get_async_session, AsyncSession
from models import Comment, Issue
from helpers.helpers import check_project_membership
from users import current_active_user

router = APIRouter(prefix="/api/v1", tags=["labels"])


@router.get(
    "/projects/{project_id}/labels",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
)
async def get_labels_for_project(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List labels for a project. Any project member can read them."""
    is_member = await check_project_membership(project_id, user, session)
    if not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    stmt = select(Issue.label).where(Issue.project_id == project_id).distinct()
    labels = (await session.scalars(stmt)).all()
    return labels
