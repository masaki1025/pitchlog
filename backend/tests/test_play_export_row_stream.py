"""CSV完成行を全件listにせず、一行ずつarchiveへ渡す。"""

import json
from itertools import islice
from unittest.mock import Mock
from uuid import UUID

import pytest

from pitchlog.exports.play_export_csv import _canonical_json, _events_rows
from pitchlog.exports.play_rows import PlayExportSupplyError
from pitchlog.repositories.play_export import PlayExportBundle


def test_event_rows_are_consumed_only_on_demand() -> None:
    """2001件を先行消費せず、500境界でも各原本を一度だけ写す。"""
    consumed = []

    def source():
        for i in range(2001):
            consumed.append(i)
            yield {
                "id": UUID(int=10 + i),
                "generation": 1,
                "d2": i,
                "event_kind": "play_input",
                "target_generation": None,
                "target_d1": None,
                "expected_version": None,
                "change_order": None,
                "is_tombstone": False,
                "replaced_at": None,
                "retired_at": None,
                "payload": {},
                "state_diff": None,
            }

    # formatter単体のsource。真正DB/認可の証拠には数えない。
    bundle = Mock(spec=PlayExportBundle, game={"id": UUID(int=1)}, events=source())
    rows = _events_rows(bundle, "a" * 64)
    assert consumed == []
    first = next(rows)
    assert first.values["event_sequence"] == 0
    assert consumed == [0]
    assert sum(1 for _ in islice(rows, 499)) == 499
    assert consumed == list(range(500))
    assert sum(1 for _ in rows) == 1501
    assert consumed == list(range(2001))


def test_event_payload_redacts_external_d4_and_credentials_with_visible_version():
    """監査業務値は保持し、外部D4/資格は閉じた版で明示redactionする。"""
    event = {
        "id": UUID(int=2),
        "generation": 7,
        "d2": 4,
        "event_kind": "game_reopen",
        "target_generation": None,
        "target_d1": None,
        "expected_version": None,
        "change_order": None,
        "is_tombstone": False,
        "replaced_at": None,
        "retired_at": None,
        "payload": {
            "action": "reopen",
            "queuedEnd": {
                "d4": "private-external-d4",
                "target": {"wireD4": "private-wire-d4", "eventId": "business-id"},
            },
            "recordingRightProof": "private-proof",
        },
        "state_diff": {"accepted": True},
    }
    bundle = Mock(spec=PlayExportBundle, game={"id": UUID(int=1)}, events=(event,))
    value = next(_events_rows(bundle, "a" * 64)).values["business_payload_json"]
    assert isinstance(value, str)
    assert all(
        secret not in value
        for secret in ("private-external-d4", "private-wire-d4", "private-proof")
    )
    parsed = json.loads(value)
    assert parsed["redactionFormatVersion"] == "pitchlog-event-business-redacted-v1"
    assert parsed["eventKind"] == "game_reopen"
    assert parsed["payload"]["action"] == "reopen"
    assert parsed["payload"]["queuedEnd"]["target"]["eventId"] == "business-id"
    assert parsed["payload"]["queuedEnd"]["d4"] == {
        "redaction": "pitchlog-csv-redacted-v1"
    }
    assert parsed["payload"]["recordingRightProof"] == {
        "redaction": "pitchlog-csv-redacted-v1"
    }


def test_all_json_sidecars_reject_unknown_secret_like_key():
    """未知資格様memberを推測して削らずZIP自体を閉拒否する。"""
    with pytest.raises(PlayExportSupplyError):
        _canonical_json({"nested": {"customSessionTokenDigest": "private"}})
