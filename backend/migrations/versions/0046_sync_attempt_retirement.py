"""結果不明の旧試行を業務publishと同じ鍵で永続遮断する。"""

import sqlalchemy as sa
from alembic import op

revision = "0046_sync_attempt_retirement"
down_revision = "0045_stats_native27_metric_keys"
branch_labels = None
depends_on = None

_OLD_PROSRC_SHA = {
    "publish_writer_binding": (
        "e662e5e668c8ebfb9f4e38a9a4dfdb30f3275feb65c26e9bd1d77d9848e20d26"
    ),
    "guard_writer_records": (
        "148a1472c69a7eac504ad76a430d1a0a019556fb8f5f3135f5f847a14eb61afb"
    ),
}


def _upgrade_existing_functions(bind: sa.Connection) -> None:
    """既配備の旧定義全値を確認してから同署名の遮断関数だけを置換する。"""
    rows = bind.exec_driver_sql(
        """
        SELECT p.proname,
          pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            pg_catalog.btrim(p.prosrc,E' \\t\\r\\n'),'UTF8')),'hex'),
          o.rolname,l.lanname,p.prokind,p.provolatile,p.prosecdef,
          p.proparallel,p.proconfig,
          pg_catalog.pg_get_function_result(p.oid),
          (SELECT pg_catalog.count(*) FROM pg_catalog.aclexplode(
            COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
            WHERE a.grantee<>p.proowner),
          (SELECT COALESCE(pg_catalog.bool_and(
            g.rolname='pitchlog_sync_binding_actor' AND
            a.privilege_type='EXECUTE' AND NOT a.is_grantable),true)
           FROM pg_catalog.aclexplode(
            COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
           LEFT JOIN pg_catalog.pg_roles g ON g.oid=a.grantee
           WHERE a.grantee<>p.proowner)
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_roles o ON o.oid=p.proowner
        JOIN pg_catalog.pg_language l ON l.oid=p.prolang
        WHERE p.oid IN (
          pg_catalog.to_regprocedure('sync_fence_api.publish_writer_binding(uuid,uuid,uuid,jsonb,bytea)'),
          pg_catalog.to_regprocedure('sync_fence_api.guard_writer_records()'))
        """
    ).fetchall()
    if not rows:
        return
    if len(rows) != 2:
        raise RuntimeError("旧writer関数が部分配備されている")
    for row in rows:
        name = row[0]
        if (
            name not in _OLD_PROSRC_SHA
            or row[1] != _OLD_PROSRC_SHA[name]
            or row[2:9]
            != (
                "pitchlog_sync_binding_fn_owner",
                "plpgsql",
                "f",
                "v",
                True,
                "u",
                ["search_path=pg_catalog, pg_temp"],
            )
            or row[9] != ("trigger" if name == "guard_writer_records" else "void")
            or row[10] != (0 if name == "guard_writer_records" else 1)
            or row[11] is not True
        ):
            raise RuntimeError("旧writer関数の定義・権限が一致しない")
    guards = bind.exec_driver_sql(
        """
        SELECT t.tgname,t.tgtype,
          t.tgfoid=pg_catalog.to_regprocedure('sync_fence_api.guard_writer_records()')
          AND t.tgenabled='O' AND NOT t.tgisinternal AND NOT t.tgdeferrable
          AND NOT t.tginitdeferred AND t.tgconstraint=0 AND t.tgnargs=0
          AND t.tgattr::text='' AND t.tgqual IS NULL
          AND t.tgargs=''::pg_catalog.bytea
          AND t.tgoldtable IS NULL AND t.tgnewtable IS NULL
        FROM pg_catalog.pg_trigger t WHERE t.tgrelid IN (
          'sync_fence.writer_bindings'::pg_catalog.regclass,
          'sync_fence.writer_admissions'::pg_catalog.regclass)
          AND NOT t.tgisinternal ORDER BY t.tgname
        """
    ).fetchall()
    if guards != [
        ("sync_writer_admission_immutable", 27, True),
        ("sync_writer_admission_no_truncate", 34, True),
        ("sync_writer_binding_immutable", 27, True),
        ("sync_writer_binding_no_truncate", 34, True),
    ]:
        raise RuntimeError("旧writer guard triggerが一致しない")
    from pitchlog.authz.attempt_recovery_product import (
        upgrade_function_sql,
        upgrade_trigger_sql,
    )

    # 公式provisionerと同じbytes実行。PL/pgSQLの%ROWTYPEをplaceholderにしない。
    raw_connection = bind.connection.driver_connection
    if raw_connection is None:
        raise RuntimeError("writer関数移行の実接続がない")
    with raw_connection.cursor() as cursor:
        for name in ("publish_writer_binding", "guard_writer_records"):
            cursor.execute(upgrade_function_sql(name).encode("utf-8"))
    for statement in upgrade_trigger_sql():
        bind.exec_driver_sql(statement)


def upgrade() -> None:
    """旧attemptの原識別と遮断世代を保存し、認可配備までは閉じる。"""
    op.create_table(
        "attempt_retirements",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("d5", sa.Uuid(), nullable=False),
        sa.Column("authority_id", sa.Uuid(), nullable=False),
        sa.Column("wire_d4", sa.Text(), nullable=False),
        sa.Column("codec_version", sa.BigInteger(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("event_fingerprint", sa.Text(), nullable=False),
        sa.Column("recovery_generation", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "wire_d4<>'' AND request_fingerprint<>'' AND event_fingerprint<>''",
            name="ck_sync_attempt_retirement_text",
        ),
        sa.CheckConstraint(
            "codec_version>0 AND recovery_generation>0",
            name="ck_sync_attempt_retirement_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "game_id"],
            ["games.tenant_id", "games.id"],
            name="fk_sync_attempt_retirement_game",
            ondelete="NO ACTION",
            match="FULL",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "attempt_id", name="pk_sync_attempt_retirements"
        ),
        schema="sync_fence",
    )
    op.execute("ALTER TABLE sync_fence.attempt_retirements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sync_fence.attempt_retirements FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE sync_fence.attempt_retirements FROM PUBLIC")
    _upgrade_existing_functions(op.get_bind())


def downgrade() -> None:
    """耐久遮断を失う物理削除を拒否する。"""
    raise RuntimeError("旧試行の遮断記録を物理削除できません")
