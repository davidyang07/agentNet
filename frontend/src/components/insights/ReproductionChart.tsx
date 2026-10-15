"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/States";
import type { EpidemicResponse } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { SEVERITY_BG, SEVERITY_FILL, severityForReproduction, type Severity } from "@/lib/severity";
import { useElementSize } from "@/lib/useElementSize";

type Point = EpidemicResponse["r_effective"][number];

// Plot margins, sized for the 11px axis labels.
const PAD = { top: 12, right: 16, bottom: 20, left: 32 };
const DOT_RADIUS = 4;
const TOOLTIP_WIDTH = 168;

// Literal classes so Tailwind generates them: a censored point is a ring in
// its state's colour rather than a filled dot.
const SEVERITY_STROKE: Record<Severity, string> = {
  critical: "stroke-critical",
  high: "stroke-high",
  warn: "stroke-warn",
  contained: "stroke-contained",
  ok: "stroke-ok",
  neutral: "stroke-neutral",
};

/**
 * R(t): how many agents, on average, each agent infected at tick t went on to
 * infect. Above the line at 1 the outbreak grows; below it, it dies out.
 *
 * One series, so no legend: the panel title names it. Colour is the point's
 * severity (dying out, growing, doubling), never decoration, and a censored
 * cohort — one whose members can still infect someone, so its value may yet
 * rise — is drawn hollow, not told apart by colour alone.
 */
export function ReproductionChart({ points }: { points: readonly Point[] }) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const innerWidth = Math.max(0, size.width - PAD.left - PAD.right);
  const innerHeight = Math.max(0, size.height - PAD.top - PAD.bottom);

  const geometry = useMemo(() => {
    if (points.length === 0 || innerWidth <= 0 || innerHeight <= 0) return null;
    const lastTick = Math.max(points[points.length - 1].tick, 8);
    // Always show the threshold with headroom above it.
    const yMax = Math.max(2, ...points.map((p) => p.value)) * 1.1;
    const xOf = (tick: number) => PAD.left + (tick / lastTick) * innerWidth;
    const yOf = (value: number) => PAD.top + innerHeight - (value / yMax) * innerHeight;
    const marks = points.map((point) => ({
      point,
      x: xOf(point.tick),
      y: yOf(point.value),
      severity: severityForReproduction(point.value),
    }));
    const path = marks.map((m, i) => `${i === 0 ? "M" : "L"}${round(m.x)} ${round(m.y)}`).join(" ");
    // Whole reproduction numbers as recessive gridlines, so a point's value
    // reads off the axis without hovering. 1 is drawn as the threshold.
    const gridValues = Array.from({ length: Math.floor(yMax) }, (_, i) => i + 1).filter(
      (value) => value !== 1,
    );
    return { marks, path, yOf, gridValues, baseline: PAD.top + innerHeight };
  }, [points, innerWidth, innerHeight]);

  if (points.length === 0) {
    return (
      <div ref={ref} className="size-full">
        <EmptyState
          compact
          title="No infections to measure"
          description="R(t) appears once an infected agent has had the chance to infect another."
        />
      </div>
    );
  }

  const hovered = hoverIndex !== null ? geometry?.marks[hoverIndex] : undefined;

  return (
    <div ref={ref} className="relative size-full">
      {geometry && size.width > 0 && (
        <svg
          width={size.width}
          height={size.height}
          role="img"
          aria-label="Reproduction number R(t) by infection tick"
          onPointerLeave={() => setHoverIndex(null)}
          onPointerMove={(e) => {
            const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
            let nearest = 0;
            let best = Infinity;
            geometry.marks.forEach((mark, index) => {
              const distance = Math.abs(mark.x - x);
              if (distance < best) {
                best = distance;
                nearest = index;
              }
            });
            setHoverIndex(nearest);
          }}
        >
          <line
            x1={PAD.left}
            x2={PAD.left + innerWidth}
            y1={geometry.baseline}
            y2={geometry.baseline}
            className="stroke-line"
            strokeWidth="1"
          />
          {geometry.gridValues.map((value) => (
            <g key={value}>
              <line
                x1={PAD.left}
                x2={PAD.left + innerWidth}
                y1={geometry.yOf(value)}
                y2={geometry.yOf(value)}
                className="stroke-line"
                strokeWidth="1"
              />
              <text
                x={PAD.left - 6}
                y={geometry.yOf(value) + 4}
                textAnchor="end"
                className="fill-fg-subtle text-2xs"
              >
                {value}
              </text>
            </g>
          ))}
          {/* The threshold the whole chart is read against. */}
          <line
            x1={PAD.left}
            x2={PAD.left + innerWidth}
            y1={geometry.yOf(1)}
            y2={geometry.yOf(1)}
            className="stroke-line-strong"
            strokeWidth="1"
            strokeDasharray="4 4"
          />
          <text
            x={PAD.left + innerWidth}
            y={geometry.yOf(1) - 5}
            textAnchor="end"
            className="fill-fg-subtle text-2xs"
          >
            R = 1
          </text>

          <path d={geometry.path} fill="none" className="stroke-fg-subtle" strokeWidth="1.5" />

          {hovered && (
            <line
              x1={hovered.x}
              x2={hovered.x}
              y1={PAD.top}
              y2={geometry.baseline}
              className="stroke-line-strong"
              strokeWidth="1"
            />
          )}

          {geometry.marks.map((mark) => (
            <circle
              key={mark.point.tick}
              cx={mark.x}
              cy={mark.y}
              r={DOT_RADIUS}
              strokeWidth="2"
              className={
                mark.point.censored
                  ? cn("fill-raised", SEVERITY_STROKE[mark.severity])
                  : cn(SEVERITY_FILL[mark.severity], "stroke-raised")
              }
            />
          ))}

          <text x={PAD.left - 6} y={geometry.yOf(1) + 4} textAnchor="end" className="fill-fg-subtle text-2xs">
            1
          </text>
          <text x={PAD.left - 6} y={geometry.baseline} textAnchor="end" className="fill-fg-subtle text-2xs">
            0
          </text>
          <text
            x={PAD.left + innerWidth}
            y={size.height - 4}
            textAnchor="end"
            className="fill-fg-subtle text-2xs"
          >
            infection tick
          </text>
        </svg>
      )}

      {hovered && (
        <div
          className="pointer-events-none absolute top-2 rounded-md border border-line bg-overlay px-2 py-1.5 shadow-pop"
          style={{
            left: Math.min(
              Math.max(hovered.x - TOOLTIP_WIDTH / 2, 4),
              Math.max(4, size.width - TOOLTIP_WIDTH),
            ),
            width: TOOLTIP_WIDTH,
          }}
        >
          <p className="mb-1 font-mono text-2xs text-fg-subtle">infected at tick {hovered.point.tick}</p>
          <p className="flex items-baseline gap-2 text-2xs">
            <span
              aria-hidden
              className={cn("size-2 shrink-0 self-center rounded-full", SEVERITY_BG[hovered.severity])}
            />
            <span className="font-mono tabular font-medium text-fg">
              R = {hovered.point.value.toFixed(2)}
            </span>
          </p>
          {hovered.point.censored && (
            <p className="mt-0.5 text-2xs text-fg-subtle">Still infectious — may rise.</p>
          )}
        </div>
      )}

      {/* The accessible fallback for the plot; see OutbreakChart for why
          sr-only sits on a wrapper. */}
      <div className="sr-only">
        <table>
          <caption>Reproduction number by infection tick</caption>
          <thead>
            <tr>
              <th scope="col">Tick</th>
              <th scope="col">R(t)</th>
              <th scope="col">Still infectious</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.tick}>
                <td>{point.tick}</td>
                <td>{point.value.toFixed(2)}</td>
                <td>{point.censored ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}
