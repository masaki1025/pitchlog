"""native197の有限source登録は前置原典と実callだけを受ける。"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

TEST_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST_ROOT / "scripts"))
from scripts import frozen_history  # noqa: E402

SOURCE_ROOT = Path(os.environ.get("PITCHLOG_PR197_SOURCE_ROOT", TEST_ROOT))
FIXTURE = TEST_ROOT / "tests/fixtures/pr197_tenant_source_expected_v1.json"
REVISION = frozen_history.read_original_pr197_pin("pr197_source_revision")


def _checker():
    """候補の検査器を共有repositoryへ書かず読み込む。"""
    script = TEST_ROOT / "scripts/check_tenant_boundary_bypass.py"
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("pr197_candidate_checker", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _checker()


@pytest.fixture(scope="module")
def expected():
    return json.loads(FIXTURE.read_text())


def _git_bytes(path: str) -> bytes:
    return _git_bytes_at(REVISION, path)


def _git_bytes_at(revision: str, path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{revision}:{path}"], cwd=SOURCE_ROOT
    )


def _declaration(checker, expected):
    return {
        "expected_fixture": checker._PR197_EXPECTED_FIXTURE,
        "owners": {
            path: {key: owner[key] for key in ("purpose", "source_sha256", "findings")}
            for path, owner in expected["owners"].items()
        },
    }


def _copy_fixed(root: Path, paths: set[str]) -> None:
    for path in sorted(paths):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git_bytes(path))


def _setup_loader(tmp_path, checker, expected, monkeypatch):
    _copy_fixed(
        tmp_path, set(expected["owners"]) | {checker._PR197_GENERATED_FACTS}
    )
    monkeypatch.setattr(checker, "_pr197_fixed_expectations", lambda _root: expected)
    monkeypatch.setattr(checker, "_load_pr196_source_owners", lambda *_: None)
    monkeypatch.setattr(
        checker, "_pr192_read_fixed_expectations",
        lambda _root: json.loads(
            (SOURCE_ROOT / "tests/fixtures/pr192_tenant_source_expected_v1.json").read_text()
        ),
    )
    monkeypatch.setattr(
        checker, "_pr192_git_bytes", lambda _root, revision, path: _git_bytes_at(revision, path)
    )
    return _declaration(checker, expected)


def test_pr197_source_registration_is_finite_and_holds_three(
    tmp_path, monkeypatch, checker, expected
):
    """71実siteのみを読み、保留3と旧identityをsite抑止しない。"""
    declaration = _setup_loader(tmp_path, checker, expected, monkeypatch)
    registered = checker._load_pr197_source_owners(
        tmp_path, declaration, {"pr196_source_registration": {}}
    )
    assert len(registered.owners) == 15
    assert sum(len(owner.findings) for owner in registered.owners) == 71
    assert len(registered.sql_paths) == 3
    assert registered.identity_successor_paths == checker._PR197_IDENTITY_PATHS
    held = {
        (site["path"], site["line"], site["code"], site["symbol"])
        for site in expected["held_findings"]
    }
    assert all(
        (owner.path, line, code, symbol) not in held
        for owner in registered.owners
        for line, code, symbol, _scope in owner.findings
    )
    monkeypatch.setattr(checker, "_pr197_registration_is_trusted", lambda _: True)
    monkeypatch.setattr(checker, "_pr197_trusted_source_registration", lambda: registered)
    for path in registered.identity_successor_paths:
        owner = next(o for o in registered.owners if o.path == path)
        relative = path.removeprefix("backend/src/")
        assert checker._pr197_identity_successor_matches(
            owner.immutable_source.decode(), relative, None,
        )
        assert not checker._pr197_identity_successor_matches(
            owner.immutable_source.decode() + "\n# changed\n", relative, None,
        )
        assert not checker._pr197_identity_successor_matches(
            owner.immutable_source.decode(), relative + ".clone", None,
        )
    reader = next(
        o for o in registered.owners if o.path.endswith("/play_export_primitives.py")
    )
    evidence = checker._pr197_source_evidence(
        reader.immutable_source.decode(),
        reader.path.removeprefix("backend/src/"),
        None,
    )
    assert len(evidence) == 5
    assert all(line != 290 for line, *_ in evidence)
    assert not checker._pr197_source_evidence(
        reader.immutable_source.decode() + "\n# changed\n",
        reader.path.removeprefix("backend/src/"), None,
    )


@pytest.mark.parametrize("mutation", [
    "missing_path", "unknown_path", "old_ast_owner", "old_followup", "current_followup",
    "old_pr191_owner", "old_pr192_owner", "frame_operation", "read_operation",
    "fake_handle", "wrong_sql", "wrong_frame_type", "extra_frame_call",
])
def test_pr197_identity_successor_rejects_profile_and_source_changes(
    tmp_path, monkeypatch, checker, expected, mutation
):
    """旧owner/新callの改竄と別型frame・別SQLをidentity後継にしない。"""
    expected = copy.deepcopy(expected)
    declaration = _setup_loader(tmp_path, checker, expected, monkeypatch)
    profile = expected["identity_successor"]
    transaction = "backend/src/pitchlog/repositories/transaction.py"
    ordinary = "backend/src/pitchlog/sync/ordinary_pitch_execution.py"
    if mutation == "missing_path":
        del profile["paths"][transaction]
    elif mutation == "unknown_path":
        profile["paths"]["backend/src/pitchlog/repositories/fake.py"] = copy.deepcopy(
            profile["paths"][transaction]
        )
    elif mutation == "old_ast_owner":
        profile["paths"][transaction]["legacy_functions"][0] = "_fake_owner"
    elif mutation == "old_followup":
        profile["paths"][transaction]["moved_followups"][0]["old"]["symbol"] = "fake"
    elif mutation == "current_followup":
        profile["paths"][transaction]["moved_followups"][0]["current"]["line"] = 1
    elif mutation == "old_pr191_owner":
        profile["pr191_ordinary_owner"]["findings"][0]["line"] = 615
    elif mutation == "old_pr192_owner":
        profile["pr192_ordinary_owner"]["findings"][0]["line"] = 629
    elif mutation == "frame_operation":
        profile["paths"][ordinary]["call_operations_sha256"]["644"] = "0" * 64
    elif mutation == "read_operation":
        profile["paths"][transaction]["call_operations_sha256"]["893"] = "0" * 64
    else:
        path = transaction if mutation in {"fake_handle", "wrong_sql"} else ordinary
        target = tmp_path / path
        source = target.read_text()
        if mutation == "fake_handle":
            source += "\ndef clone_fake_handle():\n    return object.__new__(TenantContext)\n"
        elif mutation == "wrong_sql":
            source = source.replace(
                "session.execute(call.statement, call.parameters)",
                'session.execute("SELECT * FROM sync_fence.stats_fact_versions")',
                1,
            )
        elif mutation == "wrong_frame_type":
            source = source.replace(
                "object.__new__(OrdinaryPitchFrame)",
                "object.__new__(TenantContext)", 1,
            )
        else:
            source += "\ndef extra_frame():\n    return object.__new__(OrdinaryPitchFrame)\n"
        target.write_text(source)
    with pytest.raises(checker.ContractError):
        checker._load_pr197_source_owners(
            tmp_path, declaration, {"pr196_source_registration": {}},
        )


def test_pr197_identity_successor_only_resolves_three_old_diagnostics(
    tmp_path, monkeypatch, checker, expected
):
    """実scanで旧identity3だけを後継判定し、71実siteを別に閉じる。"""
    pr196_loader = checker._load_pr196_source_owners
    declaration = _setup_loader(tmp_path, checker, expected, monkeypatch)
    registered = checker._load_pr197_source_owners(
        tmp_path, declaration, {"pr196_source_registration": {}},
    )
    monkeypatch.setattr(checker, "_load_pr196_source_owners", pr196_loader)
    shadow = SOURCE_ROOT
    pr192 = json.loads(
        (SOURCE_ROOT / "tests/fixtures/pr192_tenant_source_expected_v1.json").read_text()
    )
    metadata = checker._pr192_expected_metadata(shadow, pr192)
    monkeypatch.setattr(checker, "_pr192_trusted_materials", lambda: (pr192, metadata))
    contract = replace(checker.load_contract(shadow), pr197_source_registration=None)
    monkeypatch.setattr(
        checker, "_pr191_trusted_source_owners", lambda: contract.pr191_source_owners,
    )
    monkeypatch.setattr(
        checker, "_pr192_trusted_source_registration",
        lambda: contract.pr192_source_registration,
    )
    monkeypatch.setattr(
        checker, "_pr196_trusted_source_registration",
        lambda: contract.pr196_source_registration,
    )
    monkeypatch.setattr(checker, "_pr197_trusted_source_registration", lambda: registered)
    reexports = checker._build_reexport_map(checker._git_snapshot(SOURCE_ROOT, "HEAD"))
    before, after = [], []
    successor_contract = replace(contract, pr197_source_registration=registered)
    for path in sorted(registered.identity_successor_paths):
        relative = path.removeprefix("backend/src/")
        source = (SOURCE_ROOT / path).read_text()
        before.extend(checker.scan_source(
            source, path=relative, contract=contract, reexport_map=reexports,
        ))
        after.extend(checker.scan_source(
            source, path=relative, contract=successor_contract, reexport_map=reexports,
        ))
    held = {(site["line"], site["code"], site["symbol"])
            for site in expected["held_findings"]}
    assert held <= {(v.line, v.code, v.symbol) for v in before}
    assert not after
    transaction = "backend/src/pitchlog/repositories/transaction.py"
    reject_all = checker.scan_source(
        (SOURCE_ROOT / transaction).read_text(),
        path=transaction.removeprefix("backend/src/"),
        contract=successor_contract,
        reexport_map=reexports,
        reject_all_db_calls=True,
    )
    assert any(v.line == 893 and v.code == "TB900" for v in reject_all)


@pytest.mark.parametrize("mutation", [
    "unknown_code", "hold_site", "operation", "extra_owner", "extra_sql",
    "privileged_clone", "source_sha", "new_namespace", "generated_artifact",
])
def test_pr197_rejects_extra_authority_even_with_declaration_changed(
    tmp_path, monkeypatch, checker, expected, mutation
):
    """宣言も同時変更しても未知code/SQL/role clone等を拒否する。"""
    expected = copy.deepcopy(expected)
    declaration = _setup_loader(tmp_path, checker, expected, monkeypatch)
    startup = "backend/src/pitchlog/db/current_product_startup.py"
    if mutation == "unknown_code":
        expected["owners"][startup]["findings"][0]["code"] = "TB999"
    elif mutation == "hold_site":
        held = expected["held_findings"][0]
        expected["owners"][held["path"]]["findings"].append(
            {key: held[key] for key in ("line", "condition", "code", "symbol", "scope")}
        )
    elif mutation == "operation":
        expected["owners"][startup]["call_operations_sha256"]["237"] = "0" * 64
    elif mutation == "extra_owner":
        expected["owners"]["backend/src/pitchlog/stats/rogue.py"] = copy.deepcopy(
            expected["owners"][startup]
        )
    elif mutation == "source_sha":
        expected["owners"][startup]["source_sha256"] = "0" * 64
    elif mutation == "generated_artifact":
        generated = tmp_path / checker._PR197_GENERATED_FACTS
        generated.write_bytes(generated.read_bytes() + b"\nprint('extra')\n")
    else:
        original = (tmp_path / startup).read_text()
        if mutation == "extra_sql":
            changed = original.replace(
                'cursor.execute("SELECT version_num FROM public.alembic_version")',
                'cursor.execute("SELECT version_num FROM public.alembic_version")\n'
                '        cursor.execute("SELECT * FROM sync_fence.stats_fact_versions")',
                1,
            )
        elif mutation == "privileged_clone":
            changed = original + "\ndef clone_owner(dsn):\n    return psycopg.connect(dsn)\n"
        else:
            changed = original + "\nfrom pitchlog.other_admin import open_privileged\n"
        assert changed != original
        (tmp_path / startup).write_text(changed)
    declaration = _declaration(checker, expected)
    with pytest.raises(checker.ContractError):
        checker._load_pr197_source_owners(
            tmp_path, declaration, {"pr196_source_registration": {}}
        )


def test_pr197_absent_root_pin_fails_closed(tmp_path, checker, monkeypatch):
    """rootの前置E/SHA未供給を自己期待で補わない。"""
    monkeypatch.setattr(checker, "_PR197_FIXED_EXPECTATION_REVISION", None)
    monkeypatch.setattr(checker, "_PR197_EXPECTATION_FIXTURE_SHA256", None)
    with pytest.raises(checker.ContractError, match="未供給"):
        checker._pr197_fixed_expectations(tmp_path)


def test_pr197_sql_requires_fixed_manifest_inputs_and_exact_regeneration(
    tmp_path, monkeypatch, checker, expected
):
    """SQL3のみを型付き生成で再現し、追加SQL/manifest共改変を拒否する。"""
    manifest = json.loads(_git_bytes("backend/domain/stats-manifest.json"))
    package_files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", REVISION,
         "backend/src/pitchlog/domaingen"], cwd=SOURCE_ROOT, text=True,
    ).splitlines()
    paths = (
        set(package_files)
        | set(manifest["generationInputFiles"])
        | set(manifest["generatedFiles"])
        | set(expected["owners"])
        | {"backend/domain/stats-manifest.json", "backend/src/pitchlog/__init__.py"}
    )
    _copy_fixed(tmp_path, paths)
    monkeypatch.setattr(checker, "_pr197_registration_is_trusted", lambda _: True)
    monkeypatch.setattr(checker, "_pr197_fixed_expectations", lambda _: expected)
    monkeypatch.setattr(
        checker, "_pr192_git_bytes", lambda _root, _revision, path: _git_bytes(path)
    )
    assert checker._pr197_generated_sql_matches(tmp_path, None)
    sql = tmp_path / "backend/src/pitchlog/stats/generated/stats.sql"
    sql.write_bytes(sql.read_bytes() + b"\nSELECT * FROM sync_fence.stats_fact_versions;\n")
    assert not checker._pr197_generated_sql_matches(tmp_path, None)
    sql.write_bytes(_git_bytes("backend/src/pitchlog/stats/generated/stats.sql"))
    manifest_path = tmp_path / "backend/domain/stats-manifest.json"
    changed = copy.deepcopy(manifest)
    changed["generatedFiles"]["backend/src/pitchlog/stats/generated/stats.sql"] = hashlib.sha256(
        sql.read_bytes() + b"extra"
    ).hexdigest()
    manifest_path.write_text(json.dumps(changed))
    assert not checker._pr197_generated_sql_matches(tmp_path, None)
    manifest_path.write_bytes(_git_bytes("backend/domain/stats-manifest.json"))
    for path in checker._PR197_GENERATOR_IMPORT_FILES:
        imported = tmp_path / path
        original = imported.read_bytes()
        imported.write_bytes(original + b"\n# added import code\n")
        assert not checker._pr197_generated_sql_matches(tmp_path, None)
        imported.write_bytes(original)


def test_pr197_fixed_git_rejects_same_change_and_other_ancestor(
    tmp_path, monkeypatch, checker, expected
):
    """隔離Gitで前置Eを作り、fixture同時書換えと別祖先を拒否する。"""

    def git(*args: str) -> str:
        result = subprocess.check_output(["git", *args], cwd=tmp_path, text=True)
        return result.strip()

    def commit(message: str) -> str:
        git("add", ".")
        subprocess.check_output(
            ["git", "-c", "user.name=Codex Test",
             "-c", "user.email=codex-test@example.invalid", "commit", "-q", "-m", message],
            cwd=tmp_path, text=True,
        )
        return git("rev-parse", "HEAD")

    git("init", "-q")
    source_checker = tmp_path / "scripts/check_tenant_boundary_bypass.py"
    source_checker.parent.mkdir(parents=True)
    source_checker.write_text("# root前置Eより前の検査器\n")
    frozen = tmp_path / "contracts/tenant_boundary/frozen-inputs.json"
    frozen.parent.mkdir(parents=True)
    frozen.write_text(json.dumps({"frozen_inputs": {}}))
    source_revision = commit("source")
    monkeypatch.setattr(checker, "_PR197_SOURCE_REVISION", source_revision)
    fixture_value = copy.deepcopy(expected)
    fixture_value["source_revision"] = source_revision
    fixture_value["formal_base_revision"] = source_revision
    fixture = tmp_path / checker._PR197_EXPECTED_FIXTURE
    fixture.parent.mkdir(parents=True)
    fixture.write_text(json.dumps(fixture_value))
    expectation_revision = commit("independent fixture")
    fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    monkeypatch.setattr(checker, "_PR197_FIXED_EXPECTATION_REVISION", expectation_revision)
    monkeypatch.setattr(checker, "_PR197_EXPECTATION_FIXTURE_SHA256", fixture_sha)

    def pins(revision: str, digest: str) -> None:
        entries = {
            "pr197_source_revision": {
                "value": source_revision, "purpose": checker._PR197_SOURCE_PURPOSE,
                "sources": checker._PR197_SOURCE_CONSUMERS,
            },
            "pr197_expectation_revision": {
                "value": revision, "purpose": checker._PR197_EXPECTATION_PURPOSE,
                "sources": checker._PR197_EXPECTATION_CONSUMERS,
            },
            "pr197_expectation_fixture_sha256": {
                "value": digest, "purpose": checker._PR197_EXPECTATION_PURPOSE,
                "sources": checker._PR197_EXPECTATION_CONSUMERS,
            },
        }
        frozen.write_text(json.dumps({"frozen_inputs": entries}))

    pins(expectation_revision, fixture_sha)
    assert checker._pr197_fixed_expectations(tmp_path)["counts"]["candidate"] == 71
    # E2 は同一 fixture/checker byte の子孫でも、独立固定 E1 の置換先にはならない。
    later_revision = commit("same fixture and checker in descendant")
    assert subprocess.check_output(
        ["git", "show", f"{later_revision}:{checker._PR197_EXPECTED_FIXTURE}"],
        cwd=tmp_path,
    ) == subprocess.check_output(
        ["git", "show", f"{expectation_revision}:{checker._PR197_EXPECTED_FIXTURE}"],
        cwd=tmp_path,
    )
    pins(later_revision, fixture_sha)
    with pytest.raises(checker.ContractError):
        checker._pr197_fixed_expectations(tmp_path)
    pins(expectation_revision, fixture_sha)
    fixture.write_bytes(fixture.read_bytes() + b" ")
    mutated_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    pins(expectation_revision, mutated_sha)
    monkeypatch.setattr(checker, "_PR197_EXPECTATION_FIXTURE_SHA256", mutated_sha)
    with pytest.raises(checker.ContractError):
        checker._pr197_fixed_expectations(tmp_path)
    fixture.write_bytes(subprocess.check_output(
        ["git", "show", f"{expectation_revision}:{checker._PR197_EXPECTED_FIXTURE}"],
        cwd=tmp_path,
    ))
    monkeypatch.setattr(checker, "_PR197_EXPECTATION_FIXTURE_SHA256", fixture_sha)
    # Sの別子commitはHEAD祖先ではない。形だけ一致するfixtureでも受けない。
    unrelated = subprocess.check_output(
        ["git", "-c", "user.name=Codex Test", "-c",
         "user.email=codex-test@example.invalid", "commit-tree",
         f"{source_revision}^{{tree}}", "-p", source_revision, "-m", "sibling"],
        cwd=tmp_path, text=True,
    ).strip()
    pins(unrelated, fixture_sha)
    with pytest.raises(checker.ContractError):
        checker._pr197_fixed_expectations(tmp_path)
    source_checker.write_text("# 前置Eに検査器変更を混入\n")
    changed_checker_revision = commit("checker changed before fixture pin")
    pins(changed_checker_revision, fixture_sha)
    with pytest.raises(checker.ContractError):
        checker._pr197_fixed_expectations(tmp_path)
