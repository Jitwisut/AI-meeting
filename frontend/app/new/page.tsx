"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { agendaList, emptySetup, MeetingSetup, type SetupValue } from "@/components/MeetingSetup";
import { Recorder } from "@/components/Recorder";
import { Alert, Button, PageHeader, Panel, Segmented, Switch } from "@/components/ui";
import { errorText, useApi } from "@/lib/api";
import { fmtBytes } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { AppSettings, Me, Meeting } from "@/lib/types";

type Mode = "upload" | "recording";

function NewMeeting() {
  const router = useRouter();
  const params = useSearchParams();
  const { json } = useApi();
  const { data: settings } = useResource<AppSettings>("/api/settings");
  const { data: me } = useResource<Me>("/api/me");
  const [mode, setMode] = useState<Mode>(params.get("mode") === "recording" ? "recording" : "upload");
  const [file, setFile] = useState<File | null>(null);
  const [setup, setSetup] = useState<SetupValue>(emptySetup);
  const [recordingConsent, setRecordingConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (me?.preferences.default_language) setSetup((s) => ({ ...s, language: me.preferences.default_language! }));
  }, [me]);

  const maxBytes = (settings?.policy.max_upload_mb ?? 300) * 1024 * 1024;

  function pickFile(f: File | null) {
    setError(null);
    if (f && f.size > maxBytes) {
      setError(`ไฟล์ใหญ่เกิน ${settings?.policy.max_upload_mb} MB`);
      setFile(null);
      return;
    }
    setFile(f);
  }

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("title", setup.title);
    form.append("language", setup.language);
    form.append("agenda", JSON.stringify(agendaList(setup)));
    form.append("source", mode);
    form.append("consent_ai_processing", String(setup.consent));
    form.append("consent_recording", String(recordingConsent));
    try {
      const m = await json<Meeting>("/api/meetings/upload", { method: "POST", body: form });
      await json(`/api/meetings/${m.id}/process`, { method: "POST" });
      router.push(`/meetings/${m.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="อัปโหลดหรืออัดเสียงการประชุม" description="ใช้เมื่อไฟล์เสียงยังไม่ได้อยู่ใน SharePoint" />
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Panel>
          <Segmented<Mode>
            label="วิธีนำเข้าเสียง"
            className="mb-5"
            value={mode}
            onChange={(m) => {
              setMode(m);
              setFile(null);
            }}
            options={[
              { value: "upload", label: "อัปโหลดไฟล์" },
              { value: "recording", label: "อัดเสียงผ่านเบราว์เซอร์" },
            ]}
          />

          {mode === "upload" ? (
            <label
              className="flex cursor-pointer flex-col items-center justify-center rounded-[16px] border-[1.5px] border-dashed border-line bg-hover px-6 py-16 text-center transition-colors duration-200 hover:border-pine hover:bg-pine-wash"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                pickFile(e.dataTransfer.files[0] ?? null);
              }}
            >
              <input type="file" accept=".mp3,.wav,audio/mpeg,audio/wav" className="sr-only" onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
              {file ? (
                <>
                  <span className="font-medium">{file.name}</span>
                  <span className="mt-1 text-sm text-ink-faint">{fmtBytes(file.size)} คลิกเพื่อเปลี่ยนไฟล์</span>
                </>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" className="mb-3 h-9 w-9 text-pine" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden>
                    <path d="M12 16V4m0 0-4 4m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />
                  </svg>
                  <span className="font-medium">ลากไฟล์มาวาง หรือคลิกเพื่อเลือก</span>
                  <span className="mt-1 text-sm text-ink-faint">
                    MP3 หรือ WAV ไม่เกิน {settings?.policy.max_upload_mb ?? 300} MB และ {settings?.policy.max_audio_minutes ?? 180} นาที
                  </span>
                </>
              )}
            </label>
          ) : (
            <div className="space-y-4">
              <Switch
                tone="warn"
                checked={recordingConsent}
                onChange={setRecordingConsent}
                label="ฉันแจ้งผู้ร่วมประชุมทุกคนแล้วว่ากำลังจะบันทึกเสียง และไม่มีผู้ใดคัดค้าน"
              />
              <Recorder disabled={!recordingConsent} onRecorded={setFile} />
              <p className="text-xs text-ink-faint">
                เสียงจะถูกส่งขึ้นเซิร์ฟเวอร์หลังกดเริ่มประมวลผลเท่านั้น ไม่มีการแยกเสียงผู้พูดในระยะนี้
              </p>
            </div>
          )}
        </Panel>

        <Panel title="รายละเอียดการประชุม">
          <MeetingSetup value={setup} onChange={setSetup} />
          {error && <Alert className="mt-4">{error}</Alert>}
          <Button
            variant="primary"
            className="mt-5 w-full"
            disabled={!file || !setup.consent || (mode === "recording" && !recordingConsent)}
            busy={busy}
            onClick={submit}
          >
            อัปโหลดและเริ่มประมวลผล
          </Button>
        </Panel>
      </div>
    </>
  );
}

export default function NewMeetingPage() {
  return (
    <Suspense>
      <NewMeeting />
    </Suspense>
  );
}
