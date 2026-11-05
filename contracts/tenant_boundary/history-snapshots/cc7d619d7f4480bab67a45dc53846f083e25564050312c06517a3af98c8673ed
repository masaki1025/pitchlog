"""PR192の別固定期待・旧所有保持・v3有限登録と偽造拒否を検査する。"""

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
    "pr192_source_checker", ROOT / "scripts/check_tenant_boundary_bypass.py"
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)
EXPECTED = checker._pr192_read_fixed_expectations(ROOT)
OWNER_PATHS = tuple(EXPECTED["owners"])
ALL_SITES = [(path, i) for path in OWNER_PATHS
             for i in range(len(EXPECTED["owners"][path]["findings"]))]


def immutable_source(path: str) -> str:
    """現sourceへのfallbackなしで製品の固定Gitを読む。"""
    return subprocess.check_output(
        ["git", "show", EXPECTED["source_revision"] + ":" + path], cwd=ROOT,
    ).decode()


def immutable_expectations() -> bytes:
    """前置fixtureの別固定Gitを取得する。"""
    frozen = json.loads((ROOT / "contracts/tenant_boundary/frozen-inputs.json").read_text())
    revision = frozen["frozen_inputs"]["pr192_source_expectation_revision"]["value"]
    return subprocess.check_output(
        ["git", "show", revision + ":" + checker._PR192_EXPECTED_FIXTURE], cwd=ROOT,
    )


@pytest.fixture(scope="module")
def contract():
    """全前後と固定原典を検査した実loaderの契約。"""
    return checker.load_contract(ROOT)


@pytest.mark.parametrize("path", OWNER_PATHS)
def test_current_v3_source_keeps_old_owner_and_exact_finite_sites(contract, path):
    """歴史viewだけで現v3を成功とせず、現sourceの全byte/拒否を確認する。"""
    source = immutable_source(path)
    current = (ROOT / path).read_text()
    if path in {
        "backend/src/pitchlog/domainrt/lineup_play_prefix_continuation.py",
        "backend/src/pitchlog/domainrt/lineup_prefix_source.py",
    } and contract.pr196_source_registration is not None:
        assert checker._pr196_successor_matches(
            current, path.removeprefix("backend/src/"), contract,
        )
    else:
        assert source == current
    relative = path.removeprefix("backend/src/")
    expected = {tuple(s[k] for k in ("line", "code", "symbol", "scope"))
                for s in EXPECTED["owners"][path]["findings"]}
    without = checker.scan_source(source, path=relative,
        contract=replace(contract, pr192_source_registration=None))
    assert expected <= {(v.line, v.code, v.symbol, v.scope) for v in without}
    assert checker.scan_source(source, path=relative, contract=contract) == []
    assert checker.scan_source(source, path="pitchlog/foreign_owner.py", contract=contract)


@pytest.mark.parametrize(("path", "index"), ALL_SITES)
def test_every_old45_and_new45_site_is_required(path, index):
    """全90siteを各1件欠いても固定期待との不一致を拒否する。"""
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    declaration = copy.deepcopy(asset["pr192_source_registration"])
    declaration["owners"][path]["findings"].pop(index)
    with pytest.raises(checker.ContractError):
        checker._load_pr192_source_owners(ROOT, declaration, asset)


@pytest.mark.parametrize("mutation", [
    "owner-missing", "owner-extra", "purpose", "sha", "line", "condition", "scope",
    "symbol", "code", "duplicate", "unknown", "fixture", "sentinel",
])
def test_unknown_owner_or_site_and_old_guard_sentinel_cannot_be_registered(mutation):
    """旧guardのC7を新免除にせず、別scope/不明siteも拒否する。"""
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    declaration = copy.deepcopy(asset["pr192_source_registration"])
    owner = declaration["owners"][OWNER_PATHS[0]]
    if mutation == "owner-missing":
        declaration["owners"].pop(OWNER_PATHS[0])
    elif mutation == "owner-extra":
        declaration["owners"]["backend/src/pitchlog/foreign.py"] = copy.deepcopy(owner)
    elif mutation in {"purpose", "sha"}:
        owner["purpose" if mutation == "purpose" else "source_sha256"] = "unknown"
    elif mutation == "duplicate":
        owner["findings"].append(copy.deepcopy(owner["findings"][0]))
    elif mutation == "unknown":
        owner["unknown"] = True
    elif mutation == "fixture":
        declaration["expected_fixture"] = "other.json"
    elif mutation == "sentinel":
        owner["findings"].append({"line": 614, "condition": 7, "code": "TB007",
            "symbol": "builtins.object.__new__",
            "scope": "pitchlog.sync.ordinary_pitch_execution._evaluate_play_prefix"})
    else:
        owner["findings"][0][mutation] = True if mutation in {"line", "condition"} else "unknown"
    with pytest.raises(checker.ContractError):
        checker._load_pr192_source_owners(ROOT, declaration, asset)


@pytest.mark.parametrize("index", range(37))
def test_all_37_existing_owner_metadata_must_match_fixed_after_values(index):
    """旧所有者の判定を削らず、追随先37件を各1件変えた宣言を拒否する。"""
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    update = EXPECTED["existing_owner_followups"][index]
    key, path = update["owner_key"], update["path"]
    if key == "condition_1_resolve_scoped_finding":
        asset[key]["line"] += 1
    else:
        findings = asset[key][path]["findings"]
        matches = [i for i, row in enumerate(findings)
                   if all(row[k] == update["after"][k] for k in row)]
        assert len(matches) == 1
        findings.pop(matches[0])
    with pytest.raises(checker.ContractError):
        checker._load_pr192_source_owners(ROOT, asset["pr192_source_registration"], asset)


@pytest.fixture
def isolated_expectations(tmp_path):
    """原repoへ書かず、実object/真正祖先を持つ自前repoだけを変更する。"""
    root = tmp_path / "reference"
    root.mkdir()
    for path in (str(checker.DEFAULT_ALLOWLIST), "contracts/tenant_boundary/frozen-inputs.json",
                 checker._PR192_EXPECTED_FIXTURE, checker._PR191_EXPECTED_FIXTURE):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    objects = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "objects"], cwd=ROOT,
    ).decode().strip()
    (root / ".git/objects/info/alternates").write_text(objects + "\n")
    frozen = json.loads((root / "contracts/tenant_boundary/frozen-inputs.json").read_text())
    revision = frozen["frozen_inputs"]["pr192_source_expectation_revision"]["value"]
    subprocess.run(["git", "update-ref", "HEAD", revision], cwd=root, check=True)
    return root


@pytest.mark.parametrize("mutation", [
    "joint-fixture-declaration", "fixture-missing", "fixture-symlink", "old-fixture",
    "source-pin", "expectation-pin", "purpose", "consumer", "source-anchor-order",
])
def test_current_fixture_declaration_and_pins_cannot_replace_fixed_git(
    isolated_expectations, mutation,
):
    """別固定原典を残し、現在decl/fixture/hashの同時変更も拒否する。"""
    root = isolated_expectations
    asset = json.loads((root / checker.DEFAULT_ALLOWLIST).read_text())
    fixture = root / checker._PR192_EXPECTED_FIXTURE
    frozen_path = root / "contracts/tenant_boundary/frozen-inputs.json"
    frozen = json.loads(frozen_path.read_text())
    if mutation == "joint-fixture-declaration":
        data = json.loads(fixture.read_text())
        data["owners"][OWNER_PATHS[0]]["findings"][0]["line"] += 1
        fixture.write_text(json.dumps(data))
        asset["pr192_source_registration"]["owners"] = data["owners"]
    elif mutation == "fixture-missing":
        fixture.unlink()
    elif mutation == "fixture-symlink":
        raw = fixture.read_bytes()
        fixture.unlink()
        target = root / "other.json"
        target.write_bytes(raw)
        fixture.symlink_to(target)
    elif mutation == "old-fixture":
        (root / checker._PR191_EXPECTED_FIXTURE).write_text("{}")
    elif mutation == "source-pin":
        frozen["frozen_inputs"]["pr192_source_registration_revision"]["value"] = "HEAD"
    elif mutation == "expectation-pin":
        frozen["frozen_inputs"]["pr192_source_expectation_revision"]["value"] = (
            EXPECTED["source_revision"]
        )
    elif mutation == "source-anchor-order":
        frozen["frozen_inputs"]["pr192_source_registration_revision"]["value"] = (
            frozen["frozen_inputs"]["pr192_source_expectation_revision"]["value"]
        )
    else:
        entry = frozen["frozen_inputs"]["pr192_source_registration_revision"]
        entry["purpose" if mutation == "purpose" else "sources"] = "unknown"
    frozen_path.write_text(json.dumps(frozen, ensure_ascii=False))
    with pytest.raises(checker.ContractError):
        checker._load_pr192_source_owners(root, asset["pr192_source_registration"], asset)


@pytest.mark.parametrize("relation", ["source-head", "expectation-head", "source-expectation"])
def test_actual_fixed_git_ancestry_is_required(monkeypatch, relation):
    """参照値が同じでも非祖先の実原典へ置き換えない。"""
    original = checker._run_git
    frozen = json.loads((ROOT / "contracts/tenant_boundary/frozen-inputs.json").read_text())
    source = EXPECTED["source_revision"]
    expectation = frozen["frozen_inputs"]["pr192_source_expectation_revision"]["value"]
    pair = {"source-head": (source, "HEAD"), "expectation-head": (expectation, "HEAD"),
            "source-expectation": (source, expectation)}[relation]
    seen = []
    def run(root, args):
        if args == ["merge-base", "--is-ancestor", *pair]:
            seen.append(True)
            raise checker.ContractError("合成非祖先")
        return original(root, args)
    monkeypatch.setattr(checker, "_run_git", run)
    with pytest.raises(checker.ContractError):
        checker._pr192_read_fixed_expectations(ROOT)
    assert seen == [True]


@pytest.mark.parametrize("path", sorted(
    {f["path"] for f in EXPECTED["existing_owner_followups"]} | set(OWNER_PATHS),
))
def test_whole_source_and_declared_hash_cannot_self_authorize(contract, path):
    """source/declared hash/不変bytesを一緒に変えても真正registryに一致しない。"""
    source = immutable_source(path)
    changed = source + "\n# 固定原典からの後発差分\n"
    registration = contract.pr192_source_registration
    owners = tuple(replace(o, source_sha256=hashlib.sha256(changed.encode()).hexdigest(),
                           immutable_source=changed.encode()) if o.path == path else o
                   for o in registration.owners)
    files = tuple((p, changed.encode() if p == path else raw)
                  for p, raw in registration.source_files)
    forged = replace(registration, owners=owners, source_files=files)
    actual = checker.scan_source(changed, path=path.removeprefix("backend/src/"),
        contract=replace(contract, pr192_source_registration=forged))
    assert any(v.symbol == "pr192-source-identity" for v in actual)


@pytest.mark.parametrize("mutation", ["live", "frame", "builder", "resolution", "erase"])
def test_private_callbacks_frames_and_resolution_are_not_general_permissions(contract, mutation):
    path = {"live": "backend/src/pitchlog/repositories/play_prefix.py",
            "frame": "backend/src/pitchlog/sync/ordinary_pitch_execution.py",
            "builder": "backend/src/pitchlog/sync/terminal_pitch_projection.py",
            "resolution": "backend/src/pitchlog/repositories/transaction.py",
            "erase": "backend/src/pitchlog/repositories/ordinary_prefix_operations.py"}[mutation]
    source = immutable_source(path)
    changed = {"live": source.replace("    live()\n", "    arbitrary_callback()\n", 1),
               "frame": source.replace("object.__new__(OrdinaryPitchFrame)",
                                       "object.__new__(TenantContext)"),
               "builder": source.replace("prepared = builder(", "prepared = arbitrary_callback("),
               "resolution": source.replace("binding.context is not context", "False"),
               "erase": "x = 1\n"}[mutation]
    assert changed != source
    assert checker.scan_source(changed, path=path.removeprefix("backend/src/"), contract=contract)


def test_predecessor_693_and_old6_owners_are_preserved(contract):
    """後継は旧fixture/原典/旧6宣言を変更する許可ではない。"""
    assert immutable_expectations() == (ROOT / checker._PR192_EXPECTED_FIXTURE).read_bytes()
    raw = (ROOT / checker._PR191_EXPECTED_FIXTURE).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED["preserved_pr191_fixture_sha256"]
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    baseline = json.loads(subprocess.check_output(
        ["git", "show", EXPECTED["formal_base_revision"] + ":" + str(checker.DEFAULT_ALLOWLIST)],
        cwd=ROOT,
    ))
    assert asset["pr191_source_registration"] == baseline["pr191_source_registration"]
    assert len(contract.pr191_source_owners) == 6
    assert len(contract.pr192_source_registration.owners) == 6
    assert sum(len(o.findings) for o in contract.pr192_source_registration.owners) == 90


@pytest.mark.parametrize("current", [True, False])
def test_shared_synthetic_git_parent_preserves_current_and_legacy_origins(
    tmp_path, monkeypatch, current,
):
    """archiveと共用する準備で、実objectの新前置祖先/旧693を分離する。"""
    import test_check_tenant_boundary_bypass as shared

    original_copy = shared.shutil.copytree
    if not current:
        def historical_copy(source, destination, *args, **kwargs):
            result = original_copy(source, destination, *args, **kwargs)
            if Path(source) == ROOT / "contracts/tenant_boundary":
                asset_path = Path(destination) / "base-allowlist.json"
                value = json.loads(asset_path.read_text())
                value.pop("pr192_source_registration", None)
                value.pop("pr196_source_registration", None)
                asset_path.write_text(json.dumps(value, ensure_ascii=False))
            return result
        monkeypatch.setattr(shared.shutil, "copytree", historical_copy)
    repository, baseline = shared._initialize_test_repository(tmp_path, {})
    frozen = json.loads((ROOT / "contracts/tenant_boundary/frozen-inputs.json").read_text())
    wanted = (
        frozen["frozen_inputs"]["pr196_source_expectation_revision"]["value"] if current
        else json.loads((ROOT / checker._PR191_EXPECTED_FIXTURE).read_text())["source_revision"]
    )
    assert shared.checker._run_git(repository, ["rev-parse", baseline + "^"]).strip() == wanted
    shared.checker._run_git(repository, ["merge-base", "--is-ancestor", wanted, baseline])


@pytest.mark.parametrize("kind", ["object", "tuple"])
def test_forged_equal_objects_cannot_authorize_an_unregistered_owner(contract, kind):
    """偽eqを使ったContract注入で無関係な世代アクセスを免除できない。"""
    source = "generation = 1\n"
    path = "pitchlog/services/unregistered.py"
    owner = checker.Pr191SourceOwner("backend/src/" + path, "forged",
        hashlib.sha256(source.encode()).hexdigest(),
        frozenset({(1, "TB002", "generation", "pitchlog.services.unregistered.<module>")}),
        source.encode())
    class EqualTuple(tuple):
        def __eq__(self, other):
            return True
    if kind == "object":
        class EqualRegistration:
            owners = (owner,)
            def __eq__(self, other):
                return True
        forged = EqualRegistration()
    else:
        forged = replace(contract.pr192_source_registration, owners=EqualTuple((owner,)))
    assert checker.scan_source(source, path=path,
        contract=replace(contract, pr192_source_registration=forged))
