"use client";

import { useResource } from "@/lib/hooks";
import type { AppSettings, Me } from "@/lib/types";
import { Field, inputClass, Switch } from "./ui";

export interface SetupValue {
  title: string;
  language: string;
  agendaText: string;
  consent: boolean;
}

export const emptySetup: SetupValue = { title: "", language: "th-TH", agendaText: "", consent: false };

export function agendaList(v: SetupValue): string[] {
  return v.agendaText
    .split("\n")
    .map((s) => s.replace(/^[-•*\d.)\s]+/, "").trim())
    .filter(Boolean);
}

/** Common meeting details + consent, shared by SharePoint and upload/record flows. */
export function MeetingSetup({ value, onChange }: { value: SetupValue; onChange: (v: SetupValue) => void }) {
  const { data: settings } = useResource<AppSettings>("/api/settings");
  const set = (patch: Partial<SetupValue>) => onChange({ ...value, ...patch });
  return (
    <div className="space-y-4">
      <Field label="ชื่อการประชุม" hint="เว้นว่างไว้เพื่อใช้ชื่อไฟล์">
        <input className={inputClass} value={value.title} maxLength={300} onChange={(e) => set({ title: e.target.value })} />
      </Field>
      <Field label="ภาษาที่พูดในการประชุม">
        <select className={inputClass} value={value.language} onChange={(e) => set({ language: e.target.value })}>
          {(settings?.languages ?? [{ code: "th-TH", label: "ไทย" }]).map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </Field>
      <Field
        label="หัวข้อที่ต้องติดตาม (วาระ)"
        hint="บรรทัดละหนึ่งหัวข้อ ระบบจะบอกว่าแต่ละหัวข้อได้ข้อสรุป ถูกพูดถึง หรือไม่ได้พูดถึง"
      >
        <textarea
          className={`${inputClass} min-h-28`}
          value={value.agendaText}
          placeholder={"ออกแบบฐานข้อมูล\nการเชื่อมต่อ SharePoint"}
          onChange={(e) => set({ agendaText: e.target.value })}
        />
      </Field>
      <Switch
        checked={value.consent}
        onChange={(v) => set({ consent: v })}
        label="ผู้ร่วมประชุมรับทราบการบันทึกเสียง และยินยอมให้ประมวลผลด้วย AI ตามนโยบายบริษัท"
        description={`ไฟล์เสียงชั่วคราวจะถูกลบภายใน ${settings?.policy.temp_audio_retention_hours ?? 24} ชั่วโมงหลังประมวลผล`}
      />
    </div>
  );
}

export function useDefaultLanguage(): string | undefined {
  const { data } = useResource<Me>("/api/me");
  return data?.preferences.default_language;
}
