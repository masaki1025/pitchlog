"""真正RR専用の既reader別identityを有限な製品宣言へ接合する。"""

import copy
from typing import Any

from pitchlog.authz.started_snapshot_read_sql import (
    candidate_started_read_function_bodies,
)
from pitchlog.domaingen.core import _canonical_hash

_SOURCE_PINS = {
    "read_ordinary_history_page": (
        "sha256:1ace03022f6ebe8767ad83d7eb217bb4baa238a0fd99374348b9bc2ca82a6f2a"
    ),
    "read_play_prefix_history_page": (
        "sha256:a1cf7570ee7a2f135676ebf7ebf04ec97da71cb41fdc9a5e97d5263780e5e92a"
    ),
    "read_nonplay_active_history": (
        "sha256:3db12fd4605fdd92387d114a9b169524a42a803a3c927544cc814aaa10438f3b"
    ),
}


def candidate_declarations(
    existing: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """既3関数の完全metadataを確認し、同owner/ACLの非ロック版だけを供給する。"""
    raw = candidate_started_read_function_bodies()
    rows = []
    bodies = {}
    for old, pin in _SOURCE_PINS.items():
        source = [row for row in existing if row["function_name"] == old]
        if len(source) != 1 or _canonical_hash(source[0]) != pin:
            raise ValueError("記録画面GETの元reader宣言が固定値と不一致")
        row = copy.deepcopy(source[0])
        new = "read_started_" + old.removeprefix("read_")
        row["function_name"] = new
        row["function_id"] = f"FUNCTION:sync_right_api:{new}({row['identity_args']})"
        identity = f"sync_right_api.{new}({row['identity_args']})"
        # 元実装/現在P3 source検証を保持し、配置主体/PUBLICの既定権限は残さない。
        body = raw.pop(new)
        body += (
            f"ALTER FUNCTION {identity} OWNER TO pitchlog_sync_right_fn_owner;\n"
            f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,pitchlog_app;\n"
            f"GRANT EXECUTE ON FUNCTION {identity} TO pitchlog_app;\n"
        )
        rows.append(row)
        bodies["function|" + row["function_id"]] = body
    if len(rows) != 3 or raw:
        raise ValueError("記録画面GETの有限reader集合が不一致")
    return rows, bodies
