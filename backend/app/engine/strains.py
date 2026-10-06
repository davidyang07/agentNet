"""Worm strains (docs/PLAN.md §14.4 C.3, after [S1]: worms are inherently
polymorphic).

A strain is a `signature_bits`-bit vector held as an int -- an abstract
stand-in for [S1]'s SimHash codes, with Hamming distance standing for
semantic distance. Patient zero's strain sits `strain_benign_distance` bits
from a shared "benign behaviour" centroid, which sets how disguised the worm
is. Every successful transmission may mutate the strain, flipping
`mutation_bits` keyed positions; the winning source's strain (after any
mutation) becomes the target's.

Strains are tracked only while something reads them, so a default run draws
nothing and emits no strain metadata.
"""

from __future__ import annotations

from app.engine.rng import rng
from app.engine.state import AgentNode
from app.schemas.experiment import ExperimentConfig


def tracked(config: ExperimentConfig) -> bool:
    """Strains matter while they can mutate or be matched by immune memory."""
    return config.mutation_rate > 0.0 or config.immunity_enabled


def _flip(strain: int, positions: list[int]) -> int:
    for position in positions:
        strain ^= 1 << position
    return strain


def benign_centroid(config: ExperimentConfig) -> int:
    return rng(config.seed, 0, "strain", "benign_centroid").getrandbits(config.signature_bits)


def patient_zero_strain(config: ExperimentConfig) -> int:
    positions = rng(config.seed, 0, "strain", "patient_zero").sample(
        range(config.signature_bits), config.strain_benign_distance
    )
    return _flip(benign_centroid(config), positions)


def transmit(
    config: ExperimentConfig, tick: int, source: AgentNode, target_id: str
) -> tuple[int, bool]:
    """The strain a successful attack from `source` carries to `target_id`,
    and whether it mutated on the way. Keyed per (target, source), like
    propagation's infect:{source} draw, so attack order never matters."""
    assert source.strain is not None, "every infected agent carries a strain while tracked"
    draw = rng(config.seed, tick, target_id, f"mutate:{source.id}")
    if draw.random() < config.mutation_rate:
        positions = draw.sample(range(config.signature_bits), config.mutation_bits)
        return _flip(source.strain, positions), True
    return source.strain, False


def distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def encode(strain: int, bits: int) -> str:
    """Hex, zero-padded to the strain length -- event metadata is JSON, and a
    browser can't hold a 64-bit or wider integer exactly."""
    return f"{strain:0{(bits + 3) // 4}x}"


def success_metadata(config: ExperimentConfig, strain: int, mutated: bool) -> dict[str, object]:
    return {"strain": encode(strain, config.signature_bits), "mutated": mutated}
