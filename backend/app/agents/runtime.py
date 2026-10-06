"""The Agent Runtime (docs/BRIEF.md §6): the one
place real-agent LLM interaction happens. Deliberately NOT part of
app/engine/ -- a real model call is irreducible async I/O, which
app/engine/propagation.py::step()'s purity contract forbids. Called by
ExperimentRunner, once per tick, only after the pure, synchronous
engine.tick.advance() has already run.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from app.agents.prompts import INJECTION_PAYLOAD, build_system_prompt, response_leaked_token
from app.engine import strains
from app.engine.state import SecurityState, WorldState
from app.gateway.gateway import ModelGateway
from app.gateway.schemas import ModelRequest
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig
from app.security import immunity


async def real_agent_step(
    state: WorldState, config: ExperimentConfig, gateway: ModelGateway, tick: int
) -> tuple[WorldState, list[EventDraft]]:
    """Advance real-real lateral-compromise attempts for one tick.

    Same (state, config) -> (state', drafts) shape as propagation.step(),
    but explicitly async and, with a real provider behind the gateway, not
    reproducible byte-for-byte -- only the deterministic mock-provider path
    is. Never raises for a gateway/provider
    failure: ModelGateway already degrades that to a `None` response, which
    this function turns into a COMPROMISE_FAILED draft, same as a
    probabilistic miss.
    """
    sources = sorted(
        node_id
        for node_id, node in state.nodes.items()
        if node.agent_kind == "real" and node.security_state == SecurityState.COMPROMISED
    )

    # (source, target, probability, request) in deterministic sorted order --
    # this fixed order, not network completion order, is what keeps event
    # emission order deterministic under the mock provider (asyncio.gather
    # preserves input order in its results list regardless of completion
    # timing, so no manual reordering is needed after the gather below).
    # A request of None is an attempt immune memory blocked (docs/PLAN.md
    # §14.4 C.4): it never reaches the model, so it costs no budget.
    attempts: list[tuple[str, str, float, ModelRequest | None]] = []
    for source in sources:
        source_node = state.nodes[source]
        targets = sorted(
            t
            for t in source_node.neighbors
            if state.nodes[t].agent_kind == "real"
            and state.nodes[t].security_state == SecurityState.HEALTHY
        )
        for target in targets:
            target_node = state.nodes[target]
            same = target_node.software_type == source_node.software_type
            probability = config.p_same if same else config.p_cross
            if immunity.blocks(state, config, target, source_node.strain, tick):
                attempts.append((source, target, probability, None))
                continue
            request = ModelRequest(
                agent_id=target,
                seed=config.seed,
                tick=tick,
                system_prompt=build_system_prompt(target_node),
                user_message=INJECTION_PAYLOAD,
                max_tokens=config.model_max_tokens,
                mock_leak_probability=probability,
                purpose="propagation",
                source_agent_id=source,
            )
            attempts.append((source, target, probability, request))

    if not attempts:
        return state, []

    results = iter(
        await asyncio.gather(
            *(gateway.complete_with_attempts(a[3]) for a in attempts if a[3] is not None)
        )
    )

    drafts: list[EventDraft] = []
    claims: dict[str, str] = {}
    claimed_strains: dict[str, int] = {}
    track_strains = strains.tracked(config)

    for source, target, probability, request in attempts:
        if request is None:
            metadata = {"probability": probability, "real_agent": True}
            drafts.append(
                EventDraft(
                    sim_tick=tick,
                    event_type=EventType.COMPROMISE_ATTEMPTED,
                    source_agent_id=source,
                    target_agent_id=target,
                    metadata=metadata,
                )
            )
            drafts.append(immunity.blocked_draft(tick, source, target, metadata))
            continue
        result = next(results)
        # One per provider call, retries and failed calls included, so the
        # log accounts for every request the budget was charged for.
        for attempt in range(1, result.attempts + 1):
            drafts.append(
                EventDraft(
                    sim_tick=tick,
                    event_type=EventType.MODEL_REQUESTED,
                    agent_id=target,
                    metadata={
                        "source_agent_id": source,
                        "purpose": "propagation",
                        "attempt": attempt,
                    },
                )
            )

        response = result.response
        if response is None:
            drafts.append(
                EventDraft(
                    sim_tick=tick,
                    event_type=EventType.COMPROMISE_FAILED,
                    source_agent_id=source,
                    target_agent_id=target,
                    metadata={
                        "probability": probability,
                        "real_agent": True,
                        "gateway_error": True,
                    },
                )
            )
            continue

        drafts.append(
            EventDraft(
                sim_tick=tick,
                event_type=EventType.MODEL_RESPONDED,
                agent_id=target,
                metadata={
                    "latency_ms": response.latency_ms,
                    "tokens_used": response.tokens_used,
                    "provider": response.provider,
                },
            )
        )

        target_node = state.nodes[target]
        assert target_node.confidential_token is not None
        leaked = response_leaked_token(response.text, target_node.confidential_token)

        drafts.append(
            EventDraft(
                sim_tick=tick,
                event_type=EventType.COMPROMISE_ATTEMPTED,
                source_agent_id=source,
                target_agent_id=target,
                metadata={"probability": probability, "real_agent": True},
            )
        )

        if not leaked:
            drafts.append(
                EventDraft(
                    sim_tick=tick,
                    event_type=EventType.COMPROMISE_FAILED,
                    source_agent_id=source,
                    target_agent_id=target,
                    metadata={"probability": probability, "real_agent": True},
                )
            )
            continue

        drafts.append(
            EventDraft(
                sim_tick=tick,
                event_type=EventType.TOOL_EXECUTED,
                agent_id=target,
                metadata={"tool_name": "reveal_confidential_token"},
            )
        )

        # Same claims/tie-break convention as propagation.step(): first
        # success in sorted source order wins the target; a later success on
        # an already-claimed target is recorded but does not re-win it.
        already_claimed = target in claims
        metadata: dict[str, object] = {"probability": probability, "real_agent": True}
        if track_strains:
            strain, mutated = strains.transmit(config, tick, state.nodes[source], target)
            metadata.update(strains.success_metadata(config, strain, mutated))
        if already_claimed:
            metadata["already_compromised"] = True
        else:
            claims[target] = source
            if track_strains:
                claimed_strains[target] = strain
        drafts.append(
            EventDraft(
                sim_tick=tick,
                event_type=EventType.COMPROMISE_SUCCEEDED,
                source_agent_id=source,
                target_agent_id=target,
                metadata=metadata,
            )
        )

    if not claims:
        return state, drafts

    new_nodes = dict(state.nodes)
    for target, source in claims.items():
        new_nodes[target] = replace(
            new_nodes[target],
            security_state=SecurityState.COMPROMISED,
            compromised_by=source,
            tick_compromised=tick,
            strain=claimed_strains.get(target),
        )
    new_state = replace(state, nodes=new_nodes)
    return new_state, drafts
