# รายงานผลการประเมินคุณภาพ (Evaluation Report)

สร้างเมื่อ 2026-10-14 02:59 ด้วย `scripts/evaluate.py`

- Speech-to-Text: **mock**
- Summarizer: **mock**
- ชุดทดสอบ: 4 ไฟล์เสียงสังเคราะห์ภาษาไทย/ไทยปนอังกฤษใน `samples/` (macOS TTS เสียง Kanya)

> **หมายเหตุ:** STT แบบ mock คืนบทถอดเสียงอ้างอิงโดยตรง ค่า CER/WER จึงเป็น 0 โดยนิยาม ต้องตั้ง `STT_PROVIDER=azure` เพื่อวัดคุณภาพการถอดเสียงจริง

> **หมายเหตุ:** Summarizer แบบ mock ใช้กฎคำสำคัญ (rule-based) ผลด้านล่างคือ baseline สำหรับเปรียบเทียบกับ Azure OpenAI / Gemini

## สรุปภาพรวม

| ตัวชี้วัด | ค่าเฉลี่ย |
|---|---|
| CER (Character Error Rate) | 0% |
| WER (whitespace tokens) | 0% |
| ความถูกต้องของสถานะหัวข้อ | 79% |
| หัวข้อที่ถูกติ๊ก 'ได้ข้อสรุป' ผิด | 1 รายการ |
| Precision / Recall มติ | 100% / 100% |
| Precision / Recall action items | 92% / 100% |
| Hallucination count (มติ/งานที่ไม่ตรงกับ reference) | 1 |
| รายการที่ validator ตัด/แก้ | 0 |
| เวลาเฉลี่ยถอดเสียง + สรุป ต่อไฟล์ | 0.00 วินาที |

## รายไฟล์

### Sprint Review ทีม Backend (`backend-sprint-review`, th-TH+en-US, 50 วินาที)

- CER 0%, WER 0%
- มติ P/R 100%/100%, งาน P/R 100%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 0, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.04s, ถอดเสียง 0.00s, สรุป 0.00s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| API authentication | resolved | resolved |
| Performance testing | mentioned | mentioned |
| Deployment pipeline | mentioned | mentioned |

### ประชุมวางแผนการตลาดไตรมาสสี่ (`marketing-q4`, th-TH, 42 วินาที)

- CER 0%, WER 0%
- มติ P/R 100%/100%, งาน P/R 100%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 0, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.03s, ถอดเสียง 0.00s, สรุป 0.00s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| งบโฆษณาออนไลน์ | resolved | resolved |
| กิจกรรมลูกค้า | mentioned | mentioned |
| รายงานยอดขาย | mentioned | resolved ✗ |

### ประชุมติดตามโครงการ AI Meeting Minutes ครั้งที่ 3 (`project-sync-03`, th-TH, 57 วินาที)

- CER 0%, WER 0%
- มติ P/R 100%/100%, งาน P/R 67%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 1, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.03s, ถอดเสียง 0.00s, สรุป 0.00s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| ออกแบบฐานข้อมูล | resolved | resolved |
| การเชื่อมต่อ SharePoint | mentioned | mentioned |
| งบประมาณ Azure | mentioned | mentioned |
| การทดสอบระบบ UAT | not_mentioned | not_mentioned |

รายการที่ระบบสร้างแต่ไม่มีใน reference:
- เรื่องนี้ยังไม่มีข้อสรุป ต้องติดตามกับทีมไอทีอีกครั้ง

### ประชุมสั้นเรื่องระบบลงเวลา (`timesheet-short`, th-TH, 20 วินาที)

- CER 0%, WER 0%
- มติ P/R 100%/100%, งาน P/R 100%/100%, ผู้รับผิดชอบถูก 100%
- hallucination 0, validator แก้ไข 0 รายการ
- เวลา: แปลงไฟล์ 0.03s, ถอดเสียง 0.00s, สรุป 0.00s

| หัวข้อ | คาดหวัง | ระบบให้ |
|---|---|---|
| ระบบลงเวลาใหม่ | resolved | resolved |
| การอบรมพนักงาน | mentioned | not_mentioned ✗ |

## เกณฑ์ที่ต้องตกลงกับพี่เลี้ยง

ยังไม่มีตัวเลขเป้าหมายจากเอกสารโครงการ (plan §11) ให้ใช้ตารางนี้เป็น baseline แล้วกำหนดเกณฑ์ผ่าน เช่น CER ≤ X%, ไม่มีหัวข้อที่ติ๊ก 'ได้ข้อสรุป' ผิด, hallucination = 0 ก่อนเริ่ม UAT และควรเพิ่มไฟล์เสียงประชุมจริงที่ได้รับอนุญาตพร้อม reference ที่คนตรวจ
