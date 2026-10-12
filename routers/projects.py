import uuid

from fastapi import APIRouter, Depends
from datetime import datetime
from starlette import status
from sqlalchemy.future import select

from db import User, get_async_session, AsyncSession
from schemas import CreateProject, UpdateProject
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


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProject,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Endpoint to create a new project for the authenticated user.
    """
    new_project = Project(
        owner_id=user.id,
        **body.model_dump(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(new_project)
    await session.commit()
    await session.refresh(new_project)
    return new_project


@router.get("/projects/{project_id}", status_code=status.HTTP_200_OK)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Endpoint to retrieve a specific project by its ID for the authenticated user.
    """
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalars().first()
    if not project:
        return {"detail": "Project not found"}
    return project


@router.patch("/projects/{project_id}", status_code=status.HTTP_200_OK)
async def update_project(
    project_id: uuid.UUID,
    body: UpdateProject,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Endpoint to update a specific project by its ID for the authenticated user.
    """
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalars().first()
    if not project:
        return {"detail": "Project not found"}
    for key, value in body.model_dump().items():
        setattr(project, key, value)
    project.updated_at = datetime.utcnow()

    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project
