"""妨害の副結果だけで完了した打席を、記録時語彙で表示する。"""

import copy
from dataclasses import replace

import pytest
from test_interference_play_row import _actual
from test_record_export_direct_projection import _identity

from pitchlog.exports.record_projection import (
    RecordedExportProjectionUnavailable,
    _native_plate_display,
)

_LABELS = {
    "penalty": "当時の打撃妨害",
    "obstruction": "当時の走塁妨害",
    "offensive": "当時の守備妨害",
}


def _source(case: str):
    """実859のT1/物理mapperと記録時の表示語彙を束縛する。"""
    row, raw = copy.deepcopy(_actual(case))
    primary = row["batting_result_key"]
    secondary = row["secondary_batting_result_key"]
    vocab = [
        {
            "key": secondary,
            "category": "batting_result",
            "display_name": _LABELS.get(case, "副結果表示"),
            "disabled": False,
        }
    ]
    if primary is not None:
        vocab.append(
            {
                "key": primary,
                "category": "batting_result",
                "display_name": "当時の単打",
                "disabled": False,
            }
        )
    identity = replace(
        _identity(), play=row, payload=raw, admin_vocabularies=tuple(vocab)
    )
    return identity


@pytest.mark.parametrize("case", tuple(_LABELS))
def test_completed_interference_without_primary_uses_recorded_secondary_label(case):
    """真正副結果と裁定だけを既唯一表示生成器へ渡す。"""
    identity = _source(case)
    before = copy.deepcopy(identity.payload)
    assert identity.play["batting_result_key"] is None
    assert identity.payload["calculation"]["response"]["value"]["t1"][
        "plateAppearanceEnded"
    ] is True
    assert _native_plate_display(identity) == _LABELS[case]
    assert identity.payload == before


def test_adopted_play_keeps_primary_label():
    """実プレイ採用では副妨害の表示名に主結果を上書きしない。"""
    identity = _source("play")
    assert _native_plate_display(identity) == "当時の単打"


@pytest.mark.parametrize(
    "fault",
    (
        "wrong-secondary",
        "unknown-secondary",
        "wrong-ruling",
        "wrong-observation",
        "wrong-adoption",
        "missing-vocabulary",
        "disabled-vocabulary",
        "wrong-category",
        "wrong-primary",
        "wrong-event-kind",
    ),
)
def test_inconsistent_or_unavailable_interference_label_stays_closed(fault):
    """欠測や別裁定を副結果名で補完しない。"""
    identity = _source("penalty")
    row = copy.deepcopy(identity.play)
    raw = copy.deepcopy(identity.payload)
    vocab = [dict(item) for item in identity.admin_vocabularies]
    if fault == "wrong-secondary":
        row["secondary_batting_result_key"] = "secondary-result.obstruction"
    elif fault == "unknown-secondary":
        row["secondary_batting_result_key"] = "secondary-result.unknown"
        raw["calculation"]["request"]["t1"]["resultId"] = (
            "secondary-result.unknown"
        )
        raw["observations"]["resultId"] = "secondary-result.unknown"
    elif fault == "wrong-ruling":
        raw["calculation"]["request"]["t1"]["interferenceRuling"][
            "kind"
        ] = "obstruction"
        raw["observations"]["interferenceRuling"]["kind"] = "obstruction"
    elif fault == "wrong-observation":
        raw["observations"]["resultId"] = "secondary-result.obstruction"
    elif fault == "wrong-adoption":
        raw["calculation"]["request"]["t1"]["interferenceRuling"][
            "adopted"
        ] = {"kind": "play-result", "resultId": "batting-result.single"}
        raw["observations"]["interferenceRuling"]["adopted"] = {
            "kind": "play-result",
            "resultId": "batting-result.single",
        }
    elif fault == "missing-vocabulary":
        vocab.clear()
    elif fault == "disabled-vocabulary":
        vocab[0]["disabled"] = True
    elif fault == "wrong-category":
        vocab[0]["category"] = "batted_ball"
    elif fault == "wrong-primary":
        row["batting_result_key"] = "batting-result.single"
        vocab.append(
            {
                "key": "batting-result.single",
                "category": "batting_result",
                "display_name": "単打",
                "disabled": False,
            }
        )
    else:
        row["event_kind"] = "runner-event"
    changed = replace(identity, play=row, payload=raw, admin_vocabularies=tuple(vocab))
    if fault == "wrong-primary":
        assert _native_plate_display(changed) == "単打"
    else:
        with pytest.raises(RecordedExportProjectionUnavailable):
            _native_plate_display(changed)


def test_unrelated_completed_pitch_with_missing_primary_stays_closed():
    """任意の完了打席へ副結果 fallback を拡張しない。"""
    identity = _identity()
    row = dict(identity.play)
    row["batting_result_key"] = None
    with pytest.raises(RecordedExportProjectionUnavailable):
        _native_plate_display(replace(identity, play=row))
