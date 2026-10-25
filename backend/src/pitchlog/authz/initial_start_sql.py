"""開始の固定2関数と必要最小ACL/RLSの唯一の宣言元。"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import cast

_OWNER = "pitchlog_initial_fn_owner"
_ACTOR = "pitchlog_initial_actor"
_ARGS = "uuid, uuid, uuid, uuid, bytea, text"
_NAMES = ("read_initial_start_context", "persist_initial_start")


def start_function_declarations() -> dict[str, dict[str, object]]:
    """開始exact2関数の全属性を返す。旧9関数は含めない。"""
    result: dict[str, dict[str, object]] = {}
    for name, returns in zip(
        _NAMES,
        (
            "TABLE(context_json text)",
            "TABLE(started_at timestamp with time zone, "
            "away_lineup_id uuid, home_lineup_id uuid)",
        ),
        strict=True,
    ):
        key = f"FUNCTION:initial_right_api:{name}({_ARGS})"
        result[key] = dict(
            function_id=key,
            schema_name="initial_right_api",
            function_name=name,
            identity_args=_ARGS,
            function_kind="definer",
            owner_role_id=_OWNER,
            language="plpgsql",
            returns=returns,
            security_mode="definer",
            volatility="volatile",
            search_path=["pg_catalog", "pg_temp"],
            acl_expectations=[
                dict(grantee=_ACTOR, privilege="EXECUTE", grantable=False)
            ],
            revoked_acl_expectations=[
                dict(grantee=r, privilege="EXECUTE", grantable=False)
                for r in ("PUBLIC", "pitchlog_app")
            ],
        )
    return result


def start_column_acl_declarations() -> dict[str, dict[str, object]]:
    """開始read/saveと既UM2に必要な追加列権限だけを宣言する。"""
    # 既initial ownerのgames tenant/id/status等は重複宣言しない。
    specs = {
        _OWNER: {
            "games": {
                "away_team_record_id": ["SELECT"],
                "home_team_record_id": ["SELECT"],
                "applied_rules": ["SELECT"],
                "started_at": ["SELECT", "UPDATE"],
                "trashed_at": ["SELECT"],
                "hidden_at": ["SELECT"],
            },
            "team_records": {
                "tenant_id": ["SELECT"],
                "id": ["SELECT", "UPDATE"],
                "kind": ["SELECT"],
                "hidden_at": ["SELECT"],
            },
            "players": {
                "tenant_id": ["SELECT"],
                "id": ["SELECT", "UPDATE"],
                "team_record_id": ["SELECT"],
                "uniform_number": ["SELECT"],
                "roster_status_key": ["SELECT"],
                "hidden_at": ["SELECT"],
            },
            "game_lineups": {
                c: ["SELECT", "INSERT"]
                for c in (
                    "tenant_id",
                    "id",
                    "game_id",
                    "team_record_id",
                    "entries_with_uniform_number_snapshot",
                )
            },
        },
        _ACTOR: {
            "team_records": {
                "tenant_id": ["SELECT"],
                "id": ["SELECT", "UPDATE"],
                "kind": ["SELECT"],
                "hidden_at": ["SELECT"],
            },
            "players": {
                "tenant_id": ["SELECT"],
                "id": ["SELECT", "UPDATE"],
                "team_record_id": ["SELECT"],
                "roster_status_key": ["SELECT"],
                "hidden_at": ["SELECT"],
            },
            "lineup_memories": {
                "tenant_id": ["SELECT", "INSERT"],
                "id": ["SELECT", "INSERT"],
                "team_record_id": ["SELECT", "INSERT"],
                "lineup": ["SELECT", "INSERT", "UPDATE"],
                "migration_preserved_only": ["SELECT"],
                "retired_at": ["SELECT"],
            },
        },
    }
    rows: dict[str, dict[str, object]] = {}
    for role, tables in specs.items():
        for table, columns in tables.items():
            for column, privileges in columns.items():
                key = f"COLUMN-ACL:public:{table}:{column}:{role}"
                rows[key] = dict(
                    expectation_id=key,
                    object_kind="column",
                    object_schema="public",
                    object_id=table,
                    column_id=column,
                    grantee_role_id=role,
                    privilege_ids=privileges,
                    grant_option=False,
                )
    return deepcopy(rows)


def _exact_value(actual: object, expected: object) -> bool:
    """閉宣言でbool/int同値や余剰memberを同一視しない。"""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        return actual.keys() == expected.keys() and all(
            _exact_value(actual[k], v) for k, v in expected.items()
        )
    if isinstance(expected, list):
        assert isinstance(actual, list)
        return len(actual) == len(expected) and all(
            _exact_value(a, e) for a, e in zip(actual, expected, strict=True)
        )
    return actual == expected


def is_start_column_acl(row: Mapping[str, object]) -> bool:
    """主体/列/権限/全fieldの一致以外は拒否する。"""
    key = row.get("expectation_id")
    return isinstance(key, str) and _exact_value(
        dict(row), start_column_acl_declarations().get(key)
    )


def start_policy_declarations() -> dict[str, dict[str, object]]:
    """既単一tenant述語を使う追加policyだけを作る。"""
    from pitchlog.authz.product_table_access import build_product_policy_declaration

    specs = {
        _OWNER: {
            "team_records": ("SELECT", "UPDATE"),
            "players": ("SELECT", "UPDATE"),
            "game_lineups": ("SELECT", "INSERT"),
        },
        _ACTOR: {
            "team_records": ("SELECT", "UPDATE"),
            "players": ("SELECT", "UPDATE"),
            "lineup_memories": ("SELECT", "INSERT", "UPDATE"),
        },
    }
    rows: dict[str, dict[str, object]] = {}
    for role, tables in specs.items():
        for table, commands in tables.items():
            tenant = build_product_policy_declaration(table, "tenant_owned")
            for command in commands:
                actor_kind = "owner" if role == _OWNER else "actor"
                name = f"initial_start_{actor_kind}_{table}_{command.lower()}"
                key = f"POLICY:{table}:{name}"
                row: dict[str, object] = dict(
                    policy_id=key,
                    table_id=table,
                    profile="tenant_owned",
                    policy_name=name,
                    command=command,
                    policy_mode="permissive",
                    role_ids=[role],
                )
                for side, required in [
                    ("using", command in {"SELECT", "UPDATE"}),
                    ("with_check", command in {"INSERT", "UPDATE"}),
                ]:
                    for field in ("predicate_id", "column", "expression"):
                        row[f"{side}_{field}"] = (
                            tenant[f"{side}_{field}"] if required else None
                        )
                rows[key] = row
    return rows


def start_policy_expressions(
    row: Mapping[str, object],
) -> tuple[str | None, str | None]:
    """qual/checkを含む閉宣言全体を照合する。"""
    expected = start_policy_declarations().get(str(row.get("policy_id")))
    if expected is None or not _exact_value(dict(row), expected):
        raise ValueError("開始policyの全fieldが閉宣言と不一致")
    using, check = expected["using_expression"], expected["with_check_expression"]
    if (using is not None and not isinstance(using, str)) or (
        check is not None and not isinstance(check, str)
    ):
        raise ValueError("開始policyの式型が不正")
    return using, check


def generate_start_policy_sql(key: str) -> str:
    """新exact policyの実tenant式を生成する。"""
    row = start_policy_declarations()[key]
    roles = cast(list[str], row["role_ids"])
    sql = (
        f"-- ELEMENT-TYPE: policy\n-- ELEMENT-ID: {key}\n\n"
        f"CREATE POLICY {row['policy_name']} ON public.{row['table_id']}\n"
        f"AS PERMISSIVE FOR {row['command']} TO {roles[0]}\n"
    )
    for field, clause in [
        ("using_expression", "USING"),
        ("with_check_expression", "WITH CHECK"),
    ]:
        if row[field] is not None:
            sql += f"{clause} ({row[field]})\n"
    return sql.rstrip() + ";\n"


def generate_start_column_acl_sql(row: Mapping[str, object]) -> str:
    """全field一致した列権限だけを出力する。"""
    if not is_start_column_acl(row):
        raise ValueError("開始列ACLがexact集合と不一致")
    grants = ", ".join(
        f"{p} ({row['column_id']})" for p in cast(list[str], row["privilege_ids"])
    )
    return (
        "-- ELEMENT-TYPE: column_acl_expectation\n"
        f"-- ELEMENT-ID: {row['expectation_id']}\n\n"
        f"GRANT {grants} ON TABLE public.{row['object_id']} "
        f"TO {row['grantee_role_id']};\n"
    )


_READ_BODY = r"""
DECLARE
    payload jsonb; req record; attempt record; game_row record;
    team record; player record; entry jsonb; side text; ids uuid[];
    away_entries jsonb; home_entries jsonb; result jsonb;
    self_team uuid; snapshot jsonb; lineup record; away_id uuid; home_id uuid;
BEGIN
    IF session_user <> 'pitchlog_initial_actor' OR current_user <>
    'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL OR p_game_id IS NULL OR p_request_id IS NULL
       OR p_attempt_id IS NULL OR p_request_digest IS NULL
       OR octet_length(p_request_digest) <> 32 OR p_payload IS NULL
       OR octet_length(p_payload) > 32768
       OR nullif(current_setting('app.tenant_id',true),'') IS DISTINCT FROM
    p_tenant_id::text
       OR sha256(convert_to(p_payload,'UTF8')) IS DISTINCT FROM p_request_digest THEN
        RAISE EXCEPTION 'initial start input rejected' USING ERRCODE='42501';
    END IF;
    payload := p_payload::jsonb;
    IF jsonb_typeof(payload) <> 'object' OR
       (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(payload) k) IS DISTINCT
    FROM
       ARRAY['away','credential_digest','device_id','domain','game_id','home','start_request_id','tenant_id']::text[]
       OR payload->>'domain' <> 'pitchlog.initial-game-start.v1'
       OR payload->>'tenant_id' IS DISTINCT FROM p_tenant_id::text
       OR payload->>'game_id' IS DISTINCT FROM p_game_id::text
       OR payload->>'start_request_id' IS DISTINCT FROM p_request_id::text THEN
        RAISE EXCEPTION 'initial start payload rejected' USING ERRCODE='42501';
    END IF;
    SELECT r.device_id,r.request_digest INTO STRICT req FROM
    public.game_start_requests r
      WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id AND
    r.start_request_id=p_request_id
      FOR UPDATE;
    IF req.device_id::text IS DISTINCT FROM payload->>'device_id'
       OR req.request_digest IS DISTINCT FROM p_request_digest THEN
        RAISE EXCEPTION 'initial start owner rejected' USING ERRCODE='42501';
    END IF;
    PERFORM 1 FROM public.trusted_devices d WHERE d.tenant_id=p_tenant_id
      AND d.device_id=req.device_id AND d.revoked_at IS NULL
      AND encode(d.credential_digest,'hex')=payload->>'credential_digest' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial start device rejected' USING
    ERRCODE='42501'; END IF;
    SELECT a.outcome INTO STRICT attempt FROM public.game_start_attempts a
      WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id AND
    a.start_request_id=p_request_id
        AND a.attempt_id=p_attempt_id FOR UPDATE;
    SELECT
    g.away_team_record_id,g.home_team_record_id,g.applied_rules,g.status,g.started_at,
           g.trashed_at,g.hidden_at INTO STRICT game_row FROM public.games g
      WHERE g.tenant_id=p_tenant_id AND g.id=p_game_id FOR UPDATE;
    IF game_row.away_team_record_id=game_row.home_team_record_id
       OR game_row.trashed_at IS NOT NULL OR game_row.hidden_at IS NOT NULL THEN
        RAISE EXCEPTION 'initial start game rejected' USING ERRCODE='42501';
    END IF;
    FOREACH side IN ARRAY ARRAY['away','home'] LOOP
        IF jsonb_typeof(payload->side) IS DISTINCT FROM 'array'
           OR jsonb_array_length(payload->side) NOT IN (9,10) THEN
            RAISE EXCEPTION 'initial start entries rejected' USING ERRCODE='42501';
        END IF;
        FOR entry IN SELECT v FROM jsonb_array_elements(payload->side) v LOOP
            IF jsonb_typeof(entry) <> 'object' OR
               (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(entry) k) IS
    DISTINCT FROM
               ARRAY['batting_order','fielding_position','player_id']::text[]
               OR jsonb_typeof(entry->'player_id') <> 'string'
               OR (entry->>'player_id')::uuid::text IS DISTINCT FROM entry->>'player_id'
               OR NOT (entry->'batting_order'='null'::jsonb OR
                    (jsonb_typeof(entry->'batting_order')='number' AND
    entry->>'batting_order' ~ '^[1-9]$'))
               OR jsonb_typeof(entry->'fielding_position') <> 'object' THEN
                RAISE EXCEPTION 'initial start entry rejected' USING ERRCODE='42501';
            END IF;
            IF entry->'fielding_position'->>'kind' = 'fielding' THEN
                IF (SELECT count(*) FROM
    jsonb_object_keys(entry->'fielding_position'))<>2
                   OR jsonb_typeof(entry->'fielding_position'->'position') <> 'number'
                   OR NOT (entry->'fielding_position'->>'position' ~ '^[1-9]$') THEN
                    RAISE EXCEPTION 'initial start role rejected' USING ERRCODE='42501';
                END IF;
            ELSIF entry->'fielding_position' = '{"kind":"designated-hitter"}'::jsonb
    THEN
                NULL;
            ELSE RAISE EXCEPTION 'initial start role rejected' USING ERRCODE='42501';
            END IF;
        END LOOP;
    END LOOP;
    IF attempt.outcome='pending' THEN
        IF game_row.status <> 'preparing' OR game_row.started_at IS NOT NULL
           OR EXISTS (SELECT 1 FROM public.game_lineups l WHERE
    l.tenant_id=p_tenant_id AND l.game_id=p_game_id) THEN
            RAISE EXCEPTION 'initial start already exists' USING ERRCODE='42501';
        END IF;
        FOR team IN SELECT t.id,t.kind,t.hidden_at FROM public.team_records t
          WHERE t.tenant_id=p_tenant_id AND t.id IN
    (game_row.away_team_record_id,game_row.home_team_record_id)
          ORDER BY t.id FOR UPDATE LOOP
            IF team.hidden_at IS NOT NULL OR team.kind NOT IN ('self','opponent') THEN
                RAISE EXCEPTION 'initial start team rejected' USING ERRCODE='42501';
            END IF;
            IF team.kind='self' THEN
                IF self_team IS NOT NULL THEN RAISE EXCEPTION
    'initial start self rejected' USING ERRCODE='42501'; END IF;
                self_team:=team.id;
            END IF;
        END LOOP;
        IF self_team IS NULL OR (SELECT count(*) FROM public.team_records t WHERE
    t.tenant_id=p_tenant_id
            AND t.id IN (game_row.away_team_record_id,game_row.home_team_record_id))
    <> 2 THEN
            RAISE EXCEPTION 'initial start teams missing' USING ERRCODE='42501';
        END IF;
        SELECT array_agg((e->>'player_id')::uuid ORDER BY (e->>'player_id')::uuid)
    INTO ids
          FROM jsonb_array_elements((payload->'away')||(payload->'home')) e;
        FOR player IN SELECT p.id,p.team_record_id,p.roster_status_key,p.hidden_at
    FROM public.players p
          WHERE p.tenant_id=p_tenant_id AND p.id=ANY(ids) ORDER BY p.id FOR UPDATE LOOP
            IF player.hidden_at IS NOT NULL OR player.roster_status_key <> 'active' THEN
                RAISE EXCEPTION 'initial start player rejected' USING ERRCODE='42501';
            END IF;
        END LOOP;
        FOREACH side IN ARRAY ARRAY['away','home'] LOOP
            SELECT jsonb_agg(e ||
    jsonb_build_object('uniform_number_snapshot',p.uniform_number) ORDER BY ord)
              INTO snapshot FROM jsonb_array_elements(payload->side) WITH ORDINALITY
    AS input(e,ord)
              JOIN public.players p ON p.tenant_id=p_tenant_id AND
    p.id=(e->>'player_id')::uuid
              AND p.team_record_id=CASE WHEN side='away' THEN
    game_row.away_team_record_id ELSE game_row.home_team_record_id END
              AND p.hidden_at IS NULL AND p.roster_status_key='active';
            IF jsonb_array_length(snapshot) IS DISTINCT FROM
    jsonb_array_length(payload->side) THEN
                RAISE EXCEPTION 'initial start player missing' USING ERRCODE='42501';
            END IF;
            IF side='away' THEN away_entries:=snapshot; ELSE home_entries:=snapshot;
    END IF;
        END LOOP;
    ELSIF attempt.outcome='committed' THEN
        IF game_row.status NOT IN ('in_progress','finished') OR game_row.started_at
    IS NULL THEN
            RAISE EXCEPTION 'initial start receipt missing' USING ERRCODE='42501';
        END IF;
        IF (SELECT count(*) FROM public.game_lineups l WHERE l.tenant_id=p_tenant_id
    AND l.game_id=p_game_id)<>2 THEN
            RAISE EXCEPTION 'initial start lineups missing' USING ERRCODE='42501';
        END IF;
        FOREACH side IN ARRAY ARRAY['away','home'] LOOP
            SELECT l.id,l.entries_with_uniform_number_snapshot INTO STRICT lineup
    FROM public.game_lineups l
              WHERE l.tenant_id=p_tenant_id AND l.game_id=p_game_id
              AND l.team_record_id=CASE WHEN side='away' THEN
    game_row.away_team_record_id ELSE game_row.home_team_record_id END;
            SELECT jsonb_agg(e-'uniform_number_snapshot' ORDER BY ord) INTO snapshot
              FROM jsonb_array_elements(lineup.entries_with_uniform_number_snapshot)
    WITH ORDINALITY AS input(e,ord);
            IF snapshot IS DISTINCT FROM payload->side THEN
                RAISE EXCEPTION 'initial start immutable payload mismatch' USING
    ERRCODE='42501';
            END IF;
            IF side='away' THEN
    away_entries:=lineup.entries_with_uniform_number_snapshot; away_id:=lineup.id;
            ELSE home_entries:=lineup.entries_with_uniform_number_snapshot;
    home_id:=lineup.id; END IF;
        END LOOP;
        -- 現役選手/背番号は読まない。側所属の固定teamだけからselfを識別する。
        SELECT t.id INTO STRICT self_team FROM public.team_records t WHERE
    t.tenant_id=p_tenant_id
          AND t.id IN (game_row.away_team_record_id,game_row.home_team_record_id) AND
    t.kind='self';
    ELSE RAISE EXCEPTION 'initial start unresolved' USING ERRCODE='42501';
    END IF;
    result:=jsonb_build_object('tenant_id',p_tenant_id,'game_id',p_game_id,'start_request_id',p_request_id,
      'device_id',req.device_id,'attempt_id',p_attempt_id,'request_digest',encode(p_request_digest,'hex'),
      'outcome',attempt.outcome,'away_team_id',game_row.away_team_record_id,'home_team_id',game_row.home_team_record_id,
      'self_team_id',self_team,'applied_rules',game_row.applied_rules,'away',away_entries,'home',home_entries,
      'started_at',game_row.started_at,'away_lineup_id',away_id,'home_lineup_id',home_id);
    RETURN QUERY SELECT result::text;
EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'initial start operation rejected' USING ERRCODE='23514';
END;
"""

_SAVE_BODY = r"""
DECLARE ctx jsonb; stamp timestamptz; away_id uuid; home_id uuid;
BEGIN
    -- readは同じsubject/owner/digest/全payload検査と同一Session lockを持つ。
    SELECT r.context_json::jsonb INTO STRICT ctx FROM
    initial_right_api.read_initial_start_context(
        p_tenant_id,p_game_id,p_request_id,p_attempt_id,p_request_digest,p_payload) r;
    IF ctx->>'outcome' <> 'pending' THEN
        RAISE EXCEPTION 'initial start persistence rejected' USING ERRCODE='42501';
    END IF;
    away_id:=gen_random_uuid(); home_id:=gen_random_uuid(); stamp:=clock_timestamp();
    INSERT INTO
    public.game_lineups(tenant_id,id,game_id,team_record_id,entries_with_uniform_number_snapshot)
      VALUES(p_tenant_id,away_id,p_game_id,(ctx->>'away_team_id')::uuid,ctx->'away'),
            (p_tenant_id,home_id,p_game_id,(ctx->>'home_team_id')::uuid,ctx->'home');
    UPDATE public.games AS target SET status='in_progress',started_at=stamp
      WHERE target.tenant_id=p_tenant_id AND target.id=p_game_id
      AND target.status='preparing' AND target.started_at IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'initial start game changed' USING
    ERRCODE='42501'; END IF;
    RETURN QUERY SELECT stamp,away_id,home_id;
EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'initial start operation rejected' USING ERRCODE='23514';
END;
"""


def generate_start_function_sql(key: str) -> str:
    """固定2関数のみをsearch_path/EXECUTE/owner付きで生成する。"""
    row = start_function_declarations()[key]
    name = row["function_name"]
    returns = str(row["returns"])
    body = _READ_BODY if name == _NAMES[0] else _SAVE_BODY
    signature = f"initial_right_api.{name}({_ARGS})"
    return (
        f"-- ELEMENT-TYPE: function\n-- ELEMENT-ID: {key}\n\n"
        f"CREATE OR REPLACE FUNCTION initial_right_api.{name}(\n"
        "p_tenant_id uuid,p_game_id uuid,p_request_id uuid,p_attempt_id uuid,\n"
        "p_request_digest bytea,p_payload text)\n"
        f"RETURNS {returns}\nLANGUAGE plpgsql VOLATILE SECURITY DEFINER\n"
        f"SET search_path TO pg_catalog, pg_temp\nAS $body${body}$body$;\n"
        f"ALTER FUNCTION {signature} OWNER TO {_OWNER};\n"
        f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,pitchlog_app;\n"
        f"GRANT EXECUTE ON FUNCTION {signature} TO {_ACTOR};\n"
    )


def start_assets_present(asset: Mapping[str, object]) -> bool:
    """新開始資産が1件でもある場合に全exact検査を要求する。"""
    keys = (
        set(start_function_declarations())
        | set(start_column_acl_declarations())
        | set(start_policy_declarations())
    )
    for group, field in [
        ("functions", "function_id"),
        ("column_acl_expectations", "expectation_id"),
        ("policies", "policy_id"),
    ]:
        rows = asset.get(group, [])
        if isinstance(rows, list) and any(
            isinstance(row, dict) and row.get(field) in keys for row in rows
        ):
            return True
    return False


def validate_start_asset_sets(asset: Mapping[str, object]) -> None:
    """新2関数/列ACL/policyの欠損・未知・改変を全fieldで拒否する。"""
    if not start_assets_present(asset):
        return
    for group, field, expected in [
        ("functions", "function_id", start_function_declarations()),
        ("column_acl_expectations", "expectation_id", start_column_acl_declarations()),
        ("policies", "policy_id", start_policy_declarations()),
    ]:
        rows = asset.get(group)
        if not isinstance(rows, list):
            raise ValueError("開始資産集合が配列でない")
        actual = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("開始資産要素がobjectでない")
            key = row.get(field)
            suspicious = (
                (key in expected if isinstance(key, str) else False)
                or (
                    group == "functions"
                    and str(row.get("function_name", "")).endswith(
                        ("initial_start_context", "initial_start")
                    )
                )
                or (
                    group == "policies"
                    and str(row.get("policy_name", "")).startswith("initial_start_")
                )
            )
            if suspicious:
                if not isinstance(key, str) or key in actual:
                    raise ValueError("開始資産が重複又は識別子不正")
                actual[key] = row
        if not _exact_value(actual, expected):
            raise ValueError("開始資産全field/exact集合が不一致")
