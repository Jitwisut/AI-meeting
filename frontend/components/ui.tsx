"use client";

import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";
import type { MeetingStatus, TopicStatus } from "@/lib/types";
import { meetingStatusLabel, topicStatusLabel } from "@/lib/format";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary:
    "bg-pine text-on-accent shadow-[inset_0_1px_0_rgba(255,255,255,0.25),0_1px_2px_rgba(0,0,0,0.15)] hover:brightness-110 disabled:opacity-45 disabled:hover:brightness-100",
  secondary:
    "bg-surface text-ink shadow-[0_0_0_0.5px_var(--line),0_1px_1.5px_rgba(0,0,0,0.08)] hover:bg-hover disabled:text-ink-faint",
  ghost: "text-ink-soft hover:text-ink hover:bg-hover",
  danger: "bg-rust text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:brightness-110",
};

const base =
  "inline-flex items-center justify-center gap-2 rounded-[8px] px-3.5 py-[7px] text-[13.5px] font-medium select-none transition-[filter,background-color,transform,opacity] duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:active:scale-100";

export function Button({
  variant = "secondary",
  className = "",
  busy,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button {...props} disabled={props.disabled || busy} className={`${base} ${variants[variant]} ${className}`}>
      {busy && <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "secondary",
  children,
  className = "",
}: {
  href: string;
  variant?: Variant;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Link href={href} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </Link>
  );
}

const meetingTone: Record<MeetingStatus, string> = {
  pending: "bg-hover text-ink-soft",
  processing: "bg-sky-wash text-sky",
  awaiting_review: "bg-amber-wash text-amber",
  reviewed: "bg-pine-wash text-pine-dark",
  published: "bg-pine text-on-accent",
  failed: "bg-rust-wash text-rust",
};

export function StatusBadge({ status }: { status: MeetingStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${meetingTone[status]}`}>
      {status === "processing" && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-current" />}
      {meetingStatusLabel[status]}
    </span>
  );
}

const topicTone: Record<TopicStatus, string> = {
  resolved: "bg-pine text-on-accent",
  mentioned: "bg-amber-wash text-amber",
  unclear: "bg-surface text-ink-soft shadow-[inset_0_0_0_1px_var(--line)]",
  not_mentioned: "bg-hover text-ink-faint",
};

const topicMark: Record<TopicStatus, string> = {
  resolved: "✓",
  mentioned: "◐",
  unclear: "?",
  not_mentioned: "○",
};

export function TopicBadge({ status }: { status: TopicStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${topicTone[status]}`}>
      <span aria-hidden>{topicMark[status]}</span>
      {topicStatusLabel[status]}
    </span>
  );
}

export function Alert({
  tone = "error",
  children,
  className = "",
}: {
  tone?: "error" | "info" | "warn" | "success";
  children: React.ReactNode;
  className?: string;
}) {
  const t = {
    error: "bg-rust-wash text-rust",
    info: "bg-sky-wash text-sky",
    warn: "bg-amber-wash text-amber",
    success: "bg-pine-wash text-pine-dark",
  }[tone];
  const icon = { error: "!", info: "i", warn: "!", success: "✓" }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`pop-in flex gap-3 rounded-[10px] px-3.5 py-2.5 text-sm ${t} ${className}`}>
      <span aria-hidden className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-current text-[10px] font-bold">
        <span className="text-surface">{icon}</span>
      </span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-[1.9rem] font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
        {description && <p className="mt-1.5 text-ink-soft">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

/** A macOS-style window: translucent material, hairline edge, soft depth. */
export function Panel({
  title,
  aside,
  children,
  className = "",
  bodyClassName = "p-5",
}: {
  title?: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`glass rounded-[var(--radius-panel)] ${className}`}>
      {title && (
        <div className="flex min-h-11 items-center justify-between gap-3 border-b border-line-soft px-5 py-2.5">
          <h2 className="text-[13.5px] font-semibold">{title}</h2>
          {aside}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function Spinner({ label = "กำลังโหลด" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-ink-soft" role="status">
      <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" aria-hidden>
        {Array.from({ length: 8 }).map((_, i) => (
          <rect key={i} x="11" y="2" width="2" height="6" rx="1" fill="currentColor" opacity={(i + 1) / 8} transform={`rotate(${i * 45} 12 12)`} />
        ))}
      </svg>
      {label}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-ink-soft">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-faint">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-[8px] bg-surface px-3 py-[7px] text-sm text-ink shadow-[inset_0_0_0_0.5px_var(--line),inset_0_1px_2px_rgba(0,0,0,0.04)] placeholder:text-ink-faint transition-shadow duration-200 focus:outline-none focus:shadow-[inset_0_0_0_1px_var(--pine),0_0_0_3.5px_var(--pine-wash)]";

/** macOS switch. */
export function Switch({
  checked,
  onChange,
  label,
  description,
  tone = "default",
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: React.ReactNode;
  description?: React.ReactNode;
  tone?: "default" | "warn";
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-[10px] p-3 text-sm ${
        tone === "warn" ? "bg-amber-wash text-amber" : "bg-hover"
      } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      <span className="min-w-0 flex-1">
        {label}
        {description && <span className="mt-0.5 block text-xs opacity-75">{description}</span>}
      </span>
      <input type="checkbox" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden
        className={`relative mt-0.5 h-[22px] w-[38px] shrink-0 rounded-full transition-colors duration-300 ease-[var(--ease-mac)] peer-focus-visible:ring-[3px] peer-focus-visible:ring-pine/40 ${
          checked ? "bg-pine" : "bg-ink-faint/40"
        }`}
      >
        <span
          className={`absolute top-[2px] h-[18px] w-[18px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.3)] transition-transform duration-300 ease-[var(--ease-spring)] ${
            checked ? "translate-x-[18px]" : "translate-x-[2px]"
          }`}
        />
      </span>
    </label>
  );
}

/** macOS segmented control with a sliding thumb. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  className = "",
  role = "tablist",
}: {
  value: T;
  options: { value: T; label: React.ReactNode }[];
  onChange: (v: T) => void;
  label: string;
  className?: string;
  role?: "tablist" | "radiogroup";
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [thumb, setThumb] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const measure = () => {
      const el = refs.current[value];
      if (el) setThumb({ left: el.offsetLeft, width: el.offsetWidth });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [value, options.length]);

  return (
    <div
      role={role}
      aria-label={label}
      className={`relative inline-flex max-w-full overflow-x-auto rounded-[9px] bg-hover p-[2px] shadow-[inset_0_0_0_0.5px_var(--line)] ${className}`}
    >
      {thumb && (
        <span
          aria-hidden
          className="absolute bottom-[2px] top-[2px] rounded-[7px] bg-surface shadow-[0_0_0_0.5px_var(--line),0_2px_6px_rgba(0,0,0,0.12)] transition-[left,width] duration-300 ease-[var(--ease-mac)]"
          style={{ left: thumb.left, width: thumb.width }}
        />
      )}
      {options.map((o) => (
        <button
          key={o.value}
          ref={(el) => {
            refs.current[o.value] = el;
          }}
          type="button"
          role={role === "tablist" ? "tab" : "radio"}
          aria-selected={role === "tablist" ? value === o.value : undefined}
          aria-checked={role === "radiogroup" ? value === o.value : undefined}
          onClick={() => onChange(o.value)}
          className={`relative z-10 whitespace-nowrap rounded-[7px] px-3.5 py-[5px] text-[13px] transition-colors duration-200 ${
            value === o.value ? "font-medium text-ink" : "text-ink-soft hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Card that tilts toward the pointer in 3D. */
export function TiltCard({ children, className = "", ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div
      {...rest}
      ref={ref}
      className={`tilt ${className}`}
      onPointerMove={(e) => {
        const el = ref.current;
        if (!el || e.pointerType !== "mouse") return;
        const r = el.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        el.style.setProperty("--ry", `${x * 14}deg`);
        el.style.setProperty("--rx", `${-y * 14}deg`);
      }}
      onPointerLeave={() => {
        ref.current?.style.setProperty("--ry", "0deg");
        ref.current?.style.setProperty("--rx", "0deg");
      }}
    >
      {children}
    </div>
  );
}
