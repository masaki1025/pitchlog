"""実scopeと単一resolver/RG1へ準備中作成の接続候補を束ねる。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args
from uuid import UUID, uuid4

from pitchlog.api.schemas.base import Page
from pitchlog.api.schemas.games import (
    ExistingTournament,
    GameTypeKey,
    PreparationGameTypeOption,
    PreparationOptionsRequest,
    PreparationTournamentOption,
    PreparingGameCreate,
    PreparingGamePreparationOptions,
    PreparingGameRead,
    TournamentSelection,
    encode_preparation_options_cursor,
)
from pitchlog.db.game_state.rule_snapshot import encode_applied_rules
from pitchlog.repositories.preparing_game_creation import (
    PreparingGameInsertToken,
    PreparingOpponentTeamLockToken,
    PreparingSelfTeamLockToken,
    PreparingTournamentInsertToken,
    PreparingTournamentNameExistsToken,
    PreparingTournamentOptionsToken,
    PreparingTournamentParentToken,
)
from pitchlog.repositories.rg1 import assert_rg1_open_before_commit, read_rg1_open
from pitchlog.repositories.roster import SelfTeamRecordReadToken, TeamRecordReadToken
from pitchlog.repositories.rule_resolution import (
    StageARuleRequest,
    resolve_stage_a_rule,
)
from pitchlog.repositories.tokens import TenantOperationResult

if TYPE_CHECKING:
    from pitchlog.repositories.transaction import _TenantTransaction

_GAME_TYPES_PATH = (
    Path(__file__).resolve().parents[4] / "contracts/seeds/game-type.json"
)
type PreparingCreationFailure = Literal[
    "not_available", "tournament_name_conflict", "outcome_unconfirmed"
]


class PreparingGameCreationError(RuntimeError):
    """内部値を公開せず作成/optionsの非成功だけを分類する。"""

    def __init__(self, code: PreparingCreationFailure) -> None:
        """閉じた失敗分類だけを保存する。"""
        if code not in (
            "not_available",
            "tournament_name_conflict",
            "outcome_unconfirmed",
        ):
            raise ValueError("未定義の作成失敗")
        self.code = code
        super().__init__(code)


def _require_scope(scope: _TenantTransaction) -> None:
    """Session/任意Protocol/派生scopeを受け入れない。"""
    from pitchlog.repositories.transaction import _TenantTransaction

    if type(scope) is not _TenantTransaction:
        raise TypeError("束縛済みの実トランザクションが必要")


def _require_inserted(result: TenantOperationResult) -> None:
    """更新件数1だけを採用し、結果不明/0/複数件を非成功へ倒す。"""
    if result.rows != ((1,),) or type(result.rows[0][0]) is not int:
        raise PreparingGameCreationError("outcome_unconfirmed")


def _require_tournament(scope: _TenantTransaction, key: str) -> None:
    """指定有効大会以外を不存在と同じ外形へ閉じる。"""
    if scope.run(PreparingTournamentParentToken(key)).rows != ((key,),):
        raise PreparingGameCreationError("not_available")


def _select_tournament(
    scope: _TenantTransaction, selection: TournamentSelection
) -> str:
    """新名の衝突を拒否し、大会確定を同じscope内で行う。"""
    if isinstance(selection, ExistingTournament):
        key = selection.key
    else:
        if scope.run(PreparingTournamentNameExistsToken(selection.display_name)).rows:
            raise PreparingGameCreationError("tournament_name_conflict")
        key = str(uuid4())
        _require_inserted(
            scope.run(PreparingTournamentInsertToken(key, selection.display_name))
        )
    _require_tournament(scope, key)
    return key


def _lock_teams(scope: _TenantTransaction, away: UUID, home: UUID) -> None:
    """既存lookupと固定kindロックで両側をUUID順に検証する。"""
    self_rows = scope.run(SelfTeamRecordReadToken()).rows
    if (
        len(self_rows) != 1
        or len(self_rows[0]) != 4
        or type(self_rows[0][0]) is not UUID
        or self_rows[0][1] != "self"
        or self_rows[0][3] is not None
    ):
        raise PreparingGameCreationError("not_available")
    self_id = self_rows[0][0]
    for team_id in sorted({away, home}):
        if team_id == self_id:
            token = PreparingSelfTeamLockToken(team_id)
        else:
            rows = scope.run(TeamRecordReadToken(limit=1, record_id=team_id)).rows
            if (
                len(rows) != 1
                or len(rows[0]) != 4
                or rows[0][0] != team_id
                or rows[0][1] != "opponent"
                or rows[0][3] is not None
            ):
                raise PreparingGameCreationError("not_available")
            token = PreparingOpponentTeamLockToken(team_id)
        if scope.run(token).rows != ((team_id,),):
            # ロック待機中の非表示化/退役も成功にしない。
            raise PreparingGameCreationError("not_available")


def create_preparing_game(
    scope: _TenantTransaction, request: PreparingGameCreate
) -> PreparingGameRead:
    """同一scopeで作成する。戻り値はcommit前の候補でありHTTP成功ではない。

    呼出側はこの関数の例外をscope外まで伝播させ、scope退出のcommit後にだけ
    201を返す。RG1常閉を変更せず、現在の供給では保存成功へ到達しない。

    Args:
        scope: 認証/C2の後に取得した実scope。
        request: 既存作成DTO。変更後も同じDTO規則を再検査する。

    Returns:
        scopeのcommit完了まで公開してはならない保存値候補。

    Raises:
        TypeError: 実scope/作成DTOのexact型ではない場合。
        PreparingGameCreationError: 親不在・同名衝突・INSERT結果不明。
        Exception: RG1/resolver/DB/codec等の失敗。scope外へ伝播させる。
    """
    _require_scope(scope)
    if type(request) is not PreparingGameCreate:
        raise TypeError("作成DTOが必要")
    body = PreparingGameCreate.model_validate(request.model_dump())
    read_rg1_open(scope)
    tournament_key = _select_tournament(scope, body.tournament)
    _lock_teams(scope, body.away_team_record_id, body.home_team_record_id)
    snapshot = resolve_stage_a_rule(
        scope, StageARuleRequest(body.game_type_key, tournament_key, False)
    )
    encoded = encode_applied_rules(snapshot)
    game_id = uuid4()
    _require_inserted(
        scope.run(
            PreparingGameInsertToken(
                game_id=game_id,
                scheduled_at=body.scheduled_at,
                game_type_key=body.game_type_key,
                tournament_key=tournament_key,
                away_team_record_id=body.away_team_record_id,
                home_team_record_id=body.home_team_record_id,
                applied_rules_json=json.dumps(encoded, ensure_ascii=False),
                plate_umpire=body.plate_umpire,
                section_label=body.section_label,
                week_label=body.week_label,
                day_label=body.day_label,
                game_number_label=body.game_number_label,
            )
        )
    )
    item = PreparingGameRead(
        id=game_id,
        scheduled_at=body.scheduled_at,
        game_type_key=body.game_type_key,
        tournament_key=tournament_key,
        away_team_record_id=body.away_team_record_id,
        home_team_record_id=body.home_team_record_id,
        plate_umpire=body.plate_umpire,
        section_label=body.section_label,
        week_label=body.week_label,
        day_label=body.day_label,
        game_number_label=body.game_number_label,
        status="preparing",
        applied_rules=encoded,
    )
    assert_rg1_open_before_commit(scope)
    return item


def _game_types() -> list[PreparationGameTypeOption]:
    """正本seedの固定区分を読み、表示名やキーをコピー実装しない。"""
    try:
        rows = json.loads(_GAME_TYPES_PATH.read_text(encoding="utf-8"))
        if type(rows) is not list:
            raise ValueError
        options = []
        for row in rows:
            if (
                type(row) is not dict
                or set(row) != {"key", "category", "display_name"}
                or row["category"] != "game_type"
            ):
                raise ValueError
            options.append(
                PreparationGameTypeOption(
                    key=row["key"], display_name=row["display_name"]
                )
            )
        keys = [option.key for option in options]
        if len(keys) != len(set(keys)) or set(keys) != set(get_args(GameTypeKey)):
            raise ValueError
        return options
    except Exception:
        raise PreparingGameCreationError("outcome_unconfirmed") from None


def read_preparation_options(
    scope: _TenantTransaction, request: PreparationOptionsRequest
) -> PreparingGamePreparationOptions:
    """実scopeで大会を1ページだけ読み、正本区分と合わせる。"""
    _require_scope(scope)
    if type(request) is not PreparationOptionsRequest:
        raise TypeError("options DTOが必要")
    query = PreparationOptionsRequest.model_validate(request.model_dump())
    game_types = _game_types()
    rows = scope.run(PreparingTournamentOptionsToken(query.limit, query.cursor)).rows
    if len(rows) > query.limit + 1:
        raise PreparingGameCreationError("outcome_unconfirmed")
    if any(len(row) != 2 for row in rows):
        raise PreparingGameCreationError("outcome_unconfirmed")
    supplied = [
        PreparationTournamentOption.model_validate(
            {"key": row[0], "display_name": row[1]}
        )
        for row in rows
    ]
    tournaments = supplied[: query.limit]
    return PreparingGamePreparationOptions(
        game_types=game_types,
        tournaments=Page[PreparationTournamentOption](
            items=tournaments,
            next_cursor=(
                encode_preparation_options_cursor(tournaments[-1].key)
                if len(rows) > query.limit
                else None
            ),
        ),
    )
