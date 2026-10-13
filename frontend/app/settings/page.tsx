"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Field, inputClass, PageHeader, Panel, Spinner } from "@/components/ui";
import { errorText, useApi } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import type { AppSettings, Me } from "@/lib/types";

const CAP_LABEL: Record<string, string> = {
  sharepoint_read: "อ่านไฟล์เสียงจาก SharePoint",
  sharepoint_write: "บันทึกรายงานกลับ SharePoint",
  teams_read: "ดูรายชื่อแชทกลุ่ม Teams",
  teams_send: "ส่งข้อความเข้าแชทกลุ่มในนามของคุณ",
};

const PROVIDER_LABEL: Record<string, string> = {
  auth: "การเข้าสู่ระบบ",
  graph: "Microsoft Graph (SharePoint/Teams)",
  stt: "ถอดเสียง",
  summarizer: "สรุปด้วย AI",
};

export default function SettingsPage() {
  const { json } = useApi();
  const { data: settings, error } = useResource<AppSettings>("/api/settings");
  const { data: me, setData: setMe } = useResource<Me>("/api/me");
  const [language, setLanguage] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (me && settings) setLanguage(me.preferences.default_language ?? settings.default_language);
  }, [me, settings]);

  async function save() {
    setSaving(true);
    setMsg(null);
    try {
      const r = await json<{ preferences: Me["preferences"] }>("/api/me/preferences", {
        method: "PUT",
        body: JSON.stringify({ default_language: language }),
      });
      if (me) setMe({ ...me, preferences: r.preferences });
      setMsg({ tone: "success", text: "บันทึกการตั้งค่าแล้ว" });
    } catch (e) {
      setMsg({ tone: "error", text: errorText(e) });
    } finally {
      setSaving(false);
    }
  }

  if (error) return <Alert>{error}</Alert>;
  if (!settings || !me) return <Spinner />;
  const mock = Object.values(settings.providers).includes("mock");

  return (
    <>
      <PageHeader title="ตั้งค่า" description="ค่าเริ่มต้นของคุณ สิทธิ์ที่ระบบได้รับ และนโยบายที่องค์กรกำหนด" />
      {mock && (
        <Alert tone="warn" className="mb-6">
          ระบบกำลังทำงานในโหมดทดสอบ (mock) สำหรับบางบริการ ข้อมูล SharePoint, Teams และผลถอดเสียงเป็นข้อมูลจำลอง
        </Alert>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="ค่าเริ่มต้นของฉัน">
          <Field label="ภาษาถอดเสียงเริ่มต้น">
            <select className={inputClass} value={language} onChange={(e) => setLanguage(e.target.value)}>
              {settings.languages.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </Field>
          {msg && <Alert tone={msg.tone} className="mt-4">{msg.text}</Alert>}
          <Button variant="primary" className="mt-4" busy={saving} onClick={save}>บันทึก</Button>
        </Panel>

        <Panel title="สิทธิ์ Microsoft 365 ของบัญชีนี้">
          <ul className="space-y-3 text-sm">
            {Object.entries(me.capabilities).map(([k, c]) => (
              <li key={k} className="flex items-start gap-3">
                <span className={`mt-0.5 font-semibold ${c.granted ? "text-pine" : "text-rust"}`} aria-hidden>{c.granted ? "✓" : "✕"}</span>
                <span>
                  {CAP_LABEL[k] ?? k}
                  <span className="block text-xs text-ink-faint">{c.scopes.map((s) => s.split("/").pop()).join(", ")}{c.mock ? " (จำลอง)" : ""}</span>
                  {c.reason && <span className="block text-xs text-rust">{c.reason}</span>}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="ที่เก็บใน SharePoint">
          <dl className="space-y-2 text-sm">
            <div><dt className="text-ink-faint">ไซต์ที่อนุญาต</dt><dd>{settings.sharepoint.allowed_site_ids.length ? settings.sharepoint.allowed_site_ids.join(", ") : "ไม่ได้จำกัด (ใช้สิทธิ์ของผู้ใช้)"}</dd></div>
            <div><dt className="text-ink-faint">โฟลเดอร์รายงาน</dt><dd>{settings.sharepoint.report_folder}</dd></div>
            <div><dt className="text-ink-faint">ไลบรารีสำหรับรายงาน</dt><dd>{settings.sharepoint.report_drive_configured ? "กำหนดโดยผู้ดูแลระบบ" : "บันทึกไว้คู่กับไฟล์เสียงต้นทาง"}</dd></div>
          </dl>
        </Panel>

        <Panel title="นโยบายการใช้งาน">
          <dl className="space-y-2 text-sm">
            <div><dt className="text-ink-faint">ไฟล์ที่รับ</dt><dd>อัปโหลด: {settings.policy.upload_formats.join(", ")} อัดผ่านเว็บ: {settings.policy.recording_formats.join(", ")}</dd></div>
            <div><dt className="text-ink-faint">ขนาดและความยาวสูงสุด</dt><dd className="tnum">{settings.policy.max_upload_mb} MB, {settings.policy.max_audio_minutes} นาที</dd></div>
            <div><dt className="text-ink-faint">การเก็บไฟล์เสียงชั่วคราว</dt><dd>ลบอัตโนมัติหลังประมวลผล {settings.policy.temp_audio_retention_hours} ชั่วโมง</dd></div>
            <div><dt className="text-ink-faint">การตรวจทานโดยคน</dt><dd>บังคับก่อนส่งออกและส่ง Teams ทุกครั้ง</dd></div>
            <div><dt className="text-ink-faint">แยกเสียงผู้พูด</dt><dd>ยังไม่รองรับในระยะแรก</dd></div>
            <div><dt className="text-ink-faint">บริการที่ใช้</dt><dd>{Object.entries(settings.providers).map(([k, v]) => `${PROVIDER_LABEL[k] ?? k}: ${v}`).join(", ")}</dd></div>
          </dl>
        </Panel>
      </div>
    </>
  );
}
