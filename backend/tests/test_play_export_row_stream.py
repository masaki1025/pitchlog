"""CSV完成行を全件listにせず、一行ずつarchiveへ渡す。"""

from itertools import islice
from unittest.mock import Mock
from uuid import UUID

from pitchlog.exports.play_export_csv import _events_rows
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
