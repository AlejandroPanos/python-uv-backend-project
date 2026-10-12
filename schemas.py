import uuid

from fastapi_users import schemas
from pydantic import BaseModel
from typing import Literal


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


# Project Schemas
class CreateProject(BaseModel):
    name: str
    description: str


class UpdateProject(BaseModel):
    name: str
    description: str | None = None


# Membership Schemas
class CreateMembership(BaseModel):
    email: str
    role: Literal["maintainer", "reporter"] = "reporter"


class UpdateMembership(BaseModel):
    role: Literal["maintainer", "reporter"] = "reporter"
