"""Minimal Google Gemini REST client (generateContent), shared by summariser and speech-to-text.

NOTE: on the free tier Google may use prompts, audio and outputs to improve its products.
Use only with synthetic or non-sensitive audio (plan §9). For company data use an approved
service (e.g. Azure OpenAI / Azure AI Speech inside the company tenant).
"""
from __future__ import annotations

import base64
import time

import httpx

from app.config import get_settings
from app.errors import AppError

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_ATTEMPTS = 4
MAX_RETRY_WAIT = 60  # seconds; jobs run in the background so waiting out a short throttle is fine


def to_gemini_schema(schema: dict) -> dict:
    """Gemini's responseSchema is an OpenAPI subset: no additionalProperties, `nullable` instead of type lists."""
    out: dict = {}
    for k, v in schema.items():
        if k == "additionalProperties":
            continue
        if k == "type" and isinstance(v, list):
            out["type"] = [t for t in v if t != "null"][0]
            out["nullable"] = "null" in v
        elif k == "properties" and isinstance(v, dict):
            out[k] = {pk: to_gemini_schema(pv) for pk, pv in v.items()}
        elif isinstance(v, dict):
            out[k] = to_gemini_schema(v)
        else:
            out[k] = v
    return out


def audio_part(data: bytes, mime_type: str) -> dict:
    return {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}}


def text_part(text: str) -> dict:
    return {"text": text}


def generate(parts: list[dict], *, system: str | None = None, schema: dict | None = None,
             model: str | None = None, max_output_tokens: int | None = None, purpose: str = "Gemini") -> str:
    """Call generateContent and return the concatenated text of the first candidate."""
    s = get_settings()
    if not s.gemini_api_key:
        raise AppError(500, "gemini_not_configured", "ยังไม่ได้ตั้งค่า GEMINI_API_KEY")
    config: dict = {"temperature": 0}
    if schema:
        config["responseMimeType"] = "application/json"
        config["responseSchema"] = to_gemini_schema(schema)
    if max_output_tokens:
        config["maxOutputTokens"] = max_output_tokens
    body: dict = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    url = f"{API_BASE}/{model or s.gemini_model}:generateContent"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = httpx.post(url, headers={"x-goog-api-key": s.gemini_api_key}, json=body,
                              timeout=s.llm_timeout_seconds)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise AppError(504, "gemini_timeout", f"{purpose}: Gemini ไม่ตอบกลับภายในเวลาที่กำหนด") from exc
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
            wait = resp.headers.get("Retry-After")
            time.sleep(min(int(wait) if wait and wait.isdigit() else 5 * 2 ** attempt, MAX_RETRY_WAIT))
            continue
        break

    if resp.status_code == 429:
        raise AppError(429, "gemini_quota", f"{purpose}: ใช้โควตา Gemini ฟรีเกินกำหนด กรุณาลองใหม่ภายหลัง",
                       retry_after=60)
    if resp.status_code in (400, 403) and "API key" in resp.text:
        raise AppError(502, "gemini_auth_failed", "GEMINI_API_KEY ไม่ถูกต้องหรือไม่มีสิทธิ์ใช้ model นี้")
    if resp.status_code == 404:
        raise AppError(502, "gemini_model_not_found", f"ไม่พบ model Gemini ที่ตั้งค่าไว้ ({model or s.gemini_model})")
    if resp.status_code >= 400:
        raise AppError(502, "gemini_failed", f"{purpose}: Gemini ทำงานไม่สำเร็จ (HTTP {resp.status_code})")

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "unknown")
        raise AppError(502, "gemini_blocked", f"{purpose}: Gemini ไม่ส่งผลลัพธ์กลับมา (blocked: {reason})")
    cand = candidates[0]
    if cand.get("finishReason") == "MAX_TOKENS":
        raise AppError(502, "gemini_truncated", f"{purpose}: ผลลัพธ์จาก Gemini ยาวเกินกำหนด ลองลดขนาดช่วงเสียง")
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    if not text.strip():
        raise AppError(502, "gemini_empty", f"{purpose}: Gemini ส่งผลลัพธ์ว่างกลับมา")
    return text
