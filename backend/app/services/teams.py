"""Microsoft Teams Group Chat publishing (plan §4.3, §9).

* Only chats of type ``group`` that the signed-in user belongs to are offered.
* Messages are sent with the user's *delegated* token (ChatMessage.Send);
  application/client-credential tokens are never used for normal chat sends.
* Every send has a server-derived idempotency key (meeting + report version +
  chat). A unique constraint on that key means double clicks cannot create a
  second message, and an ambiguous timeout is resolved by looking for the
  message's reference code in the chat before any retry.
"""
from __future__ import annotations

import hashlib
import html
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, GraphError
from app.models import Meeting, MeetingReport, MeetingStatus, TeamPublication
from app.services.graph_client import GraphClient, GraphTimeout

MAX_MESSAGE_BYTES = 24_000  # Graph chat messages are limited to ~28 KB
STALE_SENDING_AFTER = timedelta(minutes=2)  # a crashed worker must not block retries forever


class TeamsService(Protocol):
    def list_group_chats(self) -> list[dict]: ...
    def list_members(self, chat_id: str) -> list[dict]: ...
    def send_message(self, chat_id: str, html_body: str) -> str: ...
    def find_message_with_reference(self, chat_id: str, reference_code: str) -> str | None: ...


def _chat_name(chat: dict) -> str:
    if chat.get("topic"):
        return chat["topic"]
    names = [m.get("displayName") for m in chat.get("members", []) if m.get("displayName")]
    return ", ".join(names[:4]) + (" …" if len(names) > 4 else "") if names else "แชทกลุ่ม (ไม่มีชื่อ)"


class GraphTeamsService:
    def __init__(self, read_token: str, send_token: str | None = None) -> None:
        self.read_token = read_token
        self.send_token = send_token

    def list_group_chats(self) -> list[dict]:
        chats = []
        with GraphClient(self.read_token) as g:
            for c in g.get_paged("/me/chats", {"$expand": "members", "$top": "50"}, max_pages=10):
                if c.get("chatType") != "group":
                    continue
                chats.append({
                    "id": c["id"], "topic": _chat_name(c),
                    "member_count": len(c.get("members", [])),
                    "last_updated": c.get("lastUpdatedDateTime"),
                    "web_url": c.get("webUrl"),
                })
        return chats

    def list_members(self, chat_id: str) -> list[dict]:
        with GraphClient(self.read_token) as g:
            return [{"name": m.get("displayName"), "email": m.get("email")}
                    for m in g.get_paged(f"/chats/{chat_id}/members")]

    def send_message(self, chat_id: str, html_body: str) -> str:
        assert self.send_token, "send token required"
        with GraphClient(self.send_token, timeout=30) as g:
            msg = g.post_json(f"/chats/{chat_id}/messages",
                              {"body": {"contentType": "html", "content": html_body}})
        return msg["id"]

    def find_message_with_reference(self, chat_id: str, reference_code: str) -> str | None:
        assert self.send_token, "send token required"
        with GraphClient(self.send_token) as g:
            page = g.get(f"/chats/{chat_id}/messages", {"$top": "50", "$orderby": "createdDateTime desc"})
        for m in page.get("value", []):
            if reference_code in (m.get("body", {}).get("content") or ""):
                return m["id"]
        return None


# ---------------------------------------------------------------------------
# Mock Teams: deterministic chats per mock user; sent messages go to a JSONL file.
# ---------------------------------------------------------------------------
MOCK_CHATS = {
    "mock-dev-user": [
        {"id": "19:mock-group-project@thread.v2", "topic": "ทีมโครงการ AI Meeting Minutes", "chatType": "group",
         "members": ["ผู้ใช้ทดสอบ", "สมชาย", "มาลี", "พี่เลี้ยง"]},
        {"id": "19:mock-group-marketing@thread.v2", "topic": "Marketing Q4", "chatType": "group",
         "members": ["ผู้ใช้ทดสอบ", "วิภา", "ปรีชา"]},
        {"id": "19:mock-group-notopic@thread.v2", "topic": None, "chatType": "group",
         "members": ["ผู้ใช้ทดสอบ", "ธนากร", "มาลี"]},
        {"id": "19:mock-oneonone@unq.gbl.spaces", "topic": None, "chatType": "oneOnOne",
         "members": ["ผู้ใช้ทดสอบ", "สมชาย"]},
    ],
    "mock-other-user": [
        {"id": "19:mock-group-secret@thread.v2", "topic": "ทีมอื่น (ไม่ใช่สมาชิก)", "chatType": "group",
         "members": ["other-user", "ผู้บริหาร"]},
    ],
}

# Test hook: "timeout_after_send" | "timeout_before_send" | "throttle" | None
MOCK_FAILURE: str | None = None
_mock_lock = threading.Lock()


class MockTeamsService:
    def __init__(self, user_key: str) -> None:
        self.user_key = user_key
        self.log = get_settings().storage_dir / "mock_teams" / "messages.jsonl"

    def _chats(self) -> list[dict]:
        return MOCK_CHATS.get(self.user_key, [])

    def list_group_chats(self) -> list[dict]:
        out = []
        for c in self._chats():
            if c["chatType"] != "group":
                continue
            members = [{"displayName": n} for n in c["members"]]
            out.append({"id": c["id"], "topic": _chat_name({"topic": c["topic"], "members": members}),
                        "member_count": len(members), "last_updated": "2026-10-10T08:00:00Z", "web_url": None})
        return out

    def list_members(self, chat_id: str) -> list[dict]:
        for c in self._chats():
            if c["id"] == chat_id:
                return [{"name": n, "email": None} for n in c["members"]]
        raise GraphError(404)

    def sent_messages(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def send_message(self, chat_id: str, html_body: str) -> str:
        if MOCK_FAILURE == "throttle":
            raise GraphError(429, "TooManyRequests", retry_after=30)
        if MOCK_FAILURE == "timeout_before_send":
            raise GraphTimeout("mock timeout before send")
        message_id = f"mock-msg-{uuid.uuid4().hex[:12]}"
        with _mock_lock:
            self.log.parent.mkdir(parents=True, exist_ok=True)
            with self.log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": message_id, "chat_id": chat_id, "sender": self.user_key,
                                     "body": html_body, "at": datetime.now(timezone.utc).isoformat()},
                                    ensure_ascii=False) + "\n")
        if MOCK_FAILURE == "timeout_after_send":
            raise GraphTimeout("mock timeout after the message was delivered")
        return message_id

    def find_message_with_reference(self, chat_id: str, reference_code: str) -> str | None:
        for m in self.sent_messages():
            if m["chat_id"] == chat_id and reference_code in m["body"]:
                return m["id"]
        return None


def get_teams(current_user, *, send: bool = False) -> TeamsService:  # noqa: ANN001
    s = get_settings()
    if s.graph_mode == "mock":
        return MockTeamsService(current_user.user.entra_oid)
    read = current_user.graph_token("graph_scopes_teams_read")
    send_token = current_user.graph_token("graph_scopes_teams_send") if send else None
    return GraphTeamsService(read, send_token)


def require_group_chat(teams: TeamsService, chat_id: str) -> dict:
    """Never trust a client-supplied chat id: it must be one of *this user's* group chats."""
    for chat in teams.list_group_chats():
        if chat["id"] == chat_id:
            return chat
    raise AppError(403, "chat_not_allowed", "คุณไม่ได้เป็นสมาชิกของแชทกลุ่มนี้ หรือแชทนี้ไม่ใช่แชทกลุ่ม")


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------
def _fmt_ms(ms: int | None) -> str:
    if ms is None:
        return ""
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


TOPIC_LABELS = {"resolved": "✅ ได้ข้อสรุป", "mentioned": "💬 มีการพูดถึง",
                "unclear": "❓ ไม่ชัดเจน", "not_mentioned": "⬜ ไม่ได้พูดถึง"}


def _render(meeting: Meeting, report: MeetingReport, reference_code: str, limit: int | None,
            summary_chars: int) -> tuple[str, bool]:
    s = report.summary_json
    e = html.escape
    truncated = False

    def cap(items: list) -> list:
        nonlocal truncated
        if limit is not None and len(items) > limit:
            truncated = True
            return items[:limit]
        return items

    parts = [f"<h2>📝 สรุปการประชุม: {e(s.get('meeting_title') or meeting.title)}</h2>"]
    summary = s.get("summary") or ""
    if summary:
        if len(summary) > summary_chars:
            summary, truncated = summary[:summary_chars] + "…", True
        parts.append(f"<p>{e(summary)}</p>")
    if s.get("decisions"):
        parts.append("<p><b>มติที่ประชุม</b></p><ul>" +
                     "".join(f"<li>{e(d['text'])}</li>" for d in cap(s["decisions"])) + "</ul>")
    if s.get("action_items"):
        items = []
        for a in cap(s["action_items"]):
            meta = [f"ผู้รับผิดชอบ: {e(a['owner'])}" if a.get("owner") else "ผู้รับผิดชอบ: ยังไม่ระบุ"]
            if a.get("due_date"):
                meta.append(f"กำหนด: {e(a['due_date'])}")
            items.append(f"<li>{e(a['task'])} <i>({', '.join(meta)})</i></li>")
        parts.append("<p><b>งานที่ต้องติดตาม</b></p><ul>" + "".join(items) + "</ul>")
    if s.get("topics"):
        parts.append("<p><b>สถานะหัวข้อ</b></p><ul>" + "".join(
            f"<li>{TOPIC_LABELS.get(t['status'], t['status'])} — {e(t['title'])}</li>" for t in cap(s["topics"])) + "</ul>")
    if truncated:
        parts.append("<p><i>… มีรายการเพิ่มเติม ดูรายงานฉบับเต็ม</i></p>")
    if report.sharepoint_web_url:
        parts.append(f'<p>📄 รายงานฉบับเต็ม: <a href="{e(report.sharepoint_web_url)}">เปิดใน SharePoint</a></p>')
    parts.append(f"<p><small>สร้างโดย AI Meeting Minutes และผ่านการตรวจสอบโดยผู้อนุมัติแล้ว, "
                 f"ฉบับที่ {report.version}, รหัสอ้างอิง {reference_code}</small></p>")
    return "".join(parts), truncated


def render_message(meeting: Meeting, report: MeetingReport, reference_code: str) -> str:
    """Render the Teams message within Graph's size limit, measured in UTF-8 bytes (Thai = 3 bytes/char).

    Whole list items are dropped instead of cutting the HTML, so tags and the reference-code
    footer (used to detect duplicates) always stay intact.
    """
    body, _ = _render(meeting, report, reference_code, None, 4000)
    limit, summary_chars = 50, 4000
    while len(body.encode("utf-8")) > MAX_MESSAGE_BYTES:
        if limit > 1:
            limit //= 2
        elif summary_chars > 200:
            summary_chars //= 2
        else:
            break
        body, _ = _render(meeting, report, reference_code, limit, summary_chars)
    return body


# ---------------------------------------------------------------------------
# Publish orchestration
# ---------------------------------------------------------------------------
def idempotency_key(meeting_id: str, version: int, chat_id: str) -> str:
    return hashlib.sha256(f"{meeting_id}|v{version}|{chat_id}".encode()).hexdigest()


def reference_code_for(key: str) -> str:
    return f"MOM-{key[:10].upper()}"


def publish(db: Session, teams: TeamsService, meeting: Meeting, report: MeetingReport,
            chat: dict, user_id: str) -> tuple[TeamPublication, bool]:
    """Send the approved report to a group chat exactly once.

    Returns (publication, created_new_message).
    """
    if not report.is_approved:
        raise AppError(409, "not_approved", "ต้องอนุมัติรายงานฉบับล่าสุดก่อนส่งเข้า Teams")

    key = idempotency_key(meeting.id, report.version, chat["id"])
    ref = reference_code_for(key)
    pub = TeamPublication(meeting_id=meeting.id, report_version=report.version, chat_id=chat["id"],
                          chat_topic=chat.get("topic"), reference_code=ref, status="sending",
                          approved_by=user_id, idempotency_key=key, attempts=1,
                          last_attempt_at=datetime.now(timezone.utc))
    db.add(pub)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        pub = db.scalar(select(TeamPublication).where(TeamPublication.idempotency_key == key))
        assert pub is not None
        if pub.status == "sent":
            return pub, False
        now = datetime.now(timezone.utc)
        stale_before = now - STALE_SENDING_AFTER
        # failed / unknown / stale sending: claim the row atomically so concurrent retries cannot both send
        claimed = db.execute(
            update(TeamPublication)
            .where(TeamPublication.id == pub.id,
                   TeamPublication.status.in_(("failed", "unknown"))
                   | ((TeamPublication.status == "sending") & (TeamPublication.last_attempt_at < stale_before)))
            .values(status="sending", attempts=TeamPublication.attempts + 1, last_attempt_at=now)
        ).rowcount
        db.commit()
        if not claimed:
            raise AppError(409, "publish_in_progress", "กำลังส่งข้อความนี้อยู่ กรุณารอสักครู่")
        db.refresh(pub)
        # A previous attempt may have reached Teams even though we saw an error.
        try:
            existing = teams.find_message_with_reference(chat["id"], ref)
        except GraphError:
            existing = None
            if pub.error_code in ("send_timeout", None):
                pub.status = "unknown"
                db.commit()
                raise AppError(503, "cannot_verify_previous_send",
                               "ไม่สามารถตรวจสอบได้ว่าข้อความครั้งก่อนส่งสำเร็จหรือไม่ จึงยังไม่ส่งซ้ำ กรุณาลองใหม่ภายหลัง")
        if existing:
            _mark_sent(db, meeting, pub, existing)
            return pub, False

    body = render_message(meeting, report, ref)
    try:
        message_id = teams.send_message(chat["id"], body)
    except GraphTimeout:
        pub.status, pub.error_code = "unknown", "send_timeout"
        pub.error_message = "หมดเวลารอการตอบกลับจาก Teams ข้อความอาจส่งสำเร็จแล้ว ระบบจะตรวจสอบก่อนส่งซ้ำ"
        db.commit()
        raise AppError(504, "send_timeout", pub.error_message) from None
    except GraphError as exc:
        pub.status, pub.error_code, pub.error_message = "failed", exc.code, exc.message
        db.commit()
        raise
    _mark_sent(db, meeting, pub, message_id)
    return pub, True


def _mark_sent(db: Session, meeting: Meeting, pub: TeamPublication, message_id: str) -> None:
    pub.status, pub.message_id = "sent", message_id
    pub.sent_at = datetime.now(timezone.utc)
    pub.error_code = pub.error_message = None
    meeting.status = MeetingStatus.PUBLISHED
    db.commit()


def mock_sent_messages(user_key: str) -> list[dict]:
    return MockTeamsService(user_key).sent_messages()


