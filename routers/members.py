import uuid

from fastapi import APIRouter, Depends, Response
from datetime import datetime
from starlette import status
from sqlalchemy.future import select

from db import User, get_async_session, AsyncSession
from schemas import CreateProject, UpdateProject
from users import current_active_user
from models import ProjectMember

router = APIRouter(prefix="/api/v1", tags=["memberships"])


@router.get("/projects/{project_id}/members", status_code=status.HTTP_200_OK)
async def list_project_members(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Endpoint to list all members of a specific project for the authenticated user.
    """
    result = await session.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    project_members = result.scalars().all()
    return project_members
