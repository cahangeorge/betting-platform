from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.model_governance import ModelEvaluation


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        Index("ix_scheduled_jobs_enabled", "enabled"),
        Index("ix_scheduled_jobs_enabled_next_run", "enabled", "next_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    runs: Mapped[list["ScheduledJobRun"]] = relationship(
        "ScheduledJobRun",
        back_populates="scheduled_job",
        cascade="all, delete-orphan",
    )


class JobCreationIdempotency(Base):
    """Durable ownership-scoped replay key for API job creation requests."""

    __tablename__ = "job_creation_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_job_creation_idempotency_user_operation_key",
        ),
        Index("ix_job_creation_idempotency_scheduled_job_id", "scheduled_job_id"),
        Index("ix_job_creation_idempotency_scrape_job_id", "scrape_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="SET NULL"), nullable=True
    )
    scrape_job_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_jobs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScheduledJobRun(Base):
    __tablename__ = "scheduled_job_runs"
    __table_args__ = (
        Index("ix_scheduled_job_runs_scheduled_job_id", "scheduled_job_id"),
        Index("ix_scheduled_job_runs_scrape_job_id", "scrape_job_id"),
        Index("ix_scheduled_job_runs_status", "status"),
        Index(
            "uq_scheduled_job_runs_active_scrape_task",
            "task_type",
            "scrape_job_id",
            unique=True,
            postgresql_where=text("scrape_job_id IS NOT NULL AND status IN ('queued', 'running')"),
            sqlite_where=text("scrape_job_id IS NOT NULL AND status IN ('queued', 'running')"),
        ),
        Index("ix_scheduled_job_runs_job_created", "scheduled_job_id", "created_at"),
        Index("uq_scheduled_job_runs_idempotency_key", "idempotency_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheduled_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"),
        nullable=True,
    )
    scrape_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("scrape_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_evaluations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)
    taskiq_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transport: Mapped[str] = mapped_column(String(32), default="inprocess", nullable=False)
    transport_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), default="scheduler", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scheduled_job: Mapped["ScheduledJob | None"] = relationship("ScheduledJob", back_populates="runs")
    model_evaluation: Mapped["ModelEvaluation | None"] = relationship("ModelEvaluation")

    @property
    def job_id(self) -> int | None:
        return self.scheduled_job_id


class TaskOutbox(Base):
    __tablename__ = "task_outbox"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_task_outbox_run_id"),
        Index("ix_task_outbox_run_id", "run_id"),
        Index("ix_task_outbox_status", "status"),
        Index("ix_task_outbox_pending", "status", "available_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scheduled_job_runs.id", ondelete="CASCADE"), nullable=False)
    task_name: Mapped[str] = mapped_column(String(100), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
