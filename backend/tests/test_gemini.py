"""Gemini transcription/summarisation with the HTTP layer mocked (no API key or network needed)."""
from __future__ import annotations

import json

import httpx
import pytest
from conftest import create_sharepoint_meeting, make_wav

from app.config import get_settings
from app.services import gemini


def _reply(text: str, status: int = 200, finish: str = "STOP") -> httpx.Response:
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
    if status != 200:
        return httpx.Response(status, json={"error": {"message": "x"}}, request=req)
    return httpx.Response(200, request=req, json={
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]})


@pytest.fixture()
def gemini_on(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr("time.sleep", lambda _: None)
    return s


def test_stt_request_and_timestamp_cleanup(gemini_on, monkeypatch, tmp_path):
    from app.services.speech_to_text import GeminiSpeechToText

    calls = []

    def fake_post(url, headers, json, timeout):  # noqa: A002
        calls.append((url, json))
        segs = [{"start_seconds": 0.2, "end_seconds": 1.1, "text": "สวัสดีครับ"},
                {"start_seconds": 1.0, "end_seconds": 0.5, "text": "เวลาผิด"},  # end before start
                {"start_seconds": 99, "end_seconds": 120, "text": "เกินความยาว"},  # outside clip
                {"start_seconds": 1.5, "end_seconds": 1.9, "text": "  "}]  # empty -> dropped
        return _reply(json_dumps({"segments": segs}))

    json_dumps = json.dumps
    monkeypatch.setattr(gemini.httpx, "post", fake_post)
    wav = make_wav(tmp_path / "a.wav", seconds=2)
    out = GeminiSpeechToText().transcribe(wav, "th-TH", "a.wav")

    url, body = calls[0]
    assert "gemini-2.5-flash:generateContent" in url
    parts = body["contents"][0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "audio/mp3" and len(parts[0]["inline_data"]["data"]) > 100
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "Thai" in parts[1]["text"]
    assert [s["text"] for s in out] == ["สวัสดีครับ", "เวลาผิด", "เกินความยาว"]
    assert all(s["end_ms"] >= s["start_ms"] for s in out)
    assert all(s["end_ms"] <= 2000 for s in out)
    assert [s["id"] for s in out] == [1, 2, 3]


def test_stt_long_audio_is_chunked_with_offsets(gemini_on, monkeypatch, tmp_path):
    from app.services.speech_to_text import GeminiSpeechToText

    monkeypatch.setattr(gemini_on, "gemini_stt_chunk_seconds", 1)
    n = {"calls": 0}

    def fake_post(url, headers, json, timeout):  # noqa: A002
        n["calls"] += 1
        return _reply('{"segments": [{"start_seconds": 0.1, "end_seconds": 0.8, "text": "ช่วง %d"}]}' % n["calls"])

    monkeypatch.setattr(gemini.httpx, "post", fake_post)
    wav = make_wav(tmp_path / "long.wav", seconds=3)
    out = GeminiSpeechToText().transcribe(wav, "th-TH", None)
    assert n["calls"] == 3
    assert [s["start_ms"] for s in out] == [100, 1100, 2100]


def test_throttle_is_retried_then_succeeds(gemini_on, monkeypatch):
    replies = [_reply("", status=429), _reply("", status=503), _reply('{"ok": true}')]
    monkeypatch.setattr(gemini.httpx, "post", lambda *a, **k: replies.pop(0))
    assert json.loads(gemini.generate([gemini.text_part("x")])) == {"ok": True}


def test_quota_exhausted_gives_thai_error(gemini_on, monkeypatch):
    from app.errors import AppError

    monkeypatch.setattr(gemini.httpx, "post", lambda *a, **k: _reply("", status=429))
    with pytest.raises(AppError) as exc:
        gemini.generate([gemini.text_part("x")])
    assert exc.value.code == "gemini_quota"


def test_truncated_output_is_reported(gemini_on, monkeypatch):
    from app.errors import AppError

    monkeypatch.setattr(gemini.httpx, "post", lambda *a, **k: _reply('{"segments": [', finish="MAX_TOKENS"))
    with pytest.raises(AppError) as exc:
        gemini.generate([gemini.text_part("x")])
    assert exc.value.code == "gemini_truncated"


def test_missing_key_fails_clearly(client):
    from app.errors import AppError
    from app.services.speech_to_text import GeminiSpeechToText

    with pytest.raises(AppError) as exc:
        GeminiSpeechToText()
    assert exc.value.code == "stt_not_configured"


def test_full_pipeline_with_gemini_stt_and_summary(client, gemini_on, monkeypatch):
    monkeypatch.setattr(gemini_on, "stt_provider", "gemini")
    monkeypatch.setattr(gemini_on, "summarizer", "gemini")

    def fake_post(url, headers, json, timeout):  # noqa: A002
        if "inline_data" in str(json["contents"][0]["parts"][0]):  # transcription request
            return _reply('{"segments": ['
                          '{"start_seconds": 1, "end_seconds": 5, "text": "หัวข้อแรกคือการออกแบบฐานข้อมูล"},'
                          '{"start_seconds": 5, "end_seconds": 9, "text": "ที่ประชุมตกลงว่าจะใช้ PostgreSQL"},'
                          '{"start_seconds": 9, "end_seconds": 13, "text": "คุณสมชายจะเขียน migration ภายในวันศุกร์นี้"}]}')
        return _reply('{"meeting_title": "ทดสอบ", "summary": "ตกลงใช้ PostgreSQL",'
                      '"topics": [{"title": "ออกแบบฐานข้อมูล", "source": "agenda", "status": "resolved",'
                      '"resolution": "ใช้ PostgreSQL", "evidence_segments": [1, 2]}],'
                      '"decisions": [{"text": "ใช้ PostgreSQL", "evidence_segments": [2]}],'
                      '"action_items": [{"task": "เขียน migration", "owner": "คุณสมชาย", "due_date": "วันศุกร์นี้",'
                      '"evidence_segments": [3]}, {"task": "งานที่แต่งขึ้น", "owner": "คุณวิชัย", "due_date": null,'
                      '"evidence_segments": [3]}], "open_questions": []}')

    monkeypatch.setattr(gemini.httpx, "post", fake_post)
    m = create_sharepoint_meeting(client, agenda=["ออกแบบฐานข้อมูล"])
    assert client.post(f"/api/meetings/{m['id']}/process").status_code == 202
    detail = client.get(f"/api/meetings/{m['id']}").json()
    assert detail["status"] == "awaiting_review", detail
    t = client.get(f"/api/meetings/{m['id']}/transcript").json()
    assert t["provider"] == "gemini" and t["segments"][1]["start_ms"] == 5000
    s = client.get(f"/api/meetings/{m['id']}/summary").json()["summary"]
    assert s["generated_by"] == "gemini"
    assert s["topics"][0]["status"] == "resolved"
    owners = {a["task"]: a["owner"] for a in s["action_items"]}
    assert owners["เขียน migration"] == "คุณสมชาย"
    assert owners["งานที่แต่งขึ้น"] is None  # validator strips an owner not present in the evidence
