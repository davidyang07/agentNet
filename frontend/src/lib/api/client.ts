import type { components } from "./schema.d.ts";

export type ExperimentConfig = components["schemas"]["ExperimentConfig"];
export type ExperimentSummary = components["schemas"]["ExperimentSummary"];

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const BACKEND_WS_URL = process.env.NEXT_PUBLIC_BACKEND_WS_URL ?? "ws://localhost:8000";

export async function createExperiment(config: ExperimentConfig): Promise<ExperimentSummary> {
  const res = await fetch(`${BACKEND_URL}/api/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    throw new Error(`failed to create experiment: ${res.status}`);
  }
  return res.json();
}

export function backendWsUrl(experimentId: string, sinceSeq?: number): string {
  const url = new URL(`${BACKEND_WS_URL}/api/experiments/${experimentId}/stream`);
  if (sinceSeq !== undefined) {
    url.searchParams.set("since_seq", String(sinceSeq));
  }
  return url.toString();
}
