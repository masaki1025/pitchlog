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
)
AUTHZ_BACKEND_TEST_PATTERN = "backend/tests/test_authz_*.py"
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
    *AUTHZ_BACKEND_WORDING_AREA_PATH_ADDITIONS,
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
EXPECTED_AREA_PATHS = {
    "sync-protocol": [
        CORE_DOCUMENT_PATHS[0],
        DATA_MODEL_DOCUMENT_PATH,
        CORE_DOCUMENT_PATHS[1],
        "frontend/package.json",
        "frontend/pnpm-lock.yaml",
        "frontend/src/lib/sync/ackAdapter.spec.ts",
        "frontend/src/lib/sync/ackAdapter.ts",
        "frontend/src/lib/sync/ackEnvelope.spec.ts",
        "frontend/src/lib/sync/ackEnvelope.ts",
        "frontend/src/lib/sync/boundaryResults.spec.ts",
        "frontend/src/lib/sync/boundaryResults.ts",
        "frontend/src/lib/sync/canonOracle.spec.ts",
        "frontend/src/lib/sync/canonOracle.ts",
        "frontend/src/lib/sync/changeOperationGate.spec.ts",
        "frontend/src/lib/sync/changeOperationGate.ts",
        "frontend/src/lib/sync/clientDiscipline.spec.ts",
        "frontend/src/lib/sync/clientDiscipline.ts",
        "frontend/src/lib/sync/durableQueue.spec.ts",
        "frontend/src/lib/sync/durableQueue.ts",
        "frontend/src/lib/sync/eventFieldRules.spec.ts",
        "frontend/src/lib/sync/eventFieldRules.ts",
        "frontend/src/lib/sync/eventKinds.spec.ts",
        "frontend/src/lib/sync/eventKinds.ts",
        "frontend/src/lib/sync/failureScenarioContract.spec.ts",
        "frontend/src/lib/sync/failureScenarioContract.ts",
        "frontend/src/lib/sync/idempotencyCollision.spec.ts",
        "frontend/src/lib/sync/idempotencyCollision.ts",
        "frontend/src/lib/sync/k5Tombstone.spec.ts",
        "frontend/src/lib/sync/k5Tombstone.ts",
        "frontend/src/lib/sync/localQueueFile.spec.ts",
        "frontend/src/lib/sync/localQueueFile.ts",
        "frontend/src/lib/sync/mappingConfirmationGate.spec.ts",
        "frontend/src/lib/sync/mappingConfirmationGate.ts",
        "frontend/src/lib/sync/p3Result.spec.ts",
        "frontend/src/lib/sync/p3Result.ts",
        "frontend/src/lib/sync/playerIdMapping.spec.ts",
        "frontend/src/lib/sync/playerIdMapping.ts",
        "frontend/src/lib/sync/processingStages.spec.ts",
        "frontend/src/lib/sync/processingStages.snapshot.json",
        "frontend/src/lib/sync/processingStages.ts",
        "frontend/src/lib/sync/restoreAdjustmentGate.spec.ts",
        "frontend/src/lib/sync/restoreAdjustmentGate.ts",
        "frontend/src/lib/sync/prohibitions.spec.ts",
        "frontend/src/lib/sync/queueState.spec.ts",
        "frontend/src/lib/sync/queueState.ts",
        "frontend/src/lib/sync/queueTransition.spec.ts",
        "frontend/src/lib/sync/queueTransition.ts",
        "frontend/src/lib/sync/rejectionReason.spec.ts",
        "frontend/src/lib/sync/rejectionReason.ts",
        "frontend/src/lib/sync/requestBoundary.spec.ts",
        "frontend/src/lib/sync/requestBoundary.ts",
        "frontend/src/lib/sync/resendRange.spec.ts",
        "frontend/src/lib/sync/resendRange.ts",
        "frontend/src/lib/sync/singleWriter.spec.ts",
        "frontend/src/lib/sync/singleWriter.ts",
        "frontend/src/lib/sync/syncEvent.ts",
        "frontend/src/lib/sync/syncNotices.spec.ts",
        "frontend/src/lib/sync/syncNotices.ts",
        "frontend/src/lib/sync/temporaryIdMapping.spec.ts",
        "frontend/src/lib/sync/temporaryIdMapping.ts",
        "frontend/src/lib/sync/undoQueueing.spec.ts",
        "frontend/src/lib/sync/undoQueueing.ts",
        "frontend/src/lib/sync/validateSyncEvent.spec.ts",
        "frontend/src/lib/sync/validateSyncEvent.ts",
        "frontend/src/testing/failureScenarioAdapter.spec.ts",
        "frontend/src/testing/failureScenarioAdapter.ts",
        "frontend/tsconfig.app.json",
        "frontend/vite.config.ts",
        "tests/fixtures/sync-protocol-failures/**",
        *ORM_SCHEMA_MIGRATION_AREA_PATHS["sync-protocol"],
    ],
    "game-state": [
        CORE_DOCUMENT_PATHS[0],
        DATA_MODEL_DOCUMENT_PATH,
        CORE_DOCUMENT_PATHS[1],
        "frontend/src/lib/courseInputView.ts",
        "frontend/src/lib/displayGeometry.ts",
        "frontend/src/lib/spatialInput.ts",
        "frontend/src/components/zone/StrikeZone.vue",
        "frontend/src/lib/courseCoordinateContract.spec.ts",
        "frontend/src/lib/displayGeometry.spec.ts",
        "frontend/src/components/zone/StrikeZone.spec.ts",
        "contracts/display_geometry_263_v1.json",
        "frontend/vite.config.ts",
        "frontend/vitest.config.ts",
        "frontend/package.json",
        "frontend/tsconfig.app.json",
        "frontend/tsconfig.json",
        "frontend/pnpm-lock.yaml",
        "mise.toml",
        "frontend/src/lib/sync/eventKinds.ts",
        "frontend/src/lib/sync/eventKinds.spec.ts",
        "frontend/src/lib/sync/eventFieldRules.ts",
        "frontend/src/lib/sync/eventFieldRules.spec.ts",
        "frontend/src/lib/sync/validateSyncEvent.ts",
        "frontend/src/lib/sync/validateSyncEvent.spec.ts",
        "frontend/src/lib/sync/canonOracle.ts",
        "frontend/src/lib/sync/canonOracle.spec.ts",
        "frontend/src/lib/sync/prohibitions.spec.ts",
        *ORM_SCHEMA_MIGRATION_AREA_PATHS["game-state"],
    ],
    "recording-rights": [
        CORE_DOCUMENT_PATHS[0],
        DATA_MODEL_DOCUMENT_PATH,
        CORE_DOCUMENT_PATHS[1],
        "frontend/src/lib/sync/ackEnvelope.spec.ts",
        "frontend/src/lib/sync/ackEnvelope.ts",
        "frontend/src/lib/sync/boundaryResults.spec.ts",
        "frontend/src/lib/sync/boundaryResults.ts",
        "frontend/src/lib/sync/canonOracle.spec.ts",
        "frontend/src/lib/sync/canonOracle.ts",
        "frontend/src/lib/sync/changeOperationGate.spec.ts",
        "frontend/src/lib/sync/changeOperationGate.ts",
        "frontend/src/lib/sync/durableQueue.spec.ts",
        "frontend/src/lib/sync/durableQueue.ts",
        "frontend/src/lib/sync/eventFieldRules.spec.ts",
        "frontend/src/lib/sync/eventFieldRules.ts",
        "frontend/src/lib/sync/k5Tombstone.spec.ts",
        "frontend/src/lib/sync/k5Tombstone.ts",
        "frontend/src/lib/sync/localQueueFile.spec.ts",
        "frontend/src/lib/sync/localQueueFile.ts",
        "frontend/src/lib/sync/p3Result.spec.ts",
        "frontend/src/lib/sync/p3Result.ts",
        "frontend/src/lib/sync/processingStages.spec.ts",
        "frontend/src/lib/sync/processingStages.snapshot.json",
        "frontend/src/lib/sync/processingStages.ts",
        "frontend/src/lib/sync/restoreAdjustmentGate.spec.ts",
        "frontend/src/lib/sync/restoreAdjustmentGate.ts",
        "frontend/src/lib/sync/queueState.spec.ts",
        "frontend/src/lib/sync/queueState.ts",
        "frontend/src/lib/sync/queueTransition.spec.ts",
        "frontend/src/lib/sync/queueTransition.ts",
        "frontend/src/lib/sync/requestBoundary.spec.ts",
        "frontend/src/lib/sync/requestBoundary.ts",
        "frontend/src/lib/sync/resendRange.spec.ts",
        "frontend/src/lib/sync/resendRange.ts",
        "frontend/src/lib/sync/syncEvent.ts",
        "frontend/src/lib/sync/undoQueueing.spec.ts",
        "frontend/src/lib/sync/undoQueueing.ts",
        "frontend/src/lib/sync/validateSyncEvent.spec.ts",
        "frontend/src/lib/sync/validateSyncEvent.ts",
        *ORM_SCHEMA_MIGRATION_AREA_PATHS["recording-rights"],
    ],
    "tenant-isolation": [
        CORE_DOCUMENT_PATHS[0],
        DATA_MODEL_DOCUMENT_PATH,
        CORE_DOCUMENT_PATHS[1],
        "contracts/authz/*",
        "scripts/check_authz_catalog.py",
        "tests/test_check_authz_catalog.py",
        *AUTHZ_TENANT_AREA_PATH_ADDITIONS,
        "tests/fixtures/authz_claims/*",
        "backend/tests/db/*",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/*conftest.py",
        "backend/.python-version",
        "docker-compose.yml",
        "frontend/src/lib/sync/canonOracle.spec.ts",
        "frontend/src/lib/sync/canonOracle.ts",
        "frontend/src/lib/sync/idempotencyCollision.ts",
        "frontend/src/lib/sync/idempotencyCollision.spec.ts",
        "frontend/src/lib/sync/processingStages.spec.ts",
        "frontend/src/lib/sync/processingStages.snapshot.json",
        "frontend/src/lib/sync/processingStages.ts",
        "frontend/src/lib/sync/restoreAdjustmentGate.spec.ts",
        "frontend/src/lib/sync/restoreAdjustmentGate.ts",
        *ORM_SCHEMA_MIGRATION_AREA_PATHS["tenant-isolation"],
    ],
    "data-migration": [
        DATA_MODEL_DOCUMENT_PATH,
        "frontend/src/lib/format.ts",
        "frontend/src/lib/sync/syncEvent.ts",
        "frontend/src/lib/sync/prohibitions.spec.ts",
        "frontend/src/lib/sync/eventFieldRules.spec.ts",
        "frontend/src/lib/sync/validateSyncEvent.spec.ts",
        *ORM_SCHEMA_MIGRATION_AREA_PATHS["data-migration"],
    ],
}
NEW_CORE_PATH_CHANGES = (
    "contracts/authz/auth-catalog.json",
    "frontend/src/lib/courseInputView.ts",
    "frontend/src/lib/format.ts",
    "backend/conftest.py",
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
    """実リポジトリの core-areas.json を持つ一時 git リポジトリを作る。

    Args:
        tmp_path: pytest が提供する一時ディレクトリ。

    Returns:
        実設定を初期コミットに含む一時リポジトリルート。
    """
    root = tmp_path / "repo"
    root.mkdir()
    run_git(root, "init", "-q", "-b", "feature/test")
    write_text(
        root,
        ".claude/core-areas.json",
        CORE_AREAS_PATH.read_text(encoding="utf-8"),
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


def load_core_guard_module() -> Any:
    """実際の core_guard.py を照合関数の正として読み込む。"""
    module_name = "core_guard_module"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
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
        and Path(path).name.startswith("test_authz_")
        and Path(path).suffix == ".py"
    )
    assert matches == expected_current
    assert all(Path(path).parent == Path("backend/tests") for path in matches)

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
    future_path = "backend/tests/test_authz_future.py"
    assert core_guard.matched_paths([future_path], tenant_only) == [future_path]
    assert not fnmatch.fnmatchcase(
        "backend/tests/db/test_authz_future.py", AUTHZ_BACKEND_TEST_PATTERN
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


def test_actual_core_area_paths_are_exact_expected_set():
    configuration = load_actual_core_areas()
    areas = configuration["areas"]
    assert isinstance(areas, list)
    actual_by_id = {area["id"]: area["paths"] for area in areas}

    assert len(actual_by_id) == len(areas), "コア領域 ID が重複している"
    assert actual_by_id == EXPECTED_AREA_PATHS


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


def test_schema_contract_test_population_does_not_depend_on_branch() -> None:
    """スキーマ契約テストの母集団がブランチの状態に依存しないと示す。"""
    population = schema_contract_test_paths()
    assert population, "backend/tests/ の母集団が空になっている"
    assert "backend/tests/test_operation_event_kind_contract.py" in population
    assert not any(
        name.startswith("backend/tests/db/test_authz_") for name in population
    ), "認可検証の資産まで巻き込んでいる"


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
