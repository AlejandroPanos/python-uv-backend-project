import uuid

from fastapi import APIRouter, Depends, Response
from datetime import datetime
from starlette import status
from sqlalchemy.future import select

from db import User, get_async_session, AsyncSession
from schemas import (
    CreateProjectRequest,
    CreateProjectResponse,
    GetProjectsResponse,
    UpdateProject,
    ProjectSchema,
)
from users import current_active_user
from models import Project, ProjectMember

router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.get("/projects", status_code=status.HTTP_200_OK)
async def list_projects(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int | None = 20,
    offset: int | None = 0,
):
    """
    Endpoint to list all projects for the authenticated user.
    """
    result = await session.execute(
        select(Project).where(Project.owner_id == user.id).limit(limit).offset(offset)
    )
    user_projects = result.scalars().all()
    return GetProjectsResponse(
        items=[ProjectSchema.model_validate(p) for p in user_projects],
        total=len(user_projects),
        limit=limit,
        offset=offset,
    )


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """
    Endpoint to create a new project for the authenticated user and add creator as owner.
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

    # Add the creator as the project owner in the ProjectMember table
    owner_membership = ProjectMember(
        project_id=new_project.id,
        user_id=user.id,
        role="owner",
        joined_at=datetime.utcnow(),
    )
    session.add(owner_membership)
    await session.commit()
    await session.refresh(owner_membership)

    return CreateProjectResponse(
        id=new_project.id,
        name=new_project.name,
        description=new_project.description,
        owner_id=new_project.owner_id,
        my_role="owner",
        member_count=1,
        open_issue_count=0,
        created_at=new_project.created_at,
        updated_at=new_project.updated_at,
    )


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
    return ProjectSchema.model_validate(project)


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
    return ProjectSchema.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Endpoint to delete a specific project by its ID for the authenticated user.
    """
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = result.scalars().first()
    if not project:
        return {"detail": "Project not found"}

    await session.delete(project)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
