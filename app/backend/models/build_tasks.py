from core.database import Base
from datetime import datetime as PyDateTime
from typing import Optional
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class Build_tasks(Base):
    __tablename__ = "build_tasks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    run_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    stage_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stage_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage_state: Mapped[str] = mapped_column(String, nullable=False)
    stage_log: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    output_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now)
    updated_at: Mapped[Optional[PyDateTime]] = mapped_column(DateTime(timezone=True), default=PyDateTime.now, onupdate=PyDateTime.now)