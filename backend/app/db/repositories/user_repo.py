from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import RefreshToken, User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower().strip()))
        return result.scalar_one_or_none()

    async def create(self, email: str, password_hash: str, settings_json: dict | None = None) -> User:
        user = User(
            email=email.lower().strip(),
            password_hash=password_hash,
            settings_json=settings_json or {},
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def update_settings(self, user: User, settings: dict) -> User:
        user.settings_json = settings
        await self.db.flush()
        return user

    async def list_paginated(
        self,
        *,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        count_stmt = select(func.count(User.id))
        if q:
            like = f"%{q.lower().strip()}%"
            stmt = stmt.where(User.email.ilike(like))
            count_stmt = count_stmt.where(User.email.ilike(like))
        stmt = stmt.order_by(User.id.desc()).limit(page_size).offset((page - 1) * page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()
        return list(rows), int(total)

    async def list_by_ids(self, ids: list[int]) -> list[User]:
        if not ids:
            return []
        result = await self.db.execute(select(User).where(User.id.in_(ids)))
        return list(result.scalars().all())

    async def list_all_active(self) -> list[User]:
        result = await self.db.execute(
            select(User).where(User.disabled_at.is_(None)).order_by(User.id)
        )
        return list(result.scalars().all())

    async def delete_by_id(self, user_id: int) -> None:
        await self.db.execute(delete(User).where(User.id == user_id))


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user_id: int, token_hash: str, expires_at: datetime) -> RefreshToken:
        rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(rt)
        await self.db.flush()
        return rt

    async def get_active(self, token_hash: str) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, token_hash: str) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked_at=datetime.utcnow())
        )
