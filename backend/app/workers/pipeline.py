"""Background processing: convert -> transcribe -> summarise (plan §3, §8).

Each stage is recorded in ``processing_jobs`` with its real status; there is
no fake percentage. Stages that already succeeded are skipped on retry, so a
retry after a failure is safe and does not redo expensive work.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_factory
from app.errors import AppError
from app.models import ActionItem, Meeting, MeetingReport, MeetingStatus, ProcessingJob, Topic, Transcript
from app.services import audio, audit
from app.services.speech_to_text import get_stt
from app.services.summarizer import summarize

log = logging.getLogger("worker")
STAGES = ("download", "convert", "transcribe", "summarize")


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_stage(db: Session, meeting_id: str, stage: str) -> ProcessingJob:
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.meeting_id == meeting_id,
                                                ProcessingJob.stage == stage))
    if job is None:
        job = ProcessingJob(meeting_id=meeting_id, stage=stage, status="queued")
        db.add(job)
        db.commit()
    return job


def start_stage(db: Session, job: ProcessingJob) -> None:
    if job.status == "failed":
        job.retry_count += 1
    job.status, job.started_at, job.finished_at = "running", now(), None
    job.error_code = job.error_message = None
    db.commit()


def finish_stage(db: Session, job: ProcessingJob, status: str = "succeeded") -> None:
    job.status, job.finished_at = status, now()
    db.commit()


def original_audio(meeting_id: str):  # noqa: ANN201
    d = audio.meeting_audio_dir(meeting_id)
    found = sorted(d.glob("original.*"))
    return found[0] if found else None


def sync_normalised_rows(db: Session, meeting_id: str, summary: dict, verified_by: str | None = None) -> None:
    """Mirror topics/action items into their own tables for querying (plan §6)."""
    for model in (Topic, ActionItem):
        for row in db.scalars(select(model).where(model.meeting_id == meeting_id)):
            db.delete(row)
    for t in summary.get("topics", []):
        ev = t.get("evidence") or []
        db.add(Topic(meeting_id=meeting_id, title=t["title"], status=t["status"],
                     evidence_start_ms=ev[0]["start_ms"] if ev else None,
                     evidence_end_ms=ev[-1]["end_ms"] if ev else None,
                     verified_by=verified_by if t.get("verified_by") else None))
    for a in summary.get("action_items", []):
        ev = a.get("evidence") or []
        db.add(ActionItem(meeting_id=meeting_id, description=a["task"], owner_text=a.get("owner"),
                          due_date=a.get("due_date"), status=a.get("status", "open"),
                          evidence_start_ms=ev[0]["start_ms"] if ev else None,
                          evidence_end_ms=ev[-1]["end_ms"] if ev else None))


def process_meeting(meeting_id: str) -> None:
    cleanup_expired_audio()
    db = session_factory()()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            log.warning("meeting %s vanished", meeting_id)
            return
        _run(db, meeting)
    finally:
        db.close()


def _run(db: Session, meeting: Meeting) -> None:
    current: ProcessingJob | None = None
    try:
        work = audio.meeting_audio_dir(meeting.id)
        wav = work / "normalized.wav"

        # download happens in the API request (needs the user's delegated token); here we only verify it.
        dl = get_stage(db, meeting.id, "download")
        if dl.status != "succeeded":
            current = dl
            if original_audio(meeting.id) is None:
                raise AppError(409, "audio_missing", "ไม่พบไฟล์เสียงต้นฉบับ กรุณาเริ่มประมวลผลใหม่")
            finish_stage(db, dl)

        transcript = db.scalar(select(Transcript).where(Transcript.meeting_id == meeting.id))

        current = get_stage(db, meeting.id, "convert")
        if transcript is not None:
            if current.status != "succeeded":
                finish_stage(db, current, "skipped")
        elif current.status != "succeeded" or not wav.exists():
            start_stage(db, current)
            src = original_audio(meeting.id)
            if src is None:
                raise AppError(409, "audio_missing", "ไฟล์เสียงถูกลบตามนโยบายการเก็บรักษาแล้ว กรุณาเลือกไฟล์ใหม่")
            audio.scan_for_malware(src)
            info = audio.probe(src)
            audio.validate(info, meeting.source_type)
            audio.convert_to_wav(src, wav)
            meeting.audio_info = info.to_dict()
            meeting.audio_available = True
            finish_stage(db, current)

        current = get_stage(db, meeting.id, "transcribe")
        if transcript is None:
            start_stage(db, current)
            stt = get_stt()
            segments = stt.transcribe(wav, meeting.language, meeting.source_filename)
            if not segments:
                raise AppError(422, "empty_transcript", "ไม่พบเสียงพูดที่ถอดความได้ในไฟล์นี้")
            transcript = Transcript(meeting_id=meeting.id, segments=segments, language=meeting.language,
                                    provider=stt.name)
            db.add(transcript)
            finish_stage(db, current)
        elif current.status != "succeeded":
            finish_stage(db, current, "succeeded")

        current = get_stage(db, meeting.id, "summarize")
        report = db.scalar(select(MeetingReport).where(MeetingReport.meeting_id == meeting.id))
        if report is None:
            start_stage(db, current)
            summary = summarize(transcript.segments, meeting.agenda or [], meeting.title)
            db.add(MeetingReport(meeting_id=meeting.id, summary_json=summary, version=1))
            sync_normalised_rows(db, meeting.id, summary)
            finish_stage(db, current)

        meeting.status = MeetingStatus.AWAITING_REVIEW
        meeting.error_code = meeting.error_message = None
        meeting.completed_at = now()
        db.commit()
        audit.record(db, "processing_completed", meeting_id=meeting.id, user_id=meeting.created_by)
    except Exception as exc:  # noqa: BLE001 - every failure must be visible to the user
        db.rollback()
        code = exc.code if isinstance(exc, AppError) else "internal_error"
        message = exc.message if isinstance(exc, AppError) else "เกิดข้อผิดพลาดภายในระหว่างประมวลผล"
        log.exception("processing failed meeting=%s code=%s", meeting.id, code)
        if current is not None:
            current.status, current.finished_at = "failed", now()
            current.error_code, current.error_message = code, message
        meeting.status, meeting.error_code, meeting.error_message = MeetingStatus.FAILED, code, message
        db.commit()
        audit.record(db, "processing_failed", meeting_id=meeting.id, user_id=meeting.created_by, code=code)


def cleanup_expired_audio() -> int:
    """Delete temporary audio after the retention period (plan §9)."""
    s = get_settings()
    cutoff = now() - timedelta(hours=s.temp_audio_retention_hours)
    removed = 0
    db = session_factory()()
    try:
        rows = db.scalars(select(Meeting).where(
            Meeting.audio_available.is_(True),
            Meeting.status.notin_((MeetingStatus.PENDING, MeetingStatus.PROCESSING)),
        )).all()
        for m in rows:
            finished = m.completed_at or m.created_at
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            if finished < cutoff:
                shutil.rmtree(s.storage_dir / "audio" / m.id, ignore_errors=True)
                m.audio_available = False
                removed += 1
        db.commit()
    finally:
        db.close()
    return removed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"removed audio for {cleanup_expired_audio()} meetings")
