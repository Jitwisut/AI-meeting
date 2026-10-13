"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { config } from "@/lib/config";
import { applyThemePref, readThemePref, type ThemePref } from "@/lib/theme";
import { Button, Segmented } from "./ui";

const I = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  cloud: "M7 18h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6.1 9.2 4.5 4.5 0 0 0 7 18z",
  mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm6-3a6 6 0 0 1-12 0m6 6v3",
  doc: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm7 0v5h5M9 13h6M9 17h6",
  gear: "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zm7.4-2.1.1-1.4-.1-1.4 2-1.6-2-3.4-2.4 1a7 7 0 0 0-2.4-1.4L14.2 2h-4l-.4 2.6a7 7 0 0 0-2.4 1.4l-2.4-1-2 3.4 2 1.6-.1 1.4.1 1.4-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2.4 1.4l.4 2.6h4l.4-2.6a7 7 0 0 0 2.4-1.4l2.4 1 2-3.4z",
};

function Icon({ d, className = "h-[18px] w-[18px]" }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

const NAV = [
  { href: "/", label: "ภาพรวม", icon: I.home },
  { href: "/sharepoint", label: "SharePoint", icon: I.cloud },
  { href: "/new", label: "อัปโหลด / อัดเสียง", icon: I.mic },
  { href: "/reports", label: "รายงานและประวัติ", icon: I.doc },
  { href: "/settings", label: "ตั้งค่า", icon: I.gear },
];

function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="relative grid h-8 w-8 place-items-center rounded-[9px] bg-[linear-gradient(145deg,var(--pine),color-mix(in_srgb,var(--pine)_55%,#5b4bd6))] shadow-[inset_0_1px_0_rgba(255,255,255,0.35),0_4px_10px_-2px_color-mix(in_srgb,var(--pine)_60%,transparent)]">
        <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" aria-hidden>
          {[4, 8, 12, 16, 20].map((x, i) => (
            <rect key={x} x={x - 1} y={12 - [3, 6, 8, 5, 2][i]} width="2" height={[3, 6, 8, 5, 2][i] * 2} rx="1" fill="white" />
          ))}
        </svg>
      </span>
      <span className="leading-tight">
        <span className="block text-[14px] font-semibold">Meeting Minutes</span>
        <span className="block text-[11px] text-ink-faint">ร่างโดย AI ตรวจโดยคน</span>
      </span>
    </span>
  );
}

function SignIn() {
  const { signIn } = useAuth();
  return (
    <main className="grid min-h-screen place-items-center px-4">
      <div className="glass-strong page-in w-full max-w-sm rounded-[20px] p-8 text-center">
        <div className="flex justify-center">
          <Logo />
        </div>
        <h1 className="mt-8 text-xl font-semibold">เข้าสู่ระบบด้วยบัญชีองค์กร</h1>
        <p className="mt-2 text-sm text-ink-soft">
          ระบบเข้าถึงไฟล์ SharePoint และแชท Teams ตามสิทธิ์ของบัญชี Microsoft 365 ของคุณเท่านั้น
        </p>
        <Button variant="primary" className="mt-6 w-full" onClick={() => signIn()}>
          เข้าสู่ระบบด้วย Microsoft
        </Button>
      </div>
    </main>
  );
}

function ThemeSwitch() {
  const [pref, setPref] = useState<ThemePref>("system");
  useEffect(() => setPref(readThemePref()), []);
  return (
    <Segmented<ThemePref>
      label="ธีม"
      role="radiogroup"
      className="w-full [&>button]:flex-1"
      value={pref}
      onChange={(v) => {
        setPref(v);
        applyThemePref(v);
      }}
      options={[
        { value: "system", label: "อัตโนมัติ" },
        { value: "light", label: "สว่าง" },
        { value: "dark", label: "มืด" },
      ]}
    />
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { ready, signedIn, accountName, mockUser, setMockUser, signOut } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  if (!ready) return <div className="p-10 text-ink-soft">กำลังตรวจสอบการเข้าสู่ระบบ…</div>;
  if (!signedIn) return <SignIn />;

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[264px_1fr]">
      <aside className="no-print sticky top-0 z-30 p-2 lg:h-screen lg:p-3">
        <div className="vibrancy flex h-full flex-col rounded-[16px]">
          <div className="flex items-center justify-between px-4 pb-3 pt-4">
            <Link href="/" className="rounded-[8px]">
              <Logo />
            </Link>
            <button
              className="rounded-[8px] px-3 py-1.5 text-sm text-ink-soft hover:bg-hover lg:hidden"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
            >
              เมนู
            </button>
          </div>
          <nav className={`${open ? "block" : "hidden"} px-2.5 lg:block`}>
            <p className="px-2.5 pb-1 pt-2 text-[11px] font-medium text-ink-faint">พื้นที่ทำงาน</p>
            {NAV.map((n) => {
              const active = isActive(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  onClick={() => setOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={`mb-0.5 flex items-center gap-2.5 rounded-[8px] px-2.5 py-[7px] text-[13.5px] transition-colors duration-150 ${
                    active ? "bg-pine-wash font-medium text-ink" : "text-ink-soft hover:bg-hover hover:text-ink"
                  }`}
                >
                  <span className={active ? "text-pine" : "text-ink-faint"}>
                    <Icon d={n.icon} />
                  </span>
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <div className={`${open ? "block" : "hidden"} mt-auto space-y-3 px-3 pb-3 pt-4 lg:block`}>
            <ThemeSwitch />
            {config.authMode === "mock" ? (
              <label className="block rounded-[10px] bg-hover p-2.5">
                <span className="text-[11px] text-ink-faint">โหมดทดสอบ: ผู้ใช้จำลอง</span>
                <select
                  value={mockUser}
                  onChange={(e) => setMockUser(e.target.value)}
                  className="mt-1 w-full rounded-[7px] bg-surface px-2 py-1.5 text-[13px] shadow-[inset_0_0_0_0.5px_var(--line)]"
                >
                  <option value="dev-user">ผู้ใช้ทดสอบ (dev-user)</option>
                  <option value="other-user">ผู้ใช้อื่น (other-user)</option>
                </select>
              </label>
            ) : (
              <div className="flex items-center gap-2.5 rounded-[10px] bg-hover p-2.5 text-[13px]">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-pine text-xs font-semibold text-on-accent">
                  {(accountName ?? "?").slice(0, 1)}
                </span>
                <span className="min-w-0 flex-1 truncate">{accountName}</span>
                <button className="text-ink-soft hover:text-ink" onClick={() => signOut()}>
                  ออก
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>
      <main className="mx-auto w-full max-w-[1320px] px-4 pb-12 pt-4 sm:px-8 lg:pt-9">
        <div key={pathname} className="page-in">
          {children}
        </div>
      </main>
    </div>
  );
}
