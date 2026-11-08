"""妨害prepareの内外SQL文脈を製品配置とは独立のowned PGで検査する。"""

import pytest

from pitchlog.authz.interference_evidence_sql import (
    _OUT,
    _OUT_ADMISSIONS,
    _PENALTY_THIRD,
    _PLACEMENT,
)

pytestmark = pytest.mark.requires_db


def _explain_interference_outer_scope(admin) -> None:
    """元source・物理走者・裁定の内外6文脈をSQL parserへ通す。"""
    scope = (
        " FROM (SELECT '{}'::jsonb AS payload) source_row CROSS JOIN "
        "(SELECT '{}'::jsonb AS before_cp, '{}'::jsonb AS after_cp, "
        "'{}'::jsonb AS p, NULL::uuid AS p_tenant_id) fixture_scope"
    )
    for expression in _OUT_ADMISSIONS:
        assert admin.execute(
            "EXPLAIN (FORMAT JSON) SELECT " + expression + scope
        ).fetchone()
    nested_scope = scope.replace(
        "NULL::uuid AS p_tenant_id",
        "NULL::uuid AS p_tenant_id, '{}'::jsonb AS m, '{}'::jsonb AS r",
    )
    for expression in (_OUT, _PLACEMENT, _PENALTY_THIRD):
        assert admin.execute(
            "EXPLAIN (FORMAT JSON) SELECT " + expression + nested_scope
        ).fetchone()


def test_interference_sql_scopes_explain(admin_connection):
    """Owned PostgreSQLで両alias文脈を検査し、保存成功へ読み替えない。"""
    _explain_interference_outer_scope(admin_connection)
