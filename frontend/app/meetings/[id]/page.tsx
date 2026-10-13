"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AudioPlayer, type AudioHandle } from "@/components/AudioPlayer";
import { PublishPanel } from "@/components/PublishPanel";
import { type ItemKind, type LinkTarget, SummarySection, TopicChecklist } from "@/components/ReviewEditor";
import { StageTrack } from "@/components/StageTrack";
import { Transcript } from "@/components/Transcript";
import { Alert, Button, Panel, Segmented, Spinner, StatusBadge, TopicBadge } from "@/components/ui";
import { errorText, useApi } from "@/lib/api";
import { fmtDate, fmtMs, sourceLabel, topicStatusLabel } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Evidence, Me, Meeting, ReportMeta, Segment, Summary } from "@/lib/types";

const Waveform3D = dynamic(() => import("@/components/three/Waveform3D"), { ssr: false });

type Tab = "summary" | "topics" | "publish";

/** Envelope from transcript timing when the audio file has expired: speech = raised bars. */
function envelopeFromSegments(segments: Segment[], durationMs: number, n = 180): number[] {
  const out = new Array(n).fill(0.04);
  for (const s of segments) {
    const a = Math.floor((s.start_ms / durationMs) * n);
    const b = Math.min(n - 1, Math.floor((s.end_ms / durationMs) * n));
    for (let i = a; i <= b; i++) out[i] = 0.35 + 0.3 * Math.abs(Math.sin(i * 1.7 + s.id));
  }
  return out;
}

const LIST_FOR: Record<ItemKind, "topics" | "decisions" | "action_items" | "open_questions"> = {
  topic: "topics",
  decision: "decisions",
  action: "action_items",
  question: "open_questions",
};

function toPatch(s: Summary) {
  const ev = (xs: Evidence[]) => xs.map((e) => ({ segment_id: e.segment_id }));
  return {
    meeting_title: s.meeting_title,
    summary: s.summary,
    topics: s.topics.map((t) => ({
      id: t.id, title: t.title, source: t.source, status: t.status,
      resolution: t.resolution, evidence: ev(t.evidence), verified: !!t.verified_by,
    })),
    decisions: s.decisions.filter((d) => d.text.trim()).map((d) => ({ id: d.id, text: d.text, evidence: ev(d.evidence) })),
    action_items: s.action_items.filter((a) => a.task.trim()).map((a) => ({
      id: a.id, task: a.task, owner: a.owner, due_date: a.due_date, status: a.status, evidence: ev(a.evidence),
    })),
    open_questions: s.open_questions.filter((q) => q.text.trim()).map((q) => ({ id: q.id, text: q.text, evidence: ev(q.evidence) })),
  };
}

function ProcessingView({ meeting, onRetry, busy, error }: { meeting: Meeting; onRetry: () => void; busy: boolean; error: string | null }) {
  return (
    <Panel title="สถานะการประมวลผล">
      <StageTrack jobs={meeting.jobs ?? []} />
      {meeting.status === "processing" && !meeting.processing_stale && (
        <p className="mt-6 text-sm text-ink-soft">
          ไฟล์ยาวอาจใช้เวลาหลายนาที ปิดหน้านี้ได้ ระบบทำงานต่อในเบื้องหลังและสถานะจะอัปเดตเอง
        </p>
      )}
      {(meeting.status === "failed" || meeting.status === "pending" || meeting.processing_stale) && (
        <div className="mt-6 space-y-3">
          {meeting.processing_stale && (
            <Alert tone="warn">งานนี้ไม่มีความคืบหน้านานผิดปกติ อาจหยุดทำงานกลางคัน กดเริ่มใหม่ได้อย่างปลอดภัย</Alert>
          )}
          {meeting.error_message && <Alert>{meeting.error_message}</Alert>}
          {error && <Alert>{error}</Alert>}
          <Button variant="primary" busy={busy} onClick={onRetry}>
            {meeting.status === "pending" ? "เริ่มประมวลผล" : "ลองประมวลผลอีกครั้ง"}
          </Button>
          {meeting.status !== "pending" && (
            <p className="text-xs text-ink-faint">ขั้นตอนที่เสร็จแล้วจะไม่ถูกทำซ้ำ</p>
          )}
        </div>
      )}
    </Panel>
  );
}

function PrintableReport({ meeting, summary, report }: { meeting: Meeting; summary: Summary; report: ReportMeta }) {
  return (
    <article className="hidden print:block">
      <h1 className="text-2xl font-semibold">{summary.meeting_title}</h1>
      <p className="text-sm">
        ฉบับที่ {report.version} {report.is_approved ? `อนุมัติโดย ${report.approved_by} ${fmtDate(report.approved_at)}` : "(ร่าง ยังไม่อนุมัติ)"} ไฟล์ {meeting.source_filename}
      </p>
      <h2 className="mt-4 font-semibold">สรุปภาพรวม</h2>
      <p>{summary.summary}</p>
      <h2 className="mt-4 font-semibold">สถานะหัวข้อ</h2>
      <ul>{summary.topics.map((t) => <li key={t.id}>{t.title}: {topicStatusLabel[t.status]}{t.resolution ? ` ข้อสรุป: ${t.resolution}` : ""}</li>)}</ul>
      <h2 className="mt-4 font-semibold">มติที่ประชุม</h2>
      <ol className="list-decimal pl-6">{summary.decisions.map((d) => <li key={d.id}>{d.text}</li>)}</ol>
      <h2 className="mt-4 font-semibold">งานที่ต้องติดตาม</h2>
      <ul>{summary.action_items.map((a) => <li key={a.id}>{a.task} ผู้รับผิดชอบ: {a.owner ?? "ยังไม่ระบุ"} กำหนด: {a.due_date ?? "ยังไม่ระบุ"}</li>)}</ul>
    </article>
  );
}

export default function MeetingPage() {
  const { id } = useParams<{ id: string }>();
  const { json } = useApi();
  const { data: me } = useResource<Me>("/api/me");
  const meetingRes = useResource<Meeting>(`/api/meetings/${id}`, (m) =>
    m && (m.status === "processing" || m.status === "pending") ? 2000 : null,
  );
  const meeting = meetingRes.data;
  const hasReport = !!meeting?.report;

  const transcriptRes = useResource<{ segments: Segment[]; provider: string }>(hasReport ? `/api/meetings/${id}/transcript` : null);
  const summaryRes = useResource<{ summary: Summary; report: ReportMeta }>(hasReport ? `/api/meetings/${id}/summary` : null);
  const waveRes = useResource<{ peaks: number[]; duration_ms: number | null }>(
    hasReport && meeting?.audio_available ? `/api/meetings/${id}/waveform?buckets=180` : null,
  );

  const [draft, setDraft] = useState<Summary | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [currentMs, setCurrentMs] = useState(0);
  const [focusId, setFocusId] = useState<number | null>(null);
  const [busy, setBusy] = useState<"save" | "approve" | "retry" | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error" | "warn"; text: string } | null>(null);
  const [showWarnings, setShowWarnings] = useState(false);
  const player = useRef<AudioHandle>(null);

  const server = summaryRes.data;
  useEffect(() => {
    if (server) setDraft(structuredClone(server.summary));
  }, [server]);

  const dirty = useMemo(
    () => !!(server && draft && JSON.stringify(toPatch(server.summary)) !== JSON.stringify(toPatch(draft))),
    [server, draft],
  );

  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  const segments = useMemo(() => transcriptRes.data?.segments ?? [], [transcriptRes.data]);
  const segById = useMemo(() => new Map(segments.map((s) => [s.id, s])), [segments]);

  const evidenceIds = useMemo(() => {
    const ids = new Set<number>();
    if (!draft) return ids;
    for (const list of [draft.topics, draft.decisions, draft.action_items, draft.open_questions])
      for (const item of list) for (const e of item.evidence) ids.add(e.segment_id);
    return ids;
  }, [draft]);

  const linkedIds = useMemo(() => {
    if (!draft || !linking) return new Set<number>();
    const list = draft[LIST_FOR[linking.kind]] as { id: string; evidence: Evidence[] }[];
    return new Set(list.find((x) => x.id === linking.id)?.evidence.map((e) => e.segment_id) ?? []);
  }, [draft, linking]);

  const toggleLink = useCallback(
    (segId: number) => {
      if (!draft || !linking) return;
      const key = LIST_FOR[linking.kind];
      const seg = segById.get(segId);
      if (!seg) return;
      const list = (draft[key] as { id: string; evidence: Evidence[] }[]).map((item) => {
        if (item.id !== linking.id) return item;
        const has = item.evidence.some((e) => e.segment_id === segId);
        const evidence = has
          ? item.evidence.filter((e) => e.segment_id !== segId)
          : [...item.evidence, { segment_id: seg.id, start_ms: seg.start_ms, end_ms: seg.end_ms, text: seg.text }].sort(
              (a, b) => a.start_ms - b.start_ms,
            );
        return { ...item, evidence };
      });
      setDraft({ ...draft, [key]: list });
    },
    [draft, linking, segById],
  );

  const durationMs = meeting?.duration_ms ?? segments.at(-1)?.end_ms ?? 0;
  const peaks = useMemo(
    () => waveRes.data?.peaks ?? (segments.length && durationMs ? envelopeFromSegments(segments, durationMs) : []),
    [waveRes.data, segments, durationMs],
  );
  const markers = useMemo(
    () => [...evidenceIds].map((sid) => segById.get(sid)).filter((s): s is Segment => !!s).map((s) => ({ ms: s.start_ms, segmentId: s.id })),
    [evidenceIds, segById],
  );
  const seek = useCallback((ms: number) => {
    setCurrentMs(ms);
    player.current?.seek(ms);
  }, []);

  const focusEvidence = useCallback((e: Evidence) => {
    setFocusId(e.segment_id);
    player.current?.seek(e.start_ms);
  }, []);

  async function save(): Promise<ReportMeta | null> {
    if (!draft || !server) return null;
    setBusy("save");
    setMsg(null);
    try {
      const r = await json<{ summary: Summary; report: ReportMeta }>(`/api/meetings/${id}/summary`, {
        method: "PATCH",
        body: JSON.stringify({ version: server.report.version, summary: toPatch(draft) }),
      });
      summaryRes.setData(r);
      setLinking(null);
      setMsg({ tone: "success", text: `บันทึกเป็นฉบับที่ ${r.report.version} แล้ว ต้องอนุมัติฉบับนี้ก่อนส่งออก` });
      void meetingRes.reload();
      return r.report;
    } catch (e) {
      setMsg({ tone: "error", text: errorText(e) });
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    if (!server) return;
    setBusy("approve");
    setMsg(null);
    try {
      await json(`/api/meetings/${id}/approve`, { method: "POST", body: JSON.stringify({ version: server.report.version }) });
      await summaryRes.reload();
      await meetingRes.reload();
      setMsg({ tone: "success", text: `อนุมัติฉบับที่ ${server.report.version} แล้ว ส่งออกหรือส่งเข้า Teams ได้ที่แท็บ "ส่งออกและเผยแพร่"` });
    } catch (e) {
      setMsg({ tone: "error", text: errorText(e) });
    } finally {
      setBusy(null);
    }
  }

  async function retry() {
    setBusy("retry");
    setMsg(null);
    try {
      await json(`/api/meetings/${id}/process`, { method: "POST" });
      await meetingRes.reload();
    } catch (e) {
      setMsg({ tone: "error", text: errorText(e) });
    } finally {
      setBusy(null);
    }
  }

  if (meetingRes.error && !meeting) return <Alert>{meetingRes.error}</Alert>;
  if (!meeting) return <Spinner />;

  const report = server?.report;
  const warnings = draft?.validation_warnings ?? [];

  return (
    <>
      <header className="no-print glass sticky top-2 z-20 mb-6 rounded-[16px] px-5 py-4 lg:top-3">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={meeting.status} />
          <span className="text-sm text-ink-faint">
            {sourceLabel[meeting.source_type]}: {meeting.source_filename}
            {meeting.duration_ms ? `, ยาว ${fmtMs(meeting.duration_ms)}` : ""}
          </span>
        </div>
        <h1 className="mt-1.5 text-[1.6rem] font-semibold leading-tight tracking-[-0.02em]">{draft?.meeting_title || meeting.title}</h1>
        {report && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-sm text-ink-soft">
              ฉบับที่ {report.version}
              {report.is_approved ? `, อนุมัติโดย ${report.approved_by} ${fmtDate(report.approved_at)}` : ", ยังไม่อนุมัติ"}
              {report.generated_by === "mock" && ", ร่างโดย AI จำลอง"}
            </span>
            <span className="flex-1" />
            {dirty && <span className="text-sm text-amber">มีการแก้ไขที่ยังไม่บันทึก</span>}
            <Button disabled={!dirty} busy={busy === "save"} onClick={save}>
              บันทึกการแก้ไข
            </Button>
            <Button
              variant="primary"
              disabled={dirty || report.is_approved || me?.can_approve === false}
              busy={busy === "approve"}
              onClick={approve}
              title={me?.can_approve === false ? "บัญชีนี้ไม่มีสิทธิ์อนุมัติ" : undefined}
            >
              {report.is_approved ? "อนุมัติแล้ว" : "อนุมัติรายงาน"}
            </Button>
          </div>
        )}
        {msg && <Alert tone={msg.tone} className="mt-4">{msg.text}</Alert>}
      </header>

      {!hasReport ? (
        <ProcessingView meeting={meeting} onRetry={retry} busy={busy === "retry"} error={null} />
      ) : !draft || !report ? (
        <Spinner label="กำลังโหลดบทถอดเสียงและสรุป" />
      ) : (
        <>
          {warnings.length > 0 && (
            <div className="no-print mb-6 rounded-[12px] bg-amber-wash px-4 py-3 text-sm text-amber">
              <button className="font-medium" onClick={() => setShowWarnings((s) => !s)} aria-expanded={showWarnings}>
                ระบบตรวจพบและแก้ไขผลจาก AI {warnings.length} รายการ {showWarnings ? "(ซ่อน)" : "(ดูรายละเอียด)"}
              </button>
              {showWarnings && (
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
            </div>
          )}

          <div className="no-print grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
            <section className="lg:sticky lg:top-6 lg:self-start">
              <div className="glass overflow-hidden rounded-[var(--radius-panel)]">
                {peaks.length > 0 && durationMs > 0 && (
                  <div className="border-b border-line-soft bg-[linear-gradient(180deg,transparent,var(--pine-wash))]">
                    <Waveform3D peaks={peaks} durationMs={durationMs} currentMs={currentMs} markers={markers} onSeek={seek} />
                  </div>
                )}
                <div className="border-b border-line-soft p-3">
                  <AudioPlayer ref={player} meetingId={meeting.id} available={!!meeting.audio_available} onTime={setCurrentMs} />
                </div>
                {linking && (
                  <p className="border-b border-sky/20 bg-sky-wash px-4 py-2 text-sm text-sky">
                    คลิกช่วงบทถอดเสียงเพื่อเพิ่มหรือเอาออกจากหลักฐาน
                    <button className="ml-2 font-medium underline" onClick={() => setLinking(null)}>เสร็จสิ้น</button>
                  </p>
                )}
                <div className="max-h-[52vh] overflow-y-auto p-3">
                  <h2 className="sr-only">บทถอดเสียง</h2>
                  {transcriptRes.error && <Alert>{transcriptRes.error}</Alert>}
                  <Transcript
                    segments={segments}
                    currentMs={currentMs}
                    focusId={focusId}
                    evidenceIds={evidenceIds}
                    linking={!!linking}
                    linkedIds={linkedIds}
                    onSeek={seek}
                    onToggleLink={toggleLink}
                  />
                </div>
                <p className="border-t border-line-soft px-4 py-2 text-xs text-ink-faint">
                  {segments.length} ช่วง ถอดเสียงโดย {transcriptRes.data?.provider === "mock" ? "ระบบจำลอง" : "Azure AI Speech"} ไม่มีการแยกผู้พูด
                </p>
              </div>
            </section>

            <section className="glass rounded-[var(--radius-panel)]">
              <div className="border-b border-line-soft px-4 py-3">
                <Segmented<Tab>
                  label="ส่วนของรายงาน"
                  value={tab}
                  onChange={setTab}
                  className="w-full [&>button]:flex-1"
                  options={[
                    { value: "summary", label: "สรุป มติ งาน" },
                    { value: "topics", label: `หัวข้อ ${draft.topics.filter((t) => t.status === "resolved").length}/${draft.topics.length}` },
                    { value: "publish", label: "ส่งออกและเผยแพร่" },
                  ]}
                />
              </div>
              <div key={tab} className="pop-in p-5">
                {tab === "summary" && (
                  <SummarySection draft={draft} onChange={setDraft} linking={linking} setLinking={setLinking} onFocusEvidence={focusEvidence} />
                )}
                {tab === "topics" && (
                  <>
                    <div className="mb-4 flex flex-wrap gap-2">
                      {(["resolved", "mentioned", "unclear", "not_mentioned"] as const).map((s) => (
                        <span key={s} className="flex items-center gap-1 text-xs text-ink-soft">
                          <TopicBadge status={s} /> {draft.topics.filter((t) => t.status === s).length}
                        </span>
                      ))}
                    </div>
                    <TopicChecklist
                      draft={draft}
                      onChange={setDraft}
                      linking={linking}
                      setLinking={setLinking}
                      onFocusEvidence={focusEvidence}
                      userId={me?.user.id ?? ""}
                    />
                  </>
                )}
                {tab === "publish" && (
                  <PublishPanel
                    meeting={meeting}
                    report={report}
                    dirty={dirty}
                    onChanged={() => {
                      void meetingRes.reload();
                      void summaryRes.reload();
                    }}
                  />
                )}
              </div>
            </section>
          </div>
          <PrintableReport meeting={meeting} summary={draft} report={report} />
        </>
      )}
    </>
  );
}
