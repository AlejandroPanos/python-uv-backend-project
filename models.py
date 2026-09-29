from enum import UNIQUE

from db import Base
from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, UUID, Enum


class Project(Base):
    __tablename__ = "projects"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, index=True)
    owner_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, ondelete="RESTRICT"
    )
    name: str = Column(String(max_length=120), nullable=False)
    description: str = Column(String(max_length=500), nullable=True)
    created_at: str = Column(String, nullable=False)
    updated_at: str = Column(String, nullable=False)


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        primary_key=True,
        nullable=False,
        ondelete="CASCADE",
    )
    user_id: UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        primary_key=True,
        nullable=False,
        ondelete="CASCADE",
    )
    role: str = Column(
        Enum("owner", "maintainer", "reporter", name="role_enum"),
        default="reporter",
        nullable=False,
    )
    joined_at: str = Column(String, nullable=False)


class Issue(Base):
    __tablename__ = "issues"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, index=True)
    project_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    reporter_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, ondelete="RESTRICT"
    )
    asignee_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, ondelete="SET NULL"
    )
    title: str = Column(String(max_length=200), nullable=False)
    body: str = Column(String(max_length=500), nullable=True)
    status: str = Column(
        Enum("open", "in_progress", "resolved", "closed", name="status_enum"),
        default="open",
        nullable=False,
    )
    priority: str = Column(
        Enum("low", "medium", "high", "urgent", name="priority_enum"),
        default="medium",
        nullable=False,
    )
    created_at: str = Column(String, nullable=False)
    updated_at: str = Column(String, nullable=False)


class Comment(Base):
    __tablename__ = "comments"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, index=True)
    issue_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False, ondelete="CASCADE"
    )
    author_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, ondelete="RESTRICT"
    )
    body: str = Column(String(max_length=500), nullable=False)
    created_at: str = Column(String, nullable=False)
    updated_at: str = Column(String, nullable=False)


class Label(Base):
    __tablename__ = "labels"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, index=True)
    project_id: UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
        ondelete="CASCADE",
    )
    name: str = Column(String(max_length=50), nullable=False)
    color: str = Column(
        String(max_length=7), nullable=False, default="#888888"
    )  # Hex color code
    UNIQUE(project_id, name)  # Ensure unique label names within a project


class IssueLabel(Base):
    __tablename__ = "issue_labels"

    issue_id: UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("issues.id"),
        primary_key=True,
        nullable=False,
        ondelete="CASCADE",
    )
    label_id: UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("labels.id"),
        primary_key=True,
        nullable=False,
        ondelete="CASCADE",
    )
