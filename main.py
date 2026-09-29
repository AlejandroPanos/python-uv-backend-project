from fastapi import FastAPI, Depends

from contextlib import asynccontextmanager

from schemas import UserCreate, UserRead, UserUpdate
from users import auth_backend, current_active_user, fastapi_users
from db import User


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Project Tracker API",
    description="A full backend project tracker with a REST API built with FastAPI.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


# Dummy route to test authentication
@app.get("/authenticated-route")
async def authenticated_route(user: User = Depends(current_active_user)):
    return {"message": f"Hello {user.email}!"}
