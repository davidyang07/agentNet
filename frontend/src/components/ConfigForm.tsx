"use client";

import { useState } from "react";

import type { ExperimentConfig } from "@/lib/api/client";

// SPEC §6.2's own canonical demo config.
export const DEFAULT_CONFIG: ExperimentConfig = {
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
  real_agent_count: 0,
  model_provider: "mock",
  model_name: "qwen-mock",
  model_max_tokens: 64,
  model_timeout_s: 20,
  model_max_retries: 1,
  model_max_concurrency: 4,
  model_max_requests_per_experiment: 500,
  tool_count: 0,
  credential_count: 0,
  resource_count: 0,
  sentinel_count: 0,
  adaptive_detection_threshold: 0.3,
};

const INPUT_CLASS =
  "w-24 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-right text-slate-200 disabled:cursor-not-allowed disabled:opacity-40";

const BUTTON_CLASS =
  "rounded-md border border-slate-700 px-3 py-1 text-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

export function ConfigForm({
  disabled,
  onStart,
}: {
  disabled: boolean;
  onStart: (config: ExperimentConfig) => void;
}) {
  const [draft, setDraft] = useState<ExperimentConfig>(DEFAULT_CONFIG);

  const setField = <K extends keyof ExperimentConfig>(key: K, value: ExperimentConfig[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <form
      className="flex flex-col gap-2 text-sm text-slate-400"
      onSubmit={(e) => {
        e.preventDefault();
        onStart(draft);
      }}
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          seed
          <input
            className={INPUT_CLASS}
            type="number"
            step={1}
            value={draft.seed}
            disabled={disabled}
            onChange={(e) => setField("seed", Math.trunc(Number(e.target.value)))}
          />
        </label>

        <label className="flex flex-col gap-1">
          node_count
          <input
            className={INPUT_CLASS}
            type="number"
            step={1}
            value={draft.node_count}
            disabled={disabled}
            onChange={(e) => setField("node_count", clamp(Math.trunc(Number(e.target.value)), 25, 100))}
          />
        </label>

        <label className="flex flex-col gap-1">
          edge_density
          <input
            className={INPUT_CLASS}
            type="number"
            step={1}
            value={draft.edge_density}
            disabled={disabled}
            onChange={(e) => setField("edge_density", clamp(Math.trunc(Number(e.target.value)), 1, 5))}
          />
        </label>

        <label className="flex flex-col gap-1">
          software_type_count
          <input
            className={INPUT_CLASS}
            type="number"
            step={1}
            value={draft.software_type_count}
            disabled={disabled}
            onChange={(e) =>
              setField("software_type_count", clamp(Math.trunc(Number(e.target.value)), 1, 5))
            }
          />
        </label>

        <label className="flex flex-col gap-1">
          p_same
          <input
            className={INPUT_CLASS}
            type="number"
            step={0.01}
            value={draft.p_same}
            disabled={disabled}
            onChange={(e) => setField("p_same", clamp(Number(e.target.value), 0.0, 1.0))}
          />
        </label>

        <label className="flex flex-col gap-1">
          p_cross
          <input
            className={INPUT_CLASS}
            type="number"
            step={0.01}
            value={draft.p_cross}
            disabled={disabled}
            onChange={(e) => setField("p_cross", clamp(Number(e.target.value), 0.0, 1.0))}
          />
        </label>

        <label className="flex flex-col gap-1">
          detector_sensitivity
          <input
            className={INPUT_CLASS}
            type="number"
            step={0.01}
            value={draft.detector_sensitivity}
            disabled={disabled}
            onChange={(e) => setField("detector_sensitivity", clamp(Number(e.target.value), 0.0, 1.0))}
          />
        </label>

        <label className="flex flex-col gap-1">
          max_ticks
          <input
            className={INPUT_CLASS}
            type="number"
            step={1}
            value={draft.max_ticks}
            disabled={disabled}
            onChange={(e) => setField("max_ticks", clamp(Math.trunc(Number(e.target.value)), 1, 2000))}
          />
        </label>

        <label className="flex flex-col gap-1">
          initial_compromised
          <select
            className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
            value={draft.initial_compromised}
            disabled={disabled}
            onChange={(e) =>
              setField("initial_compromised", e.target.value as ExperimentConfig["initial_compromised"])
            }
          >
            <option value="highest_degree">highest_degree</option>
            <option value="random_node">random_node</option>
          </select>
        </label>

        <label className="flex flex-row items-center gap-1 pb-1">
          <input
            type="checkbox"
            checked={draft.defense_enabled}
            disabled={disabled}
            onChange={(e) => setField("defense_enabled", e.target.checked)}
          />
          defense_enabled
        </label>

        <label className="flex flex-col gap-1">
          real_agent_count
          <input
            className={INPUT_CLASS}
            type="number"
            step={1}
            value={draft.real_agent_count}
            disabled={disabled}
            onChange={(e) => setField("real_agent_count", clamp(Math.trunc(Number(e.target.value)), 0, 20))}
          />
        </label>

        <label className="flex flex-col gap-1">
          model_provider
          <select
            className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
            value={draft.model_provider}
            disabled={disabled || draft.real_agent_count === 0}
            onChange={(e) => setField("model_provider", e.target.value as ExperimentConfig["model_provider"])}
          >
            <option value="mock">mock</option>
            <option value="vllm">vllm</option>
          </select>
        </label>

        {draft.real_agent_count > 0 && draft.model_provider === "vllm" && (
          <p className="basis-full text-xs text-amber-500">
            vllm requires VLLM_BASE_URL configured on the backend, or Start will fail with 400.
          </p>
        )}

        <button className={BUTTON_CLASS} type="submit" disabled={disabled}>
          Start
        </button>
      </div>
    </form>
  );
}
