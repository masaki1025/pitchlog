"""唯一P3/成績/CSV factoryの22関数を閉じた認可候補へまとめる。"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pitchlog.authz import (
    p3_binding_sql,
    p3_nonplay_bridge_sql,
    p3_projection_paged_read_sql,
    p3_projection_paged_sql,
    p3_projection_sql,
    p3_projection_trigger_patch,
    p3_right_sql,
    p3_storage_guard,
    play_export_source_read_product,
    play_export_writer_product,
    stats_primitive_sql,
)
from pitchlog.authz.function_result_type import pg_result_type
from pitchlog.domaingen.core import _canonical_hash
from pitchlog.domaingen.pregen_checks import validate_undo_selection_profile

_ROOT = Path(__file__).resolve().parents[4]
_PROFILE = "backend/domain/p3-native-selection.json"
_APP = "pitchlog_app"
_RIGHT_OWNER = "pitchlog_sync_right_fn_owner"
_NEW_OWNERS = {
    ("sync_right_api", "bind_p3_device"): _RIGHT_OWNER,
    ("sync_right_api", "check_p3_right"): _RIGHT_OWNER,
    ("sync_fence_api", "read_p3_writer_binding"): "pitchlog_sync_binding_fn_owner",
    ("sync_right_api", "persist_p3_projection"): _RIGHT_OWNER,
    ("sync_right_api", "read_p3_current"): _RIGHT_OWNER,
    ("sync_right_api", "begin_p3_projection_page"): _RIGHT_OWNER,
    ("sync_right_api", "append_p3_projection_page"): _RIGHT_OWNER,
    ("sync_right_api", "finalize_p3_projection_page"): _RIGHT_OWNER,
    ("sync_right_api", "read_p3_current_header"): _RIGHT_OWNER,
    ("sync_right_api", "read_p3_current_page"): _RIGHT_OWNER,
    ("sync_fence", "p3_reject_unfinished_page_progress"): "pitchlog_owner",
}

# 既11関数の全描画byte。別基線への無条件置換はしない。
_OLD_PINS = {
    ("FUNCTION:stats_api:open_primitive_snapshot(uuid, uuid, text)"): (
        "58e7683e89bd78ce4b1b42855b3839ecb617e6adc0dbb0ffa2d5b7525fc7d527"
    ),
    (
        "FUNCTION:stats_api:read_play_export_primitives(uuid, uuid, uuid"
        ", bigint, text, text, text, bigint, uuid, text, integer)"
    ): ("fe50fbb27a703b2ba47e7e3ddfdecf1c182536281ab1f3395ffcedbe123117fd"),
    (
        "FUNCTION:stats_api:read_play_export_source_page(uuid, bigint, bigint, integer)"
    ): ("0ca4ea487715f8c0818c5d75d93ad73d41f3a6bc1d607d371c1966b48a7f62b0"),
    (
        "FUNCTION:stats_api:read_primitive_totals(uuid, uuid, uuid, bigi"
        "nt, text, text, text)"
    ): ("35c44171aba92c6eb0b6bf3a5543aa93dc474fdf0cb992e37b9be1547785a6ea"),
    (
        "FUNCTION:stats_api:read_writer_play_export_aggregate(uuid, uuid"
        ", uuid, uuid, text, bigint, bytea)"
    ): ("ebe90a27edf228740a5360af9dc597bd20cb45aba90c38d755bbc76ceee533ba"),
    (
        "FUNCTION:stats_api:save_primitive_source(uuid, uuid, uuid, text"
        ", bigint, text, jsonb, bytea)"
    ): ("c54307a3ad249c4f084b44894ec1b664435bb5da25c7ca43336136ca810f9837"),
    (
        "FUNCTION:sync_right_api:consume_game_lifecycle(uuid, uuid, uuid"
        ", bytea, uuid, uuid, text)"
    ): ("cea10e55bf670ab6448aad5e48629e4142018853d4e483b75122f7eb2ed2f300"),
    ("FUNCTION:sync_right_api:guard_first_ball_projection_admission()"): (
        "e830c886f5501a3341e3cedad76709a1650ab22a05d3def2c4f6a7b97c77c775"
    ),
    ("FUNCTION:sync_right_api:guard_first_ball_projection_lock()"): (
        "1de7d18a7e588db75948416ad80fa531f86f925e0c130d84795c684e07ab6e90"
    ),
    (
        "FUNCTION:sync_right_api:read_nonplay_active_history(uuid, uuid,"
        " bigint, uuid, bigint, bigint, bigint, bigint, bigint, bigint, "
        "uuid, integer)"
    ): ("827d7b9adf2aa609450f43a1a23bf28f1dd77e611e8bab6dddb16ad79afb4685"),
    (
        "FUNCTION:sync_right_api:read_nonplay_history_page(uuid, uuid, u"
        "uid, bytea, uuid, uuid, text)"
    ): ("39b8073a9e66dc4e04f60eebf2bad41c1406818731ab20d763aa73e232196054"),
}
_OLD_ROW_PINS = {
    ("FUNCTION:stats_api:open_primitive_snapshot(uuid, uuid, text)"): (
        "sha256:bed2350e3ab6a176cb582557b2f886487a676caf8d4d1293b4f72b84caade796"
    ),
    (
        "FUNCTION:stats_api:read_play_export_primitives(uuid, uuid, uuid"
        ", bigint, text, text, text, bigint, uuid, text, integer)"
    ): ("sha256:fe6655fb2ce2f1a118d24d2f34dd40eac9bfeba4aff2d8b6cd090a2a206131c9"),
    (
        "FUNCTION:stats_api:read_play_export_source_page(uuid, bigint, bigint, integer)"
    ): ("sha256:c90f9b2c6e7661cb1639ed743f45ecad009c352e77f5fe532e3657a37734afac"),
    (
        "FUNCTION:stats_api:read_primitive_totals(uuid, uuid, uuid, bigi"
        "nt, text, text, text)"
    ): ("sha256:f9806376170efe17cf03b2e85bd09155c5abc8c99c06d611ddf5e986fa9a2e59"),
    (
        "FUNCTION:stats_api:read_writer_play_export_aggregate(uuid, uuid"
        ", uuid, uuid, text, bigint, bytea)"
    ): ("sha256:2e941ffe8fafa8d39a7fa8bd40653b9dd8088fd0ad2618812cf76c85f4ef64b1"),
    (
        "FUNCTION:stats_api:save_primitive_source(uuid, uuid, uuid, text"
        ", bigint, text, jsonb, bytea)"
    ): ("sha256:aef0216043205269c550bb72a5c3c05d526601127aaba3229de3bb6894add98d"),
    (
        "FUNCTION:sync_right_api:consume_game_lifecycle(uuid, uuid, uuid"
        ", bytea, uuid, uuid, text)"
    ): ("sha256:7d316b9de4b3803dc5664097a670f443a982d6e7e393c33e86ff9b40dbf27b24"),
    ("FUNCTION:sync_right_api:guard_first_ball_projection_admission()"): (
        "sha256:9b172b64fe88b45e8378105f86c6c51ae5a389df562efa53127bcc94549c78dc"
    ),
    ("FUNCTION:sync_right_api:guard_first_ball_projection_lock()"): (
        "sha256:985b8e02d6daf5b6b85844e1dc83d72a782d0fa6fd3cad4c8ee65ce55565622b"
    ),
    (
        "FUNCTION:sync_right_api:read_nonplay_active_history(uuid, uuid,"
        " bigint, uuid, bigint, bigint, bigint, bigint, bigint, bigint, "
        "uuid, integer)"
    ): ("sha256:3db12fd4605fdd92387d114a9b169524a42a803a3c927544cc814aaa10438f3b"),
    (
        "FUNCTION:sync_right_api:read_nonplay_history_page(uuid, uuid, u"
        "uid, bytea, uuid, uuid, text)"
    ): ("sha256:f2f16c636782b8e65b57359b90dcd28a544afc1d311663d53325a44dddc77408"),
}
_SIGNATURES = {
    ("stats_api", "open_primitive_snapshot"): ("uuid, uuid, text"),
    ("stats_api", "read_play_export_primitives"): (
        "uuid, uuid, uuid, bigint, text, text, text, bigint, uuid, text, integer"
    ),
    ("stats_api", "read_play_export_source_page"): ("uuid, bigint, bigint, integer"),
    ("stats_api", "read_primitive_totals"): (
        "uuid, uuid, uuid, bigint, text, text, text"
    ),
    ("stats_api", "read_writer_play_export_aggregate"): (
        "uuid, uuid, uuid, uuid, text, bigint, bytea"
    ),
    ("stats_api", "save_primitive_source"): (
        "uuid, uuid, uuid, text, bigint, text, jsonb, bytea"
    ),
    ("sync_fence", "p3_reject_unfinished_page_progress"): (""),
    ("sync_fence_api", "read_p3_writer_binding"): (
        "uuid, uuid, uuid, bytea, uuid, uuid"
    ),
    ("sync_right_api", "append_p3_projection_page"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, uuid, text"
    ),
    ("sync_right_api", "begin_p3_projection_page"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, text, text"
    ),
    ("sync_right_api", "bind_p3_device"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, bytea"
    ),
    ("sync_right_api", "check_p3_right"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, bytea"
    ),
    ("sync_right_api", "consume_game_lifecycle"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, text"
    ),
    ("sync_right_api", "finalize_p3_projection_page"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, uuid"
    ),
    ("sync_right_api", "guard_first_ball_projection_admission"): (""),
    ("sync_right_api", "guard_first_ball_projection_lock"): (""),
    ("sync_right_api", "persist_p3_projection"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, text, text"
    ),
    ("sync_right_api", "read_nonplay_active_history"): (
        "uuid, uuid, bigint, uuid, bigint, bigint, bigint, bigint, bigin"
        "t, bigint, uuid, integer"
    ),
    ("sync_right_api", "read_nonplay_history_page"): (
        "uuid, uuid, uuid, bytea, uuid, uuid, text"
    ),
    ("sync_right_api", "read_p3_current"): ("uuid, uuid, bigint"),
    ("sync_right_api", "read_p3_current_header"): ("uuid, uuid, bigint"),
    ("sync_right_api", "read_p3_current_page"): (
        "uuid, uuid, bigint, uuid, uuid, text, text, text, bigint, integer"
    ),
}


def selection_profile() -> dict[str, object]:
    """既v2 profileを唯一validatorで閉検証し、旧v1へ戻さない。"""
    profile = json.loads((_ROOT / _PROFILE).read_bytes())
    validate_undo_selection_profile(profile)
    if profile["version"] != 2:
        raise ValueError("P3の正規S profile版が不一致")
    return profile


def _factory_bundles() -> list[str]:
    profile = selection_profile()
    _, sections, _, _ = stats_primitive_sql._verified_candidate_inputs(
        _ROOT, p3_selector_profile=profile
    )
    health = sections["canonical_health"]
    return [
        *p3_right_sql.candidate_sql().values(),
        p3_binding_sql.candidate_sql(),
        p3_projection_trigger_patch.candidate_sql(),
        p3_projection_sql.candidate_sql(health_sql=health),
        p3_projection_sql.candidate_current_read_sql(health_sql=health),
        p3_projection_paged_sql.candidate_paged_begin_sql(),
        p3_projection_paged_sql.candidate_paged_append_sql(),
        p3_projection_paged_sql.candidate_paged_finalize_sql(health_sql=health),
        *p3_projection_paged_read_sql.candidate_paged_current_read_sql(
            health_sql=health
        ).values(),
        *stats_primitive_sql.candidate_function_bodies(
            p3_selector_profile=profile
        ).values(),
        *p3_nonplay_bridge_sql.candidate_function_bodies_p3_nonplay_bridge().values(),
        p3_nonplay_bridge_sql.candidate_lifecycle_p3_body(
            health, sections["canonical_source_members"]
        ),
        play_export_writer_product.candidate_function_body(p3_selector_profile=profile),
        play_export_source_read_product.candidate_read_bundle(
            p3_selector_profile=profile
        )[1],
        "\n".join(p3_storage_guard.candidate_statements()[:3]),
    ]


def _parts(source: str) -> list[dict[str, Any]]:
    """既factoryの有限CREATE単位を切り、body内の自由なSQLを補修しない。"""
    starts = list(
        re.finditer(
            r"^CREATE(?: OR REPLACE)?\s+FUNCTION\s+"
            r"([a-z_][a-z_0-9]*)\.([a-z_][a-z_0-9]*)\(",
            source,
            re.M,
        )
    )
    if not starts or source[: starts[0].start()].strip():
        raise ValueError("P3関数sourceの先頭が不正")
    result = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        piece = source[start.start() : end]
        header = re.match(
            r"CREATE(?: OR REPLACE)?\s+FUNCTION\s+"
            r"([a-z_][a-z_0-9]*)\.([a-z_][a-z_0-9]*)\((.*?)\)"
            r"\s+RETURNS\s+(TABLE\s*\([^)]*\)|trigger|uuid|text)\s+"
            r"LANGUAGE plpgsql\s+(?:(VOLATILE|STABLE)\s+)?"
            r"SECURITY (DEFINER|INVOKER)\s+"
            r"SET search_path=pg_catalog,\s*pg_temp AS (\$[a-z_0-9]+\$)",
            piece,
            re.S,
        )
        if header is None:
            raise ValueError("P3関数の閉headerが不一致")
        schema, name, arguments, returns, volatility, mode, tag = header.groups()
        parameters = []
        for argument in arguments.split(",") if arguments.strip() else []:
            match = re.fullmatch(
                r"\s*[a-z_0-9]+\s+(uuid|bytea|text|bigint|integer|jsonb)\s*", argument
            )
            if match is None:
                raise ValueError("P3関数の引数型が未登録")
            parameters.append(match[1])
        identity_args = ", ".join(parameters)
        if _SIGNATURES.get((schema, name)) != identity_args:
            raise ValueError("P3関数の固定署名が不一致")
        closing = piece.find(tag, header.end())
        if closing < 0 or piece[closing + len(tag) : closing + len(tag) + 1] != ";":
            raise ValueError("P3関数bodyの終端が不正")
        body_end = closing + len(tag) + 1
        result.append(
            {
                "schema": schema,
                "name": name,
                "identity_args": identity_args,
                "returns": returns,
                "volatility": (volatility or "VOLATILE").lower(),
                "security": mode.lower(),
                "create": piece[:body_end],
                "suffix": piece[body_end:],
                "body": piece[header.end() : closing].strip(),
            }
        )
    return result


def candidate_declarations(
    existing_rows: list[dict[str, Any]],
    existing_bodies: dict[str, str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """既source完全値を確認して22関数を描画する。適用・受理はしない。"""
    rows = {row["function_id"]: row for row in existing_rows}
    if len(rows) != len(existing_rows):
        raise ValueError("P3接合前の関数宣言が重複")
    declarations: dict[str, list[dict[str, Any]]] = {"functions": []}
    bodies = {}
    for bundle in _factory_bundles():
        for part in _parts(bundle):
            schema, name = part["schema"], part["name"]
            pg_result_type(part["returns"])
            identifier = f"FUNCTION:{schema}:{name}({part['identity_args']})"
            key = "function|" + identifier
            if key in bodies:
                raise ValueError("P3接合関数が重複")
            if identifier in _OLD_PINS:
                old_body = existing_bodies.get(key)
                if (
                    old_body is None
                    or identifier not in rows
                    or hashlib.sha256(old_body.encode()).hexdigest()
                    != _OLD_PINS[identifier]
                    or _canonical_hash(rows[identifier]) != _OLD_ROW_PINS[identifier]
                ):
                    raise ValueError("P3接合前の関数全byteが不一致")

                old = _parts(old_body.split("\n\n", 1)[1])
                if len(old) != 1:
                    raise ValueError("P3接合前の関数sourceが部分/余剰")
                row = copy.deepcopy(rows[identifier])
                if (
                    row["schema_name"] != schema
                    or row["function_name"] != name
                    or row["security_mode"] != part["security"]
                    or row["volatility"] != part["volatility"]
                    or pg_result_type(row["returns"]) != pg_result_type(part["returns"])
                ):
                    raise ValueError("P3既関数の属性を無断変更しない")
                sql = part["create"] + old[0]["suffix"]
            else:
                owner = _NEW_OWNERS.get((schema, name))
                if owner is None or identifier in rows or key in existing_bodies:
                    raise ValueError("P3新增関数が未登録/既存衝突")
                if part["security"] != "definer":
                    raise ValueError("P3新增関数のsecurity modeが不一致")
                owners = re.findall(r"OWNER\s+TO\s+([a-z_]+)\s*;", part["suffix"])
                grants = re.findall(
                    r"GRANT EXECUTE\s+ON FUNCTION.*?\s+TO\s+([a-z_]+)\s*;",
                    part["suffix"],
                    re.S,
                )
                guard = name == "p3_reject_unfinished_page_progress"
                binding_read = (schema, name) == (
                    "sync_fence_api",
                    "read_p3_writer_binding",
                )
                grantee = _RIGHT_OWNER if binding_read else _APP
                if owners != [owner] or grants != ([] if guard else [grantee]):
                    raise ValueError("P3新增関数のowner/EXECUTEが不一致")
                revoked = (
                    (["PUBLIC", _APP] if binding_read else ["PUBLIC"])
                    if not guard
                    else [
                        "PUBLIC",
                        _APP,
                        _RIGHT_OWNER,
                        "pitchlog_sync_binding_actor",
                        "pitchlog_rg1_control_actor",
                    ]
                )
                row = {
                    "function_id": identifier,
                    "schema_name": schema,
                    "function_name": name,
                    "identity_args": part["identity_args"],
                    "function_kind": "definer",
                    "owner_role_id": owner,
                    "language": "plpgsql",
                    "returns": part["returns"],
                    "security_mode": "definer",
                    "volatility": part["volatility"],
                    "search_path": ["pg_catalog", "pg_temp"],
                    "acl_expectations": []
                    if guard
                    else [
                        {"grantee": grantee, "privilege": "EXECUTE", "grantable": False}
                    ],
                    "revoked_acl_expectations": [
                        {"grantee": role, "privilege": "EXECUTE", "grantable": False}
                        for role in revoked
                    ],
                }
                sql = part["create"] + part["suffix"]
            declarations["functions"].append(row)
            bodies[key] = sql
    if len(bodies) != 22 or len(declarations["functions"]) != 22:
        raise ValueError("P3接合関数が22件の閉集合でない")
    return declarations, bodies
