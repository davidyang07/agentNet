import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadHistoricalArm } from "./loadHistoricalArm";
import type { Event, SnapshotFrame } from "@/lib/stream/reducer";

const EXPERIMENT_ID = "exp-hist-1";

function okResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

const snapshotFrame: SnapshotFrame = {
  type: "snapshot",
  experiment_id: EXPERIMENT_ID,
  last_seq: 1,
  sim_tick: 0,
  status: "finished",
  nodes: [
    { id: "a", software_type: "sw-a", security_state: "compromised", tick_compromised: 0 },
    { id: "b", software_type: "sw-a", security_state: "healthy" },
  ],
  edges: [{ source: "a", target: "b" }],
};

function compromiseEvent(seq: number): Event {
  return {
    event_id: `event-${seq}`,
    seq,
    sim_tick: 1,
    schema_version: 1,
    experiment_id: EXPERIMENT_ID,
    wall_time: "2026-01-01T00:00:00Z",
    event_type: "COMPROMISE_SUCCEEDED",
    source_agent_id: "a",
    target_agent_id: "b",
    metadata: {},
  };
}

describe("loadHistoricalArm", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("folds the full persisted event log through reduce() and returns selectMetrics() output", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      const u = String(url);
      if (u.endsWith("/detail")) return okResponse({ is_complete: true });
      if (u.endsWith("/replay-snapshot")) return okResponse(snapshotFrame);
      if (u.includes("/events")) return okResponse({ events: [compromiseEvent(2)], next_seq: null });
      throw new Error(`unexpected fetch: ${u}`);
    });

    const result = await loadHistoricalArm(EXPERIMENT_ID);

    expect(result.experimentId).toBe(EXPERIMENT_ID);
    expect(result.incomplete).toBe(false);
    // Seed compromise seeded from the snapshot (1) + one follow-up event (1).
    expect(result.metrics.newCompromises).toBe(2);
    expect(result.metrics.compromised).toBe(2);
  });

  it("reports incomplete=true for a run whose persisted record never proved a gapless seq range", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      const u = String(url);
      if (u.endsWith("/detail")) return okResponse({ is_complete: false });
      if (u.endsWith("/replay-snapshot")) return okResponse(snapshotFrame);
      if (u.includes("/events")) return okResponse({ events: [], next_seq: null });
      throw new Error(`unexpected fetch: ${u}`);
    });

    const result = await loadHistoricalArm(EXPERIMENT_ID);
    expect(result.incomplete).toBe(true);
  });
});
