from fastapi import APIRouter, Depends
from starlette import status
from sqlalchemy.future import select

from db import User, get_async_session, AsyncSession
from users import current_active_user
from models import Project

router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.get("/projects", status_code=status.HTTP_200_OK)
async def list_projects(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Endpoint to list all projects for the authenticated user.
    """
    result = await session.execute(select(Project).where(Project.owner_id == user.id))
    user_projects = result.scalars().all()
    return user_projects
