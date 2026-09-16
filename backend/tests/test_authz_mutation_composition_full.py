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
    MutationCompositionError,
    frozen_oracle_paths,
    intentionally_changed_frozen_oracle_paths,
    load_oracle_meaning_baseline_commit,
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


def test_frozen_negative_tests_execute_as_exact_set() -> None:
    """凍結基準の負例が期待する集合と完全に一致する。"""
    marked_tests = {
        name
        for name, test in globals().items()
        if name.startswith("test_")
        and any(
            marker.name == "frozen_negative"
            for marker in getattr(test, "pytestmark", ())
        )
    }

    assert marked_tests == {
        "test_frozen_oracle_rejects_input_change_without_baseline_advance",
        "test_frozen_oracle_rejects_meaning_tampering_after_reseal",
    }


def test_resealed_oracle_input_matches_baseline() -> None:
    """再封印後の入力が基準commit・sealと三者一致する。"""
    verify_frozen_oracle_unchanged()


def test_oracle_meaning_reports_the_exact_declaration_it_uses(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """意味検査が現に用いた3指定を台帳と完全一致で出力する。"""
    verify_frozen_oracle_unchanged()
    line = capsys.readouterr().out.strip()
    prefix = "frozen-strategy-executed="
    assert line.startswith(prefix)
    used = json.loads(line.removeprefix(prefix))
    ledger = json.loads(
        (
            mutation_composition.REPOSITORY_ROOT
            / "contracts/authz/frozen-baselines.json"
        ).read_text(encoding="utf-8")
    )
    matches = [
        declaration
        for declaration in ledger["declarations"].values()
        if ORACLE_SEAL_RELATIVE_PATH in declaration["frozen_targets"]
    ]
    expected = dict(matches[0])
    expected["frozen_targets"] = sorted(expected["frozen_targets"])
    assert used == expected
    assert len(matches) == 1


def test_frozen_oracle_exclusions_match_the_resealed_canonical_assets() -> None:
    """基準からHEADへの意味差分を固定値なしで導出する。"""
    baseline_commit = load_oracle_meaning_baseline_commit()
    base_frozen = set(frozen_oracle_paths(base_ref=baseline_commit))
    current_frozen = set(frozen_oracle_paths())
    changed = intentionally_changed_frozen_oracle_paths()

    assert base_frozen == current_frozen
    assert changed <= current_frozen - {ORACLE_SEAL_RELATIVE_PATH}
    assert ORACLE_SEAL_RELATIVE_PATH in current_frozen


def _clone_repository(tmp_path: Path) -> Path:
    """負例用に凍結入力と現在の意味資産を持つ一時repositoryを作る。"""
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
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=root,
        check=True,
    )
    ledger_path = Path("contracts/authz/frozen-baselines.json")
    (root / ledger_path).write_bytes(
        (mutation_composition.REPOSITORY_ROOT / ledger_path).read_bytes()
    )
    seal = json.loads((root / ORACLE_SEAL_RELATIVE_PATH).read_text(encoding="utf-8"))
    oracle_commit = seal["oracle_commit"]
    for row in seal["input_assets"]:
        relative_path = row["path"]
        frozen = subprocess.run(
            ["git", "show", f"{oracle_commit}:{relative_path}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        assert frozen.returncode == 0, frozen.stderr.decode(errors="replace")
        (root / relative_path).write_bytes(frozen.stdout)
    return root


def test_oracle_meaning_baseline_can_advance_to_head_without_code_change(
    tmp_path: Path,
) -> None:
    """7.7-2: 基準をHEADへ進めると導出差分が空になり検査が通る。"""
    root = _clone_repository(tmp_path)
    test_source = root / "backend/tests/test_authz_mutation_composition_full.py"
    test_source_before = test_source.read_bytes()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ledger_path = root / "contracts/authz/frozen-baselines.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    declarations = ledger["declarations"]
    declaration = next(
        value
        for value in declarations.values()
        if ORACLE_SEAL_RELATIVE_PATH in value["frozen_targets"]
    )
    history = ledger["baselines"][declaration["basis_series"]]
    if history[-1]["commit"] != head:
        history.append(
            {
                "commit": head,
                "supersedes": history[-1]["commit"],
                "approved_by": "山田正輝",
                "approved_at": "2026-09-16",
                "reason": "oracle意味基準を現在へ進める正当経路の実証",
            }
        )
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    verify_frozen_oracle_unchanged(root)

    assert intentionally_changed_frozen_oracle_paths(root) == frozenset()
    assert test_source.read_bytes() == test_source_before


def _write_json(path: Path, value: object) -> None:
    """負例のJSONを通常のrepository形式で書き戻す。"""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.mark.frozen_negative
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
    subprocess.run(
        [
            "git",
            "add",
            boundary_path.relative_to(root).as_posix(),
            seal_path.relative_to(root).as_posix(),
        ],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "test: tamper oracle meaning"],
        cwd=root,
        check=True,
    )

    assert boundary_row["canonical_sha256"] == (
        mutation_composition._canonical_sha256(boundary)
    )
    with pytest.raises(MutationCompositionError, match="意味本文"):
        verify_frozen_oracle_unchanged(root)


@pytest.mark.frozen_negative
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
