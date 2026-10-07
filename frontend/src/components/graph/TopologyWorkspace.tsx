"use client";

import dynamic from "next/dynamic";
import { useMemo, useState, type ReactNode } from "react";

import { AttackPathFinder } from "@/components/graph/AttackPathFinder";
import { GraphLegend, LayerToggles } from "@/components/graph/GraphLegend";
import { NodeInspector } from "@/components/graph/NodeInspector";
import { Button, SegmentedControl } from "@/components/ui/Button";
import { IconLayers, IconTarget } from "@/components/ui/icons";
import { Meter } from "@/components/ui/Metric";
import { EmptyState, Spinner } from "@/components/ui/States";
import { cn } from "@/lib/cn";
import type { BlastRadiusResponse, SecurityGraphView } from "@/lib/api/client";
import { buildTopologyModel, edgeLayer } from "@/lib/graph/model";
import { formatPercent } from "@/lib/format";
import type { InsightsMode } from "@/lib/security/useSecurityInsights";
import type { GraphState } from "@/lib/stream/reducer";
import type { EdgeLayer } from "@/lib/vocabulary";

// Sigma touches WebGL2RenderingContext at module load — it can only ever run
// in the browser, so it must be excluded from server-side rendering.
const TopologyGraph = dynamic(
  () => import("@/components/graph/TopologyGraph").then((mod) => mod.TopologyGraph),
  {
    ssr: false,
    loading: () => (
      <div className="flex size-full items-center justify-center gap-2 text-xs text-fg-muted">
        <Spinner /> Loading renderer…
      </div>
    ),
  },
);

const ALL_LAYERS: EdgeLayer[] = ["mesh", "access", "oversight"];
// Oversight is off by default: a single quarantine-authority control node has
// an edge to every agent, so leaving that layer on renders a starburst that
// buries the communication topology underneath it.
const INITIAL_LAYERS: EdgeLayer[] = ["mesh", "access"];

type RailTab = "live" | "investigate";

const RAIL_TABS: ReadonlyArray<{ value: RailTab; label: string }> = [
  { value: "live", label: "Live events" },
  { value: "investigate", label: "Investigate" },
];

/**
 * The investigation surface, shared by the live view and replay: the typed
 * security graph, an inspector for whatever is selected, and the two analyses
 * that are about *reachability* rather than counts — attack paths and blast
 * radius.
 *
 * The live view also passes `belowGraph` (the outbreak curve) and `liveRail`
 * (the event stream), which turns the side panel into two tabs. Selecting a
 * node always opens its inspector there.
 */
export function TopologyWorkspace({
  experimentId,
  stream,
  securityGraph,
  blastRadius,
  mode = "live",
  loading,
  belowGraph,
  liveRail,
}: {
  experimentId: string;
  stream: GraphState;
  securityGraph: SecurityGraphView | null;
  blastRadius: BlastRadiusResponse | null;
  mode?: InsightsMode;
  loading?: boolean;
  belowGraph?: ReactNode;
  /** Rendered with a callback that selects a node, so a row in the live
   * rail can open that node's inspector. */
  liveRail?: (selectNode: (nodeId: string) => void) => ReactNode;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [railTab, setRailTab] = useState<RailTab>("live");
  const hasRail = liveRail !== undefined;
  const activeTab: RailTab = selectedId ? "investigate" : railTab;
  const [layers, setLayers] = useState<ReadonlySet<EdgeLayer>>(new Set(INITIAL_LAYERS));
  const [path, setPath] = useState<readonly string[] | null>(null);
  const [pathSource, setPathSource] = useState("");
  const [pathTarget, setPathTarget] = useState("");
  const [focusBlastRadius, setFocusBlastRadius] = useState(false);

  const model = useMemo(
    () => buildTopologyModel(securityGraph, stream),
    [securityGraph, stream],
  );

  const nodeTypes = useMemo(() => {
    const seen = new Set<string>();
    for (const node of model.nodes) seen.add(node.nodeType);
    return [...seen].sort((a, b) => (a === "agent" ? -1 : b === "agent" ? 1 : a.localeCompare(b)));
  }, [model.nodes]);

  const nodeIds = useMemo(() => model.nodes.map((n) => n.id), [model.nodes]);

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const node of model.nodes) counts[node.nodeType] = (counts[node.nodeType] ?? 0) + 1;
    return counts;
  }, [model.nodes]);

  const focusIds = useMemo(() => {
    if (!focusBlastRadius || !blastRadius) return null;
    return new Set(blastRadius.reachable);
  }, [focusBlastRadius, blastRadius]);

  const toggleLayer = (layer: EdgeLayer) => {
    setLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  };

  const availableLayers = useMemo(() => {
    const present = new Set<EdgeLayer>();
    for (const edge of model.edges) present.add(edgeLayer(edge.edgeType));
    return ALL_LAYERS.filter((layer) => present.has(layer));
  }, [model.edges]);

  // The /analysis/blast-radius `fraction` divides reachable nodes of every
  // type by the *agent* count, so it can exceed 1.0 once tools and credentials
  // are in play. Reporting reach as a share of the whole graph is the honest
  // reading here; the agent-scoped figure is on the Results screen.
  const reachableShare =
    blastRadius && model.nodes.length > 0
      ? Math.min(1, blastRadius.reachable.length / model.nodes.length)
      : 0;

  const selectedStreamNode = selectedId ? (stream.nodes.get(selectedId) ?? null) : null;
  const incidents = selectedId ? (stream.incidentsByAgent.get(selectedId) ?? []) : [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-2">
        <span className="flex items-center gap-1.5 text-2xs text-fg-subtle">
          <IconLayers className="size-3.5" />
          Layers
        </span>
        <LayerToggles layers={layers} onToggle={toggleLayer} available={availableLayers} />

        <Button
          size="sm"
          variant={focusBlastRadius ? "primary" : "default"}
          disabled={!blastRadius}
          onClick={() => setFocusBlastRadius((v) => !v)}
          title="Dim everything the attacker cannot currently reach"
        >
          <IconTarget className="size-3.5" />
          Blast radius
        </Button>

      </div>

      <div className={cn("relative flex min-h-0 flex-1", hasRail && "flex-col xl:flex-row")}>
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Stacked under a narrow screen's live rail, the graph keeps a
              usable height of its own instead of collapsing to nothing. */}
          <div className={cn("relative flex-1", hasRail ? "min-h-80" : "min-h-0")}>
          {loading && model.nodes.length === 0 ? (
            <div className="flex size-full items-center justify-center gap-2 text-xs text-fg-muted">
              <Spinner /> Building security graph…
            </div>
          ) : model.nodes.length === 0 ? (
            <EmptyState
              className="h-full"
              title="No topology yet"
              description="The graph renders as soon as the first snapshot arrives from the run."
            />
          ) : (
            <TopologyGraph
              model={model}
              layers={layers}
              selectedId={selectedId}
              onSelect={setSelectedId}
              highlightPath={path}
              focusIds={focusIds}
            />
          )}

          {path && (
            <div className="absolute left-3 top-3 flex items-center gap-2 rounded-md border border-accent-line bg-accent-soft px-2.5 py-1.5">
              <span className="text-2xs text-fg">
                Tracing {path.length - 1} hop{path.length === 2 ? "" : "s"}:{" "}
                <span className="font-mono">{path[0]}</span> →{" "}
                <span className="font-mono">{path[path.length - 1]}</span>
              </span>
              <button
                type="button"
                onClick={() => setPath(null)}
                className="text-xs font-medium text-fg-muted transition-colors hover:text-fg"
              >
                Clear
              </button>
            </div>
          )}
          </div>

          <GraphLegend nodeTypes={nodeTypes} counts={typeCounts} />
          {belowGraph}
        </div>

        {/* Below xl the inspector slides over the graph instead of splitting
            it — a 320px panel beside a 400px graph helps nobody. With a live
            rail, the rail stacks under the graph instead. */}
        <aside
          className={cn(
            "min-h-0 shrink-0 flex-col overflow-hidden border-line bg-surface",
            hasRail
              ? "flex h-112 w-full border-t xl:h-auto xl:w-80 xl:border-l xl:border-t-0 2xl:w-96"
              : cn(
                  "w-80 border-l 2xl:w-96",
                  selectedId
                    ? "absolute inset-y-0 right-0 z-20 flex shadow-pop xl:static xl:z-auto xl:shadow-none"
                    : "hidden xl:flex",
                ),
          )}
        >
          {hasRail && (
            <div className="shrink-0 border-b border-line px-3 py-2">
              <SegmentedControl
                ariaLabel="Side panel"
                value={activeTab}
                options={RAIL_TABS}
                onChange={(tab) => {
                  if (tab === "live") setSelectedId(null);
                  setRailTab(tab);
                }}
              />
            </div>
          )}
          {liveRail && activeTab === "live" ? (
            liveRail(setSelectedId)
          ) : selectedId ? (
            <NodeInspector
              nodeId={selectedId}
              model={model}
              streamNode={selectedStreamNode}
              incidents={incidents}
              experimentId={experimentId}
              mode={mode}
              onClose={() => setSelectedId(null)}
              onTraceFrom={(id) => setPathSource(id)}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
              <h2 className="text-sm font-medium text-fg">Investigate</h2>
              <p className="mt-1 text-xs leading-5 text-fg-subtle">
                Click any node to inspect it, trace how it was compromised, and see what it can
                reach.
              </p>

              <div className="mt-4 border-t border-line pt-3">
                <h3 className="eyebrow mb-2">Attack path</h3>
                <AttackPathFinder
                  experimentId={experimentId}
                  nodeIds={nodeIds}
                  mode={mode}
                  source={pathSource}
                  target={pathTarget}
                  onSourceChange={setPathSource}
                  onTargetChange={setPathTarget}
                  onSelectPath={setPath}
                  selectedPath={path}
                />
              </div>

              {blastRadius && (
                <div className="mt-5 border-t border-line pt-3">
                  <h3 className="eyebrow mb-2">Blast radius</h3>
                  <p className="mb-2 text-xs leading-5 text-fg-subtle">
                    Everything reachable from a currently-compromised node across
                    propagation-capable edges.
                  </p>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-xl font-semibold tabular text-fg">
                      {formatPercent(reachableShare)}
                    </span>
                    <span className="font-mono text-2xs text-fg-subtle">
                      {blastRadius.reachable.length} of {model.nodes.length} nodes
                    </span>
                  </div>
                  <Meter
                    className="mt-2"
                    fraction={reachableShare}
                    severity={reachableShare >= 0.5 ? "critical" : "warn"}
                  />
                  <p className="mt-2 text-2xs text-fg-subtle">
                    {blastRadius.compromised.length} node
                    {blastRadius.compromised.length === 1 ? "" : "s"} already compromised.
                  </p>
                </div>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
