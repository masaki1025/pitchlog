"""開始済み試合の組立器が、lock順・振り分け・0球readerの非改変を守ることを検査する。

合成rowだけを既executorのmaterializationへ通す純試験で、実DB・認可・保存の
成功を示すものではない。0球reader(N2)の拒否は不可視へ倒さず、破損として扱う。
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import inspect
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from test_started_snapshot import Bundle

from pitchlog.db.game_state.models import Game
from pitchlog.db.game_state.rule_snapshot import (
    decode_applied_rules,
    encode_applied_rules,
)
from pitchlog.repositories import started_read as assembler
from pitchlog.repositories import started_snapshot as reader
from pitchlog.repositories.roster import PlayerReadToken
from pitchlog.repositories.started_snapshot_operations import (
    StartedEventSlotsExistenceToken,
    StartedLineupsReadToken,
    StartedOperationEventsExistenceToken,
    StartedPlayRowsExistenceToken,
)
from pitchlog.repositories.sync_apply import _GENERATION_READ_COLUMNS
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.d4_reference import encode_d4_reference
from pitchlog.sync.tokens import (
    GameLockToken,
    GameReadToken,
    RecordingGenerationLockToken,
    RecordingGenerationReadToken,
)

_SOURCE = Path(assembler.__file__)
_EXISTENCE = (
    StartedEventSlotsExistenceToken,
    StartedOperationEventsExistenceToken,
    StartedPlayRowsExistenceToken,
)
_N2_FIRST_FOUR = [
    GameLockToken,
    GameReadToken,
    RecordingGenerationReadToken,
    RecordingGenerationLockToken,
]


@pytest.fixture
def started_bundle(monkeypatch: pytest.MonkeyPatch) -> Bundle:
    """同handleでの読取だけを合成し、計算は実artifactへ渡す。"""
    value = Bundle()
    monkeypatch.setattr(
        _TenantTransaction, "run", lambda handle, token: value.run(handle, token)
    )
    return value


def _kinds(bundle: Bundle) -> list[type]:
    """これまでに発行されたtokenの型を順に返す。"""
    return [type(token) for token in bundle.calls]


def _outcome(bundle: Bundle) -> str:
    """組立器の結果を、成功・不可視・記録あり・破損の4語へ写す。"""
    try:
        result = assembler.read_started_game(bundle.handle, bundle.game_id)
    except assembler.StartedReadCorrupt:
        return "corrupt"
    if type(result) is assembler.StartedGameView:
        return "view"
    if type(result) is assembler.StartedReadNotVisible:
        return "not_visible"
    assert type(result) is assembler.StartedReadRecorded
    return "recorded"


def _n2_raises(bundle: Bundle) -> bool:
    """0球readerが拒否するか。呼出し記録は消して返す。"""
    try:
        reader.read_initial_started_snapshot(bundle.handle, bundle.game_id)
    except reader.StartedSnapshotUnavailable:
        return True
    finally:
        bundle.calls.clear()
    return False


# --- 振り分けの表。N2の全拒否が成功へ落ちないこと(7)と、種別(6)(9)を同時に固定する。


def _set(table: str, key: str, value: Any) -> Callable[[Bundle], None]:
    def apply(bundle: Bundle) -> None:
        getattr(bundle, table)[key] = value

    return apply


def _lineup_fault(name: str) -> Callable[[Bundle], None]:
    def apply(bundle: Bundle) -> None:
        entry = bundle.lineups[0]["entries_with_uniform_number_snapshot"][0]
        if name == "missing":
            bundle.lineups.pop()
        elif name == "extra":
            bundle.lineups.append(copy.deepcopy(bundle.lineups[0]))
        elif name == "same-team":
            bundle.lineups[1]["team_record_id"] = bundle.lineups[0]["team_record_id"]
        elif name == "other-tenant":
            bundle.lineups[0]["tenant_id"] = uuid4()
        elif name == "other-game":
            bundle.lineups[0]["game_id"] = uuid4()
        elif name == "duplicate-player":
            bundle.lineups[0]["entries_with_uniform_number_snapshot"][1][
                "player_id"
            ] = entry["player_id"]
        elif name == "missing-player":
            del bundle.players[UUID(entry["player_id"])]
        elif name == "foreign-player":
            bundle.players[UUID(entry["player_id"])]["team_record_id"] = uuid4()
        elif name == "entry-extra":
            entry["extra"] = 0
        elif name == "role-bool":
            entry["fielding_position"] = {"kind": "fielding", "position": True}
        elif name == "uniform-int":
            entry["uniform_number_snapshot"] = 1
        else:
            entry["batting_order"] = 2

    return apply


def _rules_fault(name: str) -> Callable[[Bundle], None]:
    def apply(bundle: Bundle) -> None:
        rules = bundle.game["applied_rules"]
        if name == "missing":
            del rules["dh"]
        elif name == "extra":
            rules["extra"] = 0
        elif name == "old-alias":
            rules["overtime"] = rules.pop("extensionLimit")
        elif name == "float":
            rules["regulationInnings"] = 9.0
        else:
            rules["ruleSetId"] = ""

    return apply


def _same_teams(bundle: Bundle) -> None:
    bundle.game["home_team_record_id"] = bundle.game["away_team_record_id"]


def _rows_override(token: type, rows: tuple[Any, ...]) -> Callable[[Bundle], None]:
    def apply(bundle: Bundle) -> None:
        bundle.override[token] = TenantOperationResult(rows)

    return apply


def _read_differs(bundle: Bundle) -> None:
    changed = {**bundle.game, "section_label": "別の値"}
    bundle.override[GameReadToken] = bundle._result(
        tuple(Game.__table__.c.keys()), [changed]
    )


def _generation_lock_differs(bundle: Bundle) -> None:
    changed = {**bundle.generation, "generation": 2}
    bundle.override[RecordingGenerationLockToken] = bundle._result(
        _GENERATION_READ_COLUMNS, [changed]
    )


_NOW = datetime.now(timezone.utc)
_FAULTS: list[tuple[str, str, Callable[[Bundle], None]]] = [
    # 不可視は N2 :243-246 の4条件だけ。
    ("status-preparing", "not_visible", _set("game", "status", "preparing")),
    ("status-finished", "not_visible", _set("game", "status", "finished")),
    ("trashed", "not_visible", _set("game", "trashed_at", _NOW)),
    ("hidden", "not_visible", _set("game", "hidden_at", _NOW)),
    ("import", "not_visible", _set("game", "import_batch_id", uuid4())),
    # 行はあるが不整合(9)。started_at の型・tz、同一チーム、lock と read の不一致。
    ("started-none", "corrupt", _set("game", "started_at", None)),
    ("started-naive", "corrupt", _set("game", "started_at", datetime(2026, 1, 1))),
    ("same-teams", "corrupt", _same_teams),
    ("game-id-other", "corrupt", _set("game", "id", uuid4())),
    ("game-tenant-other", "corrupt", _set("game", "tenant_id", uuid4())),
    ("team-invalid", "corrupt", _set("game", "away_team_record_id", "invalid")),
    ("lock-read-differ", "corrupt", _read_differs),
    ("lock-empty-read-present", "corrupt", _rows_override(GameLockToken, ())),
    ("read-empty-lock-present", "corrupt", _rows_override(GameReadToken, ())),
    ("lock-two-rows", "corrupt", _rows_override(GameLockToken, ((), ()))),
    # 世代。
    ("generation-bool", "corrupt", _set("generation", "generation", True)),
    ("generation-zero", "corrupt", _set("generation", "generation", 0)),
    ("generation-negative", "corrupt", _set("generation", "generation", -1)),
    ("generation-2^63", "corrupt", _set("generation", "generation", 2**63)),
    ("generation-kind", "corrupt", _set("generation", "kind", "migration")),
    ("watermark-bool", "corrupt", _set("generation", "confirmed_watermark", True)),
    ("watermark-1", "corrupt", _set("generation", "confirmed_watermark", 1)),
    ("prefix-1", "corrupt", _set("generation", "applied_prefix", 1)),
    ("revoked", "corrupt", _set("generation", "revoked_at", _NOW)),
    ("retired", "corrupt", _set("generation", "retired_at", _NOW)),
    ("generation-import", "corrupt", _set("generation", "import_batch_id", uuid4())),
    ("generation-game", "corrupt", _set("generation", "game_id", uuid4())),
    ("generation-tenant", "corrupt", _set("generation", "tenant_id", uuid4())),
    (
        "generation-read-empty",
        "corrupt",
        _rows_override(RecordingGenerationReadToken, ()),
    ),
    (
        "generation-lock-empty",
        "corrupt",
        _rows_override(RecordingGenerationLockToken, ()),
    ),
    ("generation-lock-differs", "corrupt", _generation_lock_differs),
    ("lineups-empty", "corrupt", _rows_override(StartedLineupsReadToken, ())),
    ("lineups-narrow", "corrupt", _rows_override(StartedLineupsReadToken, ((), ()))),
    # 記録あり。
    ("slot-exists", "recorded", lambda b: setattr(b, "nonempty", _EXISTENCE[0])),
    ("event-exists", "recorded", lambda b: setattr(b, "nonempty", _EXISTENCE[1])),
    ("playrow-exists", "recorded", lambda b: setattr(b, "nonempty", _EXISTENCE[2])),
    *(
        (f"lineup-{name}", "corrupt", _lineup_fault(name))
        for name in (
            "missing",
            "extra",
            "same-team",
            "other-tenant",
            "other-game",
            "duplicate-player",
            "missing-player",
            "foreign-player",
            "entry-extra",
            "role-bool",
            "uniform-int",
            "layout",
        )
    ),
    *(
        (f"rules-{name}", "corrupt", _rules_fault(name))
        for name in ("missing", "extra", "old-alias", "float", "unresolved")
    ),
]


@pytest.mark.parametrize(
    ("label", "expected", "mutate"), _FAULTS, ids=[row[0] for row in _FAULTS]
)
def test_every_fault_lands_in_not_visible_recorded_or_corrupt(
    started_bundle: Bundle,
    label: str,
    expected: str,
    mutate: Callable[[Bundle], None],
) -> None:
    """N2が拒否する全fixtureは成功へ落ちず、種別が表どおりになる(完了条件 6 7 9)。"""
    mutate(started_bundle)
    n2_rejects = _n2_raises(started_bundle)
    outcome = _outcome(started_bundle)
    assert outcome == expected, label
    if n2_rejects:
        assert outcome != "view"
    else:
        # N2が通る fixture は、記録ありの順序差だけが成功以外になりうる。
        assert outcome in {"view", "recorded"}


def test_baseline_fixture_is_a_view_and_n2_accepts_it(started_bundle: Bundle) -> None:
    """無傷のfixtureは成功し、同じ入力をN2も受理する。"""
    assert _n2_raises(started_bundle) is False
    assert _outcome(started_bundle) == "view"


@pytest.mark.parametrize("label", ["status", "trashed", "hidden", "import"])
def test_not_visible_conditions_are_exactly_the_four_of_n2(
    started_bundle: Bundle, label: str
) -> None:
    """不可視の4条件は、N2も拒否する条件と同一である(完了条件 6)。"""
    key, value = {
        "status": ("status", "preparing"),
        "trashed": ("trashed_at", _NOW),
        "hidden": ("hidden_at", _NOW),
        "import": ("import_batch_id", uuid4()),
    }[label]
    started_bundle.game[key] = value
    assert _n2_raises(started_bundle) is True
    assert _outcome(started_bundle) == "not_visible"


# --- lock順と呼出し(完了条件 1 2 3)。


def test_success_issues_tokens_in_the_adopted_lock_order(
    started_bundle: Bundle,
) -> None:
    """Games lock、世代 read、世代 lock、存在確認3件、その後にN2の順で発行する。"""
    assert _outcome(started_bundle) == "view"
    kinds = _kinds(started_bundle)
    assert kinds[:4] == _N2_FIRST_FOUR
    assert kinds[4:7] == list(_EXISTENCE)
    # N2は同じ入口を取り直す(同一TX内の再取得)。
    assert kinds[7:11] == _N2_FIRST_FOUR
    assert kinds[11] is StartedLineupsReadToken
    assert kinds[-3:] == list(_EXISTENCE)
    lock = next(
        t for t in started_bundle.calls if type(t) is RecordingGenerationLockToken
    )
    assert lock.generation == 1
    assert all(
        token.game_id == started_bundle.game_id
        for token in started_bundle.calls
        if hasattr(token, "game_id")
    )


@pytest.mark.parametrize(
    "mutate",
    [
        _set("game", "status", "preparing"),
        _set("game", "status", "finished"),
        _set("game", "trashed_at", _NOW),
        _set("game", "hidden_at", _NOW),
        _set("game", "import_batch_id", uuid4()),
    ],
)
def test_not_visible_runs_no_sql_after_the_game_read(
    started_bundle: Bundle, mutate: Callable[[Bundle], None]
) -> None:
    """不可視のときは games の lock と read の2件だけで、以後のSQLは0件である。"""
    mutate(started_bundle)
    assert _outcome(started_bundle) == "not_visible"
    assert _kinds(started_bundle) == [GameLockToken, GameReadToken]


def test_other_tenant_or_absent_game_is_uniformly_not_visible(
    started_bundle: Bundle,
) -> None:
    """lockもreadも0行なら、別tenantと不存在を区別せず不可視にする。"""
    started_bundle.override[GameLockToken] = TenantOperationResult(())
    started_bundle.override[GameReadToken] = TenantOperationResult(())
    assert _outcome(started_bundle) == "not_visible"
    assert len(started_bundle.calls) == 2


@pytest.mark.parametrize("token", _EXISTENCE)
def test_recorded_never_calls_n2(
    started_bundle: Bundle, monkeypatch: pytest.MonkeyPatch, token: type
) -> None:
    """記録ありはN2を呼ばず、人の列・lineup・名簿の読取も行わない(完了条件 3)。"""

    def forbidden(*_: Any, **__: Any) -> Any:
        raise AssertionError("記録ありでN2を呼んではならない")

    monkeypatch.setattr(assembler, "read_initial_started_snapshot", forbidden)
    started_bundle.nonempty = token
    assert _outcome(started_bundle) == "recorded"
    kinds = _kinds(started_bundle)
    assert kinds[:4] == _N2_FIRST_FOUR
    assert kinds[4 : 5 + _EXISTENCE.index(token)] == list(
        _EXISTENCE[: _EXISTENCE.index(token) + 1]
    )
    assert StartedLineupsReadToken not in kinds and PlayerReadToken not in kinds


def test_recorded_takes_precedence_over_n2_only_faults(
    started_bundle: Bundle,
) -> None:
    """N2だけが拒否する破損より、記録ありを優先して判定する(U13の暫定)。"""
    started_bundle.nonempty = _EXISTENCE[0]
    started_bundle.game["started_at"] = datetime(2026, 1, 1)
    started_bundle.generation["revoked_at"] = _NOW
    assert _outcome(started_bundle) == "recorded"


def test_missing_generation_is_corrupt_even_when_recorded(
    started_bundle: Bundle,
) -> None:
    """世代の行が無いときは、記録ありの判定へ進まず破損にする。"""
    started_bundle.nonempty = _EXISTENCE[1]
    started_bundle.override[RecordingGenerationReadToken] = TenantOperationResult(())
    assert _outcome(started_bundle) == "corrupt"
    assert _kinds(started_bundle)[-1] is RecordingGenerationReadToken


def test_generation_lock_mismatch_is_corrupt_even_when_recorded(
    started_bundle: Bundle,
) -> None:
    """世代のreadとlockが食い違うときは、記録ありの判定の前に破損にする。"""
    started_bundle.nonempty = _EXISTENCE[2]
    _generation_lock_differs(started_bundle)
    assert _outcome(started_bundle) == "corrupt"
    assert _kinds(started_bundle)[-1] is RecordingGenerationLockToken


# --- 成功の値(同じTX・同じ原本から得た値だけ)。


def test_success_view_carries_only_confirmed_values(started_bundle: Bundle) -> None:
    """見出し・規則・lineup・名簿・初期状態・current_d4を、同じ原本から返す。"""
    when = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    started_bundle.game.update(
        scheduled_at=when,
        game_type_key="game_official",
        tournament_key="spring",
        plate_umpire="審判",
        section_label="a",
        week_label="b",
        day_label="c",
        game_number_label="d",
    )
    snapshot = reader.read_initial_started_snapshot(
        started_bundle.handle, started_bundle.game_id
    )
    started_bundle.calls.clear()
    view = assembler.read_started_game(started_bundle.handle, started_bundle.game_id)
    assert type(view) is assembler.StartedGameView
    game = started_bundle.game
    assert (view.game_id, view.scheduled_at, view.game_type_key) == (
        started_bundle.game_id,
        when,
        "game_official",
    )
    assert (view.tournament_key, view.plate_umpire) == ("spring", "審判")
    assert (view.section_label, view.week_label) == ("a", "b")
    assert (view.day_label, view.game_number_label) == ("c", "d")
    assert view.away_team_record_id == game["away_team_record_id"]
    assert view.home_team_record_id == game["home_team_record_id"]
    assert view.started_at == game["started_at"] == snapshot.started_at
    assert view.applied_rules == encode_applied_rules(
        decode_applied_rules(game["applied_rules"])
    )
    assert view.lineups == snapshot.lineups
    assert view.roster == snapshot.roster
    assert view.before == snapshot.before
    assert view.current_d4 == encode_d4_reference(
        started_bundle.tenant, started_bundle.game_id, 1
    )
    assert not hasattr(view, "tenant_id")


@pytest.mark.parametrize("generation", [2**31, 2**63 - 1])
def test_current_d4_follows_the_locked_generation(
    started_bundle: Bundle, generation: int
) -> None:
    """bigintの世代を狭めず、lock済みの世代でd4を作る。"""
    started_bundle.generation["generation"] = generation
    view = assembler.read_started_game(started_bundle.handle, started_bundle.game_id)
    assert type(view) is assembler.StartedGameView
    assert view.current_d4 == encode_d4_reference(
        started_bundle.tenant, started_bundle.game_id, generation
    )
    lock = next(
        t for t in started_bundle.calls if type(t) is RecordingGenerationLockToken
    )
    assert lock.generation == generation


# --- 破損は例外で出す(完了条件 8)・handleの寿命・非改変。


def test_corrupt_is_raised_not_returned(started_bundle: Bundle) -> None:
    """破損は値で返さず固定外形の例外として送出し、原因を持たない。"""
    started_bundle.game["started_at"] = datetime(2026, 1, 1)
    with pytest.raises(assembler.StartedReadCorrupt) as caught:
        assembler.read_started_game(started_bundle.handle, started_bundle.game_id)
    assert caught.value.args == ("開始済み試合を確認できません",)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            assert "StartedReadCorrupt" not in names


def test_wrong_handle_and_game_type_reject_before_reads(
    started_bundle: Bundle,
) -> None:
    """別handle・UUID強制変換・失効したwriterは、SQLの前に破損にする。"""
    for handle, game in [
        (object(), started_bundle.game_id),
        (started_bundle.handle, str(started_bundle.game_id)),
    ]:
        with pytest.raises(assembler.StartedReadCorrupt):
            assembler.read_started_game(cast(Any, handle), cast(Any, game))
    started_bundle.handle._state_key = None
    with pytest.raises(assembler.StartedReadCorrupt):
        assembler.read_started_game(started_bundle.handle, started_bundle.game_id)
    assert started_bundle.calls == []


def test_writer_rebound_during_a_read_is_corrupt(
    started_bundle: Bundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """途中で別writerキーへ移ったrowを採用しない。"""
    original = started_bundle.run

    def rebind(handle: _TenantTransaction, token: Any) -> TenantOperationResult:
        value = original(handle, token)
        if type(token) is GameReadToken:
            handle._state_key = object()
        return value

    monkeypatch.setattr(_TenantTransaction, "run", rebind)
    with pytest.raises(assembler.StartedReadCorrupt):
        assembler.read_started_game(started_bundle.handle, started_bundle.game_id)
    assert len(started_bundle.calls) == 2


def test_expired_writer_during_n2_is_corrupt(
    started_bundle: Bundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N2の計算中にscopeが終わった場合も、成功として返さない。"""
    actual = reader.evaluate_initial_game_roster

    def expire(request: Any) -> Any:
        response = actual(request)
        started_bundle.handle._expire()
        return response

    monkeypatch.setattr(reader, "evaluate_initial_game_roster", expire)
    with pytest.raises(assembler.StartedReadCorrupt):
        assembler.read_started_game(started_bundle.handle, started_bundle.game_id)


def test_unavailable_is_never_a_dispatch_condition() -> None:
    """StartedSnapshotUnavailableは破損へ写す1箇所だけで使う(完了条件 5)。"""
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    handlers: list[ast.ExceptHandler] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            handlers.append(node)
            # 例外節の中から不可視・記録ありを返さない。
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name):
                    assert inner.id not in {
                        "StartedReadNotVisible",
                        "StartedReadRecorded",
                    }
    uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "StartedSnapshotUnavailable"
    ]
    in_handlers = [
        use
        for handler in handlers
        if handler.type
        for use in ast.walk(handler.type)
        if isinstance(use, ast.Name) and use.id == "StartedSnapshotUnavailable"
    ]
    imports = [
        alias
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == "StartedSnapshotUnavailable"
    ]
    # 参照は import と、破損へ写す except の1箇所だけ。
    assert len(in_handlers) == 1 and len(imports) == 1
    assert len(uses) == 1
    only = next(h for h in handlers if h.type is not None)
    assert len(only.body) == 1 and isinstance(only.body[0], ast.Raise)
    exc = only.body[0].exc
    assert isinstance(exc, ast.Name) and exc.id == "StartedReadCorrupt"
    cause = only.body[0].cause
    assert isinstance(cause, ast.Constant) and cause.value is None
    assert len(handlers) == 1
    # if 節の条件へも出てこない。
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            assert not any(
                isinstance(n, ast.Name) and n.id == "StartedSnapshotUnavailable"
                for n in ast.walk(node.test)
            )


def test_assembler_opens_no_session_and_writes_nothing() -> None:
    """新しいSession・TX・書込操作を持たない(handleをそのまま受ける)。"""
    text = _SOURCE.read_text(encoding="utf-8")
    for word in ("sessionmaker", "create_engine", ".begin(", ".commit(", ".flush("):
        assert word not in text
    tree = ast.parse(text)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(name.startswith("sqlalchemy") for name in imported)


def test_zero_ball_reader_public_surface_is_unchanged() -> None:
    """N2の入口・戻り値の形は、本単位で変えていない(内容の同一性はdiffで確かめる)。"""
    signature = inspect.signature(reader.read_initial_started_snapshot)
    assert list(signature.parameters) == ["handle", "game_id"]
    assert [f.name for f in dataclasses.fields(reader.StartedInitialSnapshot)] == [
        "tenant_id",
        "game_id",
        "started_at",
        "generation",
        "confirmed_watermark",
        "applied_prefix",
        "lineups",
        "saved_rules_json",
        "before",
        "rules",
        "roster",
    ]
    assert issubclass(reader.StartedSnapshotUnavailable, RuntimeError)
