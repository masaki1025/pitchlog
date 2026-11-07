"""現行started関数の閉metadataから閲覧2関数だけを派生する。"""

import copy
from typing import Any

from pitchlog.authz.viewer_effective_sql import candidate_viewer_effective_body
from pitchlog.authz.viewer_page_sql import candidate_viewer_page_body
from pitchlog.domaingen.core import _canonical_hash

_SOURCE = "read_started_play_prefix_history_page"
_SOURCE_PIN = "sha256:283eaddc887ad3382767bbb44773ccd6454309bb4103e4459297a8737f5c28a2"
_NEW = (
    ("read_viewer_play_prefix_history_page", None, candidate_viewer_page_body),
    (
        "read_viewer_effective_version",
        "uuid, uuid, bigint",
        candidate_viewer_effective_body,
    ),
)


def candidate_declarations(
    existing: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """旧owner/ACL/returnsを固定し、未知既宣言と衝突させない。"""
    sources = [row for row in existing if row.get("function_name") == _SOURCE]
    if len(sources) != 1 or _canonical_hash(sources[0]) != _SOURCE_PIN:
        raise ValueError("閲覧関数の現行元reader宣言が不一致")
    source = sources[0]
    rows: list[dict[str, Any]] = []
    bodies: dict[str, str] = {}
    for name, new_args, factory in _NEW:
        row = copy.deepcopy(source)
        args = source["identity_args"] if new_args is None else new_args
        row["function_name"] = name
        row["identity_args"] = args
        row["function_id"] = f"FUNCTION:sync_right_api:{name}({args})"
        if any(old["function_id"] == row["function_id"] for old in existing):
            raise ValueError("閲覧関数の既宣言と衝突")
        rows.append(row)
        bodies["function|" + row["function_id"]] = factory()
    if len(rows) != 2 or len(bodies) != 2:
        raise ValueError("閲覧関数の閉集合が不一致")
    return rows, bodies
