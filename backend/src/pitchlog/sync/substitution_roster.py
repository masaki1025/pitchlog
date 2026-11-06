"""同一tenant writerで途中出場者と当時背番号を照合する。"""

from __future__ import annotations

from uuid import UUID

from pitchlog.repositories import transaction
from pitchlog.repositories.roster import PlayerReadToken, player_read_statement
from pitchlog.sync.substitution_payload import SubstitutionPayload


class SubstitutionRosterUnavailable(RuntimeError):
    """選手行の所属・在籍・背番号が不一致。"""


def read_eligible_incoming(
    handle, payload: SubstitutionPayload, state: dict
) -> list[str]:
    """真正CP中の所属と実player行を同TXで一点ずつ比較する。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(payload) is not SubstitutionPayload
        or type(state) is not dict
    ):
        raise SubstitutionRosterUnavailable("交代候補の同writer資格が不一致です")
    raw = payload.to_wire()
    side = raw["operation"]["side"]
    if side not in ("away", "home") or side not in state:
        raise SubstitutionRosterUnavailable("交代側が保存状態と不一致です")
    team_id = state[side]["teamId"]
    if type(team_id) is not str:
        raise SubstitutionRosterUnavailable("交代側の所属原本が不一致です")
    selected = []
    for entry in raw["incomingSnapshots"]:
        identifier = UUID(entry["playerId"])
        token = PlayerReadToken(
            1,
            record_id=identifier,
            team_record_id=UUID(team_id),
            include_hidden=False,
        )
        columns = tuple(player_read_statement(token).selected_columns.keys())
        rows = handle.run(token).rows
        if len(rows) != 1 or len(rows[0]) != len(columns):
            raise SubstitutionRosterUnavailable("途中出場者が一点で取得できません")
        player = dict(zip(columns, rows[0], strict=True))
        if (
            player["id"] != identifier
            or player["team_record_id"] != UUID(team_id)
            or player["hidden_at"] is not None
            or player["roster_status_key"] != "active"
            or player["uniform_number"] != entry["uniformNumber"]
        ):
            raise SubstitutionRosterUnavailable("途中出場者の在籍/背番号が不一致です")
        selected.append(str(identifier))
    return selected
