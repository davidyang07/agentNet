# AgentShield → Multi-Agent Adversarial Resilience Platform — Authoritative Plan

> **This document supersedes** `docs/PHASE0_PLAN.md`, `docs/M1_PLAN.md`, `docs/M1_F3_PLAN.md`,
> `docs/M1_F5_PLAN.md`, `docs/PHASE_1_5_PLAN.md`, and `docs/PHASE_2_PLAN.md` (removed — their
> content is folded into "Migration & status" below; git history retains them if needed).
>
> **Relationship to `docs/BRIEF.md` / `docs/SPEC.md`:** those documents remain accurate for the
> mechanism they define (event schema, derived-keyed RNG, fixed-tick engine, snapshot/delta
> protocol, Pydantic↔TypeScript contract) — none of that is being replaced, only extended. Where
> their *product framing* (the M0→Phase 2 vertical-slice roadmap) conflicts with this document,
> **this document governs product direction and architecture going forward.** `CLAUDE.md` has been
> updated to point here for that split.
>
> **Naming note:** this plan originally kept the legacy name "AgentNet" and treated "AgentShield"
> as a working title for the *positioning* only. That has since been reversed: the product name in
> the docs, READMEs, and source comments is now **AgentShield**. The rename was deliberately limited
> to that user-facing naming — the lowercase `agentnet` identifiers (Postgres user/password/database
> names, the OTel service name and `agentnet.*` span-attribute prefix, and the `agentnet-backend`
> package name) are unchanged, so no database, CI, or telemetry consumer is affected.

---

## 1. Why this pivot, and why it's a pivot and not a rewrite

AgentShield today (Phases 0–2, all shipped) is a **deterministic, event-sourced simulation of
compromise propagation** over a homogeneous graph: one node type (`AgentNode`), one edge type
(undirected "neighbor"), one attack (probabilistic same/cross-software infection, optionally
mediated by a real LLM doing lateral prompt injection), one defense (a generic anomaly
detector→quarantine). It is a strong, well-tested foundation: pure/synchronous engine core,
derived-keyed determinism, an event system already typed for far more than it emits, Postgres
persistence as a passive event-bus subscriber, full replay/comparison, and a real Model Gateway
with mock/vLLM providers.

What it cannot yet do is what the new product requires: model **which agent can reach which
credential through which tool, whether a compromised agent can escalate privilege, whether the
sentinel watching it can itself be subverted, and what an attacker that adapts to defenses looks
like.** That needs a *typed* graph (multiple node kinds, multiple relationship kinds) and
*pluggable* attacker behavior, neither of which exists today.

This plan is a **migration, not a rewrite**: every subsystem in the "Preserve" list below keeps its
current contract. New capability is added as new modules that compose with the existing engine,
not modules that replace it.

---

## 2. Target architecture

### 2.1 Component map (additions marked **NEW**; unchanged components keep their existing contract)

| Component | Owns | Status |
|---|---|---|
| Frontend | Visualization, controls, inspection, replay, comparison | Preserved as-is this phase (integration is priority 8) |
| Experiment Orchestrator (`app/orchestrator/`) | Lifecycle, pause/resume/speed, seed management | Preserved; gains a scenario registry call site |
| Simulation Engine (`app/engine/`) | Topology, pure tick, simulation clock | Preserved unchanged |
| **Security Graph (`app/graph/`)** | **NEW.** Typed nodes/edges, attack-path/blast-radius/critical-node/provenance analysis | This plan, priority 1 |
| **Scenario Framework (`app/scenarios/`)** | **NEW.** Pluggable attacker behaviors behind one interface | This plan, priority 2 |
| **Adaptive Attacker (`app/scenarios/adaptive.py`)** | **NEW.** observe→choose→attack→observe→adapt, deterministic | This plan, priority 3 |
| Security Engine (`app/security/`) | Detection, quarantine (defense side) | Preserved; extended with security-plane targets (priority 4) |
| Agent Runtime (`app/agents/`) | Real LLM-backed agent behavior | Preserved; becomes one scenario implementation |
| Model Gateway (`app/gateway/`) | Uniform mock/vLLM API, budget/timeout/retry/concurrency | Preserved unchanged |
| Event / Telemetry System (`app/events/`, `app/schemas/events.py`) | Normalize, stream, persist, replay | Preserved; gains new additive `EventType` members |
| Persistence (`app/persistence/`, Postgres) | Durable event log, experiment metadata | Preserved unchanged — **no new tables required** (see §2.3) |
| **Remediation Engine (`app/remediation/`)** | **NEW.** Deterministic fix recommendations from graph + observed violations | Priority 7 |

### 2.2 Domain model

**Typed nodes** (`app/graph/types.py::NodeType`):

```
AGENT              — existing AgentNode, unchanged fields, now also a graph node
TOOL               — a callable capability an agent can invoke
MCP_SERVER         — a tool-hosting server (same edges as TOOL; distinguished for scenario targeting)
CREDENTIAL         — a secret an agent can hold/use to unlock CAN_ACCESS to a RESOURCE
RESOURCE           — a protected asset (data store, service) reachable via a CREDENTIAL or directly
MEMORY_STORE       — an agent's persistent memory (poisoning target)
SENTINEL           — a monitoring node with MONITORS + QUARANTINE_AUTHORITY edges to agents
SECURITY_CONTROL   — a control plane node; `kind` attr discriminates:
                       "trust_manager" | "threat_memory_store" | "attestation_service"
```

Every `GraphNode` carries `id`, `node_type`, `security_state` (the same five-value enum
`app/engine/state.py::SecurityState` — **compromise is a graph-wide concept, not agent-only**: a
`SENTINEL` or `CREDENTIAL` node can itself become `COMPROMISED`), and a generic `attrs: dict`
for type-specific data (mirrors the existing `metadata: dict` convention on events — no new pattern
introduced). `AGENT` nodes are backed 1:1 by the existing `AgentNode` dataclass; graph construction
reads from `WorldState`, never duplicates it.

**Typed edges** (`app/graph/types.py::EdgeType`):

```
COMMUNICATES_WITH     — agent↔agent (mirrors WorldState.edges exactly, undirected)
DELEGATES_TO          — agent→agent, directed, task delegation
TRUSTS                — agent→agent, directed, weighted (attrs.weight: float 0..1) — the attack
                         surface for "trust manipulation"
CAN_ACCESS            — agent→TOOL | MCP_SERVER | RESOURCE, directed
USES_CREDENTIAL       — agent→CREDENTIAL, directed
MONITORS              — SENTINEL→agent, directed
QUARANTINE_AUTHORITY  — SECURITY_CONTROL(kind=quarantine)→agent, directed — who can quarantine whom;
                         the attack surface for "false quarantine"
UPDATES_THREAT_MEMORY — SENTINEL↔SECURITY_CONTROL(kind=threat_memory_store) — the attack surface
                         for "threat-memory poisoning"
```

**Compromise is defined by observable policy violations, never an arbitrary state flip.** A new
`POLICY_VIOLATION` event (`app/schemas/events.py`) is the substrate: every scenario that wants to
mark a node compromised must first justify it with a `POLICY_VIOLATION` draft carrying
`metadata.violation_type` (e.g. `"credential_scope_exceeded"`, `"quarantine_authority_spoofed"`,
`"sentinel_report_falsified"`, `"attestation_replayed"`, `"unauthorized_tool_access"`). The existing
`COMPROMISE_ATTEMPTED/SUCCEEDED/FAILED` types are unchanged and still used for the propagation/
prompt-injection scenarios (their "violation" is simply the successful attempt itself); the new
type exists for security-plane and credential/tool scenarios where the violation is the meaningful
unit, not a probabilistic draw.

**Five new `EventType` members** (additive within `schema_version = 1`, following the exact
precedent of M1's `ANOMALY_DETECTED`/`AGENT_QUARANTINED` and Phase 2's `MODEL_REQUESTED`/
`MODEL_RESPONDED`/`TOOL_EXECUTED` — no version bump, no upcaster, per `docs/SPEC.md` §1b):

```
POLICY_VIOLATION      — the generic compromise substrate described above
TRUST_UPDATED         — a TRUSTS edge weight changed (attacker-driven manipulation or defender reset)
ATTESTATION_ISSUED    — a SECURITY_CONTROL(attestation_service) issues a nonce/tick-stamped attestation
ATTESTATION_VERIFIED  — an attestation is checked; metadata.replayed=true flags reuse of a stale nonce
REMEDIATION_APPLIED   — the remediation engine's recommendation was accepted into a new experiment's config
```

`THREAT_SIGNATURE_PUBLISHED`/`RECEIVED` (already defined, unused since M0) become the substrate for
threat-memory poisoning: a compromised `SENTINEL` publishes a signature with `metadata.legitimate =
false`; downstream sentinels that act on it before the false signature is detected demonstrate the
poisoning attack succeeding. No new event type needed there — this is exactly the "optional
additive metadata" pattern already established.

### 2.3 Persistence: no new migration required

`backend/migrations/0001_initial.sql`'s two tables (`experiments`, `experiment_events`) are untouched.
The graph structure itself is **never persisted** — precisely because the existing system already
proves this pattern works: `routes_history.py:218` calls `build_world(config)` again at replay
time rather than reading a stored topology, because topology is a pure deterministic function of
`(seed, config)`. `app/graph/builder.py::build_security_graph(state, config)` extends this: tool/
credential/resource/sentinel counts and their attachment (which agent holds which credential, which
sentinel monitors which agents) are deterministically derived via the same `rng(seed, tick, id,
purpose)` keying discipline used everywhere else in the engine (e.g. `topology.py:16-22`'s
`_generate_confidential_token`). Replay reconstructs the identical typed graph from the persisted
`config` with zero new tables, zero new columns, and zero migration risk. New `EventType` members
persist through the existing generic `event_type TEXT` + `metadata JSONB` columns — already schema-
free by design.

**Remediation needs no persistence either.** A recommendation is a computed `ExperimentConfig`
diff (e.g. "set `sentinel_count: 2`", "revoke credential X by excluding it"); re-testing it is
just starting a **new** experiment with that config and using the existing comparison feature
(`frontend/src/lib/comparison/`) to compare before/after metrics. This reuses 100% of existing
infrastructure.

### 2.4 New config surface (`app/schemas/experiment.py::ExperimentConfig`, additive fields, all
defaulting to values that leave every current behavior byte-for-byte unchanged)

```python
tool_count: int = Field(0, ge=0, le=20)
credential_count: int = Field(0, ge=0, le=20)
resource_count: int = Field(0, ge=0, le=20)
sentinel_count: int = Field(0, ge=0, le=5)
active_scenarios: list[str] = Field(default_factory=lambda: ["propagation", "prompt_injection"])
adaptive_detection_threshold: float = Field(0.3, ge=0.0, le=1.0)   # §4, only used by "adaptive_attacker"
false_quarantine_rate: float = Field(0.0, ge=0.0, le=1.0)           # §5, false-quarantine attack
```

`active_scenarios` lists both sync- and async-scenario-registry keys to run each tick, in list order
(deterministic) — **implemented**, closing the gap this section used to flag: the default includes
`"prompt_injection"` so `real_agent_count > 0` keeps working exactly as before this field started
gating async scenarios too, and excluding it from an explicit `active_scenarios` list now genuinely
disables it (previously impossible short of `real_agent_count=0`). Simpler than the auto-append
design originally sketched here — no config-derived list mutation, just the default value itself
carrying both scenario names.

### 2.5 New API surface (additive; flows through the existing OpenAPI→`schema.d.ts` typegen
pipeline automatically — `make types` picks these up with zero new frontend-contract machinery)

```
GET /api/experiments/{id}/graph
    → SecurityGraphView { nodes: GraphNodeView[], edges: GraphEdgeView[] }

GET /api/experiments/{id}/analysis/attack-paths?source=&target=
    → AttackPathsResponse { paths: string[][] }

GET /api/experiments/{id}/analysis/blast-radius
    → BlastRadiusResponse { compromised: string[], reachable: string[], fraction: float }

GET /api/experiments/{id}/analysis/critical-nodes?top_n=5
    → CriticalNodesResponse { nodes: [{id: string, betweenness: float}] }

GET /api/experiments/{id}/analysis/provenance?node_id=
    → ProvenanceResponse { chain: string[] }

GET /api/experiments/{id}/metrics
    → MetricsResponse { compromise_fraction, retained_utility, blast_radius_fraction,
                         privileged_exposure, security_plane_integrity, attack_success_rate,
                         false_quarantine_rate }

GET /api/experiments/{id}/remediation
    → RemediationResponse { recommendations: [{description: string, config_diff: object}] }
```

Each mirrors `routes_history.py`'s pattern of a live path (via `registry.get(id)`, using the
runner's in-memory `WorldState`/config) — history/replay equivalents can be added the same way
later (`build_security_graph(build_world(config)[0], config)`) once frontend integration (priority
8) needs them; this plan implements the live path first since it's what tests can exercise without
a browser.

---

## 3. Pluggable scenario framework (**implemented**)

`app/scenarios/base.py`:

```python
class Scenario(Protocol):
    name: str
    def step(self, state: WorldState, config: ExperimentConfig
              ) -> tuple[WorldState, list[EventDraft]]: ...
```

A scenario that needs the typed security graph (e.g. §5's not-yet-built graph-structural attacks)
calls `build_security_graph(state, config)` itself — a cheap, pure, already-deterministic
derivation (§2.3) — rather than the interface threading a graph through every call site; no
implemented scenario needed that yet. Async (LLM-backed) scenarios implement `AsyncScenario` with
`async def step(self, state, config, gateway, tick)` instead — the
same sync/async split that already exists between `app/engine/propagation.py` (sync) and
`app/agents/runtime.py::real_agent_step` (async), now formalized as an interface rather than two
hardcoded call sites. **Neither existing function's body changes.** `app/scenarios/registry.py`
holds `SYNC_SCENARIOS: dict[str, Scenario]` and `ASYNC_SCENARIOS: dict[str, AsyncScenario]`;
`app/scenarios/propagation_scenario.py` and `app/scenarios/prompt_injection_scenario.py` are thin
adapters whose `.step()` calls the existing `propagation.step`/`real_agent_step` verbatim. This is
why every existing test that calls `propagation.step` or `real_agent_step` directly keeps passing
unmodified — they're calling the same functions; the registry is purely additive plumbing on top.

`app/engine/tick.py::advance()` changes from a hardcoded two-line body to iterating
`config.active_scenarios` through the sync registry, then calling `detection.step` — same net
effect when `active_scenarios == ["propagation"]` (today's only value in every existing test and
the API's default), so no existing test's expected output changes.

---

## 4. Adaptive attacker (deterministic, rule-based v1 — **implemented**)

`app/scenarios/adaptive_attacker_scenario.py` implements observe→choose→attack→observe-defense→
adapt as a scenario whose **state lives in `WorldState` itself**, not in a separate persisted
field — simpler than originally sketched here (no `WorldState.attacker_memory` dataclass was
needed): strategy is recomputed fresh each tick from the quarantine rate among nodes the attacker
has ever compromised (`node.compromised_by is not None`), which is exactly as reproducible as a
persisted rolling estimate since it's a pure function of already-present state, per the engine's
existing purity contract. Each tick: observe (that rate, computed from the current `WorldState`),
choose (`"stealthy"` once the rate reaches `config.adaptive_detection_threshold`, `"aggressive"`
otherwise — a deterministic threshold, not a random draw), attack (one attempt per compromised
source per tick — the highest-degree healthy neighbor if aggressive, lowest-degree if stealthy —
via `rng(seed, tick, target, f"adaptive:{source}")`, the same keying discipline as every other draw
site), adapt (nothing to persist; next tick's observe step already sees the updated state). Owns
the tick increment exactly like `propagation.step`, so it's an alternative to it, not a supplement —
`active_scenarios` should select one or the other. Fully deterministic and unit-testable without
any LLM or provider.

---

## 5. Byzantine / security-plane attacks (priority 4 — implemented incrementally after 1–3)

Built on the graph model from §2.2 — each is a scenario:

- **Sentinel compromise**: a `SENTINEL` node's `security_state` can itself become `COMPROMISED`
  (via the same propagation mechanics, if a sentinel is reachable, or via a dedicated
  `credential_escalation` scenario). Once compromised, its `ANOMALY_DETECTED` emissions become
  unreliable — `detection.step` must consult `security_state` of the sentinel that "would" detect
  a node (via `MONITORS` edges) and suppress/falsify accordingly.
- **False quarantine / false reports**: a compromised `SENTINEL` or `SECURITY_CONTROL(quarantine)`
  emits `AGENT_QUARANTINED` for a `HEALTHY` node with `metadata.legitimate = false` — the
  observable violation is "quarantine authority exercised without a preceding
  `ANOMALY_DETECTED`/`COMPROMISE_SUCCEEDED` on that target," checkable mechanically from the event
  log (this is the concrete, falsifiable definition of "false quarantine" the metrics in §6 need).
- **Threat-memory poisoning**: per §2.2, a compromised sentinel publishes a `THREAT_SIGNATURE_
  PUBLISHED` with `metadata.legitimate = false`; a defender that trusts it without cross-
  verification demonstrates the attack.
- **Attestation replay**: `ATTESTATION_ISSUED` carries a monotonic `metadata.nonce` tied to
  `sim_tick`; `ATTESTATION_VERIFIED` with `metadata.replayed = true` fires when a nonce below the
  verifier's last-seen high-water mark is presented — mechanical, deterministic, no LLM judge
  needed (same "verify by exact matching, never an LLM judge" principle as Phase 2's confidential-
  token leak check).
- **Byzantine collusion**: ≥2 compromised agents coordinate target selection (e.g. both attack the
  same third agent's credential in the same tick to exceed a per-tick rate limit a single attacker
  couldn't breach alone) — a scenario that reads `security_state == COMPROMISED` peers and
  correlates target choice deterministically (sorted compromised-id order, same tie-break
  convention as `propagation.step`).

---

## 6. Metrics (`app/metrics/compute.py` — one definition, `all_metrics()`, shared by the live
endpoint, replay and the benchmarks; definitions corrected in Phase A, §14.2)

State/graph metrics read the current `WorldState`/`SecurityGraph`. Event-log metrics fold the run's
**whole** event log through `EventLogTally` (O(agents) memory): live runs fold each published
batch as it happens, and replay folds its reconstructed log.

| Metric | Exact definition |
|---|---|
| `compromise_fraction` | `COMPROMISED` agents ÷ all agents |
| `retained_utility` | agents neither `COMPROMISED` nor `QUARANTINED` ÷ all agents |
| `blast_radius_fraction` | agents reachable from a `COMPROMISED` node over propagation-capable edges (`COMMUNICATES_WITH`, `DELEGATES_TO`, `CAN_ACCESS`, `USES_CREDENTIAL`), never into or through a `QUARANTINED` node ÷ all agents |
| `privileged_exposure` | `CREDENTIAL`/`RESOURCE` nodes inside that same blast radius |
| `security_plane_integrity` | `HEALTHY` sentinel and security-control nodes ÷ all of them (1.0 when there are none) |
| `attack_success_rate` | new compromises ÷ `COMPROMISE_ATTEMPTED`. A new compromise is a `COMPROMISE_SUCCEEDED` without `initial_compromise` (the seeded node) or `already_compromised` (a second same-tick win on a claimed target) |
| `false_quarantine_rate` | `AGENT_QUARANTINED` with `metadata.legitimate == false` ÷ all `AGENT_QUARANTINED` |
| `detection_latency` | mean ticks from a node's `tick_compromised` to its first `ANOMALY_DETECTED`; `None` if no compromised node has been detected |
| `containment_latency` | **reported as `None`** (D1): in quarantine mode, detection and quarantine happen in the same tick, so the gap is always 0. Becomes the mean ticks from first detection to first legitimate quarantine once graduated response exists (§14.4 C.5) |
| `gateway_failure_count` | real-agent attempts that never reached the model (`COMPROMISE_FAILED` with `gateway_error`) — kept out of the success rate's denominator |

---

## 7. Remediation engine (priority 7 — **implemented**, narrower than this section originally
sketched; see §9 for why)

`app/remediation/analyze.py::recommend(config: ExperimentConfig, compromise_fraction: float) ->
list[Recommendation]` — deterministic, rule-based (no LLM). Above a fixed compromise-fraction
threshold: if `defense_enabled` is `False`, recommend enabling it; otherwise, if
`detector_sensitivity < 1.0`, recommend raising it. Each `Recommendation` carries a `config_diff:
dict` directly usable as a `POST /api/experiments` body for re-testing, and re-testing is scored by
running the existing comparison flow (baseline config vs. `config_diff` applied) and comparing §6's
metrics — verifying the fix without any new re-test machinery. The graph-structural rules originally
sketched here (sentinel placement, credential-fan-in splitting) are **not implemented** — see §9.

---

## 8. Testing strategy

- **Unit, pure, no I/O** (bulk of new tests): `app/graph/` construction and every analysis function
  against small hand-built graphs with known answers (a 4-node diamond has exactly 2 simple paths;
  a bridge node is the sole articulation point; etc.) — mirrors the existing style of
  `test_topology.py`/`test_rng.py`.
- **Determinism**: every new scenario and the graph builder must pass a same-seed-twice-identical
  test, exactly like `test_determinism.py`/`test_real_agent_determinism.py`. `scripts/
  verify_determinism.py` is extended to assert on the new event types once emitted, not replaced.
- **Backward compatibility**: existing tests (`test_tick.py`, `test_propagation_*`,
  `test_real_agent_*`, `test_topology*.py`, all persistence/replay tests) must pass **unmodified**
  — they are the regression suite proving the migration didn't change existing behavior. A new test
  run with `active_scenarios == ["propagation"]` (the default) must byte-for-byte match pre-
  migration output.
- **API contract**: new endpoints get the same `make types && git diff --exit-code` CI drift check
  as every existing endpoint — no new mechanism.
- **Integration**: one test per new endpoint against a live `ExperimentRunner`, following
  `test_control_endpoints.py`'s existing pattern.

---

## 9. Migration & status

### Completed before this plan (Phases 0–2, unchanged, preserved in full)
Engine (topology/propagation/RNG/tick), event system (schema, emitter, bus), orchestrator
(pause/resume/speed/reset), quarantine defense, Postgres persistence (`PostgresWriter`, history
API), client-side replay + durable comparison, Model Gateway (mock + vLLM providers, budget/
timeout/retry/concurrency), Agent Runtime (`real_agent_step` lateral prompt injection over real
LLM-backed agents), full frontend (graph/metrics/event-stream/config/control/detail/history/
replay/comparison components), CI (backend pytest+ruff, frontend vitest+eslint+tsc+build+typegen
drift).

### Implemented this session (see git log for exact commits/scope; every item below shipped with
passing tests, ran through the full backend pytest+ruff and frontend vitest+eslint+tsc+build gates,
and — where it touches the tick loop or RNG — a `scripts/verify_determinism.py` pass)

**Priority 1 — security graph + analysis (done).** `app/graph/` (`types.py`, `security_graph.py`,
`builder.py`, `analysis.py`): the full typed node/edge model from §2.2, `build_security_graph`
deterministically extending a `WorldState` with tools/credentials/resources/sentinels/security
controls (four new zero-default `ExperimentConfig` fields), and `attack_paths`/`blast_radius`/
`critical_nodes`/`provenance`. Four API endpoints (`/graph`, `/analysis/attack-paths`,
`/analysis/blast-radius`, `/analysis/critical-nodes`) over the live runner. No new Postgres
migration, per §2.3. 24+ tests.

**Priority 2 — pluggable scenario framework (done).** `app/scenarios/` (`base.py`, `registry.py`,
`propagation_scenario.py`, `prompt_injection_scenario.py`): `propagation.step` and
`real_agent_step` wrapped unchanged behind `Scenario`/`AsyncScenario` protocols; `engine/tick.py`
now runs `config.active_scenarios` (default `["propagation"]`) through the registry. **Known
simplification, not yet closed:** the async registry is not gated by `active_scenarios` — it always
runs every registered async scenario whenever a gateway is present, matching pre-refactor behavior
exactly (each async scenario already no-ops with no eligible pair) rather than adding new
config-driven selection there.

**Priority 3 — adaptive attacker (done).** `app/scenarios/adaptive_attacker_scenario.py`:
observe→choose→attack→observe→adapt, strategy recomputed each tick directly from `WorldState` (no
separate persisted attacker-memory field — simpler than §4's original sketch, and equally
deterministic/testable). Registered as `"adaptive_attacker"`, opt-in, owns the tick increment like
`propagation.step` (mutually exclusive with it in `active_scenarios`, not combinable). 10 tests
including two driving a full experiment through `ExperimentRunner`.

**Priority 4 — Byzantine/security-plane attacks (done).** **False quarantine** (prior session) plus,
this follow-up session, all four remaining §5 attacks: `app/scenarios/sentinel_compromise_scenario.py`
(a `SENTINEL` monitoring a compromised agent can itself become `COMPROMISED`, `POLICY_VIOLATION`
violation_type `"sentinel_subverted"`, then publishes false `THREAT_SIGNATURE_PUBLISHED` every
subsequent tick — threat-memory poisoning), `app/scenarios/attestation_scenario.py` (a compromised
agent can present a stale nonce — `ATTESTATION_VERIFIED` metadata.replayed=true — using the
simulation tick itself as the monotonic nonce, no new persisted high-water-mark needed), and
`app/scenarios/byzantine_collusion_scenario.py` (two compromised agents jointly exceed credential
scope on a `CREDENTIAL` neither holds, `POLICY_VIOLATION` violation_type
`"credential_scope_exceeded"`, marking the credential itself `COMPROMISED`). `WorldState` gained
`compromised_graph_nodes: frozenset[str]` as the compromise record for non-agent graph nodes;
`app/graph/builder.py` reads it uniformly. `app/security/detection.py::step` now consults compromised
sentinels' `MONITORS` edges and suppresses `ANOMALY_DETECTED` for the agents they watch — closing the
"nothing can compromise them yet" gap this section used to flag. All three new scenarios are
composable (none owns the tick increment) and opt-in (each new rate field defaults to 0.0). 44 new
tests, including a full-runner integration test running all three alongside propagation.

**Priority 5 — metrics (done).** `compromise_fraction`, `retained_utility`, `blast_radius_fraction`,
`privileged_exposure`, `security_plane_integrity`, `attack_success_rate`, `false_quarantine_rate`
(prior session), plus, this follow-up session, `detection_latency`/`containment_latency` (mean ticks
`tick_compromised`→first `ANOMALY_DETECTED`, and that detection→first *legitimate*
`AGENT_QUARANTINED`; both return `None` rather than `0.0` when no node has completed the transition,
since `0.0` would misreport "no data" as "instant"). Wired into `GET /.../metrics` as two new optional
fields.

**Priority 6 — causal replay/observability (done, small delta).** This was already substantially
covered by the pre-existing Phase 1.5 event-log persistence/replay/comparison infrastructure. The
one gap — reconstructing a single node's compromise chain — is closed by
`GET /.../analysis/provenance`, reusing priority 1's `analysis.provenance` unchanged.

**Priority 7 — remediation engine (done).** `detector_sensitivity` and `defense_enabled` (prior
session) plus, this follow-up session, `sentinel_count`: when `security_plane_integrity < 1.0` (a
sentinel is compromised) and `sentinel_count` hasn't hit the 5-node cap, `recommend` suggests raising
it by one. This is a genuinely *causally verified* lever, not the "credential consolidation"/
"sentinel placement" idea originally sketched in §7 and previously ruled out as unverifiable — priority
4's detection-suppression wiring is exactly what makes it verifiable now: spreading monitoring across
more sentinels shrinks the fraction of agents a single subverted sentinel's suppression can reach,
proven directly via `app/security/detection.py::step` in `test_remediation.py`, and demonstrated
end-to-end against a live running server (single sentinel → zero detections → recommendation to add a
second one). Structural credential-consolidation levers remain **not implemented** — still no causal
hook for them in this codebase.

**Priority 8 — frontend integration (done for the data layer + one new panel).** OpenAPI type-sync
(previous follow-up) plus, this session, `SecurityInsightsPanel.tsx`: a new, purely additive
right-hand sidebar in `ExperimentView` (`src/app/page.tsx`) that polls `GET .../metrics`,
`.../graph`, `.../analysis/critical-nodes`, and `.../remediation` every 2s and renders all nine
`MetricsResponse` fields, a non-agent node-type summary (tool/credential/sentinel/security_control
counts and how many of each are compromised — the "typed-node" gap, addressed without touching
`NetworkGraph.tsx`), the top-3 critical nodes, and remediation recommendations. It deliberately does
**not** touch `NetworkGraph.tsx` itself (still the delicate hero visual `docs/BRIEF.md` §8 flags) —
that remains the one piece of priority 8 left undone. Pure formatting/derivation logic is extracted
and unit-tested (`AgentDetailDrawer.tsx`'s existing pattern; this codebase has no jsdom/component-
rendering test setup by deliberate choice). This session again had no browser/screenshot tool
available, so the new panel is verified via eslint/tsc/vitest/build and a dev-server smoke test
(page shell renders, no runtime error) — not an actual rendered-in-a-browser check.

**Priority 9 — adapters (done, scoped to telemetry export).** `app/telemetry/otel_export.py` +
`GET /.../otel-trace`: exports an experiment's event log as an OTLP/JSON trace (one root span per
experiment, every `Event` mapped to an OTel span event) for ingestion by any OTLP-compatible
observability backend. Deliberately does **not** attempt LangGraph or MCP integration — both are
ambiguous without more product direction (docs/BRIEF.md's own "not a generic agent framework, don't
compete with LangGraph" already flagged LangGraph as out of scope), whereas telemetry export is a
single well-defined transformation of data this codebase already has. No new dependency: OTLP/JSON
is a documented wire format, built by hand rather than pulling in `opentelemetry-sdk` (no
sampling/batching/live-push behavior needed here).

**Priority 10 — CI/staging validation (done for CI; no staging environment built).**
`.github/workflows/ci.yml` already ran backend pytest+ruff and the frontend lint/test/typegen/
typecheck/build gates before this session; it now additionally runs `scripts/verify_determinism.py`
after pytest, and a new `schema-drift` job that boots the backend and fails the build if
regenerating `frontend/src/lib/api/schema.d.ts` against it produces a diff — both were already
described as part of `docs/PLAN.md` §8's testing strategy but had only ever been run by hand
(including by this and the prior session, before every commit). A dedicated staging environment was
not built — out of scope for a local-first, no-paid-credentials-required project per the original
requirements.

### Explicitly remaining (accurate as of the last commit this session)
1. `NetworkGraph.tsx` typed-node rendering (the one remaining piece of priority 8) — still needs a
   real browser/visual-verification pass no session so far has had, and remains the dashboard's
   highest-risk surface to change blind. This session again had no browser/screenshot tool
   available (confirmed via `ToolSearch`), so this was deliberately left untouched rather than
   changed blind — see priority 13 below for what frontend work was done instead.
2. MCP integration, if ever wanted — deliberately not attempted; would need explicit product
   direction on what it should concretely mean here before any code is written. (LangGraph
   integration is now done, scoped to topology import — see priority 12.)
3. A dedicated staging environment (rest of priority 10) — CI itself is now solid; a staging
   deploy target was never in scope for a local-first, no-paid-credentials project.
4. The graph-structural remediation lever originally sketched in §7 (credential consolidation)
   remains unimplemented for want of a causal hook — no scenario or defense logic in this codebase
   reacts to credential topology today, so recommending changes to it would be unverifiable.
5. This session again had no local Postgres/Docker access, so persistence/history/migration tests
   were not re-run (untouched by this session's changes; last verified under the first session's
   environment, and CI already covers them on every push via a real Postgres service container).
6. A real Qwen/vLLM endpoint was not reachable this session — the benchmark suite, golden demo, and
   `agentshield test` all ran (and are documented below) against the deterministic mock provider
   only. Priority 14 documents the exact manual command to validate against a real model.

---

## 10. Product validation (this session): benchmark suite, golden demo, external integration

Continuing from a clean, green state (all of §9's items above), this session's work targets
**product validation**: proving the platform can evaluate a real multi-agent topology end-to-end
and produce reproducible, non-fabricated benchmark evidence. Every number below is copied verbatim
from an actual run of the commands listed (`backend/.artifacts/{benchmark,golden_demo,
external_import}/`), not invented.

**A real bug was found and fixed en route:** `app/engine/propagation.py::step`,
`app/security/detection.py::step`'s quarantine branch, and
`app/scenarios/adaptive_attacker_scenario.py::step` all constructed a fresh `WorldState` without
carrying forward `compromised_graph_nodes`, silently resetting any sentinel/credential/
security-control compromise to empty every tick they ran. Since propagation/detection run every
tick in the default pipeline, this broke `sentinel_compromise`'s and `byzantine_collusion`'s
documented "stays compromised" persistence whenever composed with propagation or the adaptive
attacker — exactly §5's own worked examples, and exactly what the golden demo below needs. No
existing test caught it: the prior session's runner-integration test only asserted "finished" and
"deterministic," never accumulation across ticks. Fixed by threading `compromised_graph_nodes`
through all three `WorldState` constructions; zero regressions (full suite +
`verify_determinism.py` both pass unmodified — the fix only changes behavior once a nonzero
`sentinel_compromise_rate`/`byzantine_collusion_rate` is combined with propagation or
`adaptive_attacker` across multiple ticks, a combination no prior test exercised).

**Priority 11 — canonical benchmark suite (done).** `app/benchmark/` (`config.py`, `matrix.py`,
`runner.py`, `report.py`) + `backend/scripts/run_benchmark.py` / `make benchmark`. 14 attack-scenario
presets (propagation at three virulence/density levels, both with and without defense, the
deterministic adaptive attacker at two strategy biases, false quarantine, sentinel compromise,
attestation replay, Byzantine collusion, a combined four-vector run, real-agent lateral prompt
injection via the mock provider, and a 2,500-agent scale run), 7 defense-posture variants of one
fixed attack (off, three detector-sensitivity levels, three sentinel counts), and a before/after
remediation comparison — all deterministic, zero real provider calls, computed via the existing
`app/metrics/compute.py` functions unchanged. `BenchmarkConfig(ExperimentConfig)` (flagged
deviation from `docs/SPEC.md` §4's `node_count ∈ [25, 100]` bound) widens `node_count` to 3000 for
the scale-run preset **only** — the live, API-facing `ExperimentConfig` (and therefore
`NetworkGraph.tsx`) keeps its `[25, 100]` bound completely unchanged. Real measured numbers from
`backend/.artifacts/benchmark/report.md` (seed 42): `scale_run_2500_agents` completes 2,500 agents
in 18 ticks / well under a second; on the fixed defense-comparison attack, `defense_off` yields
`retained_utility=0.0` vs. `defense_high_sensitivity`'s `0.96`; `sentinel_compromise_attack`
(1 sentinel) shows `security_plane_integrity=0.67` after both a compromised agent and — thanks to
the persistence fix above — a subverted sentinel; the remediation case shows
`security_plane_integrity` 0.8 → 1.0 and `retained_utility` 0.0 → 0.96 after applying the
recommended `sentinel_count` increase and re-running. 26 new tests.

**Priority 12 — golden demo scenario (done).** `app/benchmark/golden_demo.py` +
`backend/scripts/run_golden_demo.py` / `make golden-demo`. One `ExperimentConfig`
(`active_scenarios=["adaptive_attacker", "prompt_injection", "sentinel_compromise",
"attestation"]`, 10 real (mock-provider) agents, 1 sentinel, seed 42) whose real event log narrates
all ten brief beats: indirect prompt injection via a real LLM-backed lateral attempt →
propagation → an initial legitimate quarantine → the adaptive attacker's deterministic
aggressive/stealthy strategy switch → a sentinel subverted mid-run (`POLICY_VIOLATION`
`sentinel_subverted`) → that sentinel publishing a false threat signature every subsequent tick
(threat-memory poisoning / false report) → a replayed attestation nonce accepted → the existing
remediation engine flagging the `security_plane_integrity` gap and recommending `sentinel_count`
1→2 → a re-run with the fix applied showing a real, reproducible improvement:
`security_plane_integrity` 0.80 → 0.83, `retained_utility` 0.05 → 0.10. `sentinel_compromise_rate`
was tuned empirically (0.08) so the baseline reliably subverts its one sentinel within `max_ticks`
while the remediated run's second sentinel doesn't also get subverted first — at higher rates both
eventually flip, a real but different, less demonstrable claim. 3 new tests, including a full
narrative-beat-presence assertion against the real event log (not a hand-written transcript). *(Superseded — see §13: this result came from a bug.)*

**Priority 13 — real external (LangGraph) integration (done, scoped to topology import).**
`examples/langgraph_research_agents/` (a genuinely separate small Python project — real
`langgraph`/`langchain-core`, never added to `backend/pyproject.toml`, so the backend gains no new
runtime dependency): a `StateGraph` (`research_agent → web_search_tool → summarizer_agent →
sentinel_agent`) whose `export_topology.py` calls the real compiled graph's `get_graph()` API to
produce a committed `topology.json`. Backend side: `app/engine/topology.py::build_world_from_agents`
(extracted from `build_world`, byte-for-byte unchanged output — verified by the existing
`test_topology.py` passing unmodified) builds a `WorldState` from an explicit agent id/edge set
instead of a `barabasi_albert_graph` draw; `app/importers/external_topology.py` parses
`topology.json` and layers the *real* tool bindings on top of `build_security_graph`'s output as
genuine (non-synthetic) `CAN_ACCESS` edges, tagging the sentinel agent's role in `attrs` for
display. `backend/scripts/run_external_import_demo.py` / `make import-demo` runs propagation +
sentinel compromise against the imported 4-agent topology end to end — real measured result:
`compromise_fraction=1.0`, `security_plane_integrity=0.8`, and the same `sentinel_count`
remediation recommendation the golden demo produces. **Scoped deliberately**: tool/credential/
resource/sentinel-*count* synthetic attachment still comes from `ExperimentConfig` exactly as for
any AgentShield-native experiment — only the agent identity/communication topology and the specific
tool-ownership edges are real imports, not a full MCP-style live protocol bridge (that remains
open per item 2 above). 7 new tests.

**Priority 14 — real Qwen/vLLM validation path (documented, unexercised this session).** No new
gateway-selection code was needed: `app/benchmark/runner.py`'s async path reuses
`app/gateway/factory.py::build_gateway` (the same function the live API already uses), so
`ExperimentConfig(model_provider="vllm")` routes through `VLLMProvider` with zero new logic.
`backend/scripts/run_golden_demo.py --model-provider vllm` is the entry point; exact setup command
is in README's "Real (LLM-backed) agents" section. No reachable vLLM endpoint
existed this session, so this path is implemented and unit-tested (provider-override wiring only)
but not run against a real model.

**Priority 15 — product UX (done, scoped to a new panel; `NetworkGraph.tsx` untouched).**
`SecurityInsightsPanel.tsx` gained a causal-trace (provenance) viewer — a node-id input calling the
already-existing but previously-unused `GET .../analysis/provenance` / `getProvenance()` client
function, rendering the compromise-chain result. No changes to `NetworkGraph.tsx` (item 1 above) —
still no browser-verification tooling available. Verified via eslint/tsc/vitest (12 tests in this
file)/build and a dev-server smoke test (`200` on `/`), not an actual rendered-in-a-browser check.

**Productization — `agentshield test` (done).** `app/benchmark/cli.py::evaluate()` +
`backend/scripts/agentshield_test.py` / `make agentshield-test`: a fast (~1s) pass/fail gate over
two concrete, causally-grounded claims (higher detector sensitivity retains at least as much
utility as no defense; the golden demo's remediation improves `security_plane_integrity`) —
deliberately excludes the full 14-scenario matrix and the 2,500-agent scale run (those stay a
manual `make benchmark`). *(Superseded — see §13: both checks passed with detection disabled.)* Wired into CI as a new, additive `agentshield-test` job
(`.github/workflows/ci.yml`) alongside the existing `backend`/`frontend`/`schema-drift` jobs, none
of which were modified.

### Next recommended milestone (closed — see §11)
~~History/replay equivalents of the `/metrics`, `/graph`, and `/analysis/*` endpoints...~~ **Done
in §11 below**: `app/engine/replay.py` + seven new `/replay/...` routes in `routes_history.py`, and
the frontend comparison view now fetches the same rich `MetricsResponse` for both live and
historical arms. The two items below remain the highest-value open work:
1. An actual browser pass on `NetworkGraph.tsx` typed-node rendering (no browser/screenshot tool
   has been available in any session so far, this one included — see §11's confirmation).
2. A real Qwen/vLLM validation run once a GPU endpoint is available (exact command in README's
   "Real (LLM-backed) agents" section).

### Closed this session: async scenario registry gating (§3)
Previously flagged here as a "known simplification": `run_async_scenarios` now gates by
`active_scenarios` exactly like `run_sync_scenarios` does, rather than running every registered
async scenario unconditionally. The default `active_scenarios` gained `"prompt_injection"` alongside
`"propagation"` so `real_agent_count > 0` keeps working exactly as before for every existing test and
API caller (no test asserted the literal old default `["propagation"]`, so this is safe); excluding
`"prompt_injection"` from an explicit `active_scenarios` list now genuinely disables it, which was
not previously possible short of `real_agent_count=0`. `_warn_if_truly_unknown` was added so a name
valid in the *other* registry (e.g. `"prompt_injection"` seen by the sync path) doesn't spuriously
log as an unrecognized scenario. 8 new tests covering the default, the new exclusion capability, and
an empty-list no-op.

## 11. Continuation: history/replay parity, remediation audit, CI hardening

Continuing from the product-validation session above (still a clean, green state at commit
`3db28f9`), this session closed the "Next recommended milestone" plus four more of the user's
explicitly prioritized gaps. Every number below is copied verbatim from an actual run of the
commands listed, not invented.

**History/replay parity (done).** `app/engine/replay.py::reconstruct_final_state(config,
target_tick)` reconstructs a persisted experiment's exact final `WorldState` by re-running
`build_world`/`advance`/`run_async_scenarios` bounded by the already-persisted `final_sim_tick`
column, instead of always running to natural completion like `simulate()` — this matches a
manually-stopped run's true historical final tick too, not just a naturally-finished one, with zero
new persistence (world state is a pure function of `(seed, config)`, §2.3). Seven new routes in
`routes_history.py` (`/replay/graph`, `/replay/analysis/{attack-paths,blast-radius,critical-nodes,
provenance}`, `/replay/metrics`, `/replay/remediation`) mirror `routes_graph.py`'s live routes
field-for-field — a Postgres-backed test asserts a live run and its persisted replay produce
byte-identical JSON for `/graph`, `/metrics`, and `/remediation` given the same `(seed, config)`.
**Deliberate limitation:** replaying a `model_provider != "mock"` real-agent run is refused
(`ReplayUnsupportedError` → HTTP 409) — a real LLM isn't guaranteed deterministic, and replay must
never silently re-issue real API calls. Frontend: `SecurityInsightsPanel` gained a `mode: "live" |
"replay"` prop (replay mode fetches once, no polling, since a reconstructed run's state is static)
and is now also rendered on `/history/[id]`. The comparison view's live arm (`runToCompletion.ts`)
now fetches the same `/metrics` REST response the historical arm (`loadHistoricalArm.ts`, via the
new `/replay/metrics`) fetches, so `ComparisonView.tsx` shows identical rich fields
(`security_plane_integrity`, `blast_radius_fraction`, etc.) for both arms instead of the old
stream-derived total/healthy/compromised/quarantined counts.

**Cross-matrix remediation audit (done).** `app/benchmark/audit.py` +
`backend/scripts/run_benchmark_audit.py` / `make benchmark-audit`: sweeps the full **14
attack-scenario × 7 defense-posture cross product (98 combinations)** — each attack re-run under
every uniform defense posture, named `{attack}__{defense}` — plus all 21 presets standalone, for
**119 configurations total**, through `recommend()` on their own baseline metrics, re-tests every
one that triggers a recommendation, and ranks the real measured `retained_utility` delta. 30 of the
119 trigger a recommendation. The run takes ~1m45s of real engine work (the 2,500-agent scale run
under `defense_off` alone is ~28s). Writes `backend/.artifacts/benchmark/{audit.json,audit.md}`;
`audit.json` carries a `coverage` block so the artifact states its own scope. **Strongest real
result:** `adaptive_attacker_aggressive_bias__defense_off` — "100% of agents are compromised and
quarantine defense is disabled -- enable it", `retained_utility` 0.0 → 0.9875.

A second, real finding worth recording honestly: raising `sentinel_count` — the only lever
`recommend()` has for a `security_plane_integrity` gap — is **posture-dependent**, not reliably
good. It grows the security-plane node pool that metric's denominator counts over. Widening the
sweep from 21 presets to the full 98-combination cross product sharpened this: the lever is
strongly *positive* for `sentinel_compromise_attack__defense_medium_sensitivity`
(`retained_utility` 0.0 → 0.9625, `security_plane_integrity` 0.667 → 1.0), yet still measurably
*worsens* `adaptive_plus_byzantine` (`security_plane_integrity` 0.833→0.571, `retained_utility`
0.925→0.6125) — 2 of the 30 candidates regress, and `audit.md` calls that count out explicitly
rather than burying it. The golden demo's own sentinel_count 1→2 fix helps because it was
empirically tuned for that single-attacker scenario (§9's priority 12 note); this is a real,
causally-explained boundary on where that lever generalizes, not a bug to paper over. *(The golden-demo claim in the last two sentences is superseded — see §13: that result came from a bug. The audit numbers above are unaffected.)*

**`agentshield test` CI hardening (done).** `app/benchmark/cli.py::Finding` gained a `duration_s`
field; `agentshield_test.py` gained a `--json` flag printing one machine-readable line (`{"ok":
bool, "findings": [...], "duration_s": ...}`) alongside the existing human-readable text mode, which
now also prints a `passed/total in Xs` summary line. Exit codes (0 pass / 1 fail) and the two
underlying pass/fail criteria are unchanged.

**LangGraph import regression coverage (strengthened).** Two additions to the existing 7-test
suite: a golden-file test pinning the real committed numbers in
`backend/.artifacts/external_import/result.json` (`compromise_fraction == 1.0`,
`security_plane_integrity == 0.8`), and four error-path tests for `load_topology_json` (missing
file → `FileNotFoundError`; malformed JSON → `json.JSONDecodeError`; missing required field / bad
edge shape → pydantic `ValidationError`) — previously untested failure modes.

**Golden demo polish (done).** `summarize_golden_demo_narrative()` collapses each *class* of
repeated per-agent beat line — propagation, lateral prompt injection, quarantine, and sentinel
subversion — down to its first occurrence, annotated with a `(+N more this run)` count. Collapsing
only "compromise propagated to X" (the first attempt) was not enough: the per-agent injection and
quarantine lines left the "Key beats" list at ~28 lines, no shorter than the raw log it was meant
to summarize. It is now **12 lines** that read as the intended arc end to end — seeded compromise →
attestation replay → sentinel subverted (+1 more) → false threat signature → propagation (+30
more) → lateral injection (+7 more) → quarantine (+9 more) → 275 replayed nonces → adaptive
strategy → `security_plane_integrity=0.80` identified → remediation recommended →
`0.80 → 0.83` on re-test. So `make golden-demo` alone shows attack → adaptation → security-plane
failure → remediation → re-test without a scroll; the full narrative is still written below it in
`report.md`. *(Superseded — see §13: this result came from a bug.)*

**Priority 7 — typed-node graph rendering (again left untouched, documented).** This session again
had no browser/screenshot tool available (confirmed via `ToolSearch` at the start of the session),
so `NetworkGraph.tsx` was deliberately not touched — consistent with every prior session's
documented decision (§9 item 1). This remains the dashboard's highest-risk surface to change blind.

**Docker/Postgres note:** unlike the prior two sessions (§9 item 5), this session *did* have Docker
access and started `docker compose up -d postgres` + created an `agentnet_test` database, so the
full Postgres-backed test suite (previously always skipped) ran for real throughout this session's
work, including the new history/replay integration tests.

### Continuation pass (audit widening + demo polish)

A follow-up pass re-ran the entire verification sweep from a clean checkout and closed two gaps
between what the docs claimed and what the code did:

- **The audit was not actually a cross product.** It swept the 21 presets ("14 scenarios *and* 7
  defenses"), not the 98 combinations they define. It now sweeps all 14 × 7 plus the standalone
  presets (119 configs), which changed the headline result and sharpened the sentinel_count
  finding — see the audit paragraph above for the measured numbers.
- **The "Key beats" summary was not actually curated.** It collapsed only propagation lines,
  leaving it as long as the raw log; it now collapses every repeated beat class (12 lines).

**Priority 7 — typed-node graph rendering (still deliberately untouched).** Chrome automation tools
were nominally listed in this pass, but driving them would mean standing up the dev server and a
live browser session purely to change the dashboard's highest-risk surface — outside the "no broad
new scope" boundary this pass was given, and still not something to change blind. Left documented,
consistent with §9 item 1.

### Remaining after this session
1. ~~An actual browser pass on `NetworkGraph.tsx` typed-node rendering.~~ **Closed in §12 below.**
2. A real Qwen/vLLM validation run once a GPU endpoint is available — `backend/scripts/
   run_golden_demo.py --model-provider vllm` (see README's "Real (LLM-backed) agents"
   section for the exact setup). Not exercised this session either — no reachable vLLM
   endpoint.

Treat the git log and test suite as ground truth over this section if they ever disagree.

## 12. Frontend redesign: a routed operator console (browser-verified)

The one item deferred by every prior session — typed-node graph rendering, and frontend work
generally — is closed here. Chrome automation *and* a running Compose stack were both available,
so every screen below was driven and looked at in a real browser, not inferred from passing tests.

### Information architecture

The single-page dashboard (a header holding the config form, the comparison panel and the
transport controls; a four-column body; a footer log) became a **routed workspace**: a persistent
rail, a run-context bar, and one screen per step of Map → Attack → Observe → Measure → Remediate →
Re-test (`/`, `/topology`, `/activity`, `/metrics`, `/defenses`, `/remediation`, plus `/history*`).
`lib/experiment/ExperimentProvider.tsx` lifts the control reducer and the live WebSocket above the
app shell, so navigation never interrupts a run; the stream is still remounted by
`key={experimentId}`, preserving the remount-by-key convention the old page relied on. The active
run id is kept in `sessionStorage` and re-verified against `GET /{id}` on load, so a refresh does
not lose the run (and a 404 lands cleanly on the launch screen).

### Design system

`src/app/globals.css` now defines the token set (surface ramp, hairlines, foreground ramp, one
accent, a six-step severity scale, radii, a dense type scale). Two rules make the density readable
and are enforced by construction: **colour means severity or security state and nothing else**, and
**the accent is interaction only**. `src/lib/severity.ts` is the single place meaning maps to
colour; `src/lib/vocabulary.ts` is the single place a backend enum maps to human copy (event types
with metadata-aware severity, node types, edge layers, scenarios, config-field labels). Machine
names stay visible next to human labels wherever reproducibility matters. Shared primitives live in
`src/components/ui/`.

### Graph (SPEC §4 preserved)

`NetworkGraph.tsx` became `components/graph/TopologyGraph.tsx`, still Sigma over Graphology, still
built once and mutated with `setNodeAttribute` — never rebuilt per frame, never React Flow. What
changed:

- **Typed nodes render.** Sigma draws WebGL discs coloured by security state; a 2D overlay canvas
  draws the shape ring that says what *kind* of node it is (square = tool, diamond = credential,
  hexagon = resource, triangle = sentinel, shield = security control), plus labels, selection halo
  and the numbered attack path. That split is what makes typed nodes possible with no custom WebGL
  program and no new dependency. Labels are placed radially and collision-checked against both
  other labels and every node, so a crowded ring degrades by dropping the least important label
  rather than by covering a node with an opaque chip.
- **Layout is deterministic and two-stage** (`lib/graph/layout.ts`). Stage 1 runs ForceAtlas2 over
  the *agent mesh alone*; stage 2 places typed nodes on per-plane rings ordered by the mean
  direction of the agents they attach to. One force pass over the whole typed graph reads badly —
  `control-quarantine` alone has an edge to every agent and collapses the mesh around it. Initial
  positions come from a golden-angle spiral rather than `Math.random()`, which also fixes a real
  bug: the old layout differed between two runs of the same seed, contrary to SPEC §4's "positions
  stable across reruns of the same seed".
- **Investigation surfaces that had no UI at all** are now reachable: attack-path tracing between
  any two nodes (`/analysis/attack-paths`, previously unused by the frontend), blast-radius focus
  (`/analysis/blast-radius`, likewise), edge-layer toggles, and a node inspector whose causal trace
  fetches on selection instead of asking the operator to type a node id into a text box.

### Bugs found and fixed en route

- **The graph never rendered in dev.** Sigma was created in one effect and killed in another; under
  React StrictMode's mount → cleanup → mount, the cleanup killed the instance while the guarded
  build effect refused to rebuild, so the canvas stayed empty. Build and teardown now live in one
  effect keyed on structure.
- **`/analysis/attack-paths` could hang the backend.** `nx.all_simple_paths` is an uncapped DFS;
  `max_paths` bounded the output but not the search, so a dense 60-agent mesh could burn unbounded
  CPU inside one request — and the route is `async def`, so that blocked the whole event loop
  (observed: the server stopped answering `/health`). `app/graph/analysis.py` now passes
  `cutoff=MAX_PATH_HOPS` (6). This is the only backend change in this work; the OpenAPI schema is
  byte-identical (verified by regenerating `schema.d.ts`), and a new test pins the bound.
- **`/analysis/blast-radius`'s `fraction` can exceed 100%** — it divides reachable nodes of *every*
  type by the *agent* count. Rather than change the response, the UI reports reach as a share of
  the whole graph and leaves the agent-scoped figure to `/metrics`.
- **A finished run reconnected to after a reload showed "no events yet".** Correct behaviour (the
  stream only carries what arrived over this connection) but misleading copy; it now explains the
  gap and links to the run's replay, which does have the complete log.

### Capability coverage

Nothing was removed. Every previous capability has a home
(configure/start/pause/resume/reset/speed, graph, agent detail, incident timeline, metrics, event
stream, security insights, comparison, history, replay, historical comparison), and the
configurator now also exposes config the UI previously could not reach at all: `active_scenarios`
and the tool/credential/resource/sentinel counts plus their per-scenario rates — i.e. the entire
typed security graph and all six attack scenarios were unreachable from the old form. Remediation
gained the missing half of its loop: a recommendation's `config_diff` can now be re-tested in
place, running baseline and patched configs to completion and comparing them.

The pure helpers the old components exported (`deriveNeighbors`, `describeCompromisedBy`,
`formatPercent`, `formatLatency`, `formatConfigDiff`, `formatProvenanceChain`,
`summarizeNonAgentNodes`) moved to `lib/format.ts` and `lib/security/summary.ts` with their tests
carried over assertion-for-assertion; the suite grew from 128 to 159 frontend tests.

### Verification

`npm run lint`, `npx next typegen && npx tsc --noEmit`, `npm test` (159 passed), `npm run build`
(clean, 12 routes), backend `ruff check` + `pytest` (375 passed, against a real Postgres),
`scripts/verify_determinism.py` (PASS, 330 events identical), and a schema-drift check
(regenerated `schema.d.ts` identical). Every screen was additionally exercised in a real browser at
1536×735 — launch, live run, topology + inspector + attack path, activity, metrics, defense
comparison, remediation validate-fix, runs list, replay playback, historical compare — with no
horizontal overflow anywhere. **Not verified:** narrow-viewport rendering was built to breakpoints
(rail collapses below `lg`, inspector overlays below `xl`, grids collapse, tables scroll in their
own containers) but could not be *looked at* — the browser window in this environment refused to
resize below the desktop width.

## 13. Review fixes (2026-10-02)

A repository review found six defects that corrupted results or wedged the service; all six are
fixed, one commit each, with a regression test that fails on the old code.

1. **`real_agent_step` dropped `compromised_graph_nodes`** — the same bug §10 fixed in the three
   sync step functions. Any tick a real agent won a target, every subverted sentinel and
   compromised credential silently reverted to healthy.
2. **`/replay/*` returned 500 for every mock real-agent run** — replay called `asyncio.run()` from
   inside the async route's loop. It now runs via `asyncio.to_thread`, which also keeps a full
   re-simulation from stalling live runs.
3. **History replay hid the first tick's compromises** — the replay-snapshot cutoff was
   `MAX(seq) WHERE sim_tick=0`, but the first tick's propagation events are also stamped
   `sim_tick=0` (SPEC §3.4 stamps the pre-increment tick). The cutoff is now the last initial event.
4. **Live event-log metrics read 0.0/None once a run passed 2,000 events** — the EventBus ring had
   rolled over. The runner now folds every batch into an `EventLogTally` (O(agents) memory; the
   whole-log functions replay uses wrap the same tally). `/otel-trace` returns 409 instead of an
   empty trace once the ring no longer holds the run's start.
5. **Runs with no attacker scenario hung at tick 0** (the console's observe-only run, add-on
   scenarios alone, or a typo); both attackers together double-ticked. `advance()` now advances the
   tick when no scenario did — output for every config with an attacker is byte-identical — and
   `POST /api/experiments` rejects unknown names, duplicates, and both attackers with 422.
6. **A malformed vLLM reply wedged the run** (`content: null` → `TypeError` past the gateway): it
   stayed "running" forever, persistence never finalized, and `/stop` returned 500. The provider
   now normalizes null content/usage; the runner stops a run cleanly on any unexpected tick error
   (`EXPERIMENT_STOPPED` with `reason: error`) and commits a tick to state only together with its
   events, so a stop during in-flight model calls no longer leaves state ahead of the log.

**Corrections to earlier sections.** Fix 1 changed the golden demo's outcome, and showed its
recorded result was produced by the bug: with its sentinel kept subverted, the demo's recommended
remediation (`sentinel_count` 1→2) gets the second sentinel subverted too — `security_plane_integrity`
**0.80 → 0.67**, outbreak unchanged — not 0.80 → 0.83 (§10 priority 12, §11). Across 40 seeds of
that config the remediation was worse in 17 of 21 recommending seeds even before the fix. The
demo also asserted beats as fixed text: on this run the adaptive attacker never switches strategy
and the defense quarantines no agent. `golden_demo.py` now narrates only from the event log and
reports the re-test as measured, verdict included ("the remediation made things worse").

The `agentshield test` gate (§10 productization) passed with detection disabled: both checks used
`>=` (0.00 ≥ 0.00), and the golden-demo check rested on the denominator effect above. Its checks
are now strict — the high-sensitivity defense must beat no defense on both `compromise_fraction`
and `retained_utility`, and the recommended remediation must strictly improve `retained_utility`
on `REMEDIATION_CASE` without lowering integrity — and `test_agentshield_cli.py` breaks detection
(never/always quarantining) and remediation (no-op/none) to prove the gate then fails.
`REMEDIATION_CASE` is a deterministic regression case, not evidence the lever generalizes: only 2
of 30 seeds of that config trigger a recommendation at all.

The §11 remediation audit is unaffected by these fixes: its 119 configurations and 30 re-tested
candidates reproduce byte-identically before and after them.

Verified against a real Postgres: backend `ruff` + `pytest` (all passing), `verify_determinism.py`,
frontend lint/test/typecheck, and the schema-drift check — this also closes §9's note that
persistence tests had not been re-run locally.

## 14. Next phases (APPROVED 2026-10-06)

> **Status: approved by the repo owner on 2026-10-06**, including decisions D1–D7 (§14.7) as
> recommended and the SPEC extensions listed in §14.4. Order: **A → B → C → D**; each phase starts
> only once the previous one is merged, and Phase D's scope is agreed separately before it starts.
> Each phase lists its exit criteria.

Two inputs drive this section. First, the repository review behind §13 left medium/low findings
open — some make displayed numbers wrong, others leak resources or block the server — and all were
re-confirmed on `main` after §13 merged. Second, the published work AgentShield cites as inspiration
(Michael Barnathan's two papers, §14.8) shows that AgentShield models how compromise *spreads*
about as well as its sources do, but not the *defenses* those sources are about.

### 14.1 Where AgentShield stands against the prompt-worm literature

**Already at parity or beyond:**
- **Spread model.** Same SI core as Barnathan's own `rac-simulator`: per-tick, per-edge attempts on
  scale-free graphs, with hubs as superspreaders. The defaults even coincide (`p_same=0.15` vs his
  per-attempt 0.15).
- **Attacks on the defenders themselves.** Sentinel subversion, attestation replay, Byzantine
  collusion and false quarantine go beyond both papers.
- **Replay, comparison and remediation.** The loop around experiments goes further than either
  paper's tooling.

**Missing — the defensive substance of "Semantic Immunity" and "Stopping Agent Smith":**
- **Detection.** It is a per-tick probability draw (`detector_sensitivity`); no behaviour is
  observed.
- **Threat signatures.** Only *fake* ones exist (from subverted sentinels), and nothing consumes
  them. `THREAT_SIGNATURE_RECEIVED` is never emitted.
- **No population immunity of any kind:** no vaccination, crowd defense or waning.
- **No worm strains or mutation.**
- **No reproduction numbers.** Neither R0 nor Reff is measured.
- **No inference-capability distinction.** Every compromised agent spreads.
- **No detector false positives,** and quarantine is permanent: `SUSPICIOUS`, `AGENT_RELEASED` and
  `AGENT_RECOVERED` are declared but unused.

"Semantic Immunity" has no experiments. Its stated future work is "deploying Semantic Immunity in a
controlled agent network with synthetic worm injection, measuring detection latency, false positive
rates, and the rate at which signature accumulation drives Reff below 1" — the experiment
AgentShield exists to run. Phase C adds the mechanisms needed to run it on an abstract model of
those defenses. It does not evaluate the AEGIS SDK itself.

### 14.2 Phase A — Correct the metrics (backend)

Every item below was reproduced on `main` at `7ce9d89`.

1. **Blast radius walks through quarantined agents.** On the chain C–Q–H–H it reports a fraction of
   1.00; the correct value is 0.25. **Fix:** traversal (`analysis.blast_radius`, and intermediate
   hops in `attack_paths`) stops at `QUARANTINED` agents, which the engine never lets relay. The
   blast-radius endpoints (live and replay) reuse `metrics.blast_radius_fraction`; they currently
   divide *all* reachable nodes by the agent count and can exceed 1.0.
2. **Attack success rate counts non-attacks.** With p=0 it reads 0.0028 because the seeded
   compromise counts as a success; duplicate same-tick wins and gateway errors are also counted.
   **Proposed definition:** new compromises (`COMPROMISE_SUCCEEDED` without `initial_compromise` or
   `already_compromised`) / `COMPROMISE_ATTEMPTED`. Gateway errors emit no `COMPROMISE_ATTEMPTED`,
   so they drop out of the denominator; count them in a separate `gateway_failure_count`.
3. **Containment latency is always 0.0.** Detection and quarantine happen in the same tick, so the
   metric carries no information. It only becomes meaningful with C.5's graduated response (D1).
4. **Remediation recommends `sentinel_count` with the defense disabled,** where sentinels cannot
   help. **Fix:** recommend `defense_enabled` first, and apply the sentinel rule only when the
   defense is on. `test_remediation.py:71` pins the current order, so that test changes (D2).
5. **Mock provider draws are keyed without the source.** Several attackers hitting one target
   always succeed or fail together (P = 0.30 vs 0.50 independent). **Fix:** key per source, as SPEC
   §3.4 rule 4 does for `infect:{source}`. This moves real-agent results and the golden demo
   numbers (D2).
6. **Adaptive attacker attacks real–real edges too.** Propagation skips them, and PHASE_2 said each
   edge has exactly one attack path. **Fix:** apply the same skip.
7. **Real-agent compromises spread a tick early.** Async drafts are stamped with the
   post-increment tick, so a node compromised by a real agent at T is already a source at T.
   **Fix:** apply SPEC §3.4 rule 7 (new compromises become sources from the next tick).
8. **Attestation at tick 0.** A tick-0 "replay" presents nonce 0 — the current tick — yet is
   flagged `replayed`. **Fix:** never flag a nonce equal to the current tick.

**Exit:**
- §6's metric table is rewritten with the exact definitions, and every definition has a test on a
  hand-built world.
- The golden demo and the agentshield gate are re-pinned deliberately.
- A before/after digest comparison (as in §13) shows only the intended changes.

**Phase A — done (2026-10-06).** Each fix has its own commit and a regression test that fails
on the old code; the pinned tests changed under D2 are named in their commits.
- **Events.** Synthetic-only runs (default, dense, adaptive, Byzantine, random seed) produce
  byte-identical event streams before and after; only their metric values change. Runs with real
  agents (A.5–A.7) and tick-0 attestation (A.8) change as intended.
- **Corrected values,** for example:
  - blast radius 1.0 → 0.017 on the random-seed run and 1.0 → 0.53 on the Byzantine combined run;
  - attack success rate 0.17 → 0.0 on the adaptive run, whose only "success" was the seeded node.
- **Remediation audit.** Still 119 configurations and 30 re-tested candidates; 4 changed.
  - Three defense-off configs now get "enable the defense" instead of "add a sentinel".
    `adaptive_plus_byzantine__defense_off` goes from no gain (integrity 0.667 → 0.571) to retained
    utility 0 → 0.925 and integrity 0.667 → 0.833; the other two no longer lower integrity.
  - The audit's 2 retained-utility regressions are unchanged: `adaptive_plus_byzantine` with the
    defense on, i.e. the sentinel lever itself (§11).
- **Golden demo.** Verdict unchanged: integrity 0.80 → 0.67 on re-test. Its baseline compromise is
  now 0.975 instead of 1.0, and the narrative now shows a legitimate quarantine at tick 1 and real
  strategy switches.

### 14.3 Phase B — Stability, deployment, reproducibility

1. **WebSockets.**
   - Detect client disconnects while the stream is idle (a concurrent receive), and end streams for
     terminal runs.
   - Bound subscriber queues: on overflow, close with a resync code so the client reconnects and
     receives a fresh snapshot.
   - Today idle connections never exit, which leaks the subscriber and the runner and hangs server
     shutdown.
2. **Run lifecycle.** Evict finished and stopped runs from memory after a TTL (history stays in
   Postgres), and cap concurrently running experiments (429).
3. **Heavy work off the event loop.**
   - Today one attack-paths query to an unreachable target takes **5.0 s** and blocks every live
     run and WebSocket.
   - Run analysis queries via `asyncio.to_thread`, bounded by a `has_path` pre-check and a cap on
     paths returned.
   - Cache replay reconstructions per finished run.
4. **Database.**
   - Give the pool acquire and command timeouts.
   - Make `writer.start()` time-bounded, so a hung database can never block `POST /api/experiments`.
   - Bound the writer queue; overflow marks the run incomplete instead of growing without limit.
5. **Model gateway.**
   - The budget counts provider attempts, not calls (today a budget of 2 made 8 HTTP calls).
   - Retry only on timeouts, 429 and 5xx — not 4xx.
   - Enforce a total per-call deadline.
   - Emit `MODEL_REQUESTED` per attempt.
6. **Input validation.**
   - `seed` within BIGINT.
   - `since_seq` bounded.
   - `top_n ≥ 1`.
   - `replay-snapshot` reports a live run's actual status.
7. **Docker.**
   - The backend image copies `migrations/`, runs without `--reload`, and runs as non-root.
   - The frontend image runs `next build`/`next start`.
   - Hot reload moves to a compose dev override.
8. **Reproducibility.**
   - Set `GIT_SHA` at build time and in CI.
   - Replay warns when a run's `app_version` differs from the server's.
   - Add a backend lockfile (D3) — topology generation depends on `networkx`.
9. **Test isolation.**
   - `conftest.py` pins the app's database to `agentnet_test` before the app is imported; today
     bare `pytest` can write into the dev database.
   - In CI, an unreachable Postgres fails the run instead of silently skipping 23 tests.
10. **Docs.**
    - Remove dead references: the missing README section, and the gitignored `*_PLAN.md` files
      cited in about 60 code comments.
    - Reword the README's "real LLM-backed agents" claim for the default mock provider.

**Exit:** every review finding is closed or explicitly waived in this section; tests cover WebSocket
disconnect, eviction and the database-hang path; CI is green.

**Phase B — done (2026-10-06),** in three PRs: B-1 (#4, items 1–6), B-2 (#5, items 7–9) and B-3
(item 10). Each fix has a test that fails on the old code. The exit tests are
`test_ws_lifecycle.py`, `test_run_lifecycle.py` and `test_db_timeouts.py`.
- **Event streams.** Synthetic-only runs are byte-identical (`verify_determinism.py`). Real-agent
  runs change as intended: `MODEL_REQUESTED` is emitted once per provider attempt, with
  `metadata.attempt`.
- **New API behaviour:**
  - 429 when `max_active_experiments` runs are active;
  - 422 for an out-of-range `seed`, `since_seq` or `top_n`;
  - WebSocket close codes 4000 (resync), 4001 (run ended) and 4004 (unknown run);
  - an `X-Replay-Version-Mismatch` header on replay responses.
- **Waived or narrowed:**
  - The WebSocket `since_seq` is not bounded: any value already falls back to a fresh snapshot.
    Only the history endpoints' `since_seq`, which reaches an INT column, is.
  - The replay warning is a response header, exposed through CORS. Showing it in the UI belongs
    to Phase D. Two unversioned `dev` builds can't be told apart, so they aren't flagged.
- **Beyond the list:**
  - App shutdown clears the run registry. Without that, runs left unfinished by one app instance
    held active-run slots for the rest of the process.
  - The lock is two files: `requirements.lock` for the image, and `requirements-dev.lock` for CI
    and development, constrained to the same versions.
  - A CI `docker` job builds and starts the stack. It checks health, that both services run as
    non-root, and that a run records the commit as its `app_version`.
  - The B.10 cleanup found one comment that was wrong rather than only stale: the frontend reducer
    described `MODEL_REQUESTED` as one per compromise attempt, which B.5 changed.

### 14.4 Phase C — Epidemiology and population immunity (the prompt-worm defenses)

Design rules:
- Every new config field defaults to a strict no-op. Default and existing configs stay
  byte-identical, checked with the §13 digest comparison.
- Every new random draw uses `rng(seed, tick, id, purpose)` with a new, distinct purpose.
- New behaviour is expressed in existing event types plus new metadata keys. Those keys are emitted
  only while the feature is enabled.
- No new dependencies.

**C.1 Epidemic metrics** — sources §14.8 [S1], [S2]. Computed from provenance already in the
state (`compromised_by`, `tick_compromised`), so live and replay agree.
- **Generation:** the seeded node is generation 0; every other infection is its source's
  generation + 1.
- **Offspring:** the number of nodes a node infected. Each infection has exactly one source, the
  first winner (SPEC §3.4 rule 6).
- **R(t):** the mean offspring of nodes infected at tick t. A cohort is flagged `censored` while any
  member is still infectious at run end.
- **R0 estimate:** the mean offspring of generations 0–1.
- **Serial interval:** the mean tick gap between a source's and its target's infection.
- **Final size:** the fraction ever infected.
- **Peak prevalence and peak tick:** per-tick counts are folded into `EventLogTally` — O(ticks)
  memory, at most 2,000 entries.

**C.2 Inference capability and topology** — [S2] "only inference-capable nodes propagate".
- Add `AgentNode.inference_capable` (default true). A compromised node that cannot run inference
  is a dead end: never a source in propagation, the adaptive attacker or the real-agent step.
  Real agents are always capable.
- The seeded node is always capable, so every run has at least one propagator.
- Config `inference_fraction` (default 1.0) and `inference_placement` ∈ {`random`, `hubs`,
  `periphery`}.
- Config `topology` ∈ {`barabasi_albert` (default), `erdos_renyi`}. Erdős–Rényi uses
  `networkx.gnm_random_graph` with the same edge count as BA (`edge_density × (n − edge_density)`),
  so `edge_density` keeps one meaning.

**C.3 Worm strains and mutation** — [S1] "worms are inherently polymorphic".
- **Strain:** a k-bit vector (`signature_bits`, default 64), an abstract stand-in for [S1]'s SimHash
  codes. Hamming distance stands for semantic distance.
- **Patient zero's strain** sits `strain_benign_distance` bits from a shared "benign behaviour"
  centroid. This sets how disguised the worm is: [S1]'s "topically-adjacent" injections are small
  distances.
- **Mutation:** each successful transmission mutates with probability `mutation_rate` (default 0),
  flipping `mutation_bits` keyed bit positions.
- `COMPROMISE_SUCCEEDED` carries `strain` / `mutated` metadata while the feature is on.

**C.4 Shared immune memory** — [S1] signature database, [S2] crowd defense and SIRVS.
`immunity_enabled` defaults to false.
- **Publication.** A detection publishes a legitimate signature, which is the detected agent's
  strain: `THREAT_SIGNATURE_PUBLISHED` with `{legitimate: true, signature}`.
- **Adoption.**
  - Participating agents adopt a signature after `signature_delay_ticks`.
  - Participation is set by `immunity_coverage` v and `immunity_placement` (random / hubs /
    periphery).
  - Holdings live in the state, with one aggregated `THREAT_SIGNATURE_RECEIVED {signature,
    adopters}` per signature per tick to bound event volume.
  - `preseed_patient_zero_signature` models [S1]'s red-team pre-seeding.
- **Protection.** Before a transmission draw, a participating target holding any signature within
  `signature_radius` of the attacking strain blocks it: `COMPROMISE_FAILED {blocked_by_signature}`,
  with no draw.
  - Mutation that escapes every radius is the waning δ of [S2]'s SIRVS model, so it emerges here
    rather than being an input.
- **Autoimmunity.**
  - Each tick every participating healthy agent receives `benign_probes_per_tick` benign vectors
    drawn near the centroid; a probe within the radius of a held signature is blocked.
  - Blocked and total counts live in state counters, not events. This makes [S1]'s trade-off
    measurable: a wider radius catches more variants and blocks more legitimate traffic.
- **Poisoning becomes causal.** Today a subverted sentinel's false signatures (existing
  `sentinel_compromise`) have no effect. With immunity on, agents adopt them, and they cost only
  benign traffic — an autoimmune attack on the immune system itself.

**C.5 Realistic detection and graduated response** — [S1] BOCPD needs evidence; "autoimmune"
false positives.
- **`detector_ramp_ticks`** (default 0 = today's behaviour). Detection probability rises to
  `detector_sensitivity` over that many ticks after compromise.
- **`detector_false_positive_rate`** (default 0). This is the detector's own error on healthy
  agents (`ANOMALY_DETECTED {false_positive}`), distinct from the false-quarantine *attack*. A false
  positive publishes a signature of benign behaviour, so autoimmunity emerges from it.
- **`response_mode`** ∈ {`quarantine` (default), `graduated`}. In graduated mode:
  - A first detection puts the agent in `SUSPICIOUS` (advisory). Its transmission is scaled by
    `suspicious_transmission_factor`.
  - A second detection quarantines it.
  - With no repeat detection within `review_ticks`, the agent is released (`AGENT_RELEASED`) back
    to `COMPROMISED` if infected (`tick_compromised` set), else `HEALTHY`.
  - Containment latency (A.3) becomes meaningful, and compromise metrics count infected
    `SUSPICIOUS` agents.

**C.6 Benchmarks, gate, docs.** A new `epidemiology` benchmark suite:
1. **[S2] threshold reproduction.** Sweep `inference_fraction` across topology × placement, defense
   off, 30 ticks, 10 seeds, 180 nodes via `BenchmarkConfig`. Expect a sharp rise near
   ρc ≈ 1/⟨k⟩ on ER, near-zero threshold with hub placement on BA, and small outbreaks with
   periphery-only placement. [S2]'s ER graph (⟨k⟩ = 5) has no exact `edge_density` equivalent, so
   the suite brackets it with ⟨k⟩ ≈ 4 and ≈ 6 and checks the qualitative threshold, not his exact
   table.
2. **[S1] trade-off sweep.** Immunity coverage × signature radius × mutation rate, reporting Reff,
   final size and benign block rate.
3. **Signature delay vs Reff.**
4. **Hub-first vs periphery immunity placement** (the [S2] Fig. 6–7 analogue).
5. **Immune-memory poisoning:** `sentinel_compromise` with immunity on.

The agentshield gate gains one strict check: on the canonical immunity case, immune memory drives
Reff below 1, and a zero-coverage control does not. It gets the same break-the-mechanism negative
tests as §13.

**API (additive; flows through the existing typegen and drift check):**
```
GET /api/experiments/{id}/epidemic            (+ /replay/epidemic twin)
    → EpidemicResponse { prevalence: [{tick, infectious, quarantined, immune}],
                         r_effective: [{tick, value, censored}],
                         generations: [{generation, nodes, mean_offspring}] }
MetricsResponse += r0_estimate, serial_interval, final_size, peak_prevalence, peak_tick,
                   immunity_coverage, signature_block_rate, benign_block_rate,
                   strains_observed, gateway_failure_count     (None when not applicable)
```

**Config (additive, all no-op by default):**
```python
inference_fraction: float = Field(1.0, ge=0.0, le=1.0)
inference_placement: Literal["random", "hubs", "periphery"] = "random"
topology: Literal["barabasi_albert", "erdos_renyi"] = "barabasi_albert"
signature_bits: int = Field(64, ge=8, le=256)
strain_benign_distance: int = Field(32, ge=0, le=256)        # ≤ signature_bits, validated
mutation_rate: float = Field(0.0, ge=0.0, le=1.0)
mutation_bits: int = Field(1, ge=1, le=64)
immunity_enabled: bool = False
immunity_coverage: float = Field(1.0, ge=0.0, le=1.0)
immunity_placement: Literal["random", "hubs", "periphery"] = "random"
signature_radius: int = Field(0, ge=0, le=256)              # ≤ signature_bits, validated
signature_delay_ticks: int = Field(1, ge=0, le=50)
preseed_patient_zero_signature: bool = False
benign_probes_per_tick: int = Field(1, ge=0, le=10)
detector_ramp_ticks: int = Field(0, ge=0, le=50)
detector_false_positive_rate: float = Field(0.0, ge=0.0, le=1.0)
response_mode: Literal["quarantine", "graduated"] = "quarantine"
suspicious_transmission_factor: float = Field(0.5, ge=0.0, le=1.0)
review_ticks: int = Field(5, ge=1, le=100)
```

**SPEC impact (needs explicit approval, D7).** All of these are opt-in extensions; none replaces a
SPEC mechanism.
- **§3.3:** an alternative Erdős–Rényi generator. BA stays the default.
- **§3.4:** two opt-in preconditions on an attempt — the source must be inference-capable, and the
  target's signatures may block it before the draw. With defaults, rules 1–7 are unchanged.
- **§3.2:** additive `AgentNode`/`WorldState` fields, and `SUSPICIOUS` used in graduated mode, as
  SPEC already reserves it.
- **§3.5:** the event schema is unchanged; only new metadata keys and new RNG purposes are added.

**Testing:**
- Unit tests per mechanism on hand-built worlds.
- **Property tests:**
  - Higher immunity coverage → smaller final size, at mutation 0.
  - Wider radius → more blocked strains and more benign blocks.
  - ρ below threshold → small outbreaks.
- Cross-`PYTHONHASHSEED` determinism for every new feature. `verify_determinism.py` becomes a
  config matrix, closing the review's gap that it only checks the default config.
- A digest check that defaults stay byte-identical.

**PRs:** one each for C.1, C.2, C.3, C.4, C.5 and C.6, in that order. Each is mergeable on its
own.

**Exit:** the epidemiology suite runs in CI-gated form; its measured results are documented here,
including any that contradict the papers' predictions.

### 14.5 Phase D — UI redesign (scope to be agreed before starting)

Inputs, beyond the user's own goals for the redesign:
- **Frontend defects from the review:**
  - An unknown `schema_version` crashes the whole app (no error boundary).
  - A sequence-gap reconnect opens duplicate sockets and can orphan one.
  - Comparison and validate-fix runs poll forever and cannot be cancelled.
  - Re-run remounts every page.
  - The outbreak curve undersamples within a tick and resets on navigation.
  - The provenance panel can show stale data.
- **New backend concepts to present:**
  - the epidemic curve with R(t) and generations;
  - strains, and immunity coverage and blocks;
  - the `SUSPICIOUS` state and release events;
  - 422 and 409 messages;
  - runs stopped with `reason: error`;
  - observe-only runs.

### 14.6 Deferred (named so they aren't forgotten; not part of A–D)

- **Tier 2 — realism:**
  - Memory, RAG and skill stores as infection reservoirs, defended by taint tracking, TTL expiry and
    schema-constrained writes ([S1] L5; Morris II). This uses the declared `MEMORY_STORE` node and
    `MEMORY_READ`/`MEMORY_WRITE` events.
  - A real self-replicating payload: check that the target's own output carries the payload and
    forward that output, rather than flipping state.
  - Adaptive system-prompt hardening for real agents ([S1] "vaccination").
  - An optional embedding detector plug-in (sentence-transformer + BOCPD + SimHash on real outputs).
    These are heavy dependencies, so it would be opt-in only.
- **Tier 3 — the RAC frontier ([S2]):**
  - Agent self-instantiation with the capability tuple ⟨P, R, I, S⟩.
  - Hayflick and attestation-depth limits.
  - Thymic selection by BFT vote.
  - Multi-step attack chains (the pⁿ reliability threshold).
  - Inference honeypots and canary tokens.
  - Economic friction as a fail-closed layer.

### 14.7 Decisions (all approved as recommended, 2026-10-06)

| # | Decision | Approved |
|---|---|---|
| D1 | Containment latency until C.5 lands | Return `None` in `quarantine` mode, and document why, rather than a constant 0 |
| D2 | Accept that A.2, A.4 and A.5 change reported numbers and the tests pinning them (ASR drops; real-agent and golden-demo numbers move) | Yes — they are wrong today |
| D3 | Backend lockfile tool | `uv pip compile` → `requirements.lock`, installed in CI and Docker |
| D4 | Signature model | Abstract bit vectors now (deterministic, no dependencies); real embeddings stay Tier 2 |
| D5 | Benign-traffic model for autoimmunity (centroid + worm distance) | Accept as the false-positive model for C.4/C.5 |
| D6 | When to start the UI redesign | After Phase C, so the redesign shows the immunity concepts once |
| D7 | The SPEC extensions listed in §14.4 | Approve as opt-in extensions |

### 14.8 Sources

- **[S1]** M. Barnathan, "Semantic Immunity: Embedding-Based Epidemiological Defense Against Prompt
  Worms in Autonomous Agent Networks", Feb 2026 — https://gaiarobotics.com/Semantic_Immunity.pdf
- **[S2]** M. Barnathan, "Stopping Agent Smith: Mitigating Recursive Hacking Through Inference
  Shaping", Gaia Robotics, Apr 2026 — https://gaiarobotics.com/RAC.pdf (simulator:
  https://github.com/gaiarobotics/rac-simulator)
- Cohen, Bitton & Nassi, "Here Comes The AI Worm" (Morris II) — https://arxiv.org/abs/2403.02817
- Lee & Tiwari, "Prompt Infection: LLM-to-LLM Prompt Injection within Multi-Agent Systems" —
  https://arxiv.org/abs/2410.07283

The AEGIS SDK repository itself was not read, because this session lacked permission to clone it.
§14 is therefore built on the papers, not on that implementation.
