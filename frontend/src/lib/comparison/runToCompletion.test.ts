import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExperimentConfig } from "@/lib/api/client";
import { reduce, initialGraphState, selectMetrics, type StreamFrame } from "@/lib/stream/reducer";

import { runExperimentToCompletion } from "./runToCompletion";

const CONFIG: ExperimentConfig = {
  seed: 42,
  node_count: 60,
  edge_density: 2,
  software_type_count: 3,
  p_same: 0.15,
  p_cross: 0.03,
  max_ticks: 200,
  detector_sensitivity: 0.2,
  defense_enabled: true,
  initial_compromised: "highest_degree",
};

const EXPERIMENT_ID = "exp-1";

function okResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function summary(status: "running" | "paused" | "finished" | "stopped") {
  return { experiment_id: EXPERIMENT_ID, status, sim_tick: 0, config: CONFIG };
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onmessage: ((ev: { data: string }) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
  }

  push(frame: StreamFrame) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

const snapshotFrame: StreamFrame = {
  type: "snapshot",
  experiment_id: EXPERIMENT_ID,
  last_seq: -1,
  sim_tick: 0,
  status: "running",
  nodes: [
    { id: "a", software_type: "x", security_state: "healthy" },
    { id: "b", software_type: "y", security_state: "healthy" },
  ],
  edges: [{ source: "a", target: "b" }],
};

const compromiseFrame: StreamFrame = {
  type: "event",
  event: {
    sim_tick: 1,
    event_type: "COMPROMISE_SUCCEEDED",
    source_agent_id: "a",
    target_agent_id: "b",
    event_id: "11111111-1111-1111-1111-111111111111",
    seq: 0,
    schema_version: 1,
    experiment_id: EXPERIMENT_ID,
    wall_time: "2026-08-25T00:00:00Z",
  },
};

const otherEventFrame: StreamFrame = {
  type: "event",
  event: {
    sim_tick: 2,
    event_type: "ANOMALY_DETECTED",
    agent_id: "b",
    event_id: "22222222-2222-2222-2222-222222222222",
    seq: 1,
    schema_version: 1,
    experiment_id: EXPERIMENT_ID,
    wall_time: "2026-08-25T00:00:01Z",
  },
};

describe("runExperimentToCompletion", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  function callsMatching(method: string, pathSuffix: string) {
    return fetchMock.mock.calls.filter(([url, init]) => {
      const m = (init as RequestInit | undefined)?.method ?? "GET";
      return m === method && String(url).endsWith(pathSuffix);
    });
  }

  it("resolves with metrics computed by the real reduce() once status polling sees a terminal state", async () => {
    let getExperimentCalls = 0;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (method === "POST" && String(url).endsWith("/api/experiments")) {
        return okResponse(summary("running"));
      }
      if (method === "GET" && String(url).endsWith(`/api/experiments/${EXPERIMENT_ID}`)) {
        getExperimentCalls += 1;
        return okResponse(getExperimentCalls === 1 ? summary("running") : summary("finished"));
      }
      if (method === "POST" && String(url).endsWith(`/api/experiments/${EXPERIMENT_ID}/stop`)) {
        return okResponse(summary("stopped"));
      }
      throw new Error(`unexpected fetch call: ${method} ${url}`);
    });

    const resultPromise = runExperimentToCompletion(CONFIG);

    // Let createExperiment's microtask resolve and the WS get constructed.
    await vi.advanceTimersByTimeAsync(0);
    expect(FakeWebSocket.instances).toHaveLength(1);
    const ws = FakeWebSocket.instances[0];
    expect(ws.url).toContain(EXPERIMENT_ID);

    ws.push(snapshotFrame);
    ws.push(compromiseFrame);
    ws.push(otherEventFrame);

    // First poll: still running.
    await vi.advanceTimersByTimeAsync(1000);
    expect(callsMatching("GET", `/api/experiments/${EXPERIMENT_ID}`)).toHaveLength(1);

    // Second poll: finished -> resolves.
    await vi.advanceTimersByTimeAsync(1000);

    const result = await resultPromise;

    let expectedState = initialGraphState;
    expectedState = reduce(expectedState, snapshotFrame);
    expectedState = reduce(expectedState, compromiseFrame);
    expectedState = reduce(expectedState, otherEventFrame);
    const expectedMetrics = selectMetrics(expectedState);

    expect(result.experimentId).toBe(EXPERIMENT_ID);
    expect(result.metrics).toEqual(expectedMetrics);
    expect(result.metrics.newCompromises).toBe(1);
    expect(result.metrics.compromised).toBe(1);

    const stopCalls = callsMatching("POST", `/api/experiments/${EXPERIMENT_ID}/stop`);
    expect(stopCalls).toHaveLength(1);
    expect(ws.closed).toBe(true);
  });

  it("rejects when the AbortSignal fires, and still best-effort stops the experiment and closes the WS", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (method === "POST" && String(url).endsWith("/api/experiments")) {
        return okResponse(summary("running"));
      }
      if (method === "GET" && String(url).endsWith(`/api/experiments/${EXPERIMENT_ID}`)) {
        return okResponse(summary("running"));
      }
      if (method === "POST" && String(url).endsWith(`/api/experiments/${EXPERIMENT_ID}/stop`)) {
        return okResponse(summary("stopped"));
      }
      throw new Error(`unexpected fetch call: ${method} ${url}`);
    });

    const controller = new AbortController();
    const resultPromise = runExperimentToCompletion(CONFIG, { signal: controller.signal });

    await vi.advanceTimersByTimeAsync(0);
    expect(FakeWebSocket.instances).toHaveLength(1);
    const ws = FakeWebSocket.instances[0];

    const assertion = expect(resultPromise).rejects.toMatchObject({ name: "AbortError" });

    controller.abort();

    await assertion;
    await vi.advanceTimersByTimeAsync(0);

    const stopCalls = callsMatching("POST", `/api/experiments/${EXPERIMENT_ID}/stop`);
    expect(stopCalls).toHaveLength(1);
    expect(ws.closed).toBe(true);
  });

  it("rejects immediately (still stopping and closing) when the signal is already aborted before the run starts", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (method === "POST" && String(url).endsWith("/api/experiments")) {
        return okResponse(summary("running"));
      }
      if (method === "GET" && String(url).endsWith(`/api/experiments/${EXPERIMENT_ID}`)) {
        return okResponse(summary("running"));
      }
      if (method === "POST" && String(url).endsWith(`/api/experiments/${EXPERIMENT_ID}/stop`)) {
        return okResponse(summary("stopped"));
      }
      throw new Error(`unexpected fetch call: ${method} ${url}`);
    });

    const controller = new AbortController();
    controller.abort();

    const resultPromise = runExperimentToCompletion(CONFIG, { signal: controller.signal });

    await expect(resultPromise).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(0);

    const stopCalls = callsMatching("POST", `/api/experiments/${EXPERIMENT_ID}/stop`);
    expect(stopCalls).toHaveLength(1);
    expect(FakeWebSocket.instances[0]?.closed).toBe(true);
  });
});
