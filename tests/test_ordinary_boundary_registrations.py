"""通常保存の物理参照とcommitted再交付所有照合の有限登録を検証する。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "ordinary_boundary_checker_under_test", ROOT / "scripts/check_tenant_boundary_bypass.py"
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


@pytest.fixture(scope="module")
def state():
    """実sourceと同snapshotの再輸出写像を共有する。"""
    contract = checker.load_contract(ROOT)
    sources = {
        p.relative_to(ROOT / "backend/src").as_posix(): p.read_text()
        for p in (ROOT / "backend/src").rglob("*.py")
    }
    return contract, sources, checker._build_reexport_map(sources)


@pytest.mark.parametrize("index", [0, 1])
def test_ordinary_exact_source_and_each_site(state, index):
    """固定2path各8siteだけを許し、他条件は維持する。"""
    contract, sources, reexports = state
    assert len(contract.ordinary_condition2_owners) == 2
    owner = contract.ordinary_condition2_owners[index]
    assert len(owner.findings) == 8
    path = owner.path.removeprefix("backend/src/")
    source = sources[path]
    assert hashlib.sha256(source.encode()).hexdigest() == owner.source_sha256
    raw = checker.scan_source(
        source, path=path, contract=replace(contract, ordinary_condition2_owners=()),
        reexport_map=reexports,
    )
    actual = checker.scan_source(source, path=path, contract=contract, reexport_map=reexports)
    assert {(v.line, v.symbol, v.scope) for v in raw if v.code == "TB002"} == owner.findings
    assert actual == [v for v in raw if v.code != "TB002"]
    for changed, target in ((source + "\n", path), (source, "pitchlog/copy.py")):
        assert any(v.code == "TB002" for v in checker.scan_source(
            changed, path=target, contract=contract, reexport_map=reexports,
        ))
    malformed = replace(
        contract, ordinary_condition2_owners=list(contract.ordinary_condition2_owners),
    )
    assert any(v.code == "TB002" for v in checker.scan_source(
        source, path=path, contract=malformed, reexport_map=reexports,
    ))
    first = next(iter(owner.findings))
    incomplete = replace(owner, findings=owner.findings - {first})
    owners = tuple(incomplete if i == index else x
                   for i, x in enumerate(contract.ordinary_condition2_owners))
    assert any(v.code == "TB002" for v in checker.scan_source(
        source, path=path, contract=replace(contract, ordinary_condition2_owners=owners),
        reexport_map=reexports,
    ))


@pytest.mark.parametrize("mutation", [
    "missing-path", "extra-path", "duplicate-path", "path", "missing-site", "extra-site",
    "hash", "scope", "symbol", "line", "unknown-key",
])
def test_ordinary_registry_cannot_self_extend(mutation):
    """自己申告でpathや全siteを増減させない。"""
    asset = json.loads((ROOT / "contracts/tenant_boundary/base-allowlist.json").read_text())
    rows = asset["condition_2_ordinary_scoped_findings"]
    owner = rows[0]
    if mutation == "missing-path":
        rows.pop()
    elif mutation == "extra-path":
        other = copy.deepcopy(owner)
        other["path"] = "backend/src/pitchlog/unknown.py"
        rows.append(other)
    elif mutation == "duplicate-path":
        rows.append(copy.deepcopy(owner))
    elif mutation == "missing-site":
        owner["findings"].pop()
    elif mutation == "extra-site":
        other = copy.deepcopy(owner["findings"][0])
        other["line"] += 1
        owner["findings"].append(other)
    elif mutation == "unknown-key":
        owner["unknown"] = True
    elif mutation in {"path", "hash"}:
        owner["path" if mutation == "path" else "source_sha256"] = "unknown"
    else:
        owner["findings"][0][mutation] = 999 if mutation == "line" else "unknown"
    with pytest.raises(checker.ContractError):
        checker._load_ordinary_condition2_owners(rows)


@pytest.mark.parametrize("mutation", [
    "missing-field", "extra-key", "path", "fqname", "scope", "line", "bool-line", "symbol", "hash",
])
def test_resolution_registration_is_single_exact_finding(mutation):
    """再交付所有照合1点を未知ownerへ広げられない。"""
    row = json.loads((ROOT / "contracts/tenant_boundary/base-allowlist.json").read_text())[
        "condition_1_resolve_scoped_finding"
    ]
    if mutation == "missing-field":
        row.pop("scope")
    elif mutation == "extra-key":
        row["unknown"] = True
    else:
        key = (
            "line" if mutation == "bool-line"
            else "source_sha256" if mutation == "hash" else mutation
        )
        row[key] = True if mutation == "bool-line" else 946 if mutation == "line" else "unknown"
    with pytest.raises(checker.ContractError):
        checker._load_resolution_owner(row)


@pytest.mark.parametrize("mutation", [
    "stalehash", "deleted", "short-circuit", "predicate", "owner-value", "runtime",
    "lookup", "outcome", "context", "scope", "extra-owner", "copied-path",
])
def test_resolution_body_change_is_rejected_even_with_new_hash(state, mutation):
    """sourceとhashの同時自己申告でも所有条件を削除・追加・短絡できない。"""
    contract, sources, reexports = state
    path = "pitchlog/repositories/transaction.py"
    source = sources[path]
    assert checker.scan_source(source, path=path, contract=contract, reexport_map=reexports) == []
    start = source.index("def _assert_existing_resolution_owner(")
    end = source.index("\n\n@dataclass", start)
    prefix, body, suffix = source[:start], source[start:end], source[end:]
    changes = {
        "stalehash": body + "\n",
        "deleted": body.replace("        or not binding.looked_up\n", "", 1),
        "short-circuit": body.replace(
            "    binding = _RESOLVE_BINDINGS.get(handle._state_key)\n",
            "    return\n    binding = _RESOLVE_BINDINGS.get(handle._state_key)\n", 1,
        ),
        "predicate": body.replace(
            "        binding is None\n", "        binding is None or True\n", 1,
        ),
        "owner-value": body.replace(
            "        owner.request_digest,\n", "        owner.device_id,\n", 1,
        ),
        "runtime": body.replace("        or binding.runtime is not runtime\n", "", 1),
        "lookup": body.replace("        or not binding.device_checked\n", "", 1),
        "outcome": body.replace('        or binding.outcome != "committed"\n', "", 1),
        "context": body.replace("        or binding.context is not context\n", "", 1),
        "scope": body.replace(
            "def _assert_existing_resolution_owner(", "def _assert_other_owner(", 1,
        ),
        "extra-owner": body + "\n\ndef _assert_unknown_owner():\n    return True\n",
        "copied-path": body,
    }
    changed = prefix + changes[mutation] + suffix
    if mutation not in {"stalehash", "copied-path"}:
        owner = replace(contract.resolution_owner,
                        source_sha256=hashlib.sha256(changed.encode()).hexdigest())
        contract = replace(contract, resolution_owner=owner)
    if mutation == "copied-path":
        path = "pitchlog/copy.py"
    assert any(v.code == "TB001" for v in checker.scan_source(
        changed, path=path, contract=contract, reexport_map=reexports,
    ))
