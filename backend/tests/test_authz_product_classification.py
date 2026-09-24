"""製品表分類と露出の事実の fail-closed 契約を検査する。"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitchlog.authz.classification import (
    ProductClassificationError,
    load_json_object,
    validate_product_table_classification,
)
from pitchlog.db import all_models
from pitchlog.db.base import Base

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CLASSIFICATION_PATH = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "product" / "table-classification.json"
)
_EXPOSURE_FACTS_PATH = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "product" / "exposure-facts.json"
)
_MANIFEST_PATH = _REPOSITORY_ROOT / "contracts" / "db" / "schema-manifest.json"
_DATA_MODEL_PATH = _REPOSITORY_ROOT / "docs" / "design" / "data-model.md"

_EXPECTED_PROFILES = {
    "tenant_owned": {
        "team_records",
        "players",
        "games",
        "lineup_memories",
        "game_lineups",
        "participation_intervals",
        "event_slots",
        "operation_events",
        "play_rows",
        "play_runners",
        "temporary_player_id_mappings",
        "idempotency_ledger",
        "rejected_event_originals",
        "evacuated_event_originals",
        "recording_generations",
        "medical_notes",
        "medical_note_versions",
        "pdf_export_records",
        "tenant_vocabularies",
        "player_merge_events",
        "player_move_records",
        "invalidation_intents",
        "migrated_final_lineups",
    },
    "self_tenant_row": {"tenants"},
    "effective_group_control": {
        "analysis_groups",
        "group_memberships",
        "sharing_grants",
        "group_invitations",
    },
    "global_read_only": {
        "game_type_rule_defaults",
        "system_vocabularies",
        "admin_vocabularies",
        "system_settings",
    },
    "function_only": {
        "tenant_auth_subjects",
        "tenant_credentials",
        "tenant_tokens",
        "rate_limit_counters",
        "admin_credentials",
        "admin_sessions",
        "admin_operation_logs",
        "migration_runs",
        "migration_quarantine",
        "migration_resolution_reports",
        "migration_warning_reports",
        "rule_sets",
        "tournament_rule_assignments",
    },
}
_EXPECTED_FACT_TABLES = {
    "non_tenant": {
        "game_type_rule_defaults",
        "system_vocabularies",
        "admin_vocabularies",
        "system_settings",
    },
    "control_resource": {
        "analysis_groups",
        "group_memberships",
        "sharing_grants",
        "group_invitations",
    },
    "mixed_ownership_rule_resource": {
        "rule_sets",
        "tournament_rule_assignments",
    },
    "admin_only": {
        "admin_credentials",
        "admin_sessions",
        "admin_operation_logs",
    },
    "pre_auth_only": {
        "tenant_auth_subjects",
        "tenant_credentials",
        "tenant_tokens",
        "rate_limit_counters",
    },
    "migration_only": {
        "migration_runs",
        "migration_quarantine",
        "migration_resolution_reports",
        "migration_warning_reports",
    },
}
_EXPECTED_SECRET_COLUMNS = {
    ("tenant_credentials", "password_hash"),
    ("admin_credentials", "password_hash"),
    ("group_invitations", "code_hash"),
    ("tenant_tokens", "id"),
    ("admin_sessions", "id"),
}
_PROFILE_MUTATIONS = (
    ("admin_credentials", "global_read_only"),
    ("tenant_credentials", "tenant_owned"),
    ("analysis_groups", "tenant_owned"),
    ("admin_operation_logs", "effective_group_control"),
    ("migration_quarantine", "global_read_only"),
    ("rate_limit_counters", "global_read_only"),
    ("rule_sets", "global_read_only"),
    ("tournament_rule_assignments", "tenant_owned"),
    ("admin_operation_logs", "tenant_owned"),
    ("admin_operation_logs", "global_read_only"),
    ("tenant_auth_subjects", "tenant_owned"),
)


@pytest.fixture(scope="module")
def documents() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    str,
    frozenset[str],
]:
    """検査対象の資産、正本、モデル母集合を読み込む。"""
    assert all_models.IMPORTED_MODEL_MODULE_NAMES
    return (
        load_json_object(_CLASSIFICATION_PATH),
        load_json_object(_EXPOSURE_FACTS_PATH),
        load_json_object(_MANIFEST_PATH),
        _DATA_MODEL_PATH.read_text(encoding="utf-8"),
        frozenset(Base.metadata.tables),
    )


def _validate(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """資産組を製品表分類の検査関数へ渡す。"""
    classification, exposure_facts, manifest, data_model, model_tables = documents
    validate_product_table_classification(
        classification=classification,
        exposure_facts=exposure_facts,
        manifest=manifest,
        model_tables=model_tables,
        canonical_source=data_model,
    )


def _classification_rows(classification: dict[str, Any]) -> list[dict[str, Any]]:
    """分類資産の表行を型付きで返す。"""
    rows = classification["tables"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _fact_rows(exposure_facts: dict[str, Any]) -> list[dict[str, Any]]:
    """露出の事実の種類行を型付きで返す。"""
    rows = exposure_facts["facts"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _row_for_table(classification: dict[str, Any], table_name: str) -> dict[str, Any]:
    """指定した表の分類行を一意に返す。"""
    rows = [
        row
        for row in _classification_rows(classification)
        if row.get("table") == table_name
    ]
    assert len(rows) == 1
    return rows[0]


def _fact_for_kind(exposure_facts: dict[str, Any], kind: str) -> dict[str, Any]:
    """指定した種類の露出の事実を一意に返す。"""
    rows = [row for row in _fact_rows(exposure_facts) if row.get("kind") == kind]
    assert len(rows) == 1
    return rows[0]


def _set_profile(
    classification: dict[str, Any],
    table_name: str,
    profile: str,
) -> None:
    """変異用に分類行をスキーマ妥当な別プロファイルへ移す。"""
    row = _row_for_table(classification, table_name)
    row["profile"] = profile
    if profile == "function_only":
        row["access_path"] = {
            "reason": "mutation_with_valid_shape",
            "owner_unit": "U-A1",
        }
    else:
        row.pop("access_path", None)


def _mutated_documents(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> list[Any]:
    """資産組を変異間で共有しない深いコピーにする。"""
    return copy.deepcopy(list(documents))


def _assert_mutation_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
    mutate: Callable[[list[Any]], None],
) -> None:
    """改変前の green を確かめてから変異が拒否されることを表明する。"""
    _validate(documents)
    mutated = _mutated_documents(documents)
    mutate(mutated)
    with pytest.raises(ProductClassificationError):
        _validate(tuple(mutated))


def test_design_assignment_satisfies_all_classification_conditions(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """詳細設計 1-4 の45表の割り当てが全条件を満たす。"""
    classification = documents[0]
    actual = {
        profile: {
            row["table"]
            for row in _classification_rows(classification)
            if row["profile"] == profile
        }
        for profile in _EXPECTED_PROFILES
    }

    assert actual == _EXPECTED_PROFILES
    assert {profile: len(tables) for profile, tables in actual.items()} == {
        "tenant_owned": 23,
        "self_tenant_row": 1,
        "effective_group_control": 4,
        "global_read_only": 4,
        "function_only": 13,
    }
    assert (
        _row_for_table(classification, "rule_sets")["access_path"]["owner_unit"]
        == "U-X1"
    )
    assert (
        _row_for_table(classification, "tournament_rule_assignments")["access_path"][
            "owner_unit"
        ]
        == "U-X1"
    )
    _validate(documents)


def test_manifest_models_and_classification_have_the_same_population(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """Manifest と Base.metadata の母集合を独立に導いて分類と照合する。"""
    classification, _exposure_facts, manifest, _data_model, model_tables = documents
    manifest_tables = {table["name"] for table in manifest["tables"]}
    classification_tables = {
        row["table"] for row in _classification_rows(classification)
    }

    assert len(manifest_tables) == len(model_tables) == 45
    assert manifest_tables == model_tables == classification_tables


def test_exposure_facts_are_complete_and_reference_manifest_objects(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """7種の事実が期待集合を持ち、その表と列が manifest に実在する。"""
    _classification, exposure_facts, manifest, _data_model, _models = documents
    manifest_columns = {
        table["name"]: {column["name"] for column in table["columns"]}
        for table in manifest["tables"]
    }
    actual_table_facts = {
        kind: {
            entry["table"] for entry in _fact_for_kind(exposure_facts, kind)["entries"]
        }
        for kind in _EXPECTED_FACT_TABLES
    }
    secret_entries = _fact_for_kind(exposure_facts, "secret_column")["entries"]
    actual_secret_columns = {
        (entry["table"], entry["column"]) for entry in secret_entries
    }
    scanned_secret_columns = {
        (table_name, column_name)
        for table_name, column_names in manifest_columns.items()
        for column_name in column_names
        if column_name in {"password_hash", "code_hash"}
        or (table_name in {"tenant_tokens", "admin_sessions"} and column_name == "id")
    }

    assert actual_table_facts == _EXPECTED_FACT_TABLES
    assert actual_secret_columns == scanned_secret_columns == _EXPECTED_SECRET_COLUMNS
    assert set(actual_table_facts) | {"secret_column"} == {
        fact["kind"] for fact in _fact_rows(exposure_facts)
    }
    assert all(
        table_name in manifest_columns
        for tables in actual_table_facts.values()
        for table_name in tables
    )
    assert all(
        column_name in manifest_columns[table_name]
        for table_name, column_name in actual_secret_columns
    )
    assert all(entry["reason"] for entry in secret_entries)


def test_every_evidence_quote_exists_verbatim_in_canonical_source(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """すべての典拠の引用が正本に一字一句存在する。"""
    _classification, exposure_facts, _manifest, data_model, _models = documents
    quotes = [
        evidence["quote"]
        for fact in _fact_rows(exposure_facts)
        for entry in fact["entries"]
        for evidence in entry["evidence"]
    ]

    assert quotes
    assert all(quote in data_model for quote in quotes)


@pytest.mark.parametrize(("table_name", "profile"), _PROFILE_MUTATIONS)
def test_unsafe_profile_mutation_is_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
    table_name: str,
    profile: str,
) -> None:
    """露出の事実と矛盾する個別のプロファイル変異を拒否する。"""

    def mutate(values: list[Any]) -> None:
        """指定された表だけを別プロファイルへ移す。"""
        _set_profile(values[0], table_name, profile)

    _assert_mutation_rejected(documents, mutate)


def test_unassigned_table_mutation_is_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """表を1件未割り当てにする変異を拒否する。"""

    def mutate(values: list[Any]) -> None:
        """分類資産から1表を取り除く。"""
        classification = values[0]
        classification["tables"] = [
            row
            for row in _classification_rows(classification)
            if row["table"] != "games"
        ]

    _assert_mutation_rejected(documents, mutate)


def test_added_model_mutation_is_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """分類も manifest も持たないモデル追加の変異を拒否する。"""

    def mutate(values: list[Any]) -> None:
        """モデル母集合だけへ架空の表を追加する。"""
        values[4] = values[4] | {"unclassified_model_table"}

    _assert_mutation_rejected(documents, mutate)


def test_missing_function_access_reason_mutation_is_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """function_only の到達理由を消す変異を拒否する。"""

    def mutate(values: list[Any]) -> None:
        """到達経路から reason だけを削る。"""
        _row_for_table(values[0], "tenant_credentials")["access_path"].pop("reason")

    _assert_mutation_rejected(documents, mutate)


def test_noncanonical_evidence_quote_mutation_is_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """正本にない文言へ典拠を変える変異を拒否する。"""

    def mutate(values: list[Any]) -> None:
        """典拠の引用を正本に存在しない文言へ変える。"""
        fact = _fact_for_kind(values[1], "non_tenant")
        fact["entries"][0]["evidence"][0]["quote"] = "正本に存在しない引用"

    _assert_mutation_rejected(documents, mutate)


def test_removed_password_fact_and_global_admin_credential_mutation_is_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """秘密列を弱めながら管理者資格情報を全体公開する変異を拒否する。"""

    def mutate(values: list[Any]) -> None:
        """管理者 password_hash の事実を消して表を全体公開へ移す。"""
        secret_fact = _fact_for_kind(values[1], "secret_column")
        secret_fact["entries"] = [
            entry
            for entry in secret_fact["entries"]
            if not (
                entry["table"] == "admin_credentials"
                and entry["column"] == "password_hash"
            )
        ]
        _set_profile(values[0], "admin_credentials", "global_read_only")

    _assert_mutation_rejected(documents, mutate)


def test_count_preserving_function_only_swap_mutation_is_rejected(
    documents: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        frozenset[str],
    ],
) -> None:
    """件数を保った function_only と tenant_owned の入れ替えを拒否する。"""

    def mutate(values: list[Any]) -> None:
        """事実のない表と管理者専用表を相互に入れ替える。"""
        _set_profile(values[0], "team_records", "function_only")
        _set_profile(values[0], "admin_operation_logs", "tenant_owned")

    _assert_mutation_rejected(documents, mutate)
