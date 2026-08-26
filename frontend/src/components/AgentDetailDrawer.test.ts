import { describe, expect, it } from "vitest";
import type { EdgeView, NodeView } from "@/lib/stream/reducer";
import { deriveNeighbors, describeCompromisedBy } from "./AgentDetailDrawer";

function node(overrides: Partial<NodeView> & Pick<NodeView, "id">): NodeView {
  return {
    software_type: "sw-a",
    security_state: "healthy",
    ...overrides,
  };
}

describe("deriveNeighbors", () => {
  it("returns neighbor ids where the node is source, target, or excludes unrelated edges", () => {
    const edges: EdgeView[] = [
      { source: "agent-000", target: "agent-001" }, // node is source
      { source: "agent-002", target: "agent-000" }, // node is target
      { source: "agent-003", target: "agent-004" }, // unrelated
    ];

    expect(deriveNeighbors("agent-000", edges)).toEqual(["agent-001", "agent-002"]);
  });
});

describe("describeCompromisedBy", () => {
  it("returns the unknown qualifier for a compromised node with null compromised_by", () => {
    const n = node({ id: "agent-000", security_state: "compromised", compromised_by: null });
    expect(describeCompromisedBy(n)).toBe("unknown (before this session's connection)");
  });

  it("returns the unknown qualifier for a quarantined node with null compromised_by", () => {
    const n = node({ id: "agent-000", security_state: "quarantined", compromised_by: null });
    expect(describeCompromisedBy(n)).toBe("unknown (before this session's connection)");
  });

  it("returns the actual agent id when compromised_by is non-null", () => {
    const n = node({
      id: "agent-000",
      security_state: "compromised",
      compromised_by: "agent-002",
    });
    expect(describeCompromisedBy(n)).toBe("agent-002");
  });

  it("returns an em dash for a healthy node with null compromised_by", () => {
    const n = node({ id: "agent-000", security_state: "healthy", compromised_by: null });
    expect(describeCompromisedBy(n)).toBe("—");
  });
});
