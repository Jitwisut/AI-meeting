"""Meeting summarisation with evidence-backed, validated output (plan §8).

Design:
  * The transcript is shown to the model as numbered segments [S1], [S2] …
    The model may only cite segment numbers; timestamps are attached by the
    server, so the model cannot invent evidence positions.
  * Long transcripts are split into chunks (map) and merged (reduce).
  * ``validate_summary`` enforces the "no fabrication" rules regardless of
    which engine produced the draft:
      - decisions / action items / discovered topics need evidence, else dropped
      - an owner or due date must literally appear in the cited evidence, else null
      - a topic is ``resolved`` only with a stated resolution + evidence,
        otherwise it is downgraded to ``mentioned`` (mentioned != resolved)
      - every agenda topic is kept; missing ones become ``unclear``
Engines: mock (rule based, offline), Azure OpenAI, Gemini.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.config import get_settings
from app.errors import AppError

TOPIC_STATUSES = ("not_mentioned", "mentioned", "resolved", "unclear")
_STATUS_RANK = {"not_mentioned": 0, "unclear": 1, "mentioned": 2, "resolved": 3}

# JSON schema the LLM must follow (raw draft; ids/timestamps are added by the server)
_EVIDENCE = {"type": "array", "items": {"type": "integer"},
             "description": "หมายเลขช่วง transcript [S#] ที่เป็นหลักฐาน"}
LLM_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "meeting_title": {"type": "string"},
        "summary": {"type": "string"},
        "topics": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "source": {"type": "string", "enum": ["agenda", "discovered"]},
                "status": {"type": "string", "enum": list(TOPIC_STATUSES)},
                "resolution": {"type": ["string", "null"]},
                "evidence_segments": _EVIDENCE,
            },
            "required": ["title", "source", "status", "resolution", "evidence_segments"],
            "additionalProperties": False,
        }},
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence_segments": _EVIDENCE},
            "required": ["text", "evidence_segments"], "additionalProperties": False,
        }},
        "action_items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "owner": {"type": ["string", "null"]},
                "due_date": {"type": ["string", "null"]},
                "evidence_segments": _EVIDENCE,
            },
            "required": ["task", "owner", "due_date", "evidence_segments"], "additionalProperties": False,
        }},
        "open_questions": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence_segments": _EVIDENCE},
            "required": ["text", "evidence_segments"], "additionalProperties": False,
        }},
    },
    "required": ["meeting_title", "summary", "topics", "decisions", "action_items", "open_questions"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """คุณคือผู้ช่วยจดรายงานการประชุม (Minutes of Meeting) ขององค์กร
ตอบเป็น JSON ตาม schema เท่านั้น ใช้ภาษาเดียวกับ transcript (ไทยเป็นหลัก)

กติกาสำคัญ (ห้ามละเมิด):
1. ใช้เฉพาะข้อมูลที่อยู่ใน transcript เท่านั้น ห้ามเดา ห้ามแต่งเติม
2. ทุกมติ (decisions), งาน (action_items), คำถามค้าง (open_questions) และหัวข้อ ต้องอ้างอิงหมายเลขช่วง [S#] ใน evidence_segments
3. owner ต้องเป็นชื่อที่ถูกพูดถึงในช่วงหลักฐานอย่างชัดเจนเท่านั้น ถ้าไม่ระบุให้ใส่ null
4. due_date ให้คัดลอกคำที่พูดจริง เช่น "วันศุกร์นี้" ถ้าไม่มีการระบุให้ใส่ null ห้ามแปลงเป็นวันที่เอง
5. สถานะหัวข้อ:
   - "resolved" เฉพาะเมื่อมีข้อสรุป/มติที่ชัดเจน และต้องกรอก resolution
   - "mentioned" เมื่อมีการพูดถึงแต่ยังไม่มีข้อสรุป (การพูดถึงไม่ได้แปลว่าจบ)
   - "unclear" เมื่อไม่แน่ใจ
   - "not_mentioned" เมื่อไม่มีการพูดถึงเลย (ใช้กับหัวข้อตามวาระเท่านั้น)
6. ต้องใส่ทุกหัวข้อในวาระ (source="agenda") ตามชื่อเดิม และเพิ่มหัวข้ออื่นที่พบได้ (source="discovered")
7. การเลื่อนเรื่องไปประชุมครั้งหน้าไม่ถือเป็นข้อสรุปของหัวข้อนั้น"""


def format_segments(segments: list[dict]) -> str:
    def ts(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"

    return "\n".join(f"[S{s['id']} {ts(s['start_ms'])}-{ts(s['end_ms'])}] {s['text']}" for s in segments)


def build_user_prompt(segments: list[dict], agenda: list[str], title_hint: str, part: tuple[int, int]) -> str:
    agenda_text = "\n".join(f"- {a}" for a in agenda) if agenda else "- (ไม่มีวาระที่กำหนดไว้)"
    part_note = f"\n(นี่คือส่วนที่ {part[0]} จาก {part[1]} ของการประชุม)" if part[1] > 1 else ""
    return (f"ชื่อการประชุม (อาจปรับให้เหมาะสม): {title_hint}\n"
            f"วาระ/หัวข้อที่ต้องติดตาม:\n{agenda_text}{part_note}\n\nTranscript:\n{format_segments(segments)}")


# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------
class SummaryEngine(Protocol):
    name: str

    def extract(self, segments: list[dict], agenda: list[str], title_hint: str, part: tuple[int, int]) -> dict: ...
    def synthesize(self, partial_summaries: list[str], title: str) -> str: ...


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(502, "llm_invalid_json", "ผลลัพธ์จาก AI ไม่อยู่ในรูปแบบที่ถูกต้อง") from exc


def _raise_llm_http(resp: httpx.Response, provider: str) -> None:
    if resp.status_code == 429:
        raise AppError(429, "llm_throttled", f"{provider} มีคำขอมากเกินไป กรุณาลองใหม่ภายหลัง",
                       retry_after=int(resp.headers.get("Retry-After", "60") or 60))
    if resp.status_code >= 400:
        raise AppError(502, "llm_failed", f"{provider} สรุปผลไม่สำเร็จ (HTTP {resp.status_code})")


class AzureOpenAIEngine:
    name = "azure_openai"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.azure_openai_endpoint and s.azure_openai_api_key and s.azure_openai_deployment):
            raise AppError(500, "llm_not_configured", "ยังไม่ได้ตั้งค่า Azure OpenAI")
        self.url = (f"{s.azure_openai_endpoint.rstrip('/')}/openai/deployments/{s.azure_openai_deployment}"
                    f"/chat/completions?api-version={s.azure_openai_api_version}")
        self.key = s.azure_openai_api_key
        self.timeout = s.llm_timeout_seconds

    def _chat(self, messages: list[dict], schema: dict | None) -> str:
        body: dict = {"messages": messages, "temperature": 0}
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "meeting_minutes", "strict": True, "schema": schema}}
        resp = httpx.post(self.url, headers={"api-key": self.key}, json=body, timeout=self.timeout)
        _raise_llm_http(resp, "Azure OpenAI")
        return resp.json()["choices"][0]["message"]["content"]

    def extract(self, segments, agenda, title_hint, part):  # noqa: ANN001
        content = self._chat([{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": build_user_prompt(segments, agenda, title_hint, part)}],
                             LLM_OUTPUT_SCHEMA)
        return _parse_json(content)

    def synthesize(self, partial_summaries, title):  # noqa: ANN001
        return self._chat([{"role": "system", "content": "รวมบทสรุปย่อยของการประชุมเดียวกันให้เป็นย่อหน้าเดียว "
                                                           "กระชับ ไม่เพิ่มข้อมูลใหม่"},
                           {"role": "user", "content": f"การประชุม: {title}\n\n" + "\n\n".join(partial_summaries)}],
                          None).strip()


def _gemini_schema(schema: dict) -> dict:
    """Gemini's responseSchema is an OpenAPI subset: no additionalProperties, nullable flag."""
    out: dict = {}
    for k, v in schema.items():
        if k == "additionalProperties":
            continue
        if k == "type" and isinstance(v, list):
            out["type"] = [t for t in v if t != "null"][0]
            out["nullable"] = "null" in v
        elif isinstance(v, dict):
            out[k] = _gemini_schema(v) if k != "properties" else {pk: _gemini_schema(pv) for pk, pv in v.items()}
        else:
            out[k] = v
    return out


class GeminiEngine:
    """Google Gemini via REST.

    NOTE: on the free tier Google may use prompts/outputs to improve its
    products. Use only with synthetic or non-sensitive audio (plan §9).
    """

    name = "gemini"

    def __init__(self) -> None:
        s = get_settings()
        if not s.gemini_api_key:
            raise AppError(500, "llm_not_configured", "ยังไม่ได้ตั้งค่า GEMINI_API_KEY")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent"
        self.key = s.gemini_api_key
        self.timeout = s.llm_timeout_seconds

    def _generate(self, system: str, user: str, schema: dict | None) -> str:
        config: dict = {"temperature": 0}
        if schema:
            config["responseMimeType"] = "application/json"
            config["responseSchema"] = _gemini_schema(schema)
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": config}
        resp = httpx.post(self.url, headers={"x-goog-api-key": self.key}, json=body, timeout=self.timeout)
        _raise_llm_http(resp, "Gemini")
        try:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise AppError(502, "llm_empty", "Gemini ไม่ได้ส่งผลลัพธ์กลับมา (อาจถูกบล็อกโดย safety filter)") from exc

    def extract(self, segments, agenda, title_hint, part):  # noqa: ANN001
        return _parse_json(self._generate(SYSTEM_PROMPT, build_user_prompt(segments, agenda, title_hint, part),
                                          LLM_OUTPUT_SCHEMA))

    def synthesize(self, partial_summaries, title):  # noqa: ANN001
        return self._generate("รวมบทสรุปย่อยของการประชุมเดียวกันให้เป็นย่อหน้าเดียว กระชับ ไม่เพิ่มข้อมูลใหม่",
                              f"การประชุม: {title}\n\n" + "\n\n".join(partial_summaries), None).strip()


# ---------------------------------------------------------------------------
# Mock engine: deterministic keyword rules, good enough for demos and tests
# ---------------------------------------------------------------------------
_DECISION_WORDS = ("ตกลงว่า", "ตกลงกัน", "อนุมัติ", "มีมติ", "มติให้", "สรุปว่า", "ตัดสินใจว่า", "agreed", "decided")
_NEGATIONS = ("ยังไม่", "ไม่ได้", "รอ", "not yet")
_UNRESOLVED = ("ยังไม่มีข้อสรุป", "ยังไม่ได้ตัดสินใจ", "ยังไม่ได้คุย", "ยกไปประชุมครั้งหน้า", "ยังไม่ได้เริ่ม")
_OWNER_RE = re.compile(r"(คุณ[^\s]+?)(?:จะ|รับผิดชอบ)")
_DUE_RE = re.compile(r"(ภายใน\s*[^\s]+(?:\s*[^\s]+)?|วัน(?:จันทร์|อังคาร|พุธ|พฤหัสบดี|ศุกร์|เสาร์|อาทิตย์)(?:นี้|หน้า)|"
                     r"วันที่[^\s]+)")
_ACTION_HINTS = ("จะรับผิดชอบ", "รับผิดชอบ", "ต้องมีคน", "จะจัด", "จะส่ง", "จะ setup", "จะทำ", "ต้องติดตาม")


def _is_decision(text: str) -> bool:
    for w in _DECISION_WORDS:
        idx = text.find(w)
        if idx >= 0 and not any(n in text[max(0, idx - 12):idx] for n in _NEGATIONS):
            return True
    return False


def _normalise(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


class MockEngine:
    name = "mock"

    def extract(self, segments, agenda, title_hint, part):  # noqa: ANN001
        decisions, actions, topics, questions = [], [], [], []
        for s in segments:
            t = s["text"]
            if _is_decision(t):
                text = re.split(r"ตกลงว่า|อนุมัติ|มีมติให้|มีมติ|สรุปว่า|ตัดสินใจว่า", t, maxsplit=1)[-1].strip()
                if "อนุมัติ" in t:
                    text = "อนุมัติ" + text
                decisions.append({"text": text or t, "evidence_segments": [s["id"]]})
            elif any(h in t for h in _ACTION_HINTS):
                owner = _OWNER_RE.search(t)
                due = _DUE_RE.search(t)
                task = t
                if owner:
                    task = t[owner.end():].strip()
                if due:
                    task = task.replace(due.group(0), "").strip()
                task = re.sub(r"^(?:จะ)?(?:รับผิดชอบ)?", "", task).strip() or t
                actions.append({"task": task, "owner": owner.group(1) if owner else None,
                                "due_date": due.group(0).replace("ภายใน", "").strip() if due else None,
                                "evidence_segments": [s["id"]]})
            if ("ถามว่า" in t or "?" in t) and not _is_decision(t):
                questions.append({"text": t, "evidence_segments": [s["id"]]})

        # topic spans: from its first mention until the next agenda topic is mentioned
        first_hit: dict[str, int] = {}
        for title in agenda:
            key = _normalise(title)
            for idx, s in enumerate(segments):
                if key and key in _normalise(s["text"]):
                    first_hit[title] = idx
                    break
        ordered = sorted(first_hit.items(), key=lambda kv: kv[1])
        for title in agenda:
            if title not in first_hit:
                topics.append({"title": title, "source": "agenda", "status": "not_mentioned",
                               "resolution": None, "evidence_segments": []})
                continue
            start = first_hit[title]
            later = [i for _, i in ordered if i > start]
            span = segments[start:(later[0] if later else len(segments))]
            unresolved = any(any(u in s["text"] for u in _UNRESOLVED) for s in span)
            decision_seg = next((s for s in span if _is_decision(s["text"])), None)
            if decision_seg and not unresolved:
                topics.append({"title": title, "source": "agenda", "status": "resolved",
                               "resolution": decision_seg["text"],
                               "evidence_segments": [span[0]["id"], decision_seg["id"]]})
            else:
                topics.append({"title": title, "source": "agenda", "status": "mentioned", "resolution": None,
                               "evidence_segments": [s["id"] for s in span]})
        summary = " ".join(s["text"] for s in segments[:3])
        return {"meeting_title": title_hint, "summary": f"[สรุปอัตโนมัติแบบ mock] {summary}"[:600],
                "topics": topics, "decisions": decisions, "action_items": actions, "open_questions": questions}

    def synthesize(self, partial_summaries, title):  # noqa: ANN001
        return " ".join(partial_summaries)[:1200]


def get_engine() -> SummaryEngine:
    choice = get_settings().summarizer
    if choice == "azure_openai":
        return AzureOpenAIEngine()
    if choice == "gemini":
        return GeminiEngine()
    return MockEngine()


# ---------------------------------------------------------------------------
# Chunking + merge
# ---------------------------------------------------------------------------
def chunk_segments(segments: list[dict], max_chars: int) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for s in segments:
        length = len(s["text"]) + 20
        if current and size + length > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(s)
        size += length
    if current:
        chunks.append(current)
    return chunks or [[]]


def merge_drafts(drafts: list[dict]) -> dict:
    if len(drafts) == 1:
        return drafts[0]
    topics: dict[str, dict] = {}
    for d in drafts:
        for t in d.get("topics", []):
            key = _normalise(t.get("title", ""))
            cur = topics.get(key)
            if cur is None:
                topics[key] = {**t, "evidence_segments": list(t.get("evidence_segments", []))}
                continue
            cur["evidence_segments"] = sorted(set(cur["evidence_segments"]) | set(t.get("evidence_segments", [])))
            if _STATUS_RANK.get(t.get("status"), 0) > _STATUS_RANK.get(cur.get("status"), 0):
                cur["status"] = t["status"]
                cur["resolution"] = t.get("resolution") or cur.get("resolution")
            if cur.get("source") != "agenda" and t.get("source") == "agenda":
                cur["source"] = "agenda"

    def concat(field: str, text_key: str) -> list[dict]:
        seen, out = set(), []
        for d in drafts:
            for item in d.get(field, []):
                k = _normalise(item.get(text_key, ""))
                if k and k not in seen:
                    seen.add(k)
                    out.append(item)
        return out

    return {
        "meeting_title": drafts[0].get("meeting_title", ""),
        "summary": "",
        "topics": list(topics.values()),
        "decisions": concat("decisions", "text"),
        "action_items": concat("action_items", "task"),
        "open_questions": concat("open_questions", "text"),
    }


# ---------------------------------------------------------------------------
# Validation (anti-hallucination guardrails)
# ---------------------------------------------------------------------------
def _evidence(ids: list, by_id: dict[int, dict]) -> list[dict]:
    out, seen = [], set()
    for raw in ids or []:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            continue
        if sid in by_id and sid not in seen:
            seen.add(sid)
            s = by_id[sid]
            out.append({"segment_id": sid, "start_ms": s["start_ms"], "end_ms": s["end_ms"], "text": s["text"]})
    return sorted(out, key=lambda e: e["start_ms"])


def _appears_in(value: str, evidence: list[dict]) -> bool:
    needle = _normalise(value)
    if not needle:
        return False
    haystack = _normalise(" ".join(e["text"] for e in evidence))
    if needle in haystack:
        return True
    # allow the honorific to be added/removed: "คุณสมชาย" vs "สมชาย"
    bare = needle.removeprefix("คุณ").removeprefix("k.").removeprefix("khun")
    return len(bare) >= 2 and bare in haystack


def _id() -> str:
    return uuid.uuid4().hex[:10]


def validate_summary(draft: dict, segments: list[dict], agenda: list[str]) -> dict:
    by_id = {s["id"]: s for s in segments}
    warnings: list[str] = []

    decisions = []
    for d in draft.get("decisions", []):
        ev = _evidence(d.get("evidence_segments"), by_id)
        text = (d.get("text") or "").strip()
        if not text:
            continue
        if not ev:
            warnings.append(f"ตัดมติที่ไม่มีหลักฐานใน transcript: “{text[:80]}”")
            continue
        decisions.append({"id": _id(), "text": text, "evidence": ev})

    actions = []
    for a in draft.get("action_items", []):
        ev = _evidence(a.get("evidence_segments"), by_id)
        task = (a.get("task") or "").strip()
        if not task:
            continue
        if not ev:
            warnings.append(f"ตัดงานที่ไม่มีหลักฐานใน transcript: “{task[:80]}”")
            continue
        owner, due = a.get("owner"), a.get("due_date")
        if owner and not _appears_in(owner, ev):
            warnings.append(f"ลบชื่อผู้รับผิดชอบ “{owner}” เพราะไม่ปรากฏในหลักฐาน (งาน: {task[:60]})")
            owner = None
        if due and not _appears_in(due, ev):
            warnings.append(f"ลบกำหนดส่ง “{due}” เพราะไม่ปรากฏในหลักฐาน (งาน: {task[:60]})")
            due = None
        actions.append({"id": _id(), "task": task, "owner": owner, "due_date": due, "status": "open",
                        "evidence": ev})

    questions = []
    for q in draft.get("open_questions", []):
        ev = _evidence(q.get("evidence_segments"), by_id)
        if (q.get("text") or "").strip() and ev:
            questions.append({"id": _id(), "text": q["text"].strip(), "evidence": ev})

    topics: list[dict] = []
    agenda_keys = {_normalise(a): a for a in agenda}
    seen_agenda: set[str] = set()
    for t in draft.get("topics", []):
        title = (t.get("title") or "").strip()
        if not title:
            continue
        key = _normalise(title)
        source = "agenda" if key in agenda_keys else "discovered"
        if source == "agenda":
            if key in seen_agenda:
                continue
            seen_agenda.add(key)
            title = agenda_keys[key]
        status = t.get("status") if t.get("status") in TOPIC_STATUSES else "unclear"
        ev = _evidence(t.get("evidence_segments"), by_id)
        resolution = (t.get("resolution") or "").strip() or None
        if source == "discovered" and not ev:
            warnings.append(f"ตัดหัวข้อที่ไม่มีหลักฐานใน transcript: “{title[:80]}”")
            continue
        if source == "discovered" and status == "not_mentioned":
            continue
        if status in ("mentioned", "resolved") and not ev:
            warnings.append(f"หัวข้อ “{title}” ไม่มีหลักฐาน จึงเปลี่ยนสถานะเป็นไม่ชัดเจน")
            status, resolution = "unclear", None
        if status == "resolved" and not resolution:
            warnings.append(f"หัวข้อ “{title}” ถูกพูดถึงแต่ไม่มีข้อสรุปที่ระบุได้ จึงเปลี่ยนเป็น 'มีการพูดถึง'")
            status = "mentioned"
        if status == "not_mentioned":
            ev, resolution = [], None
        if status != "resolved":
            resolution = None
        topics.append({"id": _id(), "title": title, "source": source, "status": status,
                       "resolution": resolution, "evidence": ev, "verified_by": None})
    for key, title in agenda_keys.items():
        if key not in seen_agenda:
            warnings.append(f"AI ไม่ได้ประเมินหัวข้อ “{title}” กรุณาตรวจสอบเอง")
            topics.append({"id": _id(), "title": title, "source": "agenda", "status": "unclear",
                           "resolution": None, "evidence": [], "verified_by": None})
    order = {_normalise(a): i for i, a in enumerate(agenda)}
    topics.sort(key=lambda t: order.get(_normalise(t["title"]), len(order)))

    return {
        "meeting_title": (draft.get("meeting_title") or "").strip(),
        "summary": (draft.get("summary") or "").strip(),
        "topics": topics,
        "decisions": decisions,
        "action_items": actions,
        "open_questions": questions,
        "validation_warnings": warnings,
    }


def summarize(segments: list[dict], agenda: list[str], title_hint: str,
              engine: SummaryEngine | None = None) -> dict:
    engine = engine or get_engine()
    chunks = chunk_segments(segments, get_settings().summary_chunk_chars)
    drafts = [engine.extract(c, agenda, title_hint, (i + 1, len(chunks))) for i, c in enumerate(chunks)]
    merged = merge_drafts(drafts)
    if len(drafts) > 1:
        merged["summary"] = engine.synthesize([d.get("summary", "") for d in drafts], title_hint)
    result = validate_summary(merged, segments, agenda)
    result["meeting_title"] = result["meeting_title"] or title_hint
    result["generated_by"] = engine.name
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result
