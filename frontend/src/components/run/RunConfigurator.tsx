"use client";

import { useState, type ReactNode } from "react";

import { Panel, PanelDivider } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { DisclosureButton } from "@/components/ui/Disclosure";
import { ChipMultiSelect, NumberField, SelectField, ToggleField } from "@/components/ui/Field";
import { IconInfo } from "@/components/ui/icons";
import { WarningBanner } from "@/components/ui/States";
import type { ExperimentConfig } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import {
  BOUNDS,
  clamp,
  DEFAULT_CONFIG,
  PRESETS,
  WITHIN_SIGNATURE_BITS,
} from "@/lib/experiment/presets";
import { SCENARIOS, scenarioMeta } from "@/lib/vocabulary";

type Field = keyof ExperimentConfig;

/**
 * The launch surface. A preset plus the four decisions an operator makes on
 * every run — how many agents, which seed, which attacks, defense on or off —
 * are always visible; the tuning parameters a preset already sets sit under
 * "Advanced settings", summarised in one line while closed.
 *
 * Every field is an `ExperimentConfig` key sent verbatim to
 * `POST /api/experiments` — the machine name is shown under each label so a
 * run is reproducible from the UI alone.
 */
export function RunConfigurator({
  disabled,
  onStart,
  initialConfig = DEFAULT_CONFIG,
  submitLabel = "Launch assessment",
  footnote,
}: {
  disabled: boolean;
  onStart: (config: ExperimentConfig) => void;
  initialConfig?: ExperimentConfig;
  submitLabel?: string;
  /** One line beside the launch button, e.g. what launching replaces. */
  footnote?: ReactNode;
}) {
  const [draft, setDraft] = useState<ExperimentConfig>(initialConfig);
  // Highlight the preset the form was opened with, if it is one — a form
  // pre-filled from the current run must not claim to be "Baseline".
  const [presetId, setPresetId] = useState<string | null>(
    () => PRESETS.find((preset) => matchesPreset(preset.config, initialConfig))?.id ?? null,
  );
  const [showAdvanced, setShowAdvanced] = useState(false);

  const set = <K extends Field>(key: K, value: ExperimentConfig[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setPresetId(null);
  };

  const setNumber = (key: Field & keyof typeof BOUNDS, value: number, integer = true) => {
    const [min, max] = BOUNDS[key];
    const capped = (WITHIN_SIGNATURE_BITS as readonly string[]).includes(key)
      ? Math.min(max, draft.signature_bits)
      : max;
    set(key, clamp(integer ? Math.trunc(value) : value, min, capped) as never);
  };

  // Narrowing a strain narrows every distance measured in its bits.
  const setSignatureBits = (value: number) => {
    const [min, max] = BOUNDS.signature_bits;
    const bits = clamp(Math.trunc(value), min, max);
    setPresetId(null);
    setDraft((prev) => {
      const next = { ...prev, signature_bits: bits };
      for (const key of WITHIN_SIGNATURE_BITS) next[key] = Math.min(next[key], bits);
      return next;
    });
  };

  const toggleScenario = (scenario: string) => {
    setPresetId(null);
    setDraft((prev) => {
      const current = prev.active_scenarios ?? [];
      if (current.includes(scenario)) {
        return { ...prev, active_scenarios: current.filter((s) => s !== scenario) };
      }
      // Scenarios that own the tick increment are mutually exclusive
      // (docs/PLAN.md §4) — selecting one deselects its counterpart rather
      // than letting the backend silently double-tick.
      const exclusive = scenarioMeta(scenario).exclusiveWith ?? [];
      const kept = current.filter((s) => !exclusive.includes(s));
      return { ...prev, active_scenarios: [...kept, scenario] };
    });
  };

  const scenarios = draft.active_scenarios ?? [];
  const usesAdaptive = scenarios.includes("adaptive_attacker");
  const usesPromptInjection = scenarios.includes("prompt_injection");
  const usesSentinelCompromise = scenarios.includes("sentinel_compromise");
  const usesAttestation = scenarios.includes("attestation");
  const usesCollusion = scenarios.includes("byzantine_collusion");
  const needsSentinels =
    (usesSentinelCompromise || usesAttestation) && draft.sentinel_count === 0;
  const needsCredentials = usesCollusion && draft.credential_count === 0;
  const needsRealAgents = usesPromptInjection && draft.real_agent_count === 0;

  return (
    <Panel>
      <form
        className="flex flex-col"
        onSubmit={(e) => {
          e.preventDefault();
          onStart(draft);
        }}
      >
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="eyebrow mr-1">Preset</span>
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              title={preset.description}
              disabled={disabled}
              onClick={() => {
                setDraft(preset.config);
                setPresetId(preset.id);
              }}
              className={cn(
                "h-7 rounded-md border px-2.5 text-xs font-medium transition-colors duration-100",
                "disabled:cursor-not-allowed disabled:opacity-40",
                presetId === preset.id
                  ? "border-accent-line bg-accent-soft text-fg"
                  : "border-line-strong bg-surface text-fg-muted hover:border-fg-subtle/60 hover:text-fg",
              )}
            >
              {preset.label}
            </button>
          ))}
        </div>
        {presetId && (
          <p className="-mt-2 mb-4 flex items-start gap-2 text-xs leading-5 text-fg-subtle">
            <IconInfo className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" />
            {PRESETS.find((p) => p.id === presetId)?.description}
          </p>
        )}

        <PanelDivider label="System under test" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <NumberField
            label="Agents"
            hint="node_count · 25–100"
            value={draft.node_count}
            disabled={disabled}
            onChange={(v) => setNumber("node_count", v)}
          />
          <NumberField
            label="Seed"
            hint="seed · determinism key"
            value={draft.seed}
            disabled={disabled}
            onChange={(v) => set("seed", Math.trunc(v))}
          />
          <LabeledToggle
            heading="Defense"
            label="Anomaly detection & quarantine"
            hint="defense_enabled"
            checked={draft.defense_enabled}
            disabled={disabled}
            onChange={(v) => set("defense_enabled", v)}
            className="col-span-2"
          />
        </div>

        <PanelDivider label="Attack scenarios" />
        <ChipMultiSelect
          ariaLabel="Active attack scenarios"
          disabled={disabled}
          options={SCENARIOS.map((s) => ({ value: s.value, label: s.label, hint: s.hint }))}
          selected={scenarios}
          onToggle={toggleScenario}
        />
        {scenarios.length === 0 && (
          <WarningBanner className="mt-3">
            No scenario selected — the system will be built and observed, but never attacked.
          </WarningBanner>
        )}

        {(needsSentinels || needsCredentials || needsRealAgents) && (
          <WarningBanner className="mt-3">
            <ul className="flex flex-col gap-0.5">
              {needsSentinels && (
                <li>
                  Sentinel subversion and attestation replay need a security plane — set Sentinels
                  (<span className="font-mono">sentinel_count</span>) under Advanced settings above
                  zero, or the scenario will no-op.
                </li>
              )}
              {needsCredentials && (
                <li>
                  Byzantine collusion targets a credential — set Credentials (
                  <span className="font-mono">credential_count</span>) under Advanced settings
                  above zero, or the scenario will no-op.
                </li>
              )}
              {needsRealAgents && (
                <li>
                  Indirect prompt injection needs LLM-backed agents — set{" "}
                  <span className="font-mono">real_agent_count</span> under Advanced settings
                  above zero, or the scenario will no-op.
                </li>
              )}
            </ul>
          </WarningBanner>
        )}

        {usesPromptInjection && draft.real_agent_count > 0 && draft.model_provider === "vllm" && (
          <WarningBanner className="mt-3">
            The vLLM provider requires <span className="font-mono">VLLM_BASE_URL</span> configured
            on the backend; without it the launch fails with a 400.
          </WarningBanner>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <DisclosureButton open={showAdvanced} onToggle={() => setShowAdvanced((v) => !v)}>
            Advanced settings
          </DisclosureButton>
          {!showAdvanced && (
            <span className="font-mono text-2xs text-fg-subtle">{advancedSummary(draft)}</span>
          )}
        </div>

        {showAdvanced && (
          <div className="mt-5 flex flex-col">
            <PanelDivider label="Topology and run length" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <SelectField
                label="Topology"
                hint="topology"
                value={draft.topology}
                disabled={disabled}
                onChange={(v) => set("topology", v)}
                options={[
                  { value: "barabasi_albert", label: "Scale-free (Barabási–Albert)" },
                  { value: "erdos_renyi", label: "Random (Erdős–Rényi)" },
                ]}
              />
              <NumberField
                label="Edge density"
                hint="edge_density · 1–5"
                value={draft.edge_density}
                disabled={disabled}
                onChange={(v) => setNumber("edge_density", v)}
              />
              <NumberField
                label="Software diversity"
                hint="software_type_count · 1–5"
                value={draft.software_type_count}
                disabled={disabled}
                onChange={(v) => setNumber("software_type_count", v)}
              />
              <SelectField
                label="Initial foothold"
                hint="initial_compromised"
                value={draft.initial_compromised}
                disabled={disabled}
                onChange={(v) => set("initial_compromised", v)}
                options={[
                  { value: "highest_degree", label: "Highest-degree agent" },
                  { value: "random_node", label: "Random agent" },
                ]}
              />
              <NumberField
                label="Max ticks"
                hint="max_ticks · 1–2000"
                value={draft.max_ticks}
                disabled={disabled}
                onChange={(v) => setNumber("max_ticks", v)}
              />
            </div>

            <PanelDivider label="Attack surface" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <NumberField
                label="Tools"
                hint="tool_count · 0–20"
                value={draft.tool_count}
                disabled={disabled}
                onChange={(v) => setNumber("tool_count", v)}
              />
              <NumberField
                label="Credentials"
                hint="credential_count · 0–20"
                value={draft.credential_count}
                disabled={disabled}
                onChange={(v) => setNumber("credential_count", v)}
              />
              <NumberField
                label="Resources"
                hint="resource_count · 0–20"
                value={draft.resource_count}
                disabled={disabled}
                onChange={(v) => setNumber("resource_count", v)}
              />
              <NumberField
                label="Sentinels"
                hint="sentinel_count · 0–5"
                value={draft.sentinel_count}
                disabled={disabled}
                onChange={(v) => setNumber("sentinel_count", v)}
              />
            </div>

            {(usesAdaptive ||
              usesPromptInjection ||
              usesSentinelCompromise ||
              usesAttestation ||
              usesCollusion) && (
              <>
                <PanelDivider label="Attack parameters" />
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {!usesAdaptive && (
                    <>
                      <NumberField
                        label="Same-stack rate"
                        hint="p_same · 0–1"
                        step={0.01}
                        value={draft.p_same}
                        disabled={disabled}
                        onChange={(v) => setNumber("p_same", v, false)}
                      />
                      <NumberField
                        label="Cross-stack rate"
                        hint="p_cross · 0–1"
                        step={0.01}
                        value={draft.p_cross}
                        disabled={disabled}
                        onChange={(v) => setNumber("p_cross", v, false)}
                      />
                    </>
                  )}
                  {usesAdaptive && (
                    <NumberField
                      label="Adaptive threshold"
                      hint="adaptive_detection_threshold"
                      step={0.05}
                      value={draft.adaptive_detection_threshold}
                      disabled={disabled}
                      onChange={(v) => setNumber("adaptive_detection_threshold", v, false)}
                    />
                  )}
                  {usesPromptInjection && (
                    <>
                      <NumberField
                        label="LLM-backed agents"
                        hint="real_agent_count · 0–20"
                        value={draft.real_agent_count}
                        disabled={disabled}
                        onChange={(v) => setNumber("real_agent_count", v)}
                      />
                      <SelectField
                        label="Model provider"
                        hint="model_provider"
                        value={draft.model_provider}
                        disabled={disabled || draft.real_agent_count === 0}
                        onChange={(v) => set("model_provider", v)}
                        options={[
                          { value: "mock", label: "Mock (deterministic)" },
                          { value: "vllm", label: "vLLM endpoint" },
                        ]}
                      />
                    </>
                  )}
                  {usesSentinelCompromise && (
                    <NumberField
                      label="Sentinel-subversion rate"
                      hint="sentinel_compromise_rate"
                      step={0.01}
                      value={draft.sentinel_compromise_rate}
                      disabled={disabled}
                      onChange={(v) => setNumber("sentinel_compromise_rate", v, false)}
                    />
                  )}
                  {usesAttestation && (
                    <NumberField
                      label="Attestation-replay rate"
                      hint="attestation_replay_rate"
                      step={0.01}
                      value={draft.attestation_replay_rate}
                      disabled={disabled}
                      onChange={(v) => setNumber("attestation_replay_rate", v, false)}
                    />
                  )}
                  {usesCollusion && (
                    <NumberField
                      label="Collusion rate"
                      hint="byzantine_collusion_rate"
                      step={0.01}
                      value={draft.byzantine_collusion_rate}
                      disabled={disabled}
                      onChange={(v) => setNumber("byzantine_collusion_rate", v, false)}
                    />
                  )}
                </div>
              </>
            )}

            <PanelDivider label="Who can spread" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <NumberField
                label="Inference-capable share"
                hint="inference_fraction · 0–1"
                step={0.05}
                value={draft.inference_fraction}
                disabled={disabled}
                onChange={(v) => setNumber("inference_fraction", v, false)}
              />
              <SelectField
                label="Capable agents placed"
                hint="inference_placement"
                value={draft.inference_placement}
                disabled={disabled || draft.inference_fraction === 1}
                onChange={(v) => set("inference_placement", v)}
                options={PLACEMENT_OPTIONS}
              />
            </div>

            <PanelDivider label="Worm strains" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <NumberField
                label="Mutation rate"
                hint="mutation_rate · 0–1"
                step={0.05}
                value={draft.mutation_rate}
                disabled={disabled}
                onChange={(v) => setNumber("mutation_rate", v, false)}
              />
              <NumberField
                label="Bits flipped per mutation"
                hint="mutation_bits"
                value={draft.mutation_bits}
                disabled={disabled || draft.mutation_rate === 0}
                onChange={(v) => setNumber("mutation_bits", v)}
              />
              <NumberField
                label="Disguise (bits from benign)"
                hint="strain_benign_distance"
                value={draft.strain_benign_distance}
                disabled={disabled}
                onChange={(v) => setNumber("strain_benign_distance", v)}
              />
              <NumberField
                label="Strain length (bits)"
                hint="signature_bits · 8–256"
                value={draft.signature_bits}
                disabled={disabled}
                onChange={setSignatureBits}
              />
            </div>

            <PanelDivider label="Immune memory" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <LabeledToggle
                heading="Shared immune memory"
                label="Detections publish signatures"
                hint="immunity_enabled"
                checked={draft.immunity_enabled}
                disabled={disabled}
                onChange={(v) => set("immunity_enabled", v)}
                className="col-span-2"
              />
              {draft.immunity_enabled && (
                <>
                  <NumberField
                    label="Coverage"
                    hint="immunity_coverage · 0–1"
                    step={0.05}
                    value={draft.immunity_coverage}
                    disabled={disabled}
                    onChange={(v) => setNumber("immunity_coverage", v, false)}
                  />
                  <SelectField
                    label="Participants placed"
                    hint="immunity_placement"
                    value={draft.immunity_placement}
                    disabled={disabled || draft.immunity_coverage === 1}
                    onChange={(v) => set("immunity_placement", v)}
                    options={PLACEMENT_OPTIONS}
                  />
                  <NumberField
                    label="Match radius (bits)"
                    hint="signature_radius"
                    value={draft.signature_radius}
                    disabled={disabled}
                    onChange={(v) => setNumber("signature_radius", v)}
                  />
                  <NumberField
                    label="Adoption delay (ticks)"
                    hint="signature_delay_ticks · 0–50"
                    value={draft.signature_delay_ticks}
                    disabled={disabled}
                    onChange={(v) => setNumber("signature_delay_ticks", v)}
                  />
                  <NumberField
                    label="Benign probes per tick"
                    hint="benign_probes_per_tick · 0–10"
                    value={draft.benign_probes_per_tick}
                    disabled={disabled}
                    onChange={(v) => setNumber("benign_probes_per_tick", v)}
                  />
                  <LabeledToggle
                    heading="Red-team pre-seeding"
                    label="Patient zero's signature"
                    hint="preseed_patient_zero_signature"
                    checked={draft.preseed_patient_zero_signature}
                    disabled={disabled}
                    onChange={(v) => set("preseed_patient_zero_signature", v)}
                  />
                </>
              )}
            </div>

            <PanelDivider label="Defense tuning" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <NumberField
                label="Detector sensitivity"
                hint="detector_sensitivity · 0–1"
                step={0.05}
                value={draft.detector_sensitivity}
                disabled={disabled || !draft.defense_enabled}
                onChange={(v) => setNumber("detector_sensitivity", v, false)}
              />
              <NumberField
                label="Detection ramp (ticks)"
                hint="detector_ramp_ticks · 0–50"
                value={draft.detector_ramp_ticks}
                disabled={disabled || !draft.defense_enabled}
                onChange={(v) => setNumber("detector_ramp_ticks", v)}
              />
              <NumberField
                label="Detector false-positive rate"
                hint="detector_false_positive_rate · 0–1"
                step={0.01}
                value={draft.detector_false_positive_rate}
                disabled={disabled || !draft.defense_enabled}
                onChange={(v) => setNumber("detector_false_positive_rate", v, false)}
              />
              <NumberField
                label="False-quarantine rate"
                hint="false_quarantine_rate · subverted authority"
                step={0.01}
                value={draft.false_quarantine_rate}
                disabled={disabled}
                onChange={(v) => setNumber("false_quarantine_rate", v, false)}
              />
              <SelectField
                label="Response"
                hint="response_mode"
                value={draft.response_mode}
                disabled={disabled || !draft.defense_enabled}
                onChange={(v) => set("response_mode", v)}
                options={[
                  { value: "quarantine", label: "Quarantine on detection" },
                  { value: "graduated", label: "Graduated: flag, then quarantine" },
                ]}
              />
              {draft.response_mode === "graduated" && (
                <>
                  <NumberField
                    label="Flagged transmission factor"
                    hint="suspicious_transmission_factor · 0–1"
                    step={0.05}
                    value={draft.suspicious_transmission_factor}
                    disabled={disabled || !draft.defense_enabled}
                    onChange={(v) => setNumber("suspicious_transmission_factor", v, false)}
                  />
                  <NumberField
                    label="Review window (ticks)"
                    hint="review_ticks · 1–100"
                    value={draft.review_ticks}
                    disabled={disabled || !draft.defense_enabled}
                    onChange={(v) => setNumber("review_ticks", v)}
                  />
                </>
              )}
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-end gap-3 border-t border-line pt-4">
          {footnote && <p className="mr-auto text-2xs text-fg-subtle">{footnote}</p>}
          <Button type="submit" variant="primary" disabled={disabled}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

const PLACEMENT_OPTIONS = [
  { value: "random" as const, label: "At random" },
  { value: "hubs" as const, label: "Hubs first" },
  { value: "periphery" as const, label: "Periphery first" },
];

/** A switch with a label above and the field's machine name below, so it
 * lines up with the number and select fields around it. */
function LabeledToggle({
  heading,
  label,
  hint,
  checked,
  disabled,
  onChange,
  className,
}: {
  heading: string;
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="text-xs font-medium text-fg-muted">{heading}</span>
      <ToggleField
        label={label}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="h-8"
      />
      <p className="text-2xs text-fg-subtle">{hint}</p>
    </div>
  );
}

/** What "Advanced settings" holds, in one line, so a closed section hides
 * nothing that changes the run without saying so. */
function advancedSummary(config: ExperimentConfig): string {
  const surface = [
    [config.tool_count, "tools"],
    [config.credential_count, "credentials"],
    [config.resource_count, "resources"],
    [config.sentinel_count, "sentinels"],
  ] as const;
  const declared = surface.filter(([count]) => count > 0);
  // Epidemiology settings (docs/PLAN.md §14.4) are named only when they
  // differ from their no-op defaults.
  const extras = [
    config.topology === "erdos_renyi" && "random graph",
    config.inference_fraction < 1 && `${Math.round(config.inference_fraction * 100)}% capable`,
    config.mutation_rate > 0 && `mutation ${config.mutation_rate}`,
    config.immunity_enabled &&
      `immune memory ${Math.round(config.immunity_coverage * 100)}%` +
        (config.preseed_patient_zero_signature ? " pre-seeded" : ""),
    config.response_mode === "graduated" && "graduated response",
    config.detector_ramp_ticks > 0 && `${config.detector_ramp_ticks}-tick ramp`,
    config.detector_false_positive_rate > 0 &&
      `detector FP ${config.detector_false_positive_rate}`,
  ].filter((extra): extra is string => Boolean(extra));
  return [
    declared.length > 0
      ? declared.map(([count, noun]) => `${count} ${noun}`).join(" · ")
      : "agent mesh only",
    `edge density ${config.edge_density}`,
    `${config.max_ticks} ticks`,
    ...extras,
  ].join(" · ");
}

/** True when every field a preset sets has that value in `config`. */
function matchesPreset(preset: ExperimentConfig, config: ExperimentConfig): boolean {
  return (Object.keys(preset) as Array<keyof ExperimentConfig>).every(
    (key) => JSON.stringify(preset[key]) === JSON.stringify(config[key]),
  );
}
