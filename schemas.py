import uuid
from datetime import datetime
from fastapi_users import schemas
from pydantic import ConfigDict
from pydantic import BaseModel
from typing import Literal


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


# Project Schemas
class ProjectSchema(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    owner_id: uuid.UUID
    my_role: Literal["owner", "maintainer", "reporter"]
    member_count: int
    open_issue_count: int = 0
    created_at: datetime
    updated_at: datetime


class GetProjectsResponse(BaseModel):
    items: list[ProjectSchema] = []
    total: int = 0
    limit: int = 20
    offset: int = 0


class CreateProjectRequest(BaseModel):
    name: str
    description: str


class CreateProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID
    my_role: Literal["owner", "maintainer", "reporter"] = "owner"
    member_count: int
    open_issue_count: int = 0
    created_at: datetime
    updated_at: datetime


class UpdateProject(BaseModel):
    name: str
    description: str | None = None


# Membership Schemas
class CreateMembership(BaseModel):
    email: str
    role: Literal["maintainer", "reporter"] = "reporter"


class UpdateMembership(BaseModel):
    role: Literal["maintainer", "reporter"] = "reporter"
