#!/usr/bin/env bash
# End-to-end smoke test against a running stack in mock mode (docker compose up).
# Journey: SharePoint file -> process -> transcript/summary -> edit -> approve -> export -> publish (x2).
set -euo pipefail
API="${API:-http://localhost:8000}"
CHAT="19:mock-group-project@thread.v2"
j() { python3 -c "import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }

echo "1) create meeting from SharePoint"
MID=$(curl -sf -X POST "$API/api/meetings" -H 'Content-Type: application/json' -d '{
  "drive_id":"mock-drive-audio","item_id":"mock-item-project-sync-03.mp3","language":"th-TH",
  "agenda":["ออกแบบฐานข้อมูล","การเชื่อมต่อ SharePoint","งบประมาณ Azure","การทดสอบระบบ UAT"],
  "consent_ai_processing":true}' | j 'd["id"]')
echo "   meeting=$MID"

echo "2) start processing (background worker)"
curl -sf -X POST "$API/api/meetings/$MID/process" > /dev/null
for i in $(seq 1 60); do
  STATUS=$(curl -sf "$API/api/meetings/$MID" | j 'd["status"]')
  [ "$STATUS" = "awaiting_review" ] && break
  [ "$STATUS" = "failed" ] && { curl -s "$API/api/meetings/$MID"; exit 1; }
  sleep 1
done
echo "   status=$STATUS"

echo "3) transcript + summary"
curl -sf "$API/api/meetings/$MID/transcript" | j '"   segments=%d" % len(d["segments"])'
curl -sf "$API/api/meetings/$MID/summary" | j '"\n".join("   %s: %s" % (t["status"], t["title"]) for t in d["summary"]["topics"])'

echo "4) edit summary (PATCH)"
VERSION=$(curl -sf "$API/api/meetings/$MID/summary" | python3 -c '
import sys, json
d = json.load(sys.stdin); s = d["summary"]
ev = lambda xs: [{"segment_id": e["segment_id"]} for e in xs]
body = {"version": d["report"]["version"], "summary": {
  "meeting_title": s["meeting_title"], "summary": "ทบทวนความคืบหน้าโครงการ: ตกลงใช้ PostgreSQL, SharePoint รอ IT",
  "topics": [{"id": t["id"], "title": t["title"], "source": t["source"], "status": t["status"],
              "resolution": t["resolution"], "evidence": ev(t["evidence"]), "verified": True} for t in s["topics"]],
  "decisions": [{"id": x["id"], "text": x["text"], "evidence": ev(x["evidence"])} for x in s["decisions"]],
  "action_items": [{"id": x["id"], "task": x["task"], "owner": x["owner"], "due_date": x["due_date"],
                    "status": x["status"], "evidence": ev(x["evidence"])} for x in s["action_items"]],
  "open_questions": []}}
json.dump(body, open("/tmp/mom_patch.json", "w"), ensure_ascii=False)
print(d["report"]["version"])')
curl -sf -X PATCH "$API/api/meetings/$MID/summary" -H 'Content-Type: application/json' \
  --data-binary @/tmp/mom_patch.json | j '"   version=%d approved=%s" % (d["report"]["version"], d["report"]["is_approved"])'
rm -f /tmp/mom_patch.json

echo "5) approve"
NEWV=$((VERSION + 1))
curl -sf -X POST "$API/api/meetings/$MID/approve" -H 'Content-Type: application/json' \
  -d "{\"version\":$NEWV}" | j '"   status=" + d["status"]'

echo "6) export DOCX to SharePoint"
curl -sf -X POST "$API/api/meetings/$MID/export" | j '"   " + d["sharepoint_web_url"]'
curl -sf -o /tmp/mom_report.docx "$API/api/meetings/$MID/export/docx" && echo "   docx bytes=$(wc -c < /tmp/mom_report.docx)"

echo "7) publish to Teams twice (double click)"
for n in 1 2; do
  curl -sf -X POST "$API/api/meetings/$MID/publish" -H 'Content-Type: application/json' \
    -d "{\"chat_id\":\"$CHAT\",\"confirm_recipients\":true}" \
    | j '"   duplicate=%s message_id=%s" % (d["duplicate"], d["publication"]["message_id"])'
done
curl -sf "$API/api/meetings/$MID" | j '"   final status=%s publications=%d" % (d["status"], len(d["publications"]))'
echo "OK"
