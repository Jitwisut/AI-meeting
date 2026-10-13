"""SharePoint access via Microsoft Graph (plan §4.2).

Graph is only the file API; the backend/worker moves bytes to the STT service.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.errors import AppError, GraphError
from app.services.graph_client import GraphClient

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg"}


@dataclass
class DriveEntry:
    id: str
    name: str
    is_folder: bool
    size: int | None = None
    web_url: str | None = None
    last_modified: str | None = None
    drive_id: str | None = None
    site_id: str | None = None
    mime_type: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def is_audio_name(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_EXTENSIONS


class SharePointService(Protocol):
    def list_sites(self) -> list[dict]: ...
    def list_drives(self, site_id: str) -> list[dict]: ...
    def list_children(self, drive_id: str, item_id: str | None, query: str | None) -> list[DriveEntry]: ...
    def get_item(self, drive_id: str, item_id: str) -> DriveEntry: ...
    def download(self, drive_id: str, item_id: str, dest: Path, max_bytes: int) -> int: ...
    def upload_report(self, drive_id: str, folder: str, filename: str, data: bytes) -> DriveEntry: ...


def _ensure_site_allowed(site_id: str | None) -> None:
    allowed = get_settings().allowed_site_ids
    if allowed and site_id not in allowed:
        raise AppError(403, "site_not_allowed", "ไซต์ SharePoint นี้ไม่อยู่ในรายการที่ได้รับอนุญาต")


_SAFE_NAME = re.compile(r"[^\w\-. ()฀-๿]+")


def safe_filename(name: str) -> str:
    return _SAFE_NAME.sub("_", name).strip()[:150] or "report"


class GraphSharePointService:
    def __init__(self, token: str) -> None:
        self.token = token

    def _client(self) -> GraphClient:
        return GraphClient(self.token)

    def list_sites(self) -> list[dict]:
        sites = []
        with self._client() as g:
            for site_id in get_settings().allowed_site_ids:
                try:
                    s = g.get(f"/sites/{site_id}", {"$select": "id,displayName,webUrl"})
                except GraphError as exc:
                    if exc.graph_status in (403, 404):
                        continue  # user cannot see this site: hide it
                    raise
                sites.append({"id": s["id"], "name": s.get("displayName"), "web_url": s.get("webUrl")})
        return sites

    def list_drives(self, site_id: str) -> list[dict]:
        _ensure_site_allowed(site_id)
        with self._client() as g:
            return [
                {"id": d["id"], "name": d.get("name"), "web_url": d.get("webUrl")}
                for d in g.get_paged(f"/sites/{site_id}/drives", {"$select": "id,name,webUrl,driveType"})
                if d.get("driveType") == "documentLibrary"
            ]

    def _entry(self, raw: dict, drive_id: str) -> DriveEntry:
        parent = raw.get("parentReference", {})
        return DriveEntry(
            id=raw["id"], name=raw.get("name", ""), is_folder="folder" in raw, size=raw.get("size"),
            web_url=raw.get("webUrl"), last_modified=raw.get("lastModifiedDateTime"),
            drive_id=parent.get("driveId", drive_id), site_id=parent.get("siteId"),
            mime_type=raw.get("file", {}).get("mimeType"),
        )

    def list_children(self, drive_id: str, item_id: str | None, query: str | None) -> list[DriveEntry]:
        select = "id,name,size,webUrl,lastModifiedDateTime,file,folder,parentReference"
        with self._client() as g:
            if query:
                safe_q = query.replace("'", "''")
                path = f"/drives/{drive_id}/root/search(q='{safe_q}')"
            elif item_id:
                path = f"/drives/{drive_id}/items/{item_id}/children"
            else:
                path = f"/drives/{drive_id}/root/children"
            entries = [self._entry(r, drive_id) for r in g.get_paged(path, {"$select": select, "$top": "200"})]
        if entries:
            _ensure_site_allowed(entries[0].site_id)
        return [e for e in entries if e.is_folder or is_audio_name(e.name)]

    def get_item(self, drive_id: str, item_id: str) -> DriveEntry:
        with self._client() as g:
            raw = g.get(f"/drives/{drive_id}/items/{item_id}",
                        {"$select": "id,name,size,webUrl,lastModifiedDateTime,file,folder,parentReference"})
        entry = self._entry(raw, drive_id)
        _ensure_site_allowed(entry.site_id)
        return entry

    def download(self, drive_id: str, item_id: str, dest: Path, max_bytes: int) -> int:
        with GraphClient(self.token, timeout=600) as g:
            return g.download(f"/drives/{drive_id}/items/{item_id}/content", dest, max_bytes)

    def upload_report(self, drive_id: str, folder: str, filename: str, data: bytes) -> DriveEntry:
        # Simple upload supports files up to 250 MB, far above a DOCX report.
        path = f"/drives/{drive_id}/root:/{folder}/{safe_filename(filename)}:/content"
        with GraphClient(self.token, timeout=120) as g:
            raw = g.put_content(
                path, data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        return self._entry(raw, drive_id)


# ---------------------------------------------------------------------------
# Mock implementation backed by samples/ (plan §10: develop with mock Graph)
# ---------------------------------------------------------------------------
MOCK_SITE_ID = "contoso.sharepoint.com,mock-site,meetings"
MOCK_DRIVE_ID = "mock-drive-audio"
MOCK_RESTRICTED_FOLDER = "mock-folder-restricted"
MOCK_RESTRICTED_ITEM = "mock-item-board-confidential"


class MockSharePointService:
    """Simulates one site with an audio library, plus a file the user cannot open."""

    def __init__(self, user_key: str) -> None:
        s = get_settings()
        self.user_key = user_key
        self.audio_dir = s.samples_dir / "audio"
        self.store = s.storage_dir / "mock_sharepoint"

    def list_sites(self) -> list[dict]:
        return [{"id": MOCK_SITE_ID, "name": "ทีมประชุม (Mock)", "web_url": "https://contoso.sharepoint.com/sites/meetings"}]

    def list_drives(self, site_id: str) -> list[dict]:
        if site_id != MOCK_SITE_ID:
            raise GraphError(404)
        return [{"id": MOCK_DRIVE_ID, "name": "Meeting Recordings", "web_url": None}]

    def _audio_entries(self) -> list[DriveEntry]:
        entries = []
        for p in sorted(self.audio_dir.glob("*")):
            if is_audio_name(p.name):
                entries.append(DriveEntry(
                    id=f"mock-item-{p.name}", name=p.name, is_folder=False, size=p.stat().st_size,
                    web_url=f"https://contoso.sharepoint.com/sites/meetings/Recordings/{p.name}",
                    last_modified="2026-10-01T09:00:00Z", drive_id=MOCK_DRIVE_ID, site_id=MOCK_SITE_ID,
                    mime_type="audio/mpeg" if p.suffix == ".mp3" else "audio/wav"))
        return entries

    def list_children(self, drive_id: str, item_id: str | None, query: str | None) -> list[DriveEntry]:
        if drive_id != MOCK_DRIVE_ID:
            raise GraphError(404)
        if item_id == MOCK_RESTRICTED_FOLDER:
            return [DriveEntry(id=MOCK_RESTRICTED_ITEM, name="board-meeting-confidential.mp3", is_folder=False,
                               size=1024, drive_id=MOCK_DRIVE_ID, site_id=MOCK_SITE_ID)]
        entries = self._audio_entries()
        if query:
            return [e for e in entries if query.lower() in e.name.lower()]
        folder = DriveEntry(id=MOCK_RESTRICTED_FOLDER, name="ผู้บริหาร (จำกัดสิทธิ์)", is_folder=True,
                            drive_id=MOCK_DRIVE_ID, site_id=MOCK_SITE_ID)
        return [folder, *entries]

    def get_item(self, drive_id: str, item_id: str) -> DriveEntry:
        if item_id == MOCK_RESTRICTED_ITEM:
            raise GraphError(403, "accessDenied", "mock: access denied")
        for e in self._audio_entries():
            if e.id == item_id and drive_id == MOCK_DRIVE_ID:
                return e
        raise GraphError(404, "itemNotFound")

    def download(self, drive_id: str, item_id: str, dest: Path, max_bytes: int) -> int:
        entry = self.get_item(drive_id, item_id)
        src = self.audio_dir / entry.name
        if src.stat().st_size > max_bytes:
            raise AppError(413, "file_too_large", "ไฟล์เสียงมีขนาดเกินกำหนด")
        shutil.copyfile(src, dest)
        return src.stat().st_size

    def upload_report(self, drive_id: str, folder: str, filename: str, data: bytes) -> DriveEntry:
        target_dir = self.store / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        name = safe_filename(filename)
        (target_dir / name).write_bytes(data)
        return DriveEntry(id=f"mock-report-{name}", name=name, is_folder=False, size=len(data),
                          web_url=f"https://contoso.sharepoint.com/sites/meetings/{folder}/{name}",
                          drive_id=drive_id, site_id=MOCK_SITE_ID)


def get_sharepoint(current_user, *, write: bool = False) -> SharePointService:  # noqa: ANN001
    s = get_settings()
    if s.graph_mode == "mock":
        return MockSharePointService(current_user.user.entra_oid)
    scope = "graph_scopes_sharepoint_write" if write else "graph_scopes_sharepoint_read"
    return GraphSharePointService(current_user.graph_token(scope))
