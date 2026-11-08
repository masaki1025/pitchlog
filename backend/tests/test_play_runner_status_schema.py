"""起点塁と走者別保存状況の公開DTO閉境界。"""

import pytest
from pydantic import ValidationError

from pitchlog.api.schemas.started_games import StartedPlayRunner


def _row(base, status, source):
    return {
        "id": "10000000-0000-0000-0000-000000000001",
        "play_id": "10000000-0000-0000-0000-000000000002",
        "base": base,
        "runner_id": "10000000-0000-0000-0000-000000000003",
        "status": status,
        "status_source": source,
        "responsible_pitcher_id": "10000000-0000-0000-0000-000000000004",
    }


def test_observed_advance_and_legacy_hold_are_public():
    """手動三進と従来holdを公開する。"""
    assert StartedPlayRunner.model_validate(_row(1, "三進", "manual")).status == "三進"
    assert StartedPlayRunner.model_validate(_row(1, "継続", "auto")).status == "継続"


@pytest.mark.parametrize(
    ("base", "status", "source"),
    [(2, "二進", "manual"), (3, "三進", "auto"), (1, "本進", "unknown")],
)
def test_impossible_or_unqualified_status_is_rejected(base, status, source):
    """逆行状況と未登録由来を拒否する。"""
    with pytest.raises(ValidationError):
        StartedPlayRunner.model_validate(_row(base, status, source))


@pytest.mark.parametrize("base", [1, 2, 3])
def test_saved_interference_out_requires_observed_source(base):
    """実保存mapperの手動裁定ラベルだけを公開し、自動裁定を推測しない。"""
    actual = StartedPlayRunner.model_validate(_row(base, "妨害裁定アウト", "manual"))
    assert actual.model_dump(mode="json") == _row(base, "妨害裁定アウト", "manual")
    with pytest.raises(ValidationError):
        StartedPlayRunner.model_validate(_row(base, "妨害裁定アウト", "auto"))


@pytest.mark.parametrize(
    ("base", "status", "source"),
    [
        (0, "妨害裁定アウト", "manual"),
        (4, "妨害裁定アウト", "manual"),
        (1, "妨害裁定アウト", "unknown"),
        (1, "妨害アウト", "manual"),
    ],
)
def test_unregistered_interference_status_is_not_public(base, status, source):
    """新規文字列や不正起点を一般的なアウトとして扱わない。"""
    with pytest.raises(ValidationError):
        StartedPlayRunner.model_validate(_row(base, status, source))
