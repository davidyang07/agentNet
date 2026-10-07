"use client";

import Graph from "graphology";
import { useEffect, useRef } from "react";
import Sigma from "sigma";

import { computeLayout } from "@/lib/graph/layout";
import {
  edgeLayer,
  nodeColor,
  nodeShape,
  nodeSize,
  renderableEdges,
  type NodeShape,
  type TopologyModel,
  type TopologyNode,
} from "@/lib/graph/model";
import { mix, severityColor, token, withAlpha } from "@/lib/theme";
import { EDGE_LAYER_META, type EdgeLayer } from "@/lib/vocabulary";

const ALL_LAYERS: EdgeLayer[] = ["mesh", "access", "oversight"];

// Overlay geometry, in CSS pixels. Annotation follows the console type floor —
// nothing on screen renders below 11px (DESIGN.md › Typography).
const LABEL_SIZE = 11;
const LABEL_HEIGHT = 16;
const LABEL_PAD_X = 5;
const BADGE_RADIUS = 8;

/** Design tokens resolved to literal values: Sigma's WebGL program and the 2D
 * overlay cannot take CSS variables. Read once per build — tokens are static. */
type GraphTheme = {
  accent: string;
  onAccent: string;
  fg: string;
  fgMuted: string;
  /** What the graph is drawn on; dimmed marks recede toward it. */
  background: string;
  labelBackground: string;
  neutral: string;
  edge: Record<EdgeLayer, string>;
  monoFont: string;
  sansFont: string;
  radius: number;
};

function readGraphTheme(): GraphTheme {
  return {
    accent: token("--color-accent"),
    onAccent: token("--color-on-accent"),
    fg: token("--color-fg"),
    fgMuted: token("--color-fg-muted"),
    background: token("--color-surface"),
    labelBackground: withAlpha(token("--color-canvas"), 0.85),
    neutral: severityColor("neutral"),
    edge: {
      mesh: token(EDGE_LAYER_META.mesh.token),
      access: token(EDGE_LAYER_META.access.token),
      oversight: token(EDGE_LAYER_META.oversight.token),
    },
    monoFont: token("--font-mono") || "monospace",
    sansFont: token("--font-sans") || "sans-serif",
    radius: parseFloat(token("--radius-xs")) || 4,
  };
}

export type TopologyGraphProps = {
  model: TopologyModel;
  layers: ReadonlySet<EdgeLayer>;
  selectedId: string | null;
  onSelect: (nodeId: string | null) => void;
  /** Ordered node ids of an attack path to trace over the graph. */
  highlightPath?: readonly string[] | null;
  /** Node ids to keep at full opacity; everything else dims. Used for blast
   * radius and for focusing a selection's neighbourhood. */
  focusIds?: ReadonlySet<string> | null;
};

type Live = {
  model: TopologyModel;
  layers: ReadonlySet<EdgeLayer>;
  selectedId: string | null;
  hoveredId: string | null;
  pathIds: readonly string[];
  pathSet: Set<string>;
  pathEdgeKeys: Set<string>;
  focusIds: ReadonlySet<string> | null;
  nodeById: Map<string, TopologyNode>;
  theme: GraphTheme;
};

function pathEdgeKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

/**
 * The investigation surface.
 *
 * Sigma renders geometry (WebGL discs and lines); a 2D overlay canvas renders
 * everything that carries meaning beyond position — the shape ring that says
 * what kind of node this is, labels, the selection halo, and the numbered
 * attack path. Splitting it that way is what makes typed nodes possible
 * without a custom WebGL program, and keeps SPEC §4's contract intact: the
 * graph is built once from the snapshot and mutated with `setNodeAttribute`,
 * never rebuilt per frame.
 */
export function TopologyGraph({
  model,
  layers,
  selectedId,
  onSelect,
  highlightPath,
  focusIds,
}: TopologyGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const onSelectRef = useRef(onSelect);

  // Everything the render callbacks read lives in one ref, so a state change
  // never has to tear down and rebuild the renderer.
  const liveRef = useRef<Live>({
    model,
    layers,
    selectedId,
    hoveredId: null,
    pathIds: [],
    pathSet: new Set(),
    pathEdgeKeys: new Set(),
    focusIds: null,
    nodeById: new Map(),
    theme: readGraphTheme(),
  });

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  // --- build (once per structure) -----------------------------------------
  useEffect(() => {
    const container = containerRef.current;
    const overlay = overlayRef.current;
    if (!container || !overlay) return;
    if (model.nodes.length === 0) return;

    const theme = readGraphTheme();
    liveRef.current.theme = theme;
    const positions = computeLayout(model.nodes, model.edges);
    const graph = new Graph({ multi: false, type: "undirected" });
    for (const node of model.nodes) {
      const point = positions.get(node.id) ?? { x: 0, y: 0 };
      graph.addNode(node.id, {
        x: point.x,
        y: point.y,
        size: nodeSize(node),
        color: nodeColor(node),
        label: node.id,
        nodeType: node.nodeType,
        // Non-agent nodes draw above the mesh: they are the smaller,
        // higher-information population.
        zIndex: node.nodeType === "agent" ? 0 : 1,
      });
    }
    for (const edge of renderableEdges(model.edges, new Set(ALL_LAYERS))) {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
      if (graph.hasEdge(edge.source, edge.target)) continue;
      graph.addEdge(edge.source, edge.target, {
        size: 1,
        layer: edgeLayer(edge.edgeType),
        edgeType: edge.edgeType,
      });
    }

    const renderer = new Sigma(graph, container, {
      // All annotation is drawn by this component's own overlay, which is not
      // subject to Sigma's label-grid culling — a typed node must never lose
      // its shape ring just because a neighbour's label won the grid cell.
      renderLabels: false,
      renderEdgeLabels: false,
      // A container can be momentarily 0px tall mid-layout (a panel opening,
      // a resize); Sigma would throw and take the whole console down with it.
      allowInvalidContainer: true,
      // Sigma's own hover chip is a white pill drawn on its hover layer,
      // independent of `renderLabels`. The overlay already draws a hover
      // label in this design system's style, so silence Sigma's.
      defaultDrawNodeHover: () => {},
      enableEdgeEvents: false,
      zIndex: true,
      minCameraRatio: 0.15,
      maxCameraRatio: 6,
      defaultNodeColor: theme.neutral,
      defaultEdgeColor: theme.edge.mesh,
      nodeReducer: (nodeKey, data) => {
        const live = liveRef.current;
        const id = String(nodeKey);
        const dimmed = isDimmed(live, id);
        return {
          ...data,
          color: dimmed ? dim(String(data.color), theme) : String(data.color),
          zIndex: live.selectedId === id || live.pathSet.has(id) ? 2 : (data.zIndex as number),
        };
      },
      edgeReducer: (edgeKey, data) => {
        const live = liveRef.current;
        const layer = data.layer as EdgeLayer;
        if (!live.layers.has(layer)) return { ...data, hidden: true };
        const [source, target] = graph.extremities(edgeKey as string);
        if (live.pathEdgeKeys.has(pathEdgeKey(source, target))) {
          return { ...data, color: theme.accent, size: 2.4, zIndex: 3 };
        }
        const touchesSelection =
          live.selectedId !== null &&
          (source === live.selectedId || target === live.selectedId);
        if (touchesSelection) {
          return { ...data, color: theme.fgMuted, size: 1.6, zIndex: 2 };
        }
        const dimmed = isDimmed(live, source) && isDimmed(live, target);
        const color = theme.edge[layer];
        return { ...data, color: dimmed ? dim(color, theme) : color };
      },
    });

    renderer.on("clickNode", ({ node }) => onSelectRef.current(node));
    renderer.on("clickStage", () => onSelectRef.current(null));
    renderer.on("enterNode", ({ node }) => {
      liveRef.current.hoveredId = node;
      container.style.cursor = "pointer";
      renderer.refresh({ skipIndexation: true });
    });
    renderer.on("leaveNode", () => {
      liveRef.current.hoveredId = null;
      container.style.cursor = "default";
      renderer.refresh({ skipIndexation: true });
    });
    renderer.on("afterRender", () => drawOverlay(renderer, overlay, liveRef.current));

    sigmaRef.current = renderer;
    graphRef.current = graph;
    renderer.refresh();
    // Sigma fits the node bounding box exactly to the viewport; the overlay
    // draws labels *outside* that box, so pull the camera back enough for them
    // to fit rather than letting the outermost ring's labels clip.
    renderer.getCamera().setState({ ratio: 1.22 });

    return () => {
      renderer.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
    // Rebuilding is keyed on structure alone: security state, selection,
    // layers and highlights are all applied without touching the layout.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model.structureKey]);

  // --- live state (colour only — never a rebuild, per SPEC §4) -------------
  useEffect(() => {
    const graph = graphRef.current;
    liveRef.current.model = model;
    liveRef.current.nodeById = new Map(model.nodes.map((n) => [n.id, n]));
    if (!graph) return;
    for (const node of model.nodes) {
      if (!graph.hasNode(node.id)) continue;
      const color = nodeColor(node);
      if (graph.getNodeAttribute(node.id, "color") !== color) {
        graph.setNodeAttribute(node.id, "color", color);
      }
    }
    sigmaRef.current?.refresh({ skipIndexation: true });
  }, [model]);

  useEffect(() => {
    const path = highlightPath ?? [];
    const pathEdgeKeys = new Set<string>();
    for (let i = 0; i < path.length - 1; i++) pathEdgeKeys.add(pathEdgeKey(path[i], path[i + 1]));
    liveRef.current.layers = layers;
    liveRef.current.selectedId = selectedId;
    liveRef.current.pathIds = path;
    liveRef.current.pathSet = new Set(path);
    liveRef.current.pathEdgeKeys = pathEdgeKeys;
    liveRef.current.focusIds = focusIds ?? null;
    sigmaRef.current?.refresh({ skipIndexation: true });
  }, [layers, selectedId, highlightPath, focusIds]);

  return (
    // Pinned to the positioned parent rather than sized with height: 100%,
    // which resolves to 0 when the parent's height comes from flex alone (the
    // stacked narrow-screen layout) — and Sigma cannot draw into 0px.
    <div className="absolute inset-0">
      <div ref={containerRef} className="absolute inset-0" />
      <canvas
        ref={overlayRef}
        aria-hidden
        className="pointer-events-none absolute inset-0 size-full"
      />
    </div>
  );
}

function isDimmed(live: Live, id: string): boolean {
  if (live.pathSet.size > 0) return !live.pathSet.has(id);
  if (live.focusIds) return !live.focusIds.has(id);
  return false;
}

/** Mixes a colour most of the way into the graph's background — the dim state
 * has to stay legible as structure while clearly receding. */
function dim(hex: string, theme: GraphTheme): string {
  return mix(hex, theme.background, 0.25);
}

// --- overlay --------------------------------------------------------------

function drawOverlay(renderer: Sigma, canvas: HTMLCanvasElement, live: Live): void {
  const { width, height } = renderer.getDimensions();
  const dpr = typeof window === "undefined" ? 1 : Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const { theme } = live;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const labelled: Array<{
    id: string;
    x: number;
    y: number;
    radius: number;
    priority: number;
  }> = [];
  // Every drawn node is an obstacle for label placement: an opaque label chip
  // laid over a node hides it completely, which is worse than no label.
  const obstacles: Array<[number, number, number, number]> = [];

  for (const node of live.model.nodes) {
    const data = renderer.getNodeDisplayData(node.id);
    if (!data || data.hidden) continue;
    const { x, y } = renderer.framedGraphToViewport(data);
    if (x < -40 || y < -40 || x > width + 40 || y > height + 40) continue;
    const radius = renderer.scaleSize(data.size);
    obstacles.push([x - radius - 4, y - radius - 4, (radius + 4) * 2, (radius + 4) * 2]);
    const dimmed = isDimmed(live, node.id);
    const color = String(data.color);
    const shape = nodeShape(node.nodeType);

    // Type ring: the second visual channel that lets colour stay reserved for
    // security state.
    if (shape !== "circle") {
      ctx.save();
      ctx.globalAlpha = dimmed ? 0.35 : 0.95;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      traceShape(ctx, shape, x, y, radius + 3.5);
      ctx.stroke();
      ctx.restore();
    }

    const isSelected = live.selectedId === node.id;
    const isHovered = live.hoveredId === node.id;
    const inPath = live.pathSet.has(node.id);

    if (isSelected || isHovered) {
      ctx.save();
      ctx.strokeStyle = isSelected ? theme.fg : withAlpha(theme.fg, 0.55);
      ctx.lineWidth = isSelected ? 1.6 : 1.2;
      ctx.beginPath();
      ctx.arc(x, y, radius + 6.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (inPath) {
      ctx.save();
      ctx.strokeStyle = theme.accent;
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.arc(x, y, radius + 5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // Higher priority wins a contested spot. Whatever the operator is
    // actively looking at always keeps its label.
    const priority = isSelected || isHovered ? 3 : inPath ? 2 : node.nodeType !== "agent" ? 1 : 0;
    const wantsLabel = priority > 0 || node.attrs.agent_kind === "real";
    if (wantsLabel && !dimmed) {
      labelled.push({ id: node.id, x, y, radius, priority });
    }
  }

  // Labels last, so no node can be drawn over one — and collision-checked, so
  // a crowded ring degrades by dropping the least important label rather than
  // by stacking unreadable text.
  // Canvas cannot resolve CSS variables, so the family is the token's computed
  // value — a `var(...)` font string would be rejected and fall back to 10px
  // sans-serif.
  ctx.font = `500 ${LABEL_SIZE}px ${theme.monoFont}`;
  ctx.textBaseline = "middle";
  const placed: Array<[number, number, number, number]> = [...obstacles];
  const centreX = width / 2;
  for (const item of [...labelled].sort((a, b) => b.priority - a.priority)) {
    const textWidth = ctx.measureText(item.id).width;
    const boxWidth = textWidth + LABEL_PAD_X * 2;
    // Labels point away from the centre of the graph, so a ring of typed nodes
    // reads outward. The mirrored side and a small vertical nudge are tried in
    // turn before a label is given up on — a ring of 19 typed nodes otherwise
    // loses a third of its labels to first-come collisions.
    const outward = item.x < centreX ? -1 : 1;
    const gap = item.radius + 6;
    let box: [number, number, number, number] | null = null;
    for (const dx of [outward, -outward]) {
      for (const dy of [0, -(LABEL_HEIGHT + 1), LABEL_HEIGHT + 1]) {
        const boxX = dx < 0 ? item.x - gap - boxWidth : item.x + gap;
        const candidate: [number, number, number, number] = [
          boxX,
          item.y - LABEL_HEIGHT / 2 + dy,
          boxWidth,
          LABEL_HEIGHT,
        ];
        // The selection and the hover target always get their label.
        if (item.priority === 3 || !placed.some((other) => overlaps(candidate, other))) {
          box = candidate;
          break;
        }
      }
      if (box) break;
    }
    if (!box) continue;
    placed.push(box);
    ctx.fillStyle = theme.labelBackground;
    roundRect(ctx, box[0], box[1], box[2], box[3], theme.radius);
    ctx.fill();
    // Whatever the operator is looking at reads brightest.
    ctx.fillStyle = item.priority >= 2 ? theme.fg : theme.fgMuted;
    ctx.fillText(item.id, box[0] + LABEL_PAD_X, box[1] + LABEL_HEIGHT / 2 + 0.5);
  }

  // Attack-path step numbers: the path is an ordered claim, and a highlighted
  // line alone cannot express order.
  if (live.pathIds.length > 1) {
    live.pathIds.forEach((id, index) => {
      const data = renderer.getNodeDisplayData(id);
      if (!data) return;
      const { x, y } = renderer.framedGraphToViewport(data);
      const radius = renderer.scaleSize(data.size);
      const badgeY = y - radius - BADGE_RADIUS - 4;
      ctx.save();
      ctx.fillStyle = theme.accent;
      ctx.beginPath();
      ctx.arc(x, badgeY, BADGE_RADIUS, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = theme.onAccent;
      ctx.font = `600 ${LABEL_SIZE}px ${theme.sansFont}`;
      ctx.textAlign = "center";
      ctx.fillText(String(index + 1), x, badgeY + 0.5);
      ctx.restore();
    });
    ctx.textAlign = "left";
  }
}

function overlaps(
  a: [number, number, number, number],
  b: [number, number, number, number],
): boolean {
  return a[0] < b[0] + b[2] && a[0] + a[2] > b[0] && a[1] < b[1] + b[3] && a[1] + a[3] > b[1];
}

function traceShape(
  ctx: CanvasRenderingContext2D,
  shape: NodeShape,
  x: number,
  y: number,
  r: number,
): void {
  ctx.beginPath();
  switch (shape) {
    case "square":
      ctx.rect(x - r * 0.85, y - r * 0.85, r * 1.7, r * 1.7);
      break;
    case "diamond":
      ctx.moveTo(x, y - r);
      ctx.lineTo(x + r, y);
      ctx.lineTo(x, y + r);
      ctx.lineTo(x - r, y);
      ctx.closePath();
      break;
    case "triangle":
      ctx.moveTo(x, y - r * 1.1);
      ctx.lineTo(x + r, y + r * 0.75);
      ctx.lineTo(x - r, y + r * 0.75);
      ctx.closePath();
      break;
    case "hexagon":
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        const px = x + r * Math.cos(angle);
        const py = y + r * Math.sin(angle);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      break;
    case "shield":
      ctx.moveTo(x - r * 0.85, y - r * 0.8);
      ctx.lineTo(x + r * 0.85, y - r * 0.8);
      ctx.lineTo(x + r * 0.85, y + r * 0.1);
      ctx.quadraticCurveTo(x + r * 0.75, y + r * 0.8, x, y + r * 1.1);
      ctx.quadraticCurveTo(x - r * 0.75, y + r * 0.8, x - r * 0.85, y + r * 0.1);
      ctx.closePath();
      break;
    default:
      ctx.arc(x, y, r, 0, Math.PI * 2);
  }
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
