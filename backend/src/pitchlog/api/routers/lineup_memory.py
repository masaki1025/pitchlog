"""自チームの前回スタメンを復元候補として返す入口。"""

from collections.abc import Mapping
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from pitchlog.api.schemas.lineup_memory import LineupMemoryEntry, LineupMemoryResponse
from pitchlog.api.schemas.roster import PlayerRead
from pitchlog.api.tenant_access import require_tenant_access
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.lineup_memory import (
    LineupMemoryReadToken,
    _normalize_lineup,
    _SelfTeamLockToken,
)
from pitchlog.repositories.roster import PlayerReadToken
from pitchlog.repositories.transaction import tenant_transaction_scope

router = APIRouter(tags=["前回スタメン"])
_PLAYER_FIELDS = (
    "id",
    "team_record_id",
    "name",
    "throws",
    "bats",
    "uniform_number",
    "roster_status_key",
    "roster_label_key",
    "hidden_at",
)


def _json_response_value(value: object) -> object:
    """不変化された記憶内 JSON 値を応答用の JSON 値へ戻す。"""
    if isinstance(value, Mapping):
        return {key: _json_response_value(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_json_response_value(item) for item in value]
    return value


@router.get(
    "/team-records/{team_record_id:uuid}/lineup-memory",
    response_model=LineupMemoryResponse,
    responses={204: {"description": "前回スタメンなし"}},
    operation_id="lineup_memory_read",
)
def read_lineup_memory(
    team_record_id: UUID,
    context: Annotated[TenantContext, Depends(require_tenant_access)],
) -> LineupMemoryResponse | Response:
    """現在の自チーム選手だけを自動採用する復元候補を返す。"""
    with tenant_transaction_scope(context) as scope:
        if not scope.run(_SelfTeamLockToken(team_record_id)).rows:
            raise HTTPException(status_code=404)

        memories = scope.run(LineupMemoryReadToken(team_record_id)).rows
        if not memories or memories[0][2] is not False:
            return Response(status_code=204)
        lineup = memories[0][1]
        if type(lineup) is not tuple:
            raise ValueError("スタメン記憶の形式が不正")
        normalized, _ = _normalize_lineup(
            cast(tuple[Mapping[str, object], ...], lineup)
        )
        entries: list[LineupMemoryEntry] = []
        for slot in normalized:
            player_id = UUID(cast(str, slot["player_id"]))
            players = scope.run(
                PlayerReadToken(
                    limit=1,
                    record_id=player_id,
                    team_record_id=team_record_id,
                    roster_status_key="active",
                )
            ).rows
            player = (
                PlayerRead.model_validate(
                    dict(zip(_PLAYER_FIELDS, players[0], strict=True))
                )
                if players
                else None
            )
            entries.append(
                LineupMemoryEntry.model_validate(
                    {
                        "batting_order": slot["batting_order"],
                        "fielding_position": _json_response_value(
                            slot["fielding_position"]
                        ),
                        "player_id": player.id if player else None,
                        "name": player.name if player else None,
                        "uniform_number": player.uniform_number if player else None,
                        "replacement_required": player is None,
                    }
                )
            )
        return LineupMemoryResponse(entries=entries)
