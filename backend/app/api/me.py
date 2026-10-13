from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import serialize_meeting
from app.auth.dependencies import CurrentUser, get_current_user
from app.config import SUPPORTED_LANGUAGES, get_settings
from app.db import get_db
from app.errors import AppError
from app.models import Meeting, MeetingStatus

router = APIRouter(prefix="/api", tags=["me"])

CAPABILITY_SCOPES = {
    "sharepoint_read": "graph_scopes_sharepoint_read",
    "sharepoint_write": "graph_scopes_sharepoint_write",
    "teams_read": "graph_scopes_teams_read",
    "teams_send": "graph_scopes_teams_send",
}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current_user)) -> dict:
    s = get_settings()
    capabilities: dict[str, dict] = {}
    for cap, scope_setting in CAPABILITY_SCOPES.items():
        if s.graph_mode == "mock":
            capabilities[cap] = {"granted": True, "scopes": getattr(s, scope_setting).split(), "mock": True}
            continue
        try:
            current.graph_token(scope_setting)
            capabilities[cap] = {"granted": True, "scopes": getattr(s, scope_setting).split()}
        except AppError as exc:
            capabilities[cap] = {"granted": False, "scopes": getattr(s, scope_setting).split(),
                                 "reason": exc.message}
    u = current.user
    return {
        "user": {"id": u.id, "name": u.display_name, "email": u.email},
        "roles": current.roles,
        "can_approve": not s.entra_approver_role or s.entra_approver_role in current.roles,
        "capabilities": capabilities,
        "preferences": u.preferences or {},
        "modes": {"auth": s.auth_mode, "graph": s.graph_mode, "stt": s.stt_provider, "summarizer": s.summarizer},
    }


class Preferences(BaseModel):
    default_language: str | None = Field(default=None)
    default_site_id: str | None = Field(default=None, max_length=300)
    default_drive_id: str | None = Field(default=None, max_length=300)


@router.put("/me/preferences")
def update_preferences(body: Preferences, current: CurrentUser = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> dict:
    if body.default_language and body.default_language not in SUPPORTED_LANGUAGES:
        raise AppError(422, "unsupported_language", "ไม่รองรับภาษานี้")
    current.user.preferences = {**(current.user.preferences or {}), **body.model_dump(exclude_none=True)}
    db.commit()
    return {"preferences": current.user.preferences}


@router.get("/settings")
def settings_view(_: CurrentUser = Depends(get_current_user)) -> dict:
    s = get_settings()
    return {
        "languages": [{"code": k, "label": v} for k, v in SUPPORTED_LANGUAGES.items()],
        "default_language": s.default_language,
        "sharepoint": {"allowed_site_ids": s.allowed_site_ids, "report_folder": s.sharepoint_report_folder,
                       "report_drive_configured": bool(s.sharepoint_report_drive_id)},
        "policy": {
            "max_upload_mb": s.max_upload_mb,
            "max_audio_minutes": s.max_audio_minutes,
            "temp_audio_retention_hours": s.temp_audio_retention_hours,
            "upload_formats": ["MP3", "WAV"],
            "recording_formats": ["WebM/Opus", "MP4/AAC", "Ogg"],
            "human_review_required": True,
            "speaker_diarization": False,
        },
        "providers": {"auth": s.auth_mode, "graph": s.graph_mode, "stt": s.stt_provider,
                      "summarizer": s.summarizer},
    }


@router.get("/dashboard")
def dashboard(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    counts = dict(db.execute(select(Meeting.status, func.count()).where(Meeting.created_by == current.id)
                             .group_by(Meeting.status)).all())
    recent = db.scalars(select(Meeting).where(Meeting.created_by == current.id)
                        .order_by(Meeting.created_at.desc()).limit(8)).all()
    return {
        "counts": {s: counts.get(s, 0) for s in MeetingStatus.ALL},
        "total": sum(counts.values()),
        "recent": [serialize_meeting(db, m) for m in recent],
    }
