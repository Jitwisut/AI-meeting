from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import get_owned_meeting, normalise_mapping_key
from app.auth.dependencies import CurrentUser, get_current_user
from app.db import get_db
from app.models import ChatMapping
from app.services.teams import get_teams

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/group-chats")
def group_chats(meeting_id: str | None = Query(default=None, max_length=32),
                current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Group chats (chatType == group) the signed-in user is a member of."""
    chats = get_teams(current).list_group_chats()
    suggested = None
    if meeting_id:
        meeting = get_owned_meeting(db, meeting_id, current)
        mapping = db.scalar(select(ChatMapping).where(
            ChatMapping.user_id == current.id, ChatMapping.mapping_key == normalise_mapping_key(meeting.title)))
        if mapping and any(c["id"] == mapping.chat_id for c in chats):
            suggested = mapping.chat_id
    return {"chats": chats, "suggested_chat_id": suggested}
