import uuid

from aiosqlite import IntegrityError
from fastapi import APIRouter, Depends, Query, HTTPException
from starlette import status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from db import User, get_async_session, AsyncSession
from models import Comment, Label
from helpers.helpers import check_project_membership
from users import current_active_user
from schemas import PostLabelSchema, GetLabelListSchema, PatchLabelSchema

router = APIRouter(prefix="/api/v1", tags=["labels"])


@router.get(
    "/projects/{project_id}/labels",
    response_model=list[GetLabelListSchema],
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

    stmt = select(Label).where(Label.project_id == project_id).order_by(Label.name)
    labels = (await session.scalars(stmt)).all()
    return [
        GetLabelListSchema(id=label.id, name=label.name, color=label.color)
        for label in labels
    ]


@router.post(
    "/projects/{project_id}/labels",
    response_model=GetLabelListSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_label_for_project(
    project_id: uuid.UUID,
    label: PostLabelSchema,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    is_member = await check_project_membership(project_id, user, session)
    if not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")

    new_label = Label(project_id=project_id, name=label.name, color=label.color)
    session.add(new_label)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Label already exists.")
    await session.refresh(new_label)
    return new_label  # needs from_attributes=True on GetLabelListSchema


@router.patch(
    "/labels/{label_id}",
    response_model=GetLabelListSchema,
    status_code=status.HTTP_200_OK,
)
async def update_label(
    label_id: uuid.UUID,
    label: PatchLabelSchema,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    existing_label = await session.scalar(select(Label).where(Label.id == label_id))
    if not existing_label or not await check_project_membership(
        existing_label.project_id, user, session
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")

    if label.name is not None:
        existing_label.name = label.name
    if label.color is not None:
        existing_label.color = label.color

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Label already exists.")
    await session.refresh(existing_label)
    return GetLabelListSchema(
        id=existing_label.id, name=existing_label.name, color=existing_label.color
    )


@router.delete(
    "/labels/{label_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT
)
async def delete_label(
    label_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a label. Any project member can delete labels."""
    stmt = select(Label).where(Label.id == label_id)
    existing_label = await session.scalar(stmt)
    if not existing_label:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Label not found.")

    is_member = await check_project_membership(existing_label.project_id, user, session)
    if not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")

    await session.delete(existing_label)
    await session.commit()
