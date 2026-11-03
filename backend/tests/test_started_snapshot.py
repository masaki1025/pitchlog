"""合成保存rowのpure readerと実単一artifactを検査し、認可成功とはしない。"""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from pitchlog.db.game_state.models import Game
from pitchlog.domainrt.first_pitch_continuation import (
    CombinedRequest,
    evaluate_first_pitch_with_continuation,
)
from pitchlog.repositories import started_snapshot as reader
from pitchlog.repositories.base import _materialize_rows
from pitchlog.repositories.roster import PlayerReadToken, player_read_statement
from pitchlog.repositories.started_snapshot_operations import (
    LINEUP_COLUMNS,
    StartedEventSlotsExistenceToken,
    StartedLineupsReadToken,
    StartedOperationEventsExistenceToken,
    StartedPlayRowsExistenceToken,
)
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(
    (
        ROOT / "contracts/state-transition/t2_first_pitch_continuation_cases_v1.json"
    ).read_text()
)["cases"]
ROSTERS = json.loads(
    (ROOT / "contracts/state-transition/initial_game_roster_cases_v1.json").read_text()
)["cases"]


class Bundle:
    """手作りrowを既executorのmaterializationだけへ通す純試験入力。"""

    def __init__(self) -> None:
        """契約の配置値から合成rowを用意する。実DB由来とは扱わない。"""
        self.tenant, self.game_id = uuid4(), uuid4()
        roster = next(
            c["request"]
            for c in ROSTERS
            if c["expected"]["ok"] is True and c["request"]["dh"] is True
        )
        self.game: dict[str, Any] = dict.fromkeys(Game.__table__.c.keys())
        self.game.update(
            tenant_id=self.tenant,
            id=self.game_id,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
            away_team_record_id=UUID(roster["away"]["team_id"]),
            home_team_record_id=UUID(roster["home"]["team_id"]),
        )
        self.game["applied_rules"] = {
            "ruleSetId": str(uuid4()),
            "regulationInnings": 9,
            "coldConditions": [],
            "extensionLimit": 9,
            "tiebreak": None,
            "dh": True,
        }
        self.generation: dict[str, Any] = dict.fromkeys(_GENERATION_READ_COLUMNS)
        self.generation.update(
            tenant_id=self.tenant,
            game_id=self.game_id,
            generation=1,
            kind="normal",
            issuance_order=1,
            holder_device=str(uuid4()),
            confirmed_watermark=0,
            applied_prefix=0,
            granted_at=datetime.now(timezone.utc),
        )
        self.lineups: list[dict[str, Any]] = []
        self.players: dict[UUID, dict[str, Any]] = {}
        for side in ("away", "home"):
            team = UUID(roster[side]["team_id"])
            entries = []
            for index, source in enumerate(roster[side]["entries"]):
                entry = copy.deepcopy(source)
                if entry["batting_order"] is not None:
                    entry["batting_order"] = int(entry["batting_order"])
                if entry["fielding_position"]["kind"] == "fielding":
                    entry["fielding_position"]["position"] = int(
                        entry["fielding_position"]["position"]
                    )
                entry["uniform_number_snapshot"] = None if index == 0 else str(index)
                entries.append(entry)
                player = UUID(entry["player_id"])
                self.players[player] = {
                    "id": player,
                    "team_record_id": team,
                    "name": "公式参照",
                    "uniform_number": "現在の別背番号",
                }
            self.lineups.append(
                dict(
                    tenant_id=self.tenant,
                    id=uuid4(),
                    game_id=self.game_id,
                    team_record_id=team,
                    entries_with_uniform_number_snapshot=entries,
                )
            )
        self.nonempty: type | None = None
        self.override: dict[type, TenantOperationResult] = {}
        self.calls: list[Any] = []
        self.handle = object.__new__(_TenantTransaction)
        self.handle._state_key = object()
        self.handle._bound_tenant_id = self.tenant

    def _result(
        self, columns: tuple[str, ...], rows: list[dict[str, Any]]
    ) -> TenantOperationResult:
        return _materialize_rows(
            tuple(tuple(row.get(k) for k in columns) for row in rows)
        )

    def run(self, handle: _TenantTransaction, token: Any) -> TenantOperationResult:
        """pure試験だけでrunを置き換える。実handle/登録の成功ではない。"""
        assert handle is self.handle
        self.calls.append(token)
        if type(token) in self.override:
            return self.override[type(token)]
        if type(token) in (GameReadToken, GameLockToken):
            return self._result(tuple(Game.__table__.c.keys()), [self.game])
        if type(token) in (RecordingGenerationReadToken, RecordingGenerationLockToken):
            return self._result(_GENERATION_READ_COLUMNS, [self.generation])
        if type(token) is StartedLineupsReadToken:
            return self._result(LINEUP_COLUMNS, self.lineups)
        if type(token) is PlayerReadToken:
            value = self.players.get(token.record_id)
            return self._result(
                tuple(player_read_statement(token).selected_columns.keys()),
                [] if value is None else [value],
            )
        assert type(token) in (
            StartedEventSlotsExistenceToken,
            StartedOperationEventsExistenceToken,
            StartedPlayRowsExistenceToken,
        )
        return TenantOperationResult(
            ((self.game_id,),) if type(token) is self.nonempty else ()
        )


@pytest.fixture
def bundle(monkeypatch: pytest.MonkeyPatch) -> Bundle:
    """同handleでの読取だけを合成し、計算は実artifactへ渡す。"""
    value = Bundle()
    monkeypatch.setattr(
        _TenantTransaction, "run", lambda handle, token: value.run(handle, token)
    )
    return value


def test_saved_sources_map_all_initial_fields_and_real_combined_artifact(
    bundle: Bundle,
) -> None:
    """真正性を模すboolを渡さず、保存rowの全fieldと同N3全値を比較する。"""
    result = reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)
    assert (
        result.before.model_dump(mode="json", by_alias=True)
        == CASES[0]["request"]["t1"]["before"]
    )
    assert (
        result.rules.model_dump(mode="json", by_alias=True)
        == CASES[0]["request"]["rules"]
    )
    request = CombinedRequest.model_validate_json(
        json.dumps(
            {
                "t1": {
                    **CASES[0]["request"]["t1"],
                    "before": result.before.model_dump(mode="json", by_alias=True),
                },
                "rules": result.rules.model_dump(mode="json", by_alias=True),
            }
        ),
        by_alias=True,
        by_name=False,
    )
    assert (
        evaluate_first_pitch_with_continuation(request).model_dump(
            mode="json", by_alias=True
        )
        == CASES[0]["expected"]
    )
    assert result.game_id == bundle.game_id and result.tenant_id == bundle.tenant
    assert result.lineups[0].entries[0].uniform_number_snapshot is None
    assert result.lineups[0].entries[1].uniform_number_snapshot == "1"
    assert json.loads(result.saved_rules_json) == bundle.game["applied_rules"]
    types = [type(t) for t in bundle.calls]
    assert types[:5] == [
        GameLockToken,
        GameReadToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
        StartedLineupsReadToken,
    ]
    assert types[-3:] == [
        StartedEventSlotsExistenceToken,
        StartedOperationEventsExistenceToken,
        StartedPlayRowsExistenceToken,
    ]
    assert all(
        t.game_id == bundle.game_id for t in bundle.calls if hasattr(t, "game_id")
    )
    for token in bundle.calls:
        if type(token) is PlayerReadToken:
            assert (
                token.limit == 1
                and token.include_hidden is True
                and token.team_record_id is not None
            )
    bundle.lineups[0]["entries_with_uniform_number_snapshot"][1][
        "uniform_number_snapshot"
    ] = "後の変更"
    assert result.lineups[0].entries[1].uniform_number_snapshot == "1"
    with pytest.raises(FrozenInstanceError):
        setattr(result, "generation", 2)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "preparing"),
        ("status", "finished"),
        ("started_at", None),
        ("started_at", datetime(2026, 1, 1)),
        ("hidden_at", datetime.now(timezone.utc)),
        ("trashed_at", datetime.now(timezone.utc)),
        ("import_batch_id", uuid4()),
        ("id", uuid4()),
        ("tenant_id", uuid4()),
        ("away_team_record_id", "invalid"),
    ],
)
def test_game_missing_or_wrong_scope_never_becomes_initial_zero(
    bundle: Bundle, field: str, value: Any
) -> None:
    """開始/可視性/同tenantの欠損・相違を拒否する。"""
    bundle.game[field] = value
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", True),
        ("generation", 0),
        ("generation", -1),
        ("generation", 2**63),
        ("kind", "migration"),
        ("confirmed_watermark", True),
        ("confirmed_watermark", 1),
        ("applied_prefix", 1),
        ("revoked_at", datetime.now(timezone.utc)),
        ("retired_at", datetime.now(timezone.utc)),
        ("import_batch_id", uuid4()),
        ("game_id", uuid4()),
        ("tenant_id", uuid4()),
    ],
)
def test_current_generation_is_exact_and_empty(
    bundle: Bundle, field: str, value: Any
) -> None:
    """旧/失効/非空世代を原本の初期値へ補完しない。"""
    bundle.generation[field] = value
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


@pytest.mark.parametrize(
    "token",
    [
        GameLockToken,
        GameReadToken,
        RecordingGenerationReadToken,
        RecordingGenerationLockToken,
        StartedLineupsReadToken,
    ],
)
@pytest.mark.parametrize("rows", [(), ((),), ((), ())])
def test_missing_duplicate_and_wrong_row_width_fail(
    bundle: Bundle, token: type, rows: Any
) -> None:
    """未取得を空stateへ替えず、行数/列数を閉じる。"""
    bundle.override[token] = TenantOperationResult(rows)
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


@pytest.mark.parametrize(
    "token",
    [
        StartedEventSlotsExistenceToken,
        StartedOperationEventsExistenceToken,
        StartedPlayRowsExistenceToken,
    ],
)
def test_any_existing_row_rejects_initial_snapshot(bundle: Bundle, token: type) -> None:
    """世代やD2によらず各原本の一行で初期snapshotを拒否する。"""
    bundle.nonempty = token
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "same-team",
        "other-tenant",
        "other-game",
        "duplicate-player",
        "missing-player",
        "foreign-player",
        "entry-extra",
        "entry-number",
        "role-bool",
        "uniform-int",
        "layout",
    ],
)
def test_saved_lineup_and_official_reference_cannot_be_substituted(
    bundle: Bundle, fault: str
) -> None:
    """名簿の不足・別所属・不正配置を既artifact又は構造で拒否する。"""
    entry = bundle.lineups[0]["entries_with_uniform_number_snapshot"][0]
    if fault == "missing":
        bundle.lineups.pop()
    elif fault == "extra":
        bundle.lineups.append(copy.deepcopy(bundle.lineups[0]))
    elif fault == "same-team":
        bundle.lineups[1]["team_record_id"] = bundle.lineups[0]["team_record_id"]
    elif fault == "other-tenant":
        bundle.lineups[0]["tenant_id"] = uuid4()
    elif fault == "other-game":
        bundle.lineups[0]["game_id"] = uuid4()
    elif fault == "duplicate-player":
        bundle.lineups[0]["entries_with_uniform_number_snapshot"][1]["player_id"] = (
            entry["player_id"]
        )
    elif fault == "missing-player":
        del bundle.players[UUID(entry["player_id"])]
    elif fault == "foreign-player":
        bundle.players[UUID(entry["player_id"])]["team_record_id"] = uuid4()
    elif fault == "entry-extra":
        entry["extra"] = 0
    elif fault == "entry-number":
        entry["batting_order"] = "1"
    elif fault == "role-bool":
        entry["fielding_position"] = {"kind": "fielding", "position": True}
    elif fault == "uniform-int":
        entry["uniform_number_snapshot"] = 1
    else:
        entry["batting_order"] = 2
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


@pytest.mark.parametrize(
    "fault", ["missing", "extra", "old-alias", "float", "bool", "unresolved"]
)
def test_saved_rules_have_no_defaults_or_current_rule_resolution(
    bundle: Bundle, fault: str
) -> None:
    """保存codecの全fieldを保持し、未知の規則を補完しない。"""
    rules = bundle.game["applied_rules"]
    if fault == "missing":
        del rules["dh"]
    elif fault == "extra":
        rules["extra"] = 0
    elif fault == "old-alias":
        rules["overtime"] = rules.pop("extensionLimit")
    elif fault == "float":
        rules["regulationInnings"] = 9.0
    elif fault == "bool":
        rules["regulationInnings"] = True
    else:
        rules["ruleSetId"] = ""
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


def test_lifetime_wrong_handle_and_game_type_reject_before_reads(
    bundle: Bundle,
) -> None:
    """別handle/失効/UUID強制変換を受け付けない。"""
    for handle, game in [
        (object(), bundle.game_id),
        (bundle.handle, str(bundle.game_id)),
    ]:
        with pytest.raises(reader.StartedSnapshotUnavailable):
            reader.read_initial_started_snapshot(cast(Any, handle), cast(Any, game))
    bundle.handle._state_key = None
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)
    assert bundle.calls == []


@pytest.mark.parametrize("token", [GameReadToken, RecordingGenerationLockToken])
def test_locked_and_read_originals_must_match(bundle: Bundle, token: type) -> None:
    """lockの原本と後続readを別の保存状態で取り替えない。"""
    if token is GameReadToken:
        changed = {**bundle.game, "section_label": "別の値"}
        result = bundle._result(tuple(Game.__table__.c.keys()), [changed])
    else:
        changed = {**bundle.generation, "generation": 2}
        result = bundle._result(_GENERATION_READ_COLUMNS, [changed])
    bundle.override[token] = result
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


def test_expired_writer_during_artifact_call_cannot_return_snapshot(
    bundle: Bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """計算中にscopeが終わった場合も、生存中readとして返さない。"""
    actual = reader.evaluate_initial_game_roster

    def expire(request: Any) -> Any:
        response = actual(request)
        bundle.handle._expire()
        return response

    monkeypatch.setattr(reader, "evaluate_initial_game_roster", expire)
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)


@pytest.mark.parametrize("generation", [2**31, 2**63 - 1])
def test_generation_bigint_is_not_narrowed_to_int32(
    bundle: Bundle, generation: int
) -> None:
    """既D4の正bigintをPython側の狭い整数へ制限しない。"""
    bundle.generation["generation"] = generation
    snapshot = reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)
    assert snapshot.generation == generation
    token = next(t for t in bundle.calls if type(t) is RecordingGenerationLockToken)
    assert token.generation == generation


def test_writer_rebound_during_one_read_is_rejected(
    bundle: Bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同じhandleでも途中で別writerキーへ移したrowを採用しない。"""
    original = bundle.run

    def rebind(handle: _TenantTransaction, token: Any) -> TenantOperationResult:
        value = original(handle, token)
        if type(token) is GameReadToken:
            handle._state_key = object()
        return value

    monkeypatch.setattr(_TenantTransaction, "run", rebind)
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)
    assert len(bundle.calls) == 2


def test_shared_initial_before_value_and_nonempty_refusal_remain(
    bundle: Bundle,
) -> None:
    """R2との共有は初期表現だけで、N2の非空拒否を広げない。"""
    assert (
        reader._initial_before().model_dump(mode="json", by_alias=True)
        == CASES[0]["request"]["t1"]["before"]
    )
    bundle.nonempty = StartedOperationEventsExistenceToken
    with pytest.raises(reader.StartedSnapshotUnavailable):
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)
