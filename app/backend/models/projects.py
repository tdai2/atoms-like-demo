from core.database import Base
from datetime import datetime as PyDateTime
from typing import Optional
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class Projects(Base):
    __tablename__ = "projects"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    template_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preview_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latest_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    spec_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    plan_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    artifact_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    test_report_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now)
    updated_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now, onupdate=PyDateTime.now)