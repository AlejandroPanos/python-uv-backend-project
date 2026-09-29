from db import Base
from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, UUID


class Project(Base):
    __tablename__ = "projects"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, index=True)
    owner_id: UUID = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    name: str = Column(String(max_length=120), nullable=False)
    description: str = Column(String(max_length=500), nullable=True)
    created_at: str = Column(String, nullable=False)
    updated_at: str = Column(String, nullable=False)
