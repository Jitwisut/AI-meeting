from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.config import get_settings
from app.errors import AppError
from app.models import Meeting, MeetingReport, ProcessingJob, TeamPublication, User
from app.services.jobs import processing_is_stale
from app.workers.pipeline import STAGES


def get_owned_meeting(db: Session, meeting_id: str, current: CurrentUser) -> Meeting:
    """Meeting access check: MVP grants access to the creator only (plan §7)."""
    meeting = db.get(Meeting, meeting_id) if re.fullmatch(r"[0-9a-f]{32}", meeting_id or "") else None
    if meeting is None or meeting.created_by != current.id:
        # 404 instead of 403 so other users' meeting ids are not disclosed
        raise AppError(404, "meeting_not_found", "ไม่พบรายการประชุม หรือคุณไม่มีสิทธิ์เข้าถึง")
    return meeting


def get_report(db: Session, meeting: Meeting, *, required: bool = True) -> MeetingReport | None:
    report = db.scalar(select(MeetingReport).where(MeetingReport.meeting_id == meeting.id))
    if report is None and required:
        raise AppError(409, "summary_not_ready", "ยังไม่มีผลสรุป กรุณารอให้ประมวลผลเสร็จก่อน")
    return report


def require_approver(current: CurrentUser) -> None:
    role = get_settings().entra_approver_role
    if role and role not in current.roles:
        raise AppError(403, "not_approver", "บัญชีของคุณไม่มีสิทธิ์อนุมัติรายงานการประชุม")


def iso(dt) -> str | None:  # noqa: ANN001
    return dt.isoformat() if dt else None


def user_name(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    u = db.get(User, user_id)
    return u.display_name if u else None


def serialize_jobs(jobs: list[ProcessingJob]) -> list[dict]:
    by_stage = {j.stage: j for j in jobs}
    out = []
    for stage in STAGES:
        j = by_stage.get(stage)
        out.append({
            "stage": stage,
            "status": j.status if j else "queued",
            "error_code": j.error_code if j else None,
            "error_message": j.error_message if j else None,
            "retry_count": j.retry_count if j else 0,
            "started_at": iso(j.started_at) if j else None,
            "finished_at": iso(j.finished_at) if j else None,
        })
    return out


def serialize_publication(db: Session, p: TeamPublication) -> dict:
    return {
        "id": p.id, "chat_id": p.chat_id, "chat_topic": p.chat_topic, "message_id": p.message_id,
        "status": p.status, "report_version": p.report_version, "reference_code": p.reference_code,
        "approved_by": user_name(db, p.approved_by), "sent_at": iso(p.sent_at),
        "error_code": p.error_code, "error_message": p.error_message, "attempts": p.attempts,
        "created_at": iso(p.created_at),
    }


def serialize_report_meta(db: Session, r: MeetingReport | None) -> dict | None:
    if r is None:
        return None
    return {
        "version": r.version, "is_approved": r.is_approved, "approved_version": r.approved_version,
        "approved_by": user_name(db, r.approved_by), "approved_at": iso(r.approved_at),
        "exported_version": r.exported_version, "sharepoint_web_url": r.sharepoint_web_url,
        "has_docx": bool(r.docx_path), "updated_at": iso(r.updated_at),
        "generated_by": r.summary_json.get("generated_by"),
    }


def serialize_meeting(db: Session, m: Meeting, *, detail: bool = False) -> dict:
    report = db.scalar(select(MeetingReport).where(MeetingReport.meeting_id == m.id))
    data = {
        "id": m.id, "title": m.title, "status": m.status, "source_type": m.source_type,
        "source_filename": m.source_filename, "source_web_url": m.source_web_url, "language": m.language,
        "created_at": iso(m.created_at), "completed_at": iso(m.completed_at),
        "error_code": m.error_code, "error_message": m.error_message,
        "duration_ms": (m.audio_info or {}).get("duration_ms"),
        "report": serialize_report_meta(db, report),
    }
    if detail:
        pubs = db.scalars(select(TeamPublication).where(TeamPublication.meeting_id == m.id)
                          .order_by(TeamPublication.created_at.desc())).all()
        data.update({
            "agenda": m.agenda or [], "audio_info": m.audio_info or {}, "audio_available": m.audio_available,
            "jobs": serialize_jobs(list(m.jobs)), "publications": [serialize_publication(db, p) for p in pubs],
            "consent_confirmed_at": iso(m.consent_confirmed_at),
            "processing_stale": m.status == "processing" and processing_is_stale(m),
        })
    return data


def normalise_mapping_key(title: str) -> str:
    return re.sub(r"[\s\d]+|ครั้งที่", "", title.lower())[:300]
