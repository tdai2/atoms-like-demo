from core.database import Base
from datetime import datetime as PyDateTime
from typing import Optional
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class Bug_fix_logs(Base):
    __tablename__ = "bug_fix_logs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    bug_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    attempt_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artifact_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    changes_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    diff_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    retest_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now)
    updated_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now, onupdate=PyDateTime.now)