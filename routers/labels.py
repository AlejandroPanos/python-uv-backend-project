import uuid

from fastapi import APIRouter, Depends, Query, HTTPException
from starlette import status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from db import User, get_async_session, AsyncSession
from models import Comment, Issue
from helpers.helpers import check_project_membership
from users import current_active_user

router = APIRouter(prefix="/api/v1", tags=["labels"])
