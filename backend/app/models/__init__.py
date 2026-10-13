"""Database tables (plan §6) plus an audit log (plan §9)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class MeetingStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_REVIEW = "awaiting_review"
    REVIEWED = "reviewed"  # approved by a human
    PUBLISHED = "published"
    FAILED = "failed"
    ALL = (PENDING, PROCESSING, AWAITING_REVIEW, REVIEWED, PUBLISHED, FAILED)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entra_oid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20))  # sharepoint | upload | recording
    source_drive_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_item_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_web_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(400), nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="th-TH")
    agenda: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default=MeetingStatus.PENDING, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_info: Mapped[dict] = mapped_column(JSON, default=dict)
    audio_available: Mapped[bool] = mapped_column(default=False)
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", order_by="ProcessingJob.started_at")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (UniqueConstraint("meeting_id", "stage"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(20))  # download | convert | transcribe | summarize
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed|skipped
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meeting: Mapped[Meeting] = relationship(back_populates="jobs")


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True)
    # content_ref is kept for moving transcripts to blob storage later; MVP stores segments inline.
    content_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments: Mapped[list] = mapped_column(JSON, default=list)
    language: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20))  # not_mentioned|mentioned|resolved|unclear
    evidence_start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(100), nullable=True)  # as spoken / ISO
    evidence_start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")


class MeetingReport(Base):
    __tablename__ = "meeting_reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exported_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    docx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    sharepoint_report_item_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sharepoint_web_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def is_approved(self) -> bool:
        return self.approved_version is not None and self.approved_version == self.version


class TeamPublication(Base):
    __tablename__ = "team_publications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    report_version: Mapped[int] = mapped_column(Integer)
    chat_id: Mapped[str] = mapped_column(String(200))
    chat_topic: Mapped[str | None] = mapped_column(String(300), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reference_code: Mapped[str] = mapped_column(String(32))
    # sending | sent | failed | unknown (request may have reached Teams; verify before retry)
    status: Mapped[str] = mapped_column(String(20))
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMapping(Base):
    """User-confirmed meeting/series -> Teams chat mapping (plan §4.3)."""

    __tablename__ = "chat_mappings"
    __table_args__ = (UniqueConstraint("user_id", "mapping_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mapping_key: Mapped[str] = mapped_column(String(300))  # e.g. normalised meeting title
    chat_id: Mapped[str] = mapped_column(String(200))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    meeting_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
