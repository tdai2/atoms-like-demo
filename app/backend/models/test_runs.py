from core.database import Base
from datetime import datetime as PyDateTime
from typing import Optional
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class Test_runs(Base):
    __tablename__ = "test_runs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    triggered_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    failed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    results_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now)
    updated_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now, onupdate=PyDateTime.now)