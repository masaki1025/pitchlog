"""初球試験の独立固定期待をtracked fixtureから閉じて読む。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

_EXPECTED_KEYS = {
    "test_first_ball_write_stamp.py": frozenset(
        ["guard_first_ball_projection_lock", "guard_first_ball_projection_admission"]
    ),
    "test_sync_apply_first_ball_payload.py": frozenset(
        ["type_target_sha256", "type_fields_sha256"]
    ),
    "test_sync_apply_product_supply.py": frozenset(
        ["other_generated_statements_sha256", "terminal_generated_statements_sha256"]
    ),
    "test_sync_apply_writer_binding.py": frozenset(
        [
            "RG1:precheck",
            "RG1:commit_check",
            "RG1:scope_binding",
            "RULE:resolve_stage_a",
            "INITIAL_RIGHT:lock_device",
            "INITIAL_RIGHT:read_existing_start",
            "INITIAL_RIGHT:read_start_game",
            "INITIAL_RIGHT:lock_preparing_game",
            "INITIAL_RIGHT:lock_current_start",
            "INITIAL_RIGHT:check_business_epoch",
            "INITIAL_RIGHT:insert_initial_grant",
            "INITIAL_RIGHT:begin_start_attempt",
            "INITIAL_RIGHT:resolve_start_attempt",
            "INITIAL_RIGHT:read_initial_start_context",
            "INITIAL_RIGHT:persist_initial_start",
            "INITIAL_RIGHT:enroll_device",
            "INITIAL_RIGHT:lookup_existing_start_attempt",
            "SYNC_FIRST_BALL:bind_device",
            "SYNC_FIRST_BALL:check_current_right",
            "SYNC_FIRST_BALL:read_device_state",
            "SYNC_WRITER_BINDING:read_writer_identity",
            "SYNC_ORDINARY_PITCH:read_ordinary_order_summary",
            "SYNC_ORDINARY_PITCH:bind_ordinary_device",
            "SYNC_ORDINARY_PITCH:check_ordinary_right",
            "SYNC_ORDINARY_PITCH:prepare_ordinary_projection",
            "SYNC_ORDINARY_PITCH:read_ordinary_checkpoint",
            "SYNC_ORDINARY_PITCH:lock_ordinary_checkpoint",
            "SYNC_ORDINARY_PITCH:read_ordinary_history_page",
            "SYNC_PLAY_PREFIX:lock_play_prefix_checkpoint",
            "SYNC_PLAY_PREFIX:prepare_play_prefix_projection",
            "SYNC_PLAY_PREFIX:read_play_prefix_checkpoint",
            "SYNC_PLAY_PREFIX:read_play_prefix_history_page",
        ]
    ),
    "test_sync_right_sql.py": frozenset(
        [
            "old_render_sha256",
            "bind_device",
            "check_current_right",
            "device_state_read_sha256",
        ]
    ),
}
_FIXTURE = Path(__file__).parent / "fixtures/first_ball_expected_source_pins_v1.json"


class SourcePinError(ValueError):
    """独立期待fixtureの欠落・改変・未知値を表す。"""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """全階層の重複keyを黙って上書きしない。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourcePinError("固定期待のkeyが重複")
        result[key] = value
    return result


def read_expected_source_pins(
    source_file: str, *, path: Path = _FIXTURE
) -> dict[str, str]:
    """全file/key/型/桁を検査し、指定試験の固定期待だけを返す。

    Args:
        source_file: 閉集合に登録された試験ファイル名。
        path: 独立期待fixture。負例試験だけが別ファイルを渡す。

    Returns:
        製品sourceから計算せず読み取った固定SHA256の写し。

    Raises:
        SourcePinError: 未知要求、欠落、重複、型又はSHA256が不正な場合。
    """
    if type(source_file) is not str or source_file not in _EXPECTED_KEYS:
        raise SourcePinError("固定期待の試験ファイルが未登録")
    try:
        raw: object = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SourcePinError("固定期待fixtureを読めない") from error
    if type(raw) is not dict or set(raw) != {"schema_version", "pins"}:
        raise SourcePinError("固定期待fixtureのキーが不正")
    document = cast(dict[str, object], raw)
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise SourcePinError("固定期待fixtureの版が不正")
    pins = document["pins"]
    if type(pins) is not dict or set(pins) != set(_EXPECTED_KEYS):
        raise SourcePinError("固定期待の試験ファイル集合が不正")
    groups = cast(dict[str, object], pins)
    result: dict[str, str] = {}
    for name, expected_keys in _EXPECTED_KEYS.items():
        values = groups[name]
        if type(values) is not dict or set(values) != expected_keys:
            raise SourcePinError("固定期待の識別子集合が不正")
        group = cast(dict[str, object], values)
        for key in expected_keys:
            value = group[key]
            if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise SourcePinError("固定期待のSHA256が不正")
            if name == source_file:
                result[key] = value
    return result
