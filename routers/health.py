from fastapi import APIRouter, Depends
from starlette import status

from db import User
from users import current_active_user

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(_: User = Depends(current_active_user)):
    """
    Health check endpoint to verify that the API is running and the user is authenticated.
    """
    return {"status": "healthy"}
