from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.common import (
    get_owned_meeting,
    get_report,
    normalise_mapping_key,
    require_approver,
    serialize_meeting,
    serialize_publication,
    serialize_report_meta,
    user_name,
)
from app.auth.dependencies import CurrentUser, get_current_user
from app.config import SUPPORTED_LANGUAGES, get_settings
from app.db import get_db
from app.errors import AppError
from app.models import ChatMapping, Meeting, MeetingStatus, TeamPublication, Transcript
from app.services import audio, audit, rate_limit
from app.services.exporter import build_docx, report_filename
from app.services.jobs import enqueue_processing, processing_is_stale
from app.services.sharepoint import MOCK_DRIVE_ID, get_sharepoint, is_audio_name
from app.services.teams import get_teams, publish, render_message, require_group_chat
from app.workers.pipeline import get_stage, original_audio, sync_normalised_rows

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


def now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_agenda(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        t = item.strip()[:200]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:30]


def _check_language(language: str) -> str:
    if language not in SUPPORTED_LANGUAGES:
        raise AppError(422, "unsupported_language", "ไม่รองรับภาษานี้")
    return language


# ---------------------------------------------------------------------------
# List / create
# ---------------------------------------------------------------------------
@router.get("")
def list_meetings(status: str | None = Query(default=None), q: str | None = Query(default=None, max_length=100),
                  limit: int = Query(default=50, ge=1, le=200),
                  current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    stmt = select(Meeting).where(Meeting.created_by == current.id)
    if status:
        stmt = stmt.where(Meeting.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Meeting.title.ilike(like), Meeting.source_filename.ilike(like)))
    rows = db.scalars(stmt.order_by(Meeting.created_at.desc()).limit(limit)).all()
    return {"meetings": [serialize_meeting(db, m) for m in rows]}


class CreateFromSharePoint(BaseModel):
    drive_id: str = Field(min_length=1, max_length=300)
    item_id: str = Field(min_length=1, max_length=300)
    title: str | None = Field(default=None, max_length=300)
    language: str = "th-TH"
    agenda: list[str] = Field(default_factory=list, max_length=30)
    consent_ai_processing: bool = False


@router.post("", status_code=201)
def create_from_sharepoint(body: CreateFromSharePoint, current: CurrentUser = Depends(get_current_user),
                           db: Session = Depends(get_db)) -> dict:
    rate_limit.check(current.id, "create")
    _check_language(body.language)
    if not body.consent_ai_processing:
        raise AppError(422, "consent_required",
                       "กรุณายืนยันว่าผู้ร่วมประชุมรับทราบการบันทึกเสียงและการประมวลผลด้วย AI ตามนโยบายบริษัท")
    # Uses the user's delegated token: files the user cannot open are rejected by Graph (403/404).
    item = get_sharepoint(current).get_item(body.drive_id, body.item_id)
    if item.is_folder or not is_audio_name(item.name):
        raise AppError(415, "not_audio", "รายการที่เลือกไม่ใช่ไฟล์เสียงที่รองรับ")
    if item.size and item.size > get_settings().max_upload_mb * 1024 * 1024:
        raise AppError(413, "file_too_large", f"ไฟล์ใหญ่เกิน {get_settings().max_upload_mb} MB")
    meeting = Meeting(
        title=(body.title or Path(item.name).stem).strip()[:300], created_by=current.id, source_type="sharepoint",
        source_drive_id=item.drive_id or body.drive_id, source_item_id=item.id, source_web_url=item.web_url,
        source_filename=item.name, language=body.language, agenda=_clean_agenda(body.agenda),
        status=MeetingStatus.PENDING, consent_confirmed_at=now(), audio_info={},
    )
    db.add(meeting)
    db.commit()
    audit.record(db, "meeting_created", user_id=current.id, meeting_id=meeting.id, source="sharepoint")
    return serialize_meeting(db, meeting, detail=True)


@router.post("/upload", status_code=201)
async def upload(
    file: UploadFile = File(...),
    title: str = Form(default="", max_length=300),
    language: str = Form(default="th-TH"),
    agenda: str = Form(default="[]"),
    source: Literal["upload", "recording"] = Form(default="upload"),
    consent_ai_processing: bool = Form(default=False),
    consent_recording: bool = Form(default=False),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rate_limit.check(current.id, "upload")
    _check_language(language)
    if not consent_ai_processing:
        raise AppError(422, "consent_required",
                       "กรุณายืนยันว่าผู้ร่วมประชุมรับทราบการบันทึกเสียงและการประมวลผลด้วย AI ตามนโยบายบริษัท")
    if source == "recording" and not consent_recording:
        raise AppError(422, "recording_consent_required", "กรุณายืนยันว่าแจ้งผู้ร่วมประชุมก่อนเริ่มอัดเสียงแล้ว")
    try:
        agenda_items = json.loads(agenda) if agenda.strip().startswith("[") else agenda.splitlines()
        if not isinstance(agenda_items, list) or not all(isinstance(a, str) for a in agenda_items):
            raise ValueError
    except ValueError as exc:
        raise AppError(422, "invalid_agenda", "รูปแบบวาระการประชุมไม่ถูกต้อง") from exc

    s = get_settings()
    filename = Path(file.filename or "recording").name[:200]
    meeting = Meeting(title=(title or Path(filename).stem or "การประชุม").strip()[:300], created_by=current.id,
                      source_type=source, source_filename=filename, language=language,
                      agenda=_clean_agenda(agenda_items), status=MeetingStatus.PENDING,
                      consent_confirmed_at=now(), audio_info={})
    db.add(meeting)
    db.flush()
    work = audio.meeting_audio_dir(meeting.id)
    tmp = work / "upload.part"
    limit = s.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with tmp.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise AppError(413, "file_too_large", f"ไฟล์ใหญ่เกิน {s.max_upload_mb} MB")
                fh.write(chunk)
        audio.scan_for_malware(tmp)
        info = audio.probe(tmp)  # real type from the bytes, not the extension
        audio.validate(info, source)
    except Exception:
        db.rollback()
        shutil.rmtree(work, ignore_errors=True)
        raise
    ext = {"mp3": "mp3", "wav": "wav", "ogg": "ogg"}.get(info.format_name,
                                                         "webm" if "webm" in info.format_name else "m4a")
    tmp.rename(work / f"original.{ext}")
    meeting.audio_info = info.to_dict()
    meeting.audio_available = True
    db.commit()
    stage = get_stage(db, meeting.id, "download")
    stage.status, stage.started_at, stage.finished_at = "succeeded", now(), now()
    db.commit()
    audit.record(db, "meeting_created", user_id=current.id, meeting_id=meeting.id, source=source,
                 format=info.format_name, size=info.size_bytes)
    return serialize_meeting(db, meeting, detail=True)


# ---------------------------------------------------------------------------
# Processing / read
# ---------------------------------------------------------------------------
@router.post("/{meeting_id}/process", status_code=202)
def process(meeting_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rate_limit.check(current.id, "process")
    meeting = get_owned_meeting(db, meeting_id, current)
    if meeting.status == MeetingStatus.PROCESSING and not processing_is_stale(meeting):
        raise AppError(409, "already_processing", "รายการนี้กำลังประมวลผลอยู่")
    if meeting.status not in (MeetingStatus.PENDING, MeetingStatus.FAILED, MeetingStatus.PROCESSING):
        raise AppError(409, "already_processed", "รายการนี้ประมวลผลเสร็จแล้ว")

    if meeting.source_type == "sharepoint" and original_audio(meeting.id) is None:
        stage = get_stage(db, meeting.id, "download")
        if stage.status == "failed":
            stage.retry_count += 1
        stage.status, stage.started_at, stage.error_code, stage.error_message = "running", now(), None, None
        db.commit()
        work = audio.meeting_audio_dir(meeting.id)
        dest = work / f"original{Path(meeting.source_filename or '.bin').suffix.lower() or '.bin'}"
        try:
            # delegated download while the user's token is available; worker never holds user tokens
            get_sharepoint(current).download(meeting.source_drive_id, meeting.source_item_id, dest,
                                             get_settings().max_upload_mb * 1024 * 1024)
            info = audio.probe(dest)
            audio.validate(info, "sharepoint")
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, AppError):
                exc = AppError(502, "download_failed", "ดาวน์โหลดไฟล์จาก SharePoint ไม่สำเร็จ กรุณาลองใหม่")
            dest.unlink(missing_ok=True)
            stage.status, stage.finished_at, stage.error_code, stage.error_message = "failed", now(), exc.code, exc.message
            meeting.status, meeting.error_code, meeting.error_message = MeetingStatus.FAILED, exc.code, exc.message
            db.commit()
            raise exc from None
        meeting.audio_info = info.to_dict()
        meeting.audio_available = True
        stage.status, stage.finished_at = "succeeded", now()

    meeting.status, meeting.error_code, meeting.error_message = MeetingStatus.PROCESSING, None, None
    db.commit()
    audit.record(db, "processing_started", user_id=current.id, meeting_id=meeting.id)
    try:
        job_id = enqueue_processing(meeting.id)
    except Exception as exc:  # noqa: BLE001 - e.g. Redis unavailable: never leave the meeting stuck
        db.rollback()
        meeting.status, meeting.error_code = MeetingStatus.FAILED, "queue_unavailable"
        meeting.error_message = "ระบบคิวงานไม่พร้อมใช้งาน ยังไม่ได้เริ่มประมวลผล กรุณาลองใหม่อีกครั้ง"
        db.commit()
        raise AppError(503, "queue_unavailable", meeting.error_message) from exc
    db.refresh(meeting)
    return {"job_id": job_id, "meeting": serialize_meeting(db, meeting, detail=True)}


@router.get("/{meeting_id}")
def get_meeting(meeting_id: str, current: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    return serialize_meeting(db, get_owned_meeting(db, meeting_id, current), detail=True)


@router.get("/{meeting_id}/transcript")
def transcript(meeting_id: str, current: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    meeting = get_owned_meeting(db, meeting_id, current)
    t = db.scalar(select(Transcript).where(Transcript.meeting_id == meeting.id))
    if t is None:
        raise AppError(409, "transcript_not_ready", "ยังไม่มีบทถอดเสียง")
    return {"language": t.language, "provider": t.provider, "segments": t.segments}


@router.get("/{meeting_id}/audio")
def meeting_audio(meeting_id: str, current: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> FileResponse:
    meeting = get_owned_meeting(db, meeting_id, current)
    wav = get_settings().storage_dir / "audio" / meeting.id / "normalized.wav"
    if not meeting.audio_available or not wav.exists():
        raise AppError(410, "audio_expired", "ไฟล์เสียงชั่วคราวถูกลบตามนโยบายการเก็บรักษาแล้ว")
    return FileResponse(wav, media_type="audio/wav", headers={"Cache-Control": "private, no-store"})


@router.get("/{meeting_id}/waveform")
def meeting_waveform(meeting_id: str, buckets: int = Query(default=180, ge=20, le=600),
                     current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    meeting = get_owned_meeting(db, meeting_id, current)
    wav = get_settings().storage_dir / "audio" / meeting.id / "normalized.wav"
    if not meeting.audio_available or not wav.exists():
        raise AppError(410, "audio_expired", "ไฟล์เสียงชั่วคราวถูกลบตามนโยบายการเก็บรักษาแล้ว")
    cache = wav.with_name(f"peaks_{buckets}.json")
    if cache.exists():
        peaks = json.loads(cache.read_text())
    else:
        peaks = audio.waveform_peaks(wav, buckets)
        cache.write_text(json.dumps(peaks))
    return {"peaks": peaks, "duration_ms": (meeting.audio_info or {}).get("duration_ms")}


@router.get("/{meeting_id}/summary")
def get_summary(meeting_id: str, current: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    meeting = get_owned_meeting(db, meeting_id, current)
    report = get_report(db, meeting)
    return {"summary": report.summary_json, "report": serialize_report_meta(db, report)}


# ---------------------------------------------------------------------------
# Human review
# ---------------------------------------------------------------------------
class EvidenceRef(BaseModel):
    segment_id: int


class TopicEdit(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    source: Literal["agenda", "discovered", "manual"] = "manual"
    status: Literal["not_mentioned", "mentioned", "resolved", "unclear"]
    resolution: str | None = Field(default=None, max_length=2000)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    verified: bool = False


class DecisionEdit(BaseModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=2000)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=50)


class ActionEdit(BaseModel):
    id: str | None = None
    task: str = Field(min_length=1, max_length=2000)
    owner: str | None = Field(default=None, max_length=200)
    due_date: str | None = Field(default=None, max_length=100)
    status: Literal["open", "done"] = "open"
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=50)


class SummaryEdit(BaseModel):
    meeting_title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=20000)
    topics: list[TopicEdit] = Field(default_factory=list, max_length=100)
    decisions: list[DecisionEdit] = Field(default_factory=list, max_length=200)
    action_items: list[ActionEdit] = Field(default_factory=list, max_length=200)
    open_questions: list[DecisionEdit] = Field(default_factory=list, max_length=200)

    @field_validator("topics")
    @classmethod
    def resolved_needs_resolution(cls, topics: list[TopicEdit]) -> list[TopicEdit]:
        for t in topics:
            if t.status == "resolved" and not (t.resolution or "").strip():
                raise ValueError(f"หัวข้อ “{t.title}” สถานะ 'ได้ข้อสรุป' ต้องระบุข้อสรุป")
        return topics


class PatchSummary(BaseModel):
    version: int = Field(ge=1)
    summary: SummaryEdit


def _rebuild_evidence(refs: list[EvidenceRef], by_id: dict[int, dict]) -> list[dict]:
    """Evidence text/timestamps always come from the stored transcript, never from the client."""
    out, seen = [], set()
    for r in refs:
        s = by_id.get(r.segment_id)
        if s and r.segment_id not in seen:
            seen.add(r.segment_id)
            out.append({"segment_id": s["id"], "start_ms": s["start_ms"], "end_ms": s["end_ms"], "text": s["text"]})
    return sorted(out, key=lambda e: e["start_ms"])


@router.patch("/{meeting_id}/summary")
def patch_summary(meeting_id: str, body: PatchSummary, current: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    import uuid

    meeting = get_owned_meeting(db, meeting_id, current)
    report = get_report(db, meeting)
    if body.version != report.version:
        raise AppError(409, "version_conflict", "รายงานถูกแก้ไขไปแล้ว กรุณาโหลดฉบับล่าสุดก่อนบันทึก",
                       detail={"current_version": report.version})
    t = db.scalar(select(Transcript).where(Transcript.meeting_id == meeting.id))
    by_id = {s["id"]: s for s in (t.segments if t else [])}
    old = report.summary_json
    e = body.summary

    def keep_id(item_id: str | None) -> str:
        return item_id or uuid.uuid4().hex[:10]

    new_summary = {
        **{k: old.get(k) for k in ("generated_by", "generated_at", "validation_warnings")},
        "meeting_title": e.meeting_title.strip(),
        "summary": e.summary.strip(),
        "topics": [{"id": keep_id(x.id), "title": x.title.strip(), "source": x.source, "status": x.status,
                    "resolution": (x.resolution or "").strip() or None if x.status == "resolved" else None,
                    "evidence": [] if x.status == "not_mentioned" else _rebuild_evidence(x.evidence, by_id),
                    "verified_by": current.id if x.verified else None} for x in e.topics],
        "decisions": [{"id": keep_id(x.id), "text": x.text.strip(), "evidence": _rebuild_evidence(x.evidence, by_id)}
                      for x in e.decisions],
        "action_items": [{"id": keep_id(x.id), "task": x.task.strip(), "owner": (x.owner or "").strip() or None,
                          "due_date": (x.due_date or "").strip() or None, "status": x.status,
                          "evidence": _rebuild_evidence(x.evidence, by_id)} for x in e.action_items],
        "open_questions": [{"id": keep_id(x.id), "text": x.text.strip(),
                            "evidence": _rebuild_evidence(x.evidence, by_id)} for x in e.open_questions],
        "edited_by": current.id,
        "edited_at": now().isoformat(),
    }
    report.summary_json = new_summary
    report.version += 1  # any edit invalidates a previous approval
    sync_normalised_rows(db, meeting.id, new_summary, verified_by=current.id)
    if meeting.status in (MeetingStatus.REVIEWED, MeetingStatus.PUBLISHED):
        meeting.status = MeetingStatus.AWAITING_REVIEW
    db.commit()
    audit.record(db, "summary_edited", user_id=current.id, meeting_id=meeting.id, version=report.version)
    return {"summary": report.summary_json, "report": serialize_report_meta(db, report)}


class ApproveBody(BaseModel):
    version: int = Field(ge=1)


@router.post("/{meeting_id}/approve")
def approve(meeting_id: str, body: ApproveBody, current: CurrentUser = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    require_approver(current)
    meeting = get_owned_meeting(db, meeting_id, current)
    report = get_report(db, meeting)
    if body.version != report.version:
        raise AppError(409, "version_conflict", "มีการแก้ไขรายงานหลังจากที่คุณเปิดดู กรุณาตรวจสอบฉบับล่าสุดก่อนอนุมัติ",
                       detail={"current_version": report.version})
    report.approved_by, report.approved_at, report.approved_version = current.id, now(), report.version
    if meeting.status == MeetingStatus.AWAITING_REVIEW:
        meeting.status = MeetingStatus.REVIEWED
    db.commit()
    audit.record(db, "report_approved", user_id=current.id, meeting_id=meeting.id, version=report.version)
    return {"report": serialize_report_meta(db, report), "status": meeting.status}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _export(db: Session, meeting: Meeting, current: CurrentUser) -> dict:
    report = get_report(db, meeting)
    if not report.is_approved:
        raise AppError(409, "not_approved", "ต้องอนุมัติรายงานฉบับล่าสุดก่อนส่งออก")
    s = get_settings()
    t = db.scalar(select(Transcript).where(Transcript.meeting_id == meeting.id))
    data = build_docx(meeting, report, user_name(db, report.approved_by), t.segments if t else None)
    filename = report_filename(meeting, report)
    out_dir = s.storage_dir / "reports" / meeting.id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"v{report.version}.docx"
    path.write_bytes(data)
    report.docx_path = str(path)

    drive_id = s.sharepoint_report_drive_id or meeting.source_drive_id or (
        MOCK_DRIVE_ID if s.graph_mode == "mock" else None)
    if not drive_id:
        db.commit()
        raise AppError(409, "report_location_missing",
                       "ยังไม่ได้กำหนดที่เก็บรายงานใน SharePoint (SHAREPOINT_REPORT_DRIVE_ID) "
                       "สามารถดาวน์โหลดไฟล์ Word ได้จากหน้ารายงาน")
    entry = get_sharepoint(current, write=True).upload_report(drive_id, s.sharepoint_report_folder, filename, data)
    report.sharepoint_report_item_id = entry.id
    report.sharepoint_web_url = entry.web_url
    report.exported_version = report.version
    db.commit()
    audit.record(db, "report_exported", user_id=current.id, meeting_id=meeting.id, version=report.version,
                 sharepoint_item=entry.id)
    return {"filename": filename, "version": report.version, "sharepoint_web_url": entry.web_url,
            "report": serialize_report_meta(db, report)}


@router.post("/{meeting_id}/export")
def export(meeting_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rate_limit.check(current.id, "export")
    return _export(db, get_owned_meeting(db, meeting_id, current), current)


@router.get("/{meeting_id}/export/docx")
def download_docx(meeting_id: str, current: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> Response:
    meeting = get_owned_meeting(db, meeting_id, current)
    report = get_report(db, meeting)
    if not report.docx_path or not Path(report.docx_path).exists():
        raise AppError(404, "docx_not_found", "ยังไม่ได้สร้างไฟล์ Word กรุณากดส่งออกก่อน")
    return FileResponse(report.docx_path, filename=report_filename(meeting, report),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------------------
# Teams publish
# ---------------------------------------------------------------------------
@router.get("/{meeting_id}/publish/preview")
def publish_preview(meeting_id: str, chat_id: str = Query(min_length=1, max_length=200),
                    current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    meeting = get_owned_meeting(db, meeting_id, current)
    report = get_report(db, meeting)
    teams = get_teams(current)
    chat = require_group_chat(teams, chat_id)
    members = teams.list_members(chat_id)
    return {
        "chat": chat,
        "members": members,
        "html": render_message(meeting, report, "MOM-PREVIEW"),
        "is_approved": report.is_approved,
        "link_notice": "ลิงก์รายงานจะเปิดได้เฉพาะสมาชิกที่มีสิทธิ์ใน SharePoint "
                       "กรุณาตรวจสอบสิทธิ์ของสมาชิกในแชทก่อนส่ง",
    }


class PublishBody(BaseModel):
    chat_id: str = Field(min_length=1, max_length=200)
    confirm_recipients: bool = False


@router.post("/{meeting_id}/publish")
def publish_to_teams(meeting_id: str, body: PublishBody, current: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    rate_limit.check(current.id, "publish", limit=10)
    meeting = get_owned_meeting(db, meeting_id, current)
    report = get_report(db, meeting)
    if not report.is_approved:
        raise AppError(409, "not_approved", "ต้องอนุมัติรายงานฉบับล่าสุดก่อนส่งเข้า Teams")
    if not body.confirm_recipients:
        raise AppError(422, "confirm_required", "กรุณายืนยันผู้รับและสิทธิ์การเปิดลิงก์รายงานก่อนส่ง")
    teams = get_teams(current, send=True)
    chat = require_group_chat(teams, body.chat_id)  # server-side membership check
    if report.exported_version != report.version:
        _export(db, meeting, current)
        db.refresh(report)
    pub, created = publish(db, teams, meeting, report, chat, current.id)

    key = normalise_mapping_key(meeting.title)
    mapping = db.scalar(select(ChatMapping).where(ChatMapping.user_id == current.id, ChatMapping.mapping_key == key))
    if mapping is None:
        db.add(ChatMapping(user_id=current.id, mapping_key=key, chat_id=chat["id"]))
    else:
        mapping.chat_id, mapping.confirmed_at = chat["id"], now()
    db.commit()
    if created:
        audit.record(db, "teams_published", user_id=current.id, meeting_id=meeting.id, chat_id=chat["id"],
                     message_id=pub.message_id, version=pub.report_version)
    return {"publication": serialize_publication(db, pub), "duplicate": not created}


@router.get("/{meeting_id}/publications")
def publications(meeting_id: str, current: CurrentUser = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    meeting = get_owned_meeting(db, meeting_id, current)
    rows = db.scalars(select(TeamPublication).where(TeamPublication.meeting_id == meeting.id)
                      .order_by(TeamPublication.created_at.desc())).all()
    return {"publications": [serialize_publication(db, p) for p in rows]}

