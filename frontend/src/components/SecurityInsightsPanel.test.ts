import { describe, expect, it } from "vitest";

import type { SecurityGraphView } from "@/lib/api/client";
import {
  formatConfigDiff,
  formatLatency,
  formatPercent,
  formatProvenanceChain,
  summarizeNonAgentNodes,
} from "./SecurityInsightsPanel";

describe("formatPercent", () => {
  it("rounds a fraction to a whole-number percent", () => {
    expect(formatPercent(0.5)).toBe("50%");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(0.336)).toBe("34%");
  });
});

describe("formatLatency", () => {
  it("returns an em dash for null or undefined", () => {
    expect(formatLatency(null)).toBe("—");
    expect(formatLatency(undefined)).toBe("—");
  });

  it("formats a numeric latency to one decimal with a unit", () => {
    expect(formatLatency(2)).toBe("2.0 ticks");
    expect(formatLatency(2.567)).toBe("2.6 ticks");
  });
});

describe("formatConfigDiff", () => {
  it("returns a placeholder for an empty diff", () => {
    expect(formatConfigDiff({})).toBe("(no change)");
  });

  it("formats a single-key diff", () => {
    expect(formatConfigDiff({ sentinel_count: 2 })).toBe("sentinel_count → 2");
  });

  it("formats a multi-key diff joined by commas", () => {
    expect(formatConfigDiff({ defense_enabled: true, detector_sensitivity: 0.4 })).toBe(
      "defense_enabled → true, detector_sensitivity → 0.4",
    );
  });
});

describe("formatProvenanceChain", () => {
  it("joins a chain with arrows", () => {
    expect(formatProvenanceChain(["agent-000", "agent-004", "agent-012"])).toBe(
      "agent-000 → agent-004 → agent-012",
    );
  });

  it("returns a placeholder for an empty chain", () => {
    expect(formatProvenanceChain([])).toBe("(no provenance chain)");
  });
});

function graphNode(id: string, node_type: string, security_state = "healthy") {
  return { id, node_type, security_state, attrs: {} } as SecurityGraphView["nodes"][number];
}

describe("summarizeNonAgentNodes", () => {
  it("excludes agent nodes", () => {
    const graph: SecurityGraphView = {
      nodes: [graphNode("agent-000", "agent"), graphNode("tool-000", "tool")],
      edges: [],
    };
    expect(summarizeNonAgentNodes(graph).map((s) => s.nodeType)).toEqual(["tool"]);
  });

  it("counts total and compromised nodes per type", () => {
    const graph: SecurityGraphView = {
      nodes: [
        graphNode("sentinel-000", "sentinel", "compromised"),
        graphNode("sentinel-001", "sentinel", "healthy"),
        graphNode("credential-000", "credential", "compromised"),
      ],
      edges: [],
    };
    expect(summarizeNonAgentNodes(graph)).toEqual([
      { nodeType: "credential", total: 1, compromised: 1 },
      { nodeType: "sentinel", total: 2, compromised: 1 },
    ]);
  });

  it("returns an empty array for a graph with only agents", () => {
    const graph: SecurityGraphView = { nodes: [graphNode("agent-000", "agent")], edges: [] };
    expect(summarizeNonAgentNodes(graph)).toEqual([]);
  });

  it("sorts by node type name", () => {
    const graph: SecurityGraphView = {
      nodes: [graphNode("tool-000", "tool"), graphNode("credential-000", "credential")],
      edges: [],
    };
    expect(summarizeNonAgentNodes(graph).map((s) => s.nodeType)).toEqual(["credential", "tool"]);
  });
});
