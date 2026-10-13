"use client";

import { useFrame } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useThemeColors } from "@/lib/theme";
import { Stage } from "./Stage";

const COLS = 56;
const ROWS = 11;
const GAP = 0.14;

/** A slowly breathing 3D "voice ribbon": the dashboard's signature. */
function Ribbon({ accent, second, dark }: { accent: string; second: string; dark: boolean }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const group = useRef<THREE.Group>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    const a = new THREE.Color(accent);
    const b = new THREE.Color(second);
    const c = new THREE.Color();
    for (let i = 0; i < COLS; i++)
      for (let j = 0; j < ROWS; j++) {
        c.copy(a).lerp(b, i / (COLS - 1)).offsetHSL(0, 0, (j / ROWS - 0.5) * 0.12);
        m.setColorAt(i * ROWS + j, c);
      }
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, [accent, second]);

  useFrame(({ clock, pointer }) => {
    const m = mesh.current;
    const g = group.current;
    if (!m || !g) return;
    const t = clock.elapsedTime;
    for (let i = 0; i < COLS; i++) {
      const u = i / (COLS - 1);
      const env = Math.sin(u * Math.PI) ** 1.4;
      for (let j = 0; j < ROWS; j++) {
        const depth = 1 - Math.abs(j - (ROWS - 1) / 2) / ((ROWS - 1) / 2);
        const wave =
          0.55 + 0.45 * Math.sin(i * 0.31 + t * 1.5 + j * 0.42) * Math.cos(i * 0.07 - t * 0.55);
        const h = 0.04 + env * wave * (0.35 + 0.65 * depth) * 1.5;
        dummy.position.set((i - COLS / 2) * GAP, h / 2, (j - ROWS / 2) * GAP);
        dummy.scale.set(1, h, 1);
        dummy.updateMatrix();
        m.setMatrixAt(i * ROWS + j, dummy.matrix);
      }
    }
    m.instanceMatrix.needsUpdate = true;
    g.rotation.y = THREE.MathUtils.lerp(g.rotation.y, -0.35 + pointer.x * 0.25 + Math.sin(t * 0.12) * 0.12, 0.04);
    g.rotation.x = THREE.MathUtils.lerp(g.rotation.x, 0.32 - pointer.y * 0.12, 0.04);
  });

  return (
    <group ref={group} position={[0, -0.45, 0]}>
      <instancedMesh ref={mesh} args={[undefined, undefined, COLS * ROWS]}>
        <boxGeometry args={[0.1, 1, 0.1]} />
        <meshStandardMaterial
          roughness={0.32}
          metalness={0.15}
          emissive={accent}
          emissiveIntensity={dark ? 0.22 : 0.04}
        />
      </instancedMesh>
    </group>
  );
}

export default function WaveHero({ className = "" }: { className?: string }) {
  const colors = useThemeColors();
  return (
    <Stage
      className={className}
      label="ภาพสามมิติของคลื่นเสียงการประชุม"
      camera={{ position: [0, 2.4, 8.8], fov: 34 }}
      fallback={<div className="h-full w-full bg-[radial-gradient(closest-side,var(--pine-wash),transparent)]" />}
    >
      <ambientLight intensity={colors.dark ? 0.45 : 0.75} />
      <directionalLight position={[3, 6, 5]} intensity={colors.dark ? 1.4 : 1.6} />
      <pointLight position={[-4, 2, 2]} intensity={colors.dark ? 18 : 8} color={colors.accent} />
      <Ribbon accent={colors.accent} second={colors.dark ? "#8b7bff" : "#6a5ae0"} dark={colors.dark} />
    </Stage>
  );
}
