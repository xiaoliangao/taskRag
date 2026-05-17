from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserMe,
    UserPublic,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: SessionDep) -> UserPublic:
    user = await AuthService(db).register(body.email, body.password)
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db: SessionDep) -> TokenPair:
    return await AuthService(db).login(body.email, body.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: SessionDep) -> TokenPair:
    return await AuthService(db).refresh(body.refresh_token)


@router.get("/me", response_model=UserMe)
async def me(current_user: CurrentUserDep) -> UserMe:
    return UserMe(id=current_user.id, email=current_user.email, settings=current_user.settings_json or {})


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, db: SessionDep, _: CurrentUserDep) -> Response:
    await AuthService(db).logout(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
