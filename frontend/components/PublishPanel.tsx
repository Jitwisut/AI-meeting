"use client";

import { useEffect, useState } from "react";
import { ApiError, errorText, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { GroupChat, Meeting, Publication, ReportMeta } from "@/lib/types";
import { Alert, Button, inputClass } from "./ui";

interface Preview {
  chat: GroupChat;
  members: { name: string | null; email: string | null }[];
  html: string;
  is_approved: boolean;
  link_notice: string;
}

const pubTone: Record<Publication["status"], string> = {
  sent: "text-pine-dark",
  sending: "text-sky",
  failed: "text-rust",
  unknown: "text-amber",
};
const pubLabel: Record<Publication["status"], string> = {
  sent: "ส่งแล้ว",
  sending: "กำลังส่ง",
  failed: "ส่งไม่สำเร็จ",
  unknown: "ยังไม่ทราบผล",
};

export function PublishPanel({
  meeting,
  report,
  dirty,
  onChanged,
}: {
  meeting: Meeting;
  report: ReportMeta;
  dirty: boolean;
  onChanged: () => void;
}) {
  const { json, blob } = useApi();
  const { data: chatsData, error: chatsError } = useResource<{ chats: GroupChat[]; suggested_chat_id: string | null }>(
    `/api/teams/group-chats?meeting_id=${meeting.id}`,
  );
  const [chatId, setChatId] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState<"export" | "publish" | "docx" | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error" | "warn"; text: string } | null>(null);

  useEffect(() => {
    if (!chatId && chatsData?.suggested_chat_id) setChatId(chatsData.suggested_chat_id);
  }, [chatsData, chatId]);

  useEffect(() => {
    setPreview(null);
    setConfirm(false);
    if (!chatId) return;
    json<Preview>(`/api/meetings/${meeting.id}/publish/preview?chat_id=${encodeURIComponent(chatId)}`)
      .then(setPreview)
      .catch((e) => setMsg({ tone: "error", text: errorText(e) }));
  }, [chatId, json, meeting.id, report.version]);

  const approved = report.is_approved && !dirty;

  async function exportDocx() {
    setBusy("export");
    setMsg(null);
    try {
      await json(`/api/meetings/${meeting.id}/export`, { method: "POST" });
      setMsg({ tone: "success", text: "บันทึกไฟล์ Word ลง SharePoint แล้ว" });
      onChanged();
    } catch (e) {
      setMsg({ tone: "error", text: errorText(e) });
    } finally {
      setBusy(null);
    }
  }

  async function downloadDocx() {
    setBusy("docx");
    try {
      const b = await blob(`/api/meetings/${meeting.id}/export/docx`);
      const url = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = url;
      a.download = `MoM_${meeting.title}_v${report.version}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMsg({ tone: "error", text: errorText(e) });
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    setBusy("publish");
    setMsg(null);
    try {
      const r = await json<{ publication: Publication; duplicate: boolean }>(`/api/meetings/${meeting.id}/publish`, {
        method: "POST",
        body: JSON.stringify({ chat_id: chatId, confirm_recipients: confirm }),
      });
      setMsg({
        tone: "success",
        text: r.duplicate
          ? `ฉบับนี้ถูกส่งเข้า “${r.publication.chat_topic}” แล้ว ระบบไม่ได้ส่งซ้ำ`
          : `ส่งเข้า “${r.publication.chat_topic}” แล้ว`,
      });
      onChanged();
    } catch (e) {
      const unknown = e instanceof ApiError && e.code === "send_timeout";
      setMsg({ tone: unknown ? "warn" : "error", text: errorText(e) + (unknown ? " กดส่งอีกครั้งได้อย่างปลอดภัย ระบบจะตรวจสอบก่อน" : "") });
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  const pubs = meeting.publications ?? [];

  return (
    <div className="space-y-8">
      {!approved && (
        <Alert tone="warn">
          {dirty ? "มีการแก้ไขที่ยังไม่บันทึก บันทึกและอนุมัติก่อนส่งออก" : "ต้องอนุมัติรายงานฉบับล่าสุดก่อนส่งออกหรือส่งเข้า Teams"}
        </Alert>
      )}

      <section>
        <h3 className="mb-1 font-semibold">ไฟล์รายงาน</h3>
        <p className="mb-3 text-sm text-ink-soft">
          {report.exported_version
            ? `ส่งออกล่าสุด: ฉบับที่ ${report.exported_version}${report.exported_version !== report.version ? " (ไม่ใช่ฉบับล่าสุด)" : ""}`
            : "ยังไม่ได้ส่งออก"}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={!approved} busy={busy === "export"} onClick={exportDocx}>
            บันทึก Word ลง SharePoint
          </Button>
          <Button disabled={!report.has_docx} busy={busy === "docx"} onClick={downloadDocx}>
            ดาวน์โหลด Word
          </Button>
          <Button variant="ghost" onClick={() => window.print()}>
            พิมพ์ / บันทึกเป็น PDF
          </Button>
        </div>
        {report.sharepoint_web_url && (
          <a href={report.sharepoint_web_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-pine hover:underline">
            เปิดรายงานใน SharePoint
          </a>
        )}
      </section>

      <section>
        <h3 className="mb-1 font-semibold">ส่งเข้าแชทกลุ่ม Teams</h3>
        <p className="mb-3 text-sm text-ink-soft">ข้อความจะถูกส่งในนามของคุณ เฉพาะแชทกลุ่มที่คุณเป็นสมาชิก</p>
        {chatsError && <Alert className="mb-3">{chatsError}</Alert>}
        <select className={inputClass} value={chatId} onChange={(e) => setChatId(e.target.value)} aria-label="แชทกลุ่มปลายทาง">
          <option value="">เลือกแชทกลุ่ม</option>
          {chatsData?.chats.map((c) => (
            <option key={c.id} value={c.id}>
              {c.topic} ({c.member_count} คน){c.id === chatsData.suggested_chat_id ? " ใช้ครั้งก่อน" : ""}
            </option>
          ))}
        </select>

        {preview && (
          <div className="mt-4 space-y-3">
            <div>
              <p className="mb-1 text-sm font-medium">ตัวอย่างข้อความ</p>
              <iframe
                title="ตัวอย่างข้อความ Teams"
                sandbox="allow-same-origin"
                srcDoc={`<style>body{font-family:system-ui,sans-serif;font-size:14px;line-height:1.55;color:#1a2530;margin:12px}h2{font-size:16px}</style>${preview.html}`}
                className="h-72 w-full rounded-md border border-line bg-white"
              />
            </div>
            <div className="text-sm">
              <p className="font-medium">ผู้รับ {preview.members.length} คน</p>
              <p className="text-ink-soft">{preview.members.map((m) => m.name).filter(Boolean).join(", ")}</p>
              <p className="mt-1 text-xs text-amber">{preview.link_notice}</p>
            </div>
            <label className="flex items-start gap-3 rounded-[10px] bg-hover p-3 text-sm">
              <input type="checkbox" className="mt-1 h-4 w-4" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
              ฉันตรวจสอบรายชื่อผู้รับแล้ว และผู้รับมีสิทธิ์เปิดรายงานใน SharePoint
            </label>
            <Button variant="primary" disabled={!approved || !confirm} busy={busy === "publish"} onClick={publish}>
              ส่งเข้า Teams
            </Button>
          </div>
        )}
      </section>

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <section>
        <h3 className="mb-2 font-semibold">ประวัติการส่ง</h3>
        {pubs.length === 0 ? (
          <p className="text-sm text-ink-faint">ยังไม่เคยส่ง</p>
        ) : (
          <ul className="divide-y divide-line-soft text-sm">
            {pubs.map((p) => (
              <li key={p.id} className="py-2.5">
                <span className="flex flex-wrap justify-between gap-2">
                  <span className="font-medium">{p.chat_topic}</span>
                  <span className={pubTone[p.status]}>{pubLabel[p.status]}</span>
                </span>
                <span className="tnum block text-xs text-ink-faint">
                  ฉบับที่ {p.report_version}, อนุมัติโดย {p.approved_by}, {p.sent_at ? `ส่งเมื่อ ${fmtDate(p.sent_at)}` : `พยายาม ${p.attempts} ครั้ง`}, รหัส {p.reference_code}
                </span>
                {p.error_message && p.status !== "sent" && <span className="block text-xs text-rust">{p.error_message}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
