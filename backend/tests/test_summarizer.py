from __future__ import annotations

from app.services.summarizer import chunk_segments, merge_drafts, summarize, validate_summary

SEGMENTS = [
    {"id": 1, "start_ms": 0, "end_ms": 4000, "text": "หัวข้อแรกคือเรื่องงบประมาณ ยังไม่มีข้อสรุป"},
    {"id": 2, "start_ms": 4000, "end_ms": 8000, "text": "คุณสมชายจะส่งรายงานภายในวันศุกร์นี้"},
    {"id": 3, "start_ms": 8000, "end_ms": 12000, "text": "ที่ประชุมตกลงว่าจะใช้ PostgreSQL"},
]


def test_mentioned_is_not_marked_resolved_without_resolution():
    draft = {"topics": [{"title": "งบประมาณ", "source": "agenda", "status": "resolved", "resolution": None,
                         "evidence_segments": [1]}]}
    out = validate_summary(draft, SEGMENTS, ["งบประมาณ"])
    assert out["topics"][0]["status"] == "mentioned"
    assert out["validation_warnings"]


def test_fabricated_evidence_and_items_are_dropped():
    draft = {
        "decisions": [{"text": "อนุมัติงบ 10 ล้าน", "evidence_segments": [42]},
                      {"text": "ใช้ PostgreSQL", "evidence_segments": [3]}],
        "action_items": [{"task": "ทำสไลด์", "owner": "คุณวิชัย", "due_date": "พรุ่งนี้", "evidence_segments": [2]},
                         {"task": "งานลอย", "owner": None, "due_date": None, "evidence_segments": []}],
        "topics": [{"title": "หัวข้อแต่งขึ้น", "source": "discovered", "status": "mentioned", "resolution": None,
                    "evidence_segments": []}],
    }
    out = validate_summary(draft, SEGMENTS, [])
    assert [d["text"] for d in out["decisions"]] == ["ใช้ PostgreSQL"]
    assert out["decisions"][0]["evidence"][0]["start_ms"] == 8000
    assert len(out["action_items"]) == 1
    assert out["action_items"][0]["owner"] is None  # "คุณวิชัย" not in evidence
    assert out["action_items"][0]["due_date"] is None  # "พรุ่งนี้" not in evidence
    assert out["topics"] == []


def test_owner_and_due_kept_when_in_evidence():
    draft = {"action_items": [{"task": "ส่งรายงาน", "owner": "สมชาย", "due_date": "วันศุกร์นี้",
                               "evidence_segments": [2]}]}
    out = validate_summary(draft, SEGMENTS, [])
    assert out["action_items"][0]["owner"] == "สมชาย"
    assert out["action_items"][0]["due_date"] == "วันศุกร์นี้"


def test_missing_agenda_topic_becomes_unclear():
    out = validate_summary({"topics": []}, SEGMENTS, ["การทดสอบ"])
    assert out["topics"][0]["status"] == "unclear"


def test_mentioned_without_evidence_becomes_unclear():
    draft = {"topics": [{"title": "งบประมาณ", "source": "agenda", "status": "mentioned", "resolution": None,
                         "evidence_segments": []}]}
    assert validate_summary(draft, SEGMENTS, ["งบประมาณ"])["topics"][0]["status"] == "unclear"


def test_chunk_and_merge_keeps_best_status():
    chunks = chunk_segments(SEGMENTS * 5, max_chars=120)
    assert len(chunks) > 1
    merged = merge_drafts([
        {"topics": [{"title": "งบประมาณ", "source": "agenda", "status": "mentioned", "resolution": None,
                     "evidence_segments": [1]}], "decisions": [{"text": "a", "evidence_segments": [3]}]},
        {"topics": [{"title": "งบประมาณ", "source": "agenda", "status": "resolved", "resolution": "ใช้ PostgreSQL",
                     "evidence_segments": [3]}], "decisions": [{"text": "a", "evidence_segments": [3]}]},
    ])
    assert merged["topics"][0]["status"] == "resolved"
    assert merged["topics"][0]["evidence_segments"] == [1, 3]
    assert len(merged["decisions"]) == 1


def test_summarize_with_chunking(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "summary_chunk_chars", 60)
    out = summarize(SEGMENTS, ["งบประมาณ"], "ทดสอบ")
    assert out["generated_by"] == "mock"
    assert out["topics"][0]["status"] == "mentioned"
    assert out["decisions"] and out["decisions"][0]["evidence"]


def test_gemini_schema_conversion():
    from app.services.summarizer import LLM_OUTPUT_SCHEMA, _gemini_schema

    g = _gemini_schema(LLM_OUTPUT_SCHEMA)
    owner = g["properties"]["action_items"]["items"]["properties"]["owner"]
    assert owner == {"type": "string", "nullable": True}
    assert "additionalProperties" not in str(g)
