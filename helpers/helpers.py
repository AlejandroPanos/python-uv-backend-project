import uuid

from sqlalchemy import select

from db import User, AsyncSession
from models import ProjectMember


async def check_project_membership(
    project_id: uuid.UUID, user: User, session: AsyncSession
) -> bool:
    is_member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )
    return bool(is_member)


async def get_project_member_role(
    project_id: uuid.UUID, user: User, session: AsyncSession
) -> str | None:
    return await session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )
