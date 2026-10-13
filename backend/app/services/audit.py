from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AuditLog

log = logging.getLogger("audit")


def record(db: Session, action: str, *, user_id: str | None = None, meeting_id: str | None = None,
           commit: bool = True, **detail: object) -> None:
    """Append-only audit trail. Never put tokens or transcript text in ``detail``."""
    db.add(AuditLog(user_id=user_id, meeting_id=meeting_id, action=action, detail=detail))
    if commit:
        db.commit()
    log.info("audit action=%s meeting=%s user=%s", action, meeting_id, user_id)
