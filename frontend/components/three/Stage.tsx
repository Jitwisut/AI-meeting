"use client";

import { Canvas, type CanvasProps } from "@react-three/fiber";
import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/theme";

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * Canvas wrapper: renders only while on screen, stops animating for reduced-motion users,
 * caps pixel ratio, and shows `fallback` when WebGL is unavailable.
 */
export function Stage({
  children,
  className = "",
  fallback = null,
  camera,
  label,
  ...rest
}: Omit<CanvasProps, "children"> & {
  children: React.ReactNode;
  className?: string;
  fallback?: React.ReactNode;
  label: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [supported, setSupported] = useState<boolean | null>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    setSupported(webglAvailable());
    const el = host.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { rootMargin: "80px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={host} className={className} role="img" aria-label={label}>
      {supported === false
        ? fallback
        : supported && (
            <Canvas
              dpr={[1, 1.75]}
              gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
              camera={camera ?? { position: [0, 2, 7], fov: 35 }}
              frameloop={visible && !reduced ? "always" : "demand"}
              {...rest}
            >
              {children}
            </Canvas>
          )}
    </div>
  );
}
