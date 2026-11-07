"""隔離owned PGへP3 26件超の私有候補を配備する構文・ACL前置。"""

from __future__ import annotations

from pathlib import Path
from typing import LiteralString, cast

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.p3_projection_paged_sql import (
    candidate_paged_append_sql,
    candidate_paged_begin_sql,
    candidate_paged_finalize_sql,
)

from .test_p3_candidate_compile_author import (
    initial_scope_database as initial_scope_database,
)
from .test_p3_candidate_compile_author import (
    product_node_binary as product_node_binary,
)
from .test_p3_candidate_compile_author import (
    test_owned_candidate_0048_compiles as _install_old_candidate,
)
from .test_p3_candidate_compile_author import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db
_PACKET = Path.home() / ".cache/pitchlog/mvp-past-correction-product-20261106"
_PAGING = _PACKET / "paging-26-plus-20261107"


def test_owned_p3_paging_private_functions_compile(vertical_database) -> None:
    """旧25件候補に重ね、未正式0048の頁関数とdeferred guardだけを検査する。"""
    _install_old_candidate(vertical_database)
    selector = (_PACKET / "p3-play_primitives_native.sql").read_text()
    sections = {
        part.split("\n", 1)[0]: part.split("\n", 1)[1].strip()
        for part in selector.split("-- pitchlog-query: ")[1:]
    }
    health = sections["canonical_health"]
    bodies = (
        (_PAGING / "p3-capsule-paging-r6.candidate.sql").read_text(),
        (_PAGING / "p3-paging-progress-r3.candidate.sql").read_text(),
        (_PAGING / "p3-paging-stats-stage-r5.candidate.sql").read_text(),
        candidate_paged_begin_sql(),
        candidate_paged_append_sql(),
        candidate_paged_finalize_sql(health_sql=health),
    )
    with psycopg.connect(vertical_database.authority.database.business_admin) as conn:
        for body in bodies:
            conn.execute(sql.SQL(cast(LiteralString, body)), prepare=False)
        rows = conn.execute(
            "SELECT p.proname, pg_catalog.pg_get_userbyid(p.proowner), "
            "p.prosecdef FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='sync_right_api' AND p.proname IN "
            "('begin_p3_projection_page','append_p3_projection_page',"
            "'finalize_p3_projection_page') ORDER BY p.proname"
        ).fetchall()
        assert rows == [
            (name, "pitchlog_sync_right_fn_owner", True)
            for name in (
                "append_p3_projection_page",
                "begin_p3_projection_page",
                "finalize_p3_projection_page",
            )
        ]
