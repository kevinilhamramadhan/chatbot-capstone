"""Conversation log — mirrors the team's `chatbot_conversations` table locally.

When the backend eventually owns this table, rows can be migrated 1:1.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationLog(Base):
    __tablename__ = "chatbot_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wa_number: Mapped[str] = mapped_column(String(32), index=True)

    # "in" = from customer, "out" = from bot/system (incl. proactive notifs).
    direction: Mapped[str] = mapped_column(String(4))
    content: Mapped[str] = mapped_column(Text)

    # Best-effort detected intent / routing decision for analytics.
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
