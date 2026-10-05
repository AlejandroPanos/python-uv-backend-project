from fastapi import APIRouter, Depends
from starlette import status

from db import User
from users import current_active_user
from models import Project

router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.get("/projects", status_code=status.HTTP_200_OK)
async def list_projects(_: User = Depends(current_active_user)):
    """
    Endpoint to list all projects for the authenticated user.
    """
    return Project.objects.all()
