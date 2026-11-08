"""画面由来の終了版API/CSVを、部分成功や別内容で合格させない。"""

import hashlib
import json
from uuid import UUID

import pytest
from db.test_p3_paging_screen_e2e import _verify_stats_csv

from pitchlog.api.routers.basic_stats import _CSV_HEADERS, _csv_row
from pitchlog.api.schemas.basic_stats import PlayerBasicStats
from pitchlog.exports.csv import stream_csv
from pitchlog.stats.basic_stats import BATTING_ITEMS, PITCHING_ITEMS


def _case(tmp_path):
    def items(definitions):
        return [
            dict(metric_id=key, label=label, state="available", value=0, display="0")
            for key, label, _ in definitions
        ]

    player = PlayerBasicStats(
        player_id=UUID(int=1),
        player_name="選手",
        team_record_id=UUID(int=2),
        team_name="試験",
        is_pitcher=True,
        batting=items(BATTING_ITEMS),
        pitching=items(PITCHING_ITEMS),
        pending=[],
    )
    game = str(UUID(int=3))
    api = dict(
        game_id=game,
        mode="official",
        next_cursor=None,
        players=[player.model_dump(mode="json")],
    )
    path = tmp_path / "stats.csv"
    data = b"".join(stream_csv(_CSV_HEADERS, [_csv_row(player)]))
    path.write_bytes(data)
    (tmp_path / "stats.csv.api.json").write_text(json.dumps(api))
    observed = dict(
        gameId=game,
        statsRows=1,
        csvBytes=len(data),
        csvSha256=hashlib.sha256(data).hexdigest(),
    )
    return path, api, observed


def test_csv_matches_every_api_cell(tmp_path):
    """完成CSVを、同じ終了済試合の全API表示値と照合する。"""
    path, _, observed = _case(tmp_path)
    _verify_stats_csv(path, observed)


def test_changed_csv_is_rejected_even_with_matching_size_and_sha(tmp_path):
    """ダウンロードのhashだけ合っていても、別内容を同版の成績としない。"""
    path, _, observed = _case(tmp_path)
    path.write_bytes(path.read_bytes().replace("選手".encode(), "別名".encode()))
    observed.update(
        csvBytes=path.stat().st_size,
        csvSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    with pytest.raises(AssertionError):
        _verify_stats_csv(path, observed)


@pytest.mark.parametrize("field,value", [("mode", "current"), ("next_cursor", "next")])
def test_open_or_partial_stats_are_not_final_csv(tmp_path, field, value):
    """暫定版や未取得の残頁を終了版全件と取り違えない。"""
    path, api, observed = _case(tmp_path)
    api[field] = value
    (tmp_path / "stats.csv.api.json").write_text(json.dumps(api))
    with pytest.raises(AssertionError):
        _verify_stats_csv(path, observed)
