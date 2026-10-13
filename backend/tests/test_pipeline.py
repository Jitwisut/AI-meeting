from __future__ import annotations

from conftest import AS_OTHER, create_sharepoint_meeting, processed_meeting


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_full_pipeline_from_sharepoint(client):
    m = processed_meeting(client)
    stages = {j["stage"]: j["status"] for j in m["jobs"]}
    assert stages == {"download": "succeeded", "convert": "succeeded", "transcribe": "succeeded",
                      "summarize": "succeeded"}
    assert m["duration_ms"] > 50_000

    t = client.get(f"/api/meetings/{m['id']}/transcript").json()
    assert len(t["segments"]) == 8 and t["segments"][0]["start_ms"] >= 0

    s = client.get(f"/api/meetings/{m['id']}/summary").json()["summary"]
    status = {x["title"]: x["status"] for x in s["topics"]}
    assert status["ออกแบบฐานข้อมูล"] == "resolved"
    assert status["การเชื่อมต่อ SharePoint"] == "mentioned"
    assert status["การทดสอบระบบ UAT"] == "not_mentioned"
    assert all(d["evidence"] for d in s["decisions"])
    owners = {a["owner"] for a in s["action_items"]}
    assert "คุณสมชาย" in owners

    audio = client.get(f"/api/meetings/{m['id']}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"

    wf = client.get(f"/api/meetings/{m['id']}/waveform", params={"buckets": 120}).json()
    assert len(wf["peaks"]) == 120 and max(wf["peaks"]) == 1.0 and min(wf["peaks"]) >= 0
    assert client.get(f"/api/meetings/{m['id']}/waveform", headers=AS_OTHER).status_code == 404


def test_restricted_sharepoint_file_is_rejected(client):
    r = client.post("/api/meetings", json={"drive_id": "mock-drive-audio", "item_id": "mock-item-board-confidential",
                                           "consent_ai_processing": True})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "graph_forbidden"


def test_consent_is_required(client):
    r = client.post("/api/meetings", json={"drive_id": "mock-drive-audio",
                                           "item_id": "mock-item-project-sync-03.mp3"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"


def test_other_user_cannot_see_meeting(client):
    m = create_sharepoint_meeting(client)
    assert client.get(f"/api/meetings/{m['id']}", headers=AS_OTHER).status_code == 404
    assert client.post(f"/api/meetings/{m['id']}/process", headers=AS_OTHER).status_code == 404
    assert client.get("/api/meetings", headers=AS_OTHER).json()["meetings"] == []


def test_upload_wav_and_process(client, wav_file):
    with wav_file.open("rb") as fh:
        r = client.post("/api/meetings/upload", files={"file": ("tone.wav", fh, "audio/wav")},
                        data={"title": "ทดสอบอัปโหลด", "agenda": '["หัวข้อ A"]', "consent_ai_processing": "true"})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert client.post(f"/api/meetings/{mid}/process").status_code == 202
    detail = client.get(f"/api/meetings/{mid}").json()
    assert detail["status"] == "awaiting_review"
    segs = client.get(f"/api/meetings/{mid}/transcript").json()["segments"]
    assert segs[0]["text"].startswith("[MOCK STT]")


def test_upload_rejects_fake_mp3(client, tmp_path):
    fake = tmp_path / "notes.mp3"
    fake.write_text("this is not audio")
    with fake.open("rb") as fh:
        r = client.post("/api/meetings/upload", files={"file": ("notes.mp3", fh, "audio/mpeg")},
                        data={"consent_ai_processing": "true"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] in ("invalid_audio", "no_audio_stream")


def test_upload_rejects_webm_as_plain_upload_but_accepts_recording(client, tmp_path):
    import subprocess

    webm = tmp_path / "rec.webm"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
                    "-t", "1", "-c:a", "libopus", str(webm)], check=True)
    with webm.open("rb") as fh:
        r = client.post("/api/meetings/upload", files={"file": ("rec.webm", fh, "audio/webm")},
                        data={"consent_ai_processing": "true"})
    assert r.status_code == 415
    with webm.open("rb") as fh:
        r = client.post("/api/meetings/upload", files={"file": ("rec.webm", fh, "audio/webm")},
                        data={"consent_ai_processing": "true", "source": "recording", "consent_recording": "true"})
    assert r.status_code == 201, r.text


def test_retry_after_failure_is_safe(client, monkeypatch):
    from app.services import speech_to_text

    m = create_sharepoint_meeting(client)
    calls = {"n": 0}
    original = speech_to_text.MockSpeechToText.transcribe

    def flaky(self, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            from app.errors import AppError
            raise AppError(502, "stt_failed", "boom")
        return original(self, *a, **kw)

    monkeypatch.setattr(speech_to_text.MockSpeechToText, "transcribe", flaky)
    client.post(f"/api/meetings/{m['id']}/process")
    failed = client.get(f"/api/meetings/{m['id']}").json()
    assert failed["status"] == "failed" and failed["error_code"] == "stt_failed"
    client.post(f"/api/meetings/{m['id']}/process")
    ok = client.get(f"/api/meetings/{m['id']}").json()
    assert ok["status"] == "awaiting_review"
    jobs = {j["stage"]: j for j in ok["jobs"]}
    assert jobs["transcribe"]["retry_count"] == 1
    assert jobs["download"]["retry_count"] == 0  # not downloaded twice


def test_cannot_process_twice(client):
    m = processed_meeting(client)
    r = client.post(f"/api/meetings/{m['id']}/process")
    assert r.status_code == 409


def test_recording_without_duration_header_is_accepted(client, tmp_path):
    """Chrome MediaRecorder WebM has no Duration element (non-seekable writer)."""
    import json
    import subprocess

    webm = tmp_path / "chrome.webm"
    piped = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
                            "-t", "2", "-c:a", "libopus", "-live", "1", "-f", "webm", "pipe:1"],
                           check=True, stdout=subprocess.PIPE)  # live, non-seekable: like MediaRecorder
    webm.write_bytes(piped.stdout)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(webm)],
                                      capture_output=True, text=True).stdout)
    assert "duration" not in probe["format"]  # reproduces the browser case
    with webm.open("rb") as fh:
        r = client.post("/api/meetings/upload", files={"file": ("chrome.webm", fh, "audio/webm")},
                        data={"consent_ai_processing": "true", "source": "recording", "consent_recording": "true"})
    assert r.status_code == 201, r.text
    assert 1500 < r.json()["audio_info"]["duration_ms"] < 2600


def test_queue_failure_does_not_leave_meeting_stuck(client, monkeypatch):
    from app.api import meetings as meetings_api

    m = create_sharepoint_meeting(client)

    def down(_):
        raise ConnectionError("redis down")

    monkeypatch.setattr(meetings_api, "enqueue_processing", down)
    r = client.post(f"/api/meetings/{m['id']}/process")
    assert r.status_code == 503 and r.json()["error"]["code"] == "queue_unavailable"
    assert client.get(f"/api/meetings/{m['id']}").json()["status"] == "failed"
    monkeypatch.undo()
    assert client.post(f"/api/meetings/{m['id']}/process").status_code == 202
    assert client.get(f"/api/meetings/{m['id']}").json()["status"] == "awaiting_review"


def test_stale_processing_can_be_retried(client, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.db import session_factory
    from app.models import Meeting, ProcessingJob
    from app.services import jobs

    m = create_sharepoint_meeting(client)
    monkeypatch.setattr(jobs, "enqueue_processing", lambda _: None)
    monkeypatch.setattr("app.api.meetings.enqueue_processing", lambda _: None)  # simulate a lost job
    client.post(f"/api/meetings/{m['id']}/process")
    assert client.post(f"/api/meetings/{m['id']}/process").status_code == 409  # still fresh
    db = session_factory()()
    old = datetime.now(timezone.utc) - timedelta(seconds=jobs.JOB_TIMEOUT_SECONDS + 60)
    db.get(Meeting, m["id"]).created_at = old
    for j in db.query(ProcessingJob).filter_by(meeting_id=m["id"]):
        j.started_at = j.finished_at = old
    db.commit()
    db.close()
    assert client.get(f"/api/meetings/{m['id']}").json()["processing_stale"] is True
    monkeypatch.undo()
    assert client.post(f"/api/meetings/{m['id']}/process").status_code == 202
