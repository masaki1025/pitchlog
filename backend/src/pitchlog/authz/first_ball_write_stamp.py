"""初球DB書込印の正式profileとguardの単一定義。

順序付き印は正式bind_device/check_current_rightだけが発行する。
profileの値だけを認可や実保存の成功証明として扱わない。
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, LiteralString

_SCHEMA = "sync_fence"
_TABLE = "first_ball_write_admissions"
_OWNER = "pitchlog_sync_right_fn_owner"
_REJECTION = "first ball write admission rejected"
# xmin(system列)を読む表。列SELECTでは読めないため表単位SELECTを与える。
_TABLE_SELECT = (_TABLE, "writer_admissions")

# bind/rightの実SQL照合結果からだけ遷移させるBの閉契約。bool受付APIではない。
STATE_TRANSITIONS = (
    ("absent", "device_true", "device_verified"),
    ("device_verified", "device_true", "device_verified"),
    ("device_verified", "right_true", "right_verified"),
    ("right_verified", "right_true", "right_verified"),
    ("right_verified", "consume", "consumed"),
)
TERMINAL_STATES = frozenset({"invalid", "consumed"})

_LOCK = """CREATE FUNCTION sync_right_api.guard_first_ball_projection_lock()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $stamp$
DECLARE current_generation bigint;
BEGIN
 IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'play_rows' OR TG_OP<>'INSERT'
 OR TG_WHEN<>'BEFORE' OR TG_LEVEL<>'ROW' OR TG_NARGS<>0
 OR session_user<>'pitchlog_app' OR current_user<>'pitchlog_app'
 OR NEW.tenant_id IS NULL OR NEW.game_id IS NULL OR NEW.source_event_id IS NULL
 OR NEW.tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid
 OR NEW.import_batch_id IS NOT NULL OR NEW.legacy_row_identifier IS NOT NULL
 OR NEW.migration_unverified IS DISTINCT FROM false THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 -- 既核と同じgame→current generationの順。資格GUCを設定しない。
 PERFORM 1 FROM public.games g
 WHERE g.tenant_id=NEW.tenant_id AND g.id=NEW.game_id FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 SELECT r.generation INTO STRICT current_generation
 FROM public.recording_generations r WHERE r.tenant_id=NEW.tenant_id
 AND r.game_id=NEW.game_id AND r.kind='normal' AND r.revoked_at IS NULL
 AND r.retired_at IS NULL;
 PERFORM 1 FROM public.recording_generations r
 WHERE r.tenant_id=NEW.tenant_id AND r.game_id=NEW.game_id
 AND r.generation=current_generation AND r.kind='normal'
 AND r.revoked_at IS NULL AND r.retired_at IS NULL FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation THEN
 RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
END;
$stamp$;
ALTER FUNCTION sync_right_api.guard_first_ball_projection_lock()
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.guard_first_ball_projection_lock()
 FROM PUBLIC, pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor;
"""

_ADMIT = """CREATE FUNCTION sync_right_api.guard_first_ball_projection_admission()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $stamp$
DECLARE own_xid text; row_xmin text;
 stamp sync_fence.first_ball_write_admissions%ROWTYPE;
 event_row record; binding sync_fence.writer_bindings%ROWTYPE;
 ordinary boolean:=false;
BEGIN
 -- 読取/照合だけをEXCEPTION付き内側blockへ閉じる。この内側はsubtransactionなので
 -- 印への書込とxmin照合は必ず外側(top-level)で行う。
 BEGIN
 IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'play_rows' OR TG_OP<>'INSERT'
 OR TG_WHEN<>'BEFORE' OR TG_LEVEL<>'ROW' OR TG_NARGS<>0
 OR session_user<>'pitchlog_app' OR current_user<>'pitchlog_sync_right_fn_owner'
 OR NEW.id IS NULL OR NEW.source_event_id IS NULL OR NEW.game_id IS NULL
 OR NEW.tenant_id IS NULL OR NEW.import_batch_id IS NOT NULL
 OR NEW.legacy_row_identifier IS NOT NULL
 OR NEW.migration_unverified IS DISTINCT FROM false
 OR NEW.tenant_id IS DISTINCT FROM
 NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 own_xid:=pg_catalog.pg_current_xact_id()::text;
 SELECT e.d5,e.generation,e.d1,e.payload INTO STRICT event_row
 FROM public.operation_events e
 WHERE e.tenant_id=NEW.tenant_id AND e.id=NEW.source_event_id AND e.game_id=NEW.game_id
 AND e.ledger_kind='accepted' AND e.event_kind='play_input' AND NOT e.is_tombstone
 AND e.generation IS NOT NULL AND e.d1>0 AND e.d2 IS NOT NULL
 AND e.replaced_at IS NULL AND e.retired_at IS NULL AND e.import_batch_id IS NULL
 AND e.legacy_row_identifier IS NULL AND NOT e.migration_unverified;
 ordinary:=event_row.payload->>'formatVersion'='ordinary-pitch-play-v1';
 IF ordinary IS DISTINCT FROM true THEN
 IF event_row.payload->>'formatVersion' IS DISTINCT FROM 'first-ball-play-v1'
 OR event_row.d1 IS DISTINCT FROM 1
 OR EXISTS(SELECT 1 FROM sync_fence.ordinary_pitch_write_admissions o
 WHERE o.tenant_id=NEW.tenant_id AND o.game_id=NEW.game_id AND o.d5=event_row.d5
 AND o.state IN ('device_verified','right_verified','evaluated','consumed')) THEN
 RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 SELECT s.* INTO STRICT stamp FROM sync_fence.first_ball_write_admissions s
 JOIN sync_fence.writer_bindings b
 ON (b.tenant_id,b.attempt_id,b.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 JOIN sync_fence.writer_admissions a
 ON (a.tenant_id,a.attempt_id,a.phase_id)=(s.tenant_id,s.attempt_id,s.phase_id)
 WHERE s.tenant_id=NEW.tenant_id AND s.game_id=NEW.game_id AND s.d5=event_row.d5
 AND s.internal_generation=event_row.generation AND s.state='right_verified'
 AND s.source_event_id IS NULL AND s.play_row_id IS NULL AND s.consumed_at IS NULL
 AND b.state='open' AND b.expires_at>pg_catalog.clock_timestamp()
 AND b.transaction_id=own_xid AND b.backend_pid=pg_catalog.pg_backend_pid()
 AND b.postmaster_started_at=pg_catalog.pg_postmaster_start_time()
 AND b.database_oid=(SELECT d.oid::text FROM pg_catalog.pg_database d
                     WHERE d.datname=pg_catalog.current_database())
 AND a.lease_id=b.lease_id AND a.transaction_id=own_xid
 AND a.xmin::text::numeric=pg_catalog.mod(own_xid::numeric,4294967296::numeric)
 -- 全binding不変列の照合。別phase/nonce/世代/instance/hashを合成しない。
 AND (pg_catalog.to_jsonb(s)-'state'-'source_event_id'-'play_row_id'-'consumed_at')
     =(pg_catalog.to_jsonb(b)-'state'-'close_id')
 FOR UPDATE OF s;
 -- 再lockしない。上のadmissionはxmin=own_xidで同top-level TXの既assert由来と
 -- 証明され、そのassertが同じbinding行のFOR SHAREをTX終了まで保持している。
 SELECT b.* INTO STRICT binding FROM sync_fence.writer_bindings b
 WHERE (b.tenant_id,b.attempt_id,b.phase_id)
 =(stamp.tenant_id,stamp.attempt_id,stamp.phase_id);
 -- admissionは実assertでinstance/system/xid/nonceを確認した入口証跡にすぎない。
 -- device/rightの実成功はBで順序付きstampを作り、ここでも現条件を照合する。
 IF NOT EXISTS(SELECT 1 FROM public.idempotency_ledger l
   WHERE l.tenant_id=NEW.tenant_id AND l.d5=event_row.d5 AND l.kind='accepted'
   AND l.source_fingerprint=stamp.event_fingerprint AND l.retired_at IS NULL
   AND l.import_batch_id IS NULL)
 OR NOT EXISTS(SELECT 1 FROM public.rg1_restore_gate g WHERE g.singleton_id=1
   AND g.state='open' AND g.recovery_generation=stamp.recovery_generation)
 OR NOT EXISTS(SELECT 1 FROM public.recording_generations r
   WHERE r.tenant_id=NEW.tenant_id AND r.game_id=NEW.game_id
   AND r.generation=stamp.internal_generation AND r.kind='normal'
   AND r.holder_device=stamp.device_id::text AND r.revoked_at IS NULL
   AND r.retired_at IS NULL AND r.import_batch_id IS NULL
   AND r.recovery_generation=stamp.recovery_generation)
 THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 -- 同じdevice identityをFOR SHAREで再確認。元credential/proofは保存しない。
 PERFORM 1 FROM public.trusted_devices d WHERE d.tenant_id=NEW.tenant_id
 AND d.device_id=stamp.device_id AND d.revoked_at IS NULL FOR SHARE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 END IF;
 EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END;
 IF ordinary THEN
 PERFORM sync_right_api.consume_ordinary_projection(pg_catalog.to_jsonb(NEW));
 RETURN NEW;
 END IF;
 -- 外側: subtransactionなしで消費する。0行は固定42501、PKなので複数行はない。
 UPDATE sync_fence.first_ball_write_admissions s
 SET state='consumed',source_event_id=NEW.source_event_id,play_row_id=NEW.id,
     consumed_at=pg_catalog.clock_timestamp()
 WHERE (s.tenant_id,s.attempt_id,s.phase_id)
 =(stamp.tenant_id,stamp.attempt_id,stamp.phase_id)
 AND s.state='right_verified' AND s.lease_id=binding.lease_id
 AND s.transaction_id=own_xid AND s.nonce_digest=binding.nonce_digest
 AND s.event_fingerprint=stamp.event_fingerprint
 AND s.source_event_id IS NULL AND s.play_row_id IS NULL AND s.consumed_at IS NULL
 RETURNING s.xmin::text INTO row_xmin;
 -- 毎回の書込xminでnested consumeを拒否。失敗は同statementのINSERTごとrollback。
 IF NOT FOUND OR row_xmin IS NULL
 OR row_xmin::numeric<>pg_catalog.mod(own_xid::numeric,4294967296::numeric) THEN
  RAISE EXCEPTION 'first ball write admission rejected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END;
$stamp$;
ALTER FUNCTION sync_right_api.guard_first_ball_projection_admission()
 OWNER TO pitchlog_sync_right_fn_owner;
REVOKE ALL ON FUNCTION sync_right_api.guard_first_ball_projection_admission()
 FROM PUBLIC, pitchlog_app, pitchlog_sync_binding_actor, pitchlog_rg1_control_actor;
"""

_FUNCTIONS = {
    "guard_first_ball_projection_lock": ("invoker", _LOCK),
    "guard_first_ball_projection_admission": ("definer", _ADMIT),
}
# 昇順の2trigger以外を追加/省略/改名したprofileは受け付けない。
_TRIGGERS = (
    ("trg_first_ball_10_lock", "guard_first_ball_projection_lock"),
    ("trg_first_ball_20_admit", "guard_first_ball_projection_admission"),
)


def _profile() -> dict[str, Any]:
    """正式な有限body/owner/ACL/状態契約を描画する。"""
    from pitchlog.sync.control_provider.writer_binding_models import (
        FirstBallWriteAdmission,
    )

    table = FirstBallWriteAdmission.__table__
    columns = tuple(column.name for column in table.c)
    protected = tuple(
        name
        for name in columns
        if name
        not in {
            "state",
            "source_event_id",
            "play_row_id",
            "consumed_at",
        }
    )
    functions = []
    for name, (security, sql) in _FUNCTIONS.items():
        functions.append(
            {
                "function_id": f"FUNCTION:sync_right_api:{name}()",
                "schema_name": "sync_right_api",
                "function_name": name,
                "identity_args": "",
                "owner_role_id": _OWNER,
                "security_mode": security,
                "language": "plpgsql",
                "returns": "trigger",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": [],
                "sql": sql,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            }
        )
    triggers = [
        {
            "trigger_id": f"TRIGGER:play_rows:{name}",
            "trigger_name": name,
            "schema_name": "public",
            "table_id": "play_rows",
            "timing": "BEFORE",
            "events": ["INSERT"],
            "level": "ROW",
            "when": None,
            "arguments": [],
            "enabled": "O",
            "function_id": f"FUNCTION:sync_right_api:{function}()",
            "sql": f"CREATE TRIGGER {name} BEFORE INSERT ON public.play_rows "
            f"FOR EACH ROW EXECUTE FUNCTION sync_right_api.{function}();",
        }
        for name, function in _TRIGGERS
    ]
    # 既表は必要列SELECTのみ。業務表DML/role/CREATE権限を追加しない。
    selects = {
        _TABLE: list(columns),
        "writer_bindings": [*protected, "state", "close_id"],
        "writer_admissions": [
            "tenant_id",
            "attempt_id",
            "phase_id",
            "lease_id",
            "transaction_id",
        ],
        "operation_events": [
            "payload",
            "tenant_id",
            "id",
            "game_id",
            "generation",
            "d1",
            "d2",
            "d5",
            "ledger_kind",
            "event_kind",
            "is_tombstone",
            "replaced_at",
            "retired_at",
            "import_batch_id",
            "legacy_row_identifier",
            "migration_unverified",
        ],
        "idempotency_ledger": [
            "tenant_id",
            "d5",
            "kind",
            "source_fingerprint",
            "retired_at",
            "import_batch_id",
        ],
    }
    policies = []
    for table_name in selects:
        schema = (
            _SCHEMA
            if table_name in {_TABLE, "writer_bindings", "writer_admissions"}
            else "public"
        )
        command = "ALL" if table_name == _TABLE else "SELECT"
        predicate = (
            "tenant_id = NULLIF(pg_catalog.current_setting("
            "'app.tenant_id',true),'')::uuid"
        )
        sql = (
            f"CREATE POLICY first_ball_stamp_{table_name} "
            f"ON {schema}.{table_name} FOR {command} TO {_OWNER} "
            f"USING ({predicate})"
        )
        if command == "ALL":
            sql += f" WITH CHECK ({predicate})"
        policies.append(
            {
                "table_id": table_name,
                "schema_name": schema,
                "command": command,
                "role": _OWNER,
                "sql": sql + ";",
            }
        )
    acl = [
        {
            "table_id": name,
            "schema_name": (
                _SCHEMA
                if name in {_TABLE, "writer_bindings", "writer_admissions"}
                else "public"
            ),
            "grantee": _OWNER,
            "privilege": "SELECT",
            "columns": names,
            "grantable": False,
        }
        for name, names in selects.items()
        if name not in _TABLE_SELECT
    ]
    # xminはsystem列で、列ACLは正式catalog照会(attnum>0)に現れない。xminを読む
    # 2表だけ表単位SELECTにし、既存の表ACL突合で観測可能にする。
    table_acls = [
        {
            "table_id": name,
            "schema_name": _SCHEMA,
            "grantee": _OWNER,
            "privilege": "SELECT",
            "grantable": False,
        }
        for name in _TABLE_SELECT
    ]
    acl += [
        {
            "table_id": "recording_generations",
            "schema_name": "public",
            "grantee": _OWNER,
            "privilege": "SELECT",
            "columns": ["import_batch_id"],
            "grantable": False,
        },
        {
            "table_id": _TABLE,
            "schema_name": _SCHEMA,
            "grantee": _OWNER,
            "privilege": "INSERT",
            "columns": [*protected, "state"],
            "grantable": False,
        },
        {
            "table_id": _TABLE,
            "schema_name": _SCHEMA,
            "grantee": _OWNER,
            "privilege": "UPDATE",
            "columns": ["state", "source_event_id", "play_row_id", "consumed_at"],
            "grantable": False,
        },
    ]
    return {
        "status": "FORMAL_PROFILE_STAMPED_BIND_RIGHT",
        "roles": [],
        "schemas": [
            {
                "schema_name": _SCHEMA,
                "grantee": _OWNER,
                "privilege": "USAGE",
                "grantable": False,
            }
        ],
        "table": {
            "schema_name": _SCHEMA,
            "table_id": _TABLE,
            "owner": "pitchlog_owner",
            "enable_rls": True,
            "force_rls": True,
            "physical_delete_allowed": False,
            "truncate_allowed": False,
        },
        "functions": functions,
        "triggers": triggers,
        "table_acls": table_acls,
        "column_acls": acl,
        "policies": policies,
        "state_transitions": [list(row) for row in STATE_TRANSITIONS],
        "terminal_states": sorted(TERMINAL_STATES),
        "stamp_issuance": "STAMPED_BIND_RIGHT",
        "runtime_registered": True,
    }


def formal_profile() -> dict[str, Any]:
    """正式profileの防御的コピーを返す。実installerを呼ばない。"""
    return copy.deepcopy(_profile())


def _strict_json(value: object) -> str:
    """bool/intやtuple/listを同一視しない閉JSON比較にする。"""

    def check(item: object) -> None:
        if item is None or type(item) in (str, int, bool):
            return
        if type(item) is list:
            for member in item:
                check(member)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for member in item.values():
                check(member)
            return
        raise ValueError("初球書込印の閉profileが不一致")

    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def require_formal(candidate: object) -> None:
    """候補定義全値の一致だけを検査し、認可/DB成功には昇格させない。"""
    try:
        if _strict_json(candidate) != _strict_json(_profile()):
            raise ValueError("初球書込印の閉profileが不一致")
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise ValueError("初球書込印の閉profileが不一致") from None


def formal_declarations() -> dict[str, list[dict[str, Any]]]:
    """正式asset形へ有限のprofileを写し、独立な権限定義を持たない。"""
    profile = formal_profile()
    require_formal(profile)
    result: dict[str, list[dict[str, Any]]] = {
        "functions": [],
        "policies": [],
        "acl_expectations": [],
        "column_acl_expectations": [],
    }
    for item in profile["functions"]:
        result["functions"].append(
            {
                key: value
                for key, value in item.items()
                if key not in {"sql", "sql_sha256"}
            }
            | {
                "function_kind": item["security_mode"],
                "volatility": "volatile",
                "revoked_acl_expectations": [
                    {"grantee": grantee, "privilege": "EXECUTE", "grantable": False}
                    for grantee in ("PUBLIC", "pitchlog_app")
                ],
            }
        )
    for item in profile["table_acls"]:
        result["acl_expectations"].append(
            {
                "acl_id": (
                    f"ACL:{item['schema_name']}:{item['table_id']}:{item['grantee']}"
                ),
                "object_kind": "table",
                "object_schema": item["schema_name"],
                "object_id": item["table_id"],
                "profile": "function_only",
                "grantee_role_id": item["grantee"],
                "privilege_ids": [item["privilege"]],
                "grant_option": item["grantable"],
            }
        )
    columns: dict[str, dict[str, Any]] = {}
    for item in profile["column_acls"]:
        for column in item["columns"]:
            key = (
                f"COLUMN-ACL:{item['schema_name']}:{item['table_id']}:"
                f"{column}:{item['grantee']}"
            )
            value = columns.setdefault(
                key,
                {
                    "expectation_id": key,
                    "object_kind": "column",
                    "object_schema": item["schema_name"],
                    "object_id": item["table_id"],
                    "column_id": column,
                    "grantee_role_id": item["grantee"],
                    "privilege_ids": [],
                    "grant_option": item["grantable"],
                },
            )
            value["privilege_ids"].append(item["privilege"])
    result["column_acl_expectations"] = list(columns.values())
    for item in profile["policies"]:
        name = "first_ball_stamp_" + item["table_id"]
        prefix = (
            f"CREATE POLICY {name} ON {item['schema_name']}.{item['table_id']} "
            f"FOR {item['command']} TO {item['role']} USING ("
        )
        text = item["sql"]
        if not text.startswith(prefix) or not text.endswith(");"):
            raise ValueError("正式印policyの閉形式が不一致")
        using = text[len(prefix) : -2]
        check = None
        if item["command"] == "ALL":
            using, check = using.split(") WITH CHECK (", 1)
        result["policies"].append(
            {
                "policy_id": f"POLICY:{item['table_id']}:{name}",
                "table_id": item["table_id"],
                "profile": "function_only",
                "policy_name": name,
                "command": item["command"],
                "policy_mode": "permissive",
                "role_ids": [item["role"]],
                "using_predicate_id": None,
                "using_column": None,
                "using_expression": using,
                "with_check_predicate_id": None,
                "with_check_column": None,
                "with_check_expression": check,
            }
        )
    return result


STAMP_TRIGGER_QUERY: LiteralString = """
SELECT pg_catalog.jsonb_build_array(t.tgname, t.tgtype::integer, t.tgenabled::text,
       n.nspname, p.proname, o.rolname, p.prosecdef,
       ARRAY(SELECT a.attname::text FROM pg_catalog.unnest(t.tgattr::smallint[])
             WITH ORDINALITY v(attnum,ord)
             JOIN pg_catalog.pg_attribute a
             ON a.attrelid=t.tgrelid AND a.attnum=v.attnum
             ORDER BY v.ord),
       t.tgdeferrable, t.tginitdeferred, t.tgconstraint=0,
       t.tgqual IS NULL, t.tgnargs::integer,
       pg_catalog.encode(t.tgargs,'hex'), t.tgoldtable, t.tgnewtable) AS value
FROM pg_catalog.pg_trigger t
JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
JOIN pg_catalog.pg_roles o ON o.oid=p.proowner
WHERE t.tgrelid='public.play_rows'::pg_catalog.regclass AND NOT t.tgisinternal
ORDER BY t.tgname
"""


def stamp_trigger_expectations() -> tuple[tuple[object, ...], ...]:
    """新2triggerと既identity triggerの全集合を閉じる。"""
    return (
        (
            "trg_first_ball_10_lock",
            7,
            "O",
            "sync_right_api",
            "guard_first_ball_projection_lock",
            _OWNER,
            False,
            [],
            False,
            False,
            True,
            True,
            0,
            "",
            None,
            None,
        ),
        (
            "trg_first_ball_20_admit",
            7,
            "O",
            "sync_right_api",
            "guard_first_ball_projection_admission",
            _OWNER,
            True,
            [],
            False,
            False,
            True,
            True,
            0,
            "",
            None,
            None,
        ),
        (
            "trg_play_rows_projection_identity_immutable",
            19,
            "O",
            "public",
            "prevent_play_rows_projection_identity_update",
            "pitchlog_owner",
            False,
            ["id", "source_event_id", "legacy_row_identifier"],
            False,
            False,
            True,
            True,
            0,
            "",
            None,
            None,
        ),
    )


def formal_function_bodies() -> dict[str, str]:
    """初回だけ2triggerを配置するcanonical SQLを同じguardから描画する。"""
    profile = formal_profile()
    require_formal(profile)
    result = {row["function_id"]: row["sql"] for row in profile["functions"]}
    key = profile["functions"][0]["function_id"]
    result[key] += "\n" + "\n".join(row["sql"] for row in profile["triggers"]) + "\n"
    return result


def stamp_trigger_reapply_check() -> str:
    """再適用で既triggerを修復せず、完全一致した場合だけ通す。"""
    literal = json.dumps(stamp_trigger_expectations(), separators=(",", ":"))
    expected = "'" + literal.replace("'", "''") + "'::pg_catalog.jsonb"
    query = STAMP_TRIGGER_QUERY.strip()
    return f"""
    IF (SELECT COALESCE(
          pg_catalog.jsonb_agg(r.value ORDER BY r.value->>0), '[]'::pg_catalog.jsonb)
        FROM ({query}) r) IS DISTINCT FROM {expected} THEN
        RAISE EXCEPTION 'first ball projection trigger definition collision';
    END IF;"""


def is_formal_stamp_lock_declaration(row: object) -> bool:
    """新invokerの署名・owner・trigger戻り・全ACLを単一正式宣言と照合する。"""
    try:
        expected = next(
            item
            for item in formal_declarations()["functions"]
            if item["function_name"] == "guard_first_ball_projection_lock"
        )
        return _strict_json(row) == _strict_json(expected)
    except (ValueError, TypeError, KeyError, StopIteration, RecursionError):
        return False
