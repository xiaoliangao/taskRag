from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUserDep, SessionDep
from app.core.config import get_settings
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

# slowapi limiter is optional — wrap with try/except so route still imports if dep missing
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    _limiter = Limiter(key_func=get_remote_address)
    _settings = get_settings()
    register_limit = _limiter.limit(_settings.rate_limit_register)
    login_limit = _limiter.limit(_settings.rate_limit_login)
except ImportError:  # pragma: no cover
    def _noop(*_a, **_kw):
        def _decorator(fn):
            return fn
        return _decorator

    register_limit = _noop()
    login_limit = _noop()


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
@register_limit
async def register(request: Request, body: RegisterRequest, db: SessionDep) -> UserPublic:
    user = await AuthService(db).register(body.email, body.password)
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenPair)
@login_limit
async def login(request: Request, body: LoginRequest, db: SessionDep) -> TokenPair:
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
