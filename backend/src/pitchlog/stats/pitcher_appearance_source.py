"""単一SQL entry投影の閉じた値境界。保存資格は発行しない。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast
from uuid import UUID


class PitcherAppearanceSourceUnavailable(ValueError):
    """原本/投影/型が不足または不一致で登板を供給できない。"""


_SHA = re.compile(r"[a-f0-9]{64}")
_FINGERPRINT = re.compile(r"(?:wire-v1:)?[a-f0-9]{64}")


@dataclass(frozen=True, slots=True)
class ProjectedPitcherEntry:
    """SQLで評価済みの値。これ自身はwriter/認可/同TX証明ではない。"""

    tenant_id: UUID
    game_id: UUID
    origin_kind: str
    source_id: UUID
    generation: int
    d1: int | None
    player_id: UUID
    defending_side: str
    inning: int
    half: str
    proof_kind: str
    artifact_sha256: str
    source_fingerprint: str


def decode_projected_entry(rows: object) -> ProjectedPitcherEntry | None:
    """1行完全形だけを受け、正当なentry無しと不正を区別する。"""
    if type(rows) is not tuple or len(rows) != 1:
        raise PitcherAppearanceSourceUnavailable("entry投影行数が不一致です")
    row = rows[0]
    if (
        type(row) is not tuple
        or len(row) != 14
        or type(row[0]) is not str
        or row[0] != "evaluated"
    ):
        raise PitcherAppearanceSourceUnavailable("entry投影が未供給です")
    (
        _,
        tenant,
        game,
        origin,
        source,
        generation,
        d1,
        player,
        side,
        inning,
        half,
        kind,
        artifact,
        fingerprint,
    ) = row
    if (
        any(type(value) is not UUID for value in (tenant, game, source))
        or type(origin) is not str
        or origin not in {"start", "play", "substitution", "reopen"}
        or type(generation) is not int
        or not 0 < generation < 2**63
        or type(artifact) is not str
        or _SHA.fullmatch(artifact) is None
        or type(fingerprint) is not str
        or _FINGERPRINT.fullmatch(fingerprint) is None
        or (origin == "start" and d1 is not None)
        or (origin != "start" and (type(d1) is not int or not 0 < d1 < 2**63))
    ):
        raise PitcherAppearanceSourceUnavailable("entryの原本identityが不一致です")
    entry = (player, side, inning, half, kind)
    if all(value is None for value in entry):
        if origin == "start":
            raise PitcherAppearanceSourceUnavailable("開始の守備投手が未供給です")
        return None
    if (
        any(value is None for value in entry)
        or type(player) is not UUID
        or type(side) is not str
        or side not in {"home", "away"}
        or type(half) is not str
        or half not in {"top", "bottom"}
        or type(inning) is not int
        or not 0 < inning < 2**63
        or type(kind) is not str
        or kind not in {"defensive-half-entry", "pitcher-defensive-entry"}
        or (origin == "start" and (half != "top" or inning != 1))
        or (side, half) not in {("home", "top"), ("away", "bottom")}
        or (origin == "substitution") != (kind == "pitcher-defensive-entry")
    ):
        raise PitcherAppearanceSourceUnavailable("entryの出場identityが不一致です")
    return ProjectedPitcherEntry(
        cast(UUID, tenant),
        cast(UUID, game),
        origin,
        cast(UUID, source),
        generation,
        cast(int | None, d1),
        player,
        side,
        inning,
        half,
        kind,
        artifact,
        fingerprint,
    )
