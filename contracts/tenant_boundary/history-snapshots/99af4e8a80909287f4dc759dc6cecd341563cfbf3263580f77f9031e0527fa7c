"""固定0039の元試験をfixture起動前に隔離する、試験専用pytest plugin。"""

from __future__ import annotations

import ast
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import frozen_history

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = "backend/tests/fixtures/product_authz_stage_a_profile_v0039.json"
_REFERENCE = "stage_a_0039_profile_reference_revision"
_FIXED_REFERENCE = frozen_history.read_original_pr197_pin(
    "stage_a_0039_profile_reference_revision"
)
_PURPOSE = (
    "正式51bcbの0039歴史検証profile972file/31caseをroot前置Git全byteへ束縛し、"
    "現木/fixture/任意revision同時改変を拒否。current製品loader・任意profile許可・"
    "署名・一般受理へ流用しない。"
)
_CONSUMERS = [
    "backend/tests/stage_a_0039_profile.py:immutable_stage_a_0039_profile",
    "backend/tests/test_stage_a_0039_profile.py:immutable_profile_expectation",
]
_MODULE = "backend/tests/db/test_stage_a_rule_candidates.py"
_NODE_PREFIX = "tests/db/test_stage_a_rule_candidates.py::"
_CHILD_FD = "PITCHLOG_STAGE_A_0039_PROOF_FD"
_CHILD: dict[str, Any] | None = None
_SESSIONS: dict[pytest.Config, _Session] = {}


def _fail() -> ValueError:
    """原文や接続資格を例外へ含めない。"""
    return ValueError("0039歴史profileの固定原典・実行証明が不一致です")


def _sha(value: bytes) -> str:
    """生bytesを固定hashへ写す。"""
    return hashlib.sha256(value).hexdigest()


def _unique(pairs):
    """重複JSON keyを補修せず拒否する。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise _fail()
        result[key] = value
    return result


def _json(raw: bytes | str):
    """非標準数値や重複を受け付けない。"""

    def invalid(_value):
        raise _fail()

    return json.loads(raw, object_pairs_hook=_unique, parse_constant=invalid)


def _git(root: Path, *args: str) -> bytes:
    """固定Git原典だけを読み、stderrや原文を失敗表示しない。"""
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False, timeout=30
    )
    if result.returncode != 0:
        raise _fail()
    return result.stdout


def _plain(path: Path) -> None:
    """親directoryのsymlinkも書込/参照の境界にしない。"""
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise _fail()


def _path(value: Any) -> str:
    """正規relative pathだけを許す。"""
    if type(value) is not str:
        raise _fail()
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(x in {"", ".", ".."} for x in path.parts)
    ):
        raise _fail()
    if (
        not value.startswith(("backend/", "contracts/", "scripts/"))
        or ".env" in path.parts
    ):
        raise _fail()
    return value


def _read_profile(root: Path) -> dict[str, Any]:
    """Root前置Git Eのfixtureへ全byte束縛し、現木自己期待を拒否する。"""
    _plain(root)
    _plain(root / _FIXTURE)
    _plain(root / "contracts/tenant_boundary/frozen-inputs.json")
    frozen = _json((root / "contracts/tenant_boundary/frozen-inputs.json").read_bytes())
    reference = frozen["frozen_inputs"][_REFERENCE]
    if (
        type(reference) is not dict
        or set(reference) != {"value", "purpose", "sources"}
        or reference["purpose"] != _PURPOSE
        or reference["sources"] != _CONSUMERS
        or type(reference["value"]) is not str
        or re.fullmatch("[a-f0-9]{40}", reference["value"]) is None
        or reference["value"] != _FIXED_REFERENCE
    ):
        raise _fail()
    commit = reference["value"]
    _git(root, "merge-base", "--is-ancestor", commit, "HEAD")
    raw = (root / _FIXTURE).read_bytes()
    if _git(root, "show", commit + ":" + _FIXTURE) != raw:
        raise _fail()
    value = _json(raw)
    required = {
        "schema_version",
        "revision",
        "profile",
        "files",
        "test_module",
        "case_ids",
        "expected_generated_ddl_count",
        "expected_full_statement_count",
        "expected_pre_rule_statement_count",
    }
    if (
        type(value) is not dict
        or set(value) != required
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["profile"] != "stage-a-0039-fixed-canonical-v1"
        or type(value["revision"]) is not str
        or re.fullmatch("[a-f0-9]{40}", value["revision"]) is None
        or value["test_module"] != _MODULE
        or type(value["files"]) is not list
        or len(value["files"]) != 972
        or type(value["case_ids"]) is not list
        or len(value["case_ids"]) != 31
    ):
        raise _fail()
    paths = []
    for row in value["files"]:
        if (
            type(row) is not dict
            or set(row) != {"path", "sha256"}
            or type(row["sha256"]) is not str
            or re.fullmatch("[a-f0-9]{64}", row["sha256"]) is None
        ):
            raise _fail()
        paths.append(_path(row["path"]))
    if paths != sorted(set(paths)) or _MODULE not in paths:
        raise _fail()
    ids = value["case_ids"]
    if any(type(x) is not str or not x.startswith(_NODE_PREFIX) for x in ids) or len(
        ids
    ) != len(set(ids)):
        raise _fail()
    for key in (
        "expected_generated_ddl_count",
        "expected_full_statement_count",
        "expected_pre_rule_statement_count",
    ):
        if type(value[key]) is not int or value[key] <= 0:
            raise _fail()
    _git(root, "merge-base", "--is-ancestor", value["revision"], commit)
    return value


def immutable_stage_a_0039_profile(root: Path) -> dict[str, Any]:
    """前置Eだけを受ける、宣言済みfrozen consumer。"""
    try:
        return _read_profile(root)
    except (OSError, KeyError, TypeError, ValueError, subprocess.TimeoutExpired):
        raise _fail() from None


def _profile(root: Path) -> dict[str, Any]:
    """内部呼出しも同じconsumerからだけ原本を得る。"""
    return immutable_stage_a_0039_profile(root)


def _verify_parent(root: Path, profile: dict[str, Any]) -> None:
    """plugin宣言1つだけを逆射影して元module全ASTを保つ。"""
    _plain(root / _MODULE)
    actual = ast.parse((root / _MODULE).read_bytes())
    assignments = [
        x
        for x in actual.body
        if isinstance(x, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pytest_plugins" for t in x.targets)
    ]
    if len(assignments) != 1 or ast.literal_eval(assignments[0].value) != (
        "stage_a_0039_profile",
    ):
        raise _fail()
    actual.body.remove(assignments[0])
    old = _git(root, "show", profile["revision"] + ":" + _MODULE)
    if ast.dump(actual, include_attributes=False) != ast.dump(
        ast.parse(old), include_attributes=False
    ):
        raise _fail()


def _materialize(root: Path, destination: Path, profile: dict[str, Any]) -> None:
    """新規実体directoryへ有限Git原本だけを書き、現在木fallbackを作らない。"""
    _plain(destination)
    if _profile(root) != profile:
        raise _fail()
    if destination.exists() or destination.resolve().is_relative_to(root.resolve()):
        raise _fail()
    destination.mkdir(mode=0o700)
    for row in profile["files"]:
        raw = _git(root, "show", profile["revision"] + ":" + row["path"])
        if _sha(raw) != row["sha256"]:
            raise _fail()
        target = destination / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        _plain(target)
        target.write_bytes(raw)
    _verify_files(destination, profile)


def _verify_files(root: Path, profile: dict[str, Any]) -> None:
    """閉file集合と全bytesを再確認し、pycや未知fileも入れない。"""
    _plain(root)
    expected = {row["path"]: row["sha256"] for row in profile["files"]}
    entries = list(root.rglob("*"))
    if any(p.is_symlink() for p in entries):
        raise _fail()
    directories = {
        str(parent)
        for path in expected
        for parent in PurePosixPath(path).parents
        if str(parent) != "."
    }
    if {p.relative_to(root).as_posix() for p in entries if p.is_dir()} != directories:
        raise _fail()
    actual = {p.relative_to(root).as_posix(): p for p in entries if p.is_file()}
    if set(actual) != set(expected):
        raise _fail()
    for path, sha in expected.items():
        _plain(actual[path])
        if _sha(actual[path].read_bytes()) != sha:
            raise _fail()


class _Imports(importlib.abc.MetaPathFinder):
    """歴史packageの未宣言/別root importを現環境へfallbackしない。"""

    def __init__(self, root: Path, profile: dict[str, Any]):
        self.root = root
        self.modules = {}
        for row in profile["files"]:
            path = row["path"]
            if not path.endswith(".py"):
                continue
            if path.startswith("backend/src/"):
                name = path.removeprefix("backend/src/")
            elif path.startswith("backend/tests/"):
                name = path.removeprefix("backend/tests/")
            elif path.startswith("scripts/"):
                name = path
            else:
                continue
            name = name.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
            self.modules[name] = row

    def find_spec(self, fullname, path=None, target=None):
        if not (
            fullname == "pitchlog"
            or fullname.startswith("pitchlog.")
            or fullname == "scripts"
            or fullname.startswith("scripts.")
            or fullname == "db"
            or fullname.startswith("db.")
            or fullname in self.modules
        ):
            return None
        if fullname == "scripts" and fullname not in self.modules:
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or tuple(spec.submodule_search_locations or ()) != (
                str(self.root / "scripts"),
            ):
                raise _fail()
            return spec
        row = self.modules.get(fullname)
        if row is None:
            raise _fail()
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        expected = self.root / row["path"]
        if (
            spec is None
            or spec.origin != str(expected)
            or _sha(expected.read_bytes()) != row["sha256"]
        ):
            raise _fail()
        return spec


@dataclass(frozen=True)
class _Session:
    """標準pytestの親collectionに登録した一回session参照。"""

    config: pytest.Config
    control: Path
    root: Path
    plugin: Path
    output: Path
    profile: dict[str, Any]


def _environment(session: _Session, fd: int) -> dict[str, str]:
    """共有DB/任意import経路を継承せず、owned factoryだけへ渡す。"""
    names = {"PATH", "HOME", "LANG", "LC_ALL"}
    env = {key: value for key, value in os.environ.items() if key in names}
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(
                (
                    str(session.plugin.parent),
                    str(session.root / "backend/tests"),
                    str(session.root / "backend/src"),
                )
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
            _CHILD_FD: str(fd),
            "PITCHLOG_PYTEST_TMPDIR": str(session.output / "pytest-tmp"),
            "PITCHLOG_PYTEST_TMP_KEEP_DAYS": "0",
            "DOCKER_HOST": "unix:///var/run/docker.sock",
        }
    )
    return env


def _child(
    session: _Session, nodeid: str | None, *, collect: bool = False
) -> subprocess.CompletedProcess:
    """正規pytestを実起動し、実exit/JUnitを返す。呼出者SQL/資格flagは受け取らない。"""
    if (
        _SESSIONS.get(session.config) is not session
        or _profile(session.control) != session.profile
    ):
        raise _fail()
    if (
        type(collect) is not bool
        or (collect and nodeid is not None)
        or (not collect and nodeid is None)
    ):
        raise _fail()
    if nodeid is not None and nodeid not in session.profile["case_ids"]:
        raise _fail()
    _verify_files(session.root, session.profile)
    fd, writer = os.pipe()
    ticket = {
        "parent_pid": os.getpid(),
        "control_root": str(session.control),
        "profile_root": str(session.root),
        "plugin_sha256": _sha(session.plugin.read_bytes()),
        "nodeid": nodeid,
        "collect": collect,
    }
    os.write(writer, json.dumps(ticket).encode())
    os.close(writer)
    try:
        args = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-p",
            "stage_a_0039_profile",
        ]
        if collect:
            args += ["--collect-only", "-q", "tests/db/test_stage_a_rule_candidates.py"]
        else:
            if nodeid is None:
                raise _fail()
            args += ["-q", "--junitxml=" + str(session.output / "result.xml"), nodeid]
        return subprocess.run(
            args,
            cwd=session.root / "backend",
            env=_environment(session, fd),
            pass_fds=(fd,),
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
    finally:
        os.close(fd)


def _junit(raw: bytes, nodeid: str) -> None:
    """対象1caseの非skip call成功を標準JUnitで厳密確認する。"""
    if not 1 <= len(raw) <= 65536 or b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise _fail()
    root = ET.fromstring(raw)
    suites = list(root.iter("testsuite"))
    cases = list(root.iter("testcase"))
    if (
        len(suites) != 1
        or len(cases) != 1
        or suites[0].get("tests") != "1"
        or any(suites[0].get(k) != "0" for k in ("failures", "errors", "skipped"))
        or list(cases[0])
        or cases[0].get("name") != nodeid.split("::", 1)[1]
        or cases[0].get("classname") != "tests.db.test_stage_a_rule_candidates"
    ):
        raise _fail()


def _run_case(session: _Session, nodeid: str) -> None:
    """親fixtureの代わりに子の全旧fixture/assertを実行する。"""
    result_path = session.output / "result.xml"
    result_path.unlink(missing_ok=True)
    completed = _child(session, nodeid)
    if completed.returncode != 0 or not result_path.is_file():
        raise _fail()
    _junit(result_path.read_bytes(), nodeid)
    _verify_files(session.root, session.profile)


def pytest_configure(config: pytest.Config) -> None:
    """環境boolではなく継承pipeを消費し、子のsource/root/import境界を設定する。"""
    global _CHILD
    value = os.environ.get(_CHILD_FD)
    if value is None:
        return
    if (
        re.fullmatch(r"[1-9][0-9]*", value) is None
        or int(value) < 3
        or _CHILD is not None
    ):
        raise _fail()
    try:
        if not stat.S_ISFIFO(os.fstat(int(value)).st_mode):
            raise _fail()
        with os.fdopen(int(value), "rb") as pipe:
            raw = pipe.read(16385)
        if len(raw) > 16384:
            raise _fail()
        ticket = _json(raw)
    except (OSError, ValueError, TypeError) as error:
        raise _fail() from error
    if (
        type(ticket) is not dict
        or set(ticket)
        != {
            "parent_pid",
            "control_root",
            "profile_root",
            "plugin_sha256",
            "nodeid",
            "collect",
        }
        or type(ticket["parent_pid"]) is not int
        or ticket["parent_pid"] != os.getppid()
        or type(ticket["collect"]) is not bool
        or not Path(ticket["control_root"]).is_absolute()
        or not Path(ticket["profile_root"]).is_absolute()
    ):
        raise _fail()
    control, root = Path(ticket["control_root"]), Path(ticket["profile_root"])
    if ticket["plugin_sha256"] != _sha(Path(__file__).read_bytes()) or ticket[
        "plugin_sha256"
    ] != _sha((control / "backend/tests/stage_a_0039_profile.py").read_bytes()):
        raise _fail()
    os.environ.pop(_CHILD_FD, None)
    profile = _profile(control)
    if (ticket["collect"] and ticket["nodeid"] is not None) or (
        not ticket["collect"] and ticket["nodeid"] is None
    ):
        raise _fail()
    if ticket["nodeid"] is not None and ticket["nodeid"] not in profile["case_ids"]:
        raise _fail()
    _verify_files(root, profile)
    finder = _Imports(root, profile)
    for name, module in tuple(sys.modules.items()):
        if (
            name == "pitchlog"
            or name.startswith("pitchlog.")
            or name == "db"
            or name.startswith("db.")
            or name in finder.modules
        ):
            expected = finder.modules.get(name)
            if expected is None or getattr(module, "__file__", None) != str(
                root / expected["path"]
            ):
                raise _fail()
    sys.meta_path.insert(0, finder)
    _CHILD = {"ticket": ticket, "profile": profile, "finder": finder}
    config.add_cleanup(lambda: sys.meta_path.remove(finder))
    if not ticket["collect"]:
        _start_child_database(config)


def _start_child_database(config: pytest.Config) -> None:
    """真正な子factoryだけでautouse用DBを配置し、親DSNを継承しない。"""
    if _CHILD is None or _CHILD["ticket"]["collect"]:
        raise _fail()
    from db_fixtures import _dsn_names, disposable_postgres_cluster
    from psycopg.conninfo import make_conninfo

    names = _dsn_names()
    if any(name in os.environ for name in names):
        raise _fail()
    stack = ExitStack()
    try:
        # 元factoryは起動後の実endpointへ差し替えるrole用テンプレートを要求する。
        # endpoint無しの公開試験資格だけを先に渡し、この値では接続しない。
        os.environ[names[1]] = make_conninfo(
            user="pitchlog_stage_a_test_role", password="public-owned-child-fixture"
        )
        factory = cast(Any, disposable_postgres_cluster).__wrapped__()
        cluster = stack.enter_context(factory())
        os.environ[names[0]] = cluster.admin_dsn
        os.environ[names[1]] = cluster.role_dsn_template
    except BaseException:
        stack.close()
        for name in names:
            os.environ.pop(name, None)
        raise

    def cleanup_database() -> None:
        try:
            stack.close()
        finally:
            for name in names:
                os.environ.pop(name, None)

    config.add_cleanup(cleanup_database)


def _closed_function(
    item: pytest.Function, call: Callable[[], None]
) -> pytest.Function:
    """標準fixture managerに新しい引数なしcallの依存を再計算させる。"""
    replacement = pytest.Function.from_parent(
        item.parent, name=item.name, originalname=item.originalname, callobj=call
    )
    replacement.own_markers = list(item.own_markers)
    replacement.keywords.update(item.keywords)
    return replacement


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """親fixture起動前に標準Functionを置換し、手製reportを作らない。"""
    if _CHILD is not None:
        expected = (
            _CHILD["profile"]["case_ids"]
            if _CHILD["ticket"]["collect"]
            else [_CHILD["ticket"]["nodeid"]]
        )
        if [x.nodeid for x in items] != expected:
            raise _fail()
        return
    targets = [
        x for x in items if isinstance(x, pytest.Function) and x.path == _ROOT / _MODULE
    ]
    if not targets:
        return
    profile = _profile(_ROOT)
    _verify_parent(_ROOT, profile)
    if any(x.nodeid not in profile["case_ids"] for x in targets) or len(
        {x.nodeid for x in targets}
    ) != len(targets):
        raise _fail()
    base = Path.home() / ".cache/pitchlog/stage-a-0039-child"
    _plain(base)
    base.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="pytest-", dir=base)
    config.add_cleanup(temporary.cleanup)
    work = Path(temporary.name)
    root, plugin_dir, output = work / "profile", work / "plugin", work / "output"
    _materialize(_ROOT, root, profile)
    plugin_dir.mkdir()
    output.mkdir()
    plugin = plugin_dir / "stage_a_0039_profile.py"
    plugin.write_bytes(Path(__file__).read_bytes())
    state = _Session(config, _ROOT, root, plugin, output, profile)
    _SESSIONS[config] = state

    def cleanup_session() -> None:
        _SESSIONS.pop(config, None)

    config.add_cleanup(cleanup_session)
    collected = _child(state, None, collect=True)
    actual_ids = [
        x for x in collected.stdout.splitlines() if x.startswith(_NODE_PREFIX)
    ]
    if collected.returncode != 0 or actual_ids != profile["case_ids"]:
        raise _fail()
    replacements = {}

    def invocation(nodeid):
        def call():
            _run_case(state, nodeid)

        return call

    for item in targets:
        bound_call = invocation(item.nodeid)
        replacement = _closed_function(item, bound_call)
        replacements[item] = replacement
    items[:] = [replacements.get(item, item) for item in items]
