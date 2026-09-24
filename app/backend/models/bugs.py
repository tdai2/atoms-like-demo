from core.database import Base
from datetime import datetime as PyDateTime
from typing import Optional
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class Bugs(Base):
    __tablename__ = "bugs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reproduction: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    related_case_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fix_attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latest_fix_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now)
    updated_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now, onupdate=PyDateTime.now)