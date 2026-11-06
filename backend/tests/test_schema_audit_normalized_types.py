"""型別名だけを正規化し、不正な型の変更は保持して検出する。"""

import copy

import pytest
from db import test_schema_audit as audit
from db.test_schema_audit import _manifest_columns


def _columns(kind: str):
    return _manifest_columns(
        {
            "tables": [
                {
                    "name": "example",
                    "columns": [
                        {
                            "name": "saved_at",
                            "type": kind,
                            "nullable": False,
                            "default": None,
                        }
                    ],
                }
            ]
        }
    )


def test_timestamptz_alias_has_the_same_column_contract():
    """PostgreSQLの同じOIDの別名だけを同一化する。"""
    assert _columns("timestamptz") == _columns("timestamp with time zone")


def test_timezone_and_precision_changes_are_not_normalized_away():
    """タイムゾーンや精度の喪失を別名扱いで隠さない。"""
    expected = _columns("timestamp with time zone")
    assert _columns("timestamp without time zone") != expected
    assert _columns("timestamp(3) with time zone") != expected


@pytest.mark.parametrize(
    ("owner", "constraint"),
    (
        ("writer_bindings", "uq_sync_writer_binding_lease"),
        ("writer_bindings", "uq_sync_writer_binding_nonce"),
        (
            "ordinary_pitch_write_admissions",
            "ordinary_pitch_write_admissions_tenant_id_frame_id_key",
        ),
        (
            "ordinary_pitch_write_admissions",
            "ordinary_pitch_write_admissions_tenant_id_source_event_id_key",
        ),
        (
            "ordinary_pitch_write_admissions",
            "ordinary_pitch_write_admissions_tenant_id_play_row_id_key",
        ),
        (
            "ordinary_pitch_history",
            "ordinary_pitch_history_tenant_id_game_id_internal_generatio_key",
        ),
        ("stats_fact_versions", "stats_fact_versions_tenant_id_id_key"),
        ("stats_fact_versions", "uq_stats_current_game_model"),
        (
            "stats_primitive_sources",
            "stats_primitive_sources_tenant_id_game_id_fact_version_id_r_key",
        ),
    ),
)
def test_private_constraint_relocation_is_rejected(owner: str, constraint: str):
    """全fieldを保っても、別の許可済private表への移設は拒否する。"""
    manifest = audit._load_manifest()
    destinations = {
        "writer_bindings",
        "ordinary_pitch_write_admissions",
        "ordinary_pitch_history",
        "stats_fact_versions",
        "stats_primitive_sources",
    } - {owner}
    assert len(destinations) == 4
    for destination in sorted(destinations):
        changed = copy.deepcopy(manifest)
        source = next(t for t in changed["tables"] if t["name"] == owner)
        row = next(c for c in source["unique_constraints"] if c["name"] == constraint)
        source["unique_constraints"].remove(row)
        target = next(t for t in changed["tables"] if t["name"] == destination)
        target["unique_constraints"].append(row)
        with pytest.raises(ValueError, match="閉集合"):
            audit._cross_table_audit_violations(
                changed,
                audit._manifest_columns(changed),
                audit._manifest_unique_constraints(changed),
                audit._manifest_foreign_keys(changed),
            )
