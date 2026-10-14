# AI Meeting Minutes Platform

ระบบถอดเสียงประชุมภาษาไทย สรุปหัวข้อ มติ และงานติดตามด้วย AI พร้อมหลักฐานอ้างอิงจากบทถอดเสียง
ให้คนตรวจทานและอนุมัติ แล้วจึงส่งออกเป็น Word ลง SharePoint และส่งสรุปเข้าแชทกลุ่ม Microsoft Teams
(แผนงานฉบับเต็ม: [plan.md](plan.md))

```
Audio (SharePoint / อัปโหลด / อัดผ่านเว็บ) → Speech-to-Text → Structured Summary → Human Review → Publish
```

## เริ่มใช้งาน (โหมด mock ไม่ต้องมี credentials)

```bash
cp .env.example .env
```

```bash
docker compose up -d --build
```

- เว็บ: http://localhost:3000
- API docs: http://localhost:8000/api/docs

ในโหมด mock ระบบใช้ SharePoint/Teams จำลองและไฟล์เสียงสังเคราะห์ภาษาไทยใน `samples/` เลือกผู้ใช้ทดสอบได้ที่มุมล่างซ้าย
(`other-user` ใช้ทดสอบว่ามองไม่เห็นข้อมูลของผู้อื่น) ข้อความที่ "ส่งเข้า Teams" จะถูกเขียนลง volume `storage` ที่ `/data/mock_teams/messages.jsonl`

เมื่อได้ credentials จริงแล้ว ดู [docs/setup-credentials.md](docs/setup-credentials.md) และวิธี deploy frontend บน Vercel ดู [docs/deploy-vercel.md](docs/deploy-vercel.md)

### รันแบบไม่ใช้ Docker (พัฒนา)

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

ค่าเริ่มต้นของ backend เมื่อรันนอก Docker คือ SQLite + `QUEUE_MODE=sync` (ประมวลผลในคำขอเดียว) ต้องมี `ffmpeg` ในเครื่อง

## ทดสอบ

```bash
cd backend && .venv/bin/python -m pytest -q
```

```bash
./scripts/e2e_mock.sh
```

```bash
backend/.venv/bin/python scripts/evaluate.py
```

- `pytest` — 42 tests: pipeline, สิทธิ์, ไฟล์ปลอม, ไฟล์อัดจาก Chrome ที่ไม่มี duration, คิวล่ม/งานค้าง, การ retry, การกันส่งซ้ำ (กดซ้ำ / timeout หลังส่ง), chat ที่ไม่ใช่ของผู้ใช้, ต้องอนุมัติก่อนส่ง, mentioned ≠ resolved, ฟอนต์ภาษาไทยใน DOCX, Graph pagination/429
- `e2e_mock.sh` — เดิน journey เต็มกับ stack ที่รันอยู่ (Postgres + Redis + worker)
- `evaluate.py` — วัด CER/WER, precision/recall, hallucination, เวลา → [docs/evaluation-report.md](docs/evaluation-report.md)
- `scripts/generate_samples.py` — สร้างไฟล์เสียงตัวอย่างใหม่ (macOS `say -v Kanya` + ffmpeg)

## โครงสร้าง

```text
backend/    FastAPI + SQLAlchemy + RQ worker (services: sharepoint, speech_to_text, summarizer, teams, exporter)
frontend/   Next.js 15 + TypeScript + Tailwind (ภาษาไทย)
docs/       architecture, api-contract, security-checklist, setup-credentials, evaluation-report
samples/    ไฟล์เสียงสังเคราะห์ + transcript/summary อ้างอิง (ไม่มีข้อมูลจริง)
scripts/    generate_samples.py, evaluate.py, e2e_mock.sh
```

## สถานะเทียบกับ plan

| plan | สถานะ |
|---|---|
| MVP 1 Entra ID sign-in | ✅ MSAL (PKCE) + JWT validation + OBO — ทดสอบด้วย mock แล้ว **ยังไม่ได้ทดสอบกับ tenant จริง** |
| MVP 2 เลือก/ดาวน์โหลดไฟล์ SharePoint | ✅ mock ทดสอบแล้ว / Graph adapter รอทดสอบจริง |
| MVP 3 อัปโหลด MP3/WAV + อัดเสียงผ่านเบราว์เซอร์ | ✅ ทดสอบด้วย MediaRecorder จริงใน Chromium (สัญญาณสังเคราะห์) — ควรลองกับไมโครโฟนจริงและ Safari |
| MVP 4 ถอดเสียง + timestamp | ✅ Azure fast transcription (รอ key), Gemini (ฟรี, test audio เท่านั้น) + mock |
| MVP 5 สรุปพร้อมหลักฐาน | ✅ Azure OpenAI / Gemini / mock + validator กันการแต่งข้อมูล |
| MVP 6 Review / แก้ไข / อนุมัติ | ✅ |
| MVP 7 Export DOCX → SharePoint | ✅ (PDF ผ่านการพิมพ์ของเบราว์เซอร์) |
| MVP 8 เลือก Group Chat + ส่งหลังอนุมัติ | ✅ delegated send, กันส่งซ้ำ |
| MVP 9 สถานะงาน ประวัติ retry | ✅ |
| §11 ชุดทดสอบ + รายงานคุณภาพ | ✅ baseline (mock) — ต้องรันซ้ำกับบริการจริงและเสียงจริง |
| §13 / §14 งานกับพี่เลี้ยงและ IT | ⬜ ต้องดำเนินการโดยผู้รับผิดชอบโครงการ (ดู checklist ใน setup-credentials) |

ไม่อยู่ใน MVP ตาม plan: speaker diarization, bot เข้าประชุม, real-time streaming, ส่งอัตโนมัติโดยไม่อนุมัติ
