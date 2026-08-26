import type { components } from "./schema.d.ts";

export type ExperimentConfig = components["schemas"]["ExperimentConfig"];
export type ExperimentSummary = components["schemas"]["ExperimentSummary"];
export type ExperimentListItem = components["schemas"]["ExperimentListItem"];
export type ExperimentListResponse = components["schemas"]["ExperimentListResponse"];
export type ExperimentDetail = components["schemas"]["ExperimentDetail"];
export type EventHistoryResponse = components["schemas"]["EventHistoryResponse"];
export type HistorySnapshotFrame = components["schemas"]["SnapshotFrame"];

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

export async function getExperiment(experimentId: string, signal?: AbortSignal): Promise<ExperimentSummary> {
  const res = await fetch(`${BACKEND_URL}/api/experiments/${experimentId}`, { signal });
  if (!res.ok) {
    throw new Error(`failed to get experiment: ${res.status}`);
  }
  return res.json();
}

async function postControl(
  experimentId: string,
  action: "stop" | "pause" | "resume",
): Promise<ExperimentSummary> {
  const res = await fetch(`${BACKEND_URL}/api/experiments/${experimentId}/${action}`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`failed to ${action} experiment: ${res.status}`);
  }
  return res.json();
}

export function stopExperiment(experimentId: string): Promise<ExperimentSummary> {
  return postControl(experimentId, "stop");
}

export function pauseExperiment(experimentId: string): Promise<ExperimentSummary> {
  return postControl(experimentId, "pause");
}

export function resumeExperiment(experimentId: string): Promise<ExperimentSummary> {
  return postControl(experimentId, "resume");
}

export async function setSpeed(
  experimentId: string,
  multiplier: number,
): Promise<ExperimentSummary> {
  const res = await fetch(`${BACKEND_URL}/api/experiments/${experimentId}/speed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ multiplier }),
  });
  if (!res.ok) {
    throw new Error(`failed to set speed: ${res.status}`);
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

export type ListExperimentsParams = {
  status?: "finished" | "stopped" | "incomplete";
  defenseEnabled?: boolean;
  limit?: number;
  cursor?: string;
};

export async function listExperiments(
  params: ListExperimentsParams = {},
): Promise<ExperimentListResponse> {
  const url = new URL(`${BACKEND_URL}/api/experiments`);
  if (params.status) url.searchParams.set("status", params.status);
  if (params.defenseEnabled !== undefined) {
    url.searchParams.set("defense_enabled", String(params.defenseEnabled));
  }
  if (params.limit !== undefined) url.searchParams.set("limit", String(params.limit));
  if (params.cursor) url.searchParams.set("cursor", params.cursor);

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`failed to list experiments: ${res.status}`);
  }
  return res.json();
}

export async function getExperimentDetail(experimentId: string): Promise<ExperimentDetail> {
  const res = await fetch(`${BACKEND_URL}/api/experiments/${experimentId}/detail`);
  if (!res.ok) {
    throw new Error(`failed to get experiment detail: ${res.status}`);
  }
  return res.json();
}

async function fetchEventPage(
  path: "events" | "incidents",
  experimentId: string,
  sinceSeq: number,
  limit?: number,
): Promise<EventHistoryResponse> {
  const url = new URL(`${BACKEND_URL}/api/experiments/${experimentId}/${path}`);
  url.searchParams.set("since_seq", String(sinceSeq));
  if (limit !== undefined) url.searchParams.set("limit", String(limit));

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`failed to fetch ${path}: ${res.status}`);
  }
  return res.json();
}

export function fetchEventHistory(
  experimentId: string,
  sinceSeq: number,
  limit?: number,
): Promise<EventHistoryResponse> {
  return fetchEventPage("events", experimentId, sinceSeq, limit);
}

export function fetchIncidents(
  experimentId: string,
  sinceSeq: number,
  limit?: number,
): Promise<EventHistoryResponse> {
  return fetchEventPage("incidents", experimentId, sinceSeq, limit);
}

export async function fetchReplaySnapshot(experimentId: string): Promise<HistorySnapshotFrame> {
  const res = await fetch(`${BACKEND_URL}/api/experiments/${experimentId}/replay-snapshot`);
  if (!res.ok) {
    throw new Error(`failed to fetch replay snapshot: ${res.status}`);
  }
  return res.json();
}
