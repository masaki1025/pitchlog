"""core_guard.py の単体・統合テスト。

検査資産は黙って書き換えられると検査自体が意味を失い、guard_paths の漏れは CI が
green のまま起きる。そのため架空設定の単体テストに加え、実設定を直接読む回帰テストを持つ。
"""
import ast
import fnmatch
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "core_guard.py"
CORE_AREAS_PATH = REPO / ".claude" / "core-areas.json"
REQUIRED_CHECK_TEXT = "コア領域/検査経路の変更: 人間による逐行確認を実施した"
GUARD_PATHS = [
    ".claude/core-areas.json",
    ".github/workflows/ci.yml",
    "scripts/core_guard.py",
    ".github/pull_request_template.md",
    ".claude/skills/pr/SKILL.md",
]
CORE_DOCUMENT_PATHS = (
    "docs/design/sync-protocol.md",
    "docs/requirements/requirements-pitchlog-2026-07-22.md",
)
DATA_MODEL_DOCUMENT_PATH = "docs/design/data-model.md"
DATA_MODEL_AREA_IDS = (
    "sync-protocol",
    "game-state",
    "recording-rights",
    "tenant-isolation",
    "data-migration",
)
DATA_MODEL_GUARD_PATHS = (
    "scripts/design_relations/citation-map-data-model.json",
    "scripts/design_relations/closure-handoff-data-model.json",
    "tests/fixtures/data-model-source.txt",
    "scripts/design_relations/fixture-sha256-data-model.txt",
)
ADR_001_PATH = "docs/adr/ADR-001-codex-model-selection.md"
ADR_003_PATH = "docs/adr/ADR-003-domain-calc-method.md"
CORE_ADR_AREA_PATHS = {
    "sync-protocol": (ADR_001_PATH, ADR_003_PATH),
    "game-state": (ADR_001_PATH, ADR_003_PATH),
    "recording-rights": (ADR_001_PATH,),
    "tenant-isolation": (ADR_001_PATH,),
    "data-migration": (ADR_001_PATH, ADR_003_PATH),
}
AUTHZ_GUARD_BASE_REVISION = "56c281c409e972927940fad830aa38352df32f1e"
AUTHZ_GUARD_CANDIDATE_PATHS = (
    "scripts/check_authz_catalog.py",
    "scripts/check_authz_function_bodies.py",
    "scripts/check_design_propagation.py",
    "scripts/check_doc_coverage.py",
    "scripts/check_docs_status.py",
    "scripts/check_failure_injection_points.py",
    "scripts/check_mcdc_map.py",
    "scripts/check_processing_stages.py",
    "scripts/check_shared_preconditions.py",
    "tests/test_check_authz_catalog.py",
    "tests/test_check_authz_function_bodies.py",
    "tests/test_check_design_propagation.py",
    "tests/test_check_doc_coverage.py",
    "tests/test_check_docs_status.py",
    "tests/test_check_failure_injection_points.py",
    "tests/test_check_mcdc_map.py",
    "tests/test_check_processing_stages.py",
    "tests/test_check_shared_preconditions.py",
)
AUTHZ_GUARD_PATH_ADDITIONS = (
    "scripts/check_authz_catalog.py",
    "scripts/check_authz_function_bodies.py",
    "scripts/check_mcdc_map.py",
    "scripts/check_failure_injection_points.py",
    "scripts/check_shared_preconditions.py",
    "scripts/check_docs_status.py",
    "tests/test_check_authz_catalog.py",
    "tests/test_check_authz_function_bodies.py",
    "tests/test_check_mcdc_map.py",
    "tests/test_check_failure_injection_points.py",
    "tests/test_check_shared_preconditions.py",
    "tests/test_check_docs_status.py",
    "scripts/check_frozen_baselines.py",
    "scripts/frozen-baseline-scan-allowlist.json",
    "scripts/frozen_baselines.py",
    "tests/frozen_negatives/test_frozen_baseline_acceptance.py",
    "tests/frozen_negatives/test_frozen_baseline_ci_dispatch.py",
    "tests/frozen_negatives/test_frozen_baseline_ledger.py",
    "tests/frozen_negatives/test_frozen_baseline_scan.py",
    "tests/frozen_scan_fixtures.py",
    "tests/test_frozen_baseline_acceptance_rules.py",
    "tests/test_frozen_baseline_declarations.py",
    "tests/test_frozen_negative_inventory.py",
    "tests/test_frozen_scan_rules.py",
)
AUTHZ_BACKEND_TEST_PATTERN = "backend/tests/test_authz*.py"
AUTHZ_BACKEND_WORDING_AREA_PATH_ADDITIONS = (
    "backend/tests/wording_scan.py",
    "backend/tests/test_wording_scan.py",
)
AUTHZ_BACKEND_PREVIOUSLY_COVERED_PATHS = (
    "backend/tests/test_authz_ddl.py",
    "backend/tests/test_authz_mutation.py",
    "backend/tests/test_authz_mutation_composition.py",
    "backend/tests/test_authz_mutation_composition_full.py",
    "backend/tests/test_authz_mutation_execution.py",
    *AUTHZ_BACKEND_WORDING_AREA_PATH_ADDITIONS,
)
AUTHZ_TENANT_AREA_PATH_ADDITIONS = (
    "scripts/check_authz_function_bodies.py",
    "scripts/check_mcdc_map.py",
    "scripts/check_failure_injection_points.py",
    "scripts/check_shared_preconditions.py",
    "tests/test_check_authz_function_bodies.py",
    "tests/test_check_mcdc_map.py",
    "tests/test_check_failure_injection_points.py",
    "tests/test_check_shared_preconditions.py",
    "backend/src/pitchlog/authz/*",
    AUTHZ_BACKEND_TEST_PATTERN,
    "backend/tests/test_product_authz*.py",
    "backend/tests/product_authz*.py",
    *AUTHZ_BACKEND_WORDING_AREA_PATH_ADDITIONS,
)
TENANT_BOUNDARY_AREA_PATH_CASES = (
    (
        "backend/src/pitchlog/repositories/*",
        "backend/src/pitchlog/repositories/base.py",
    ),
    ("backend/tests/db_fixtures.py", "backend/tests/db_fixtures.py"),
    (
        "scripts/check_tenant_boundary_bypass.py",
        "scripts/check_tenant_boundary_bypass.py",
    ),
    ("scripts/frozen_history.py", "scripts/frozen_history.py"),
    ("scripts/frozen_archive.py", "scripts/frozen_archive.py"),
    (
        "contracts/tenant_boundary/*",
        "contracts/tenant_boundary/nested/future.json",
    ),
    (
        "tests/fixtures/tenant_boundary/*",
        "tests/fixtures/tenant_boundary/positive/pitchlog/repositories/base.py",
    ),
    (
        "tests/fixtures/frozen-archive-cases/*",
        "tests/fixtures/frozen-archive-cases/manifest.json",
    ),
    (
        "tests/test_check_tenant_boundary_bypass.py",
        "tests/test_check_tenant_boundary_bypass.py",
    ),
    ("tests/test_frozen_archive.py", "tests/test_frozen_archive.py"),
    (
        "tests/test_frozen_archive_case_runner.py",
        "tests/test_frozen_archive_case_runner.py",
    ),
    ("tests/test_frozen_history.py", "tests/test_frozen_history.py"),
)
TENANT_BOUNDARY_AREA_PATH_ADDITIONS = tuple(
    pattern for pattern, _ in TENANT_BOUNDARY_AREA_PATH_CASES
)
TENANT_BOUNDARY_CORE_PATHS = tuple(
    path for _, path in TENANT_BOUNDARY_AREA_PATH_CASES
)
RECEPTION_INPUT_AREA_IDS = ("sync-protocol", "recording-rights")
RECEPTION_INPUT_AREA_PATHS = (
    "frontend/src/lib/sync/receptionInput.spec.ts",
    "frontend/src/lib/sync/receptionInput.ts",
)
ORM_SCHEMA_MIGRATION_AREA_PATHS = {
    "sync-protocol": (
        ".env.example",
        "backend/alembic.ini",
        "backend/migrations/*",
        "backend/tests/db/*",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/src/pitchlog/db/__init__.py",
        "backend/src/pitchlog/db/all_models.py",
        "backend/src/pitchlog/db/base.py",
        "backend/src/pitchlog/db/config.py",
        "backend/src/pitchlog/db/engine.py",
        "backend/src/pitchlog/db/mixins.py",
        "backend/src/pitchlog/db/model_metadata.py",
        "backend/src/pitchlog/db/url.py",
        "backend/src/pitchlog/db/sync_protocol/*",
        "backend/tests/test_alembic_environment.py",
        "backend/tests/test_database_configuration.py",
        "backend/tests/test_database_url.py",
        "backend/tests/test_migration_hygiene.py",
        "backend/tests/test_model_mixins.py",
        "backend/tests/test_operation_event_kind_contract.py",
        "backend/tests/test_schema_manifest.py",
        "backend/tests/test_sync_protocol_models.py",
        "contracts/db/schema-manifest.json",
        "scripts/generate_orm_acceptance_sheets.py",
        "tests/test_environment_template.py",
        "tests/test_orm_acceptance_sheets.py",
    ),
    "game-state": (
        ".env.example",
        "backend/alembic.ini",
        "backend/migrations/*",
        "backend/tests/db/*",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/src/pitchlog/db/__init__.py",
        "backend/src/pitchlog/db/all_models.py",
        "backend/src/pitchlog/db/base.py",
        "backend/src/pitchlog/db/config.py",
        "backend/src/pitchlog/db/engine.py",
        "backend/src/pitchlog/db/mixins.py",
        "backend/src/pitchlog/db/model_metadata.py",
        "backend/src/pitchlog/db/url.py",
        "backend/src/pitchlog/db/game_state/*",
        "backend/tests/test_alembic_environment.py",
        "backend/tests/test_database_configuration.py",
        "backend/tests/test_database_url.py",
        "backend/tests/test_game_state_models.py",
        "backend/tests/test_migration_hygiene.py",
        "backend/tests/test_model_mixins.py",
        "backend/tests/test_schema_manifest.py",
        "contracts/db/schema-manifest.json",
        "scripts/generate_orm_acceptance_sheets.py",
        "tests/test_environment_template.py",
        "tests/test_orm_acceptance_sheets.py",
    ),
    "recording-rights": (
        ".env.example",
        "backend/alembic.ini",
        "backend/migrations/*",
        "backend/tests/db/*",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/src/pitchlog/db/__init__.py",
        "backend/src/pitchlog/db/all_models.py",
        "backend/src/pitchlog/db/base.py",
        "backend/src/pitchlog/db/config.py",
        "backend/src/pitchlog/db/engine.py",
        "backend/src/pitchlog/db/mixins.py",
        "backend/src/pitchlog/db/model_metadata.py",
        "backend/src/pitchlog/db/url.py",
        "backend/src/pitchlog/db/recording_rights/*",
        "backend/tests/test_alembic_environment.py",
        "backend/tests/test_database_configuration.py",
        "backend/tests/test_database_url.py",
        "backend/tests/test_migration_hygiene.py",
        "backend/tests/test_model_mixins.py",
        "backend/tests/test_recording_rights_models.py",
        "backend/tests/test_schema_manifest.py",
        "contracts/db/schema-manifest.json",
        "scripts/generate_orm_acceptance_sheets.py",
        "tests/test_environment_template.py",
        "tests/test_orm_acceptance_sheets.py",
    ),
    "tenant-isolation": (
        ".env.example",
        "backend/alembic.ini",
        "backend/migrations/*",
        "backend/src/pitchlog/db/__init__.py",
        "backend/src/pitchlog/db/all_models.py",
        "backend/src/pitchlog/db/base.py",
        "backend/src/pitchlog/db/config.py",
        "backend/src/pitchlog/db/engine.py",
        "backend/src/pitchlog/db/mixins.py",
        "backend/src/pitchlog/db/model_metadata.py",
        "backend/src/pitchlog/db/url.py",
        "backend/src/pitchlog/db/tenant_isolation/*",
        "backend/tests/test_alembic_environment.py",
        "backend/tests/test_database_configuration.py",
        "backend/tests/test_database_url.py",
        "backend/tests/test_migration_hygiene.py",
        "backend/tests/test_model_mixins.py",
        "backend/tests/test_schema_manifest.py",
        "backend/tests/test_tenant_models.py",
        "contracts/db/schema-manifest.json",
        "scripts/generate_orm_acceptance_sheets.py",
        "tests/test_environment_template.py",
        "tests/test_orm_acceptance_sheets.py",
    ),
    "data-migration": (
        ".env.example",
        "backend/alembic.ini",
        "backend/migrations/*",
        "backend/tests/db/*",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/src/pitchlog/db/__init__.py",
        "backend/src/pitchlog/db/all_models.py",
        "backend/src/pitchlog/db/base.py",
        "backend/src/pitchlog/db/config.py",
        "backend/src/pitchlog/db/engine.py",
        "backend/src/pitchlog/db/mixins.py",
        "backend/src/pitchlog/db/model_metadata.py",
        "backend/src/pitchlog/db/url.py",
        "backend/src/pitchlog/db/data_migration/*",
        "backend/tests/test_alembic_environment.py",
        "backend/tests/test_data_migration_models.py",
        "backend/tests/test_database_configuration.py",
        "backend/tests/test_database_url.py",
        "backend/tests/test_migration_hygiene.py",
        "backend/tests/test_model_mixins.py",
        "backend/tests/test_schema_manifest.py",
        "backend/tests/test_type_boundary_contract.py",
        "backend/tests/type_boundary_contract.py",
        "contracts/db/schema-manifest.json",
        "scripts/generate_orm_acceptance_sheets.py",
        "tests/test_environment_template.py",
        "tests/test_orm_acceptance_sheets.py",
    ),
}
APPENDIX_E_GAME_STATE_AREA_PATH_ADDITIONS = (
    "contracts/state-transition/*",
    "contracts/vocabulary/*",
    "scripts/check_deriver_dependencies.py",
    "scripts/check_expander_dependencies.py",
    "scripts/check_gap_register.py",
    "scripts/check_human_review_signature.py",
    "scripts/check_input_axes_descriptor.py",
    "scripts/check_input_axes_three_way_parity.py",
    "scripts/check_provenance.py",
    "scripts/check_required_set_mutation.py",
    "scripts/check_required_set_coverage.py",
    "scripts/check_vocabulary_manifest.py",
    "scripts/state_transition_freeze.py",
    "tests/test_deriver_dependencies.py",
    "tests/test_expander_dependencies.py",
    "tests/test_game_end_contract_schema.py",
    "tests/test_gap_register.py",
    "tests/test_human_review_signature.py",
    "tests/test_input_axes_descriptor.py",
    "tests/test_input_axes_three_way_parity.py",
    "tests/test_required_set_mutation.py",
    "tests/test_required_set_coverage.py",
    "tests/test_state_transition_contract_schema.py",
    "tests/test_state_transition_freeze.py",
    "tests/test_vocabulary_manifest.py",
    "tests/test_vocabulary_seed.py",
    "tests/test_consumer_handoff.py",
)
NORMALIZATION_AREA_PATH_ADDITIONS = (
    "scripts/check_state_transition_normalization.py",
    "scripts/state_transition_normalization.py",
    "tests/test_state_transition_normalization.py",
)
REFERENCE_DISCOVERY_AREA_PATH_ADDITIONS = (
    "scripts/check_frozen_baselines.py",
    "tests/frozen_negatives/test_frozen_baseline_acceptance.py",
    "tests/frozen_negatives/test_frozen_baseline_ci_dispatch.py",
    "tests/frozen_negatives/test_frozen_baseline_ledger.py",
    "tests/frozen_scan_fixtures.py",
    "tests/test_ci_wiring.py",
    "tests/test_core_guard.py",
    "tests/test_frozen_negative_inventory.py",
    "tests/test_frozen_scan_rules.py",
)
# 敵対レビュー指摘 1 — ケース生成・代表選択・凍結の検査を担う新規 6 本の登録。
CASE_GENERATION_AREA_PATH_ADDITIONS = (
    "scripts/check_branch_row_mapping.py",
    "scripts/check_manual_fixture_baselines.py",
    "scripts/expand_game_end_cases.py",
    "scripts/expand_state_transition_cases.py",
    "scripts/representative_selection.py",
    "tests/test_branch_row_mapping.py",
)
VOCABULARY_DATA_MIGRATION_AREA_PATH_ADDITIONS = (
    "contracts/vocabulary/*",
    "scripts/check_vocabulary_manifest.py",
    "tests/test_vocabulary_manifest.py",
    "tests/test_vocabulary_seed.py",
)
APPENDIX_E_GAME_STATE_ASSET_PATHS = (
    "contracts/state-transition/deriver_dependency_policy_schema_v1.json",
    "contracts/state-transition/deriver_dependency_policy_v1.json",
    "contracts/state-transition/expander_dependency_policy_schema_v1.json",
    "contracts/state-transition/expander_dependency_policy_v1.json",
    "contracts/state-transition/game_end_contract_schema_v1.json",
    "contracts/state-transition/gap_register_schema_v1.json",
    "contracts/state-transition/gap_register_v1.json",
    "contracts/state-transition/human_review_signature_schema_v1.json",
    "contracts/state-transition/input_axes_descriptor_schema_v1.json",
    "contracts/state-transition/input_axes_descriptor_v1.json",
    "contracts/state-transition/state_transition_contract_schema_v1.json",
    "contracts/vocabulary/input_vocabulary_v1.json",
    "contracts/vocabulary/vocabulary_manifest_schema_v1.json",
    "contracts/vocabulary/vocabulary_manifest_v1.json",
    "contracts/vocabulary/vocabulary_seed_schema_v1.json",
    *APPENDIX_E_GAME_STATE_AREA_PATH_ADDITIONS[2:],
    *NORMALIZATION_AREA_PATH_ADDITIONS,
)
NEW_CORE_PATH_CHANGES = (
    "contracts/authz/auth-catalog.json",
    ADR_001_PATH,
    ADR_003_PATH,
    "frontend/src/lib/courseInputView.ts",
    "frontend/src/lib/format.ts",
    "backend/conftest.py",
    *TENANT_BOUNDARY_CORE_PATHS,
)
DOMAIN_CALC_AREA_IDS = ("game-state", "data-migration")
UM1_TENANT_AREA_PATH_ADDITIONS = (
    "backend/tests/test_*_boundary.py",
    "backend/tests/test_*_repository.py",
    "backend/src/pitchlog/api/*",
    "backend/tests/test_api_*.py",
    "backend/tests/test_roster_*.py",
    "backend/tests/test_request_presentation.py",
    "tests/test_census_baseline_check.py",
)
UF2_AUTH_STORE_AREA_PATH_ADDITIONS = ("frontend/src/stores/authStore*",)
UF6_CLIENT_AREA_PATH_ADDITIONS = ("frontend/src/api/client*",)
UF6_TENANT_AREA_PATH_ADDITIONS = ("frontend/src/api/*",)
UF8_GAME_SCREEN_AREA_PATH_ADDITIONS = ("frontend/src/screens/GameScreen*",)
UF5_TEAM_AREA_PATH_ADDITIONS = (
    "frontend/src/components/settings/TeamMembersContent*",
    "frontend/src/lib/rosterQueryKeys*",
    "frontend/src/screens/TeamScreen*",
)
D2_DOMAIN_CALC_PATH_ADDITIONS = (
    "frontend/src/domain/*",
    "backend/src/pitchlog/domainrt/*",
    "frontend/public/domain/*",
    "frontend/scripts/domain-checks/*",
    "frontend/scripts/domain-build/*",
    "frontend/scripts/domain-sql/*",
    "frontend/index.html",
    "frontend/eslint.config.js",
    "frontend/.dependency-cruiser.cjs",
    "frontend/src/testing/vectorRunner.ts",
    "frontend/src/testing/vectorRunner.spec.ts",
    "frontend/src/testing/vectorConformance.spec.ts",
    "frontend/src/testing/handoffLoader.ts",
    "frontend/src/testing/handoffLoader.spec.ts",
    "frontend/src/testing/artifactAdapter.ts",
    "frontend/src/testing/artifactAdapter.spec.ts",
    "backend/tests/domainrt/*",
    "backend/Dockerfile",
)
D2_DOMAIN_CALC_GLOBS = (
    "frontend/src/domain/*",
    "backend/src/pitchlog/domainrt/*",
    "frontend/public/domain/*",
    "frontend/scripts/domain-checks/*",
    "frontend/scripts/domain-build/*",
    "frontend/scripts/domain-sql/*",
    "backend/tests/domainrt/*",
)
D2_SYNC_PROTOCOL_PATH_ADDITIONS = ("tests/domain/runners/test_handoff_loader.py",)
US1_SYNC_APPLY_AREA_PATH_ADDITIONS = (
    "backend/src/pitchlog/sync/*",
    "backend/src/pitchlog/repositories/sync_apply.py",
    "backend/tests/test_sync_apply_*.py",
)
# 登録済みRG1層は履歴の検証に保持し、現在の追加層と混同しない。
UR1_REGISTERED_PATHS: dict[str, tuple[str, ...]] = {
    "sync-protocol": (
        "backend/src/pitchlog/repositories/rg1.py",
        "backend/src/pitchlog/repositories/operation_registry.py",
        "backend/tests/test_rg1_*",
        "contracts/tenant_boundary/repository-contract.json",
        "contracts/tenant_boundary/base-allowlist.json",
        "contracts/authz/product/function-bodies/*rg1*",
    ),
    "recording-rights": (
        "backend/src/pitchlog/repositories/rg1.py",
        "backend/src/pitchlog/repositories/operation_registry.py",
        "backend/src/pitchlog/authz/classification.py",
        "backend/src/pitchlog/authz/product_control_access.py",
        "backend/src/pitchlog/authz/product_table_access.py",
        "backend/src/pitchlog/authz/product_catalog.py",
        "backend/src/pitchlog/authz/product_provisioning.py",
        "backend/src/pitchlog/authz/product_function_acl.py",
        "backend/tests/test_rg1_*",
        "contracts/authz/product/ddl-elements.json",
        "contracts/authz/product/table-classification.json",
        "contracts/authz/product/exposure-facts.json",
        "contracts/authz/product/function-bodies/*rg1*",
        "contracts/tenant_boundary/repository-contract.json",
        "contracts/tenant_boundary/base-allowlist.json",
        "scripts/check_authz_catalog.py",
        "tests/test_check_authz_catalog.py",
    ),
}
UF13_TENANT_ROUTE_PATHS = (
    "frontend/src/router*",
    "frontend/src/App*",
)
EXPECTED_AREA_PATH_ADDITIONS: dict[str, tuple[str, ...]] = {
    "game-state": ("backend/src/pitchlog/db/stage_a_startup.py",),
    "tenant-isolation": (
        "backend/src/pitchlog/services/game_creation.py",
        "backend/tests/test_game_preparing*.py",
    ),
}
REGISTERED_BEFORE_UR1: dict[str, tuple[str, ...]] = {
    "sync-protocol": US1_SYNC_APPLY_AREA_PATH_ADDITIONS,
    "recording-rights": US1_SYNC_APPLY_AREA_PATH_ADDITIONS,
}
UF5_AREA_PATH_ADDITIONS: dict[str, tuple[str, ...]] = {
    "tenant-isolation": UF5_TEAM_AREA_PATH_ADDITIONS,
    "data-migration": UF5_TEAM_AREA_PATH_ADDITIONS,
}
DOMAIN_CALC_GLOBS = (
    "backend/domain/*",
    "backend/src/pitchlog/domaincheck/*",
    "backend/src/pitchlog/domaingen/*",
    "backend/src/pitchlog/domainmut/*",
    "backend/src/pitchlog/generated/*",
    "backend/tests/domain/*",
    "frontend/src/lib/generated/*",
    "tests/domain/*",
    *D2_DOMAIN_CALC_GLOBS,
)
PRODUCT_RLS_AREA_PATH_ADDITIONS = (
    "docs/ops/product-rls-real-schema.md",
    "scripts/product_rls_real_schema/*",
    "scripts/product-rls-real-schema-targets.json",
)
# 計画書 4-8 節の予定パス。①③ は完全パス、② は専用ディレクトリ配下とする。
PRODUCT_RLS_PLANNED_EXACT_PATHS = frozenset(
    {
        "docs/ops/product-rls-real-schema.md",
        "scripts/product-rls-real-schema-targets.json",
    }
)
PRODUCT_RLS_PLANNED_DIRECTORY = "scripts/product_rls_real_schema/"
# 同表の代表パスで各パターンの fnmatch 一致を確かめる。
PRODUCT_RLS_PATTERN_EXAMPLES = (
    ("docs/ops/product-rls-real-schema.md",),
    (
        "scripts/product_rls_real_schema/runner.py",
        "scripts/product_rls_real_schema/catalog_plugin.py",
    ),
    ("scripts/product-rls-real-schema-targets.json",),
)


def assert_registered_block(paths: Sequence[str], block: tuple[str, ...]) -> int:
    """登録ブロックが一意かつ宣言順の連続列として残ることを確認する。

    Args:
        paths: 領域へ登録されたパス列。
        block: 登録時の宣言順を保持するパス群。

    Returns:
        ブロック先頭の位置。
    """
    assert block
    assert all(paths.count(pattern) == 1 for pattern in block)
    start = paths.index(block[0])
    assert tuple(paths[start : start + len(block)]) == block
    return start


def core_guard_source_with_additions(
    additions: dict[str, tuple[str, ...]],
) -> str:
    """実検査器の追加層宣言だけを隔離履歴用の値へ置き換える。

    Args:
        additions: 隔離履歴で先行宣言する領域別追加層。

    Returns:
        指定した追加層を関数定義前に持つ検査器ソース。
    """
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    declarations = [
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "AREA_PATH_ADDITIONS"
    ]
    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.end_lineno is not None
    lines = source.splitlines(keepends=True)
    replacement = (
        "AREA_PATH_ADDITIONS: Mapping[str, tuple[str, ...]] = "
        f"{additions!r}\n"
    )
    return "".join(
        [
            *lines[: declaration.lineno - 1],
            replacement,
            *lines[declaration.end_lineno :],
        ]
    )


EXISTING_REAL_GUARD_PATHS = (
    ".claude/core-areas.json",
    ".github/workflows/ci.yml",
    "scripts/core_guard.py",
    ".github/pull_request_template.md",
    ".claude/skills/pr/SKILL.md",
    ".claude/skills/release/SKILL.md",
    ".claude/skills/task-done/SKILL.md",
)
NEW_GUARD_PATHS = (
    "scripts/design_relations/defects.json",
    "scripts/design_relations/sync-protocol.json",
    "scripts/design_relations/citation-map-data-model.json",
    "scripts/design_relations/closure-handoff-data-model.json",
    "scripts/design_relations/req-universe.json",
    "scripts/design_relations/fixture-sha256.txt",
    "scripts/design_relations/fixture-sha256-data-model.txt",
    "scripts/check_design_propagation.py",
    "scripts/check_doc_coverage.py",
    "scripts/check_processing_stages.py",
    *AUTHZ_GUARD_PATH_ADDITIONS[:6],
    "tests/fixtures/sync-protocol-source.txt",
    "tests/fixtures/data-model-source.txt",
    "tests/test_check_design_propagation.py",
    "tests/test_check_doc_coverage.py",
    "tests/test_check_processing_stages.py",
    *AUTHZ_GUARD_PATH_ADDITIONS[6:],
    "tests/test_ci_wiring.py",
    "tests/test_core_guard.py",
    ".claude/skills/finalize-doc/SKILL.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "conftest.py",
    "tests/conftest.py",
)


def write_text(root: Path, relative_path: str, content: str) -> None:
    """一時リポジトリ内に UTF-8 テキストファイルを作る。

    Args:
        root: 一時リポジトリのルート。
        relative_path: root からの相対パス。
        content: 書き込む内容。
    """
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(root: Path, relative_path: str, value: object) -> None:
    """一時リポジトリ内に JSON ファイルを作る。

    Args:
        root: 一時リポジトリのルート。
        relative_path: root からの相対パス。
        value: JSON として書き込む値。
    """
    write_text(root, relative_path, json.dumps(value, ensure_ascii=False))


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """一時リポジトリに対して git コマンドを実行する。

    Args:
        root: 一時リポジトリのルート。
        *args: git に渡す引数。

    Returns:
        git コマンドの結果。
    """
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )


def make_repo(tmp_path: Path, core_paths: list[str] | None = None) -> Path:
    """検査用の core-areas.json を持つ一時 git リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        core_paths: 一時設定に入れるコア領域の glob パターン。

    Returns:
        初期コミット済みの一時リポジトリルート。
    """
    root = tmp_path / "repo"
    root.mkdir()
    run_git(root, "init", "-q", "-b", "feature/test")
    write_json(
        root,
        ".claude/core-areas.json",
        {
            "description": "test",
            "guard_paths": GUARD_PATHS,
            "areas": [
                {
                    "id": "test-core",
                    "name": "テスト用コア領域",
                    "paths": core_paths or [],
                }
            ],
        },
    )
    write_text(root, "README.md", "base\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "base",
    )
    return root


def make_repo_with_actual_core_areas(tmp_path: Path) -> Path:
    """実設定を基に宣言の全件を登録した合成リポジトリを作る。

    U-F8 までの登録を保持し、U-F5 登録前なら合成リポジトリだけに補う。
    U-F5 より後の登録があっても既存ブロックの位置から判定する。
    D-2 の登録も実設定の登録済みブロックとして確かめる。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。

    Returns:
        実設定を初期コミットに含む一時リポジトリルート。
    """
    root = tmp_path / "repo"
    root.mkdir()
    run_git(root, "init", "-q", "-b", "feature/test")
    configuration = load_actual_core_areas()
    areas = {area["id"]: area for area in configuration["areas"]}
    assert UF6_CLIENT_AREA_PATH_ADDITIONS[0] in areas["sync-protocol"]["paths"]
    assert UF6_CLIENT_AREA_PATH_ADDITIONS[0] in areas["recording-rights"]["paths"]
    assert UF6_TENANT_AREA_PATH_ADDITIONS[0] in areas["tenant-isolation"]["paths"]
    for area_id, additions in UF5_AREA_PATH_ADDITIONS.items():
        paths = areas[area_id]["paths"]
        present = tuple(pattern in paths for pattern in additions)
        assert len(set(present)) == 1, f"{area_id} に U-F5 の部分登録がある"
        if all(present):
            assert_registered_block(paths, additions)
        else:
            paths.extend(additions)
    for area_id, additions in REGISTERED_BEFORE_UR1.items():
        assert_registered_block(areas[area_id]["paths"], additions)
    write_text(
        root,
        ".claude/core-areas.json",
        json.dumps(configuration, ensure_ascii=False, indent=2) + "\n",
    )
    write_text(root, "README.md", "base\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "base",
    )
    return root


def make_layered_core_repo(
    tmp_path: Path, *, has_area_path_additions: bool = True
) -> tuple[Path, str]:
    """5 領域と基線定義を持つ履歴検査用リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        has_area_path_additions: 基線の親側に追加層の定義を置くか。

    Returns:
        合成リポジトリと変更不能な初期コミット OID。
    """
    root = tmp_path / "layered-repo"
    root.mkdir()
    run_git(root, "init", "-q", "-b", "main")
    areas = [
        {
            "id": area_id,
            "name": area_id,
            "description": "合成領域",
            "paths": [f"base/{area_id}.py"],
        }
        for area_id in (
            "sync-protocol",
            "game-state",
            "recording-rights",
            "tenant-isolation",
            "data-migration",
        )
    ]
    write_json(
        root,
        ".claude/core-areas.json",
        {"description": "合成基線", "guard_paths": [], "areas": areas},
    )
    source = "ANCHOR = 'base'\n"
    if has_area_path_additions:
        source += "AREA_PATH_ADDITIONS = {}\n"
    write_text(root, "scripts/core_guard.py", source)
    write_text(root, "tests/test_core_guard.py", "EXPECTED = 'base'\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "baseline",
    )
    return root, run_git(root, "rev-parse", "HEAD").stdout.strip()


def commit_area_path_changes(
    root: Path,
    additions: dict[str, tuple[str, ...]],
    *,
    cochanged_paths: tuple[str, ...] = (),
) -> str:
    """領域別 paths と指定した基線定義を同一コミットで変更する。

    Args:
        root: 合成リポジトリのルート。
        additions: 領域 ID ごとの追加パス。
        cochanged_paths: JSON と同一コミットで変更するパス。

    Returns:
        作成したコミットの OID。
    """
    path = root / ".claude/core-areas.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    for area in document["areas"]:
        area["paths"].extend(additions.get(area["id"], ()))
    write_json(root, ".claude/core-areas.json", document)
    for relative_path in cochanged_paths:
        current = (root / relative_path).read_text(encoding="utf-8")
        write_text(root, relative_path, current + "CHANGED = True\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "area paths change",
    )
    return run_git(root, "rev-parse", "HEAD").stdout.strip()


def commit_change(
    root: Path,
    relative_path: str,
    content: str = "changed\n",
) -> tuple[str, str]:
    """ファイル変更をコミットし、比較用の base/head SHA を返す。

    Args:
        root: 一時リポジトリのルート。
        relative_path: 追加・更新するファイルの相対パス。
        content: 変更後のファイル内容。

    Returns:
        変更前の base SHA と変更後の head SHA。
    """
    base_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    write_text(root, relative_path, content)
    run_git(root, "add", relative_path)
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "change",
    )
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    return base_sha, head_sha


def commit_changes(root: Path, relative_paths: tuple[str, ...]) -> tuple[str, str]:
    """複数ファイルの変更を1コミットにまとめ、比較用SHAを返す。

    Args:
        root: 一時リポジトリのルート。
        relative_paths: 追加・更新するファイルの相対パス。

    Returns:
        変更前の base SHA と変更後の head SHA。
    """
    base_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    for relative_path in relative_paths:
        write_text(root, relative_path, "changed\n")
    run_git(root, "add", *relative_paths)
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "change",
    )
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    return base_sha, head_sha


def commit_rename(root: Path, old_path: str, new_path: str) -> tuple[str, str]:
    """同一内容のファイルを git mv し、比較用の base/head SHA を返す。

    Args:
        root: 一時リポジトリのルート。
        old_path: rename 前のファイルの相対パス。
        new_path: rename 後のファイルの相対パス。

    Returns:
        rename 前の base SHA と rename 後の head SHA。
    """
    _, base_sha = commit_change(root, old_path, "unchanged\n")
    (root / new_path).parent.mkdir(parents=True, exist_ok=True)
    run_git(root, "mv", old_path, new_path)
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "rename",
    )
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    return base_sha, head_sha


def assert_exact_rename(
    root: Path,
    base_sha: str,
    head_sha: str,
    old_path: str,
    new_path: str,
) -> None:
    """git が変更を類似度 100% の rename と認識したことを確認する。"""
    result = run_git(root, "diff", "--name-status", f"{base_sha}...{head_sha}")

    assert result.stdout.splitlines() == [f"R100\t{old_path}\t{new_path}"]


def write_event(tmp_path: Path, base_sha: str, head_sha: str, body: object) -> Path:
    """pull_request イベント JSON を作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。
        base_sha: イベントに設定する base SHA。
        head_sha: イベントに設定する head SHA。
        body: イベントに設定する PR 本文。

    Returns:
        作成したイベント JSON のパス。
    """
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": base_sha},
                    "head": {"sha": head_sha},
                    "body": body,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return event_path


def run_guard(
    root: Path,
    *,
    event_name: str | None = None,
    event_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """指定イベント環境で core_guard.py をサブプロセス実行する。

    Args:
        root: ``--root`` に渡す一時リポジトリのルート。
        event_name: GITHUB_EVENT_NAME に設定する値。
        event_path: GITHUB_EVENT_PATH に設定する JSON パス。

    Returns:
        標準出力・標準エラーを取得したサブプロセスの結果。
    """
    env = os.environ.copy()
    env.pop("GITHUB_EVENT_NAME", None)
    env.pop("GITHUB_EVENT_PATH", None)
    if event_name is not None:
        env["GITHUB_EVENT_NAME"] = event_name
    if event_path is not None:
        env["GITHUB_EVENT_PATH"] = str(event_path)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=REPO,
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )


def load_actual_core_areas() -> dict[str, Any]:
    """書き漏らしを CI 自身で検出するため、実際のコア領域設定を読む。

    Returns:
        JSON オブジェクトとして読み込んだ実設定。
    """
    value = json.loads(CORE_AREAS_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _require_reference_discovery_policy(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """参照導出検査の資産側宣言を fail-closed で取得する。"""
    policy = configuration.get("reference_discovery")
    assert isinstance(policy, dict), "reference_discovery 宣言がない"
    assert policy.get("schema_version") == 1
    for key in (
        "scan_roots",
        "contract_roots",
        "required_area_ids",
        "detected_reference_forms",
        "not_detected",
    ):
        values = policy.get(key)
        assert isinstance(values, list) and values, f"{key} が空または配列でない"
        assert all(isinstance(value, str) and value for value in values)
        assert len(values) == len(set(values)), f"{key} に重複がある"
    claim = policy.get("claim")
    assert isinstance(claim, str) and claim
    exclusions = policy.get("declared_exclusions")
    assert isinstance(exclusions, dict), "declared_exclusions 宣言がない"
    paths = exclusions.get("paths")
    assert isinstance(paths, list) and len(paths) == 11
    assert all(isinstance(path, str) and path for path in paths)
    assert paths == sorted(set(paths)), "declared_exclusions.paths に重複または順序違反"
    reason = exclusions.get("reason")
    assert isinstance(reason, str) and reason
    assert exclusions.get("deferred_to") == (
        "TSK-540 送り（unresolved-report.md の S34・design.md 8-6）"
    )
    return policy


def _static_path_parts(node: ast.AST) -> tuple[str, ...] | None:
    """AST 式から静的に読めるパス部分を左から順に返す。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = _static_path_parts(node.right)
        if right is None:
            return None
        left = _static_path_parts(node.left)
        return (*(() if left is None else left), *right)
    if isinstance(node, ast.Call):
        function_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
        )
        if function_name not in {"Path", "PurePath", "PurePosixPath"}:
            return None
        parts: list[str] = []
        for argument in node.args:
            argument_parts = _static_path_parts(argument)
            if argument_parts is None:
                parts.clear()
                continue
            parts.extend(argument_parts)
        return tuple(parts) if parts else None
    return None


def _normalized_static_paths(tree: ast.AST) -> frozenset[str]:
    """文字列と ``/``・Path 呼び出しから静的パス候補を導出する。"""
    paths: set[str] = set()
    for node in ast.walk(tree):
        parts = _static_path_parts(node)
        if parts is None:
            continue
        normalized = "/".join(
            part.replace("\\", "/").strip("/") for part in parts if part
        )
        if normalized:
            paths.add(normalized)
    return frozenset(paths)


def _python_import_dependencies(
    tree: ast.AST,
    modules: dict[str, str],
) -> set[str]:
    """静的 import が指す走査対象 Python ファイルを返す。"""
    dependencies: set[str] = set()

    def add_module(module_name: str) -> None:
        dependency = modules.get(module_name)
        if dependency is not None:
            dependencies.add(dependency)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_module(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module is not None:
                add_module(node.module)
                for alias in node.names:
                    add_module(f"{node.module}.{alias.name}")
    return dependencies


def derive_contract_reference_python_paths(
    root: Path,
    configuration: dict[str, Any],
) -> tuple[str, ...]:
    """契約ルートへの静的参照とその逆依存閉包を決定的に導出する。

    Args:
        root: 走査対象のリポジトリルート。
        configuration: ``core-areas.json`` の内容。

    Returns:
        コア領域へ登録すべき Python ファイルのソート済み相対パス。
    """
    policy = _require_reference_discovery_policy(configuration)
    scan_roots = tuple(policy["scan_roots"])
    contract_roots = tuple(policy["contract_roots"])
    source_paths: list[str] = []
    for scan_root in scan_roots:
        directory = root / scan_root
        assert directory.is_dir(), f"参照走査ルートを解決できない: {scan_root}"
        source_paths.extend(
            path.relative_to(root).as_posix()
            for path in directory.rglob("*.py")
            if path.is_file()
        )
    source_paths = sorted(set(source_paths))
    assert source_paths, "参照走査対象の Python ファイルがない"

    module_paths = {
        source_path.removesuffix(".py").replace("/", "."): source_path
        for source_path in source_paths
    }
    trees: dict[str, ast.AST] = {}
    static_paths_by_source: dict[str, frozenset[str]] = {}
    for source_path in source_paths:
        source = (root / source_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=source_path)
        trees[source_path] = tree
        static_paths_by_source[source_path] = _normalized_static_paths(tree)

    direct_references = {
        source_path
        for source_path, static_paths in static_paths_by_source.items()
        if any(
            static_path == contract_root
            or static_path.startswith(f"{contract_root}/")
            or f"{contract_root}/" in static_path
            for static_path in static_paths
            for contract_root in contract_roots
        )
    }
    dependencies: dict[str, set[str]] = {}
    for source_path, tree in trees.items():
        referenced_sources = _python_import_dependencies(tree, module_paths)
        for static_path in static_paths_by_source[source_path]:
            referenced_sources.update(
                candidate
                for candidate in source_paths
                if candidate != source_path
                and (
                    static_path == candidate
                    or f"{candidate}" in static_path
                )
            )
        dependencies[source_path] = referenced_sources

    discovered = set(direct_references)
    while True:
        dependents = {
            source_path
            for source_path, referenced_sources in dependencies.items()
            if referenced_sources & discovered
        }
        expanded = discovered | dependents
        if expanded == discovered:
            break
        discovered = expanded
    return tuple(sorted(discovered))


def assert_contract_reference_python_paths_are_registered(
    root: Path,
    configuration: dict[str, Any],
) -> tuple[str, ...]:
    """参照から導いた Python ファイルが宣言領域へ登録済みと示す。"""
    policy = _require_reference_discovery_policy(configuration)
    excluded = set(policy["declared_exclusions"]["paths"])
    candidates = tuple(
        path
        for path in derive_contract_reference_python_paths(root, configuration)
        if path not in excluded
    )
    areas = configuration.get("areas")
    assert isinstance(areas, list)
    areas_by_id = {
        area.get("id"): area
        for area in areas
        if isinstance(area, dict) and isinstance(area.get("id"), str)
    }
    missing_by_area: dict[str, list[str]] = {}
    for area_id in policy["required_area_ids"]:
        area = areas_by_id.get(area_id)
        assert isinstance(area, dict), f"参照登録先の領域がない: {area_id}"
        patterns = area.get("paths")
        assert isinstance(patterns, list)
        missing = [
            candidate
            for candidate in candidates
            if not any(
                isinstance(pattern, str)
                and fnmatch.fnmatchcase(candidate, pattern)
                for pattern in patterns
            )
        ]
        if missing:
            missing_by_area[area_id] = missing
    assert missing_by_area == {}, f"契約参照 Python ファイルが未登録: {missing_by_area}"
    return candidates


def load_base_core_areas(
    root: Path = REPO,
    base_revision: str = AUTHZ_GUARD_BASE_REVISION,
) -> dict[str, Any]:
    """指定リポジトリの固定基準版 core-areas.json を Git から読む。"""
    value = json.loads(
        run_git(
            root,
            "show",
            f"{base_revision}:.claude/core-areas.json",
        ).stdout
    )
    assert isinstance(value, dict)
    return value


def load_core_guard_module(
    script_path: Path = SCRIPT,
    *,
    module_name: str = "core_guard_module",
) -> Any:
    """指定した core_guard.py を照合関数の正として読み込む。

    Args:
        script_path: 読み込む検査器のパス。
        module_name: importlibへ登録する一意なモジュール名。
    """
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_AUDIT_PATHS_MARKER = "__CORE_GUARD_AUDIT_PATHS__="
_AUDIT_RUNNER = f"""
import json
import os
import runpy
import sys

opened_paths = []


def record_open(event, arguments):
    if event != "open" or not arguments:
        return
    try:
        path = os.fsdecode(os.fspath(arguments[0]))
    except TypeError:
        return
    opened_paths.append(path)


sys.addaudithook(record_open)
script = sys.argv[1]
root = sys.argv[2]
sys.path.insert(0, os.path.dirname(script))
sys.argv = [script, "--root", root]
try:
    runpy.run_path(script, run_name="__main__")
except BaseException:
    pass
finally:
    sys.__stdout__.write(
        "\\n{_AUDIT_PATHS_MARKER}" + json.dumps(opened_paths) + "\\n"
    )
"""


def _checker_opened_paths(root: Path, checker: Path) -> set[str]:
    """子プロセスの監査イベントから検査器が開いたパスを返す。

    Args:
        root: 判定対象ツリーのルート。
        checker: 実行する検査器。

    Returns:
        root 配下で開かれたファイルのルート相対パス。
    """
    result = subprocess.run(
        [sys.executable, "-c", _AUDIT_RUNNER, str(checker), str(root)],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    marker_index = result.stdout.rfind(_AUDIT_PATHS_MARKER)
    assert marker_index >= 0, (
        f"監査イベントの出力を取得できない: {checker}: {result.stderr}"
    )
    payload = result.stdout[marker_index + len(_AUDIT_PATHS_MARKER) :].splitlines()[0]
    opened_paths = json.loads(payload)
    assert isinstance(opened_paths, list)

    resolved_root = root.resolve()
    relative_paths: set[str] = set()
    for opened_path in opened_paths:
        if not isinstance(opened_path, str):
            continue
        candidate = Path(opened_path)
        if not candidate.is_absolute():
            candidate = resolved_root / candidate
        if not candidate.is_file():
            continue
        try:
            relative = candidate.resolve().relative_to(resolved_root)
        except ValueError:
            continue
        relative_paths.add(relative.as_posix())
    return relative_paths


def derive_authz_guard_candidate_paths(
    root: Path,
    base_revision: str = AUTHZ_GUARD_BASE_REVISION,
) -> list[str]:
    """基準版の領域または認可契約を開く検査器と名前の対を導出する。

    Args:
        root: 判定対象ツリーのルート。
        base_revision: core-areas.json を読む固定 Git revision。

    Returns:
        guard_paths の登録候補となるルート相対パス。
    """
    baseline = load_base_core_areas(root, base_revision)
    areas = baseline.get("areas")
    assert isinstance(areas, list)
    patterns = tuple(
        pattern
        for area in areas
        if isinstance(area, dict)
        for pattern in area.get("paths", [])
        if isinstance(pattern, str)
    )

    candidates: set[str] = set()
    for checker in sorted((root / "scripts").glob("check_*.py")):
        opened_paths = _checker_opened_paths(root, checker)
        if not any(
            opened_path.startswith("contracts/authz/")
            or any(
                fnmatch.fnmatchcase(opened_path, pattern)
                for pattern in patterns
            )
            for opened_path in opened_paths
        ):
            continue
        checker_path = checker.relative_to(root).as_posix()
        candidates.add(checker_path)
        paired_test = root / "tests" / f"test_{checker.name}"
        if paired_test.is_file():
            candidates.add(paired_test.relative_to(root).as_posix())
    return sorted(candidates)


def assert_authz_guard_candidates_are_registered(
    configuration: dict[str, Any],
) -> None:
    """実測で固定した認可検査器の全候補が guard_paths にあると示す。"""
    guard_paths = configuration.get("guard_paths")
    assert isinstance(guard_paths, list)
    missing = sorted(set(AUTHZ_GUARD_CANDIDATE_PATHS) - set(guard_paths))
    assert missing == [], f"guard_paths に未登録の認可検査資産: {missing}"


def expected_authz_guard_paths() -> frozenset[str]:
    """固定基準版と認可検査資産の追加集合から guard_paths を導出する。"""
    baseline_guard_paths = load_base_core_areas().get("guard_paths")
    assert isinstance(baseline_guard_paths, list)
    assert all(isinstance(path, str) for path in baseline_guard_paths)
    return frozenset(baseline_guard_paths) | frozenset(AUTHZ_GUARD_PATH_ADDITIONS)


def assert_authz_guard_paths_are_exact(configuration: dict[str, Any]) -> None:
    """現設定の guard_paths が固定基準版と認可追加の和に一致すると示す。"""
    guard_paths = configuration.get("guard_paths")
    assert isinstance(guard_paths, list)
    expected = expected_authz_guard_paths()
    actual = set(guard_paths)
    assert actual == expected, (
        "guard_paths が固定基準版と認可追加の和集合に不一致: "
        f"不足={sorted(expected - actual)}, 余分={sorted(actual - expected)}"
    )
    assert len(guard_paths) == len(actual), "guard_paths に重複がある"


def assert_authz_tenant_area_patterns_are_registered(
    configuration: dict[str, Any],
) -> None:
    """追加対象のパターンが tenant-isolation に全件あると示す。"""
    areas = configuration.get("areas")
    assert isinstance(areas, list)
    tenant_area = next(
        area
        for area in areas
        if isinstance(area, dict) and area.get("id") == "tenant-isolation"
    )
    tenant_paths = tenant_area.get("paths")
    assert isinstance(tenant_paths, list)
    missing = sorted(set(AUTHZ_TENANT_AREA_PATH_ADDITIONS) - set(tenant_paths))
    assert missing == [], f"tenant-isolation.paths に未登録のパターン: {missing}"


def assert_reception_input_paths_are_registered(
    configuration: dict[str, Any],
) -> None:
    """同期受け取り境界の共通実装が両領域へ登録済みと示す。"""
    areas = configuration.get("areas")
    assert isinstance(areas, list)
    areas_by_id = {
        area.get("id"): area
        for area in areas
        if isinstance(area, dict) and isinstance(area.get("id"), str)
    }
    for area_id in RECEPTION_INPUT_AREA_IDS:
        area = areas_by_id.get(area_id)
        assert isinstance(area, dict)
        paths = area.get("paths")
        assert isinstance(paths, list)
        missing = sorted(set(RECEPTION_INPUT_AREA_PATHS) - set(paths))
        assert missing == [], (
            f"{area_id}.paths に未登録の receptionInput 資産: {missing}"
        )


def make_authz_guard_probe_repo(tmp_path: Path) -> tuple[Path, str]:
    """認可検査資産の導出を試す最小の合成ツリーを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。

    Returns:
        合成ツリーのルートと core-areas.json を固定した revision。
    """
    root = make_repo(tmp_path, core_paths=["backend/core/*"])
    write_text(root, "contracts/authz/probe.json", "{}\n")
    write_text(root, "backend/core/probe.txt", "core\n")
    base_revision = run_git(root, "rev-parse", "HEAD").stdout.strip()
    return root, base_revision


def write_authz_guard_probe(
    root: Path,
    *,
    checker_name: str,
    opened_path: str,
    with_pair: bool,
) -> None:
    """指定パスだけを開く合成検査器と任意の名前の対を作る。

    Args:
        root: 合成ツリーのルート。
        checker_name: `check_` から始まる検査器名。
        opened_path: 検査器が開くルート相対パス。
        with_pair: 名前の対となるテストも作るか。
    """
    write_text(
        root,
        f"scripts/{checker_name}",
        (
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "root = Path(sys.argv[sys.argv.index('--root') + 1])\n"
            f"(root / {opened_path!r}).read_text(encoding='utf-8')\n"
        ),
    )
    if with_pair:
        write_text(
            root,
            f"tests/test_{checker_name}",
            "def test_probe():\n    assert True\n",
        )


SCHEMA_CONTRACT_TOKENS = ("pitchlog.db", "schema-manifest", "migrations")


def _local_module_dependencies(
    path: Path, module_paths: dict[str, str]
) -> set[str]:
    """テスト補助モジュールへの import 依存をリポジトリ相対パスで返す。

    Args:
        path: 解析対象の Python ファイル。
        module_paths: モジュール名からリポジトリ相対パスへの対応。

    Returns:
        `backend/tests/` 配下にある依存先のリポジトリ相対パス。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module.split(".")[0])
    return {module_paths[name] for name in names if name in module_paths}


def schema_contract_test_paths() -> set[str]:
    """スキーマ契約に触れる `backend/tests/` の資産を走査で返す。

    ブランチの状態に依存しない規則で切る。版管理の差分を母集団にすると、
    マージ後の develop では差分が空になり検査が空洞化する(実測)。

    Returns:
        スキーマ契約を参照するテストと、それが import する補助モジュール。
    """
    test_root = REPO / "backend/tests"
    files = {
        path.relative_to(REPO).as_posix(): path
        for path in test_root.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    module_paths = {Path(name).stem: name for name in files}
    population = {
        name
        for name, path in files.items()
        if any(
            token in path.read_text(encoding="utf-8")
            for token in SCHEMA_CONTRACT_TOKENS
        )
    }
    while True:
        added = {
            dependency
            for name in population
            for dependency in _local_module_dependencies(
                files[name], module_paths
            )
        } - population
        if not added:
            return population
        population |= added


def schema_contract_asset_paths() -> list[str]:
    """スキーマ契約の実体とスキーマ契約テストを機械導出して返す。"""
    db_python_files = (REPO / "backend/src/pitchlog/db").rglob("*.py")
    migration_files = (
        path
        for path in (REPO / "backend/migrations").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    contract_files = (
        path
        for path in (REPO / "contracts/db").rglob("*")
        if path.is_file()
    )
    task_test_files = schema_contract_test_paths()
    return sorted(
        {
            *(
                path.relative_to(REPO).as_posix()
                for path in (
                    *db_python_files,
                    *migration_files,
                    *contract_files,
                )
            ),
            *task_test_files,
        }
    )


def assert_schema_contract_assets_are_registered(
    asset_paths: list[str], *, configured: Any | None = None
) -> None:
    """スキーマ契約の実体が実際の領域パターンへ全件一致することを検証する。"""
    core_guard = load_core_guard_module()
    if configured is None:
        configured = core_guard.load_core_areas(REPO)
    area_patterns_only = core_guard.CoreAreas(
        path_patterns=configured.path_patterns,
        guard_paths=frozenset(),
    )
    matched = set(core_guard.matched_paths(asset_paths, area_patterns_only))
    missing = sorted(set(asset_paths) - matched)
    assert missing == [], f"areas[].paths に未登録のスキーマ契約資産: {missing}"


def has_expected_data_model_registrations(configuration: dict[str, Any]) -> bool:
    """データモデル正本と検査資産が期待する集合へ登録済みか判定する。"""
    areas = configuration.get("areas")
    guard_paths = configuration.get("guard_paths")
    if not isinstance(areas, list) or not isinstance(guard_paths, list):
        return False

    paths_by_area: dict[str, set[str]] = {}
    for area in areas:
        if not isinstance(area, dict):
            return False
        area_id = area.get("id")
        paths = area.get("paths")
        if (
            not isinstance(area_id, str)
            or not isinstance(paths, list)
            or not all(isinstance(path, str) for path in paths)
        ):
            return False
        paths_by_area[area_id] = set(paths)

    return (
        all(
            DATA_MODEL_DOCUMENT_PATH in paths_by_area.get(area_id, set())
            for area_id in DATA_MODEL_AREA_IDS
        )
        and set(DATA_MODEL_GUARD_PATHS).issubset(set(guard_paths))
    )


def test_actual_config_registers_data_model_assets_in_expected_sets():
    configuration = load_actual_core_areas()

    assert has_expected_data_model_registrations(configuration)


def test_actual_config_registers_fixed_authz_guard_candidates():
    """実測済みの 18 パスがすべて guard_paths にあることを検証する。"""
    configuration = load_actual_core_areas()

    assert_authz_guard_candidates_are_registered(configuration)
    registered_additions = [
        path
        for path in configuration["guard_paths"]
        if path in AUTHZ_GUARD_PATH_ADDITIONS
    ]
    assert registered_additions == list(AUTHZ_GUARD_PATH_ADDITIONS)


def test_guard_paths_population_remains_unchanged():
    """guard_paths を固定基準版と認可追加の和集合で exact に閉じる。"""
    assert_authz_guard_paths_are_exact(load_actual_core_areas())


def test_guard_paths_reject_removal_and_same_size_replacement():
    """guard_paths の削除と同数置換が exact-set 検査で red になる。"""
    removed = min(expected_authz_guard_paths())

    missing = load_actual_core_areas()
    missing["guard_paths"].remove(removed)
    with pytest.raises(AssertionError, match="guard_paths .*和集合に不一致"):
        assert_authz_guard_paths_are_exact(missing)

    replaced = load_actual_core_areas()
    index = replaced["guard_paths"].index(removed)
    replaced["guard_paths"][index] = "tests/guard-path-replacement-probe.py"
    with pytest.raises(AssertionError, match="guard_paths .*和集合に不一致"):
        assert_authz_guard_paths_are_exact(replaced)


@pytest.mark.parametrize(
    "guard_path",
    AUTHZ_GUARD_CANDIDATE_PATHS,
    ids=AUTHZ_GUARD_CANDIDATE_PATHS,
)
def test_each_fixed_authz_guard_candidate_is_required(guard_path: str):
    """実測母集団の各要素を 1 件ずつ外すと登録検査が red になる。"""
    configuration = load_actual_core_areas()
    configuration["guard_paths"].remove(guard_path)

    with pytest.raises(AssertionError, match="guard_paths に未登録"):
        assert_authz_guard_candidates_are_registered(configuration)


def test_actual_config_registers_fixed_authz_tenant_patterns():
    """tenant-isolation への追加パターンを exact-set で検証する。"""
    configuration = load_actual_core_areas()

    assert_authz_tenant_area_patterns_are_registered(configuration)
    tenant_area = next(
        area
        for area in configuration["areas"]
        if area["id"] == "tenant-isolation"
    )
    registered_additions = [
        path
        for path in tenant_area["paths"]
        if path in AUTHZ_TENANT_AREA_PATH_ADDITIONS
    ]
    assert registered_additions == list(AUTHZ_TENANT_AREA_PATH_ADDITIONS)


@pytest.mark.parametrize(
    "path",
    AUTHZ_BACKEND_PREVIOUSLY_COVERED_PATHS,
    ids=AUTHZ_BACKEND_PREVIOUSLY_COVERED_PATHS,
)
def test_each_authz_backend_contract_file_matches_tenant_isolation(path: str):
    """追加した認可契約7件を実設定の tenant 領域だけで検出する。"""
    configuration = load_actual_core_areas()
    tenant_area = next(
        area
        for area in configuration["areas"]
        if area["id"] == "tenant-isolation"
    )
    core_guard = load_core_guard_module()
    tenant_only = core_guard.CoreAreas(
        path_patterns=tuple(tenant_area["paths"]),
        guard_paths=frozenset(),
    )

    assert core_guard.matched_paths([path], tenant_only) == [path]


def test_authz_backend_pattern_covers_current_and_future_without_overmatch():
    """認可テストの現集合・将来名を覆い、現追跡ファイルを過剰包含しない。"""
    tracked_files = run_git(REPO, "ls-files").stdout.splitlines()
    matches = tuple(
        path
        for path in tracked_files
        if fnmatch.fnmatchcase(path, AUTHZ_BACKEND_TEST_PATTERN)
    )
    expected_current = tuple(
        path
        for path in tracked_files
        if Path(path).parent == Path("backend/tests")
        and Path(path).name.startswith("test_authz")
        and Path(path).suffix == ".py"
    )
    assert matches == expected_current
    assert all(Path(path).parent == Path("backend/tests") for path in matches)
    previous_pattern = AUTHZ_BACKEND_TEST_PATTERN.replace(
        "test_authz*", "test_authz_*"
    )
    previous_matches = {
        path
        for path in tracked_files
        if fnmatch.fnmatchcase(path, previous_pattern)
    }
    assert previous_matches <= set(matches)
    assert len(matches) >= len(previous_matches)

    configuration = load_actual_core_areas()
    tenant_area = next(
        area
        for area in configuration["areas"]
        if area["id"] == "tenant-isolation"
    )
    core_guard = load_core_guard_module()
    tenant_only = core_guard.CoreAreas(
        path_patterns=tuple(tenant_area["paths"]),
        guard_paths=frozenset(),
    )
    future_path = "backend/tests/test_authz.py"
    assert core_guard.matched_paths([future_path], tenant_only) == [future_path]
    excluded_paths = (
        "backend/tests/test_authorization.py",
        "frontend/test_authz_x.py",
        "backend/tests/nested/test_authz_x.py",
        "backend/tests/test_health.py",
    )
    assert all(
        not fnmatch.fnmatchcase(path, AUTHZ_BACKEND_TEST_PATTERN)
        for path in excluded_paths
    )


@pytest.mark.parametrize(
    "pattern",
    AUTHZ_TENANT_AREA_PATH_ADDITIONS,
    ids=AUTHZ_TENANT_AREA_PATH_ADDITIONS,
)
def test_each_fixed_authz_tenant_pattern_is_required(pattern: str):
    """追加した各パターンを 1 件ずつ外すと登録検査が red になる。"""
    configuration = load_actual_core_areas()
    tenant_area = next(
        area
        for area in configuration["areas"]
        if area["id"] == "tenant-isolation"
    )
    tenant_area["paths"].remove(pattern)

    with pytest.raises(AssertionError, match="tenant-isolation.paths に未登録"):
        assert_authz_tenant_area_patterns_are_registered(configuration)


@pytest.mark.parametrize(
    "pattern",
    AUTHZ_TENANT_AREA_PATH_ADDITIONS,
    ids=AUTHZ_TENANT_AREA_PATH_ADDITIONS,
)
def test_each_authz_tenant_pattern_matches_a_tracked_file(pattern: str):
    """追加した tenant-isolation パターンの空振りを拒否する。"""
    tracked_files = run_git(REPO, "ls-files").stdout.splitlines()

    matches = [
        path for path in tracked_files if fnmatch.fnmatchcase(path, pattern)
    ]
    assert matches, f"実在する追跡ファイルに一致しないパターン: {pattern}"


@pytest.mark.parametrize(
    ("pattern", "path"),
    TENANT_BOUNDARY_AREA_PATH_CASES,
    ids=TENANT_BOUNDARY_AREA_PATH_ADDITIONS,
)
def test_each_tenant_boundary_path_matches_tenant_isolation(
    pattern: str,
    path: str,
) -> None:
    """強制点を変え得る各パスを tenant 領域の paths だけで検出する。"""
    configuration = load_actual_core_areas()
    tenant_area = next(
        area for area in configuration["areas"] if area["id"] == "tenant-isolation"
    )
    assert pattern in tenant_area["paths"]
    core_guard = load_core_guard_module()
    tenant_only = core_guard.CoreAreas(
        path_patterns=tuple(tenant_area["paths"]),
        guard_paths=frozenset(),
    )

    assert core_guard.matched_paths([path], tenant_only) == [path]


@pytest.mark.parametrize(
    ("pattern", "path"),
    TENANT_BOUNDARY_AREA_PATH_CASES,
    ids=TENANT_BOUNDARY_AREA_PATH_ADDITIONS,
)
def test_each_tenant_boundary_path_removal_is_red(
    pattern: str,
    path: str,
) -> None:
    """各追加パターンを外すと対応パスのコア判定が red になる。"""
    configuration = load_actual_core_areas()
    tenant_area = next(
        area for area in configuration["areas"] if area["id"] == "tenant-isolation"
    )
    tenant_area["paths"].remove(pattern)
    core_guard = load_core_guard_module()
    tenant_only = core_guard.CoreAreas(
        path_patterns=tuple(tenant_area["paths"]),
        guard_paths=frozenset(),
    )

    with pytest.raises(AssertionError, match="コア判定から外れた"):
        assert core_guard.matched_paths([path], tenant_only) == [path], (
            f"コア判定から外れた: {path}"
        )


@pytest.mark.parametrize("area_id", RECEPTION_INPUT_AREA_IDS)
@pytest.mark.parametrize("path", RECEPTION_INPUT_AREA_PATHS)
def test_reception_input_matches_each_owning_area_without_guard_paths(
    area_id: str,
    path: str,
):
    """共通実装の対を各所有領域の paths だけで検出する。"""
    configuration = load_actual_core_areas()
    area = next(item for item in configuration["areas"] if item["id"] == area_id)
    core_guard = load_core_guard_module()
    area_only = core_guard.CoreAreas(
        path_patterns=tuple(area["paths"]),
        guard_paths=frozenset(),
    )

    assert core_guard.matched_paths([path], area_only) == [path]


@pytest.mark.parametrize("area_id", RECEPTION_INPUT_AREA_IDS)
@pytest.mark.parametrize("path", RECEPTION_INPUT_AREA_PATHS)
def test_reception_input_registration_rejects_each_missing_area_path(
    area_id: str,
    path: str,
):
    """両領域の各 registration を 1 件ずつ外すと red になる。"""
    configuration = load_actual_core_areas()
    area = next(item for item in configuration["areas"] if item["id"] == area_id)
    area["paths"].remove(path)

    with pytest.raises(AssertionError, match="未登録の receptionInput 資産"):
        assert_reception_input_paths_are_registered(configuration)


@pytest.mark.parametrize(
    ("checker_name", "opened_path", "with_pair", "expected_delta"),
    (
        (
            "check_contract_probe.py",
            "contracts/authz/probe.json",
            True,
            2,
        ),
        (
            "check_core_area_probe.py",
            "backend/core/probe.txt",
            True,
            2,
        ),
        (
            "check_unpaired_probe.py",
            "contracts/authz/probe.json",
            False,
            1,
        ),
    ),
)
def test_authz_guard_candidate_derivation_is_complete_for_each_branch(
    tmp_path: Path,
    checker_name: str,
    opened_path: str,
    with_pair: bool,
    expected_delta: int,
):
    """述語の 2 入力分岐と名前の対の有無を独立した探針で検証する。"""
    root, base_revision = make_authz_guard_probe_repo(tmp_path)
    baseline = derive_authz_guard_candidate_paths(root, base_revision)
    write_authz_guard_probe(
        root,
        checker_name=checker_name,
        opened_path=opened_path,
        with_pair=with_pair,
    )

    candidates = derive_authz_guard_candidate_paths(root, base_revision)

    assert baseline == []
    assert len(candidates) == len(baseline) + expected_delta
    assert f"scripts/{checker_name}" in candidates
    paired_path = f"tests/test_{checker_name}"
    assert (paired_path in candidates) is with_pair


def test_copied_actual_config_rejects_one_missing_data_model_path(tmp_path):
    original_bytes = CORE_AREAS_PATH.read_bytes()
    copied_path = tmp_path / "core-areas.json"
    copied_path.write_bytes(original_bytes)
    configuration = json.loads(copied_path.read_text(encoding="utf-8"))
    area = next(
        item for item in configuration["areas"] if item["id"] == "game-state"
    )
    area["paths"].remove(DATA_MODEL_DOCUMENT_PATH)
    copied_path.write_text(
        json.dumps(configuration, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    copied_configuration = json.loads(copied_path.read_text(encoding="utf-8"))
    assert CORE_AREAS_PATH.read_bytes() == original_bytes
    assert not has_expected_data_model_registrations(copied_configuration)


def test_actual_core_area_paths_follow_merge_base_layers():
    """マージ作業ツリーを取り込み後の比較元 blob と突合する。"""
    core_guard = load_core_guard_module()
    base_sha = run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(REPO, base_sha)
    candidate = load_actual_core_areas()
    baseline_ids = {area["id"] for area in baseline["areas"]}
    declared_ids = set(core_guard.AREA_PATH_ADDITIONS)
    stationary_ids = baseline_ids - declared_ids

    assert len(baseline_ids) == len(baseline["areas"]), "コア領域 ID が重複している"
    assert len(baseline_ids) == 5
    assert declared_ids <= baseline_ids
    assert stationary_ids | declared_ids == baseline_ids
    assert declared_ids == set(EXPECTED_AREA_PATH_ADDITIONS)
    core_guard.validate_area_path_layers(baseline, candidate)


def test_merge_base_blob_is_used_instead_of_pr_base_tip(tmp_path: Path):
    """base ブランチ先端が動いても分岐点の blob を比較元にする。"""
    core_guard = load_core_guard_module()
    root, original_base = make_layered_core_repo(tmp_path)
    run_git(root, "branch", "feature", original_base)
    target_tip = commit_area_path_changes(
        root,
        {"sync-protocol": ("base-branch-only.py",)},
    )
    run_git(root, "checkout", "-q", "feature")
    feature_head = run_git(root, "rev-parse", "HEAD").stdout.strip()

    used_revision = core_guard.verify_area_path_baseline(
        root,
        target_tip,
        feature_head,
    )

    assert used_revision == original_base
    assert used_revision != target_tip


def test_each_area_becomes_stationary_when_omitted_from_declaration(
    tmp_path: Path,
):
    """回転後に宣言から外れた各領域を据え置き層として固定する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = json.loads(json.dumps(baseline))
    baseline_ids = {area["id"] for area in baseline["areas"]}
    assert dict(core_guard.AREA_PATH_ADDITIONS) == EXPECTED_AREA_PATH_ADDITIONS
    declared = dict(core_guard.AREA_PATH_ADDITIONS)
    declared_ids = set(declared)
    attempts = 0

    assert len(baseline_ids) == len(baseline["areas"]) == 5
    assert declared_ids <= baseline_ids
    for area_id in sorted(baseline_ids - declared_ids):
        mutated = json.loads(json.dumps(candidate))
        area = next(item for item in mutated["areas"] if item["id"] == area_id)
        area["paths"].append("unregistered/probe.py")
        with pytest.raises(core_guard.GuardError, match=rf"{area_id}\.paths"):
            core_guard.validate_area_path_layers(
                baseline, mutated, declared
            )
        attempts += 1

    assert attempts == len(baseline_ids - declared_ids)


def test_change_absent_from_declared_addition_layer_is_rejected(tmp_path: Path):
    """追加対象領域でも追加層に無いパスを拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    declared = dict(core_guard.AREA_PATH_ADDITIONS)
    area_id = next(iter(declared))
    head_sha = commit_area_path_changes(
        root,
        {area_id: (*declared[area_id], "unregistered/probe.py")},
    )

    with pytest.raises(core_guard.GuardError, match=rf"{area_id}\.paths"):
        core_guard.verify_area_path_baseline(root, base_sha, head_sha)


def test_deleting_baseline_tenant_path_is_rejected(tmp_path: Path) -> None:
    """比較元にある tenant パスを削った候補を拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = json.loads(json.dumps(baseline))
    tenant_area = next(
        area for area in candidate["areas"] if area["id"] == "tenant-isolation"
    )
    tenant_area["paths"].remove("base/tenant-isolation.py")
    tenant_area["paths"].extend(UF5_TEAM_AREA_PATH_ADDITIONS)

    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(
            baseline, candidate, UF5_AREA_PATH_ADDITIONS
        )


def test_json_and_expected_literal_cochange_cannot_redefine_baseline(tmp_path: Path):
    """03c41ca 型の JSON と期待値の共変更を merge-base 基線で拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    head_sha = commit_area_path_changes(
        root,
        {"sync-protocol": ("same-line.py",)},
        cochanged_paths=("tests/test_core_guard.py",),
    )

    with pytest.raises(core_guard.GuardError, match="sync-protocol.paths"):
        core_guard.verify_area_path_baseline(root, base_sha, head_sha)


def test_json_expected_and_anchor_cochange_is_rejected(tmp_path: Path):
    """親に追加層の定義があれば JSON・期待値・アンカーの共変更を拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    head_sha = commit_area_path_changes(
        root,
        dict(core_guard.AREA_PATH_ADDITIONS),
        cochanged_paths=(
            "scripts/core_guard.py",
            "tests/test_core_guard.py",
        ),
    )

    with pytest.raises(core_guard.GuardError, match="同一コミット"):
        core_guard.verify_area_path_baseline(root, base_sha, head_sha)


def test_cochange_before_area_path_additions_is_accepted(tmp_path: Path):
    """親に追加層の定義がなければ当時の JSON と期待値の共変更を受理する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(
        tmp_path, has_area_path_additions=False
    )
    head_sha = commit_area_path_changes(
        root,
        dict(core_guard.AREA_PATH_ADDITIONS),
        cochanged_paths=("scripts/core_guard.py", "tests/test_core_guard.py"),
    )

    assert core_guard.verify_area_path_baseline(root, base_sha, head_sha) == base_sha


def test_parent_without_core_guard_does_not_activate_cochange_rule(tmp_path: Path):
    """ルートと親に core_guard.py がないコミットには規則を適用しない。"""
    core_guard = load_core_guard_module()
    root = make_repo(tmp_path)
    base_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    write_text(root, "scripts/core_guard.py", "AREA_PATH_ADDITIONS = {}\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "add guard",
    )
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()

    assert not core_guard._parent_has_area_path_additions(root, base_sha)
    assert not core_guard._parent_has_area_path_additions(root, head_sha)


def test_merge_checks_all_parents_but_diff_tree_remains_empty(tmp_path: Path):
    """複数親のどれかに定義があれば認識し、通常のマージ差分は空のまま扱う。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(
        tmp_path, has_area_path_additions=False
    )
    write_text(root, "scripts/core_guard.py", "AREA_PATH_ADDITIONS = {}\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "add layer definition",
    )
    run_git(root, "branch", "with-definition")
    run_git(root, "reset", "--hard", base_sha)
    write_text(root, "other.txt", "other branch\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "other branch",
    )
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "merge",
        "-q",
        "--no-ff",
        "-s",
        "ours",
        "with-definition",
        "-m",
        "merge",
    )
    merge_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()

    assert core_guard._parent_has_area_path_additions(root, merge_sha)
    assert core_guard._changed_paths_in_commit(root, merge_sha) == frozenset()
    assert core_guard.verify_area_path_baseline(root, base_sha, merge_sha) == base_sha


def test_registered_addition_layer_passes_in_a_separate_commit(tmp_path: Path):
    """据え置き層と宣言済み追加層だけから成る変更が実際に通る。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    head_sha = commit_area_path_changes(
        root,
        dict(core_guard.AREA_PATH_ADDITIONS),
    )

    used_revision = core_guard.verify_area_path_baseline(root, base_sha, head_sha)

    assert used_revision == base_sha


def test_stage_a_startup_declaration_keeps_json_baseline_stationary() -> None:
    """実基線と実JSONの二領域に起動入口の登録が残る。"""
    core_guard = load_core_guard_module()
    baseline = core_guard.load_core_areas_at_revision(
        REPO, run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    )
    configuration = load_actual_core_areas()
    startup = "backend/src/pitchlog/db/stage_a_startup.py"

    assert core_guard.AREA_PATH_ADDITIONS["game-state"] == (startup,)
    assert core_guard.AREA_PATH_ADDITIONS["tenant-isolation"] == (
        "backend/src/pitchlog/services/game_creation.py",
        "backend/tests/test_game_preparing*.py",
    )
    for document in (baseline, configuration):
        for area in document["areas"]:
            if area["id"] in ("game-state", "tenant-isolation"):
                assert area["paths"].count(startup) == 1
    core_guard.validate_area_path_layers(baseline, configuration)


def test_stage_a_startup_registration_and_later_rotation(tmp_path: Path) -> None:
    """起動入口は二領域に一致し、後続宣言は登録済み層を残さず回転する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = json.loads(json.dumps(baseline))
    startup = "backend/src/pitchlog/db/stage_a_startup.py"
    stage_additions: dict[str, tuple[str, ...]] = {
        "game-state": (startup,),
        "tenant-isolation": (startup,),
    }
    test_path = "backend/tests/test_rule_resolution.py"
    for area in candidate["areas"]:
        if area["id"] in ("game-state", "tenant-isolation"):
            area["paths"].append(startup)

    core_guard.validate_area_path_layers(baseline, candidate, stage_additions)
    assert all(
        core_guard.matched_paths(
            (startup,),
            core_guard.CoreAreas(
                path_patterns=tuple(area["paths"]), guard_paths=frozenset()
            ),
        )
        for area in candidate["areas"]
        if area["id"] in ("game-state", "tenant-isolation")
    )

    # 一領域ずつの登録は各領域の独立した追加層であり、部分追加ではない。
    one_area = json.loads(json.dumps(baseline))
    next(area for area in one_area["areas"] if area["id"] == "game-state")[
        "paths"
    ].append(startup)
    core_guard.validate_area_path_layers(baseline, one_area, stage_additions)

    invalid = json.loads(json.dumps(candidate))
    next(area for area in invalid["areas"] if area["id"] == "tenant-isolation")[
        "paths"
    ].append("backend/src/pitchlog/db/unregistered.py")
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(baseline, invalid, stage_additions)

    rotated = json.loads(json.dumps(candidate))
    for area in rotated["areas"]:
        if area["id"] in ("game-state", "tenant-isolation"):
            area["paths"].append(test_path)
    rotated_declaration = {
        "game-state": (test_path,),
        "tenant-isolation": (test_path,),
    }
    core_guard.validate_area_path_layers(candidate, rotated, rotated_declaration)
    with pytest.raises(core_guard.GuardError, match="game-state.paths"):
        core_guard.validate_area_path_layers(candidate, rotated)


def test_stage_a_startup_actual_registration_requires_human_check(
    tmp_path: Path,
) -> None:
    """登録済み起動入口は実JSONでも未記入の逐行確認を拒否する。"""
    startup = "backend/src/pitchlog/db/stage_a_startup.py"
    areas = {area["id"]: area for area in load_actual_core_areas()["areas"]}
    assert all(
        areas[area_id]["paths"].count(startup) == 1
        for area_id in ("game-state", "tenant-isolation")
    )
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_change(root, startup)
    event_path = write_event(tmp_path, base_sha, head_sha, f"- [ ] {REQUIRED_CHECK_TEXT}")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert startup in result.stderr
    assert f"- [x] {REQUIRED_CHECK_TEXT}" in result.stderr


def test_addition_layer_requires_complete_declared_suffix(tmp_path: Path) -> None:
    """複数件の追加層が基線の末尾に宣言順で続く場合だけ受理する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    base_area = next(
        area for area in baseline["areas"] if area["id"] == "tenant-isolation"
    )
    base_area["paths"].append("base/second.py")
    candidate = json.loads(json.dumps(baseline))
    area = next(area for area in candidate["areas"] if area["id"] == "tenant-isolation")
    additions = UM1_TENANT_AREA_PATH_ADDITIONS
    declared = {"tenant-isolation": additions}
    area["paths"] = [*base_area["paths"], *additions]

    core_guard.validate_area_path_layers(baseline, candidate, declared)
    for changed_paths in (
        [base_area["paths"][1], base_area["paths"][0], *additions],
        [additions[0], *base_area["paths"], *additions[1:]],
        [base_area["paths"][0], additions[0], base_area["paths"][1], *additions[1:]],
        [*base_area["paths"], additions[1], additions[0], *additions[2:]],
        [*base_area["paths"], *additions[:-1]],
    ):
        mutated = json.loads(json.dumps(candidate))
        mutated_area = next(
            item for item in mutated["areas"] if item["id"] == "tenant-isolation"
        )
        mutated_area["paths"] = changed_paths
        with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
            core_guard.validate_area_path_layers(baseline, mutated, declared)


def test_tenant_declaration_accepts_json_before_registration(tmp_path: Path) -> None:
    """隔離履歴で未登録、宣言、登録、後続登録の順に受理する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    assert core_guard.verify_area_path_baseline(root, base_sha, base_sha) == base_sha

    write_text(
        root,
        "scripts/core_guard.py",
        core_guard_source_with_additions(UF5_AREA_PATH_ADDITIONS),
    )
    run_git(root, "add", "scripts/core_guard.py")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "declaration only",
    )
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    uf5_core_guard = load_core_guard_module(
        root / "scripts" / "core_guard.py",
        module_name="uf5_isolated_core_guard",
    )
    baseline = uf5_core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = uf5_core_guard.load_core_areas_at_revision(root, head_sha)

    assert candidate == baseline
    tenant_area = next(
        area for area in candidate["areas"] if area["id"] == "tenant-isolation"
    )
    assert tenant_area["paths"] == ["base/tenant-isolation.py"]
    assert dict(uf5_core_guard.AREA_PATH_ADDITIONS) == UF5_AREA_PATH_ADDITIONS
    uf5_core_guard.validate_area_path_layers(baseline, candidate)
    assert (
        uf5_core_guard.verify_area_path_baseline(root, base_sha, head_sha) == base_sha
    )

    registered_sha = commit_area_path_changes(root, UF5_AREA_PATH_ADDITIONS)
    registered = uf5_core_guard.load_core_areas_at_revision(root, registered_sha)
    for area in registered["areas"]:
        area_id = area["id"]
        expected_paths = [
            f"base/{area_id}.py",
            *UF5_AREA_PATH_ADDITIONS.get(area_id, ()),
        ]
        assert area["paths"] == expected_paths
    assert (
        uf5_core_guard.verify_area_path_baseline(root, base_sha, registered_sha)
        == base_sha
    )

    future_additions: dict[str, tuple[str, ...]] = {
        "tenant-isolation": ("future/tenant-entry*",),
        "data-migration": ("future/migration-entry*",),
    }
    write_text(
        root,
        "scripts/core_guard.py",
        core_guard_source_with_additions(future_additions),
    )
    run_git(root, "add", "scripts/core_guard.py")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "future declaration only",
    )
    future_core_guard = load_core_guard_module(
        root / "scripts" / "core_guard.py",
        module_name="future_isolated_core_guard",
    )
    future_sha = commit_area_path_changes(root, future_additions)
    future = future_core_guard.load_core_areas_at_revision(root, future_sha)
    assert (
        future_core_guard.verify_area_path_baseline(root, registered_sha, future_sha)
        == registered_sha
    )
    for area in future["areas"]:
        area_id = area["id"]
        paths = area["paths"]
        additions = UF5_AREA_PATH_ADDITIONS.get(area_id, ())
        if additions:
            assert_registered_block(paths, additions)
            assert tuple(paths[-len(future_additions[area_id]) :]) == future_additions[
                area_id
            ]

    with pytest.raises(uf5_core_guard.GuardError, match="tenant-isolation.paths"):
        uf5_core_guard.verify_area_path_baseline(
            root,
            registered_sha,
            future_sha,
        )


def test_current_declaration_accepts_json_after_stage_a_baseline(tmp_path: Path) -> None:
    """二領域の起動入口登録後、JSON据置き宣言とtenant追加登録を受理する。"""
    core_guard = load_core_guard_module()
    root, initial_sha = make_layered_core_repo(tmp_path)
    startup = "backend/src/pitchlog/db/stage_a_startup.py"
    stage_additions: dict[str, tuple[str, ...]] = {
        "game-state": (startup,),
        "tenant-isolation": (startup,),
    }
    write_text(
        root,
        "scripts/core_guard.py",
        core_guard_source_with_additions(stage_additions),
    )
    run_git(root, "add", "scripts/core_guard.py")
    run_git(
        root,
        "-c", "user.email=test@example.com", "-c", "user.name=test",
        "commit", "-qm", "stage_a declaration",
    )
    base_sha = commit_area_path_changes(root, stage_additions)
    stage_core_guard = load_core_guard_module(
        root / "scripts/core_guard.py", module_name="stage_a_isolated_core_guard"
    )
    assert stage_core_guard.verify_area_path_baseline(root, initial_sha, base_sha) == (
        initial_sha
    )

    write_text(root, "scripts/core_guard.py", SCRIPT.read_text(encoding="utf-8"))
    run_git(root, "add", "scripts/core_guard.py")
    run_git(
        root,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "declaration only",
    )
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = core_guard.load_core_areas_at_revision(root, head_sha)

    assert candidate == baseline
    tenant_area = next(
        area for area in candidate["areas"] if area["id"] == "tenant-isolation"
    )
    game_area = next(area for area in candidate["areas"] if area["id"] == "game-state")
    assert tenant_area["paths"] == ["base/tenant-isolation.py", startup]
    assert game_area["paths"] == ["base/game-state.py", startup]
    assert dict(core_guard.AREA_PATH_ADDITIONS) == EXPECTED_AREA_PATH_ADDITIONS
    core_guard.validate_area_path_layers(baseline, candidate)
    assert core_guard.verify_area_path_baseline(root, base_sha, head_sha) == base_sha

    registered_sha = commit_area_path_changes(
        root, {"tenant-isolation": EXPECTED_AREA_PATH_ADDITIONS["tenant-isolation"]}
    )
    registered = core_guard.load_core_areas_at_revision(root, registered_sha)
    for area in registered["areas"]:
        area_id = area["id"]
        assert area["paths"] == [
            f"base/{area_id}.py",
            *stage_additions.get(area_id, ()),
            *(
                EXPECTED_AREA_PATH_ADDITIONS["tenant-isolation"]
                if area_id == "tenant-isolation"
                else ()
            ),
        ]
    assert core_guard.verify_area_path_baseline(root, base_sha, registered_sha) == (
        base_sha
    )

    partial = json.loads(json.dumps(candidate))
    next(area for area in partial["areas"] if area["id"] == "tenant-isolation")[
        "paths"
    ].append(EXPECTED_AREA_PATH_ADDITIONS["tenant-isolation"][0])
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(baseline, partial)

    undeclared = json.loads(json.dumps(candidate))
    next(area for area in undeclared["areas"] if area["id"] == "tenant-isolation")[
        "paths"
    ].append("backend/src/pitchlog/services/unregistered.py")
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(baseline, undeclared)

    future = json.loads(json.dumps(registered))
    next(area for area in future["areas"] if area["id"] == "tenant-isolation")[
        "paths"
    ].append("future/tenant-entry.py")
    core_guard.validate_area_path_layers(
        registered, future, {"tenant-isolation": ("future/tenant-entry.py",)}
    )
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(registered, future)


def test_preparing_declaration_detects_new_paths_and_requires_human_check(
    tmp_path: Path,
) -> None:
    """隔離履歴で宣言前後の検出と登録後の逐行確認を検証する。"""
    core_guard = load_core_guard_module()
    root, _ = make_layered_core_repo(tmp_path)
    startup = "backend/src/pitchlog/db/stage_a_startup.py"
    stage_additions: dict[str, tuple[str, ...]] = {
        "game-state": (startup,),
        "tenant-isolation": (startup,),
    }
    base_sha = commit_area_path_changes(root, stage_additions)
    additions = EXPECTED_AREA_PATH_ADDITIONS["tenant-isolation"]
    planned_paths = (
        "backend/src/pitchlog/services/game_creation.py",
        "backend/tests/test_game_preparing_components.py",
    )
    write_text(root, "scripts/core_guard.py", SCRIPT.read_text(encoding="utf-8"))
    run_git(root, "add", "scripts/core_guard.py")
    run_git(
        root,
        "-c", "user.email=test@example.com", "-c", "user.name=test",
        "commit", "-qm", "preparing declaration",
    )
    declaration_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    declared = core_guard.load_core_areas_at_revision(root, declaration_sha)
    assert declared == baseline
    core_guard.validate_area_path_layers(baseline, declared)
    assert core_guard.verify_area_path_baseline(root, base_sha, declaration_sha) == base_sha
    tenant = next(area for area in declared["areas"] if area["id"] == "tenant-isolation")
    assert tenant["paths"] == ["base/tenant-isolation.py", startup]
    assert core_guard.matched_paths(
        planned_paths, core_guard.CoreAreas(tuple(tenant["paths"]), frozenset())
    ) == []

    registered_sha = commit_area_path_changes(root, {"tenant-isolation": additions})
    registered = core_guard.load_core_areas_at_revision(root, registered_sha)
    core_guard.validate_area_path_layers(baseline, registered)
    assert core_guard.verify_area_path_baseline(root, base_sha, registered_sha) == base_sha
    registered_tenant = next(
        area for area in registered["areas"] if area["id"] == "tenant-isolation"
    )
    assert registered_tenant["paths"] == ["base/tenant-isolation.py", startup, *additions]
    registered_paths = core_guard.CoreAreas(tuple(registered_tenant["paths"]), frozenset())
    assert core_guard.matched_paths(planned_paths, registered_paths) == list(planned_paths)

    _, product_sha = commit_changes(root, planned_paths)
    event = write_event(tmp_path, registered_sha, product_sha, f"- [ ] {REQUIRED_CHECK_TEXT}")
    result = run_guard(root, event_name="pull_request", event_path=event)
    assert result.returncode == 1
    assert all(f"{path}: PR 本文に必須チェックがない" in result.stderr for path in planned_paths)
    event = write_event(tmp_path, registered_sha, product_sha, f"- [x] {REQUIRED_CHECK_TEXT}")
    result = run_guard(root, event_name="pull_request", event_path=event)
    assert result.returncode == 0, result.stderr

    future_additions: dict[str, tuple[str, ...]] = {
        "tenant-isolation": ("future/tenant-entry.py",)
    }
    write_text(
        root,
        "scripts/core_guard.py",
        core_guard_source_with_additions(future_additions),
    )
    run_git(root, "add", "scripts/core_guard.py")
    run_git(
        root,
        "-c", "user.email=test@example.com", "-c", "user.name=test",
        "commit", "-qm", "later declaration",
    )
    future_declaration_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    future_core_guard = load_core_guard_module(
        root / "scripts/core_guard.py", module_name="future_preparing_core_guard"
    )
    assert future_core_guard.load_core_areas_at_revision(
        root, future_declaration_sha
    ) == registered
    assert future_core_guard.verify_area_path_baseline(
        root, product_sha, future_declaration_sha
    ) == product_sha
    future_registered_sha = commit_area_path_changes(root, future_additions)
    future_registered = future_core_guard.load_core_areas_at_revision(
        root, future_registered_sha
    )
    assert future_core_guard.verify_area_path_baseline(
        root, product_sha, future_registered_sha
    ) == product_sha
    future_tenant = next(
        area for area in future_registered["areas"] if area["id"] == "tenant-isolation"
    )
    assert future_tenant["paths"] == [
        "base/tenant-isolation.py",
        startup,
        *additions,
        *future_additions["tenant-isolation"],
    ]
    assert core_guard.matched_paths(
        planned_paths, core_guard.CoreAreas(tuple(future_tenant["paths"]), frozenset())
    ) == list(planned_paths)


def test_sync_apply_additions_declared_for_other_area_are_rejected(tmp_path: Path) -> None:
    """別領域に同じ追加層を宣言しても tenant の変更を拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    head_sha = commit_area_path_changes(
        root, {"tenant-isolation": US1_SYNC_APPLY_AREA_PATH_ADDITIONS}
    )

    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = core_guard.load_core_areas_at_revision(root, head_sha)
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(
            baseline, candidate, EXPECTED_AREA_PATH_ADDITIONS
        )


def test_tenant_additions_declared_for_other_area_are_rejected(tmp_path: Path) -> None:
    """別領域に同じ追加層を宣言しても tenant の変更を拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    head_sha = commit_area_path_changes(
        root, {"tenant-isolation": UF6_TENANT_AREA_PATH_ADDITIONS}
    )
    declared = dict(UF5_AREA_PATH_ADDITIONS)
    declared.pop("tenant-isolation")
    declared["recording-rights"] = UF6_TENANT_AREA_PATH_ADDITIONS

    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = core_guard.load_core_areas_at_revision(root, head_sha)
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(baseline, candidate, declared)


def test_one_of_seven_tenant_additions_declared_is_rejected(tmp_path: Path) -> None:
    """複数件の宣言に対して 1 件だけの部分追加を拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    head_sha = commit_area_path_changes(
        root, {"tenant-isolation": UM1_TENANT_AREA_PATH_ADDITIONS[:1]}
    )

    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = core_guard.load_core_areas_at_revision(root, head_sha)
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(
            baseline, candidate, {"tenant-isolation": UM1_TENANT_AREA_PATH_ADDITIONS}
        )


def test_reordered_tenant_additions_are_rejected(tmp_path: Path) -> None:
    """複数件の宣言順を変えると計画順の paths を拒否する。"""
    core_guard = load_core_guard_module()
    root, base_sha = make_layered_core_repo(tmp_path)
    head_sha = commit_area_path_changes(
        root,
        {"tenant-isolation": tuple(reversed(UM1_TENANT_AREA_PATH_ADDITIONS))},
    )

    baseline = core_guard.load_core_areas_at_revision(root, base_sha)
    candidate = core_guard.load_core_areas_at_revision(root, head_sha)
    with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
        core_guard.validate_area_path_layers(
            baseline, candidate, {"tenant-isolation": UM1_TENANT_AREA_PATH_ADDITIONS}
        )


def test_product_rls_paths_remain_in_develop_baseline() -> None:
    """着地済み RLS から U-F5 までの登録順を末尾に依存せず保つ。"""
    core_guard = load_core_guard_module()
    base_sha = run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(REPO, base_sha)
    configuration = load_actual_core_areas()
    registered_tail = (*PRODUCT_RLS_AREA_PATH_ADDITIONS, ADR_001_PATH)
    base_area = next(
        area for area in baseline["areas"] if area["id"] == "tenant-isolation"
    )
    current_area = next(
        area for area in configuration["areas"] if area["id"] == "tenant-isolation"
    )
    base_paths = tuple(base_area["paths"])
    current_paths = tuple(current_area["paths"])
    registered_blocks = (
        registered_tail,
        UM1_TENANT_AREA_PATH_ADDITIONS,
        UF2_AUTH_STORE_AREA_PATH_ADDITIONS,
        UF6_TENANT_AREA_PATH_ADDITIONS,
        UF8_GAME_SCREEN_AREA_PATH_ADDITIONS,
        UF5_TEAM_AREA_PATH_ADDITIONS,
    )
    block_starts = tuple(
        assert_registered_block(current_paths, block) for block in registered_blocks
    )
    assert block_starts == tuple(sorted(block_starts))
    for block in registered_blocks:
        assert_registered_block(base_paths, block)
    core_guard.validate_area_path_layers(baseline, configuration)
    for pattern, planned_paths in zip(
        PRODUCT_RLS_AREA_PATH_ADDITIONS, PRODUCT_RLS_PATTERN_EXAMPLES, strict=True
    ):
        assert all(fnmatch.fnmatchcase(path, pattern) for path in planned_paths)

    tracked_files = run_git(REPO, "ls-files").stdout.splitlines()
    matches = tuple(
        tuple(path for path in tracked_files if fnmatch.fnmatchcase(path, pattern))
        for pattern in PRODUCT_RLS_AREA_PATH_ADDITIONS
    )
    assert all(
        path in PRODUCT_RLS_PLANNED_EXACT_PATHS
        or path.startswith(PRODUCT_RLS_PLANNED_DIRECTORY)
        for matched_paths in matches
        for path in matched_paths
    )
    # 比較元に登録済みの TSK-344 追跡集合。期待 node 資産も含む。
    assert matches == (
        ("docs/ops/product-rls-real-schema.md",),
        (
            "scripts/product_rls_real_schema/__init__.py",
            "scripts/product_rls_real_schema/expected-nodes-27ff94eb.txt",
            "scripts/product_rls_real_schema/runner.py",
        ),
        ("scripts/product-rls-real-schema-targets.json",),
    )


def test_uf2_auth_store_is_registered_in_actual_tenant_isolation() -> None:
    """実設定の tenant-isolation に U-F2 の authStore を登録済みと示す。"""
    configuration = load_actual_core_areas()
    tenant_area = next(
        area for area in configuration["areas"] if area["id"] == "tenant-isolation"
    )
    assert "frontend/src/stores/authStore*" in tenant_area["paths"]


def test_uf6_api_paths_are_registered_in_actual_core_areas() -> None:
    """U-F6 の2パターンを正しい3領域だけに一意に登録済みと示す。"""
    configuration = load_actual_core_areas()
    areas = {area["id"]: area for area in configuration["areas"]}
    expected_areas = {
        UF6_CLIENT_AREA_PATH_ADDITIONS[0]: {
            "sync-protocol",
            "recording-rights",
        },
        UF6_TENANT_AREA_PATH_ADDITIONS[0]: {"tenant-isolation"},
    }
    for pattern, owners in expected_areas.items():
        actual_owners = {
            area_id for area_id, area in areas.items() if pattern in area["paths"]
        }
        assert actual_owners == owners
        assert all(areas[area_id]["paths"].count(pattern) == 1 for area_id in owners)


def test_uf8_game_screen_paths_are_registered_in_all_areas() -> None:
    """比較元に登録済みの画面と spec を全領域で保持する。"""
    core_guard = load_core_guard_module()
    base_sha = run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(REPO, base_sha)
    candidate = load_actual_core_areas()
    pattern = UF8_GAME_SCREEN_AREA_PATH_ADDITIONS[0]
    screen_paths = (
        "frontend/src/screens/GameScreen.vue",
        "frontend/src/screens/GameScreen.spec.ts",
    )
    for base_area, area in zip(baseline["areas"], candidate["areas"], strict=True):
        assert area["id"] == base_area["id"]
        assert_registered_block(base_area["paths"], UF8_GAME_SCREEN_AREA_PATH_ADDITIONS)
        assert_registered_block(area["paths"], UF8_GAME_SCREEN_AREA_PATH_ADDITIONS)
        assert all(fnmatch.fnmatchcase(path, pattern) for path in screen_paths)

    assert core_guard.matched_paths(
        screen_paths, core_guard.load_core_areas(REPO)
    ) == list(screen_paths)
    core_guard.validate_area_path_layers(baseline, candidate)


def test_us1_sync_apply_paths_are_registered_in_both_areas() -> None:
    """U-S1の登録済み層を保ち、その後にRG1層だけを追加する。"""
    core_guard = load_core_guard_module()
    base_sha = run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(REPO, base_sha)
    configuration = load_actual_core_areas()
    base_areas = {area["id"]: area for area in baseline["areas"]}
    current_areas = {area["id"]: area for area in configuration["areas"]}
    representatives = (
        ("backend/src/pitchlog/sync/apply.py", US1_SYNC_APPLY_AREA_PATH_ADDITIONS[0]),
        (
            "backend/src/pitchlog/repositories/sync_apply.py",
            US1_SYNC_APPLY_AREA_PATH_ADDITIONS[1],
        ),
        ("backend/tests/test_sync_apply_entry.py", US1_SYNC_APPLY_AREA_PATH_ADDITIONS[2]),
        (
            "backend/tests/test_sync_apply_tenant_boundary.py",
            US1_SYNC_APPLY_AREA_PATH_ADDITIONS[2],
        ),
    )

    assert set(base_areas) == set(current_areas) == set(DATA_MODEL_AREA_IDS)
    for area_id in ("sync-protocol", "recording-rights"):
        paths = tuple(current_areas[area_id]["paths"])
        base_paths = tuple(base_areas[area_id]["paths"])
        assert_registered_block(base_paths, US1_SYNC_APPLY_AREA_PATH_ADDITIONS)
        assert_registered_block(paths, US1_SYNC_APPLY_AREA_PATH_ADDITIONS)
        assert_registered_block(base_paths, UR1_REGISTERED_PATHS[area_id])
        assert_registered_block(paths, UR1_REGISTERED_PATHS[area_id])
        assert paths == base_paths
        for path, pattern in representatives:
            assert pattern in paths
            assert fnmatch.fnmatchcase(path, pattern)
    for area_id in ("game-state", "tenant-isolation", "data-migration"):
        if area_id not in core_guard.AREA_PATH_ADDITIONS:
            assert current_areas[area_id]["paths"] == base_areas[area_id]["paths"]
    # 宣言済み追加だけを許し、据え置き層の削除・未宣言追加を拒否する。
    core_guard.validate_area_path_layers(baseline, configuration)


def test_uf5_team_paths_are_registered_for_tenant_and_migration() -> None:
    """U-F5 の製品6ファイルをT・Dだけへ宣言順で登録済みと示す。"""
    core_guard = load_core_guard_module()
    base_sha = run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(REPO, base_sha)
    candidate = load_actual_core_areas()
    expected_files = (
        "frontend/src/components/settings/TeamMembersContent.spec.ts",
        "frontend/src/components/settings/TeamMembersContent.vue",
        "frontend/src/lib/rosterQueryKeys.spec.ts",
        "frontend/src/lib/rosterQueryKeys.ts",
        "frontend/src/screens/TeamScreen.spec.ts",
        "frontend/src/screens/TeamScreen.vue",
    )

    assert set(UF5_AREA_PATH_ADDITIONS) == {
        "tenant-isolation",
        "data-migration",
    }
    baseline_areas = {area["id"]: area for area in baseline["areas"]}
    candidate_areas = {area["id"]: area for area in candidate["areas"]}
    expected_area_ids = set(UF5_AREA_PATH_ADDITIONS)
    for area_id, area in candidate_areas.items():
        contains = tuple(
            pattern in area["paths"] for pattern in UF5_TEAM_AREA_PATH_ADDITIONS
        )
        if area_id in expected_area_ids:
            assert all(contains)
            assert_registered_block(area["paths"], UF5_TEAM_AREA_PATH_ADDITIONS)
            assert_registered_block(
                baseline_areas[area_id]["paths"], UF5_TEAM_AREA_PATH_ADDITIONS
            )
        else:
            assert not any(contains)

    for pattern in UF5_TEAM_AREA_PATH_ADDITIONS:
        matches = tuple(
            path for path in expected_files if fnmatch.fnmatchcase(path, pattern)
        )
        assert len(matches) == 2
    assert core_guard.matched_paths(
        expected_files, core_guard.load_core_areas(REPO)
    ) == list(expected_files)
    core_guard.validate_area_path_layers(baseline, candidate)


@pytest.mark.parametrize(
    "core_path",
    ("frontend/src/screens/GameScreen.vue", "frontend/src/screens/GameScreen.spec.ts"),
)
def test_uf8_game_screen_change_requires_human_check(
    tmp_path: Path, core_path: str
) -> None:
    """実登録を使う合成 PR で未記入チェックを拒否する。"""
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_change(root, core_path)
    event_path = write_event(tmp_path, base_sha, head_sha, f"- [ ] {REQUIRED_CHECK_TEXT}")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert core_path in result.stderr
    assert f"- [x] {REQUIRED_CHECK_TEXT}" in result.stderr


@pytest.mark.parametrize(
    "core_path",
    (
        "frontend/src/components/settings/TeamMembersContent.spec.ts",
        "frontend/src/components/settings/TeamMembersContent.vue",
        "frontend/src/lib/rosterQueryKeys.spec.ts",
        "frontend/src/lib/rosterQueryKeys.ts",
        "frontend/src/screens/TeamScreen.spec.ts",
        "frontend/src/screens/TeamScreen.vue",
    ),
)
def test_uf5_team_change_requires_human_check(
    tmp_path: Path, core_path: str
) -> None:
    """実登録を使う合成 PR で製品 6 ファイルの未記入チェックを拒否する。"""
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_change(root, core_path)
    event_path = write_event(tmp_path, base_sha, head_sha, f"- [ ] {REQUIRED_CHECK_TEXT}")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert core_path in result.stderr
    assert f"- [x] {REQUIRED_CHECK_TEXT}" in result.stderr


def test_area_registration() -> None:
    """既存の登録履歴を後続追加に依存せず保ち、領域契約の先行追加層を固定する。"""
    core_guard = load_core_guard_module()
    configuration = load_actual_core_areas()
    areas = {area["id"]: area for area in configuration["areas"]}
    base_sha = run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    baseline = core_guard.load_core_areas_at_revision(REPO, base_sha)
    baseline_areas = {area["id"]: area for area in baseline["areas"]}
    tracked_files = run_git(REPO, "ls-files").stdout.splitlines()
    declared_ids = set(core_guard.AREA_PATH_ADDITIONS)
    stationary_ids = set(areas) - declared_ids
    appendix_e_additions = (
        ADR_001_PATH,
        ADR_003_PATH,
        *APPENDIX_E_GAME_STATE_AREA_PATH_ADDITIONS[:3],
        "scripts/check_expanded_fixture_parity.py",
        *APPENDIX_E_GAME_STATE_AREA_PATH_ADDITIONS[3:14],
        "tests/test_expanded_fixture_parity.py",
        *APPENDIX_E_GAME_STATE_AREA_PATH_ADDITIONS[14:],
        *NORMALIZATION_AREA_PATH_ADDITIONS,
        *REFERENCE_DISCOVERY_AREA_PATH_ADDITIONS,
        *CASE_GENERATION_AREA_PATH_ADDITIONS,
    )
    registered_additions = {
        "sync-protocol": (
            *appendix_e_additions,
            *UF6_CLIENT_AREA_PATH_ADDITIONS,
            *UF8_GAME_SCREEN_AREA_PATH_ADDITIONS,
        ),
        "game-state": (*appendix_e_additions, *UF8_GAME_SCREEN_AREA_PATH_ADDITIONS),
        "recording-rights": (
            ADR_001_PATH,
            *UF6_CLIENT_AREA_PATH_ADDITIONS,
            *UF8_GAME_SCREEN_AREA_PATH_ADDITIONS,
        ),
        "tenant-isolation": (
            ADR_001_PATH,
            *UM1_TENANT_AREA_PATH_ADDITIONS,
            *UF2_AUTH_STORE_AREA_PATH_ADDITIONS,
            *UF6_TENANT_AREA_PATH_ADDITIONS,
            *UF8_GAME_SCREEN_AREA_PATH_ADDITIONS,
            *UF5_TEAM_AREA_PATH_ADDITIONS,
        ),
        "data-migration": (
            ADR_001_PATH,
            ADR_003_PATH,
            *VOCABULARY_DATA_MIGRATION_AREA_PATH_ADDITIONS,
            *UF8_GAME_SCREEN_AREA_PATH_ADDITIONS,
            *UF5_TEAM_AREA_PATH_ADDITIONS,
        ),
    }

    assert len(areas) == len(configuration["areas"]) == 5
    assert len(DOMAIN_CALC_GLOBS) == 15
    assert dict(core_guard.AREA_PATH_ADDITIONS) == EXPECTED_AREA_PATH_ADDITIONS
    assert declared_ids <= set(areas)
    assert stationary_ids | declared_ids == set(areas)
    assert set(areas) == set(registered_additions) == set(baseline_areas)
    assert declared_ids == set(EXPECTED_AREA_PATH_ADDITIONS)
    for area_id in DATA_MODEL_AREA_IDS:
        registered = registered_additions[area_id]
        current_paths = tuple(areas[area_id]["paths"])
        base_paths = tuple(baseline_areas[area_id]["paths"])
        assert_registered_block(base_paths, registered)
        assert_registered_block(current_paths, registered)
        additions = REGISTERED_BEFORE_UR1.get(area_id, ())
        if additions:
            assert_registered_block(current_paths, additions)
        assert len(registered) == len(set(registered))
        assert all(
            any(fnmatch.fnmatchcase(path, pattern) for path in tracked_files)
            for pattern in registered
        )
    for area_id, additions in REGISTERED_BEFORE_UR1.items():
        base_paths = tuple(baseline_areas[area_id]["paths"])
        current_paths = tuple(areas[area_id]["paths"])
        assert_registered_block(base_paths, UR1_REGISTERED_PATHS[area_id])
        assert_registered_block(current_paths, UR1_REGISTERED_PATHS[area_id])
        assert current_paths == base_paths
        assert all(
            any(fnmatch.fnmatchcase(path, pattern) for path in tracked_files)
            for pattern in additions
        )
    assert all(
        any(fnmatch.fnmatchcase(path, pattern) for path in tracked_files)
        for pattern in UM1_TENANT_AREA_PATH_ADDITIONS
    )
    assert any(
        fnmatch.fnmatchcase(path, UF2_AUTH_STORE_AREA_PATH_ADDITIONS[0])
        for path in tracked_files
    )
    core_guard.validate_area_path_layers(baseline, configuration)


def test_registered_d2_paths_match_tracked_files_without_overlap() -> None:
    """登録済みの各 glob が実在ファイルに一致し、旧層と重複しない。

    名前は D-2 の登録を由来とするが、先行追加層の窓口は回転式なので、
    本体が見ているのは「現在宣言されている追加層」である。
    D-2 の分は core-areas.json へ着地済みで、宣言としての役目を終えている
    (DOMAIN_RUNTIME_PATH_ADDITIONS の中身は下の assert が直接固定する)。
    着地済みの paths が JSON から消えることは、CI の
    validate_area_path_layers が merge-base との比較で止める。
    """
    core_guard = load_core_guard_module()
    assert dict(core_guard.AREA_PATH_ADDITIONS) == EXPECTED_AREA_PATH_ADDITIONS
    assert tuple(core_guard.DOMAIN_RUNTIME_PATH_ADDITIONS) == (
        D2_DOMAIN_CALC_PATH_ADDITIONS
    )
    assert set(D2_DOMAIN_CALC_GLOBS) <= set(D2_DOMAIN_CALC_PATH_ADDITIONS)
    configuration = load_actual_core_areas()
    areas = {area["id"]: area for area in configuration["areas"]}
    tracked_files = run_git(REPO, "ls-files").stdout.splitlines()
    for area_id, additions in REGISTERED_BEFORE_UR1.items():
        patterns = areas[area_id]["paths"]
        assert_registered_block(tuple(patterns), additions)
        earlier_patterns = patterns[: patterns.index(additions[0])]
        assert not set(additions) & set(earlier_patterns)
        for pattern in additions:
            matched = [
                path for path in tracked_files if fnmatch.fnmatchcase(path, pattern)
            ]
            assert matched, f"実在ファイルに一致しない: {area_id}: {pattern}"
            assert all(
                not any(fnmatch.fnmatchcase(path, old) for old in earlier_patterns)
                for path in matched
            ), f"既存 glob が被覆済み: {area_id}: {pattern}"


def test_ur1_registered_paths_are_retained_after_declaration_rotation() -> None:
    """追加層が回転した後も実基線・実候補のRG1登録を保持する。"""
    core_guard = load_core_guard_module()
    configuration = load_actual_core_areas()
    baseline = core_guard.load_core_areas_at_revision(
        REPO, run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    )
    for document in (baseline, configuration):
        areas = {area["id"]: area for area in document["areas"]}
        for area_id, additions in UR1_REGISTERED_PATHS.items():
            assert_registered_block(areas[area_id]["paths"], additions)
    core_guard.validate_area_path_layers(baseline, configuration)
    for area_id in UR1_REGISTERED_PATHS:
        for pattern in UR1_REGISTERED_PATHS[area_id]:
            partial = json.loads(json.dumps(configuration))
            area = next(area for area in partial["areas"] if area["id"] == area_id)
            area["paths"].remove(pattern)
            with pytest.raises(core_guard.GuardError, match=rf"{area_id}\.paths"):
                core_guard.validate_area_path_layers(baseline, partial)


def test_uf13_declaration_retains_json_and_checks_product_registration() -> None:
    """宣言だけではJSONを変えず、合成登録でrouter/Appの全4実例を検出する。"""
    core_guard = load_core_guard_module()
    baseline = core_guard.load_core_areas_at_revision(
        REPO, run_git(REPO, "rev-parse", "origin/develop").stdout.strip()
    )
    configuration = load_actual_core_areas()
    core_guard.validate_area_path_layers(baseline, configuration)
    tenant = next(area for area in configuration["areas"] if area["id"] == "tenant-isolation")
    baseline_tenant = next(area for area in baseline["areas"] if area["id"] == "tenant-isolation")
    # 先行統合済みのLoginScreenは据え置き層として両方に保持する。
    assert "frontend/src/screens/LoginScreen*" in baseline_tenant["paths"]
    assert "frontend/src/screens/LoginScreen*" in tenant["paths"]
    presence = [pattern in tenant["paths"] for pattern in UF13_TENANT_ROUTE_PATHS]
    assert len(set(presence)) == 1
    if not any(presence):
        assert configuration == baseline
        tenant["paths"].extend(UF13_TENANT_ROUTE_PATHS)
    else:
        assert_registered_block(tenant["paths"], UF13_TENANT_ROUTE_PATHS)
    core_guard.validate_area_path_layers(baseline, configuration)
    candidate_areas = core_guard.CoreAreas(tuple(tenant["paths"]), frozenset())
    paths = [
        "frontend/src/router.ts", "frontend/src/router.spec.ts",
        "frontend/src/App.vue", "frontend/src/App.spec.ts",
    ]
    assert core_guard.matched_paths(paths, candidate_areas) == paths
    for pattern in UF13_TENANT_ROUTE_PATHS:
        missing = json.loads(json.dumps(configuration))
        area = next(area for area in missing["areas"] if area["id"] == "tenant-isolation")
        area["paths"].remove(pattern)
        with pytest.raises(core_guard.GuardError, match="tenant-isolation.paths"):
            core_guard.validate_area_path_layers(baseline, missing)


def test_uf13_registered_products_require_human_confirmation(tmp_path: Path) -> None:
    """合成履歴へ登録した4製品・試験パスは本人未記入なら実CLIで拒否する。"""
    root = make_repo_with_actual_core_areas(tmp_path)
    configuration = load_actual_core_areas()
    tenant = next(area for area in configuration["areas"] if area["id"] == "tenant-isolation")
    for pattern in UF13_TENANT_ROUTE_PATHS:
        if pattern not in tenant["paths"]:
            tenant["paths"].append(pattern)
    write_json(root, ".claude/core-areas.json", configuration)
    run_git(root, "add", ".claude/core-areas.json")
    run_git(
        root, "-c", "user.email=test@example.com", "-c", "user.name=test",
        "commit", "--allow-empty", "-qm", "registered synthetic baseline",
    )
    base_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    paths = (
        "frontend/src/router.ts", "frontend/src/router.spec.ts",
        "frontend/src/App.vue", "frontend/src/App.spec.ts",
    )
    for path in paths:
        write_text(root, path, "product change\n")
    run_git(root, "add", ".")
    run_git(
        root, "-c", "user.email=test@example.com", "-c", "user.name=test",
        "commit", "-qm", "synthetic products",
    )
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    event_path = write_event(tmp_path, base_sha, head_sha, f"- [ ] {REQUIRED_CHECK_TEXT}")
    result = run_guard(root, event_name="pull_request", event_path=event_path)
    assert result.returncode == 1
    assert all(f"{path}: PR 本文に必須チェックがない" in result.stderr for path in paths)
    event_path = write_event(tmp_path, base_sha, head_sha, f"- [x] {REQUIRED_CHECK_TEXT}")
    result = run_guard(root, event_name="pull_request", event_path=event_path)
    assert result.returncode == 0, result.stderr


def test_uf13_retains_login_registration_after_predecessor_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """先行LoginScreen統合済みの隔離履歴で登録と旧層削除拒否を実CLI検証する。"""
    root = make_repo_with_actual_core_areas(tmp_path)
    baseline = load_actual_core_areas()
    login = "frontend/src/screens/LoginScreen*"
    additions = tuple(pattern for pattern in UF13_TENANT_ROUTE_PATHS if pattern != login)
    tenant = next(area for area in baseline["areas"] if area["id"] == "tenant-isolation")
    tenant["paths"] = [pattern for pattern in tenant["paths"] if pattern not in additions]
    if login not in tenant["paths"]:
        tenant["paths"].append(login)
    write_json(root, ".claude/core-areas.json", baseline)
    write_text(root, "scripts/core_guard.py", core_guard_source_with_additions({
        "tenant-isolation": (login,),
    }))
    run_git(root, "add", ".")
    run_git(root, "-c", "user.email=test@example.com", "-c", "user.name=test",
            "commit", "--allow-empty", "-qm", "synthetic merged LoginScreen baseline")
    base_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    # 実PRと同じく、先行LoginScreen宣言からrouter/Appへ先に回転する。
    write_text(root, "scripts/core_guard.py", core_guard_source_with_additions({
        "tenant-isolation": additions,
    }))
    run_git(root, "add", "scripts/core_guard.py")
    run_git(root, "-c", "user.email=test@example.com", "-c", "user.name=test",
            "commit", "-qm", "synthetic declaration rotation before JSON")
    tenant["paths"].extend(additions)
    write_json(root, ".claude/core-areas.json", baseline)
    write_text(root, "frontend/src/router.ts", "product change\n")
    run_git(root, "add", ".")
    run_git(root, "-c", "user.email=test@example.com", "-c", "user.name=test",
            "commit", "-qm", "synthetic route registration")
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    # 将来の回転を再現した候補実体を実行し、ホストの現在追加層には依存させない。
    monkeypatch.setattr(sys.modules[__name__], "SCRIPT", root / "scripts/core_guard.py")
    event = write_event(tmp_path, base_sha, head_sha, f"- [ ] {REQUIRED_CHECK_TEXT}")
    result = run_guard(root, event_name="pull_request", event_path=event)
    assert result.returncode == 1
    assert "frontend/src/router.ts: PR 本文に必須チェックがない" in result.stderr
    event = write_event(tmp_path, base_sha, head_sha, f"- [x] {REQUIRED_CHECK_TEXT}")
    result = run_guard(root, event_name="pull_request", event_path=event)
    assert result.returncode == 0, result.stderr
    assert login in tenant["paths"]
    tenant["paths"].remove(login)
    assert login not in tenant["paths"]
    write_json(root, ".claude/core-areas.json", baseline)
    run_git(root, "add", ".")
    run_git(root, "-c", "user.email=test@example.com", "-c", "user.name=test",
            "commit", "-qm", "synthetic forbidden LoginScreen removal")
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    event = write_event(tmp_path, base_sha, head_sha, f"- [x] {REQUIRED_CHECK_TEXT}")
    result = run_guard(root, event_name="pull_request", event_path=event)
    assert result.returncode == 1
    assert "tenant-isolation.paths" in result.stderr


def test_ur1_actual_path_set_is_guarded_in_both_meaning_areas() -> None:
    """RG1の製品・認可・試験差分を実登録で記録権と同期へ帰属させる。"""
    core_guard = load_core_guard_module()
    configuration = load_actual_core_areas()
    areas = {area["id"]: area["paths"] for area in configuration["areas"]}
    rg1_paths = (
        "backend/src/pitchlog/repositories/rg1.py",
        "backend/src/pitchlog/repositories/operation_registry.py",
        "backend/src/pitchlog/authz/classification.py",
        "backend/src/pitchlog/authz/product_control_access.py",
        "backend/src/pitchlog/authz/product_table_access.py",
        "backend/src/pitchlog/authz/product_catalog.py",
        "backend/src/pitchlog/authz/product_provisioning.py",
        "backend/src/pitchlog/authz/product_function_acl.py",
        "backend/tests/test_rg1_lock_contract.py",
        "contracts/authz/product/ddl-elements.json",
        "contracts/authz/product/table-classification.json",
        "contracts/authz/product/exposure-facts.json",
        "contracts/authz/product/function-bodies/functions/"
        "FUNCTION:rg1_api:rg1_read_open(uuid).sql",
        "contracts/tenant_boundary/repository-contract.json",
        "contracts/tenant_boundary/base-allowlist.json",
        "scripts/check_authz_catalog.py",
        "tests/test_check_authz_catalog.py",
    )
    sync_paths = (
        "backend/src/pitchlog/repositories/rg1.py",
        "backend/src/pitchlog/repositories/operation_registry.py",
        "backend/tests/test_rg1_lock_contract.py",
        "contracts/tenant_boundary/repository-contract.json",
        "contracts/tenant_boundary/base-allowlist.json",
        "contracts/authz/product/function-bodies/functions/"
        "FUNCTION:rg1_api:rg1_read_open(uuid).sql",
    )
    assert core_guard.matched_paths(rg1_paths, core_guard.load_core_areas(REPO)) == list(
        rg1_paths
    )
    assert all(
        any(fnmatch.fnmatchcase(path, pattern) for pattern in areas["recording-rights"])
        for path in rg1_paths
    )
    assert all(
        any(fnmatch.fnmatchcase(path, pattern) for pattern in areas["sync-protocol"])
        for path in sync_paths
    )


@pytest.mark.parametrize(
    "pattern",
    DOMAIN_CALC_GLOBS,
)
def test_future_domain_calc_file_is_covered_by_each_registered_glob(
    pattern: str,
) -> None:
    """各 glob が将来追加される下位ファイルも自動的に覆うと示す。"""
    configuration = load_actual_core_areas()
    areas = {area["id"]: area for area in configuration["areas"]}
    future_path = f"{pattern.removesuffix('*')}future/nested_probe.py"

    for area_id in DOMAIN_CALC_AREA_IDS:
        patterns = areas[area_id]["paths"]
        assert any(fnmatch.fnmatchcase(future_path, item) for item in patterns)
        without_glob = [item for item in patterns if item != pattern]
        assert not any(
            fnmatch.fnmatchcase(future_path, item) for item in without_glob
        ), f"{area_id} で {pattern} を除いても将来ファイルが被覆されている"


@pytest.mark.parametrize(
    "pattern",
    DOMAIN_CALC_GLOBS,
)
def test_each_domain_calc_glob_change_triggers_guard(
    tmp_path: Path,
    pattern: str,
) -> None:
    """各追加 glob 配下の新規パス変更で core-guard が発火する。"""
    future_path = f"{pattern.removesuffix('*')}future/nested_probe.py"
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_change(root, future_path)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert future_path in result.stderr


def test_domain_calc_adjacent_path_does_not_trigger_guard(tmp_path: Path) -> None:
    """登録対象外の隣接パス変更では core-guard が発火しない。"""
    root = make_repo_with_actual_core_areas(tmp_path)
    path = "backend/src/pitchlog/domain_other/future_probe.py"
    base_sha, head_sha = commit_change(root, path)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 0, result.stderr


def test_core_adrs_have_the_expected_area_ownership() -> None:
    """規範またはレビュー強制点を持つADRだけが該当領域へ帰属すると示す。"""
    configuration = load_actual_core_areas()
    actual_by_path = {
        path: {
            area["id"]
            for area in configuration["areas"]
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in area["paths"])
        }
        for path in (
            ADR_001_PATH,
            "docs/adr/ADR-002-frontend-vue.md",
            ADR_003_PATH,
            "docs/adr/ADR-004-merge-gate-scope.md",
        )
    }

    assert actual_by_path == {
        ADR_001_PATH: set(CORE_ADR_AREA_PATHS),
        "docs/adr/ADR-002-frontend-vue.md": set(),
        ADR_003_PATH: {"sync-protocol", "game-state", "data-migration"},
        "docs/adr/ADR-004-merge-gate-scope.md": set(),
    }


def test_appendix_e_assets_are_owned_by_game_state_and_sync_areas() -> None:
    """付録E/Fの契約・検査資産43件が状況計算と同期へ全件帰属すると示す。"""
    configuration = load_actual_core_areas()
    areas_by_id = {area["id"]: area for area in configuration["areas"]}
    assert len(APPENDIX_E_GAME_STATE_ASSET_PATHS) == 43
    assert all((REPO / path).is_file() for path in APPENDIX_E_GAME_STATE_ASSET_PATHS)

    for area_id in ("game-state", "sync-protocol"):
        patterns = areas_by_id[area_id]["paths"]
        assert set(APPENDIX_E_GAME_STATE_AREA_PATH_ADDITIONS).issubset(patterns)
        assert set(NORMALIZATION_AREA_PATH_ADDITIONS).issubset(patterns)
        missing = [
            path
            for path in APPENDIX_E_GAME_STATE_ASSET_PATHS
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        ]
        assert missing == [], f"{area_id} に未登録: {missing}"


def test_vocabulary_assets_are_owned_by_data_migration_area() -> None:
    """付録D-4の語彙資産と検査がデータ移行にも帰属すると示す。"""
    configuration = load_actual_core_areas()
    data_migration = next(
        area for area in configuration["areas"] if area["id"] == "data-migration"
    )
    patterns = data_migration["paths"]
    vocabulary_assets = (
        "contracts/vocabulary/input_vocabulary_v1.json",
        "contracts/vocabulary/vocabulary_manifest_schema_v1.json",
        "contracts/vocabulary/vocabulary_manifest_v1.json",
        "contracts/vocabulary/vocabulary_seed_schema_v1.json",
        "scripts/check_vocabulary_manifest.py",
        "tests/test_vocabulary_manifest.py",
        "tests/test_vocabulary_seed.py",
    )

    assert set(VOCABULARY_DATA_MIGRATION_AREA_PATH_ADDITIONS).issubset(patterns)
    missing = [
        path
        for path in vocabulary_assets
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
    ]
    assert missing == []


def test_contract_reference_python_paths_are_discovered_deterministically() -> None:
    """契約参照の導出と資産で宣言した除外の完全一致を固定する。"""
    configuration = load_actual_core_areas()
    policy = _require_reference_discovery_policy(configuration)
    areas_by_id = {area["id"]: area for area in configuration["areas"]}

    first = derive_contract_reference_python_paths(REPO, configuration)
    second = derive_contract_reference_python_paths(REPO, configuration)
    excluded = tuple(policy["declared_exclusions"]["paths"])

    assert first == second
    assert first == tuple(sorted(set(first)))
    assert set(excluded) <= set(first)
    registered = D2_SYNC_PROTOCOL_PATH_ADDITIONS[0]
    sync_patterns = areas_by_id["sync-protocol"]["paths"]
    assert registered in first
    assert any(fnmatch.fnmatchcase(registered, pattern) for pattern in sync_patterns)
    for area_id in policy["required_area_ids"]:
        patterns = areas_by_id[area_id]["paths"]
        assert "scripts/*" not in patterns
        assert "tests/*" not in patterns
        missing = tuple(
            path
            for path in first
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        )
        assert set(missing) == set(excluded)

    assert assert_contract_reference_python_paths_are_registered(
        REPO, configuration
    ) == (
        tuple(path for path in first if path not in excluded)
    )


@pytest.mark.parametrize(
    "relative_path",
    (
        "scripts/unrelated_naming_style.py",
        "tests/nested/arbitrary_asset_name.py",
    ),
)
def test_unregistered_contract_reference_fails_without_updating_paths(
    tmp_path: Path,
    relative_path: str,
) -> None:
    """命名によらず静的契約参照を検出し、設定を自動更新せず fail する。"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "tests").mkdir()
    configuration = json.loads(json.dumps(load_actual_core_areas()))
    for area in configuration["areas"]:
        if area["id"] in configuration["reference_discovery"]["required_area_ids"]:
            area["paths"] = []
    write_text(
        root,
        relative_path,
        'CONTRACT = "contracts/state-transition/future_contract_v1.json"\n',
    )
    before = json.dumps(configuration, ensure_ascii=False, sort_keys=True)

    with pytest.raises(AssertionError, match=relative_path):
        assert_contract_reference_python_paths_are_registered(root, configuration)

    assert json.dumps(configuration, ensure_ascii=False, sort_keys=True) == before


def test_reverse_dependency_closure_fails_for_unregistered_dependent(
    tmp_path: Path,
) -> None:
    """契約参照ファイルを静的に読む側も名前によらず登録対象にする。"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "tests").mkdir()
    configuration = json.loads(json.dumps(load_actual_core_areas()))
    for area in configuration["areas"]:
        if area["id"] in configuration["reference_discovery"]["required_area_ids"]:
            area["paths"] = []
    direct_path = "scripts/opaque_asset_name.py"
    dependent_path = "tests/another_opaque_name.py"
    write_text(
        root,
        direct_path,
        'CONTRACT = "contracts/vocabulary/future_seed_v1.json"\n',
    )
    write_text(
        root,
        dependent_path,
        'SOURCE = Path("scripts") / "opaque_asset_name.py"\n',
    )

    candidates = derive_contract_reference_python_paths(root, configuration)

    assert direct_path in candidates
    assert dependent_path in candidates
    with pytest.raises(AssertionError, match=dependent_path):
        assert_contract_reference_python_paths_are_registered(root, configuration)


def test_appendix_e_assets_trigger_actual_core_guard(tmp_path: Path) -> None:
    """付録E/Fの資産43件の同時変更が全件強化レビュー対象になると示す。"""
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_changes(root, APPENDIX_E_GAME_STATE_ASSET_PATHS)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert all(path in result.stderr for path in APPENDIX_E_GAME_STATE_ASSET_PATHS)
    assert f"- [x] {REQUIRED_CHECK_TEXT}" in result.stderr


def test_database_tests_have_the_same_area_ownership_as_migrations() -> None:
    """DB migration を所有する全領域が DB テストも同じく所有すると示す。"""
    configuration = load_actual_core_areas()
    areas = configuration["areas"]
    migration_area_ids = {
        area["id"] for area in areas if "backend/migrations/*" in area["paths"]
    }
    database_test_area_ids = {
        area["id"] for area in areas if "backend/tests/db/*" in area["paths"]
    }

    assert database_test_area_ids == migration_area_ids


def test_all_schema_contract_assets_match_an_actual_core_area_path():
    """今後増えるスキーマ契約資産も実際の領域パターンで自動検出する。"""
    assert_schema_contract_assets_are_registered(schema_contract_asset_paths())


def test_unregistered_schema_contract_asset_is_rejected_without_creating_it():
    """走査範囲内に未登録ファイルが増えた場合は同じ判定をredにする。"""
    hypothetical_path = "backend/src/pitchlog/db/unregistered_area/models.py"
    assets = [*schema_contract_asset_paths(), hypothetical_path]

    with pytest.raises(AssertionError, match=hypothetical_path):
        assert_schema_contract_assets_are_registered(assets)


def test_schema_contract_population_closes_forward_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """スキーマ契約テストの母集団は import 先だけを推移的に含める。"""
    write_text(
        tmp_path,
        "backend/tests/test_seed.py",
        'import helper\nSCHEMA_REF = "migrations"\n',
    )
    write_text(tmp_path, "backend/tests/helper.py", "VALUE = 1\n")
    write_text(tmp_path, "backend/tests/test_importer.py", "import helper\n")
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)

    population = schema_contract_test_paths()

    assert "backend/tests/test_seed.py" in population
    assert "backend/tests/helper.py" in population
    assert "backend/tests/test_importer.py" not in population, (
        "逆向きの閉包は認可検証の資産を巻き込む"
    )


def test_schema_contract_test_population_does_not_depend_on_branch() -> None:
    """スキーマ契約テストの母集団がブランチの状態に依存しないと示す。

    名前による判定は正当な経路の試験も禁じ、別の場所へ広がる退行を見逃す。
    閉包の向きは `test_schema_contract_population_closes_forward_only` が
    import の挙動で固定する。
    """
    population = schema_contract_test_paths()
    assert population, "backend/tests/ の母集団が空になっている"
    assert "backend/tests/test_operation_event_kind_contract.py" in population


def test_unregistered_schema_contract_test_is_rejected() -> None:
    """スキーマ契約テストを登録から外すと全件検査をredにする。"""
    missing_path = "backend/tests/test_operation_event_kind_contract.py"
    core_guard = load_core_guard_module()
    configured = core_guard.load_core_areas(REPO)
    without_new_test = core_guard.CoreAreas(
        path_patterns=tuple(
            pattern
            for pattern in configured.path_patterns
            if pattern != missing_path
        ),
        guard_paths=frozenset(),
    )

    with pytest.raises(AssertionError, match=missing_path):
        assert_schema_contract_assets_are_registered(
            schema_contract_asset_paths(), configured=without_new_test
        )


def test_actual_core_area_document_changes_trigger_guard(tmp_path):
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_changes(root, CORE_DOCUMENT_PATHS)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert all(path in result.stderr for path in CORE_DOCUMENT_PATHS)


def test_actual_config_does_not_register_documents_for_data_migration():
    configuration = load_actual_core_areas()
    areas = configuration["areas"]
    assert isinstance(areas, list)
    area = next(item for item in areas if item["id"] == "data-migration")

    assert all(path not in area["paths"] for path in CORE_DOCUMENT_PATHS)


def test_actual_guard_paths_are_exact_expected_set():
    configuration = load_actual_core_areas()

    assert configuration["guard_paths"] == list(EXISTING_REAL_GUARD_PATHS + NEW_GUARD_PATHS)


@pytest.mark.parametrize("guard_path", NEW_GUARD_PATHS, ids=NEW_GUARD_PATHS)
def test_each_actual_guard_path_change_triggers_guard(tmp_path, guard_path):
    configuration = load_actual_core_areas()
    assert guard_path in configuration["guard_paths"]

    root = make_repo_with_actual_core_areas(tmp_path)
    content = "changed\n"
    if guard_path == ".claude/core-areas.json":
        content = (root / guard_path).read_text(encoding="utf-8") + "\n"
    base_sha, head_sha = commit_change(root, guard_path, content)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert guard_path in result.stderr


@pytest.mark.parametrize("core_path", NEW_CORE_PATH_CHANGES, ids=NEW_CORE_PATH_CHANGES)
def test_each_new_actual_core_path_change_triggers_guard(tmp_path, core_path):
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_change(root, core_path)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert core_path in result.stderr
    assert f"- [x] {REQUIRED_CHECK_TEXT}" in result.stderr


def test_nested_path_matching_actual_core_glob_triggers_guard(tmp_path):
    core_path = "contracts/authz/nested/example.json"
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_change(root, core_path)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert core_path in result.stderr


def test_adjacent_path_not_matching_actual_core_glob_does_not_trigger_guard(tmp_path):
    root = make_repo_with_actual_core_areas(tmp_path)
    base_sha, head_sha = commit_change(root, "contracts/authz-other/example.json")
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 0, result.stderr


def test_skips_non_pull_request_event_without_event_path(tmp_path):
    result = run_guard(tmp_path, event_name="push")

    assert result.returncode == 0
    assert "PR イベントではない — スキップ" in result.stdout


def test_allows_non_matching_change_when_core_paths_are_empty(tmp_path):
    root = make_repo(tmp_path)
    base_sha, head_sha = commit_change(root, "docs/notes.md")
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 0, result.stderr
    assert (
        "コア領域の paths が未定義。設計書 6.3 の落とし込み規則に従い実装追随で登録する"
        " — コア検査対象なし"
    ) in result.stdout


def test_allows_guard_path_change_with_completed_check(tmp_path):
    root = make_repo(tmp_path)
    base_sha, head_sha = commit_change(root, ".github/workflows/ci.yml")
    event_path = write_event(
        tmp_path,
        base_sha,
        head_sha,
        f"- [x] {REQUIRED_CHECK_TEXT}",
    )

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body",
    ["", f"- [ ] {REQUIRED_CHECK_TEXT}"],
)
def test_rejects_guard_path_change_without_completed_check(tmp_path, body):
    root = make_repo(tmp_path)
    base_sha, head_sha = commit_change(root, ".github/workflows/ci.yml")
    event_path = write_event(tmp_path, base_sha, head_sha, body)

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert ".github/workflows/ci.yml" in result.stderr
    assert f"- [x] {REQUIRED_CHECK_TEXT}" in result.stderr


def test_rejects_matching_core_glob_without_completed_check(tmp_path):
    root = make_repo(tmp_path, core_paths=["backend/core/*.py"])
    base_sha, head_sha = commit_change(root, "backend/core/service.py")
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert "backend/core/service.py" in result.stderr


def test_rejects_rename_from_protected_path_to_unprotected_path(tmp_path):
    old_path = "backend/core/service.py"
    new_path = "backend/public/service.py"
    root = make_repo(tmp_path, core_paths=["backend/core/*.py"])
    base_sha, head_sha = commit_rename(root, old_path, new_path)
    assert_exact_rename(root, base_sha, head_sha, old_path, new_path)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert old_path in result.stderr


def test_rejects_rename_from_unprotected_path_to_protected_path(tmp_path):
    old_path = "backend/public/service.py"
    new_path = "backend/core/service.py"
    root = make_repo(tmp_path, core_paths=["backend/core/*.py"])
    base_sha, head_sha = commit_rename(root, old_path, new_path)
    assert_exact_rename(root, base_sha, head_sha, old_path, new_path)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert new_path in result.stderr


def test_allows_rename_between_unprotected_paths(tmp_path):
    old_path = "backend/public/old_service.py"
    new_path = "backend/public/new_service.py"
    root = make_repo(tmp_path, core_paths=["backend/core/*.py"])
    base_sha, head_sha = commit_rename(root, old_path, new_path)
    assert_exact_rename(root, base_sha, head_sha, old_path, new_path)
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 0, result.stderr


def test_fails_closed_on_invalid_event_json(tmp_path):
    root = make_repo(tmp_path)
    event_path = tmp_path / "event.json"
    event_path.write_text("{", encoding="utf-8")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert "GITHUB_EVENT_PATH の JSON が不正" in result.stderr


def test_fails_closed_when_event_path_is_missing(tmp_path):
    root = make_repo(tmp_path)

    result = run_guard(root, event_name="pull_request")

    assert result.returncode == 1
    assert "GITHUB_EVENT_PATH が未設定" in result.stderr


def test_fails_closed_when_base_sha_is_missing(tmp_path):
    root = make_repo(tmp_path)
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    event_path = tmp_path / "event.json"
    write_json(
        tmp_path,
        "event.json",
        {"pull_request": {"head": {"sha": head_sha}, "body": ""}},
    )

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert "base SHA がない" in result.stderr


def test_fails_closed_when_body_is_null(tmp_path):
    root = make_repo(tmp_path)
    sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    event_path = write_event(tmp_path, sha, sha, None)

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert "本文(body)が null" in result.stderr


def test_fails_closed_when_git_diff_fails(tmp_path):
    root = make_repo(tmp_path)
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()
    event_path = write_event(tmp_path, "missing-base", head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert "git diff に失敗" in result.stderr


def test_fails_closed_on_invalid_core_areas_json(tmp_path):
    root = make_repo(tmp_path)
    base_sha, head_sha = commit_change(root, "docs/notes.md")
    write_text(root, ".claude/core-areas.json", "{")
    event_path = write_event(tmp_path, base_sha, head_sha, "")

    result = run_guard(root, event_name="pull_request", event_path=event_path)

    assert result.returncode == 1
    assert "core-areas.json の JSON が不正" in result.stderr


def _load_required_check_text_from_script() -> str:
    """scripts/core_guard.py から REQUIRED_CHECK_TEXT の実値を読む(正は script 側)。"""
    module = load_core_guard_module()
    return module.REQUIRED_CHECK_TEXT


def test_check_text_is_consistent_across_script_template_and_skill():
    (
        """チェック文言が core_guard.py・PR テンプレ・/pr スキルで一致することを検証する("""
        """計画ステップ 5)。"""
    )
    canonical = _load_required_check_text_from_script()
    assert canonical == REQUIRED_CHECK_TEXT  # テスト側リテラルの腐り検知

    template = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert f"- [ ] {canonical}" in template, "PR テンプレに未チェック形の必須文言がない"

    skill = (REPO / ".claude" / "skills" / "pr" / "SKILL.md").read_text(encoding="utf-8")
    assert "REQUIRED_CHECK_TEXT" in skill, "/pr スキルが文言の正(core_guard.py)を参照していない"
    assert "guard_paths" in skill, "/pr スキルが guard_paths 判定に言及していない"
