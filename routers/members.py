from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from starlette import status
from sqlalchemy.future import select

from db import User, get_async_session, AsyncSession
from schemas import CreateMembership, UpdateMembership
from users import current_active_user
from models import Project, ProjectMember

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


@router.post("/projects/{project_id}/members", status_code=status.HTTP_201_CREATED)
async def create_project_member(
    project_id: uuid.UUID,
    body: CreateMembership,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Endpoint to create a new member for a specific project for the authenticated user.
    """
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Only owner or maintainer can add members
    caller_role = await session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )

    if project.owner_id != user.id and caller_role not in ["owner", "maintainer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or maintainers can add members",
        )

    # Find the invitee via email
    invitee = await session.scalars(
        select(User).where(func.lower(User.email) == body.email.lower())
    )
    invitee = invitee.first()
    if invitee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitee not found"
        )

    # Construct the member object and check for existing membership
    member = ProjectMember(
        project_id=project_id,
        user_id=invitee.id,
        role=body.role,
        joined_at=datetime.utcnow(),
    )
    session.add(member)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Failed to add member: {str(e)}",
        )

    await session.refresh(member)
    return member


@router.post(
    "/projects/{project_id}/members/{user_id}", status_code=status.HTTP_201_CREATED
)
async def update_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMembership,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Endpoint to update the role of a specific project member for the authenticated user.
    """
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Only owner or maintainer can update member roles
    caller_role = await session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )

    if project.owner_id != user.id and caller_role not in ["owner", "maintainer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or maintainers can update member roles",
        )

    member = await session.get(
        ProjectMember, {"project_id": project_id, "user_id": user_id}
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    member.role = body.role
    session.add(member)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Failed to update member role: {str(e)}",
        )

    await session.refresh(member)
    return member
