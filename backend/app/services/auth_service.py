from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DuplicateResourceError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.models.user import User
from app.db.repositories.user_repo import RefreshTokenRepository, UserRepository
from app.schemas.auth import TokenPair, UserPublic

DEFAULT_USER_SETTINGS = {
    "timezone": "Asia/Singapore",
    "email_notifications_enabled": True,
    "preferred_llm_provider": "deepseek",
    "preferred_llm_model": "deepseek-chat",
    "preferred_embedding_provider": "siliconflow",
}


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.tokens = RefreshTokenRepository(db)

    async def register(self, email: str, password: str) -> User:
        existing = await self.users.get_by_email(email)
        if existing:
            raise DuplicateResourceError("Email already registered", {"field": "email"})
        user = await self.users.create(
            email=email,
            password_hash=hash_password(password),
            settings_json=dict(DEFAULT_USER_SETTINGS),
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.users.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")
        return await self._issue_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        token_hash = hash_refresh_token(refresh_token)
        rt = await self.tokens.get_active(token_hash)
        if not rt:
            raise UnauthorizedError("Invalid refresh token")
        if rt.expires_at.replace(tzinfo=UTC) < datetime.now(tz=UTC):
            raise UnauthorizedError("Refresh token expired")
        # Rotate
        await self.tokens.revoke(token_hash)
        user = await self.users.get_by_id(rt.user_id)
        if not user:
            raise UnauthorizedError("User no longer exists")
        return await self._issue_pair(user)

    async def logout(self, refresh_token: str) -> None:
        await self.tokens.revoke(hash_refresh_token(refresh_token))
        await self.db.commit()

    async def _issue_pair(self, user: User) -> TokenPair:
        access, expires_in = create_access_token(user.id)
        raw_refresh, hashed, exp = create_refresh_token()
        await self.tokens.create(user_id=user.id, token_hash=hashed, expires_at=exp)
        await self.db.commit()
        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=expires_in,
            user=UserPublic.model_validate(user),
        )
