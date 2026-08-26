"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { getExperimentDetail, type ExperimentDetail } from "@/lib/api/client";
import { ArmPanel } from "@/components/ComparisonView";
import { useComparison } from "@/lib/comparison/useComparison";

type DetailState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "loaded"; detail: ExperimentDetail };

// Only ever sets state inside the fetch's resolution callbacks (never
// synchronously at the top of the effect), matching useReplayStream's
// pattern (react-hooks/set-state-in-effect).
function useExperimentDetailState(id: string | null): DetailState {
  const [state, setState] = useState<DetailState>({ status: "loading" });

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getExperimentDetail(id).then(
      (detail) => {
        if (!cancelled) setState({ status: "loaded", detail });
      },
      (err: unknown) => {
        if (!cancelled) setState({ status: "error", error: err instanceof Error ? err.message : String(err) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [id]);

  return state;
}

// Displays the persisted config/seed/defense settings for each arm --
// arbitrary historical pairs are allowed (docs/PHASE_1_5_PLAN.md §10), so
// this is what lets a viewer judge whether the pair is a methodologically
// fair comparison rather than assuming "same config, defense flipped".
function ConfigSummary({ id, state }: { id: string; state: DetailState }) {
  if (state.status === "loading") {
    return <p className="mb-2 text-xs text-slate-500">Loading config…</p>;
  }
  if (state.status === "error") {
    return <p className="mb-2 text-xs text-red-400">{state.error}</p>;
  }
  const { detail } = state;
  return (
    <dl className="mb-2 space-y-0.5 border-b border-slate-800 pb-2 text-xs text-slate-500">
      <div className="flex justify-between">
        <dt>id</dt>
        <dd className="font-mono">{id.slice(0, 8)}</dd>
      </div>
      <div className="flex justify-between">
        <dt>seed</dt>
        <dd className="font-mono">{detail.seed}</dd>
      </div>
      <div className="flex justify-between">
        <dt>node_count</dt>
        <dd className="font-mono">{detail.config.node_count}</dd>
      </div>
      <div className="flex justify-between">
        <dt>defense_enabled</dt>
        <dd className="font-mono">{detail.config.defense_enabled ? "true" : "false"}</dd>
      </div>
      <div className="flex justify-between">
        <dt>status</dt>
        <dd className="font-mono">{detail.final_status ?? "unknown"}</dd>
      </div>
      <div className="flex justify-between">
        <dt>integrity</dt>
        <dd className={detail.is_complete === true ? "text-emerald-400" : "text-amber-400"}>
          {detail.is_complete === true ? "complete" : "incomplete"}
        </dd>
      </div>
    </dl>
  );
}

function CompareContent() {
  const params = useSearchParams();
  const idA = params.get("a");
  const idB = params.get("b");
  const { armA, armB, compareHistorical } = useComparison();
  const startedFor = useRef<string | null>(null);
  const detailA = useExperimentDetailState(idA);
  const detailB = useExperimentDetailState(idB);

  useEffect(() => {
    if (!idA || !idB) return;
    const key = `${idA}:${idB}`;
    if (startedFor.current === key) return;
    startedFor.current = key;
    compareHistorical(idA, idB);
  }, [idA, idB, compareHistorical]);

  if (!idA || !idB) {
    return (
      <p className="p-4 text-sm text-slate-400">
        Select two experiments from{" "}
        <Link href="/history" className="underline hover:text-slate-200">
          the history list
        </Link>{" "}
        to compare.
      </p>
    );
  }

  return (
    <>
      <p className="px-4 py-2 text-xs text-slate-500">
        Simulation results only — not real-world security evidence. These two runs may differ in
        more than defense_enabled (seed, topology, other config) — compare the settings above
        before drawing conclusions from the metrics below.
      </p>
      <div className="flex gap-3 p-4">
        <div className="flex-1">
          <ConfigSummary id={idA} state={detailA} />
          <ArmPanel label="Arm A" arm={armA} />
        </div>
        <div className="flex-1">
          <ConfigSummary id={idB} state={detailB} />
          <ArmPanel label="Arm B" arm={armB} />
        </div>
      </div>
    </>
  );
}

export default function ComparePage() {
  return (
    <main className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
        <h1 className="text-lg font-semibold">AgentNet — Compare</h1>
        <Link href="/history" className="text-sm text-slate-400 hover:text-slate-200">
          ← Back to history
        </Link>
      </header>
      <Suspense fallback={<p className="p-4 text-sm text-slate-400">Loading…</p>}>
        <CompareContent />
      </Suspense>
    </main>
  );
}
