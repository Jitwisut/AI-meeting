"use client";

import { type ThreeEvent, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { fmtMs } from "@/lib/format";
import { useThemeColors } from "@/lib/theme";
import { Stage } from "./Stage";

export interface WaveMarker {
  ms: number;
  segmentId: number;
}

const WIDTH = 10;

function Bars({
  peaks,
  durationMs,
  currentMs,
  markers,
  onSeek,
  colors,
  onHover,
}: {
  peaks: number[];
  durationMs: number;
  currentMs: number;
  markers: WaveMarker[];
  onSeek: (ms: number) => void;
  colors: ReturnType<typeof useThemeColors>;
  onHover: (ms: number | null) => void;
}) {
  const n = peaks.length;
  const bars = useRef<THREE.InstancedMesh>(null);
  const mirror = useRef<THREE.InstancedMesh>(null);
  const head = useRef<THREE.Mesh>(null);
  const pins = useRef<THREE.Group>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const grow = useRef(0);
  const hovered = useRef<number | null>(null);
  const lastLit = useRef(-2);
  const step = WIDTH / n;

  const played = useMemo(() => new THREE.Color(colors.accent), [colors.accent]);
  const rest = useMemo(() => new THREE.Color(colors.faint), [colors.faint]);
  const hot = useMemo(() => new THREE.Color(colors.sky), [colors.sky]);

  useLayoutEffect(() => {
    lastLit.current = -2; // force recolour on theme change
  }, [played, rest]);

  // In "demand" mode (off-screen or reduced motion) frames only render when invalidated.
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    invalidate();
  }, [invalidate, currentMs, peaks, played, markers]);

  const xOf = (ms: number) => (Math.min(1, Math.max(0, ms / Math.max(1, durationMs))) - 0.5) * WIDTH;

  useFrame((state, dt) => {
    const b = bars.current;
    const m = mirror.current;
    if (!b || !m) return;
    grow.current = state.frameloop === "demand" ? 1 : Math.min(1, grow.current + dt * 1.4);
    const e = 1 - (1 - grow.current) ** 3;
    if (grow.current < 1 || lastLit.current === -2) {
      for (let i = 0; i < n; i++) {
        const h = (0.05 + peaks[i] * 1.5) * e;
        dummy.position.set((i + 0.5) * step - WIDTH / 2, h / 2, 0);
        dummy.scale.set(1, h, 1);
        dummy.updateMatrix();
        b.setMatrixAt(i, dummy.matrix);
        dummy.position.y = -h / 2 - 0.02;
        dummy.updateMatrix();
        m.setMatrixAt(i, dummy.matrix);
      }
      b.instanceMatrix.needsUpdate = true;
      m.instanceMatrix.needsUpdate = true;
    }
    const lit = Math.floor((currentMs / Math.max(1, durationMs)) * n);
    if (lit !== lastLit.current || hovered.current !== null) {
      for (let i = 0; i < n; i++) {
        const c = i === hovered.current ? hot : i < lit ? played : rest;
        b.setColorAt(i, c);
        m.setColorAt(i, c);
      }
      if (b.instanceColor) b.instanceColor.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
      lastLit.current = lit;
    }
    if (head.current) head.current.position.x = THREE.MathUtils.lerp(head.current.position.x, xOf(currentMs), 0.25);
    if (pins.current) {
      const t = state.clock.elapsedTime;
      pins.current.children.forEach((c, i) => {
        c.position.y = 1.85 + Math.sin(t * 2 + i) * 0.05;
      });
    }
    state.camera.position.x = THREE.MathUtils.lerp(state.camera.position.x, state.pointer.x * 0.6, 0.03);
    state.camera.lookAt(0, 0.45, 0);
  });

  const toMs = (e: ThreeEvent<PointerEvent | MouseEvent>) =>
    e.instanceId == null ? null : ((e.instanceId + 0.5) / n) * durationMs;

  return (
    <group rotation={[0.08, 0, 0]}>
      <instancedMesh
        ref={bars}
        args={[undefined, undefined, n]}
        onClick={(e) => {
          e.stopPropagation();
          const ms = toMs(e);
          if (ms != null) onSeek(ms);
        }}
        onPointerMove={(e) => {
          e.stopPropagation();
          hovered.current = e.instanceId ?? null;
          onHover(toMs(e));
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          hovered.current = null;
          lastLit.current = -1;
          onHover(null);
          document.body.style.cursor = "";
        }}
      >
        <boxGeometry args={[step * 0.62, 1, 0.22]} />
        <meshStandardMaterial roughness={0.35} metalness={0.1} emissive={colors.accent} emissiveIntensity={colors.dark ? 0.12 : 0} />
      </instancedMesh>
      <instancedMesh ref={mirror} args={[undefined, undefined, n]}>
        <boxGeometry args={[step * 0.62, 1, 0.22]} />
        <meshStandardMaterial transparent opacity={colors.dark ? 0.14 : 0.1} roughness={0.6} />
      </instancedMesh>
      <mesh ref={head} position={[xOf(currentMs), 0.9, 0.16]}>
        <boxGeometry args={[0.025, 2.1, 0.025]} />
        <meshBasicMaterial color={colors.ink} />
      </mesh>
      <group ref={pins}>
        {markers.map((mk) => (
          <mesh
            key={mk.segmentId}
            position={[xOf(mk.ms), 1.85, 0]}
            onClick={(e) => {
              e.stopPropagation();
              onSeek(mk.ms);
            }}
          >
            <sphereGeometry args={[0.07, 20, 20]} />
            <meshStandardMaterial color={colors.amber} emissive={colors.amber} emissiveIntensity={0.6} />
          </mesh>
        ))}
      </group>
    </group>
  );
}

/** Interactive 3D waveform of the meeting: played part lit, evidence pins float above, click to seek. */
export default function Waveform3D({
  peaks,
  durationMs,
  currentMs,
  markers,
  onSeek,
}: {
  peaks: number[];
  durationMs: number;
  currentMs: number;
  markers: WaveMarker[];
  onSeek: (ms: number) => void;
}) {
  const colors = useThemeColors();
  const [hoverMs, setHoverMs] = useState<number | null>(null);
  return (
    <div className="relative">
      <Stage
        className="h-40 w-full"
        label="คลื่นเสียงสามมิติของการประชุม คลิกเพื่อเล่นจากตำแหน่งนั้น"
        camera={{ position: [0, 1.25, 5.4], fov: 40 }}
        fallback={null}
      >
        <ambientLight intensity={colors.dark ? 0.5 : 0.8} />
        <directionalLight position={[2, 5, 6]} intensity={1.5} />
        <Bars
          peaks={peaks}
          durationMs={durationMs}
          currentMs={currentMs}
          markers={markers}
          onSeek={onSeek}
          colors={colors}
          onHover={setHoverMs}
        />
      </Stage>
      {hoverMs != null && (
        <span className="tnum pointer-events-none absolute right-3 top-2 rounded-full bg-surface px-2 py-0.5 text-xs shadow-[0_0_0_0.5px_var(--line)]">
          {fmtMs(hoverMs)}
        </span>
      )}
      <span className="pointer-events-none absolute bottom-1.5 left-3 flex items-center gap-1.5 text-[11px] text-ink-faint">
        <span className="h-2 w-2 rounded-full bg-amber" /> หลักฐานที่ AI อ้างอิง
      </span>
    </div>
  );
}
