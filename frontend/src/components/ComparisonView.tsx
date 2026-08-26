"use client";

import { useState } from "react";

import { DEFAULT_CONFIG } from "@/components/ConfigForm";
import type { ExperimentConfig } from "@/lib/api/client";
import { useComparison, type ArmState } from "@/lib/comparison/useComparison";

const BUTTON_CLASS =
  "rounded-md border border-slate-700 px-3 py-1 text-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

function ArmPanel({ label, arm }: { label: string; arm: ArmState }) {
  return (
    <div className="flex-1 rounded-md border border-slate-800 p-3 text-sm">
      <h3 className="mb-2 font-medium text-slate-300">{label}</h3>

      {arm.status === "idle" && <p className="text-slate-500">Not yet run.</p>}

      {arm.status === "running" && <p className="text-slate-400">Running…</p>}

      {arm.status === "error" && <p className="text-red-400">{arm.error}</p>}

      {arm.status === "done" && arm.metrics && (
        <dl className="space-y-1 text-slate-400">
          <div className="flex justify-between">
            <dt>Total</dt>
            <dd className="font-mono">{arm.metrics.total}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Healthy</dt>
            <dd className="font-mono">{arm.metrics.healthy}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Compromised</dt>
            <dd className="font-mono">{arm.metrics.compromised}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Quarantined</dt>
            <dd className="font-mono">{arm.metrics.quarantined}</dd>
          </div>
          <div className="flex justify-between border-t border-slate-800 pt-1">
            <dt>New compromises</dt>
            <dd className="font-mono">{arm.metrics.newCompromises}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Total exposure</dt>
            <dd className="font-mono">{arm.metrics.totalExposure}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Outbreak duration</dt>
            <dd className="font-mono">{arm.metrics.outbreakDuration}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

export function ComparisonView({ baseConfig }: { baseConfig: ExperimentConfig | null }) {
  const { armA, armB, runComparison } = useComparison();
  const running = armA.status === "running" || armB.status === "running";
  // Collapsed by default: this panel isn't part of the core configure ->
  // Start -> observe loop, and its two metrics tables permanently occupy
  // a lot of vertical space in the header — enough to squeeze the graph
  // (the hero visual) down to near-nothing on a laptop-height viewport if
  // always expanded.
  const [expanded, setExpanded] = useState(running);

  return (
    <section className="flex flex-col gap-2 border-t border-slate-800 pt-3 text-sm">
      <div className="flex items-center justify-between">
        <button
          type="button"
          className="flex items-center gap-2 font-medium text-slate-300 hover:text-slate-100"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          <span className="text-slate-500">{expanded ? "▾" : "▸"}</span>
          Comparison
        </button>
        <button
          className={BUTTON_CLASS}
          onClick={() => {
            setExpanded(true);
            runComparison(baseConfig ?? DEFAULT_CONFIG);
          }}
          disabled={running}
        >
          Compare (defense on/off)
        </button>
      </div>

      {expanded && (
        <>
          <p className="text-xs text-slate-500">
            Simulation results only — not real-world security evidence. Both arms rerun the same
            config (seed, topology, etc.) with only <code>defense_enabled</code> flipped.
          </p>

          <div className="flex gap-3">
            <ArmPanel label="Defense ON" arm={armA} />
            <ArmPanel label="Defense OFF" arm={armB} />
          </div>
        </>
      )}
    </section>
  );
}
