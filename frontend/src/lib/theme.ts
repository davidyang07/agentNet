// Design tokens for the renderers that cannot take a CSS class: Sigma's WebGL
// program and the graph's 2D canvas overlay need literal colour strings and
// font families. They read the custom properties globals.css declares (from
// DESIGN.md), so a token's value is only ever written in one place.

import type { Severity } from "@/lib/severity";

const cache = new Map<string, string>();

/** Resolved value of a `--*` custom property on <html>. Empty during SSR. */
export function token(name: `--${string}`): string {
  const hit = cache.get(name);
  if (hit !== undefined) return hit;
  if (typeof document === "undefined") return "";
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  // Only cache a resolved value: before the stylesheet applies, the property
  // reads empty and must be asked again.
  if (value) cache.set(name, value);
  return value;
}

export function severityColor(severity: Severity): string {
  return token(`--color-${severity}`);
}

function channels(hex: string): [number, number, number] | null {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match) return null;
  const value = parseInt(match[1], 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

/** `hex` at `alpha` opacity, as an rgba() string. */
export function withAlpha(hex: string, alpha: number): string {
  const rgb = channels(hex);
  return rgb ? `rgba(${rgb.join(", ")}, ${alpha})` : hex;
}

/** `amount` (0..1) of `hex` mixed into `base`, in sRGB — the same mix the
 * `-soft`/`-line` tokens use. */
export function mix(hex: string, base: string, amount: number): string {
  const a = channels(hex);
  const b = channels(base);
  if (!a || !b) return hex;
  const out = a.map((c, i) => Math.round(c * amount + b[i] * (1 - amount)));
  return `#${out.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}
