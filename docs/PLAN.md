# AgentNet → Multi-Agent Adversarial Resilience Platform — Authoritative Plan

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
> **Naming note (flagged deviation):** the instruction that produced this plan referred to the
> repository as "AgentShield." The actual repository, package, and product name throughout the
> codebase, database, CI, and docs is **AgentNet**. Renaming would touch dozens of unrelated files
> (package name, Docker images, CI, every doc) for no functional benefit and isn't in the explicit
> requirements list, so this plan **keeps the name AgentNet** and treats "AgentShield" as the
> instruction's working title for the *positioning* (Multi-Agent Adversarial Resilience Platform),
> not a rename mandate. Flagging this per `CLAUDE.md`'s "surface material deviations" rule.

---

## 1. Why this pivot, and why it's a pivot and not a rewrite

AgentNet today (Phases 0–2, all shipped) is a **deterministic, event-sourced simulation of
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
active_scenarios: list[str] = Field(default_factory=lambda: ["propagation"])
adaptive_detection_threshold: float = Field(0.3, ge=0.0, le=1.0)   # §4, only used by "adaptive_attacker"
false_quarantine_rate: float = Field(0.0, ge=0.0, le=1.0)           # §5, false-quarantine attack
```

`active_scenarios` lists sync-scenario-registry keys to run each tick, in list order
(deterministic). **As implemented (see §9), the async registry is not yet gated by
`active_scenarios`** — `orchestrator/runner.py` still runs every registered async scenario
unconditionally whenever a gateway is present, exactly matching pre-refactor behavior (each async
scenario already no-ops with no eligible source/target pair) rather than the auto-append design
originally sketched here.

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

## 3. Pluggable scenario framework (**implemented** — see §9 for the one gap)

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

## 6. Metrics (priority 5 — `app/metrics/compute.py`, pure functions over `WorldState` +
`SecurityGraph` + a bounded live event buffer; no new persistence, computed on demand like the
analysis endpoints — **implemented**, see §9 for exact scope)

| Metric | Definition | Status |
|---|---|---|
| Compromise fraction | `compromise_fraction(state)` = compromised agents / all agents | done |
| Retained utility | `retained_utility(state)` = agents neither compromised nor quarantined / all agents | done |
| Blast radius fraction | `blast_radius_fraction(graph)` = agent nodes in `analysis.blast_radius(graph)` / all agents | done |
| Privileged exposure | `privileged_exposure(graph)` = credential/resource nodes in `analysis.blast_radius(graph)` | done |
| Security-plane integrity | `security_plane_integrity(graph)` = healthy sentinel/security-control nodes / all such nodes | done |
| Attack success rate | `attack_success_rate(events)` = `COMPROMISE_SUCCEEDED` / (`COMPROMISE_SUCCEEDED` + `COMPROMISE_FAILED`) | done |
| False quarantine rate | `false_quarantine_rate(events)` = `AGENT_QUARANTINED` with `metadata.legitimate == false` / total `AGENT_QUARANTINED` | done |
| Detection latency | ticks between a node's `tick_compromised` and its `ANOMALY_DETECTED` | not implemented |
| Containment latency | ticks between `ANOMALY_DETECTED` and `AGENT_QUARANTINED` | not implemented |
| Retained utility | fraction of agents neither `COMPROMISED` nor `QUARANTINED` at run end |
| Privileged exposure | count of `RESOURCE`/`CREDENTIAL` nodes reachable (via `analysis.attack_paths`) from any currently-compromised agent |
| Security-plane integrity | fraction of `SENTINEL`/`SECURITY_CONTROL` nodes with `security_state == HEALTHY` |

These reuse the existing `MetricsPanel.tsx` pattern once frontend integration (priority 8) wires
them in; the backend functions and an API endpoint are implementable and independently testable now.

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

**Priority 4 — Byzantine/security-plane attacks (partial).** Only **false quarantine** is
implemented, as an opt-in `false_quarantine_rate` extension to the existing, unmodified
`app/security/detection.py::step` (default 0.0 = strict no-op). **Not implemented:** sentinel
compromise, threat-memory poisoning, attestation replay, Byzantine collusion — none of §5's other
four attacks have any code. Sentinel/`SECURITY_CONTROL` graph nodes exist (priority 1) but are
purely structural/analysis-only; nothing in the codebase can compromise them yet.

**Priority 5 — metrics (partial).** `app/metrics/compute.py` + `GET /.../metrics`:
`compromise_fraction`, `retained_utility`, `blast_radius_fraction`, `privileged_exposure`,
`security_plane_integrity`, `attack_success_rate`, `false_quarantine_rate` — all implemented and
tested. **Not implemented:** detection latency and containment latency (§6) — both need per-event
tick correlation (first `ANOMALY_DETECTED`/`AGENT_QUARANTINED` tick minus `tick_compromised`) that
this pass deliberately didn't approximate rather than ship an unverified definition.

**Priority 6 — causal replay/observability (done, small delta).** This was already substantially
covered by the pre-existing Phase 1.5 event-log persistence/replay/comparison infrastructure. The
one gap — reconstructing a single node's compromise chain — is closed by
`GET /.../analysis/provenance`, reusing priority 1's `analysis.provenance` unchanged.

**Priority 7 — remediation engine (done, narrower than originally sketched).**
`app/remediation/analyze.py::recommend` only recommends `detector_sensitivity` and
`defense_enabled` — the two config levers with a *causally verified* effect on
`app/security/detection.py`'s actual behavior. §7's original sketch (sentinel placement, credential
consolidation) is **not implemented**: those levers have no effect on any scenario or defense logic
in this codebase today, so recommending them would be an unverifiable, fabricated "fix." This was
checked, not assumed: `test_routes_remediation.py::test_applying_the_recommendation_measurably_improves_compromise_fraction`
proves a real recommendation, applied to a fresh experiment, actually improves the targeted metric.

**Priority 8 — frontend integration (partial, data layer only).** `frontend/src/lib/api/client.ts`
gained typed fetch wrappers for all seven new endpoints, with unit tests. **Not implemented:** any
new visual component (typed-node rendering by `NodeType`, an attack-path/blast-radius panel, a
remediation panel) — this session has no way to drive a real browser to verify new UI renders
correctly, and shipping unverified changes to the dashboard's hero visual (`NetworkGraph.tsx`,
explicitly called out as a delicate first-class surface in `docs/BRIEF.md` §8) was judged worse
than not shipping them.

### Explicitly remaining (accurate as of the last commit this session; next in priority order)
1. Sentinel compromise, threat-memory poisoning, attestation replay, Byzantine collusion (§5).
2. Detection latency / containment latency metrics (§6).
3. Graph-structural remediation rules (§7) — blocked on (1): they need sentinel/credential nodes to
   actually participate in some scenario's mechanics before a recommendation about them is
   verifiable.
4. Frontend visual components (§9 priority 8 above) — needs a real browser/visual-verification pass
   this session didn't have.
5. LangGraph/MCP/OpenTelemetry adapters (priority 9) — no work started; genuinely out of scope
   until 1–4 above are solid, per the priority order in the originating instruction, and per
   `docs/BRIEF.md`'s explicit "not a generic agent framework, don't compete with LangGraph."
6. CI/staging validation beyond the existing `make test`/`make lint` gates (priority 10) — every
   change this session already runs through those gates; a dedicated staging environment or
   additional CI stages were not built.

Treat the git log and test suite as ground truth over this section if they ever disagree.
