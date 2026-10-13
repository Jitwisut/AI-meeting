"use client";

import { fmtMs, topicStatusLabel } from "@/lib/format";
import type { ActionItem, Decision, Evidence, Summary, Topic, TopicStatus } from "@/lib/types";
import { inputClass, TopicBadge } from "./ui";

export type ItemKind = "topic" | "decision" | "action" | "question";
export interface LinkTarget {
  kind: ItemKind;
  id: string;
}

interface Common {
  draft: Summary;
  onChange: (s: Summary) => void;
  linking: LinkTarget | null;
  setLinking: (t: LinkTarget | null) => void;
  onFocusEvidence: (e: Evidence) => void;
}

const newId = () => Math.random().toString(16).slice(2, 12);

export function EvidenceChips({
  evidence,
  target,
  linking,
  setLinking,
  onFocusEvidence,
}: {
  evidence: Evidence[];
  target: LinkTarget;
  linking: LinkTarget | null;
  setLinking: (t: LinkTarget | null) => void;
  onFocusEvidence: (e: Evidence) => void;
}) {
  const active = linking?.kind === target.kind && linking.id === target.id;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      {evidence.length === 0 && <span className="text-xs text-amber">ไม่มีหลักฐานจากบทถอดเสียง</span>}
      {evidence.map((e) => (
        <button
          key={e.segment_id}
          type="button"
          onClick={() => onFocusEvidence(e)}
          title={e.text}
          className="tnum rounded-full bg-pine-wash px-2 py-0.5 text-xs text-pine-dark transition-transform hover:scale-105"
        >
          {fmtMs(e.start_ms)}
        </button>
      ))}
      <button
        type="button"
        onClick={() => setLinking(active ? null : target)}
        className={`rounded px-1.5 py-0.5 text-xs ${active ? "bg-sky text-surface" : "text-sky hover:underline"}`}
      >
        {active ? "เสร็จสิ้นการเลือกหลักฐาน" : "แก้หลักฐาน"}
      </button>
    </div>
  );
}

function RemoveButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} className="shrink-0 rounded px-2 py-1 text-xs text-ink-faint hover:bg-rust-wash hover:text-rust" aria-label={label}>
      ลบ
    </button>
  );
}

function AutoText({ value, onChange, placeholder, label }: { value: string; onChange: (v: string) => void; placeholder?: string; label: string }) {
  return (
    <textarea
      aria-label={label}
      rows={Math.max(1, Math.ceil(value.length / 60))}
      className={`${inputClass} resize-y`}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function SummarySection(p: Common) {
  const { draft, onChange } = p;
  const set = <K extends keyof Summary>(k: K, v: Summary[K]) => onChange({ ...draft, [k]: v });

  const updDecision = (list: "decisions" | "open_questions", id: string, patch: Partial<Decision>) =>
    set(list, draft[list].map((d) => (d.id === id ? { ...d, ...patch } : d)));
  const updAction = (id: string, patch: Partial<ActionItem>) =>
    set("action_items", draft.action_items.map((a) => (a.id === id ? { ...a, ...patch } : a)));

  return (
    <div className="space-y-8">
      <section>
        <label className="mb-1 block text-sm font-medium" htmlFor="mtitle">ชื่อการประชุม</label>
        <input id="mtitle" className={inputClass} value={draft.meeting_title} onChange={(e) => set("meeting_title", e.target.value)} />
        <label className="mb-1 mt-4 block text-sm font-medium" htmlFor="msummary">สรุปภาพรวม</label>
        <textarea id="msummary" className={`${inputClass} min-h-28`} value={draft.summary} onChange={(e) => set("summary", e.target.value)} />
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold">มติที่ประชุม</h3>
          <button className="text-sm text-pine hover:underline" onClick={() => set("decisions", [...draft.decisions, { id: newId(), text: "", evidence: [] }])}>
            เพิ่มมติ
          </button>
        </div>
        {draft.decisions.length === 0 && <p className="text-sm text-ink-faint">AI ไม่พบมติที่มีหลักฐานชัดเจน</p>}
        <ul className="space-y-3">
          {draft.decisions.map((d) => (
            <li key={d.id} className="rounded-[12px] bg-hover p-3.5 transition-colors">
              <div className="flex gap-2">
                <AutoText label="ข้อความมติ" value={d.text} onChange={(v) => updDecision("decisions", d.id, { text: v })} />
                <RemoveButton label="ลบมตินี้" onClick={() => set("decisions", draft.decisions.filter((x) => x.id !== d.id))} />
              </div>
              <EvidenceChips evidence={d.evidence} target={{ kind: "decision", id: d.id }} {...p} />
            </li>
          ))}
        </ul>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold">งานที่ต้องติดตาม</h3>
          <button
            className="text-sm text-pine hover:underline"
            onClick={() => set("action_items", [...draft.action_items, { id: newId(), task: "", owner: null, due_date: null, status: "open", evidence: [] }])}
          >
            เพิ่มงาน
          </button>
        </div>
        {draft.action_items.length === 0 && <p className="text-sm text-ink-faint">ไม่มีงานที่ต้องติดตาม</p>}
        <ul className="space-y-3">
          {draft.action_items.map((a) => (
            <li key={a.id} className="rounded-[12px] bg-hover p-3.5 transition-colors">
              <div className="flex gap-2">
                <AutoText label="รายละเอียดงาน" value={a.task} onChange={(v) => updAction(a.id, { task: v })} />
                <RemoveButton label="ลบงานนี้" onClick={() => set("action_items", draft.action_items.filter((x) => x.id !== a.id))} />
              </div>
              <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <input
                  className={inputClass}
                  aria-label="ผู้รับผิดชอบ"
                  placeholder="ผู้รับผิดชอบ (ไม่ระบุ)"
                  value={a.owner ?? ""}
                  onChange={(e) => updAction(a.id, { owner: e.target.value || null })}
                />
                <input
                  className={inputClass}
                  aria-label="กำหนดส่ง"
                  placeholder="กำหนดส่ง (ไม่ระบุ)"
                  value={a.due_date ?? ""}
                  onChange={(e) => updAction(a.id, { due_date: e.target.value || null })}
                />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={a.status === "done"} onChange={(e) => updAction(a.id, { status: e.target.checked ? "done" : "open" })} />
                  เสร็จแล้ว
                </label>
              </div>
              <EvidenceChips evidence={a.evidence} target={{ kind: "action", id: a.id }} {...p} />
            </li>
          ))}
        </ul>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold">ประเด็นที่ยังเปิดอยู่</h3>
          <button className="text-sm text-pine hover:underline" onClick={() => set("open_questions", [...draft.open_questions, { id: newId(), text: "", evidence: [] }])}>
            เพิ่มประเด็น
          </button>
        </div>
        {draft.open_questions.length === 0 && <p className="text-sm text-ink-faint">ไม่มี</p>}
        <ul className="space-y-3">
          {draft.open_questions.map((q) => (
            <li key={q.id} className="rounded-[12px] bg-hover p-3.5 transition-colors">
              <div className="flex gap-2">
                <AutoText label="ประเด็น" value={q.text} onChange={(v) => updDecision("open_questions", q.id, { text: v })} />
                <RemoveButton label="ลบประเด็นนี้" onClick={() => set("open_questions", draft.open_questions.filter((x) => x.id !== q.id))} />
              </div>
              <EvidenceChips evidence={q.evidence} target={{ kind: "question", id: q.id }} {...p} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

const STATUSES: TopicStatus[] = ["resolved", "mentioned", "unclear", "not_mentioned"];

export function TopicChecklist(p: Common & { userId: string }) {
  const { draft, onChange } = p;
  const upd = (id: string, patch: Partial<Topic>) =>
    onChange({ ...draft, topics: draft.topics.map((t) => (t.id === id ? { ...t, ...patch } : t)) });

  return (
    <div>
      <p className="mb-4 text-sm text-ink-soft">
        &ldquo;ได้ข้อสรุป&rdquo; ต้องมีข้อสรุประบุชัดเจน การถูกพูดถึงหรือการเลื่อนไปประชุมครั้งหน้ายังไม่นับว่าจบ
      </p>
      <ul className="space-y-3">
        {draft.topics.map((t) => (
          <li key={t.id} className={`rounded-[12px] p-3.5 transition-colors ${t.verified_by ? "bg-pine-wash" : "bg-hover"}`}>
            <div className="flex flex-wrap items-start gap-2">
              <input
                className={`${inputClass} flex-1 font-medium`}
                aria-label="ชื่อหัวข้อ"
                value={t.title}
                onChange={(e) => upd(t.id, { title: e.target.value })}
              />
              <RemoveButton label="ลบหัวข้อนี้" onClick={() => onChange({ ...draft, topics: draft.topics.filter((x) => x.id !== t.id) })} />
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5" role="radiogroup" aria-label={`สถานะของ ${t.title}`}>
              {STATUSES.map((s) => (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-label={topicStatusLabel[s]}
                  aria-checked={t.status === s}
                  onClick={() => upd(t.id, { status: s, resolution: s === "resolved" ? t.resolution : null })}
                  className={t.status === s ? "" : "opacity-45 hover:opacity-80"}
                >
                  <TopicBadge status={s} />
                </button>
              ))}
            </div>
            {t.status === "resolved" && (
              <div className="mt-2">
                <AutoText
                  label="ข้อสรุป"
                  value={t.resolution ?? ""}
                  placeholder="ข้อสรุปของหัวข้อนี้ (จำเป็น)"
                  onChange={(v) => upd(t.id, { resolution: v })}
                />
                {!t.resolution?.trim() && <p className="mt-1 text-xs text-rust">ต้องระบุข้อสรุปเมื่อเลือก &ldquo;{topicStatusLabel.resolved}&rdquo;</p>}
              </div>
            )}
            {t.status !== "not_mentioned" && <EvidenceChips evidence={t.evidence} target={{ kind: "topic", id: t.id }} {...p} />}
            <label className="mt-2 flex items-center gap-2 text-xs text-ink-soft">
              <input
                type="checkbox"
                checked={!!t.verified_by}
                onChange={(e) => upd(t.id, { verified_by: e.target.checked ? p.userId : null })}
              />
              ตรวจสอบสถานะหัวข้อนี้แล้ว
            </label>
          </li>
        ))}
      </ul>
      <button
        className="mt-3 text-sm text-pine hover:underline"
        onClick={() =>
          onChange({
            ...draft,
            topics: [...draft.topics, { id: newId(), title: "หัวข้อใหม่", source: "manual", status: "mentioned", resolution: null, evidence: [], verified_by: p.userId }],
          })
        }
      >
        เพิ่มหัวข้อ
      </button>
    </div>
  );
}
