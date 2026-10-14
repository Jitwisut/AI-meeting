from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    env = {
        "ENVIRONMENT": "test", "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
        "STORAGE_DIR": str(tmp_path / "storage"), "SAMPLES_DIR": str(SAMPLES), "QUEUE_MODE": "sync",
        "AUTH_MODE": "mock", "GRAPH_MODE": "mock", "STT_PROVIDER": "mock", "SUMMARIZER": "mock",
        "SHAREPOINT_ALLOWED_SITE_IDS": "", "ENTRA_APPROVER_ROLE": "",
        # never let real credentials from a developer's .env leak into tests
        "GEMINI_MODEL": "gemini-3.6-flash,gemini-3.8-flash,gemini-3.5-flash-lite", "GEMINI_STT_MODEL": "gemini-3.6-flash,gemini-3.8-flash,gemini-3.5-flash-lite",
        "GEMINI_API_KEY": "", "AZURE_SPEECH_KEY": "", "AZURE_OPENAI_API_KEY": "", "ENTRA_API_CLIENT_SECRET": "",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from app import config, db
    from app.services import rate_limit, teams

    config.get_settings.cache_clear()
    db.reset_engine()
    rate_limit.reset()
    monkeypatch.setattr(teams, "MOCK_FAILURE", None)
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    db.reset_engine()
    config.get_settings.cache_clear()


AS_OTHER = {"X-Mock-User": "other-user"}
PROJECT_CHAT = "19:mock-group-project@thread.v2"


def make_wav(path: Path, seconds: float = 2.0) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
                    "-t", str(seconds), str(path)], check=True)
    return path


def create_sharepoint_meeting(client, name: str = "project-sync-03.mp3", agenda: list[str] | None = None) -> dict:
    import json

    meeting_def = json.loads((SAMPLES / "meetings" / f"{Path(name).stem}.json").read_text(encoding="utf-8"))
    r = client.post("/api/meetings", json={
        "drive_id": "mock-drive-audio", "item_id": f"mock-item-{name}", "language": "th-TH",
        "agenda": agenda if agenda is not None else meeting_def["agenda"], "consent_ai_processing": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def processed_meeting(client, name: str = "project-sync-03.mp3") -> dict:
    m = create_sharepoint_meeting(client, name)
    r = client.post(f"/api/meetings/{m['id']}/process")
    assert r.status_code == 202, r.text
    detail = client.get(f"/api/meetings/{m['id']}").json()
    assert detail["status"] == "awaiting_review", detail
    return detail


def approved_meeting(client, name: str = "project-sync-03.mp3") -> dict:
    m = processed_meeting(client, name)
    version = client.get(f"/api/meetings/{m['id']}/summary").json()["report"]["version"]
    r = client.post(f"/api/meetings/{m['id']}/approve", json={"version": version})
    assert r.status_code == 200, r.text
    return m


@pytest.fixture()
def wav_file(tmp_path) -> Path:
    if os.system("which ffmpeg > /dev/null") != 0:
        pytest.skip("ffmpeg not installed")
    return make_wav(tmp_path / "tone.wav")
