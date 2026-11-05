"""安打の固定後発登録だけを検査し、旧原典・一般許可を置換しない。"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pr196_source_checker",
    ROOT / "scripts/check_tenant_boundary_bypass.py")
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)
EXPECTED = checker._pr196_read_fixed_expectations(ROOT)
ALL_SITES = [(p, i) for p, row in EXPECTED["owners"].items() for i in range(len(row["findings"]))]

def immutable_source(path, *, before=False):
    """現在sourceへfallbackせず固定Gitだけを返す。"""
    revision = EXPECTED["formal_base_revision" if before else "source_revision"]
    return subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT).decode()

def immutable_expectations():
    """期待Eの全byteを外部固定値から得る。"""
    return subprocess.check_output(["git",
        "show",
        checker._pr196_source_input_revisions(ROOT)[1] + ":" + checker._PR196_EXPECTED_FIXTURE],
        cwd=ROOT)

@pytest.fixture(scope="module")
def contract():
    """旧全登録と固定Eを実loaderで検証する。"""
    return checker.load_contract(ROOT)

@pytest.mark.parametrize("path", tuple(EXPECTED["owners"]))
def test_current_fixed_sources_only_resolve_declared_changes(contract, path):
    """models既49を許可せず、実changed-source人口で新差分だけを通す。"""
    source = immutable_source(path)
    assert (ROOT / path).read_text() == source
    relative = path.removeprefix("backend/src/")
    before = immutable_source(path, before=True)
    assert checker.scan_source_change(before,
        source,
        path=relative,
        contract=contract,
        changed_lines=set()) == []
    assert checker._pr196_source_evidence(source,
        relative,
        contract) == frozenset(tuple(s[k] for k in ("line",
        "code",
        "symbol",
        "scope")) for s in EXPECTED["owners"][path]["findings"])
    assert checker.scan_source_change(before,
        source,
        path=relative,
        contract=replace(contract,
        pr196_source_registration=None),
        changed_lines=set())
    assert not checker._pr196_source_evidence(source, "pitchlog/foreign.py", contract)

@pytest.mark.parametrize("path,index", ALL_SITES)
@pytest.mark.parametrize("mutation",
    ["missing",
    "duplicate",
    "line",
    "float",
    "bool",
    "condition",
    "code",
    "scope",
    "symbol",
    "purpose",
    "hash"])
def test_every_site_and_owner_is_exact(path, index, mutation):
    """15tupleの欠落/余剰/型/用途/hashを各1件でも変えれば拒否する。"""
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    value = copy.deepcopy(asset["pr196_source_registration"])
    row = value["owners"][path]
    site = row["findings"][index]
    if mutation == "missing":
        row["findings"].pop(index)
    elif mutation == "duplicate":
        row["findings"].append(copy.deepcopy(site))
    elif mutation == "float":
        site["line"] = float(site["line"])
    elif mutation == "bool":
        site["line"] = True
    elif mutation in {"purpose", "hash"}:
        row["purpose" if mutation == "purpose" else "source_sha256"] = "unapproved"
    else:
        site[mutation] = site["line"] + 1 if mutation == "line" else "unapproved"
    with pytest.raises(checker.ContractError):
        checker._load_pr196_source_owners(ROOT, value, asset)

@pytest.mark.parametrize("fault", ["extra", "missing", "sentinel", "field"])
def test_unknown_registration_cannot_expand_scope(fault):
    """identity sentinelを許可tupleへ混ぜたりownerを増やしたりしない。"""
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    value = copy.deepcopy(asset["pr196_source_registration"])
    path = next(iter(value["owners"]))
    if fault == "extra":
        value["owners"]["backend/src/pitchlog/foreign.py"] = copy.deepcopy(value["owners"][path])
    elif fault == "missing":
        value["owners"].pop(path)
    elif fault == "field":
        value["unapproved"] = True
    else:
        value["owners"][path]["findings"].append({"line":1,
        "condition":2,
        "code":"TB002",
        "symbol":"pr192-source-identity",
        "scope":"pitchlog.domainrt.lineup_prefix_source.<module>"})
    with pytest.raises(checker.ContractError):
        checker._load_pr196_source_owners(ROOT, value, asset)

@pytest.mark.parametrize("path", tuple(EXPECTED["owners"]))
def test_changed_bytes_and_claimed_hash_cannot_self_authorize(contract, path):
    """sourceとContract hashを同時に変えても固定Git資格にはならない。"""
    import hashlib
    source = immutable_source(path) + "\n# unknown source byte\n"
    registration = contract.pr196_source_registration
    forged = replace(registration,
        owners=tuple(replace(o,
        immutable_source=source.encode(),
        source_sha256=hashlib.sha256(source.encode()).hexdigest())
        if o.path == path else o for o in registration.owners))
    counterfeit = replace(contract, pr196_source_registration=forged)
    assert not checker._pr196_registration_is_trusted(counterfeit)
    assert not checker._pr196_source_evidence(source,
        path.removeprefix("backend/src/"),
        counterfeit)
    assert checker.scan_source_change(immutable_source(path,
        before=True),
        source,
        path=path.removeprefix("backend/src/"),
        contract=contract,
        changed_lines=set())

@pytest.mark.parametrize("fault",
    ["registration",
    "owners",
    "owner",
    "site",
    "path",
    "source",
    "contract"])
def test_equal_impostors_do_not_supply_evidence(contract, fault):
    """偽eq/派生tuple/str/Contractで閉じた証拠を偽装しない。"""
    class Equal:
        def __eq__(self, other):
            return True
        def __getattr__(self, name):
            return getattr(contract, name)
    class Sequence(tuple):
        __hash__ = tuple.__hash__
        def __eq__(self, other):
            return True
    class Text(str):
        pass
    registration = contract.pr196_source_registration
    owner = registration.owners[0]
    source = owner.immutable_source.decode()
    path = owner.path.removeprefix("backend/src/")
    if fault == "registration":
        registration = Equal()
    elif fault == "owners":
        registration = replace(registration, owners=Sequence(registration.owners))
    elif fault == "owner":
        registration = replace(registration, owners=(Equal(), *registration.owners[1:]))
    elif fault == "site":
        owner = replace(owner, findings=frozenset((Sequence(next(iter(owner.findings))),)))
        registration = replace(registration, owners=(owner, *registration.owners[1:]))
    elif fault == "path":
        path = Text(path)
    elif fault == "source":
        source = Text(source)
    counterfeit = Equal() if fault == "contract" else replace(contract,
        pr196_source_registration=registration)
    assert not checker._pr196_source_evidence(source, path, counterfeit)
    assert not checker._pr196_successor_matches(source, path, counterfeit)

def test_index_is_one_literal_not_general_db_permission(contract):
    """既49を消さず、新Index以外の任意textを拒否する。"""
    path = "backend/src/pitchlog/db/tenant_isolation/models.py"
    source = immutable_source(path)
    before = immutable_source(path, before=True)
    relative = path.removeprefix("backend/src/")
    assert len(checker._pr196_source_evidence(source, relative, contract)) == 1
    assert len(checker.scan_source(source, path=relative, contract=contract)) == 49
    changed = source + "\nprobe = text('SELECT 1')\n"
    assert not checker._pr196_source_evidence(changed, relative, contract)
    assert checker.scan_source_change(before,
        changed,
        path=relative,
        contract=contract,
        changed_lines=set())

def test_legacy_all_sites_and_maps_remain_unchanged(contract):
    """旧51/90site・不変6・全metadata/fixtureを別層のまま保持する。"""
    assert sum(len(o.findings) for o in contract.pr191_source_owners) == 51
    assert sum(len(o.findings) for o in contract.pr192_source_registration.owners) == 90
    assert checker._pr192_registration_is_trusted(contract)
    assert checker._pr196_registration_is_trusted(contract)
    assert immutable_expectations() == (ROOT / checker._PR196_EXPECTED_FIXTURE).read_bytes()
    asset = json.loads((ROOT / checker.DEFAULT_ALLOWLIST).read_text())
    assert all(checker._pr196_same_json(asset[k],
        v) for k,
        v in EXPECTED["preserved_state"]["owner_asset_fields"].items())

@pytest.fixture
def isolated_root(tmp_path):
    """負例は共有fixtureを編集せずcache内最小rootへ置く。"""
    import shutil
    (tmp_path / ".git").symlink_to(ROOT / ".git")
    for path in ["contracts/tenant_boundary/frozen-inputs.json",
        str(checker.DEFAULT_ALLOWLIST),
        checker._PR196_EXPECTED_FIXTURE,
        checker._PR192_EXPECTED_FIXTURE,
        checker._PR191_EXPECTED_FIXTURE]:
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, dest)
    return tmp_path

@pytest.mark.parametrize("fault",
    ["fixture",
    "symlink",
    "source",
    "expectation",
    "purpose",
    "consumer"])
def test_fixture_or_frozen_values_cannot_replace_e(isolated_root, fault):
    """現在fixture/両固定値の変更やsymlinkで前置Eを代替しない。"""
    path = isolated_root / checker._PR196_EXPECTED_FIXTURE
    frozen_path = isolated_root / "contracts/tenant_boundary/frozen-inputs.json"
    frozen = json.loads(frozen_path.read_text())
    if fault == "fixture":
        path.write_text(path.read_text()+"\n")
    elif fault == "symlink":
        path.unlink()
        path.symlink_to(ROOT / checker._PR196_EXPECTED_FIXTURE)
    else:
        key = (
            "pr196_source_registration_revision" if fault == "source"
            else "pr196_source_expectation_revision"
        )
        field = "value" if fault in {"source",
            "expectation"} else "purpose" if fault == "purpose" else "sources"
        frozen["frozen_inputs"][key][field] = "unapproved"
        frozen_path.write_text(json.dumps(frozen))
    with pytest.raises(checker.ContractError):
        checker._pr196_read_fixed_expectations(isolated_root)

@pytest.mark.parametrize("relation",
    ["source-head",
    "expectation-head",
    "source-expectation",
    "base-source"])
def test_real_git_ancestry_is_required(monkeypatch, relation):
    """一つでも真の祖先を失えば固定値だけを根拠にしない。"""
    original = checker._run_git
    pairs = {"source-head":(checker._pr196_source_input_revisions(ROOT)[0],
        "HEAD"),
        "expectation-head":(checker._pr196_source_input_revisions(ROOT)[1],
        "HEAD"),
        "source-expectation":(checker._pr196_source_input_revisions(ROOT)[0],
        checker._pr196_source_input_revisions(ROOT)[1]),
        "base-source":(EXPECTED["formal_base_revision"],
        checker._pr196_source_input_revisions(ROOT)[0])}
    def refuse(root, arguments):
        if arguments == ["merge-base","--is-ancestor",*pairs[relation]]:
            raise checker.ContractError("祖先なし")
        return original(root, arguments)
    monkeypatch.setattr(checker,"_run_git",refuse)
    with pytest.raises(checker.ContractError):
        checker._pr196_read_fixed_expectations(ROOT)


@pytest.mark.parametrize(
    "fault", ["missing", "extra", "bool", "short", "wrong", "purpose", "consumer"],
)
def test_typed_absolute_e_fixture_digest_is_not_self_derived(isolated_root, fault):
    """typed絶対SHAとE Gitblobは別照合し、現在木の自己期待へしない。"""
    path = isolated_root / "contracts/tenant_boundary/frozen-inputs.json"
    frozen = json.loads(path.read_text())
    key = "pr196_source_expectation_fixture_sha256"
    entry = frozen["frozen_inputs"][key]
    if fault == "missing":
        del frozen["frozen_inputs"][key]
    elif fault == "extra":
        entry["extra"] = True
    elif fault == "purpose":
        entry["purpose"] += " unapproved"
    elif fault == "consumer":
        entry["sources"] = []
    else:
        entry["value"] = {"bool": True, "short": "bad", "wrong": "0" * 64}[fault]
    path.write_text(json.dumps(frozen))
    with pytest.raises(checker.ContractError):
        checker._pr196_read_fixed_expectations(isolated_root)
