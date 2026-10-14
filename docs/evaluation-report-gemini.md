# รายงานผลการประเมินคุณภาพ (Evaluation Report)

สร้างเมื่อ 2026-10-14 12:14 ด้วย `scripts/evaluate.py`

- Speech-to-Text: **gemini**
- Summarizer: **gemini**
- ชุดทดสอบ: 4 ไฟล์เสียงสังเคราะห์ภาษาไทย/ไทยปนอังกฤษใน `samples/` (macOS TTS เสียง Kanya)

## สรุปภาพรวม

| ตัวชี้วัด | ค่าเฉลี่ย |
|---|---|
| CER (Character Error Rate) | 5% |
| WER (whitespace tokens) | 67% |
| ความถูกต้องของสถานะหัวข้อ | 81% |
| หัวข้อที่ถูกติ๊ก 'ได้ข้อสรุป' ผิด | 1 รายการ |
| Precision / Recall มติ | 100% / 100% |
| Precision / Recall action items | 100% / 100% |
| Hallucination count (มติ/งานที่ไม่ตรงกับ reference) | 0 |
| รายการที่ validator ตัด/แก้ | 0 |
| เวลาเฉลี่ยถอดเสียง + สรุป ต่อไฟล์ | 119.89 วินาที |

## รายไฟล์

### Sprint Review ทีม Backend (`backend-sprint-review`, th-TH+en-US, 50 วินาที)

- CER 5%, WER 21%
- มติ P/R 100%/100%, งาน P/R 100%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 0, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.07s, ถอดเสียง 128.91s, สรุป 67.89s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| API authentication | resolved | resolved |
| Performance testing | mentioned | mentioned |
| Deployment pipeline | mentioned | mentioned |

### ประชุมวางแผนการตลาดไตรมาสสี่ (`marketing-q4`, th-TH, 42 วินาที)

- CER 6%, WER 130%
- มติ P/R 100%/100%, งาน P/R 100%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 0, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.35s, ถอดเสียง 25.58s, สรุป 136.31s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| งบโฆษณาออนไลน์ | resolved | resolved |
| กิจกรรมลูกค้า | mentioned | mentioned |
| รายงานยอดขาย | mentioned | mentioned |

### ประชุมติดตามโครงการ AI Meeting Minutes ครั้งที่ 3 (`project-sync-03`, th-TH, 57 วินาที)

- CER 7%, WER 67%
- มติ P/R 100%/100%, งาน P/R 100%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 0, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.15s, ถอดเสียง 8.98s, สรุป 14.83s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| ออกแบบฐานข้อมูล | resolved | resolved |
| การเชื่อมต่อ SharePoint | mentioned | not_mentioned ✗ |
| งบประมาณ Azure | mentioned | mentioned |
| การทดสอบระบบ UAT | not_mentioned | not_mentioned |

### ประชุมสั้นเรื่องระบบลงเวลา (`timesheet-short`, th-TH, 20 วินาที)

- CER 3%, WER 50%
- มติ P/R 100%/100%, งาน P/R 100%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 0, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.03s, ถอดเสียง 74.82s, สรุป 22.22s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| ระบบลงเวลาใหม่ | resolved | resolved |
| การอบรมพนักงาน | mentioned | resolved ✗ |

## เกณฑ์ที่ต้องตกลงกับพี่เลี้ยง

ยังไม่มีตัวเลขเป้าหมายจากเอกสารโครงการ (plan §11) ให้ใช้ตารางนี้เป็น baseline แล้วกำหนดเกณฑ์ผ่าน เช่น CER ≤ X%, ไม่มีหัวข้อที่ติ๊ก 'ได้ข้อสรุป' ผิด, hallucination = 0 ก่อนเริ่ม UAT และควรเพิ่มไฟล์เสียงประชุมจริงที่ได้รับอนุญาตพร้อม reference ที่คนตรวจ
