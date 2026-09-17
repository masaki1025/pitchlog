"""ステップ20の全資産をDBなしで実行する。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from db.authz import mutation_composition
from db.authz.mutation_composition import (
    ORACLE_SEAL_RELATIVE_PATH,
    STEP2_BASE_REVISION,
    STEP2_CHANGED_CANONICAL_ASSET_PATHS,
    MutationCompositionError,
    frozen_oracle_paths,
    intentionally_changed_frozen_oracle_paths,
    load_step20_catalog,
    run_step20,
    select_step20_work,
    step20_selection_from_environment,
    verify_frozen_oracle_unchanged,
)


def test_step20_asset_populations_execute_as_exact_sets() -> None:
    """選択した相互作用・cut set・MC/DC pairを全件実行する。"""
    catalog = load_step20_catalog()
    selection = step20_selection_from_environment(os.environ)
    interactions, cut_sets, mcdc_pairs = select_step20_work(catalog, selection)

    result = run_step20(catalog, selection)

    assert {row.interaction_id for row in result.interactions} == {
        row.interaction_id for row in interactions
    }
    assert {row.cut_set_id for row in result.cut_sets} == {
        row.cut_set_id for row in cut_sets
    }
    assert {(row.decision_id, row.condition_id) for row in result.mcdc_pairs} == {
        (row.decision_id, row.condition_id) for row in mcdc_pairs
    }


def test_frozen_oracle_paths_have_no_branch_diff() -> None:
    """入力baselineとポインタを除くoracle意味本文が固定されている。"""
    verify_frozen_oracle_unchanged()


def test_frozen_oracle_exclusions_match_the_resealed_canonical_assets() -> None:
    """099a8fa基準からポインタを除くoracle意味差分がゼロである。"""
    base_frozen = set(frozen_oracle_paths(base_ref=STEP2_BASE_REVISION))
    current_frozen = set(frozen_oracle_paths())
    changed = intentionally_changed_frozen_oracle_paths()

    assert base_frozen == current_frozen
    assert changed == STEP2_CHANGED_CANONICAL_ASSET_PATHS
    assert changed < current_frozen
    assert ORACLE_SEAL_RELATIVE_PATH in current_frozen


def _clone_repository(tmp_path: Path) -> Path:
    """負例用に現在のHEADと履歴を持つ一時repositoryを作る。"""
    root = tmp_path / "repository"
    result = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            str(mutation_composition.REPOSITORY_ROOT),
            str(root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return root


def _write_json(path: Path, value: object) -> None:
    """負例のJSONを通常のrepository形式で書き戻す。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_frozen_oracle_rejects_meaning_tampering_after_reseal(
    tmp_path: Path,
) -> None:
    """意味本文とsealを同時に改ざんしても固定基準との差分でredになる。"""
    root = _clone_repository(tmp_path)
    boundary_path = root / "contracts/authz/boundary-proposal.json"
    seal_path = root / ORACLE_SEAL_RELATIVE_PATH
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    control = next(
        row
        for row in boundary["boundaries"]
        if row["boundary_id"] == "BOUNDARY:CONTROL-READS"
    )
    control["responsibility"] = "return_all_tenants_control_rows_without_filter"
    boundary_row = next(
        row
        for row in seal["sealed_assets"]
        if row["path"] == "contracts/authz/boundary-proposal.json"
    )
    boundary_row["canonical_sha256"] = mutation_composition._canonical_sha256(boundary)
    _write_json(boundary_path, boundary)
    _write_json(seal_path, seal)

    assert boundary_row["canonical_sha256"] == (
        mutation_composition._canonical_sha256(boundary)
    )
    with pytest.raises(MutationCompositionError, match="意味本文"):
        verify_frozen_oracle_unchanged(root)


def test_frozen_oracle_rejects_input_change_without_baseline_advance(
    tmp_path: Path,
) -> None:
    """sealのoracle_commitを進めない入力資産変更を三者照合でredにする。"""
    root = _clone_repository(tmp_path)
    seal = json.loads((root / ORACLE_SEAL_RELATIVE_PATH).read_text(encoding="utf-8"))
    input_path = root / seal["input_assets"][0]["path"]
    input_path.write_bytes(input_path.read_bytes() + b" ")

    with pytest.raises(MutationCompositionError, match="三者不一致"):
        verify_frozen_oracle_unchanged(root)
