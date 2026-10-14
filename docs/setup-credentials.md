# การตั้งค่า Credentials และสิ่งที่ต้องขอจากทีม IT

ระบบรันได้ครบทุกขั้นในโหมด `mock` โดยไม่ต้องมี credentials ใด ๆ เมื่อได้รับสิทธิ์จริงแล้ว ให้กรอกค่าใน `.env`
(คัดลอกจาก `.env.example`) **ด้วยตัวเอง** แล้วสลับ provider ทีละตัว ห้าม commit `.env` และใน production
ให้เก็บ secret ใน Azure Key Vault

> ⚠️ หาก tenant เป็นของ KBTG การสร้าง App Registration, การให้ admin consent และการสร้าง Azure resource
> ต้องผ่านทีม IT ตาม plan §4.1 อย่าสร้างเองใน tenant องค์กรโดยไม่ได้รับอนุมัติ

## 1. Checklist ขอจากทีม IT (plan §4.1)

- [ ] Test tenant / SharePoint site / Document Library และโฟลเดอร์ไฟล์เสียงทดสอบ
- [ ] แชทกลุ่ม Teams สำหรับทดสอบ (ผู้พัฒนาเป็นสมาชิก)
- [ ] App Registration (ดูข้อ 2) + admin consent สำหรับ delegated permissions
- [ ] Azure AI Speech resource (region ที่รองรับ `th-TH`) + quota
- [ ] Azure OpenAI resource + deployment (เช่น gpt-4o / gpt-4.1) ที่ได้รับอนุมัติ
- [ ] นโยบาย data classification, retention ของเสียง/transcript, consent การบันทึกเสียง และการเผยแพร่ในแชท
- [ ] แนวทาง Key Vault / secret rotation และ logging
- [ ] ตัดสินใจ: ใช้ delegated `Files.Read.All` หรือ application `Sites.Selected` (ดูข้อ 5)

## 2. Microsoft Entra ID App Registration

แนะนำ 1 App Registration ที่มีทั้ง SPA platform และ Web API (หรือแยก 2 app ก็ได้)

| ตั้งค่าใน Entra admin center | ค่า |
|---|---|
| Supported account types | Single tenant |
| Platform: Single-page application | Redirect URI `http://localhost:3000` (และ URL ของ production) |
| Expose an API | Application ID URI `api://<client-id>`, เพิ่ม scope `access_as_user` (Admins and users) |
| Manifest | `"requestedAccessTokenVersion": 2` (ระบบตรวจ issuer แบบ v2.0) |
| Certificates & secrets | สร้าง client secret (หรือ certificate) สำหรับ On-Behalf-Of |
| App roles (ไม่บังคับ) | `MoM.Approver` หากต้องการจำกัดผู้อนุมัติ แล้วตั้ง `ENTRA_APPROVER_ROLE=MoM.Approver` |

**API permissions (Microsoft Graph, Delegated)** — ขอ admin consent:

| Permission | ใช้ทำอะไร |
|---|---|
| `Files.Read.All` | เลือก/ดาวน์โหลดไฟล์เสียงจาก SharePoint |
| `Files.ReadWrite.All` | บันทึกรายงาน DOCX กลับ SharePoint |
| `Chat.ReadBasic` | แสดงรายชื่อแชทที่ผู้ใช้เป็นสมาชิก (`GET /me/chats`) |
| `ChatMember.Read` | แสดงรายชื่อผู้รับก่อนส่ง |
| `ChatMessage.Send` | ส่งข้อความเข้าแชทกลุ่มในนามผู้ใช้ |
| `Chat.Read` | ตรวจว่าข้อความเคยส่งสำเร็จแล้วหรือไม่ก่อน retry (กันส่งซ้ำ) |

> ตรวจสอบชื่อ scope และ endpoint กับเอกสาร Microsoft Graph ปัจจุบันอีกครั้งก่อนใช้งานจริง (plan §4.2)
> หาก IT ไม่อนุญาต `Chat.Read` สามารถตัดออกจาก `GRAPH_SCOPES_TEAMS_SEND` ได้ แต่ระบบจะไม่สามารถยืนยัน
> ผลส่งที่ timeout และจะไม่ส่งซ้ำอัตโนมัติ (ผู้ใช้ต้องตรวจในแชทเอง)

## 3. ค่าใน `.env`

| ตัวแปร | หาได้จาก |
|---|---|
| `ENTRA_TENANT_ID`, `NEXT_PUBLIC_ENTRA_TENANT_ID` | Entra admin center → Overview → Directory (tenant) ID |
| `ENTRA_API_CLIENT_ID`, `NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID` | App registration → Overview → Application (client) ID |
| `NEXT_PUBLIC_ENTRA_API_SCOPE` | `api://<client-id>/access_as_user` |
| `ENTRA_API_CLIENT_SECRET` | App registration → Certificates & secrets (เก็บใน Key Vault) |
| `SHAREPOINT_ALLOWED_SITE_IDS` | Graph Explorer: `GET /v1.0/sites/{hostname}:/sites/{site-path}` → `id` (รูปแบบ `host,guid,guid`) |
| `SHAREPOINT_REPORT_DRIVE_ID` | `GET /v1.0/sites/{site-id}/drives` → `id` ของไลบรารีที่ใช้เก็บรายงาน |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | Azure portal → Speech resource → Keys and Endpoint |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` | Azure portal → Azure OpenAI resource → Keys and Endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | Azure AI Foundry → Deployments → ชื่อ deployment |
| `GEMINI_API_KEY` | Google AI Studio (ใช้กับข้อมูลสังเคราะห์เท่านั้น ดูข้อ 4) |

จากนั้นสลับ provider เช่น

```env
AUTH_MODE=entra
NEXT_PUBLIC_AUTH_MODE=entra
GRAPH_MODE=real
STT_PROVIDER=azure
SUMMARIZER=azure_openai
```

แล้ว `docker compose up -d --build` (ค่า `NEXT_PUBLIC_*` ถูกฝังตอน build frontend จึงต้อง build ใหม่)

## 4. Gemini (ทางเลือกฟรีสำหรับ demo)

| | Azure AI Speech | Gemini free tier |
|---|---|---|
| ฟรี | 5 ชม./เดือน เฉพาะ real-time (fast transcription/batch ที่ระบบใช้ **ไม่ฟรี**) | ฟรีภายในโควตาคำขอ ไม่ต้องใช้บัตร |
| เวลาในบทถอดเสียง | แม่นระดับคำ | โดยประมาณ (ระดับวินาที) |

วิธีเปิดใช้:
1. https://aistudio.google.com/apikey → **Create API key**
2. ตั้งค่า `STT_PROVIDER=gemini`, `SUMMARIZER=gemini`, `GEMINI_API_KEY=<key>` (บน Render: ai-meeting-api → Environment)
3. ระบบส่งเสียงเป็น MP3 ช่วงละ `GEMINI_STT_CHUNK_SECONDS` (ค่าเริ่มต้น 10 นาที) ไปถอดเสียง แล้วตรวจ/ปรับ timestamp
   ให้อยู่ในช่วงที่ถูกต้องก่อนบันทึก หากเจอข้อความ "ใช้โควตา Gemini ฟรีเกินกำหนด" ให้รอแล้วกดลองใหม่

### ข้อควรระวังเรื่อง Gemini

Gemini แบบ free tier: Google อาจนำ prompt/ผลลัพธ์ไปใช้ปรับปรุงบริการ ซึ่งขัดกับ plan §9 (ข้อตกลง data processing)
**ใช้ได้เฉพาะไฟล์เสียงสังเคราะห์ใน `samples/`** ห้ามใช้กับเสียงหรือ transcript ประชุมจริงของบริษัท
หากต้องการใช้กับข้อมูลจริง ต้องเป็นบริการที่บริษัทอนุมัติ (เช่น Azure OpenAI ใน tenant องค์กร)

## 5. Least privilege สำหรับ SharePoint

MVP ใช้ delegated token ของผู้ใช้ (ผ่าน On-Behalf-Of) จึงเข้าถึงได้เฉพาะไฟล์ที่ผู้ใช้มีสิทธิ์อยู่แล้ว และระบบจำกัด
ไซต์เพิ่มเติมด้วย `SHAREPOINT_ALLOWED_SITE_IDS` หาก IT ต้องการแคบกว่านี้ ทางเลือกคือ application permission
`Sites.Selected` + site grant เฉพาะไซต์ (ต้องเพิ่ม client-credential path ใน `backend/app/services/sharepoint.py`)
**การส่งแชทยังคงต้องเป็น delegated `ChatMessage.Send` เสมอ** (plan §4.2)

## 6. ทดสอบหลังตั้งค่า

1. เปิด `http://localhost:3000` → เข้าสู่ระบบ → หน้า **ตั้งค่า** ต้องเห็น ✓ ครบทุกสิทธิ์
2. หน้า **เลือกไฟล์จาก SharePoint** ต้องเห็นไซต์/ไลบรารีที่อนุญาต
3. ประมวลผลไฟล์สั้น ๆ 1 ไฟล์ → ตรวจ transcript ภาษาไทย
4. อนุมัติ → ส่งเข้า **แชทกลุ่มทดสอบ** เท่านั้น (ขออนุญาตก่อนตาม plan §13)
5. รัน `scripts/evaluate.py` เพื่อวัด CER และคุณภาพสรุปของบริการจริง
