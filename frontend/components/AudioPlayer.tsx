"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { errorText, useApi } from "@/lib/api";

export interface AudioHandle {
  seek: (ms: number) => void;
}

/** Fetches audio with the auth header (an <audio src> cannot send one) and plays it from a blob URL. */
export const AudioPlayer = forwardRef<AudioHandle, { meetingId: string; available: boolean; onTime: (ms: number) => void }>(
  function AudioPlayer({ meetingId, available, onTime }, ref) {
    const { blob } = useApi();
    const audio = useRef<HTMLAudioElement>(null);
    const [url, setUrl] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
      if (!available) return;
      let objectUrl: string | null = null;
      blob(`/api/meetings/${meetingId}/audio`)
        .then((b) => {
          objectUrl = URL.createObjectURL(b);
          setUrl(objectUrl);
        })
        .catch((e) => setError(errorText(e)));
      return () => {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
      };
    }, [blob, meetingId, available]);

    useImperativeHandle(ref, () => ({
      seek(ms: number) {
        if (!audio.current) return;
        audio.current.currentTime = ms / 1000;
        void audio.current.play().catch(() => undefined);
      },
    }));

    if (!available || error) {
      return (
        <p className="rounded-[10px] bg-hover px-3 py-2 text-sm text-ink-faint">
          {error ?? "ไฟล์เสียงชั่วคราวถูกลบตามนโยบายการเก็บรักษาแล้ว ยังอ่านบทถอดเสียงได้ตามปกติ"}
        </p>
      );
    }
    return (
      <audio
        ref={audio}
        controls
        src={url ?? undefined}
        className="w-full"
        onTimeUpdate={(e) => onTime(e.currentTarget.currentTime * 1000)}
        aria-label="เสียงการประชุม"
      />
    );
  },
);
