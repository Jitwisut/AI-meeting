"use client";

import { useEffect, useState } from "react";

export type ThemePref = "system" | "light" | "dark";

export function readThemePref(): ThemePref {
  try {
    const t = localStorage.getItem("theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function applyThemePref(pref: ThemePref) {
  const root = document.documentElement;
  if (pref === "system") delete root.dataset.theme;
  else root.dataset.theme = pref;
  try {
    if (pref === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", pref);
  } catch {
    /* storage unavailable: preference lasts for this page only */
  }
  window.dispatchEvent(new Event("themechange"));
}

/** Resolved colours from CSS tokens, re-read when the theme or OS appearance changes (for WebGL). */
export function useThemeColors() {
  const read = () => {
    if (typeof window === "undefined") return { accent: "#0f8a6c", ink: "#1c1d1f", faint: "#8b9099", sky: "#0062cc", amber: "#a85f00", dark: false };
    const cs = getComputedStyle(document.documentElement);
    const v = (n: string) => cs.getPropertyValue(n).trim();
    return { accent: v("--pine"), ink: v("--ink"), faint: v("--ink-faint"), sky: v("--sky"), amber: v("--amber"), dark: cs.colorScheme === "dark" };
  };
  const [colors, setColors] = useState(read);
  useEffect(() => {
    const update = () => setColors(read());
    update();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    window.addEventListener("themechange", update);
    return () => {
      mq.removeEventListener("change", update);
      window.removeEventListener("themechange", update);
    };
  }, []);
  return colors;
}

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const h = () => setReduced(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, []);
  return reduced;
}
