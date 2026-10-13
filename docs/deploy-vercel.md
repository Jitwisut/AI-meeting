# Deploy บน Vercel

## ภาพรวม: Vercel รับเฉพาะ Frontend

| ส่วน | Deploy ที่ไหน | เหตุผล |
|---|---|---|
| `frontend/` (Next.js) | **Vercel** | รองรับ Next.js โดยตรง |
| `backend/` (FastAPI) + `worker` (RQ) + PostgreSQL + Redis | **ที่อื่น** เช่น Azure Container Apps (ตาม plan), Render หรือ Railway | Vercel Functions เป็น serverless: ไม่มี background worker ที่รันค้าง, จำกัดเวลาทำงานต่อคำขอ, ไม่มี `ffmpeg`, และไม่มีดิสก์ถาวรสำหรับไฟล์เสียงชั่วคราว ซึ่ง pipeline ถอดเสียงต้องใช้ทั้งหมด |

> ⚠️ plan §3 ระบุว่า **ห้ามใช้ข้อมูลจริงของบริษัทบน personal hosting** บัญชี Vercel/Render ส่วนตัว
> ใช้ได้เฉพาะ demo ด้วยไฟล์เสียงสังเคราะห์ใน `samples/` ระบบจริงต้อง deploy บน infrastructure ที่ IT อนุมัติ

## ขั้นที่ 1: Deploy backend ก่อน (ต้องได้ URL แบบ HTTPS)

Frontend บน Vercel เป็น HTTPS จึงเรียก backend ที่เป็น HTTP ไม่ได้ (เบราว์เซอร์บล็อก mixed content)

ตัวอย่างบน Render (สำหรับ demo):
1. New → **PostgreSQL** และ **Key Value (Redis)** → จด connection URL
2. New → **Web Service** → เลือก repo → Root Directory `backend` → Runtime **Docker**
   (Dockerfile ติดตั้ง `ffmpeg` ให้แล้ว)
3. New → **Background Worker** → repo เดียวกัน, Root Directory `backend`, Docker,
   Docker Command: `rq worker meetings --url $REDIS_URL --with-scheduler`
4. ตั้ง Environment Variables ให้ทั้ง Web Service และ Worker เหมือนกัน:

```env
DATABASE_URL=postgresql+psycopg://...        # จาก Render Postgres (เปลี่ยน prefix เป็น postgresql+psycopg://)
REDIS_URL=redis://...
QUEUE_MODE=rq
STORAGE_DIR=/data
CORS_ORIGINS=https://<ชื่อโปรเจกต์>.vercel.app
AUTH_MODE=mock          # demo เท่านั้น — ใครมี URL ก็ใช้ได้
GRAPH_MODE=mock
STT_PROVIDER=mock
SUMMARIZER=mock
```

> ข้อจำกัดสำคัญ: Web Service กับ Worker ต้องเห็นไฟล์เสียงชุดเดียวกัน (`STORAGE_DIR`) บน Docker Compose
> ใช้ volume ร่วมกัน แต่บน Render/Container Apps สอง service **ไม่แชร์ดิสก์กัน** ต้องต่อ storage ร่วม
> (เช่น Azure Files mount ที่ `/data`) หรือรันทั้งสองใน container เดียว ไม่เช่นนั้น worker จะหาไฟล์เสียงไม่เจอ
>
> `samples/` ต้องอยู่ใน image ด้วยหากใช้ mock (`SAMPLES_DIR`) — ใน Docker Compose ใช้ volume mount
> ถ้า deploy แยก ให้เพิ่ม `COPY` samples ลง image หรือ mount ไว้

ทดสอบ: เปิด `https://<backend>/api/health` ต้องได้ `{"status":"ok", ...}`

## ขั้นที่ 2: Import โปรเจกต์ใน Vercel

1. ไปที่ https://vercel.com/new → **Import Git Repository** → เลือก `Jitwisut/AI-meeting`
   (ครั้งแรกต้องกด Install/Configure GitHub App ให้ Vercel เข้าถึง repo นี้)
2. ตั้งค่าหน้า **Configure Project**:

| ช่อง | เลือก / ใส่ |
|---|---|
| Project Name | เช่น `ai-meeting-minutes` |
| Framework Preset | **Next.js** (ตรวจพบอัตโนมัติหลังเลือก Root Directory) |
| **Root Directory** | กด Edit → เลือก **`frontend`** ← สำคัญที่สุด เพราะ repo เป็น monorepo |
| Build Command | ปล่อยค่าเริ่มต้น (`next build`) |
| Output Directory | ปล่อยค่าเริ่มต้น |
| Install Command | ปล่อยค่าเริ่มต้น (`npm install`, ใช้ `package-lock.json`) |
| Node.js Version | Settings → General → **22.x** (หลัง deploy ครั้งแรก) |

3. เปิด **Environment Variables** แล้วเพิ่ม (เลือก Environment: Production + Preview):

| Key | Value (demo / mock) | Value (ใช้งานจริง) |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `https://<backend>` (ไม่มี `/` ท้าย) | URL backend ขององค์กร |
| `NEXT_PUBLIC_AUTH_MODE` | `mock` | `entra` |
| `NEXT_PUBLIC_ENTRA_TENANT_ID` | – | Tenant ID |
| `NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID` | – | Client ID ของ SPA |
| `NEXT_PUBLIC_ENTRA_API_SCOPE` | – | `api://<api-client-id>/access_as_user` |

   ตัวแปร `NEXT_PUBLIC_*` ถูกฝังตอน build ถ้าแก้ภายหลังต้อง **Redeploy** (Deployments → ⋯ → Redeploy)
   ห้ามใส่ secret ใด ๆ ใน `NEXT_PUBLIC_*` เพราะผู้ใช้ทุกคนเห็นได้

4. กด **Deploy** → ได้ URL เช่น `https://ai-meeting-minutes.vercel.app`

## ขั้นที่ 3: ผูกสองฝั่งเข้าด้วยกัน

1. กลับไปที่ backend → ตั้ง `CORS_ORIGINS` เป็น URL จริงของ Vercel (หลายค่าคั่นด้วย `,`
   เช่นใส่ทั้ง production domain และ custom domain) → restart backend
   Preview deployment ของ Vercel ได้ URL ใหม่ทุกครั้ง ถ้าต้องการให้ preview ใช้งานได้ ต้องเพิ่ม URL นั้นด้วย
2. (โหมด `entra`) ใน App Registration → Authentication → Single-page application → เพิ่ม Redirect URI
   `https://<ชื่อโปรเจกต์>.vercel.app`
3. เปิดเว็บ → หน้า **ตั้งค่า** ต้องไม่มี error และหน้า SharePoint ต้องโหลดรายการไฟล์ได้

## ตรวจสอบหลัง deploy

- [ ] `https://<backend>/api/health` ตอบ `ok`
- [ ] หน้าแรกบน Vercel แสดง dashboard และภาพ 3D (เบราว์เซอร์ต้องรองรับ WebGL; ถ้าไม่รองรับจะแสดงพื้นหลังแทน)
- [ ] เปิด DevTools → Console ต้องไม่มี CORS error (ถ้ามี = `CORS_ORIGINS` ไม่ตรงกับ URL)
- [ ] ลอง flow: เลือกไฟล์ SharePoint (mock) → ประมวลผล → อนุมัติ → ส่ง Teams (mock)

## ปัญหาที่พบบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| Build ล้มเหลว "Couldn't find any `pages` or `app` directory" | ยังไม่ได้ตั้ง Root Directory เป็น `frontend` |
| หน้าเว็บขึ้น "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้" | `NEXT_PUBLIC_API_BASE` ผิด, backend หลับ (free tier), หรือ backend เป็น HTTP |
| CORS error ใน Console | เพิ่ม URL ของ Vercel ใน `CORS_ORIGINS` ของ backend แล้ว restart |
| แก้ env แล้วไม่มีผล | ต้อง Redeploy เพราะ `NEXT_PUBLIC_*` ฝังตอน build |
| งานค้าง "กำลังประมวลผล" | worker ไม่ได้รัน หรือ worker ไม่เห็นไฟล์เสียง (storage ไม่แชร์) — ดูขั้นที่ 1 |
| Login วนกลับหน้าเดิม (entra) | Redirect URI ใน App Registration ไม่ตรงกับ URL ของ Vercel |
