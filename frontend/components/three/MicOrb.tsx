"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useThemeColors } from "@/lib/theme";
import { Stage } from "./Stage";

function Orb({ levelRef, active, colors }: { levelRef: React.RefObject<number>; active: boolean; colors: ReturnType<typeof useThemeColors> }) {
  const mesh = useRef<THREE.Mesh>(null);
  const geo = useMemo(() => new THREE.IcosahedronGeometry(1, 18), []);
  const base = useMemo(() => Float32Array.from(geo.attributes.position.array as Float32Array), [geo]);
  const smooth = useRef(0);

  useFrame(({ clock }) => {
    const m = mesh.current;
    if (!m) return;
    const t = clock.elapsedTime;
    const target = active ? Math.min(1, (levelRef.current ?? 0) * 1.6) : 0;
    smooth.current = THREE.MathUtils.lerp(smooth.current, target, 0.18);
    const amp = 0.04 + smooth.current * 0.32;
    const pos = geo.attributes.position.array as Float32Array;
    for (let i = 0; i < pos.length; i += 3) {
      const x = base[i], y = base[i + 1], z = base[i + 2];
      const n =
        Math.sin(x * 3.1 + t * 2.1) * Math.sin(y * 3.7 + t * 1.7) * Math.sin(z * 2.9 + t * 1.3) +
        0.5 * Math.sin(x * 6.3 - t * 2.9 + y * 2.0);
      const k = 1 + n * amp;
      pos[i] = x * k;
      pos[i + 1] = y * k;
      pos[i + 2] = z * k;
    }
    geo.attributes.position.needsUpdate = true;
    geo.computeVertexNormals();
    m.rotation.y = t * 0.25;
    m.rotation.x = Math.sin(t * 0.3) * 0.2;
    const s = 1 + smooth.current * 0.12;
    m.scale.setScalar(s);
  });

  return (
    <mesh ref={mesh} geometry={geo}>
      <meshPhysicalMaterial
        color={colors.accent}
        roughness={0.25}
        metalness={0.1}
        clearcoat={1}
        clearcoatRoughness={0.2}
        emissive={colors.accent}
        emissiveIntensity={(active ? 0.35 : 0.12) + (colors.dark ? 0.15 : 0)}
        transparent
        opacity={active ? 1 : 0.85}
      />
    </mesh>
  );
}

/** Microphone level made visible: an orb that ripples with the speaker's voice while recording. */
export default function MicOrb({ levelRef, active, className = "" }: { levelRef: React.RefObject<number>; active: boolean; className?: string }) {
  const colors = useThemeColors();
  return (
    <Stage className={className} label={active ? "กำลังอัดเสียง ทรงกลมขยับตามระดับเสียง" : "พร้อมอัดเสียง"} camera={{ position: [0, 0, 3.9], fov: 40 }}>
      <ambientLight intensity={colors.dark ? 0.35 : 0.6} />
      <directionalLight position={[3, 4, 5]} intensity={1.6} />
      <pointLight position={[-3, -2, 2]} intensity={10} color={colors.dark ? "#8b7bff" : "#6a5ae0"} />
      <Orb levelRef={levelRef} active={active} colors={colors} />
    </Stage>
  );
}
