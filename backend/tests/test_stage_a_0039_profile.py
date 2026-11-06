"""歴史profileの固定Git境界とfixture前collection置換を、DBなしで検査する。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import stage_a_0039_profile as api

pytest_plugins = ("pytester",)


@pytest.fixture(scope="session")
def immutable_profile_expectation() -> dict[str, Any]:
    """宣言済みconsumerでroot前置Eの期待だけを読む。"""
    return api.immutable_stage_a_0039_profile(api._ROOT)


@pytest.fixture
def metadata_root(tmp_path: Path) -> Path:
    """本物Eを読める独立Gitだけへ負対向のmetadataを複製する。"""
    root = tmp_path / "control"
    root.mkdir()
    for name in (api._FIXTURE, "contracts/tenant_boundary/frozen-inputs.json"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((api._ROOT / name).read_bytes())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    common = Path(api._git(api._ROOT, "rev-parse", "--git-common-dir").decode().strip())
    if not common.is_absolute():
        common = api._ROOT / common
    (root / ".git/objects/info/alternates").write_text(
        str(common.resolve() / "objects") + "\n"
    )
    frozen = json.loads(
        (root / "contracts/tenant_boundary/frozen-inputs.json").read_text()
    )
    revision = frozen["frozen_inputs"][api._REFERENCE]["value"]
    subprocess.run(["git", "-C", str(root), "update-ref", "HEAD", revision], check=True)
    return root


def test_real_immutable_profile_and_parent_whole_module(immutable_profile_expectation):
    """970blob/31caseと元全ASTは固定Gitから得られ、現在木期待へ変えない。"""
    profile = immutable_profile_expectation
    assert len(profile["files"]) == 970 and len(profile["case_ids"]) == 31
    api._verify_parent(api._ROOT, profile)


@pytest.mark.parametrize(
    "fault", ["missing", "purpose", "consumer", "revision", "fixture", "both", "extra"]
)
def test_metadata_or_declared_reference_tampering_is_rejected(metadata_root, fault):
    """fixture/参照の同時変更も前置E/Git祖先照合をすり抜けない。"""
    frozen_path = metadata_root / "contracts/tenant_boundary/frozen-inputs.json"
    frozen = json.loads(frozen_path.read_text())
    reference = frozen["frozen_inputs"][api._REFERENCE]
    fixture_path = metadata_root / api._FIXTURE
    fixture = json.loads(fixture_path.read_text())
    if fault == "missing":
        del frozen["frozen_inputs"][api._REFERENCE]
    elif fault == "purpose":
        reference["purpose"] += "changed"
    elif fault == "consumer":
        reference["sources"].append("unknown.py:consumer")
    elif fault == "revision":
        reference["value"] = "0" * 40
    elif fault == "extra":
        reference["unknown"] = True
    else:
        fixture["files"][0]["sha256"] = "0" * 64
        fixture_path.write_text(json.dumps(fixture))
        if fault == "both":
            reference["value"] = fixture["revision"]
    frozen_path.write_text(json.dumps(frozen))
    with pytest.raises(ValueError):
        api._profile(metadata_root)


def test_unapproved_ancestor_commit_and_fixture_cannot_rotate_anchor(metadata_root):
    """fixtureと参照を同時に真正Gitへ保存しても、承認済E以外を拒否する。"""
    path = metadata_root / api._FIXTURE
    profile = json.loads(path.read_text())
    profile["expected_generated_ddl_count"] += 1
    path.write_text(json.dumps(profile))
    subprocess.run(
        ["git", "-C", str(metadata_root), "add", "--", api._FIXTURE], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(metadata_root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "unapproved fixture replacement",
        ],
        check=True,
    )
    revision = api._git(metadata_root, "rev-parse", "HEAD").decode().strip()
    assert revision != api._FIXED_REFERENCE
    assert (
        api._git(metadata_root, "show", revision + ":" + api._FIXTURE)
        == path.read_bytes()
    )
    frozen_path = metadata_root / "contracts/tenant_boundary/frozen-inputs.json"
    frozen = json.loads(frozen_path.read_text())
    frozen["frozen_inputs"][api._REFERENCE]["value"] = revision
    frozen_path.write_text(json.dumps(frozen))
    with pytest.raises(ValueError):
        api.immutable_stage_a_0039_profile(metadata_root)


@pytest.mark.parametrize(
    "value",
    [
        "../outside.py",
        "/absolute.py",
        "backend/../outside.py",
        "backend/.env",
        "other/file.py",
    ],
)
def test_noncanonical_or_unowned_paths_are_rejected(value):
    """親逃避/絶対/.env/他scopeを許可しない。"""
    with pytest.raises(ValueError):
        api._path(value)


@pytest.fixture(scope="session")
def actual_materialized(tmp_path_factory, immutable_profile_expectation):
    """root固定Gitの有限全原物を本当に複製するが、DBは実行しない。"""
    root = tmp_path_factory.mktemp("actual-profile") / "data"
    api._materialize(api._ROOT, root, immutable_profile_expectation)
    return root


@pytest.mark.parametrize("fault", ["bytes", "extra", "empty-directory", "symlink"])
def test_materialized_files_are_closed_and_not_root_fallback(
    actual_materialized, immutable_profile_expectation, fault
):
    """全byte/未知file/余剰directory/aliasを同じ実検証器で拒否する。"""
    root = actual_materialized
    profile = immutable_profile_expectation
    target = root / profile["files"][0]["path"]
    original = target.read_bytes()
    extra = root / "unknown.py"
    directory = root / "unknown"
    try:
        if fault == "bytes":
            target.write_bytes(original + b" ")
        elif fault == "extra":
            extra.write_text("pass")
        elif fault == "empty-directory":
            directory.mkdir()
        else:
            extra.symlink_to(target)
        with pytest.raises(ValueError):
            api._verify_files(root, profile)
    finally:
        target.write_bytes(original)
        extra.unlink(missing_ok=True)
        if directory.exists():
            directory.rmdir()
    api._verify_files(root, profile)


def test_destination_inside_repository_or_existing_rejected(
    tmp_path, immutable_profile_expectation
):
    """実repository内への書込みと既存profileの上書きを拒否する。"""
    for destination in (api._ROOT / "forbidden-history-test", tmp_path):
        with pytest.raises(ValueError):
            api._materialize(api._ROOT, destination, immutable_profile_expectation)
        assert not (api._ROOT / "forbidden-history-test").exists()


def test_unknown_or_other_root_import_is_rejected(
    actual_materialized, immutable_profile_expectation, monkeypatch
):
    """未知project importと別rootの同名moduleは現環境へfallbackしない。"""
    finder = api._Imports(actual_materialized, immutable_profile_expectation)
    with pytest.raises(ValueError):
        finder.find_spec("pitchlog.not_declared")
    spec = api.importlib.machinery.ModuleSpec(
        "pitchlog", loader=None, origin="/other/pitchlog.py"
    )
    monkeypatch.setattr(
        api.importlib.machinery.PathFinder, "find_spec", lambda *args: spec
    )
    with pytest.raises(ValueError):
        finder.find_spec("pitchlog")


def _xml(node: str, **attributes: str) -> bytes:
    """JUnit decoderだけの有限入力。実行資格を作るfixtureではない。"""
    fields = {"tests": "1", "failures": "0", "errors": "0", "skipped": "0"} | attributes
    tag = " ".join(f'{key}="{value}"' for key, value in fields.items())
    return (
        f"<testsuites><testsuite {tag}>"
        '<testcase classname="tests.db.test_stage_a_rule_candidates" '
        f'name="{node}"/></testsuite></testsuites>'
    ).encode()


@pytest.mark.parametrize(
    "fault", ["zero", "multiple", "failed", "error", "skipped", "wrong-name", "doctype"]
)
def test_child_execution_must_be_exact_one_real_non_skip_junit(
    fault, immutable_profile_expectation
):
    """収集0/未実行/skip/失敗をchildの成功として補完しない。"""
    nodeid = immutable_profile_expectation["case_ids"][0]
    name = nodeid.split("::", 1)[1]
    api._junit(_xml(name), nodeid)
    if fault == "zero":
        raw = _xml(name, tests="0")
    elif fault == "multiple":
        raw = _xml(name, tests="2")
    elif fault in ("failed", "error", "skipped"):
        raw = _xml(
            name,
            **{
                {"failed": "failures", "error": "errors", "skipped": "skipped"}[
                    fault
                ]: "1"
            },
        )
    elif fault == "wrong-name":
        raw = _xml("unknown")
    else:
        raw = b"<!DOCTYPE test>" + _xml(name)
    with pytest.raises(ValueError):
        api._junit(raw, nodeid)


@pytest.mark.parametrize("marker", ["", "0", "2", "true", "01", "-1"])
def test_unqualified_child_marker_is_rejected(monkeypatch, marker):
    """bool/envだけでは子資格にできず、未知fdも読む前に拒否する。"""
    monkeypatch.setenv(api._CHILD_FD, marker)
    with pytest.raises(ValueError):
        api.pytest_configure(cast(Any, None))


def test_standard_function_recalculates_before_fixture_setup(pytester):
    """本物pytestのfixture依存を再計算し、親autouseとcaseIDを残す。"""
    pytester.makeini("[pytest]\nmarkers = requires_db\n")
    pytester.makeconftest("""import pytest
@pytest.fixture(autouse=True)
def always_guard():
    yield
@pytest.fixture
def poison():
    raise AssertionError("old eager fixture executed")
""")
    items = pytester.getitems("""import pytest
@pytest.mark.requires_db
@pytest.mark.parametrize("poison", [1, 2], ids=["a", "b"])
def test_original(poison):
    raise AssertionError("original must execute only in qualified child")
""")
    assert len(items) == 2
    calls = []
    for item in items:
        replacement = api._closed_function(item, lambda: calls.append(True))
        assert replacement.nodeid == item.nodeid
        assert replacement.get_closest_marker("requires_db") is not None
        assert "poison" not in replacement.fixturenames
        assert "always_guard" in replacement.fixturenames
        replacement.obj()
    assert calls == [True, True]
