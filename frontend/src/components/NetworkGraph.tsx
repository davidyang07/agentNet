"use client";

import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { useEffect, useRef } from "react";
import Sigma from "sigma";

import type { GraphState } from "@/lib/stream/reducer";

// The only place security state maps to appearance (SPEC §4).
const COLORS: Record<string, string> = {
  healthy: "#64748b", // slate
  suspicious: "#f59e0b", // amber
  compromised: "#ef4444", // red
  quarantined: "#3b82f6", // blue
  recovered: "#22c55e", // green
};

const FORCE_ATLAS2_ITERATIONS = 100;

export function NetworkGraph({
  state,
  onNodeClick,
}: {
  state: GraphState;
  onNodeClick?: (agentId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const builtForRef = useRef<string | null>(null);

  // Build the Graphology graph once per experiment, from the first
  // snapshot, and run layout once so positions stay stable across the run.
  useEffect(() => {
    if (!containerRef.current) return;
    if (!state.experimentId) return;
    if (state.nodes.size === 0) return;
    if (builtForRef.current === state.experimentId) return;

    sigmaRef.current?.kill();

    const graph = new Graph();
    for (const node of state.nodes.values()) {
      graph.addNode(node.id, {
        x: Math.random(),
        y: Math.random(),
        size: 4,
        label: node.id,
        color: COLORS[node.security_state] ?? COLORS.healthy,
      });
    }
    for (const edge of state.edges) {
      if (!graph.hasEdge(edge.source, edge.target)) {
        graph.addEdge(edge.source, edge.target, { size: 1, color: "#334155" });
      }
    }

    forceAtlas2.assign(graph, { iterations: FORCE_ATLAS2_ITERATIONS });

    graphRef.current = graph;
    sigmaRef.current = new Sigma(graph, containerRef.current);
    sigmaRef.current.on("clickNode", ({ node }) => onNodeClick?.(node));
    builtForRef.current = state.experimentId;
    // onNodeClick is intentionally omitted below: including it would rebuild the graph
    // and rerun layout on every parent render. sigmaRef.current?.kill() (before rebuild,
    // and on unmount) always unbinds the listener before any new one is attached.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.experimentId, state.nodes, state.edges]);

  // Recolor nodes as their security_state changes — never rebuilds the
  // graph (SPEC §4: "not React Flow", setNodeAttribute only).
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    for (const node of state.nodes.values()) {
      if (graph.hasNode(node.id)) {
        graph.setNodeAttribute(node.id, "color", COLORS[node.security_state] ?? COLORS.healthy);
      }
    }
  }, [state.nodes]);

  useEffect(() => {
    return () => {
      sigmaRef.current?.kill();
      sigmaRef.current = null;
    };
  }, []);

  return <div ref={containerRef} className="h-full w-full" />;
}
