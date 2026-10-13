"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, inputClass, PageHeader, Spinner, StatusBadge } from "@/components/ui";
import { fmtDate, meetingStatusLabel } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Meeting, MeetingStatus } from "@/lib/types";

function Reports() {
  const params = useSearchParams();
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const path = `/api/meetings?limit=200${status ? `&status=${status}` : ""}${query ? `&q=${encodeURIComponent(query)}` : ""}`;
  const { data, error, loading } = useResource<{ meetings: Meeting[] }>(path);

  return (
    <>
      <PageHeader title="รายงานและประวัติการส่ง" description="ไฟล์ Word ใน SharePoint ผู้อนุมัติ และสถานะการส่งเข้า Teams ของแต่ละการประชุม" />
      <form
        className="mb-5 flex flex-wrap gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <select className={`${inputClass} w-auto`} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="สถานะ">
          <option value="">ทุกสถานะ</option>
          {(Object.keys(meetingStatusLabel) as MeetingStatus[]).map((s) => (
            <option key={s} value={s}>{meetingStatusLabel[s]}</option>
          ))}
        </select>
        <input className={`${inputClass} w-64`} placeholder="ค้นหาชื่อการประชุมหรือไฟล์" value={q} onChange={(e) => setQ(e.target.value)} />
      </form>
      {error && <Alert>{error}</Alert>}
      {loading && !data ? (
        <Spinner />
      ) : data?.meetings.length === 0 ? (
        <p className="glass rounded-[var(--radius-panel)] px-6 py-12 text-center text-ink-soft">
          ไม่พบรายการตามเงื่อนไขนี้
        </p>
      ) : (
        <div className="glass overflow-x-auto rounded-[var(--radius-panel)]">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="border-b border-line text-left text-ink-soft">
              <tr>
                <th className="px-4 py-3 font-medium">การประชุม</th>
                <th className="px-4 py-3 font-medium">สถานะ</th>
                <th className="px-4 py-3 font-medium">ฉบับ / ผู้อนุมัติ</th>
                <th className="px-4 py-3 font-medium">รายงาน</th>
                <th className="px-4 py-3 font-medium">สร้างเมื่อ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {data?.meetings.map((m) => (
                <tr key={m.id} className="hover:bg-hover">
                  <td className="px-4 py-3">
                    <Link href={`/meetings/${m.id}`} className="font-medium text-ink hover:text-pine hover:underline">{m.title}</Link>
                    {m.error_message && <span className="block text-xs text-rust">{m.error_message}</span>}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={m.status} /></td>
                  <td className="px-4 py-3 text-ink-soft">
                    {m.report ? (
                      <>
                        ฉบับที่ {m.report.version}
                        <span className="block text-xs">{m.report.is_approved ? `อนุมัติโดย ${m.report.approved_by}` : "ยังไม่อนุมัติฉบับนี้"}</span>
                      </>
                    ) : "–"}
                  </td>
                  <td className="px-4 py-3">
                    {m.report?.sharepoint_web_url ? (
                      <a href={m.report.sharepoint_web_url} target="_blank" rel="noreferrer" className="text-pine hover:underline">
                        เปิดใน SharePoint
                      </a>
                    ) : <span className="text-ink-faint">ยังไม่ส่งออก</span>}
                  </td>
                  <td className="tnum px-4 py-3 text-ink-soft">{fmtDate(m.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function ReportsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Reports />
    </Suspense>
  );
}
