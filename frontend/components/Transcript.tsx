"use client";

import { useEffect, useRef } from "react";
import { fmtMs } from "@/lib/format";
import type { Segment } from "@/lib/types";

/**
 * The transcript as a timeline ("tape"). Segments cited as evidence are marked;
 * in linking mode, clicking a segment toggles it as evidence for the active item.
 */
export function Transcript({
  segments,
  currentMs,
  focusId,
  evidenceIds,
  linking,
  linkedIds,
  onSeek,
  onToggleLink,
}: {
  segments: Segment[];
  currentMs: number;
  focusId: number | null;
  evidenceIds: Set<number>;
  linking: boolean;
  linkedIds: Set<number>;
  onSeek: (ms: number) => void;
  onToggleLink: (id: number) => void;
}) {
  const refs = useRef<Record<number, HTMLLIElement | null>>({});

  useEffect(() => {
    if (focusId != null) refs.current[focusId]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusId]);

  return (
    <ol className="tape relative space-y-0.5">
      {segments.map((s) => {
        const playing = currentMs >= s.start_ms && currentMs < s.end_ms;
        const linked = linkedIds.has(s.id);
        const cited = evidenceIds.has(s.id);
        return (
          <li
            key={s.id}
            ref={(el) => {
              refs.current[s.id] = el;
            }}
            className={`group relative grid grid-cols-[4.25rem_1fr] rounded-md transition-colors ${
              focusId === s.id ? "bg-amber-wash" : playing ? "bg-pine-wash/70" : ""
            } ${linking ? "cursor-pointer hover:bg-sky-wash" : ""} ${linked ? "ring-2 ring-sky" : ""}`}
            onClick={linking ? () => onToggleLink(s.id) : undefined}
          >
            <button
              type="button"
              className="tnum relative py-2 pr-3 text-right text-xs text-ink-faint hover:text-pine"
              onClick={(e) => {
                e.stopPropagation();
                onSeek(s.start_ms);
              }}
              title="เล่นจากช่วงนี้"
            >
              {fmtMs(s.start_ms)}
              <span
                className={`absolute -right-[4.5px] top-[0.95rem] h-2.5 w-2.5 rounded-full border-2 border-surface ${
                  cited ? "bg-pine" : playing ? "bg-ink" : "bg-line"
                }`}
                aria-hidden
              />
            </button>
            <p className="py-1.5 pl-4 pr-2 leading-relaxed">
              <span className="sr-only">ช่วง {s.id}: </span>
              {s.text}
              {linking && (
                <span className="ml-2 text-xs text-sky opacity-0 group-hover:opacity-100">
                  {linked ? "เอาออกจากหลักฐาน" : "ใช้เป็นหลักฐาน"}
                </span>
              )}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
