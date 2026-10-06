"""Shared immune memory (docs/PLAN.md §14.4 C.4, after [S1]'s signature
database and [S2]'s crowd defense and SIRVS model).

- **Publication.** A detection publishes the detected agent's strain as a
  legitimate signature (detection.step). A subverted sentinel publishes
  poisoned ones (sentinel_compromise_scenario).
- **Adoption.** Participating agents -- `immunity_coverage` of them, placed
  by `immunity_placement` -- hold every signature from `signature_delay_ticks`
  after it was published. One THREAT_SIGNATURE_RECEIVED per signature
  records the adoption, which bounds event volume.
- **Protection.** Before a transmission draw (or model call), a
  participating target holding a signature within `signature_radius` of the
  attacking strain blocks the attack. A mutation that escapes every radius
  is SIRVS's waning immunity, which therefore emerges rather than being set.
- **Autoimmunity.** Each tick every healthy participant screens
  `benign_probes_per_tick` benign vectors against what it holds. A wider
  radius catches more variants and blocks more legitimate traffic, so a
  poisoned signature costs benign traffic and stops no worm.

Benign traffic is the D5 model: the benign centroid with a keyed number of
bits, uniform in [0, strain_benign_distance], flipped -- so it spans the gap
between normal behaviour and the worm.
"""

from __future__ import annotations

from dataclasses import replace

from app.engine import strains
from app.engine.rng import rng
from app.engine.state import Signature, WorldState, is_susceptible
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig


def benign_vector(config: ExperimentConfig, tick: int, key: str, purpose: str) -> int:
    draw = rng(config.seed, tick, key, purpose)
    flips = draw.randint(0, config.strain_benign_distance)
    positions = draw.sample(range(config.signature_bits), flips)
    vector = strains.benign_centroid(config)
    for position in positions:
        vector ^= 1 << position
    return vector


def held(state: WorldState, tick: int) -> list[Signature]:
    """Signatures every participant holds at `tick`."""
    return [s for s in state.signatures if s.adopt_tick <= tick]


def _matches(signatures: list[Signature], vector: int, radius: int) -> bool:
    return any(strains.distance(s.vector, vector) <= radius for s in signatures)


def blocks(
    state: WorldState, config: ExperimentConfig, target_id: str, strain: int | None, tick: int
) -> bool:
    """Whether `target_id`'s immune memory stops an attack carrying `strain`."""
    if not config.immunity_enabled or strain is None:
        return False
    if not state.nodes[target_id].immune_participant:
        return False
    return _matches(held(state, tick), strain, config.signature_radius)


def blocked_draft(
    tick: int, source: str, target: str, metadata: dict[str, object]
) -> EventDraft:
    return EventDraft(
        sim_tick=tick,
        event_type=EventType.COMPROMISE_FAILED,
        source_agent_id=source,
        target_agent_id=target,
        metadata={**metadata, "blocked_by_signature": True},
    )


def publish(
    signatures: list[Signature],
    config: ExperimentConfig,
    tick: int,
    vector: int,
    *,
    legitimate: bool,
    agent_id: str | None,
) -> EventDraft | None:
    """Adds a signature unless an identical one is already published, and
    returns its THREAT_SIGNATURE_PUBLISHED draft."""
    if any(s.vector == vector and s.legitimate == legitimate for s in signatures):
        return None
    signature = Signature(
        vector=vector, legitimate=legitimate, adopt_tick=tick + config.signature_delay_ticks
    )
    signatures.append(signature)
    return published_draft(config, signature, agent_id, tick)


def published_draft(
    config: ExperimentConfig,
    signature: Signature,
    agent_id: str | None,
    tick: int,
    *,
    preseeded: bool = False,
) -> EventDraft:
    metadata: dict[str, object] = {
        "legitimate": signature.legitimate,
        "signature": strains.encode(signature.vector, config.signature_bits),
    }
    if preseeded:
        metadata["preseeded"] = True
    return EventDraft(
        sim_tick=tick,
        event_type=EventType.THREAT_SIGNATURE_PUBLISHED,
        agent_id=agent_id,
        metadata=metadata,
    )


def received_draft(
    config: ExperimentConfig, signature: Signature, adopters: int, tick: int
) -> EventDraft:
    return EventDraft(
        sim_tick=tick,
        event_type=EventType.THREAT_SIGNATURE_RECEIVED,
        metadata={
            "legitimate": signature.legitimate,
            "signature": strains.encode(signature.vector, config.signature_bits),
            "adopters": adopters,
        },
    )


def step(state: WorldState, config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """Adoption, then autoimmunity, for one tick. Pure, synchronous, total.
    Runs after detection, so a signature published with no delay is held
    from the same tick."""
    if not config.immunity_enabled:
        return state, []

    tick = state.tick
    participants = sorted(n for n, node in state.nodes.items() if node.immune_participant)
    drafts: list[EventDraft] = []
    signatures = list(state.signatures)
    for i, signature in enumerate(signatures):
        if not signature.announced and signature.adopt_tick <= tick:
            signatures[i] = replace(signature, announced=True)
            drafts.append(received_draft(config, signature, len(participants), tick))

    holding = [s for s in signatures if s.adopt_tick <= tick]
    probes = blocked = 0
    for agent_id in participants:
        if not is_susceptible(state.nodes[agent_id]):
            continue
        for i in range(config.benign_probes_per_tick):
            probes += 1
            # Nothing held, nothing to block: skip the draw.
            if holding and _matches(
                holding,
                benign_vector(config, tick, agent_id, f"benign_probe:{i}"),
                config.signature_radius,
            ):
                blocked += 1

    return (
        replace(
            state,
            signatures=tuple(signatures),
            benign_probes=state.benign_probes + probes,
            benign_blocked=state.benign_blocked + blocked,
        ),
        drafts,
    )
