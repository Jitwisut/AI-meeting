"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { fmtMs } from "@/lib/format";
import { Alert, Button } from "./ui";

const MicOrb = dynamic(() => import("./three/MicOrb"), { ssr: false });

function pickMime(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return candidates.find((c) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(c)) ?? "";
}

/** Browser recording with MediaRecorder. Output is WebM/Opus or MP4 (Safari); the backend converts it. */
export function Recorder({ disabled, onRecorded }: { disabled: boolean; onRecorded: (file: File | null) => void }) {
  const [state, setState] = useState<"idle" | "recording" | "done">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const level = useRef(0);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const ctx = useRef<AudioContext | null>(null);
  const raf = useRef<number | null>(null);
  const started = useRef(0);

  useEffect(
    () => () => {
      stream.current?.getTracks().forEach((t) => t.stop());
      if (raf.current) cancelAnimationFrame(raf.current);
      void ctx.current?.close();
    },
    [],
  );
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  async function start() {
    setError(null);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      stream.current = s;
      const mime = pickMime();
      const r = new MediaRecorder(s, mime ? { mimeType: mime } : undefined);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      r.onstop = () => {
        const type = r.mimeType || mime || "audio/webm";
        const blob = new Blob(chunks, { type });
        const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        const file = new File([blob], `recording-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.${ext}`, { type });
        setUrl(URL.createObjectURL(blob));
        onRecorded(file);
        s.getTracks().forEach((t) => t.stop());
        if (raf.current) cancelAnimationFrame(raf.current);
        void ctx.current?.close();
        level.current = 0;
      };
      ctx.current = new AudioContext();
      const analyser = ctx.current.createAnalyser();
      analyser.fftSize = 512;
      ctx.current.createMediaStreamSource(s).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      let lastTick = 0;
      const loop = (now: number) => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += (v - 128) ** 2;
        level.current = Math.sqrt(sum / buf.length) / 64; // read by the 3D orb every frame
        if (now - lastTick > 250) {
          setElapsed(Date.now() - started.current); // timer re-renders only 4×/s
          lastTick = now;
        }
        raf.current = requestAnimationFrame(loop);
      };
      started.current = Date.now();
      r.start(1000);
      rec.current = r;
      setState("recording");
      onRecorded(null);
      raf.current = requestAnimationFrame(loop);
    } catch {
      setError("เปิดไมโครโฟนไม่ได้ กรุณาอนุญาตการใช้ไมโครโฟนในเบราว์เซอร์ แล้วลองใหม่");
    }
  }

  function stop() {
    rec.current?.stop();
    setState("done");
  }

  const recording = state === "recording";

  return (
    <div>
      <div className="relative overflow-hidden rounded-[18px] bg-[radial-gradient(circle_at_50%_45%,var(--pine-wash),transparent_65%)] shadow-[inset_0_0_0_0.5px_var(--line)]">
        <MicOrb levelRef={level} active={recording} className="mx-auto h-60 w-full max-w-sm" />
        <div className="flex flex-col items-center gap-3 pb-6">
          <span className={`tnum text-3xl font-semibold tracking-tight ${recording ? "text-ink" : "text-ink-faint"}`}>
            {recording && <span className="pulse-dot mr-2 inline-block h-2.5 w-2.5 rounded-full bg-rust align-middle" />}
            {fmtMs(elapsed)}
          </span>
          {recording ? (
            <Button variant="danger" onClick={stop} className="min-w-36 rounded-full">
              หยุดอัด
            </Button>
          ) : (
            <Button variant="primary" onClick={start} disabled={disabled} className="min-w-36 rounded-full">
              {state === "done" ? "อัดใหม่" : "เริ่มอัดเสียง"}
            </Button>
          )}
        </div>
      </div>
      {disabled && state === "idle" && (
        <p className="mt-2 text-center text-xs text-ink-faint">เปิดสวิตช์ยืนยันการแจ้งผู้ร่วมประชุมด้านบนก่อนเริ่มอัดเสียง</p>
      )}
      {error && <Alert className="mt-3">{error}</Alert>}
      {url && state === "done" && <audio controls src={url} className="mt-3 w-full" />}
    </div>
  );
}
