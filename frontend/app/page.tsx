"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { Alert, ButtonLink, Spinner, StatusBadge, TiltCard } from "@/components/ui";
import { fmtDate, fmtMs, meetingStatusLabel, sourceLabel } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Me, Meeting, MeetingStatus } from "@/lib/types";

const WaveHero = dynamic(() => import("@/components/three/WaveHero"), { ssr: false });

interface Dashboard {
  counts: Record<MeetingStatus, number>;
  total: number;
  recent: Meeting[];
}

const ORDER: MeetingStatus[] = ["awaiting_review", "processing", "failed", "reviewed", "published", "pending"];
const TILE_ACCENT: Record<MeetingStatus, string> = {
  awaiting_review: "text-amber",
  processing: "text-sky",
  failed: "text-rust",
  reviewed: "text-pine",
  published: "text-pine",
  pending: "text-ink-faint",
};

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "สวัสดีตอนเช้า" : h < 17 ? "สวัสดีตอนบ่าย" : "สวัสดีตอนเย็น";
}

export default function DashboardPage() {
  const { data: me } = useResource<Me>("/api/me");
  const { data, error, loading } = useResource<Dashboard>("/api/dashboard", (d) =>
    d && d.counts.processing > 0 ? 3000 : null,
  );
  const needsReview = data?.counts.awaiting_review ?? 0;

  return (
    <>
      <section className="glass relative mb-6 overflow-hidden rounded-[22px] lg:min-h-[330px]">
        <WaveHero className="h-44 w-full lg:absolute lg:inset-y-0 lg:right-0 lg:h-full lg:w-[54%]" />
        <div className="relative max-w-xl px-6 pb-9 pt-2 sm:px-10 lg:max-w-[44%] lg:py-14">
          <p className="text-sm text-ink-soft">
            {greeting()}
            {me ? `, ${me.user.name}` : ""}
          </p>
          <h1 className="mt-2 text-[2.1rem] font-semibold leading-[1.2] tracking-[-0.025em] sm:text-[2.6rem]">
            {needsReview > 0 ? `${needsReview} การประชุมรอให้คุณตรวจ` : "เปลี่ยนเสียงประชุมเป็นรายงานที่ตรวจสอบได้"}
          </h1>
          <p className="mt-3 max-w-md text-ink-soft">
            AI ร่างสรุปพร้อมอ้างอิงช่วงเสียงทุกข้อ คุณตรวจ แก้ อนุมัติ แล้วส่งเข้าแชทกลุ่ม Teams
          </p>
          <div className="pointer-events-auto mt-7 flex flex-wrap gap-2">
            <ButtonLink href="/sharepoint" variant="primary">
              เลือกไฟล์จาก SharePoint
            </ButtonLink>
            <ButtonLink href="/new">อัปโหลดหรืออัดเสียง</ButtonLink>
          </div>
        </div>
      </section>

      {error && <Alert>{error}</Alert>}
      {loading && !data && <Spinner />}
      {data && (
        <>
          <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {ORDER.map((s) => (
              <TiltCard key={s} className="glass rounded-[var(--radius-panel)]">
                <Link href={`/reports?status=${s}`} className="block rounded-[var(--radius-panel)] px-4 py-4">
                  <span className={`lift tnum block text-[2rem] font-semibold leading-none tracking-tight ${TILE_ACCENT[s]}`}>
                    {data.counts[s] ?? 0}
                  </span>
                  <span className="mt-2 block text-[13px] text-ink-soft">{meetingStatusLabel[s]}</span>
                </Link>
              </TiltCard>
            ))}
          </div>

          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-[15px] font-semibold">ล่าสุด</h2>
            {data.total > data.recent.length && (
              <Link href="/reports" className="text-sm text-pine hover:underline">
                ดูทั้งหมด {data.total} รายการ
              </Link>
            )}
          </div>
          {data.recent.length === 0 ? (
            <div className="glass rounded-[var(--radius-panel)] px-6 py-12 text-center">
              <p className="font-medium">ยังไม่มีรายการประชุม</p>
              <p className="mt-1 text-sm text-ink-soft">เริ่มจากเลือกไฟล์เสียงใน SharePoint หรืออัปโหลด MP3/WAV</p>
            </div>
          ) : (
            <ul className="glass divide-y divide-line-soft overflow-hidden rounded-[var(--radius-panel)]">
              {data.recent.map((m) => (
                <li key={m.id}>
                  <Link
                    href={`/meetings/${m.id}`}
                    className="group flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 transition-colors hover:bg-hover"
                  >
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-pine-wash text-pine" aria-hidden>
                      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                        {[5, 9, 13, 17].map((x, i) => (
                          <rect key={x} x={x - 1} y={12 - [3, 6, 4, 2][i]} width="2" height={[3, 6, 4, 2][i] * 2} rx="1" />
                        ))}
                      </svg>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{m.title}</span>
                      <span className="text-[13px] text-ink-faint">
                        {sourceLabel[m.source_type]}
                        {m.duration_ms ? `, ยาว ${fmtMs(m.duration_ms)}` : ""}, <span className="tnum">{fmtDate(m.created_at)}</span>
                      </span>
                    </span>
                    <StatusBadge status={m.status} />
                    <span className="text-ink-faint transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden>
                      ›
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}
