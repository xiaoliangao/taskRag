from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_topics_user_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default="{}")
    sources: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default="{}")
    schedule_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="daily")
    schedule_time: Mapped[str] = mapped_column(Text, nullable=False, server_default="09:00")
    schedule_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_results_per_source_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)


class TopicSourceState(Base, TimestampMixin):
    __tablename__ = "topic_source_states"

    topic_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
