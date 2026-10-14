"""Speech-to-Text providers (plan §8).

Azure AI Speech *fast transcription* REST API is used: it accepts the audio
file directly (no blob SAS needed) and returns phrase-level timestamps. Long
recordings are split into chunks and the offsets are re-applied, so the
pipeline stays asynchronous (runs in the background worker).

Verify locale support (th-TH) and limits against current Microsoft docs
before production (plan §4.2 note).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Protocol

import httpx

from app.config import get_settings
from app.errors import AppError
from app.services import audio, gemini


class SpeechToText(Protocol):
    name: str

    def transcribe(self, wav_path: Path, language: str, source_name: str | None) -> list[dict]:
        """Return segments: [{id, start_ms, end_ms, text}]"""
        ...


def _locales(language: str) -> list[str]:
    return language.split("+")


def _number(segments: list[dict]) -> list[dict]:
    out = []
    for i, seg in enumerate(s for s in segments if s["text"].strip()):
        out.append({"id": i + 1, "start_ms": int(seg["start_ms"]), "end_ms": int(seg["end_ms"]),
                    "text": seg["text"].strip(), **({"locale": seg["locale"]} if seg.get("locale") else {})})
    return out


class AzureFastTranscription:
    name = "azure_speech"

    def __init__(self) -> None:
        s = get_settings()
        if not s.azure_speech_key or not (s.azure_speech_region or s.azure_speech_endpoint):
            raise AppError(500, "stt_not_configured", "ยังไม่ได้ตั้งค่า Azure AI Speech")
        base = s.azure_speech_endpoint.rstrip("/") or f"https://{s.azure_speech_region}.api.cognitive.microsoft.com"
        self.url = f"{base}/speechtotext/transcriptions:transcribe?api-version={s.azure_speech_api_version}"
        self.key = s.azure_speech_key
        self.chunk_seconds = s.stt_chunk_seconds

    def _transcribe_file(self, path: Path, language: str) -> list[dict]:
        definition = {"locales": _locales(language), "profanityFilterMode": "None"}
        with path.open("rb") as fh:
            resp = httpx.post(
                self.url,
                headers={"Ocp-Apim-Subscription-Key": self.key},
                files={"audio": (path.name, fh, "audio/wav"),
                       "definition": (None, json.dumps(definition), "application/json")},
                timeout=900,
            )
        if resp.status_code == 429:
            raise AppError(429, "stt_throttled", "บริการถอดเสียงมีคำขอมากเกินไป กรุณาลองใหม่ภายหลัง",
                           retry_after=int(resp.headers.get("Retry-After", "60")))
        if resp.status_code in (401, 403):
            raise AppError(502, "stt_auth_failed", "Azure AI Speech ปฏิเสธการเชื่อมต่อ ตรวจสอบ key/region")
        if resp.status_code >= 400:
            raise AppError(502, "stt_failed", f"Azure AI Speech ถอดเสียงไม่สำเร็จ (HTTP {resp.status_code})")
        data = resp.json()
        return [{"start_ms": p["offsetMilliseconds"],
                 "end_ms": p["offsetMilliseconds"] + p["durationMilliseconds"],
                 "text": p.get("text", ""), "locale": p.get("locale")}
                for p in data.get("phrases", [])]

    def transcribe(self, wav_path: Path, language: str, source_name: str | None) -> list[dict]:
        info = audio.probe(wav_path)
        if info.duration_ms <= self.chunk_seconds * 1000:
            return _number(self._transcribe_file(wav_path, language))
        segments: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            for chunk, offset in audio.split_wav(wav_path, Path(tmp), self.chunk_seconds):
                for seg in self._transcribe_file(chunk, language):
                    segments.append({**seg, "start_ms": seg["start_ms"] + offset, "end_ms": seg["end_ms"] + offset})
        return _number(segments)


GEMINI_STT_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["start_seconds", "end_seconds", "text"],
            },
        }
    },
    "required": ["segments"],
}

_LANGUAGE_HINT = {
    "th-TH": "Thai",
    "en-US": "English",
    "th-TH+en-US": "Thai mixed with English words and phrases (keep English terms in English)",
}

GEMINI_STT_SYSTEM = """You are a precise speech-to-text engine for business meeting recordings.
Rules:
- Transcribe verbatim in the original spoken language(s). Never translate, summarise, correct grammar or add content.
- Do not label or guess speakers.
- Split into segments at natural sentence or pause boundaries, each at most about 20 seconds long.
- start_seconds and end_seconds are measured from the beginning of THIS audio clip, in seconds (decimals allowed),
  in chronological order.
- Write a word you cannot make out as [ไม่ชัด]. Never invent words for unclear audio.
- If the clip contains no intelligible speech, return an empty segments list."""


class GeminiSpeechToText:
    """Google Gemini audio understanding, used as a free-tier transcription option.

    Audio is sent as small MP3 chunks (``GEMINI_STT_CHUNK_SECONDS``) inline; timestamps returned by
    the model are clamped to each chunk and offset to the meeting timeline. Timestamps from a
    generative model are approximate (seconds), unlike Azure AI Speech word timings.
    Free tier: Google may use the audio to improve its products — synthetic/test audio only.
    """

    name = "gemini"

    def __init__(self) -> None:
        s = get_settings()
        if not s.gemini_api_key:
            raise AppError(500, "stt_not_configured", "ยังไม่ได้ตั้งค่า GEMINI_API_KEY สำหรับถอดเสียง")
        self.model = s.gemini_stt_model
        self.chunk_seconds = s.gemini_stt_chunk_seconds

    def _transcribe_chunk(self, wav: Path, language: str, duration_ms: int) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            mp3 = Path(tmp) / "chunk.mp3"
            audio.encode_compact(wav, mp3)
            data = mp3.read_bytes()
        hint = _LANGUAGE_HINT.get(language, language)
        text = gemini.generate(
            [gemini.audio_part(data, "audio/mp3"),
             gemini.text_part(f"Transcribe this meeting audio. Spoken language: {hint}. "
                              f"Clip length: {duration_ms / 1000:.1f} seconds.")],
            system=GEMINI_STT_SYSTEM, schema=GEMINI_STT_SCHEMA, model=self.model,
            max_output_tokens=32768, purpose="ถอดเสียง",
        )
        try:
            raw = json.loads(text).get("segments", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            raise AppError(502, "stt_invalid_json", "ผลถอดเสียงจาก Gemini ไม่อยู่ในรูปแบบที่ถูกต้อง") from exc
        return _clean_model_segments(raw, duration_ms)

    def transcribe(self, wav_path: Path, language: str, source_name: str | None) -> list[dict]:
        info = audio.probe(wav_path)
        if info.duration_ms <= self.chunk_seconds * 1000:
            return _number(self._transcribe_chunk(wav_path, language, info.duration_ms))
        segments: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            for chunk, offset in audio.split_wav(wav_path, Path(tmp), self.chunk_seconds):
                chunk_ms = audio.probe(chunk).duration_ms
                for seg in self._transcribe_chunk(chunk, language, chunk_ms):
                    segments.append({**seg, "start_ms": seg["start_ms"] + offset, "end_ms": seg["end_ms"] + offset})
        return _number(segments)


def _clean_model_segments(raw: list, duration_ms: int) -> list[dict]:
    """Validate model-produced timestamps: numeric, inside the clip, end > start, chronological."""
    out: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            start = int(float(item.get("start_seconds", 0)) * 1000)
            end = int(float(item.get("end_seconds", 0)) * 1000)
        except (TypeError, ValueError):
            continue
        start = min(max(0, start), duration_ms)
        if out:
            start = max(start, out[-1]["start_ms"])  # keep chronological order
        end = min(max(end, start + 500), duration_ms) if duration_ms > start else start
        out.append({"start_ms": start, "end_ms": end, "text": text})
    return out


class MockSpeechToText:
    """Returns the reference transcript for known sample files.

    Unknown audio gets clearly-labelled placeholder segments, so the rest of
    the pipeline (summary, review, publish) can still be exercised.
    """

    name = "mock"

    def transcribe(self, wav_path: Path, language: str, source_name: str | None) -> list[dict]:
        ref_dir = get_settings().samples_dir / "reference"
        if source_name:
            ref = ref_dir / f"{Path(source_name).stem}.transcript.json"
            if ref.exists():
                return _number(json.loads(ref.read_text(encoding="utf-8"))["segments"])
        duration = audio.probe(wav_path).duration_ms
        step = 15000
        segments = []
        for i, start in enumerate(range(0, max(duration, 1), step)):
            segments.append({"start_ms": start, "end_ms": min(start + step, duration),
                             "text": f"[MOCK STT] ช่วงเสียงที่ {i + 1} — ยังไม่ได้เชื่อมต่อบริการถอดเสียงจริง"})
        return _number(segments)


def get_stt() -> SpeechToText:
    provider = get_settings().stt_provider
    if provider == "azure":
        return AzureFastTranscription()
    if provider == "gemini":
        return GeminiSpeechToText()
    return MockSpeechToText()
