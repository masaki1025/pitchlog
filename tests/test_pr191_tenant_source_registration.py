"""PR191の不変Git原典・旧所有保持・新v2有限siteを検証する。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr191_source_checker", ROOT / "scripts/check_tenant_boundary_bypass.py"
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)
EXPECTED_PATH = ROOT / "tests/fixtures/pr191_tenant_source_expected_v1.json"
EXPECTED = json.loads(EXPECTED_PATH.read_text())


def immutable_source(path: str) -> str:
    """現在木のfallbackなしで用途付き固定Gitの全byteを読む。"""
    return subprocess.check_output(
        ["git", "show", EXPECTED["source_revision"] + ":" + path], cwd=ROOT,
    ).decode()


@pytest.fixture(scope="module")
def contract():
    """正式loaderが原典と独立fixtureを突合した契約を返す。"""
    return checker.load_contract(ROOT)


@pytest.mark.parametrize("path", list(EXPECTED["owners"]))
def test_v2_source_has_only_independently_fixed_sites(contract, path):
    """新枠を外すと独立期待のsiteだけが赤になり、他ownerへ移らない。"""
    source = immutable_source(path)
    assert source == (ROOT / path).read_text()
    relative = path.removeprefix("backend/src/")
    raw = checker.scan_source(source, path=relative,
                              contract=replace(contract, pr191_source_owners=()))
    expected = {tuple(site[key] for key in ("line", "code", "symbol", "scope"))
                for site in EXPECTED["owners"][path]["findings"]}
    assert {(v.line, v.code, v.symbol, v.scope) for v in raw} == expected
    assert checker.scan_source(source, path=relative, contract=contract) == []
    assert checker.scan_source(source, path="pitchlog/foreign_owner.py", contract=contract)


@pytest.mark.parametrize("mutation", [
    "missing", "extra", "purpose", "source_sha256", "line", "bool-line", "scope",
    "symbol", "code", "duplicate", "unknown-key", "fixture-path",
])
def test_v2_declaration_cannot_change_independent_site_set(mutation):
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    declaration = asset["pr191_source_registration"]
    owner = next(iter(declaration["owners"].values()))
    if mutation == "missing":
        declaration["owners"].pop(next(iter(declaration["owners"])))
    elif mutation == "extra":
        declaration["owners"]["backend/src/pitchlog/foreign.py"] = copy.deepcopy(owner)
    elif mutation == "duplicate":
        owner["findings"].append(copy.deepcopy(owner["findings"][0]))
    elif mutation == "unknown-key":
        owner["unknown"] = True
    elif mutation == "fixture-path":
        declaration["expected_fixture"] = "other.json"
    elif mutation in {"purpose", "source_sha256"}:
        owner[mutation] = "unknown"
    else:
        owner["findings"][0]["line" if mutation == "bool-line" else mutation] = (
            True if mutation == "bool-line" else 1 if mutation == "line" else "unknown"
        )
    with pytest.raises(checker.ContractError):
        checker._load_pr191_source_owners(ROOT, declaration)


@pytest.mark.parametrize("path", list(EXPECTED["owners"]))
def test_source_and_declared_hash_cannot_self_authorize(contract, path):
    source = immutable_source(path)
    changed = source + "\n# 原典全byteを変えたsourceを自己申告で受理しない。\n"
    owners = tuple(replace(owner, source_sha256=hashlib.sha256(changed.encode()).hexdigest())
                   if owner.path == path else owner for owner in contract.pr191_source_owners)
    assert checker.scan_source(changed, path=path.removeprefix("backend/src/"),
                               contract=replace(contract, pr191_source_owners=owners))
    owner = next(o for o in contract.pr191_source_owners if o.path == path)
    forged = replace(owner, source_sha256=hashlib.sha256(changed.encode()).hexdigest(),
                     immutable_source=changed.encode())
    owners = tuple(forged if o.path == path else o for o in contract.pr191_source_owners)
    assert checker.scan_source(changed, path=path.removeprefix("backend/src/"),
                               contract=replace(contract, pr191_source_owners=owners))


@pytest.mark.parametrize("old", [
    "recovery_generation: Annotated[int, Field(strict=True, gt=0)]",
    "return self.prefix_ref.generation",
])
def test_removed_schema_registrations_do_not_authorize_reintroduction(contract, old):
    source = (
        "from typing import Annotated\nfrom pydantic import Field\n"
        "class StartedRecordedPrefixGameRead:\n"
        "    def _prefix_correlations(self):\n        " + old + "\n"
    )
    assert "backend/src/pitchlog/api/schemas/started_games.py" not in (
        checker.ORDINARY_CONDITION2_SCOPES
    )
    assert any(v.code == "TB002" for v in checker.scan_source(
        source, path="pitchlog/api/schemas/started_games.py", contract=contract,
    ))


@pytest.mark.parametrize("mutation", ["hold", "destination", "responsibility", "after-runner"])
def test_runner_copy_cannot_drop_hold_or_recalculate_responsibility(contract, mutation):
    path = "backend/src/pitchlog/sync/terminal_pitch_projection.py"
    source = immutable_source(path)
    changed = {
        "hold": source.replace('effect.modality != "hold"', 'False', 1),
        "destination": source.replace('effect.destination is not None', 'False', 1),
        "responsibility": source.replace(
            'runner.responsible_pitcher_id', 'str(uuid5(play_id, "new"))', 1,
        ),
        "after-runner": source.replace(
            'for runner in before_runners', 'for runner in after_runners',
        ),
    }[mutation]
    assert changed != source
    owners = tuple(replace(o, source_sha256=hashlib.sha256(changed.encode()).hexdigest())
                   if o.path == path else o for o in contract.pr191_source_owners)
    assert any(v.code == "TB003" for v in checker.scan_source(
        changed, path=path.removeprefix("backend/src/"),
        contract=replace(contract, pr191_source_owners=owners),
    ))


@pytest.mark.parametrize("mutation", ["callback", "lifetime", "frame-type", "third-frame"])
def test_liveness_and_sealed_frame_are_not_generic_construction_permissions(contract, mutation):
    if mutation in {"callback", "lifetime"}:
        path = "backend/src/pitchlog/repositories/play_prefix.py"
        source = immutable_source(path)
        changed = source.replace('    live()\n', '    (lambda: None)()\n', 1)
        if mutation == "lifetime":
            changed = source.replace('_locked_prefix_context(handle, event, source)',
                                     '_locked_prefix_context(other_handle, event, source)', 1)
    else:
        path = "backend/src/pitchlog/sync/ordinary_pitch_execution.py"
        source = immutable_source(path)
        changed = 'object.__new__(OtherFrame)'.join(
            source.rsplit('object.__new__(OrdinaryPitchFrame)', 1)
        )
        if mutation == "third-frame":
            changed = source + '\ndef third():\n    return object.__new__(OrdinaryPitchFrame)\n'
    assert source != changed
    assert any(v.code == "TB007" for v in checker.scan_source(
        changed, path=path.removeprefix("backend/src/"), contract=contract,
    ))


@pytest.mark.parametrize("mutation", ["play-prefix-type", "field-type", "unknown-bind"])
def test_play_prefix_fixed_builder_is_an_exact_complete_shape(mutation):
    """既3完全形を変えず、新bigint枝だけの一般化も拒否する。"""
    import ast

    source = immutable_source("backend/src/pitchlog/repositories/function_operations.py")
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == "_build_fixed_function_statement")
    assert checker._is_fixed_builder_body(node, checker._FIXED_BUILDER_BODY)
    function_source = ast.get_source_segment(source, node)
    assert function_source is not None
    changed = {
        "play-prefix-type": function_source.replace(
            "in _SYNC_PLAY_PREFIX_FUNCTION_TYPES", "in anything", 1,
        ),
        "field-type": function_source.replace("and field_type is int", "and field_type is str", 1),
        "unknown-bind": function_source.replace('"wire_history_version",', '"unknown_bind",', 1),
    }[mutation]
    assert changed != function_source
    changed_node = next(n for n in ast.parse(changed).body
                        if isinstance(n, ast.FunctionDef)
                        and n.name == "_build_fixed_function_statement")
    assert not checker._is_fixed_builder_body(changed_node, checker._FIXED_BUILDER_BODY)
