"""成績5関数のPG表記と既system xmin5だけのACL採取を閉検査する。"""

from __future__ import annotations

import re

import pytest

from pitchlog.authz.function_result_type import pg_result_type
from pitchlog.authz.product_catalog import CatalogQueryId, _query_for_id

_XMIN_RELATIONS = {
    ("public", "idempotency_ledger"),
    ("public", "event_slots"),
    ("public", "operation_events"),
    ("public", "play_rows"),
    ("sync_fence", "ordinary_pitch_checkpoints"),
}


def test_column_acl_preserves_positive_columns_and_only_adds_five_xmin_relations():
    """正の全列/NULL ACL/owner除外を保持し、負列の採取だけexact5へ閉じる。"""
    query = _query_for_id(CatalogQueryId.COLUMN_ACL)
    normalized = " ".join(query.split())
    finite_predicate = (
        "AND ( attribute.attnum > 0 OR ( attribute.attnum < 0 "
        "AND attribute.attname = 'xmin' "
        "AND (namespace.nspname, relation.relname) IN ( "
        "('public', 'idempotency_ledger'), ('public', 'event_slots'), "
        "('public', 'operation_events'), "
        "('public', 'play_rows'), ('sync_fence', 'ordinary_pitch_checkpoints') "
        ") ) )"
    )
    assert finite_predicate in normalized
    assert normalized.count(" OR ") == 1
    assert normalized.count("attribute.attnum < 0") == 1
    assert normalized.count("attribute.attnum > 0") == 1
    pairs = re.findall(r"\('([^']+)', '([^']+)'\)", query)
    assert len(pairs) == 5 and set(pairs) == _XMIN_RELATIONS
    assert "pg_catalog.aclexplode(attribute.attacl)" in query
    assert "acldefault" not in query
    assert "AND NOT attribute.attisdropped" in query
    assert "AND privilege.grantee <> relation.relowner" in query
    assert "WHERE namespace.nspname = ANY(%s)" in query
    assert "AND relation.relname = ANY(%s)" in query
    assert "ORDER BY 1, 2, attribute.attnum, 4, 5, 6" in query
    # 誤権限も観測し旧exact集合と比較する。観測時にSELECT/FnOwnerへ間引かない。
    assert "privilege.privilege_type =" not in query
    assert "grantee.rolname =" not in query


@pytest.mark.parametrize(
    "schema,table,column",
    [
        ("public", "games", "xmin"),
        ("other", "event_slots", "xmin"),
        ("public", "event_slots", "xmax"),
        ("public", "event_slots", "tableoid"),
        ("other", "play_rows", "xmin"),
        ("public", "ordinary_pitch_checkpoints", "xmin"),
        ("sync_fence", "play_rows", "xmin"),
        ("public", "play_rows", "xmax"),
        ("public", "play_rows", "tableoid"),
        ("public", "play_rows", "ctid"),
    ],
)
def test_unknown_system_column_or_relation_is_not_added(schema, table, column):
    """別表/別schema/他system列を新しい採取対象へ広げない。"""
    query = _query_for_id(CatalogQueryId.COLUMN_ACL)
    assert not ((schema, table) in _XMIN_RELATIONS and column == "xmin")
    pairs = set(re.findall(r"\('([^']+)', '([^']+)'\)", query))
    assert pairs == _XMIN_RELATIONS
    assert query.count("attribute.attname = 'xmin'") == 1
    assert not re.search(r"attribute\.attname\s+(?:IN|LIKE)", query)


@pytest.mark.parametrize(
    "declaration,observed",
    [
        (
            "TABLE(fact_version_id uuid,revision bigint,source_set_sha256 text,"
            "model_sha256 text,source_count bigint,row_count bigint,"
            "transaction_id text,"
            "completion_state text)",
            "TABLE(fact_version_id uuid, revision bigint, source_set_sha256 text, "
            "model_sha256 text, source_count bigint, row_count bigint, "
            "transaction_id text, "
            "completion_state text)",
        ),
        (
            "TABLE(metric_id text,state text,value numeric,d2 bigint,"
            "source_event_id uuid)",
            "TABLE(metric_id text, state text, value numeric, d2 bigint, "
            "source_event_id uuid)",
        ),
        (
            "TABLE(metric_id text,state text,value numeric)",
            "TABLE(metric_id text, state text, value numeric)",
        ),
        (
            "TABLE(revision bigint,source_set_sha256 text)",
            "TABLE(revision bigint, source_set_sha256 text)",
        ),
        (
            "TABLE(fact_version_id uuid,source_event_id uuid,model_sha256 text,"
            "source_set_sha256 text)",
            "TABLE(fact_version_id uuid, source_event_id uuid, model_sha256 text, "
            "source_set_sha256 text)",
        ),
    ],
)
def test_five_stats_table_results_match_observed_pg_spelling(declaration, observed):
    """実PG差分の5列宣言だけを書式正規化して全fieldを一致させる。"""
    assert pg_result_type(declaration) == observed
    assert pg_result_type(observed) == observed


@pytest.mark.parametrize(
    "value,expected",
    [
        ("void", "void"),
        ("trigger", "trigger"),
        ("bigint", "bigint"),
        ("SETOF uuid", "SETOF uuid"),
        ("TABLE (id uuid)", "TABLE(id uuid)"),
        ('TABLE("a,b" numeric(12,3),x text)', 'TABLE("a,b" numeric(12,3), x text)'),
        ('TABLE("a""b,c" text,x text)', 'TABLE("a""b,c" text, x text)'),
        ("TABLE(a numeric(12, 3),b uuid[])", "TABLE(a numeric(12, 3), b uuid[])"),
        ('TABLE("unclosed text,x text)', 'TABLE("unclosed text,x text)'),
        ("TABLE(a numeric(12,3),b text", "TABLE(a numeric(12,3),b text"),
        ("TABLE(a text),b text)", "TABLE(a text),b text)"),
    ],
)
def test_result_format_does_not_change_types_quotes_or_invalid_nesting(value, expected):
    """既単一結果・型内カンマ・引用符を保持し、不正括弧を補修しない。"""
    assert pg_result_type(value) == expected


@pytest.mark.parametrize(
    "changed",
    [
        "TABLE(other bigint,source_set_sha256 text)",
        "TABLE(revision integer,source_set_sha256 text)",
        "TABLE(source_set_sha256 text,revision bigint)",
        "TABLE(revision bigint)",
        "TABLE(revision bigint,source_set_sha256 text,extra text)",
        'TABLE("revision" bigint,source_set_sha256 text)',
    ],
)
def test_result_name_type_order_missing_extra_remain_unequal(changed):
    """型/列を無視する比較や期待値の欠落許可へ変えない。"""
    expected = pg_result_type("TABLE(revision bigint,source_set_sha256 text)")
    assert pg_result_type(changed) != expected
