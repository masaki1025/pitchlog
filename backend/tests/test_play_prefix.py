"""実source集約不足や自己申告でbridge/責任資格を発行しない。"""

import copy

import pytest

from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError
from pitchlog.repositories.play_prefix import (
    _require_legacy_compatibility,
    _verify_source_evidence,
)


def evidence():
    """全3play/履歴3の仮原本。真正DB証拠ではない。"""
    return {
        "content": {"prefix_ref": {"length": "3"}, "history_depth": "3"},
        "source_evidence": {
            "all_play_count": 3,
            "ordinary_play_count": 3,
            "invalid_count": 0,
            "non_play_count": 0,
            "history_count": 3,
            "pa_change_count": 0,
        },
    }


def test_exact_real_aggregate_needed_for_bridge_and_no_change():
    """ordinary長を全play長へ無言で読み替えず、PA交代を拒否する。"""
    row = evidence()
    _verify_source_evidence(row, bridge=True)
    for field in row["source_evidence"]:
        changed = copy.deepcopy(row)
        changed["source_evidence"][field] += 1
        with pytest.raises(OrdinaryPrefixError):
            _verify_source_evidence(changed, bridge=True)
    with pytest.raises(OrdinaryPrefixError):
        _verify_source_evidence({"content": row["content"]}, bridge=True)
    with pytest.raises(OrdinaryPrefixError):
        _require_legacy_compatibility("0" * 64, "1" * 64)


def _lineup_initial_from_fixture():
    """公開名簿の実ABIを使う試験入力。DB/開始資格を模擬発行しない。"""
    import json
    from datetime import UTC, datetime
    from pathlib import Path
    from types import SimpleNamespace
    from uuid import UUID

    from pitchlog.domainrt.first_pitch import StateSnapshot
    from pitchlog.domainrt.first_pitch_continuation import SavedRuleWire
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.initial_game_roster import InitialRosterProjection

    root = Path(__file__).resolve().parents[2]
    cases = json.loads(
        (
            root / "contracts/state-transition/lineup_play_prefix_cases_v1.json"
        ).read_text()
    )["cases"]
    first = next(c for c in cases if c["caseId"] == "V3-STARTED-CHAIN-01")["request"]
    raw = {"dh": True}
    for side, team in first["source"]["lineup"].items():
        raw[side] = {
            "team_id": team["teamId"],
            "entries": [
                {
                    "player_id": team["pitcherId"],
                    "batting_order": None,
                    "fielding_position": {"kind": "fielding", "position": "1"},
                },
                *[
                    {
                        "player_id": player,
                        "batting_order": slot,
                        "fielding_position": {"kind": "designated-hitter"}
                        if slot == "1"
                        else {"kind": "fielding", "position": slot},
                    }
                    for slot, player in team["battingOrder"].items()
                ],
            ],
        }
    with open_domain_host() as host:
        roster = json.loads(host.call("validateInitialGameRoster", json.dumps(raw)))
    assert roster["ok"] is True
    snapshot = copy.deepcopy(first["t1"]["before"])
    del snapshot["battingOrderBySide"]
    return SimpleNamespace(
        tenant_id=UUID(first["prefixRef"]["tenantId"]),
        game_id=UUID(first["prefixRef"]["gameId"]),
        generation=1,
        started_at=datetime(2026, 10, 31, tzinfo=UTC),
        roster=InitialRosterProjection.model_validate_json(json.dumps(roster["value"])),
        before=StateSnapshot.model_validate_json(json.dumps(snapshot)),
        rules=SavedRuleWire.model_validate_json(json.dumps(first["rules"])),
    ), cases


def test_lineup_zero_origin_ref_does_not_alias_game_or_private_digest():
    """zeroは成功開始UUID/rev1/history0。wire/full content/物理epochを区別する。"""
    from uuid import UUID

    from pitchlog.domainrt.first_ball_projection import _canonical_json
    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.lineup_play_prefix_continuation import SourcePosition
    from pitchlog.repositories.play_prefix import (
        _initial_lineup_document,
        read_lineup_prefix_document,
    )

    initial, _ = _lineup_initial_from_fixture()
    origin = str(UUID(int=9001))
    position = SourcePosition(d1="1", d2="1", appliedWatermark="0")
    with open_domain_host() as host:
        doc, source = _initial_lineup_document(
            initial, origin, "test-d4", 1, host.artifact_sha256, position
        )
    assert doc.prefix_ref.checkpoint.id == origin != str(initial.game_id)
    assert doc.prefix_ref.checkpoint.revision == "1"
    assert doc.prefix_ref.history_version == "0"
    assert doc.history_version == "1"
    assert doc.prefix_ref.checkpoint.digest != doc.content_digest
    assert doc.last_source is None and source.position == position
    assert (
        read_lineup_prefix_document(
            doc.model_dump_json(by_alias=True, exclude_unset=True)
        )
        == doc
    )
    raw = doc.model_dump(mode="json", by_alias=True, exclude_unset=True)
    for key, value in [
        ("history_version", "2"),
        ("content_digest", "0" * 64),
        ("version", "2"),
        ("projection_snapshot", {}),
    ]:
        bad = copy.deepcopy(raw)
        bad[key] = value
        with pytest.raises(OrdinaryPrefixError):
            read_lineup_prefix_document(_canonical_json(bad))


def test_native_outer_identity_revision_epoch_digest_and_state_before_ready():
    """実外側列の欠落/型/値変更を後段SQLまで持ち越さない。DB資格試験ではない。"""
    from uuid import UUID

    from pitchlog.domainrt.host import open_domain_host
    from pitchlog.domainrt.lineup_play_prefix_continuation import SourcePosition
    from pitchlog.repositories.play_prefix import (
        _check_native_lineup_row,
        _initial_lineup_document,
    )

    initial, _ = _lineup_initial_from_fixture()
    with open_domain_host() as host:
        doc, _ = _initial_lineup_document(
            initial,
            str(UUID(int=9001)),
            "test-d4",
            1,
            host.artifact_sha256,
            SourcePosition(d1="1", d2="1", appliedWatermark="0"),
        )
    row = {
        "tenant_id": str(initial.tenant_id),
        "game_id": str(initial.game_id),
        "internal_generation": initial.generation,
        "id": doc.id,
        "revision": int(doc.revision),
        "history_version": int(doc.history_version),
        "recovery_generation": 1,
        "confirmed_watermark": 0,
        "applied_watermark": 0,
        "content_digest": doc.content_digest,
        "state": "current",
        "saved_at": "2026-10-31T00:00:00Z",
    }
    arguments = {
        "tenant": initial.tenant_id,
        "game": initial.game_id,
        "generation": initial.generation,
        "epoch": 1,
        "watermark": 0,
    }
    _check_native_lineup_row(row, doc, **arguments)
    for field in row:
        for member in (None, True, "unknown", -1):
            changed = copy.deepcopy(row)
            changed[field] = member
            if field == "saved_at" and member is not None:
                continue
            with pytest.raises(OrdinaryPrefixError):
                _check_native_lineup_row(changed, doc, **arguments)
        changed = copy.deepcopy(row)
        del changed[field]
        with pytest.raises(OrdinaryPrefixError):
            _check_native_lineup_row(changed, doc, **arguments)
