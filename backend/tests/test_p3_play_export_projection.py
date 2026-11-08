"""P3列写像は既唯一表示helperを再利用し、旧記録時表示を保持する。"""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from test_record_export_direct_projection import _identity

from pitchlog.exports.p3_projection import CorrectionResultReference, project_p3_direct
from pitchlog.exports.p3_snapshot import P3SnapshotIdentity
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.exports.record_projection import project_recorded_direct
from pitchlog.sync.idempotency import source_fingerprint


def _inputs(target=True):
    """表示値入力であり、capsule/保存資格のmintを模擬しない。"""
    original = _identity()
    old_payload = deepcopy(original.payload)
    old_payload["observations"]["resultId"] = "batting-result.ball"
    old_payload["calculation"]["response"]["value"]["t1"]["plateAppearanceEnded"] = (
        False
    )
    old_play = {
        **original.play,
        "id": UUID(int=4),
        "game_id": original.source.game_id,
        "version": 1,
        "batting_result_key": "batting-result.ball",
    }
    original = replace(
        original,
        play=old_play,
        payload=old_payload,
        admin_vocabularies=(
            {"key": "batting-result.ball", "display_name": "旧記録時のボール"},
        ),
    )
    values = project_recorded_direct(original)
    for index in (34, 86, 87):
        values[CSV_HEADERS["plays.csv"][index]] = "元の生成集計"
    old_play = {
        key: str(value) if type(value) is UUID else value
        for key, value in old_play.items()
    }
    assert type(old_play["id"]) is str
    payload = deepcopy(old_payload)
    payload["calculation"]["request"]["t1"]["before"]["stateFields"][
        "state.count.balls"
    ] = "2"
    event = UUID(int=999) if target else original.source.source_event_id
    play_id = UUID(int=888) if target else UUID(old_play["id"])
    new_play = {**old_play, "id": str(play_id), "source_event_id": str(event)}
    if target:
        new_play["batting_result_key"] = "batting-result.called-strike"
        payload["observations"]["resultId"] = "batting-result.called-strike"
    d1 = 1 if target else 2
    item = {
        "d1": d1,
        "d2": d1 * 1000,
        "state": "corrected",
        "original_event_id": str(original.source.source_event_id),
        "effective_event_id": str(event),
        "original_play_row_id": old_play["id"],
        "effective_play_row_id": str(play_id),
        "original_payload": old_payload,
        "original_history_entry": {},
        "original_play_row": old_play,
        "original_play_runners": [],
        "payload": payload,
        "history_entry": {},
        "play_row": new_play,
        "play_runners": [],
    }
    item["digest"] = source_fingerprint(item)
    key = P3SnapshotIdentity(
        original.source.tenant_id,
        original.source.game_id,
        1,
        UUID(int=777),
        d1,
        UUID(old_play["id"]),
        event,
        play_id,
        1,
        item["digest"],
        "a" * 64,
        UUID(int=666),
    )
    ref = (
        CorrectionResultReference(
            key.tenant_id,
            key.game_id,
            key.capsule_id,
            event,
            UUID(int=555),
            "batting-result.called-strike",
            "訂正時に取得した見逃し",
            datetime(2026, 11, 8, tzinfo=timezone.utc),
        )
        if target
        else None
    )
    return values, item, key, ref


def test_target_reuses_original_references_and_single_state_projector():
    """新result参照以外の旧表示を保持し、保存T1を直写する。"""
    values, item, key, ref = _inputs()
    result = project_p3_direct(values, item, key, target_d1=1, reference=ref)
    assert result[CSV_HEADERS["plays.csv"][15]] == "2"
    assert result[CSV_HEADERS["plays.csv"][45]] == "訂正時に取得した見逃し"
    for index in (
        0,
        1,
        7,
        8,
        27,
        32,
        33,
        59,
        63,
        64,
        71,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
        84,
        85,
    ):
        assert (
            result[CSV_HEADERS["plays.csv"][index]]
            == values[CSV_HEADERS["plays.csv"][index]]
        )
    assert len(result) == 85
    assert set(result) == set(CSV_HEADERS["plays.csv"]) - {
        CSV_HEADERS["plays.csv"][i] for i in (34, 86, 87)
    }


def test_follower_changes_only_completed_t1_display_fields():
    """同じ物理原本の後続は語彙参照を取り直さない。"""
    values, item, key, ref = _inputs(False)
    result = project_p3_direct(values, item, key, target_d1=1, reference=ref)
    assert result[CSV_HEADERS["plays.csv"][45]] == values[CSV_HEADERS["plays.csv"][45]]
    assert result[CSV_HEADERS["plays.csv"][15]] == "2"


@pytest.mark.parametrize(
    "mutation",
    [
        "no-reference",
        "other-capsule",
        "other-event",
        "unknown-key",
        "naive-time",
        "missing-column",
        "forged-digest",
        "changed-observation",
        "changed-name-identity",
        "changed-physical",
        "changed-runner",
    ],
)
def test_missing_or_foreign_sources_are_not_current_roster_or_zero_filled(mutation):
    """新参照/旧snapshot/真正payloadの不足や改変を拒否する。"""
    values, item, key, ref = _inputs()
    if mutation == "no-reference":
        ref = None
    elif mutation == "other-capsule":
        ref = replace(ref, capsule_id=UUID(int=444))
    elif mutation == "other-event":
        ref = replace(ref, effective_event_id=UUID(int=444))
    elif mutation == "unknown-key":
        with pytest.raises(PlayExportSupplyError):
            replace(ref, key="batting-result.home-run")
        return
    elif mutation == "naive-time":
        with pytest.raises(PlayExportSupplyError):
            replace(ref, captured_at=datetime(2026, 11, 8))
        return
    elif mutation == "missing-column":
        values.pop(next(iter(values)))
    elif mutation == "forged-digest":
        item["payload"]["observations"]["resultId"] = "batting-result.ball"
    elif mutation == "changed-observation":
        item["payload"]["observations"]["pitchSpeed"] = {"kmh": 100}
    elif mutation == "changed-name-identity":
        item["payload"]["participants"] = {"batter": "other-player"}
    elif mutation == "changed-physical":
        item["play_row"]["batter_id"] = str(UUID(int=444))
    else:
        item["play_runners"] = [{"runner": "other"}]
    if mutation not in {"forged-digest"}:
        item["digest"] = source_fingerprint(
            {k: v for k, v in item.items() if k != "digest"}
        )
        key = replace(key, item_digest=item["digest"])
    with pytest.raises(PlayExportSupplyError):
        project_p3_direct(values, item, key, target_d1=1, reference=ref)


def test_p3_origin_uses_actual_context_and_keeps_original_origin():
    """通常originは変更せずP3のeffective参照を別版へ記録する。"""
    values, item, key, ref = _inputs()
    result = project_p3_direct(values, item, key, target_d1=1, reference=ref)
    raw_origin = result[CSV_HEADERS["plays.csv"][72]]
    assert isinstance(raw_origin, str)
    origin = json.loads(raw_origin)
    assert origin["formatVersion"] == "play-export-input-origin-p3-v1"
    assert origin["operationKind"] == "play_change"
    assert origin["sourceEventId"] == str(key.effective_event_id)
    assert origin["capsuleId"] == str(key.capsule_id)
    assert origin["itemDigest"] == key.item_digest
    assert origin["originalInputOrigin"] == json.loads(
        values[CSV_HEADERS["plays.csv"][72]]
    )
    assert (
        origin["calculationArtifactSha256"]
        == item["payload"]["calculation"]["artifactSha256"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-key",
        "unknown-version",
        "unknown-operation",
        "bad-source-id",
        "bad-artifact",
        "unknown-kind",
    ],
)
def test_input_origin_unknown_shape_is_not_relabelled(mutation):
    """旧入力経路が閉版でない場合は推測してP3版へ補修しない。"""
    values, item, key, ref = _inputs()
    origin = json.loads(values[CSV_HEADERS["plays.csv"][72]])
    if mutation == "unknown-key":
        origin["credential"] = "must-not-copy"
    elif mutation == "unknown-version":
        origin["formatVersion"] = "unknown"
    elif mutation == "unknown-operation":
        origin["operationKind"] = "game_reopen"
    elif mutation == "bad-source-id":
        origin["sourceEventId"] = "not-a-uuid"
    elif mutation == "bad-artifact":
        origin["calculationArtifactSha256"] = "x" * 64
    else:
        origin["sourceKind"] = "unknown"
    values[CSV_HEADERS["plays.csv"][72]] = json.dumps(origin)
    with pytest.raises(PlayExportSupplyError):
        project_p3_direct(values, item, key, target_d1=1, reference=ref)


def test_second_correction_origin_has_constant_depth_and_keeps_first_record():
    """二度目同値followersでも旧監査を再帰JSONへ複写しない。"""
    from pitchlog.exports.p3_projection import p3_input_origin

    values, item, key, _ = _inputs()
    normal = values[CSV_HEADERS["plays.csv"][72]]
    first = p3_input_origin(normal, item["payload"], key, target=True)
    second_key = replace(key, capsule_id=UUID(int=7777))
    second = p3_input_origin(first, item["payload"], second_key, target=True)
    raw = json.loads(second)
    assert raw["capsuleId"] == str(second_key.capsule_id)
    assert raw["originalInputOrigin"] == json.loads(normal)
    assert raw["originalInputOrigin"]["formatVersion"] == "play-export-input-origin-v1"
    assert json.loads(first)["capsuleId"] == str(key.capsule_id)
