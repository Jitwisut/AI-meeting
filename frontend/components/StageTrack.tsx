import { fmtDate, stageLabel } from "@/lib/format";
import type { Job } from "@/lib/types";

const tone: Record<Job["status"], string> = {
  queued: "border-line bg-surface text-ink-faint",
  running: "border-sky bg-sky-wash text-sky",
  succeeded: "border-pine bg-pine text-on-accent",
  skipped: "border-pine bg-pine-wash text-pine-dark",
  failed: "border-rust bg-rust-wash text-rust",
};

const statusText: Record<Job["status"], string> = {
  queued: "รอคิว",
  running: "กำลังทำงาน",
  succeeded: "เสร็จแล้ว",
  skipped: "ใช้ผลเดิม",
  failed: "ล้มเหลว",
};

/** Real per-stage status from the backend; no invented percentages (plan §5). */
export function StageTrack({ jobs }: { jobs: Job[] }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-4">
      {jobs.map((j, i) => (
        <li key={j.stage} className="relative">
          <div className="flex items-center gap-3">
            <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border-2 text-sm font-semibold ${tone[j.status]}`}>
              {j.status === "succeeded" || j.status === "skipped" ? "✓" : j.status === "failed" ? "!" : i + 1}
            </span>
            <div className="min-w-0">
              <p className="font-medium leading-tight">{stageLabel[j.stage]}</p>
              <p className={`text-xs ${j.status === "failed" ? "text-rust" : "text-ink-faint"}`}>
                {j.status === "running" && <span className="pulse-dot mr-1 inline-block h-1.5 w-1.5 rounded-full bg-sky align-middle" />}
                {statusText[j.status]}
                {j.retry_count > 0 && ` (ลองใหม่ ${j.retry_count} ครั้ง)`}
              </p>
            </div>
          </div>
          {j.status === "failed" && j.error_message && <p className="mt-2 text-sm text-rust">{j.error_message}</p>}
          {j.finished_at && j.status !== "failed" && <p className="tnum mt-1 pl-11 text-xs text-ink-faint">{fmtDate(j.finished_at)}</p>}
        </li>
      ))}
    </ol>
  );
}
