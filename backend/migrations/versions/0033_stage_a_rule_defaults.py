"""FR-014段階Aで出所を証明できる全体既定5組だけを配置する。"""

from collections.abc import Sequence
from json import dumps
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "0033_stage_a_rule_defaults"
down_revision: str | Sequence[str] | None = "0032_rg1_restore_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RULES = (
    (
        "game_official",
        "ca626b2e-8751-530e-a431-9ef5c00f7d95",
        [],
        12,
        {
            "startInning": 10,
            "runnerPlacement": "no_out_first_second",
            "leadoffRule": "continue_lineup",
        },
    ),
    (
        "game_semi_official",
        "8fa3b9b7-481b-538b-8093-6af96050d97f",
        [
            {"pointDifference": 10, "startInning": 5},
            {"pointDifference": 7, "startInning": 7},
        ],
        9,
        None,
    ),
    (
        "game_open",
        "b679f9f1-86a8-54f7-9466-a5b01d932953",
        [
            {"pointDifference": 10, "startInning": 5},
            {"pointDifference": 7, "startInning": 7},
        ],
        9,
        None,
    ),
    (
        "game_intrasquad",
        "45677369-9e25-5220-9a30-1d89b338174c",
        [
            {"pointDifference": 10, "startInning": 5},
            {"pointDifference": 7, "startInning": 7},
        ],
        9,
        None,
    ),
    ("game_other", "6ff51660-bee2-552a-9075-1f3f3d1e0dd7", [], 9, None),
)
_IDS = tuple(row[1] for row in _RULES)
_KEYS = tuple(row[0] for row in _RULES)
_POLICIES = (
    ("rule_sets", "tsk550_seed_rule_sets_select"),
    ("rule_sets", "tsk550_seed_rule_sets_insert"),
    ("game_type_rule_defaults", "tsk550_seed_defaults_select"),
    ("game_type_rule_defaults", "tsk550_seed_defaults_insert"),
)


def _acl_state(connection: sa.engine.Connection) -> tuple[tuple[object, ...], ...]:
    """配置が既存の表・列ACLを動かさないことを照合する。"""
    rows = connection.execute(
        sa.text("""
        SELECT relation.relname, attribute.attnum, attribute.attname,
               relation.relacl::text, attribute.attacl::text
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = relation.oid
        WHERE relation.oid IN (
            'public.rule_sets'::regclass,
            'public.game_type_rule_defaults'::regclass
        )
          AND attribute.attnum > 0
          AND NOT attribute.attisdropped
        ORDER BY relation.relname, attribute.attnum
    """)
    ).all()
    return tuple(tuple(row) for row in rows)


def _fixed_list(values: tuple[str, ...]) -> str:
    """固定された候補文字列だけをSQLリテラルへ写す。"""
    if not values or any(
        not value.replace("-", "").replace("_", "").isalnum() for value in values
    ):
        raise RuntimeError("配置対象の固定識別子が不正です")
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """衝突時には全取消しし、既存行を変更せず5組だけを配置する。"""
    connection = op.get_bind()
    if (
        connection.execute(sa.text("SELECT current_user")).scalar_one()
        != "pitchlog_owner"
    ):
        raise RuntimeError("規則配置にはpitchlog_owner接続が必要です")
    if len(_RULES) != 5 or len(set(_IDS)) != 5 or len(set(_KEYS)) != 5:
        raise RuntimeError("規則配置の固定5組が不正です")

    connection.exec_driver_sql(
        "LOCK TABLE public.game_type_rule_defaults, public.rule_sets "
        "IN ACCESS EXCLUSIVE MODE"
    )
    relation_state = connection.execute(
        sa.text("""
        SELECT relname, pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity
        FROM pg_catalog.pg_class
        WHERE oid IN ('public.rule_sets'::regclass,
                      'public.game_type_rule_defaults'::regclass)
        ORDER BY relname
    """)
    ).all()
    if relation_state != [
        ("game_type_rule_defaults", "pitchlog_owner", True, True),
        ("rule_sets", "pitchlog_owner", True, True),
    ]:
        raise RuntimeError("規則配置先のownerまたはFORCE RLSが不正です")
    acl_before = _acl_state(connection)
    policy_before = set(
        connection.execute(
            sa.text("""
        SELECT tablename, policyname FROM pg_catalog.pg_policies
        WHERE schemaname = 'public'
          AND tablename IN ('rule_sets', 'game_type_rule_defaults')
    """)
        ).all()
    )
    if any(policy in policy_before for policy in _POLICIES):
        raise RuntimeError("規則配置の一時policy名が衝突しています")
    vocabulary = (
        connection.execute(
            sa.text("""
        SELECT key FROM public.system_vocabularies
        WHERE category = 'game_type' AND key = ANY(:keys)
        ORDER BY key
    """),
            {"keys": list(_KEYS)},
        )
        .scalars()
        .all()
    )
    if vocabulary != sorted(_KEYS):
        raise RuntimeError("規則配置先の試合区分5件が不足しています")

    ids = _fixed_list(_IDS)
    keys = _fixed_list(_KEYS)
    pairs = ", ".join(f"('{key}', '{rule_id}')" for key, rule_id, *_ in _RULES)
    connection.exec_driver_sql(
        "CREATE POLICY tsk550_seed_rule_sets_select ON public.rule_sets "
        f"FOR SELECT TO pitchlog_owner USING (id IN ({ids}))"
    )
    connection.exec_driver_sql(
        "CREATE POLICY tsk550_seed_rule_sets_insert ON public.rule_sets "
        f"FOR INSERT TO pitchlog_owner WITH CHECK (id IN ({ids}))"
    )
    connection.exec_driver_sql(
        "CREATE POLICY tsk550_seed_defaults_select "
        "ON public.game_type_rule_defaults "
        f"FOR SELECT TO pitchlog_owner USING (game_type_key IN ({keys}))"
    )
    connection.exec_driver_sql(
        "CREATE POLICY tsk550_seed_defaults_insert "
        "ON public.game_type_rule_defaults FOR INSERT TO pitchlog_owner "
        f"WITH CHECK (game_type_category = 'game_type' "
        f"AND (game_type_key, rule_set_id) IN ({pairs}))"
    )
    collision_ids = (
        connection.execute(
            sa.text("""
        SELECT id::text FROM public.rule_sets WHERE id = ANY(:ids)
    """),
            {"ids": list(_IDS)},
        )
        .scalars()
        .all()
    )
    collision_keys = (
        connection.execute(
            sa.text("""
        SELECT game_type_key FROM public.game_type_rule_defaults
        WHERE game_type_key = ANY(:keys)
    """),
            {"keys": list(_KEYS)},
        )
        .scalars()
        .all()
    )
    if collision_ids or collision_keys:
        raise RuntimeError("規則配置の固定IDまたは区分キーが既存行と衝突しています")

    insert_rule = sa.text("""
        INSERT INTO public.rule_sets
          (id, regulation_innings, called_game_conditions,
           extra_innings_limit, tiebreak_rule, uses_dh)
        VALUES (CAST(:id AS uuid), 9, CAST(:cold AS jsonb), :limit,
                CAST(:tiebreak AS jsonb), true)
    """)
    insert_default = sa.text("""
        INSERT INTO public.game_type_rule_defaults
          (game_type_key, game_type_category, rule_set_id)
        VALUES (:key, 'game_type', CAST(:id AS uuid))
    """)
    for key, rule_id, cold, limit, tiebreak in _RULES:
        connection.execute(
            insert_rule,
            {
                "id": rule_id,
                "cold": dumps(cold),
                "limit": limit,
                "tiebreak": None if tiebreak is None else dumps(tiebreak),
            },
        )
    for key, rule_id, *_ in _RULES:
        connection.execute(insert_default, {"key": key, "id": rule_id})

    actual = connection.execute(
        sa.text("""
        SELECT d.game_type_key, r.id, r.regulation_innings,
               r.called_game_conditions, r.extra_innings_limit,
               r.tiebreak_rule, r.uses_dh
        FROM public.game_type_rule_defaults AS d
        JOIN public.rule_sets AS r ON r.id = d.rule_set_id
        WHERE d.game_type_key = ANY(:keys)
        ORDER BY d.game_type_key
    """),
        {"keys": list(_KEYS)},
    ).all()
    expected = sorted(
        (key, UUID(rule_id), 9, cold, limit, tiebreak, True)
        for key, rule_id, cold, limit, tiebreak in _RULES
    )
    if actual != expected:
        raise RuntimeError("規則配置後の固定5組と規則値が不一致です")

    for table, policy in reversed(_POLICIES):
        connection.exec_driver_sql(f"DROP POLICY {policy} ON public.{table}")
    policy_after = set(
        connection.execute(
            sa.text("""
        SELECT tablename, policyname FROM pg_catalog.pg_policies
        WHERE schemaname = 'public'
          AND tablename IN ('rule_sets', 'game_type_rule_defaults')
    """)
        ).all()
    )
    if policy_after != policy_before:
        raise RuntimeError("規則配置後に一時policyが残っています")
    final_state = connection.execute(
        sa.text("""
        SELECT relname, pg_get_userbyid(relowner), relrowsecurity, relforcerowsecurity
        FROM pg_catalog.pg_class
        WHERE oid IN ('public.rule_sets'::regclass,
                      'public.game_type_rule_defaults'::regclass)
        ORDER BY relname
    """)
    ).all()
    if final_state != relation_state:
        raise RuntimeError("規則配置後にRLSまたはownerが変化しました")
    if _acl_state(connection) != acl_before:
        raise RuntimeError("規則配置後に表または列ACLが変化しました")


def downgrade() -> None:
    """参照済み試合の規則を物理削除せず逆適用を拒否する。"""
    raise RuntimeError("規則配置の逆適用には別承認の訂正migrationが必要です")
