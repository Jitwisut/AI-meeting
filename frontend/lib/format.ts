import type { MeetingStatus, TopicStatus } from "./types";

export function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "–";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

export function fmtBytes(n: number | null | undefined): string {
  if (n == null) return "";
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const meetingStatusLabel: Record<MeetingStatus, string> = {
  pending: "รอเริ่มประมวลผล",
  processing: "กำลังประมวลผล",
  awaiting_review: "รอตรวจทาน",
  reviewed: "อนุมัติแล้ว",
  published: "ส่งเข้า Teams แล้ว",
  failed: "ล้มเหลว",
};

export const topicStatusLabel: Record<TopicStatus, string> = {
  resolved: "ได้ข้อสรุป",
  mentioned: "พูดถึงแล้ว ยังไม่มีข้อสรุป",
  unclear: "ไม่ชัดเจน",
  not_mentioned: "ไม่ได้พูดถึง",
};

export const stageLabel: Record<string, string> = {
  download: "รับไฟล์เสียง",
  convert: "ตรวจและแปลงไฟล์",
  transcribe: "ถอดเสียงเป็นข้อความ",
  summarize: "สรุปด้วย AI",
};

export const sourceLabel: Record<string, string> = {
  sharepoint: "SharePoint",
  upload: "อัปโหลด",
  recording: "อัดผ่านเว็บ",
};
