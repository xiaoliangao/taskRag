"""Admin panel API.

All routes require `is_admin=True` on the calling user.

Capabilities:
- Users: list/search, view detail, enable/disable, promote/demote admin,
  delete, reset password (sends temp password to email).
- Broadcast: send announcement email to all or selected users.
- Health: check status of LLM provider, embedding provider, Qdrant, Celery,
  Postgres, Redis, SMTP.
"""
from __future__ import annotations

import logging
import secrets
import string
import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentAdminDep, SessionDep
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.db.models.document import TopicDocument
from app.db.models.topic import Topic
from app.db.models.user import User
from app.db.repositories.user_repo import UserRepository
from app.schemas.admin import (
    AdminBroadcastRequest,
    AdminBroadcastResponse,
    AdminHealthComponent,
    AdminHealthReport,
    AdminResetPasswordResponse,
    AdminUserList,
    AdminUserPatch,
    AdminUserRow,
)
from app.services.email_service import (
    EmailNotConfiguredError,
    is_configured as smtp_is_configured,
    send_email,
)

log = logging.getLogger(__name__)

router = APIRouter()


async def _enrich_rows(db, users: list[User]) -> list[AdminUserRow]:
    """Augment user rows with topic_count and document_count via two grouped queries.
    Cheap because the user list is page_size capped."""
    if not users:
        return []
    ids = [u.id for u in users]
    topic_counts = dict(
        (
            await db.execute(
                select(Topic.user_id, func.count(Topic.id))
                .where(Topic.user_id.in_(ids))
                .group_by(Topic.user_id)
            )
        ).all()
    )
    # documents are linked through topics → topic_documents
    doc_counts = dict(
        (
            await db.execute(
                select(Topic.user_id, func.count(TopicDocument.document_id))
                .join(TopicDocument, TopicDocument.topic_id == Topic.id)
                .where(Topic.user_id.in_(ids))
                .group_by(Topic.user_id)
            )
        ).all()
    )
    return [
        AdminUserRow(
            id=u.id,
            email=u.email,
            created_at=u.created_at,
            is_admin=u.is_admin,
            disabled_at=u.disabled_at,
            topic_count=int(topic_counts.get(u.id, 0)),
            document_count=int(doc_counts.get(u.id, 0)),
        )
        for u in users
    ]


# ─────────────────────────── Users ───────────────────────────


@router.get("/users", response_model=AdminUserList)
async def list_users(
    db: SessionDep,
    _admin: CurrentAdminDep,
    q: str | None = Query(default=None, description="Email substring search"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AdminUserList:
    repo = UserRepository(db)
    rows, total = await repo.list_paginated(q=q, page=page, page_size=page_size)
    return AdminUserList(
        items=await _enrich_rows(db, rows),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=AdminUserRow)
async def get_user(user_id: int, db: SessionDep, _admin: CurrentAdminDep) -> AdminUserRow:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    rows = await _enrich_rows(db, [user])
    return rows[0]


@router.patch("/users/{user_id}", response_model=AdminUserRow)
async def patch_user(
    user_id: int,
    body: AdminUserPatch,
    db: SessionDep,
    current_admin: CurrentAdminDep,
) -> AdminUserRow:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    # Guardrails: don't lock yourself out.
    if user.id == current_admin.id:
        if body.is_admin is False:
            raise ForbiddenError("You cannot demote yourself")
        if body.disabled is True:
            raise ForbiddenError("You cannot disable your own account")

    if body.is_admin is not None:
        user.is_admin = bool(body.is_admin)
    if body.disabled is not None:
        user.disabled_at = datetime.now(tz=UTC) if body.disabled else None
    await db.commit()
    await db.refresh(user)
    rows = await _enrich_rows(db, [user])
    return rows[0]


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: SessionDep,
    current_admin: CurrentAdminDep,
) -> Response:
    if user_id == current_admin.id:
        raise ForbiddenError("You cannot delete your own account")
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    await repo.delete_by_id(user_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/reset-password", response_model=AdminResetPasswordResponse)
async def reset_password(
    user_id: int,
    db: SessionDep,
    _admin: CurrentAdminDep,
) -> AdminResetPasswordResponse:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    # 12-char temp password: letters+digits, decent entropy without ambiguity.
    alphabet = string.ascii_letters + string.digits
    new_pw = "".join(secrets.choice(alphabet) for _ in range(12))
    user.password_hash = hash_password(new_pw)
    await db.commit()

    if smtp_is_configured():
        try:
            send_email(
                to=user.email,
                subject="TaskRAG · 临时密码",
                text_body=(
                    "管理员为你重置了 TaskRAG 账户密码。新的临时密码:\n\n"
                    f"  {new_pw}\n\n"
                    "请尽快登录后修改密码。如果不是你本人请求,请联系管理员。"
                ),
                html_body=(
                    "<p>管理员为你重置了 TaskRAG 账户密码。新的临时密码:</p>"
                    f"<pre style='font-size:18px;padding:12px 16px;background:#f6f8fa;border-radius:6px;display:inline-block;'>{new_pw}</pre>"
                    "<p style='color:#666;'>请尽快登录后修改密码。</p>"
                ),
            )
            return AdminResetPasswordResponse(delivery="email", new_password_preview=None)
        except EmailNotConfiguredError:
            pass
        except Exception as exc:
            log.warning("reset password email failed: %s", exc)
    # Fallback: surface the new password to the admin UI so they can hand it over manually.
    log.warning("[ADMIN RESET] user=%s temp_password=%s (SMTP unavailable)", user.email, new_pw)
    return AdminResetPasswordResponse(delivery="log", new_password_preview=new_pw)


# ─────────────────────────── Broadcast ───────────────────────────


@router.post("/broadcast", response_model=AdminBroadcastResponse)
async def broadcast(
    body: AdminBroadcastRequest,
    db: SessionDep,
    _admin: CurrentAdminDep,
) -> AdminBroadcastResponse:
    repo = UserRepository(db)
    if body.target == "all":
        targets = await repo.list_all_active()
    else:
        if not body.user_ids:
            return AdminBroadcastResponse(queued=0, skipped=0, delivery="email")
        targets = await repo.list_by_ids(body.user_ids)
        targets = [u for u in targets if u.disabled_at is None]

    if not smtp_is_configured():
        log.warning("[ADMIN BROADCAST] subject=%s recipients=%d (SMTP not configured)", body.subject, len(targets))
        return AdminBroadcastResponse(queued=0, skipped=len(targets), delivery="log")

    queued = 0
    skipped = 0
    for u in targets:
        prefs = u.settings_json or {}
        if not prefs.get("email_notifications_enabled", True):
            skipped += 1
            continue
        try:
            send_email(
                to=u.email,
                subject=body.subject,
                text_body=body.body,
                html_body=f"<div style='font-family:-apple-system,Helvetica,Arial,sans-serif;'><h2>{body.subject}</h2><p>{body.body.replace(chr(10), '<br/>')}</p><hr/><p style='color:#999;font-size:12px;'>— TaskRAG</p></div>",
            )
            queued += 1
        except Exception as exc:
            log.warning("broadcast email failed to=%s: %s", u.email, exc)
            skipped += 1
    return AdminBroadcastResponse(queued=queued, skipped=skipped, delivery="email")


# ─────────────────────────── Health ───────────────────────────


@router.get("/health", response_model=AdminHealthReport)
async def health(db: SessionDep, _admin: CurrentAdminDep) -> AdminHealthReport:
    components: list[AdminHealthComponent] = []
    settings = get_settings()

    # Postgres
    t0 = time.perf_counter()
    try:
        await db.execute(select(1))
        components.append(
            AdminHealthComponent(
                name="postgres",
                status="ok",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        )
    except Exception as exc:
        components.append(
            AdminHealthComponent(name="postgres", status="fail", detail=str(exc)[:200])
        )

    # Redis
    t0 = time.perf_counter()
    try:
        import redis

        cli = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        cli.ping()
        components.append(
            AdminHealthComponent(
                name="redis",
                status="ok",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        )
    except Exception as exc:
        components.append(
            AdminHealthComponent(name="redis", status="fail", detail=str(exc)[:200])
        )

    # Qdrant
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{settings.qdrant_url}/readyz")
            ok = r.status_code < 500
        components.append(
            AdminHealthComponent(
                name="qdrant",
                status="ok" if ok else "fail",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        )
    except Exception as exc:
        components.append(
            AdminHealthComponent(name="qdrant", status="fail", detail=str(exc)[:200])
        )

    # SMTP
    if smtp_is_configured():
        components.append(
            AdminHealthComponent(
                name="smtp",
                status="ok",
                detail=f"{settings.gmail_smtp_host}:{settings.gmail_smtp_port}",
            )
        )
    else:
        components.append(
            AdminHealthComponent(name="smtp", status="skipped", detail="credentials not set")
        )

    # Celery — peek at registered workers via broker
    try:
        from app.tasks.celery_app import celery_app

        i = celery_app.control.inspect(timeout=1)
        active = i.ping() or {}
        if active:
            components.append(
                AdminHealthComponent(
                    name="celery",
                    status="ok",
                    detail=f"{len(active)} worker(s)",
                )
            )
        else:
            components.append(
                AdminHealthComponent(name="celery", status="warn", detail="no workers responded")
            )
    except Exception as exc:
        components.append(
            AdminHealthComponent(name="celery", status="fail", detail=str(exc)[:200])
        )

    return AdminHealthReport(checked_at=datetime.now(tz=UTC), components=components)
