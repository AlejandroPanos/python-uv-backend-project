import uuid
import re
from datetime import datetime
from fastapi_users import schemas
from datetime import datetime
from pydantic import field_validator, ConfigDict
from pydantic import BaseModel, Field
from typing import Literal


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


# ---------------------------
# Project Schemas
# ---------------------------
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


# ---------------------------
# Membership Schemas
# ---------------------------
class CreateMembership(BaseModel):
    email: str
    role: Literal["maintainer", "reporter"] = "reporter"


class UpdateMembership(BaseModel):
    role: Literal["maintainer", "reporter"] = "reporter"


# ---------------------------
# Issues schemas
# ---------------------------
class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str


class LabelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str


class IssueSchemaForList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: Literal["open", "in_progress", "resolved", "closed"]
    priority: Literal["low", "medium", "high", "urgent"]
    reporter: UserSummary
    assignee: UserSummary | None = None
    labels: list[LabelSchema] = []
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime


class IssueListResponse(BaseModel):
    items: list[IssueSchemaForList] = []
    total: int = 0
    limit: int = 20
    offset: int = 0


class PostIssueRequest(BaseModel):
    title: str
    body: str | None = None
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    assignee_id: uuid.UUID | None = None
    label_ids: list[uuid.UUID] = []


class PostIssueResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    body: str | None = None
    status: Literal["open", "in_progress", "resolved", "closed"]
    priority: Literal["low", "medium", "high", "urgent"]
    reporter: UserSummary
    assignee: UserSummary | None = None
    labels: list[LabelSchema] = []
    comment_count: int = 0
    my_role: Literal["owner", "maintainer", "reporter"]
    created_at: datetime
    updated_at: datetime


class GetIssueResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    body: str | None = None
    status: Literal["open", "in_progress", "resolved", "closed"]
    priority: Literal["low", "medium", "high", "urgent"]
    reporter: UserSummary
    assignee: UserSummary | None = None
    labels: list[LabelSchema] = []
    comment_count: int = 0
    my_role: Literal["owner", "maintainer", "reporter"]
    created_at: datetime
    updated_at: datetime


class PatchIssueRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    assignee_id: uuid.UUID | None = None
    label_ids: list[uuid.UUID] | None = None


class PatchIssueResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    body: str | None = None
    status: Literal["open", "in_progress", "resolved", "closed"]
    priority: Literal["low", "medium", "high", "urgent"]
    reporter: UserSummary
    assignee: UserSummary | None = None
    labels: list[LabelSchema] = []
    comment_count: int = 0
    my_role: Literal["owner", "maintainer", "reporter"]
    created_at: datetime
    updated_at: datetime


# ---------------------------
# Comment schemas
# ---------------------------
class CommentSchemaForList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: uuid.UUID
    body: str
    author: UserSummary
    created_at: datetime
    updated_at: datetime


class GetIssuesCommentsResponse(BaseModel):
    items: list[CommentSchemaForList] = []
    total: int = 0
    limit: int = 20
    offset: int = 0


class PostCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Body cannot be empty or just whitespace")
        return v


class PatchCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Body cannot be empty or just whitespace")
        return v


# ---------------------------
# Label schemas
# ---------------------------
class GetLabelListSchema(BaseModel):
    id: uuid.UUID
    name: str
    color: str


class PostLabelSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(min_length=1, max_length=7)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty or just whitespace")
        return v

    @field_validator("color")
    @classmethod
    def color_not_blank(cls, v: str) -> str:
        color_pattern = r"^#[0-9a-fA-F]{6}$"
        v = v.strip()
        if not v:
            raise ValueError("Color cannot be empty or just whitespace")
        if not re.match(color_pattern, v):
            raise ValueError("Color must be a valid hex code like '#FFFFFF'")
        return v


class PatchLabelSchema(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, min_length=1, max_length=7)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty or just whitespace")
        return v

    @field_validator("color")
    @classmethod
    def color_not_blank(cls, v: str) -> str:
        if v is None:
            return v
        color_pattern = r"^#[0-9a-fA-F]{6}$"
        v = v.strip()
        if not v:
            raise ValueError("Color cannot be empty or just whitespace")
        if not re.match(color_pattern, v):
            raise ValueError("Color must be a valid hex code like '#FFFFFF'")
        return v
