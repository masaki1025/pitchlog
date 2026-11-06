"""毎球CSVの保存値参照・欠測分離・88列写像をpureに検査する。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.repositories import base
from pitchlog.repositories.play_export import (
    COLUMN_SUPPLY,
    MAX_PAGE_SIZE,
    PlayExportEventsToken,
    PlayExportParticipationsToken,
    PlayExportPlayRowsToken,
    PlayExportRunnersToken,
    PlayExportSnapshot,
    PlayExportSource,
    PlayExportSourceUnavailable,
    PlayExportTenantVocabularyToken,
    _roster_arrays,
    iter_sidecar_rows,
    project_play_cells,
    project_play_row,
)

TENANT = uuid4()
GAME = uuid4()
AWAY = uuid4()
HOME = uuid4()
BATTER = uuid4()
PITCHER = uuid4()
CATCHER = uuid4()
RUNNER = uuid4()
EVENT = uuid4()


def _player(name: str, *, throws: str = "right", bats: str = "right") -> dict:
    """現在参照の選手行。"""
    return {
        "id": uuid4(),
        "team_record_id": AWAY,
        "name": name,
        "throws": throws,
        "bats": bats,
        "uniform_number": "007",
        "roster_status_key": "active",
        "roster_label_key": None,
        "hidden_at": None,
    }


def _game() -> dict:
    """G01の保存値。"""
    return {
        "id": GAME,
        "tenant_id": TENANT,
        "scheduled_at": datetime(2026, 7, 9, tzinfo=UTC),
        "game_type_key": "game_official",
        "section_label": "春季",
        "week_label": "3",
        "day_label": "土",
        "game_number_label": "1",
        "plate_umpire": "主審",
        "away_team_record_id": AWAY,
        "home_team_record_id": HOME,
        "started_at": datetime(2026, 7, 9, 9, 0, tzinfo=UTC),
        "status": "in_progress",
        "trashed_at": None,
        "hidden_at": None,
    }


def _lineup(team_id: UUID, player_ids: tuple[UUID, ...]) -> dict:
    """9人分の保存lineup。"""
    entries = []
    for index, player_id in enumerate(player_ids, start=1):
        entries.append(
            {
                "player_id": str(player_id),
                "batting_order": index,
                "fielding_position": {"kind": "fielding", "position": index},
                "uniform_number_snapshot": f"00{index}",
            }
        )
    return {
        "tenant_id": TENANT,
        "id": uuid4(),
        "game_id": GAME,
        "team_record_id": team_id,
        "entries_with_uniform_number_snapshot": entries,
    }


def _participations(team_id: UUID, player_ids: tuple[UUID, ...]) -> tuple[dict, ...]:
    """D2=1で有効な打順・守備区間。"""
    rows = []
    for index, player_id in enumerate(player_ids, start=1):
        rows.append(
            {
                "id": uuid4(),
                "tenant_id": TENANT,
                "game_id": GAME,
                "slot_kind": "batting_order",
                "slot": str(index),
                "player_id": player_id,
                "valid_from_d2": 1,
                "valid_until_d2": None,
                "uniform_number_snapshot": f"00{index}",
                "unknown_for_migration": False,
                "retired_at": None,
            }
        )
        rows.append(
            {
                "id": uuid4(),
                "tenant_id": TENANT,
                "game_id": GAME,
                "slot_kind": "fielding_position",
                "slot": str(index),
                "player_id": player_id,
                "valid_from_d2": 1,
                "valid_until_d2": None,
                "uniform_number_snapshot": f"00{index}",
                "unknown_for_migration": False,
                "retired_at": None,
            }
        )
    return tuple(rows)


def _payload() -> dict:
    """保存T1のbefore/afterと観測だけを持つevent payload。"""
    before = {
        "stateFields": {
            "state.half": "top",
            "state.count.strikes": "0",
            "state.count.balls": "0",
            "state.outs": "0",
            "state.runners": "empty",
            "state.battingOrder": "1",
            "state.tiebreakActive": False,
            "state.gameEnded": False,
            "state.inning": "1",
            "state.score": {"home": "0", "away": "0"},
        },
        "scoreboard": {
            "inningScores": {"home": "0", "away": "0"},
            "hits": "0",
            "errors": "0",
            "strikeouts": "0",
            "walks": "0",
        },
    }
    after = {
        "stateFields": {
            "state.half": "top",
            "state.count.strikes": "0",
            "state.count.balls": "1",
            "state.outs": "0",
            "state.runners": "first",
            "state.battingOrder": "2",
            "state.tiebreakActive": False,
            "state.gameEnded": False,
            "state.inning": "1",
            "state.score": {"home": "0", "away": "0"},
        },
        "scoreboard": {
            "inningScores": {"home": "0", "away": "0"},
            "hits": "0",
            "errors": "0",
            "strikeouts": "0",
            "walks": "0",
        },
    }
    return {
        "formatVersion": "ordinary-pitch-play-v1",
        "observations": {
            "pitchTypeKey": "pitch-type.fastball",
            "course": {"unit": "1/263", "x": "132", "y": "66"},
            "pitchSpeed": {"kmh": "142.5", "outsideRangeConfirmed": False},
            "stance": "3",
            "battingSide": "右",
        },
        "participants": {
            "batterId": str(BATTER),
            "pitcherId": str(PITCHER),
            "catcherId": str(CATCHER),
            "battingOrder": "1",
        },
        "calculation": {
            "formatVersion": "ordinary-pitch-calculation-v1",
            "artifactSha256": "0" * 64,
            "request": {"t1": {"before": before}},
            "response": {
                "ok": True,
                "value": {
                    "t1": {
                        "after": after,
                        "statFlags": {"投球数": True},
                        "plateAppearanceEnded": False,
                    }
                },
            },
        },
    }


def _source() -> PlayExportSource:
    """全参照が揃った合成source。"""
    away_players = tuple(_player(f"先攻{index}") for index in range(1, 10))
    home_players = tuple(_player(f"後攻{index}") for index in range(1, 10))
    players = {row["id"]: row for row in (*away_players, *home_players)}
    # 打者・走者・投手・捕手は実際の参照先へ差し替える。
    players[BATTER] = _player("打者", bats="left")
    players[PITCHER] = _player("投手", throws="left")
    players[RUNNER] = _player("走者")
    players[PITCHER]["team_record_id"] = HOME
    players[RUNNER]["team_record_id"] = AWAY
    players[CATCHER] = _player("捕手")
    players[CATCHER]["team_record_id"] = HOME

    away_order = (BATTER, RUNNER, *(row["id"] for row in away_players[2:]))
    home_order = (
        *(row["id"] for row in home_players[:0]),
        PITCHER,
        CATCHER,
        *(row["id"] for row in home_players[3:]),
    )
    lineups = (_lineup(AWAY, away_order), _lineup(HOME, home_order))
    participations = (
        *_participations(AWAY, away_order),
        *_participations(HOME, home_order),
    )
    event = {
        "id": EVENT,
        "tenant_id": TENANT,
        "game_id": GAME,
        "generation": 1,
        "d1": 1,
        "d2": 1,
        "d5": uuid4(),
        "ledger_kind": "accepted",
        "event_kind": "play_input",
        "payload": _payload(),
        "state_diff": {},
        "is_tombstone": False,
        "replaced_at": None,
        "target_generation": None,
        "target_d1": None,
        "expected_version": None,
        "change_order": None,
        "legacy_row_identifier": None,
        "migration_unverified": False,
        "retired_at": None,
    }
    return PlayExportSource(
        handle=cast(Any, None),
        game=_game(),
        lineups=lineups,
        participations=participations,
        players=players,
        teams={
            AWAY: {
                "id": AWAY,
                "tenant_id": TENANT,
                "kind": "opponent",
                "name": "先攻チーム",
                "hidden_at": None,
            },
            HOME: {
                "id": HOME,
                "tenant_id": TENANT,
                "kind": "self",
                "name": "後攻チーム",
                "hidden_at": None,
            },
        },
        tenant_vocabularies={
            ("pitch_type", "pitch-type.fastball"): {
                "key": "pitch-type.fastball",
                "display_name": "ストレート",
            }
        },
        events={EVENT: event},
        snapshot=PlayExportSnapshot(GAME, "a" * 64, "b" * 64, "2026-07-09 09:00:00"),
    )


def test_column_supply_matches_all_88_headers() -> None:
    """供給matrixの列順が候補JSONの88列と一致する。"""
    assert tuple(row[0] for row in COLUMN_SUPPLY) == CSV_HEADERS["plays.csv"]
    assert len(COLUMN_SUPPLY) == 88
    assert {row[1] for row in COLUMN_SUPPLY} == set(range(88))


def test_registry_contains_five_closed_read_operations() -> None:
    """追加read tokenが単一表・tenant条件付きで登録される。"""
    for token_type in (
        PlayExportPlayRowsToken,
        PlayExportEventsToken,
        PlayExportRunnersToken,
        PlayExportParticipationsToken,
        PlayExportTenantVocabularyToken,
    ):
        assert token_type in base._OPERATION_REGISTRY


def test_tokens_reject_implicit_conversion_and_free_filters() -> None:
    """文字列UUID・不正上限・未知語彙カテゴリを拒否する。"""
    with pytest.raises(ValueError):
        PlayExportPlayRowsToken(cast(Any, "not-a-uuid"), None, None, 1)
    with pytest.raises(ValueError):
        PlayExportPlayRowsToken(GAME, 1, None, 1)
    with pytest.raises(ValueError):
        PlayExportEventsToken(GAME, False, 1, None, 1)
    with pytest.raises(ValueError):
        PlayExportRunnersToken((), None, None, 1)
    with pytest.raises(ValueError):
        PlayExportParticipationsToken(GAME, None, MAX_PAGE_SIZE + 1)
    with pytest.raises(ValueError):
        PlayExportTenantVocabularyToken("admin", None, 1)


def test_projection_reads_saved_t1_without_recalculation() -> None:
    """保存T1のafter/観測/走者だけを写し、既知の未接続列だけを欠測にする。"""
    source = _source()
    play = {
        "id": uuid4(),
        "game_id": GAME,
        "source_event_id": EVENT,
        "play_number": 1,
        "batting_order": 1,
        "batter_id": BATTER,
        "batting_side": "右",
        "strategy_key": None,
        "strategy_detail_key": None,
        "strategy_result_key": None,
        "pitcher_id": PITCHER,
        "catcher_id": CATCHER,
        "batter_status": "継続",
        "event_kind": "pitch",
        "stance": "3",
        "pitch_type_key": "pitch-type.fastball",
        "batting_result_key": "batting-result.ball",
        "secondary_batting_result_key": None,
        "raw_fielder_position": None,
        "batted_ball_type": None,
        "batted_ball_strength": None,
        "pickoff_type": None,
        "pickoff_detail": None,
        "error_type": None,
        "raw_error_position": None,
        "press": None,
        "fake_run": None,
        "comment": "メモ",
        "hidden_at": None,
        "version": 1,
    }
    runner = {
        "id": uuid4(),
        "play_id": play["id"],
        "base": 1,
        "runner_id": RUNNER,
        "status": "継続",
        "status_source": "auto",
        "responsible_pitcher_id": PITCHER,
        "retired_at": None,
    }
    values, missing = project_play_cells(source, play, (runner,))
    headers = {item.header for item in missing}
    assert headers == {
        "球数",
        "コースX",
        "コースY",
        "打球位置X",
        "打球位置Y",
        "打席結果",
        "Result_col",
        "先攻打順",
        "後攻打順",
        "top_score",
        "bottom_score",
    }
    assert values["回"] == "1"
    assert values["表.裏"] == "表"
    assert values["S"] == "0"
    assert values["B"] == "1"
    assert values["アウト"] == "0"
    assert values["打席の継続"] == "打席継続"
    assert values["イニング継続"] == "イニング継続"
    assert values["試合継続"] == "試合継続"
    assert values["球種"] == "ストレート"
    assert values["打撃結果"] == "ボール"
    assert values["球速"] == "142.5"
    assert values["一走打順"] == 2
    assert values["一走氏名"] == "走者"
    assert values["一走状況"] == "継続"
    assert values["打者氏名"] == "打者"
    assert values["投手左右"] == "左"


def test_projection_never_replaces_missing_with_zero_or_current_roster() -> None:
    """未接続列がある行は部分88列を返さない。"""
    source = _source()
    play = {
        "id": uuid4(),
        "game_id": GAME,
        "source_event_id": EVENT,
        "play_number": 1,
        "batting_order": 1,
        "batter_id": BATTER,
        "batting_side": "右",
        "strategy_key": None,
        "strategy_detail_key": None,
        "strategy_result_key": None,
        "pitcher_id": PITCHER,
        "catcher_id": CATCHER,
        "batter_status": None,
        "event_kind": "pitch",
        "stance": None,
        "pitch_type_key": "pitch-type.fastball",
        "batting_result_key": "batting-result.ball",
        "secondary_batting_result_key": None,
        "raw_fielder_position": None,
        "batted_ball_type": None,
        "batted_ball_strength": None,
        "pickoff_type": None,
        "pickoff_detail": None,
        "error_type": None,
        "raw_error_position": None,
        "press": None,
        "fake_run": None,
        "comment": None,
        "hidden_at": None,
        "version": 1,
    }
    with pytest.raises(PlayExportSourceUnavailable) as error:
        project_play_row(source, play, ())
    assert error.value.missing
    assert all(item.header in CSV_HEADERS["plays.csv"] for item in error.value.missing)


def test_roster_arrays_keep_legacy_lengths_and_saved_uniforms() -> None:
    """旧配列は保存lineup/区間から作り、固定長を勝手に伸ばさない。"""
    source = _source()
    arrays = _roster_arrays(source, AWAY, 1)
    assert arrays is not None
    assert [len(arrays[key]) for key in ("poses", "names", "nums", "lrs")] == [
        10,
        20,
        10,
        11,
    ]
    assert arrays["names"][0] == "打者"
    assert arrays["nums"][0] == "001"
    assert arrays["names"][9] == "打者"
    assert arrays["names"][10] == "走者"


class _FakeHandle:
    """登録readの代わりに固定ページを返す。"""

    def __init__(self, *, plays=(), runners=()):
        self.plays = list(plays)
        self.runners = list(runners)
        self.calls = []

    def run(self, operation):
        from pitchlog.repositories.play_export import (
            PLAY_ROW_COLUMNS,
            PLAY_RUNNER_COLUMNS,
        )
        from pitchlog.repositories.tokens import TenantOperationResult

        self.calls.append(operation)
        if isinstance(operation, PlayExportPlayRowsToken):
            page = self.plays.pop(0) if self.plays else []
            columns = PLAY_ROW_COLUMNS
        elif isinstance(operation, PlayExportRunnersToken):
            page = self.runners.pop(0) if self.runners else []
            columns = PLAY_RUNNER_COLUMNS
        else:
            raise AssertionError("未想定のoperation")
        return TenantOperationResult(
            tuple(tuple(row[column] for column in columns) for row in page)
        )


def _play(number: int, player_id: UUID = BATTER) -> dict:
    """iter_playsが必要とするPlayRow全列。"""
    return {
        "id": uuid4(),
        "tenant_id": TENANT,
        "game_id": GAME,
        "source_event_id": EVENT,
        "play_number": number,
        "batting_order": 1,
        "batter_id": player_id,
        "batting_side": "右",
        "strategy_key": None,
        "strategy_detail_key": None,
        "strategy_result_key": None,
        "pitcher_id": PITCHER,
        "catcher_id": CATCHER,
        "batter_status": None,
        "event_kind": "pitch",
        "stance": None,
        "course_x": None,
        "course_y": None,
        "pitch_type_key": None,
        "batting_result_key": None,
        "secondary_batting_result_key": None,
        "raw_fielder_position": None,
        "resolved_fielder_id": None,
        "batted_ball_type": None,
        "batted_ball_strength": None,
        "hit_x": None,
        "hit_y": None,
        "pickoff_type": None,
        "pickoff_detail": None,
        "error_type": None,
        "raw_error_position": None,
        "resolved_error_player_id": None,
        "pitch_speed": None,
        "press": None,
        "fake_run": None,
        "comment": None,
        "version": 1,
        "hidden_at": None,
        "legacy_row_identifier": None,
        "migration_unverified": False,
        "import_batch_id": None,
        "retired_at": None,
    }


def _runner(play_id: UUID) -> dict:
    """iter_runners_forが必要とするPlayRunner全列。"""
    return {
        "id": uuid4(),
        "tenant_id": TENANT,
        "play_id": play_id,
        "base": 1,
        "runner_id": RUNNER,
        "status": "継続",
        "status_source": "auto",
        "responsible_pitcher_id": PITCHER,
        "retired_at": None,
        "import_batch_id": None,
    }


def test_iter_plays_continues_keyset_across_500_boundary() -> None:
    """500行の次ページが0から再開せず、重複欠落なく継続する。"""
    first = [_play(number) for number in range(1, 501)]
    second = [_play(501)]
    handle = _FakeHandle(plays=[first, second])
    source = replace(_source(), handle=handle)

    plays = list(source.iter_plays())

    assert len(plays) == 501
    assert plays[0]["play_number"] == 1
    assert plays[-1]["play_number"] == 501
    tokens = [
        call for call in handle.calls if isinstance(call, PlayExportPlayRowsToken)
    ]
    assert tokens[0].after_play_number is None
    assert tokens[1].after_play_number == 500
    assert tokens[1].after_id == first[-1]["id"]


def test_iter_runners_batches_all_page_play_ids_once() -> None:
    """ページ内play_id集合を1回の走者readへ渡し、N+1にしない。"""
    first = _play(1)
    second = _play(2)
    handle = _FakeHandle(
        plays=[[first, second]],
        runners=[[_runner(first["id"]), _runner(second["id"])]],
    )
    source = replace(_source(), handle=handle)

    runners = list(source.iter_runners_for((first["id"], second["id"])))

    assert len(runners) == 2
    tokens = [call for call in handle.calls if isinstance(call, PlayExportRunnersToken)]
    assert tokens == [
        PlayExportRunnersToken((first["id"], second["id"]), None, None, MAX_PAGE_SIZE)
    ]


def test_visibility_closes_hidden_trashed_and_other_tenant() -> None:
    """可視判定はtenant・trashed・hidden・statusを同じ非成功へ閉じる。"""
    from pitchlog.repositories.play_export import _visible_game

    game = _game()
    assert _visible_game(game, GAME, TENANT)
    assert not _visible_game(game, GAME, uuid4())
    assert not _visible_game({**game, "trashed_at": datetime.now(UTC)}, GAME, TENANT)
    assert not _visible_game({**game, "hidden_at": datetime.now(UTC)}, GAME, TENANT)
    assert not _visible_game({**game, "status": "trashed"}, GAME, TENANT)
    assert not _visible_game({**game, "status": "hidden"}, GAME, TENANT)


def test_all_88_columns_are_supplied_or_in_the_declared_gap() -> None:
    """供給値と欠測の和が88列に一致し、暗黙の空欄を作らない。"""
    source = _source()
    play = _play(1)
    values, missing = project_play_cells(source, play, ())
    assert set(values) <= set(CSV_HEADERS["plays.csv"])
    assert set(values) | {item.header for item in missing} == set(
        CSV_HEADERS["plays.csv"]
    )
    assert len({item.header for item in missing}) == len(missing)
    assert {item.header for item in missing} == {
        "球数",
        "コースX",
        "コースY",
        "打球位置X",
        "打球位置Y",
        "打席結果",
        "Result_col",
        "先攻打順",
        "後攻打順",
        "top_score",
        "bottom_score",
    }


def test_all_nine_sidecars_use_fixed_headers() -> None:
    """9サイドカーが固定ヘッダの全キーを返す。"""
    play = _play(1)
    runner = _runner(play["id"])

    for name in (
        "play_links.csv",
        "events.csv",
        "runners.csv",
        "lineups.csv",
        "participations.csv",
        "game.csv",
        "references.csv",
        "projections.csv",
        "preserved_sources.csv",
    ):
        handle = _FakeHandle(plays=[[play]], runners=[[runner]])
        source = replace(_source(), handle=handle)
        rows = list(iter_sidecar_rows(source, name))
        if name == "preserved_sources.csv":
            assert rows == []
            continue
        assert rows
        for row in rows:
            assert set(row.values) == set(CSV_HEADERS[name])
        if name == "play_links.csv":
            assert rows[0].values["row_number"] == 1
            assert rows[0].values["recording_generation"] == 1
            assert rows[0].values["event_sequence"] == 1
        if name == "references.csv":
            kinds = [row.values["reference_kind"] for row in rows]
            assert kinds == sorted(kinds)
