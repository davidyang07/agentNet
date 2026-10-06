// The single place meaning maps to colour. Every badge, meter, table cell,
// KPI tile and graph node resolves its colour through this module, so a
// "compromised" agent, a critical finding and a failing metric can never
// drift into three different reds across three screens.

import type { NodeView } from "@/lib/stream/reducer";

export type Severity = "critical" | "high" | "warn" | "contained" | "ok" | "neutral";

export type SecurityState = NodeView["security_state"];

/** Human copy for a security state — never render the raw enum. */
export const SECURITY_STATE_LABEL: Record<SecurityState, string> = {
  healthy: "Healthy",
  suspicious: "Suspicious",
  compromised: "Compromised",
  quarantined: "Quarantined",
  recovered: "Recovered",
};

export const SECURITY_STATE_SEVERITY: Record<SecurityState, Severity> = {
  healthy: "neutral",
  suspicious: "warn",
  compromised: "critical",
  quarantined: "contained",
  recovered: "ok",
};

/** One-line explanation of what each state means, for legends and tooltips. */
export const SECURITY_STATE_HINT: Record<SecurityState, string> = {
  healthy: "No policy violation observed.",
  suspicious: "Anomalous behaviour flagged, not yet confirmed.",
  compromised: "Attacker-controlled — a policy violation was observed.",
  quarantined: "Isolated by the defense; can no longer propagate.",
  recovered: "Returned to a trusted state after containment.",
};

/** Tailwind classes per severity. Colour goes on marks — dots, meters, graph
 * nodes, chart bands — never on text (DESIGN.md › Colors › Ink), so there is
 * no text-colour map. Canvas and WebGL read the same tokens via lib/theme.ts. */
export const SEVERITY_BG: Record<Severity, string> = {
  critical: "bg-critical",
  high: "bg-high",
  warn: "bg-warn",
  contained: "bg-contained",
  ok: "bg-ok",
  neutral: "bg-neutral",
};

/** Fill for SVG marks (chart bands, legend swatches). */
export const SEVERITY_FILL: Record<Severity, string> = {
  critical: "fill-critical",
  high: "fill-high",
  warn: "fill-warn",
  contained: "fill-contained",
  ok: "fill-ok",
  neutral: "fill-neutral",
};

/** Tinted surface for an area that *is* in a state — an error banner, a
 * finding card. */
export const SEVERITY_SURFACE: Record<Severity, string> = {
  critical: "border-critical-line bg-critical-soft",
  high: "border-high-line bg-high-soft",
  warn: "border-warn-line bg-warn-soft",
  contained: "border-contained-line bg-contained-soft",
  ok: "border-ok-line bg-ok-soft",
  neutral: "border-line bg-raised",
};

/**
 * Severity of a 0..1 fraction where *higher is worse* (compromise fraction,
 * blast radius, attack success rate). Thresholds are presentation-only — the
 * backend makes no such claim — so they are stated once, here, rather than
 * being re-invented per screen.
 */
export function severityForRisk(fraction: number): Severity {
  if (fraction >= 0.5) return "critical";
  if (fraction >= 0.25) return "high";
  if (fraction > 0) return "warn";
  return "ok";
}

/** Severity of a 0..1 fraction where *higher is better* (retained utility,
 * security-plane integrity). */
export function severityForHealth(fraction: number): Severity {
  if (fraction >= 0.9) return "ok";
  if (fraction >= 0.6) return "warn";
  if (fraction >= 0.3) return "high";
  return "critical";
}

export type RunStatus = "idle" | "running" | "paused" | "finished" | "stopped";

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  idle: "No run",
  running: "Running",
  paused: "Paused",
  finished: "Complete",
  stopped: "Stopped",
};

export const RUN_STATUS_SEVERITY: Record<RunStatus, Severity> = {
  idle: "neutral",
  running: "ok",
  paused: "warn",
  finished: "neutral",
  stopped: "neutral",
};
