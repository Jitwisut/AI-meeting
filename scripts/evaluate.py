"""Quality evaluation over samples/ (plan §11 Metrics).

Runs the *currently configured* STT and summariser (see .env) on every sample
meeting and compares against the hand-written references:

  * CER (character error rate; the main metric for Thai, which has no spaces)
    and WER (whitespace tokens; only meaningful for English parts)
  * topic status accuracy (mentioned / resolved / not_mentioned …)
  * precision / recall of decisions and action items (fuzzy text match)
  * owner accuracy for matched action items
  * hallucination count = predicted decisions/actions with no reference match
    + items the validator had to drop or correct
  * processing time per stage

Usage (from repo root):
  backend/.venv/bin/python scripts/evaluate.py [--out docs/evaluation-report.md]

With STT_PROVIDER=mock the transcript *is* the reference, so CER is 0 by
construction; the summary metrics are still real. Set STT_PROVIDER=azure and
SUMMARIZER=azure_openai|gemini to measure the real services.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.services import audio  # noqa: E402
from app.services.speech_to_text import get_stt  # noqa: E402
from app.services.summarizer import summarize  # noqa: E402

MATCH_THRESHOLD = 0.55


def norm(text: str) -> str:
    return re.sub(r"[\s.,!?\"'“”()\-–:;]+", "", (text or "").lower())


def edit_distance(a: list | str, b: list | str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    return edit_distance(r, h) / max(1, len(r))


def wer(ref: str, hyp: str) -> float:
    r, h = ref.lower().split(), hyp.lower().split()
    return edit_distance(r, h) / max(1, len(r))


def similar(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def match(pred: list[str], ref: list[str]) -> list[tuple[int, int]]:
    """Greedy one-to-one matching by similarity."""
    pairs = sorted(((similar(p, r), i, j) for i, p in enumerate(pred) for j, r in enumerate(ref)), reverse=True)
    used_p, used_r, out = set(), set(), []
    for score, i, j in pairs:
        if score < MATCH_THRESHOLD or i in used_p or j in used_r:
            continue
        used_p.add(i)
        used_r.add(j)
        out.append((i, j))
    return out


def pr(n_match: int, n_pred: int, n_ref: int) -> tuple[float, float]:
    precision = n_match / n_pred if n_pred else (1.0 if not n_ref else 0.0)
    recall = n_match / n_ref if n_ref else 1.0
    return precision, recall


def evaluate_sample(meeting_file: Path) -> dict:
    meeting = json.loads(meeting_file.read_text(encoding="utf-8"))
    mid = meeting["id"]
    expected = meeting["expected"]
    ref_transcript = json.loads((ROOT / "samples" / "reference" / f"{mid}.transcript.json").read_text(encoding="utf-8"))
    src = ROOT / "samples" / "audio" / f"{mid}.wav"

    timings = {}
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "normalized.wav"
        t0 = time.perf_counter()
        audio.convert_to_wav(src, wav)
        timings["convert_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        segments = get_stt().transcribe(wav, meeting["language"], src.name)
        timings["transcribe_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    summary = summarize(segments, meeting["agenda"], meeting["title"])
    timings["summarize_s"] = time.perf_counter() - t0

    ref_text = " ".join(s["text"] for s in ref_transcript["segments"])
    hyp_text = " ".join(s["text"] for s in segments)

    topic_status = {norm(t["title"]): t["status"] for t in summary["topics"]}
    topic_rows = [(t["title"], t["status"], topic_status.get(norm(t["title"]), "missing")) for t in expected["topics"]]
    topic_correct = sum(1 for _, exp, got in topic_rows if exp == got)
    false_resolved = sum(1 for _, exp, got in topic_rows if got == "resolved" and exp != "resolved")

    pred_dec = [d["text"] for d in summary["decisions"]]
    dec_pairs = match(pred_dec, expected["decisions"])
    pred_act = [a["task"] for a in summary["action_items"]]
    act_pairs = match(pred_act, [a["task"] for a in expected["action_items"]])
    owner_ok = sum(
        1 for i, j in act_pairs
        if norm(summary["action_items"][i]["owner"] or "") == norm(expected["action_items"][j]["owner"] or "")
    )
    hallucinations = (len(pred_dec) - len(dec_pairs)) + (len(pred_act) - len(act_pairs))

    return {
        "id": mid,
        "title": meeting["title"],
        "language": meeting["language"],
        "duration_s": ref_transcript["duration_ms"] / 1000,
        "cer": cer(ref_text, hyp_text),
        "wer": wer(ref_text, hyp_text),
        "topics": topic_rows,
        "topic_accuracy": topic_correct / max(1, len(topic_rows)),
        "false_resolved": false_resolved,
        "decision_pr": pr(len(dec_pairs), len(pred_dec), len(expected["decisions"])),
        "action_pr": pr(len(act_pairs), len(pred_act), len(expected["action_items"])),
        "owner_accuracy": owner_ok / len(act_pairs) if act_pairs else None,
        "hallucinations": hallucinations,
        "validator_corrections": len(summary.get("validation_warnings", [])),
        "unmatched_predictions": [pred_dec[i] for i in range(len(pred_dec)) if i not in {p for p, _ in dec_pairs}]
        + [pred_act[i] for i in range(len(pred_act)) if i not in {p for p, _ in act_pairs}],
        "timings": timings,
    }


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def render(results: list[dict]) -> str:
    s = get_settings()
    n = len(results)
    avg = lambda key: sum(r[key] for r in results) / n  # noqa: E731
    avg_p = lambda key, k: sum(r[key][k] for r in results) / n  # noqa: E731
    lines = [
        "# รายงานผลการประเมินคุณภาพ (Evaluation Report)",
        "",
        f"สร้างเมื่อ {datetime.now():%Y-%m-%d %H:%M} ด้วย `scripts/evaluate.py`",
        "",
        f"- Speech-to-Text: **{s.stt_provider}**",
        f"- Summarizer: **{s.summarizer}**",
        f"- ชุดทดสอบ: {n} ไฟล์เสียงสังเคราะห์ภาษาไทย/ไทยปนอังกฤษใน `samples/` (macOS TTS เสียง Kanya)",
        "",
    ]
    if s.stt_provider == "mock":
        lines += ["> **หมายเหตุ:** STT แบบ mock คืนบทถอดเสียงอ้างอิงโดยตรง ค่า CER/WER จึงเป็น 0 โดยนิยาม "
                  "ต้องตั้ง `STT_PROVIDER=azure` เพื่อวัดคุณภาพการถอดเสียงจริง", ""]
    if s.summarizer == "mock":
        lines += ["> **หมายเหตุ:** Summarizer แบบ mock ใช้กฎคำสำคัญ (rule-based) ผลด้านล่างคือ baseline "
                  "สำหรับเปรียบเทียบกับ Azure OpenAI / Gemini", ""]
    lines += [
        "## สรุปภาพรวม",
        "",
        "| ตัวชี้วัด | ค่าเฉลี่ย |",
        "|---|---|",
        f"| CER (Character Error Rate) | {pct(avg('cer'))} |",
        f"| WER (whitespace tokens) | {pct(avg('wer'))} |",
        f"| ความถูกต้องของสถานะหัวข้อ | {pct(avg('topic_accuracy'))} |",
        f"| หัวข้อที่ถูกติ๊ก 'ได้ข้อสรุป' ผิด | {sum(r['false_resolved'] for r in results)} รายการ |",
        f"| Precision / Recall มติ | {pct(avg_p('decision_pr', 0))} / {pct(avg_p('decision_pr', 1))} |",
        f"| Precision / Recall action items | {pct(avg_p('action_pr', 0))} / {pct(avg_p('action_pr', 1))} |",
        f"| Hallucination count (มติ/งานที่ไม่ตรงกับ reference) | {sum(r['hallucinations'] for r in results)} |",
        f"| รายการที่ validator ตัด/แก้ | {sum(r['validator_corrections'] for r in results)} |",
        f"| เวลาเฉลี่ยถอดเสียง + สรุป ต่อไฟล์ | {avg_p('timings', 'transcribe_s') + avg_p('timings', 'summarize_s'):.2f} วินาที |",
        "",
        "## รายไฟล์",
        "",
    ]
    for r in results:
        dp, dr = r["decision_pr"]
        ap, ar = r["action_pr"]
        lines += [
            f"### {r['title']} (`{r['id']}`, {r['language']}, {r['duration_s']:.0f} วินาที)",
            "",
            f"- CER {pct(r['cer'])}, WER {pct(r['wer'])}",
            f"- มติ P/R {pct(dp)}/{pct(dr)}, งาน P/R {pct(ap)}/{pct(ar)}, ผู้รับผิดชอบถูก {pct(r['owner_accuracy'])}",
            f"- hallucination {r['hallucinations']}, validator แก้ไข {r['validator_corrections']} รายการ",
            f"- เวลา: แปลงไฟล์ {r['timings']['convert_s']:.2f}s, ถอดเสียง {r['timings']['transcribe_s']:.2f}s, "
            f"สรุป {r['timings']['summarize_s']:.2f}s",
            "",
            "| หัวข้อ | คาดหวัง | ระบบให้ |",
            "|---|---|---|",
            *[f"| {t} | {exp} | {got}{'' if exp == got else ' ✗'} |" for t, exp, got in r["topics"]],
            "",
        ]
        if r["unmatched_predictions"]:
            lines += ["รายการที่ระบบสร้างแต่ไม่มีใน reference:", *[f"- {u}" for u in r["unmatched_predictions"]], ""]
    lines += [
        "## เกณฑ์ที่ต้องตกลงกับพี่เลี้ยง",
        "",
        "ยังไม่มีตัวเลขเป้าหมายจากเอกสารโครงการ (plan §11) ให้ใช้ตารางนี้เป็น baseline "
        "แล้วกำหนดเกณฑ์ผ่าน เช่น CER ≤ X%, ไม่มีหัวข้อที่ติ๊ก 'ได้ข้อสรุป' ผิด, hallucination = 0 ก่อนเริ่ม UAT "
        "และควรเพิ่มไฟล์เสียงประชุมจริงที่ได้รับอนุญาตพร้อม reference ที่คนตรวจ",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "docs" / "evaluation-report.md"))
    args = parser.parse_args()
    results = [evaluate_sample(f) for f in sorted((ROOT / "samples" / "meetings").glob("*.json"))]
    report = render(results)
    Path(args.out).write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
