"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { agendaList, emptySetup, MeetingSetup, type SetupValue } from "@/components/MeetingSetup";
import { Alert, Button, inputClass, PageHeader, Panel, Spinner } from "@/components/ui";
import { errorText, useApi } from "@/lib/api";
import { fmtBytes, fmtDate } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { DriveEntry, Me, Meeting } from "@/lib/types";

interface Site {
  id: string;
  name: string;
  web_url: string | null;
}
interface Drive {
  id: string;
  name: string;
}

export default function SharePointPage() {
  const router = useRouter();
  const { json } = useApi();
  const { data: me } = useResource<Me>("/api/me");
  const { data: sitesData, error: sitesError } = useResource<{ sites: Site[] }>("/api/sharepoint/sites");
  const [siteId, setSiteId] = useState<string>("");
  const [driveId, setDriveId] = useState<string>("");
  const [path, setPath] = useState<{ id: string | null; name: string }[]>([{ id: null, name: "รากของไลบรารี" }]);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [selected, setSelected] = useState<DriveEntry | null>(null);
  const [setup, setSetup] = useState<SetupValue>(emptySetup);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!siteId && sitesData?.sites.length) {
      const pref = me?.preferences.default_site_id;
      setSiteId(sitesData.sites.find((s) => s.id === pref)?.id ?? sitesData.sites[0].id);
    }
  }, [sitesData, siteId, me]);
  useEffect(() => {
    if (me?.preferences.default_language) setSetup((s) => ({ ...s, language: me.preferences.default_language! }));
  }, [me]);

  const { data: drivesData, error: drivesError } = useResource<{ drives: Drive[] }>(
    siteId ? `/api/sharepoint/drives?site_id=${encodeURIComponent(siteId)}` : null,
  );
  useEffect(() => {
    if (drivesData?.drives.length && !drivesData.drives.some((d) => d.id === driveId)) {
      const pref = me?.preferences.default_drive_id;
      setDriveId(drivesData.drives.find((d) => d.id === pref)?.id ?? drivesData.drives[0].id);
    }
  }, [drivesData, driveId, me]);

  const folder = path[path.length - 1];
  const filesPath = driveId
    ? `/api/sharepoint/files?drive_id=${encodeURIComponent(driveId)}` +
      (folder.id ? `&item_id=${encodeURIComponent(folder.id)}` : "") +
      (submittedQuery ? `&q=${encodeURIComponent(submittedQuery)}` : "")
    : null;
  const { data: files, error: filesError, loading: filesLoading } = useResource<{ items: DriveEntry[] }>(filesPath);

  async function start() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const m = await json<Meeting>("/api/meetings", {
        method: "POST",
        body: JSON.stringify({
          drive_id: selected.drive_id ?? driveId,
          item_id: selected.id,
          title: setup.title || null,
          language: setup.language,
          agenda: agendaList(setup),
          consent_ai_processing: setup.consent,
        }),
      });
      await json(`/api/meetings/${m.id}/process`, { method: "POST" });
      router.push(`/meetings/${m.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  const listError = sitesError || drivesError || filesError;

  return (
    <>
      <PageHeader
        title="เลือกไฟล์เสียงจาก SharePoint"
        description="แสดงเฉพาะไซต์ที่ได้รับอนุญาตและไฟล์ที่บัญชีของคุณเปิดได้"
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Panel
          title={
            <span className="flex flex-wrap items-center gap-2 text-sm font-normal">
              {path.map((p, i) => (
                <span key={`${p.id}-${i}`} className="flex items-center gap-2">
                  {i > 0 && <span className="text-ink-faint">/</span>}
                  <button
                    className={i === path.length - 1 ? "font-semibold" : "text-pine hover:underline"}
                    onClick={() => {
                      setPath(path.slice(0, i + 1));
                      setSelected(null);
                    }}
                  >
                    {p.name}
                  </button>
                </span>
              ))}
            </span>
          }
        >
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            <select className={inputClass} value={siteId} onChange={(e) => { setSiteId(e.target.value); setDriveId(""); setPath(path.slice(0, 1)); }} aria-label="ไซต์">
              {sitesData?.sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <select className={inputClass} value={driveId} onChange={(e) => { setDriveId(e.target.value); setPath(path.slice(0, 1)); }} aria-label="ไลบรารีเอกสาร">
              {drivesData?.drives.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
          <form
            className="mb-4 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setSubmittedQuery(query.trim());
            }}
          >
            <input className={inputClass} placeholder="ค้นหาชื่อไฟล์" value={query} onChange={(e) => setQuery(e.target.value)} />
            <Button type="submit">ค้นหา</Button>
          </form>
          {listError && <Alert className="mb-3">{listError}</Alert>}
          {filesLoading && !files ? (
            <Spinner />
          ) : files && files.items.length === 0 ? (
            <p className="py-8 text-center text-ink-soft">ไม่มีไฟล์เสียงในโฟลเดอร์นี้</p>
          ) : (
            <ul className="space-y-0.5">
              {files?.items.map((f) => (
                <li key={f.id}>
                  <button
                    className={`flex w-full items-center gap-3 rounded-[10px] px-3 py-2 text-left transition-colors duration-150 ${
                      selected?.id === f.id ? "bg-pine-wash" : "hover:bg-hover"
                    }`}
                    onClick={() => {
                      if (f.is_folder) {
                        setPath([...path, { id: f.id, name: f.name }]);
                        setSelected(null);
                      } else setSelected(f);
                    }}
                    aria-pressed={selected?.id === f.id}
                  >
                    <span aria-hidden className={`grid h-8 w-8 shrink-0 place-items-center rounded-[8px] ${f.is_folder ? "bg-sky-wash text-sky" : "bg-pine-wash text-pine"}`}>
                      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                        {f.is_folder ? (
                          <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.6l2 2h8.4A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z" />
                        ) : (
                          [5, 9, 13, 17].map((x, i) => <rect key={x} x={x - 1} y={12 - [3, 6, 4, 2][i]} width="2" height={[3, 6, 4, 2][i] * 2} rx="1" />)
                        )}
                      </svg>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{f.name}</span>
                      {!f.is_folder && (
                        <span className="tnum text-xs text-ink-faint">
                          {fmtBytes(f.size)} แก้ไขล่าสุด {fmtDate(f.last_modified)}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="รายละเอียดการประชุม">
          {selected ? (
            <p className="mb-4 rounded-[10px] bg-hover px-3 py-2 text-sm">
              ไฟล์ที่เลือก: <span className="font-medium">{selected.name}</span>
            </p>
          ) : (
            <p className="mb-4 text-sm text-ink-soft">เลือกไฟล์เสียงจากรายการทางซ้าย</p>
          )}
          <MeetingSetup value={setup} onChange={setSetup} />
          {error && <Alert className="mt-4">{error}</Alert>}
          <Button variant="primary" className="mt-5 w-full" disabled={!selected || !setup.consent} busy={busy} onClick={start}>
            เริ่มถอดเสียงและสรุป
          </Button>
        </Panel>
      </div>
    </>
  );
}
