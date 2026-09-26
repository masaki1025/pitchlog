"""テナント境界迂回検査の正例・負例・閉集合契約を検証する。"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVELOP_REPOSITORY_ROOT = Path("/home/ymdms/projects/pitchlog")
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_tenant_boundary_bypass.py"
POSITIVE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary" / "positive"
NEGATIVE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary" / "negative"
PRODUCT_APPLICATION_PATHS = (
    "pitchlog/authz/runtime_contract.py",
    "pitchlog/db/engine.py",
    "pitchlog/repositories/base.py",
    "pitchlog/repositories/binding.py",
    "pitchlog/repositories/cache_invalidation.py",
    "pitchlog/repositories/context.py",
    "pitchlog/repositories/repository_contract.py",
    "pitchlog/repositories/tenant_context_contract.py",
    "pitchlog/repositories/tokens.py",
)
EXPECTED_NEGATIVE_IDS = frozenset(
    {
        "C1_ASSERT_OWNER_SHAPES",
        "C1_CAN_SHAPES",
        "C1_CHECK_ACCESS_SHAPES",
        "C1_HAS_PERMISSION_SHAPES",
        "C1_IS_ALLOWED_SHAPES",
        "C1_MAY_SHAPES",
        "C1_REQUIRE_ROLE_SHAPES",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_ASSIGNMENT",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_CLASS_ASSIGNMENT",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_EXCEPT",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_MATCH",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_MODULE_ASSIGNMENT",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_PARAMETER",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_STAR",
        "C2_ADJUDICATED_IMPORT_SHADOWED_BY_WALRUS",
        "C2_GENERATION_IMPORT",
        "C2_GENERATION_ARGUMENT_NAME",
        "C2_GENERATION_ATTRIBUTE_ASSIGNMENT",
        "C2_GENERATION_KEYWORD_ARGUMENT",
        "C2_GENERATION_MATCH_KEYWORD",
        "C2_IDEMPOTENCY_KEY_IMPORT",
        "C2_IDEMPOTENT_KEY_IMPORT",
        "C2_REVISION_NO_IMPORT",
        "C2_SEQ_NO_IMPORT",
        "C2_SEQUENCE_NO_IMPORT",
        "C2_TOMBSTONE_IMPORT",
        "C3_AT_BAT_RESULT_IMPORT",
        "C3_AVG_IMPORT",
        "C3_EARNED_RUN_IMPORT",
        "C3_ERA_IMPORT",
        "C3_INNING_STATE_IMPORT",
        "C3_OBP_IMPORT",
        "C3_RBI_IMPORT",
        "C3_RESPONSIBLE_PITCHER_IMPORT",
        "C3_SLG_IMPORT",
        "C4_CACHE_CLEAR_API",
        "C4_DIRECT_INVALIDATION_WRITE",
        "C4_EVICT_API",
        "C4_INVALIDATE_API",
        "C4_PURGE_CACHE_API",
        "C4_TRIGGER_CORRECT_PLAY",
        "C4_TRIGGER_DISABLE_TENANT",
        "C4_TRIGGER_END_GROUP",
        "C4_TRIGGER_GAME_LIFECYCLE",
        "C4_TRIGGER_GRANT_FLAG",
        "C4_TRIGGER_LEAVE_GROUP",
        "C4_TRIGGER_PLAYER_IDENTITY",
        "C4_TRIGGER_POSTGAME_CORRECTION",
        "C4_TRIGGER_REENABLE_TENANT",
        "C4_TRIGGER_RESTORED_SYNC",
        "C4_TRIGGER_ROSTER_STATUS",
        "C4_TRIGGER_SETTING",
        "C4_TRIGGER_SUBSTITUTION",
        "C4_TRIGGER_UNDO",
        "C5_ALIAS_EXECUTE",
        "C5_ASYNC_SESSION",
        "C5_BASE_INTERNAL_MUTATIONS",
        "C5_CONTEXT_AFTER_TERMINATOR",
        "C5_CONTEXT_CONDITIONAL_ALIAS_CLASS_BASE",
        "C5_CONTEXT_CONDITIONAL_ALIAS_CLOSURE",
        "C5_CONTEXT_CONTAINER_SUBSCRIPT",
        "C5_CONTEXT_IN_ANNOTATED_ASSIGNMENT",
        "C5_CONTEXT_IN_CLASS_BASE",
        "C5_CONTEXT_IN_DEFAULT_ARG",
        "C5_CONTEXT_IN_DICT_COMPREHENSION",
        "C5_CONTEXT_IN_EXCEPTION_HANDLER_TYPE",
        "C5_CONTEXT_IN_FUNCTION_IMPORT",
        "C5_CONTEXT_IF_ELSE_ORIGIN_MERGE",
        "C5_CONTEXT_IFEXP_ORIGIN_MERGE",
        "C5_CONTEXT_IN_LAMBDA_DEFAULT",
        "C5_CONTEXT_IN_LOCAL_ALIAS",
        "C5_CONTEXT_RELATIVE_IMPORT",
        "C5_CONTEXT_REEXPORT_CONDITIONAL",
        "C5_CONTEXT_REEXPORT_CYCLE",
        "C5_CONTEXT_REEXPORT_DEPTH_LIMIT",
        "C5_CONTEXT_REEXPORT_FACADE",
        "C5_CONTEXT_REEXPORT_MISSING_MODULE",
        "C5_CONTEXT_REEXPORT_SELF_REFERENCE",
        "C5_CONTEXT_REEXPORT_STAR",
        "C5_CONTEXT_REEXPORT_SUBCLASS",
        "C5_CONTEXT_REEXPORT_UNSUPPORTED_ASSIGN",
        "C5_CONTEXT_MATCH_ORIGIN_MERGE",
        "C5_CONTEXT_IN_SUBSCRIPT_TARGET",
        "C5_CONTEXT_PROOF_DIRECT_REFERENCE",
        "C5_CONTEXT_PROOF_INDIRECT_REFERENCE",
        "C5_DYNAMIC_EVAL_EXECUTE",
        "C5_DYNAMIC_EXEC",
        "C5_DYNAMIC_GETATTR_EXECUTE",
        "C5_DYNAMIC_IMPORT_PSYCOPG",
        "C5_DYNAMIC_IMPORTLIB",
        "C5_ENGINE_RETURN_ALIAS",
        "C5_ENGINE_RAW_CONNECTION",
        "C5_IMPORT_REBOUND_BY_GLOBAL_IMPORT",
        "C5_IMPORT_REBOUND_BY_GLOBAL_WRITER",
        "C5_IMPORT_REBOUND_BY_STAR",
        "C5_MULTILINE_SCALARS",
        "C5_PGCONN_EXEC",
        "C5_PSYCOPG_DIRECT",
        "C5_SECRET_IN_DEFAULT_CAPTURE",
        "C5_SET_CONFIG_FALSE",
        "C5_SET_TENANT_SQL",
        "C5_SQLALCHEMY_ORM",
        "C5_TENANT_CONTEXT_OBJECT_NEW",
        "C5_TENANT_CONTEXT_OBJECT_SETATTR_UNTYPED",
        "C5_TENANT_CONTEXT_TYPE_CALL",
        "C5_CONTEXT_TRY_EXCEPT_ORIGIN_MERGE",
        "C5_TENANT_CONTEXT_OBJECT_NEW_TYPE",
        "C5_TENANT_CONTEXT_DATACLASSES_REPLACE",
        "C5_UNKNOWN_ENGINE_ARGUMENT",
        "C5_UNKNOWN_SESSION_ARGUMENT",
    }
)
REEXPORT_SUPPORT_SOURCES = {
    "pitchlog/repositories/context.py": '''\
"""再輸出写像テスト用の canonical constructor。"""


class TenantContext:
    """再輸出起源の終端となる型。"""
''',
}

CensusIdentity = tuple[str, int, int, str, str, str, str]

EXPECTED_CONDITION_2_PATTERNS = (
    "(?:^|_)idempotenc[a-z0-9_]*(?:_|$)",
    "(?:^|_)idempotent_key(?:_|$)",
    "(?:^|_)seq_no(?:_|$)",
    "(?:^|_)sequence_no(?:_|$)",
    "(?:^|_)tombstone(?:_|$)",
    "(?:^|_)revision_no(?:_|$)",
    "(?:^|_)generation(?:_|$)",
)
EXPECTED_CONDITION_2_ADJUDICATIONS = {
    "pitchlog.domaincheck.runners.catalog_independence.TracedGeneration": (
        "ドメイン計算カタログの独立性検査で使う追跡世代であり、"
        "同期プロトコルの世代ではない"
    ),
    "pitchlog.domaingen.backends.common.BackendGenerationError": (
        "ドメイン計算のコード生成 backend が送出する例外型であり、"
        "同期プロトコルの世代ではない"
    ),
    "pitchlog.domaingen.core.EXIT_GENERATION_FAILED": (
        "ドメイン計算のコード生成が失敗したことを表す終了コードの定数であり、"
        "同期プロトコルの世代ではない"
    ),
    "pitchlog.domaingen.core.GenerationError": (
        "ドメイン計算のコード生成が送出する例外型であり、"
        "同期プロトコルの世代ではない"
    ),
    "pitchlog.domaingen.formatter.FormatterGenerationError": (
        "ドメイン計算の表示コード生成が送出する例外型であり、"
        "同期プロトコルの世代ではない"
    ),
    "pitchlog.domainmut.engine.MutationGeneration": (
        "ドメイン計算 DSL の変異生成結果であり、同期プロトコルの世代ではない"
    ),
}

_FLOW_OMISSION_RUNNER = r"""
import ast
import importlib.util
import sys

script = sys.argv[1]
spec = importlib.util.spec_from_file_location(
    "check_tenant_boundary_bypass_flow_omission",
    script,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
original_expression = module._FlowProvenance._expression


def omit_call_registration(self, node, environment):
    if isinstance(node, ast.Call):
        return module._UNKNOWN_FLOW_VALUE
    return original_expression(self, node, environment)


module._FlowProvenance._expression = omit_call_registration
raise SystemExit(module.main(sys.argv[2:]))
"""


def _load_checker_module(path: Path, module_name: str) -> ModuleType:
    """検査器を指定した別モジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_checker() -> ModuleType:
    """検査器をリポジトリの import 設定に依存せず読む。"""
    return _load_checker_module(
        SCRIPT,
        "check_tenant_boundary_bypass_under_test",
    )


def _resolve_merge_base(base_ref: str, head_ref: str) -> str:
    """比較元と HEAD の merge-base を解決し、取れなければ検査を失敗させる。"""
    result = subprocess.run(
        ["git", "merge-base", base_ref, head_ref],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "stderr なし"
        raise AssertionError(
            f"{base_ref} と {head_ref} の merge-base を解決できない: {detail}"
        )
    merge_base = result.stdout.strip()
    if not merge_base:
        raise AssertionError(
            f"{base_ref} と {head_ref} の merge-base が空"
        )
    return merge_base


def _load_checker_from_revision(revision: str, destination: Path) -> ModuleType:
    """VCS 上の検査器を一時ファイルへ取り出して別モジュールとして読む。"""
    relative_script = SCRIPT.relative_to(REPOSITORY_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_script}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    destination.write_bytes(result.stdout)
    digest = hashlib.sha256(result.stdout).hexdigest()
    return _load_checker_module(
        destination,
        f"check_tenant_boundary_bypass_{digest}",
    )


def _checker_census(
    checker_module: ModuleType,
    *,
    repository_root: Path,
    source_root: Path,
) -> frozenset[CensusIdentity]:
    """検査器の全文走査結果を比較用の exact-set にする。"""
    contract = checker_module.load_contract(repository_root)
    violations = checker_module.scan_directory(source_root, contract=contract)
    return frozenset(
        (
            violation.path,
            violation.line,
            violation.end_line,
            violation.scope,
            violation.code,
            violation.symbol,
            violation.message,
        )
        for violation in violations
    )


def _compare_checker_census(
    reference_checker: ModuleType,
    candidate_checker: ModuleType,
    *,
    repository_root: Path,
    source_root: Path,
    reference_repository_root: Path | None = None,
) -> tuple[frozenset[CensusIdentity], frozenset[CensusIdentity]]:
    """merge-base 版から作業ツリー版への違反集合の増減を返す。

    この比較が証明するのは、両版が ``source_root`` にある現在の
    ``backend/src`` へ出す違反集合が同じこと、またはその差が期待どおりであること。
    現在のツリーに存在しない構文やコードへの挙動は証明せず、将来のコードは覆わない。
    """
    reference = _checker_census(
        reference_checker,
        repository_root=reference_repository_root or repository_root,
        source_root=source_root,
    )
    candidate = _checker_census(
        candidate_checker,
        repository_root=repository_root,
        source_root=source_root,
    )
    return candidate - reference, reference - candidate


def _insert_generated_use(template: str, use: str) -> str:
    """生成テンプレートの marker 位置へ同じ字下げで利用形を差し込む。"""
    marker = "__USE__"
    marker_index = template.index(marker)
    line_start = template.rfind("\n", 0, marker_index) + 1
    indentation = template[line_start:marker_index]
    assert not indentation.strip()
    replacement = "\n".join(
        f"{indentation}{line}" if line else ""
        for line in use.splitlines()
    )
    return template.replace(f"{indentation}{marker}", replacement, 1)


def _tenant_context_provenance_corpus() -> tuple[tuple[str, str], ...]:
    """入手経路・事前束縛・利用形・match pattern の直積を作る。"""
    routes = {
        "direct-assignment": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    factory = TenantContext
    __USE__
""",
        "if-expression": """\
from pitchlog.repositories.context import TenantContext
from external.helpers import safe

def build(__PREBOUND__flag, tenant_id):
    factory = TenantContext if flag else safe
    __USE__
""",
        "if-else": """\
from pitchlog.repositories.context import TenantContext
from external.helpers import safe

def build(__PREBOUND__flag, tenant_id):
    if flag:
        factory = TenantContext
    else:
        factory = safe
    __USE__
""",
        "try-except": """\
from pitchlog.repositories.context import TenantContext
from external.helpers import safe

def build(__PREBOUND__tenant_id):
    try:
        factory = TenantContext
    except RuntimeError:
        factory = safe
    __USE__
""",
        "list-subscript": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    factory = [TenantContext][0]
    __USE__
""",
        "dict-get": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    factory = {"context": TenantContext}.get("context")
    __USE__
""",
        "tuple-unpack": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    factory, = (TenantContext,)
    __USE__
""",
        "walrus": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    if factory := TenantContext:
        __USE__
""",
        "local-function-return": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    def acquire():
        return TenantContext
    factory = acquire()
    __USE__
""",
        "lambda-return": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    acquire = lambda: TenantContext
    factory = acquire()
    __USE__
""",
        "comprehension": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    factory = [item for item in (TenantContext,)][0]
    __USE__
""",
        "with-as": """\
from contextlib import nullcontext
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    with nullcontext(TenantContext) as factory:
        __USE__
""",
        "for-target": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    for factory in (TenantContext,):
        __USE__
""",
        "except-as": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    try:
        raise RuntimeError
    except TenantContext as factory:
        __USE__
""",
        "argument-default": """\
from pitchlog.repositories.context import TenantContext

def acquire(factory=TenantContext):
    return factory

def build(__PREBOUND__tenant_id):
    factory = acquire()
    __USE__
""",
        "function-import": """\
def build(__PREBOUND__tenant_id):
    from pitchlog.repositories.context import TenantContext as factory
    __USE__
""",
        "local-alias": """\
from pitchlog.repositories.context import TenantContext

def build(__PREBOUND__tenant_id):
    imported = TenantContext
    factory = imported
    __USE__
""",
        "global-rebinding": """\
from pitchlog.repositories.context import TenantContext

global_factory = TenantContext

def replace(other):
    global global_factory
    global_factory = other

def build(__PREBOUND__tenant_id):
    factory = global_factory
    __USE__
""",
        "star-import": """\
from pitchlog.repositories.context import *

def build(__PREBOUND__tenant_id):
    factory = TenantContext
    __USE__
""",
    }
    uses = {
        "direct-call": "return factory(tenant_id)",
        "class-base": "class Forged(factory):\n    pass\nreturn Forged",
        "closure-call": (
            "def invoke():\n    return factory(tenant_id)\nreturn invoke()"
        ),
        "attribute-call": "return factory.TenantContext(tenant_id)",
    }
    prebindings = {
        "unbound": "",
        "prebound": "factory, ",
    }
    corpus = [
        (
            f"{binding_id}/{route_id}/{use_id}",
            _insert_generated_use(
                template.replace("__PREBOUND__", prebinding),
                use,
            ),
        )
        for binding_id, prebinding in prebindings.items()
        for route_id, template in routes.items()
        for use_id, use in uses.items()
    ]
    match_patterns = {
        "scalar": ("", "TenantContext", "factory", "factory", ""),
        "sequence": ("", "[TenantContext]", "[factory]", "factory", ""),
        "mapping": (
            "",
            '{"k": TenantContext}',
            '{"k": factory}',
            "factory",
            "",
        ),
        "class": (
            """\
class SomeClass:
    def __init__(self, attr):
        self.attr = attr

""",
            "SomeClass(TenantContext)",
            "SomeClass(attr=factory)",
            "factory",
            "",
        ),
        "as": ("", "[TenantContext]", "[_] as factory", "factory", ""),
        "or": (
            "",
            '[TenantContext] if flag else {"k": TenantContext}',
            '[factory] | {"k": factory}',
            "factory",
            "flag, ",
        ),
        "star": ("", "[TenantContext]", "[*factory]", "factory[0]", ""),
    }
    for binding_id, prebinding in prebindings.items():
        for pattern_id, (
            preamble,
            subject,
            pattern,
            target,
            extra_arguments,
        ) in match_patterns.items():
            template = f"""\
from pitchlog.repositories.context import TenantContext

{preamble}def build({prebinding}{extra_arguments}tenant_id):
    match {subject}:
        case {pattern}:
            __USE__
"""
            target_uses = {
                "direct-call": f"return {target}(tenant_id)",
                "class-base": (
                    f"class Forged({target}):\n    pass\nreturn Forged"
                ),
                "closure-call": (
                    f"def invoke():\n    return {target}(tenant_id)\n"
                    "return invoke()"
                ),
                "attribute-call": f"return {target}.TenantContext(tenant_id)",
            }
            corpus.extend(
                (
                    f"{binding_id}/match-{pattern_id}/{use_id}",
                    _insert_generated_use(template, use),
                )
                for use_id, use in target_uses.items()
            )
    case_ids = [case_id for case_id, _ in corpus]
    assert len(case_ids) == len(set(case_ids))
    return tuple(corpus)


def _source_is_tb007_red(
    checker_module: ModuleType,
    contract: Any,
    source: str,
) -> bool:
    """生成ソースが指定 checker で条件 5 の red になるか返す。"""
    return any(
        violation.code == "TB007"
        for violation in checker_module.scan_source(
            source,
            path="pitchlog/services/generated_provenance_case.py",
            contract=contract,
        )
    )


def _prepare_reference_contract_root(destination: Path) -> Path:
    """旧 checker が読める裁定導入前スキーマの契約 root を一時作成する。"""
    contract_root = destination / "contracts" / "tenant_boundary"
    shutil.copytree(
        REPOSITORY_ROOT / "contracts" / "tenant_boundary",
        contract_root,
    )
    allowlist_path = destination / checker.DEFAULT_ALLOWLIST
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert isinstance(allowlist, dict)
    del allowlist["condition_2_adjudications"]
    allowlist_path.write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture_root = destination / "tests" / "fixtures" / "tenant_boundary"
    shutil.copytree(POSITIVE_ROOT, fixture_root / "positive")
    shutil.copytree(NEGATIVE_ROOT, fixture_root / "negative")
    return destination


def _assert_removed_tb007_matches_declared_relaxations(
    removed: frozenset[CensusIdentity],
) -> None:
    """減分が (iii) の宣言範囲への緩和だけで説明できると示す。"""
    source_root = REPOSITORY_ROOT / "backend" / "src"
    sources = {
        path.relative_to(source_root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.py"))
    }
    reexport_map = checker._build_reexport_map(sources)
    contract = checker.load_contract(REPOSITORY_ROOT)
    scanners: dict[str, tuple[ast.Module, Any]] = {}

    for identity in removed:
        path, line, end_line, _, code, symbol, _ = identity
        assert code == "TB007"
        if path not in scanners:
            tree = ast.parse(sources[path], filename=path)
            scanner = checker._SourceScanner(
                path=path,
                module=checker._module_name(path),
                tree=tree,
                changed_lines=None,
                contract=contract,
                reject_all_db_calls=False,
                reexport_map=reexport_map,
            )
            scanner.visit(tree)
            scanner._validate_call_coverage(tree)
            scanners[path] = (tree, scanner)
        tree, scanner = scanners[path]

        matching_calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if node.lineno != line or node.end_lineno != end_line:
                continue
            resolved = scanner.aliases.resolve(
                node.func
            ) or scanner._raw_expression(node.func)
            if symbol == "<unresolved-callable>" or symbol == resolved:
                matching_calls.append(node)

        assert matching_calls, identity
        explanations = []
        for node in matching_calls:
            if (
                isinstance(node.func, ast.Name)
                and id(node.func) in scanner.lexically_bound_name_ids
            ):
                explanations.append(node)
                continue
            constructor_name = contract.tenant_context.constructor_symbol.rsplit(
                ".", 1
            )[-1]
            callable_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if callable_name == constructor_name:
                continue
            resolved = scanner.aliases.resolve(
                node.func
            ) or scanner._raw_expression(node.func)
            reexport = scanner._reexport_resolution(node.func, resolved)
            if reexport is not None and (
                reexport.unresolved
                or contract.tenant_context.constructor_symbol in reexport.origins
            ):
                continue
            known_callable = scanner.flow.callable_symbol(node)
            if (
                known_callable is not None
                and known_callable
                != contract.tenant_context.constructor_symbol
            ):
                explanations.append(node)
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and known_callable is None
            ):
                explanations.append(node)
                continue
            alias_resolved = scanner.aliases.resolve(node.func)
            known_alias_callable = (
                scanner.aliases.resolve_known(node.func)
                if isinstance(node.func, ast.Name) and alias_resolved is not None
                else None
            )
            if (
                known_alias_callable is not None
                and scanner.aliases.canonical(known_alias_callable)
                != contract.tenant_context.constructor_symbol
                and known_callable is None
            ):
                explanations.append(node)

        assert explanations, identity


def _omit_flow_call_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """不変条件の負例用に flow の Call 登録だけを意図的に落とす。"""
    original_expression = checker._FlowProvenance._expression

    def omit_call_registration(
        self: Any,
        node: ast.AST,
        environment: dict[str, Any],
    ) -> Any:
        if isinstance(node, ast.Call):
            return checker._UNKNOWN_FLOW_VALUE
        return original_expression(self, node, environment)

    monkeypatch.setattr(
        checker._FlowProvenance,
        "_expression",
        omit_call_registration,
    )


def _call_coverage_sets(
    source: str,
    *,
    path: str,
    contract: Any,
) -> tuple[frozenset[int], frozenset[int], frozenset[int], frozenset[int]]:
    """同じ AST に対する Call の4登録集合を返す。"""
    tree = ast.parse(source, filename=path)
    scanner = checker._SourceScanner(
        path=path,
        module=checker._module_name(path),
        tree=tree,
        changed_lines=None,
        contract=contract,
        reject_all_db_calls=False,
    )
    scanner.visit(tree)
    return (
        frozenset(
            id(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
        ),
        frozenset(scanner.flow.callable_symbols),
        frozenset(scanner.flow.receiver_kinds),
        frozenset(scanner.checked_call_ids),
    )


checker = _load_checker()


def test_relative_import_from_init_uses_current_package_as_base() -> None:
    """__init__.py の相対 import は親でなく自パッケージを基点にする。"""
    assert checker._absolute_import_from_module(
        current_module="pitchlog.repositories",
        current_is_package=True,
        imported_module="context",
        level=1,
    ) == "pitchlog.repositories.context"


def test_relative_import_with_level_greater_than_one_ascends_packages() -> None:
    """level > 1 は現在モジュールの親パッケージからさらに上へ遡る。"""
    assert checker._absolute_import_from_module(
        current_module="pitchlog.services.handlers.command",
        current_is_package=False,
        imported_module="repositories.context",
        level=3,
    ) == "pitchlog.repositories.context"


def _read_contract_asset(relative_path: Path) -> dict[str, Any]:
    """テナント境界の契約資産を JSON object として読む。"""
    value = json.loads((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _fixture_source(path: Path) -> str:
    """fixture を UTF-8 で読む。"""
    return path.read_text(encoding="utf-8")


def _external_source(path: str) -> bytes:
    """作業ツリーの外部凍結対象を読む。"""
    return (REPOSITORY_ROOT / path).read_bytes()


def _accepted_snapshot(relative_path: Path) -> dict[str, Any]:
    """純粋な遷移検査用に先頭履歴を受理済み状態へ変える。"""
    asset = _read_contract_asset(relative_path)
    entry = asset["baseline_control"]["history"][0]
    entry["source_commit"] = "abcdef0"
    entry["approved_by"] = "テスト承認者"
    entry["approved_on"] = "2026-09-20"
    return asset


def _first_adoption_snapshot(relative_path: Path) -> dict[str, Any]:
    """現在資産から初回受理時点の識別値と先頭履歴だけを取り出す。"""
    asset = _read_contract_asset(relative_path)
    control = asset["baseline_control"]
    identity = control["identity"]
    first_entry = control["history"][0]
    current_identifiers = list(first_entry["new_baseline_identifiers"])
    control["history"] = [first_entry]
    identity["current_identifiers"] = current_identifiers
    revision_field = identity["field"]
    identifier_field, revision = current_identifiers[0].split(":", maxsplit=1)
    assert identifier_field == revision_field
    asset[revision_field] = int(revision)
    return asset


def _contract_digest(value: dict[str, Any]) -> str:
    """source_digest 欄を除く JSON 資産の正規化 digest を計算する。"""
    payload = dict(value)
    payload.pop("source_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _changed_lines_containing(source: str, *needles: str) -> frozenset[int]:
    """指定文字列を含む変異行を差分母集団として返す。"""
    lines = source.splitlines()
    changed = {
        line_number
        for line_number, line in enumerate(lines, start=1)
        if any(needle in line for needle in needles)
    }
    assert all(any(needle in line for line in lines) for needle in needles)
    return frozenset(changed)


def _scan_diff_mutation(
    baseline: str,
    mutated: str,
    *,
    path: str,
    changed_lines: frozenset[int],
    contract: Any,
) -> list[Any]:
    """差分行を入口に、基準版と変異後の全行比較を実行する。"""
    assert changed_lines
    assert (
        checker.scan_source_change(
            None,
            baseline,
            path=path,
            changed_lines=frozenset(
                range(1, len(baseline.splitlines()) + 1)
            ),
            contract=contract,
        )
        == []
    )
    return checker.scan_source_change(
        baseline,
        mutated,
        path=path,
        changed_lines=changed_lines,
        contract=contract,
    )


def _commit_test_repository(repository: Path, message: str) -> str:
    """一時リポジトリの全変更をコミットして commit ID を返す。"""
    checker._run_git(repository, ["add", "."])
    checker._run_git(
        repository,
        [
            "-c",
            "user.name=Tenant Boundary Test",
            "-c",
            "user.email=tenant-boundary@example.invalid",
            "commit",
            "-m",
            message,
        ],
    )
    return checker._run_git(repository, ["rev-parse", "HEAD"]).strip()


def _initialize_test_repository(
    tmp_path: Path,
    sources: dict[str, str],
) -> tuple[Path, str]:
    """実際の差分検査を行える最小 Git リポジトリを作る。"""
    repository = tmp_path / "repository"
    shutil.copytree(
        REPOSITORY_ROOT / "contracts" / "tenant_boundary",
        repository / "contracts" / "tenant_boundary",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary",
        repository / "tests" / "fixtures" / "tenant_boundary",
    )
    script_path = repository / "scripts" / SCRIPT.name
    script_path.parent.mkdir(parents=True)
    shutil.copy2(SCRIPT, script_path)
    for relative, source in sources.items():
        path = repository / "backend" / "src" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    checker._run_git(repository, ["init"])
    source_commits = {
        entry["source_commit"]
        for relative_path in checker.FROZEN_BASELINE_ASSETS
        for entry in _read_contract_asset(relative_path)["baseline_control"]["history"]
        if entry["source_commit"] != checker.PENDING_SOURCE_COMMIT
    }
    for source_commit in sorted(source_commits):
        checker._run_git(
            repository,
            ["fetch", "--no-tags", str(REPOSITORY_ROOT), source_commit],
        )
    return repository, _commit_test_repository(repository, "baseline")


def _write_test_repository_sources(
    repository: Path,
    sources: dict[str, str],
) -> None:
    """一時リポジトリの製品ソースを変異後の内容へ更新する。"""
    for relative, source in sources.items():
        path = repository / "backend" / "src" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def _point_default_base_ref_at(repository: Path, commit: str) -> None:
    """一時リポジトリの凍結既定比較元を指定 commit へ向ける。"""
    assert checker.DEFAULT_BASE_REF == "origin/develop"
    checker._run_git(
        repository,
        ["update-ref", "refs/remotes/origin/develop", commit],
    )


def _actual_implementation_mutation(case_id: str) -> tuple[str, str, str]:
    """既存の製品変異テストと同じ基準版・変異版を返す。"""
    if case_id == "base-direct-sql":
        relative = "pitchlog/repositories/base.py"
        source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
        mutated = source.replace(
            "from sqlalchemy.orm import Session",
            "from sqlalchemy import text\nfrom sqlalchemy.orm import Session",
            1,
        ).replace(
            "            execution_result = self._session.execute(\n",
            "            self._session.execute(text(\"SELECT 1\"))\n"
            "            execution_result = self._session.execute(\n",
            1,
        )
    elif case_id == "binding-nonlocal-set-config":
        relative = "pitchlog/repositories/binding.py"
        source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
        mutated = source.replace(
            "SELECT set_config('app.tenant_id', :tenant_id, true)",
            "SELECT set_config('app.tenant_id', :tenant_id, false)",
            1,
        )
    elif case_id == "base-call-outside-allowed-symbol":
        relative = "pitchlog/repositories/base.py"
        source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
        mutated = source.replace(
            "        _operation_spec(operation)\n",
            "        self._session.execute(operation)\n"
            "        _operation_spec(operation)\n",
            1,
        )
    elif case_id == "binding-unlisted-symbol":
        relative = "pitchlog/repositories/binding.py"
        source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
        mutation = """

def _unlisted_database_access(session: Session) -> None:
    session.execute(text("SELECT 1"))
"""
        mutated = f"{source.rstrip()}{mutation}\n"
    else:
        raise AssertionError(f"未定義の実装変異: {case_id}")

    assert mutated != source
    return relative, source, mutated


def test_checker_census_matches_merge_base(tmp_path: Path) -> None:
    """センサス差分を今回変更した TB002・TB007 の写像だけに固定する。"""
    merge_base = _resolve_merge_base("origin/develop", "HEAD")
    baseline_checker = _load_checker_from_revision(
        merge_base,
        tmp_path / "check_tenant_boundary_bypass_merge_base.py",
    )
    reference_repository_root = _prepare_reference_contract_root(
        tmp_path / "reference_repository"
    )

    added, removed = _compare_checker_census(
        baseline_checker,
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=REPOSITORY_ROOT / "backend" / "src",
        reference_repository_root=reference_repository_root,
    )

    assert added
    assert {identity[4] for identity in added} <= {"TB002", "TB007"}
    assert removed
    assert {identity[4] for identity in removed} <= {"TB002", "TB007"}
    removed_tb007 = frozenset(
        identity for identity in removed if identity[4] == "TB007"
    )
    assert removed_tb007
    _assert_removed_tb007_matches_declared_relaxations(removed_tb007)
    adjudicated_symbols = set(EXPECTED_CONDITION_2_ADJUDICATIONS)
    adjudicated_names = {
        symbol.rsplit(".", 1)[-1] for symbol in adjudicated_symbols
    }
    current_census = _checker_census(
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=REPOSITORY_ROOT / "backend" / "src",
    )
    for identity in removed:
        if identity[4] != "TB002" or identity[5] in (
            adjudicated_symbols | adjudicated_names
        ):
            continue
        assert any(
            current[0] == identity[0]
            and current[1] == identity[1]
            and current[4] == "TB002"
            for current in current_census
        )


def test_generated_provenance_corpus_never_weakens_develop(
    tmp_path: Path,
) -> None:
    """生成経路について develop が red なら HEAD も必ず red にする。"""
    develop_checker = _load_checker_from_revision(
        "origin/develop",
        tmp_path / "check_tenant_boundary_bypass_develop.py",
    )
    assert DEVELOP_REPOSITORY_ROOT.is_dir(), (
        "develop checker の契約資産を読むメインツリーが存在しない: "
        f"{DEVELOP_REPOSITORY_ROOT}"
    )
    develop_contract = develop_checker.load_contract(DEVELOP_REPOSITORY_ROOT)
    head_contract = checker.load_contract(REPOSITORY_ROOT)
    outcomes: list[tuple[str, bool, bool]] = []
    for case_id, source in _tenant_context_provenance_corpus():
        develop_red = _source_is_tb007_red(
            develop_checker,
            develop_contract,
            source,
        )
        head_red = _source_is_tb007_red(checker, head_contract, source)
        outcomes.append((case_id, develop_red, head_red))

    weakened = [
        case_id
        for case_id, develop_red, head_red in outcomes
        if develop_red and not head_red
    ]
    assert not weakened, (
        "develop では TB007 だが HEAD で green になる生成経路: "
        + ", ".join(weakened)
    )


def test_dynamic_method_on_known_non_db_receiver_is_green() -> None:
    """既知の非 DB instance から得た動的 method は過剰拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
class Runner:
    def run(self, handler_name):
        handler = getattr(self, handler_name)
        return handler()
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/dynamic_handler.py",
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize(
    "case_id",
    (
        "unbound/dict-get/direct-call",
        "unbound/local-function-return/direct-call",
        "unbound/argument-default/direct-call",
        "unbound/match-scalar/direct-call",
        "unbound/dict-get/class-base",
        "unbound/local-function-return/class-base",
        "unbound/argument-default/class-base",
        "prebound/match-sequence/direct-call",
        "prebound/match-sequence/closure-call",
        "prebound/match-mapping/direct-call",
        "prebound/match-mapping/closure-call",
    ),
)
def test_previously_weakened_provenance_routes_are_red(case_id: str) -> None:
    """前版比較で見つかった経路を HEAD 単独でも TB007 に固定する。"""
    source = dict(_tenant_context_provenance_corpus())[case_id]
    contract = checker.load_contract(REPOSITORY_ROOT)

    assert _source_is_tb007_red(checker, contract, source)


def test_condition_5_scope_declaration_is_verbatim_in_design() -> None:
    """検査器の保証宣言が設計書 1-1 / 6-0 と逐語一致する。"""
    module_docstring = checker.__doc__
    assert module_docstring is not None
    declaration = module_docstring.split("\n\n", 1)[1]
    design = (
        REPOSITORY_ROOT / "docs/features/tenant-boundary-enforcement/design.md"
    ).read_text(encoding="utf-8")

    assert design.count(declaration) == 2


def test_condition_2_patterns_and_adjudications_are_exact_sets() -> None:
    """広い候補7本と理由付き裁定6件を資産どおり固定する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    condition2 = next(rule for rule in contract.rules if rule.condition == 2)

    assert tuple(pattern.pattern for pattern in condition2.patterns) == (
        EXPECTED_CONDITION_2_PATTERNS
    )
    assert {
        item.symbol: item.reason
        for item in contract.condition2_adjudications
    } == EXPECTED_CONDITION_2_ADJUDICATIONS


def test_condition_2_adjudication_requires_a_reason() -> None:
    """裁定理由を欠く資産を読み込み時に拒否する。"""
    allowlist = _read_contract_asset(checker.DEFAULT_ALLOWLIST)
    del allowlist["condition_2_adjudications"][0]["reason"]
    inventory, inventory_bytes = checker._read_json(
        REPOSITORY_ROOT / checker.DEFAULT_INVENTORY
    )
    apis, _, _, _ = checker._load_inventory(inventory)

    with pytest.raises(checker.ContractError, match=r"missing=\['reason'\]"):
        checker._load_allowlist(allowlist, inventory_bytes, apis)


@pytest.mark.parametrize(
    "symbol",
    tuple(sorted(EXPECTED_CONDITION_2_ADJUDICATIONS)),
)
def test_condition_2_adjudicated_symbols_are_green(symbol: str) -> None:
    """完全修飾参照と同一モジュールの裸クラス名を同じ裁定で許可する。"""
    module, class_name = symbol.rsplit(".", 1)
    path = f"{module.replace('.', '/')}.py"
    source = f"""\
class {class_name}:
    pass


value = {class_name}()
"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path=path,
        contract=contract,
    )

    assert violations == []


def test_condition_2_adjudicated_import_is_green() -> None:
    """別モジュールからの裸の import 名も完全修飾した裁定へ照合する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from pitchlog.domaingen.core import GenerationError

error_type = GenerationError
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/generation_errors.py",
        contract=contract,
    )

    assert violations == []


def test_condition_2_adjudicated_module_constant_is_green() -> None:
    """再束縛のない module 定数を完全修飾した裁定へ照合する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
EXIT_GENERATION_FAILED = 1


def main():
    return EXIT_GENERATION_FAILED
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/domaingen/core.py",
        contract=contract,
    )

    assert violations == []


def test_condition_2_adjudicated_import_shadowed_by_parameter_is_red() -> None:
    """裁定済み import と同名でも字句引数なら裁定せず拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from pitchlog.domaingen.core import GenerationError


def use(GenerationError):
    return GenerationError
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/shadowed_generation_error.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB002"}


@pytest.mark.parametrize(
    "source",
    (
        "def use(generation, /):\n    return 1\n",
        "def use(generation):\n    return 1\n",
        "def use(*, generation):\n    return 1\n",
        "def use(*generation):\n    return 1\n",
        "def use(**generation):\n    return 1\n",
        "use = lambda generation: 1\n",
    ),
    ids=(
        "positional-only",
        "positional-or-keyword",
        "keyword-only",
        "variadic-positional",
        "variadic-keyword",
        "lambda",
    ),
)
def test_condition_2_argument_names_are_syntactic_candidates(source: str) -> None:
    """未使用でも全種類の ast.arg.arg を条件 2 の候補にする。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/generation_argument.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB002"}


def test_unmatched_argument_name_is_green() -> None:
    """条件 2 の候補に一致しない未使用引数は拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        "def use(other):\n    return 1\n",
        path="pitchlog/services/ordinary_argument.py",
        contract=contract,
    )

    assert violations == []


def test_condition_2_unadjudicated_generation_is_red() -> None:
    """裁定に無い新しい Generation シンボルを fail-closed で拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
class FutureGeneration:
    pass
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/domaingen/future.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB002"}


def test_condition_2_local_generation_variable_is_not_adjudicated() -> None:
    """型が既知でも裸の局所変数 generation は裁定せず拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
class MutationGeneration:
    pass


generation: MutationGeneration
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/domainmut/engine.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB002"}


def test_recording_generation_remains_red_in_product_tree() -> None:
    """記録権世代の実モデル参照4行を条件2の候補として維持する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source_root = REPOSITORY_ROOT / "backend" / "src"
    path = "pitchlog/db/recording_rights/models.py"

    violations = checker.scan_source(
        _fixture_source(source_root / path),
        path=path,
        contract=contract,
    )
    condition2 = [violation for violation in violations if violation.code == "TB002"]

    recording_generation_lines = {
        item.line
        for item in condition2
        if "RecordingGeneration" in item.symbol
    }
    assert recording_generation_lines == {153, 246, 247, 248}


def test_product_call_coverage_sets_are_complete() -> None:
    """製品 tree の全 Call が flow と scanner の両方へ登録される。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source_root = REPOSITORY_ROOT / "backend" / "src"
    totals = [0, 0, 0, 0]

    for source_path in sorted(source_root.rglob("*.py")):
        relative = source_path.relative_to(source_root).as_posix()
        coverage = _call_coverage_sets(
            _fixture_source(source_path),
            path=relative,
            contract=contract,
        )
        assert coverage[0] == coverage[1] == coverage[2] == coverage[3], relative
        for index, call_ids in enumerate(coverage):
            totals[index] += len(call_ids)

    # 総数のべた書きは develop 側の変更で古くなる(実際 2261 -> 2874 で落ちた)。
    # 守りたいのは「母集団が空でない」ことと「4 集合が全ファイルで一致する」ことなので、
    # その 2 つだけを固定する。各ファイルの一致は上のループが既に検証している。
    assert totals[0] > 0
    assert len(set(totals)) == 1


@pytest.mark.parametrize(
    "fixture_name",
    (
        "c5_context_ifexp_origin_merge.py",
        "c5_context_if_else_origin_merge.py",
        "c5_context_try_except_origin_merge.py",
        "c5_context_match_origin_merge.py",
        "c5_context_container_subscript.py",
        "c5_context_conditional_alias_closure.py",
        "c5_context_conditional_alias_class_base.py",
    ),
)
def test_flow_preserves_tenant_context_in_possible_origin_sets(
    fixture_name: str,
) -> None:
    """合流・コンテナ・閉包・基底を越えて構築起源を保持する。"""
    relative = f"pitchlog/services/{fixture_name}"
    source = _fixture_source(NEGATIVE_ROOT / relative)
    tree = ast.parse(source, filename=relative)
    contract = checker.load_contract(REPOSITORY_ROOT)
    scanner = checker._SourceScanner(
        path=relative,
        module=checker._module_name(relative),
        tree=tree,
        source=source,
        changed_lines=None,
        contract=contract,
        reject_all_db_calls=False,
    )
    constructor = contract.tenant_context.constructor_symbol

    call_origins = (
        scanner.flow.callable_value(node).origins
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    )
    base_origins = (
        scanner.flow.class_base_value(node).origins
        for node in ast.walk(tree)
    )
    assert any(constructor in origins for origins in call_origins) or any(
        constructor in origins for origins in base_origins
    )

    violations = checker.scan_source(
        source,
        path=relative,
        contract=contract,
    )
    assert "TB007" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    ("source", "expected_tb007"),
    (
        ("""\
def assign(factory, values):
    factory().item, *factory().rest = values
""", False),
        ("""\
def select(value, factory):
    match value:
        case _ if factory():
            return None
""", False),
        ("""\
try:
    pass
except* factory():
    pass
""", True),
        ("""\
def run[T: factory()](value: annotate()) -> returns():
    return value
""", True),
        ("""\
class Example[T: bound()](metaclass=factory()):
    pass
""", True),
    ),
)
def test_additional_call_positions_satisfy_coverage_invariant(
    source: str,
    expected_tb007: bool,
) -> None:
    """構文マトリクス上の Call を flow と scanner の双方で覆う。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/coverage_matrix.py",
        contract=contract,
    )

    assert ("TB007" in {violation.code for violation in violations}) is expected_tb007


@pytest.mark.parametrize("omitted_layer", ("flow", "scanner"))
def test_call_coverage_invariant_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    omitted_layer: str,
) -> None:
    """flow または scanner の訪問漏れを ContractError にする。"""
    if omitted_layer == "flow":
        _omit_flow_call_registration(monkeypatch)
    else:

        def omit_scanner_call(self: Any, node: ast.Call) -> None:
            _ = (self, node)

        monkeypatch.setattr(
            checker._SourceScanner,
            "visit_Call",
            omit_scanner_call,
        )
    contract = checker.load_contract(REPOSITORY_ROOT)

    with pytest.raises(checker.ContractError, match="Call 被覆不変条件"):
        checker.scan_source(
            "def run(factory):\n    return factory()\n",
            path="pitchlog/services/coverage_probe.py",
            contract=contract,
        )


def test_call_coverage_mismatch_is_not_cancelled_across_entrypoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """基準版と新側に同じ訪問漏れがあっても判定不能を相殺しない。"""
    relative = "pitchlog/services/coverage_probe.py"
    baseline = """\
def run(factory):
    return factory()


marker = 0
"""
    head = baseline.replace("marker = 0", "marker = 1")
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    _write_test_repository_sources(repository, {relative: head})
    _commit_test_repository(repository, "change unrelated marker")
    contract = checker.load_contract(repository)
    _omit_flow_call_registration(monkeypatch)

    with pytest.raises(checker.ContractError, match="Call 被覆不変条件"):
        checker.scan_source_change(
            baseline,
            head,
            path=relative,
            changed_lines=frozenset({5}),
            contract=contract,
        )
    with pytest.raises(checker.ContractError, match="Call 被覆不変条件"):
        checker.check_repository(repository, base_ref=base_ref)

    assert checker.main(
        ["--root", str(repository), "--base-ref", base_ref]
    ) == 2
    assert "Call 被覆不変条件" in capsys.readouterr().err

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _FLOW_OMISSION_RUNNER,
            str(repository / "scripts" / SCRIPT.name),
            "--root",
            str(repository),
            "--base-ref",
            base_ref,
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Call 被覆不変条件" in result.stderr


def test_positive_fixtures_pass() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_directory(POSITIVE_ROOT, contract=contract)

    assert violations == []


def test_frozen_baseline_asset_paths_are_an_exact_set() -> None:
    """tenant_boundary 配下の 7 資産を履歴検査から漏らさない。"""
    asset_root = REPOSITORY_ROOT / "contracts" / "tenant_boundary"
    actual = {
        path.relative_to(REPOSITORY_ROOT)
        for path in asset_root.glob("*.json")
    }

    assert actual == set(checker.FROZEN_BASELINE_ASSETS)


@pytest.mark.parametrize("relative_path", checker.FROZEN_BASELINE_ASSETS)
def test_every_frozen_baseline_asset_has_a_valid_chained_history(
    relative_path: Path,
) -> None:
    """初回受理と末尾識別値を検査し、先頭の pending 状態だけを固定する。"""
    asset = _read_contract_asset(relative_path)

    history = checker._validate_baseline_control(
        asset,
        relative_path.as_posix(),
    )

    assert history
    assert history[0]["source_commit"] == checker.PENDING_SOURCE_COMMIT
    assert history[0]["previous_baseline_identifiers"] == [checker.NO_BASELINE]
    assert history[-1]["new_baseline_identifiers"] == asset["baseline_control"][
        "identity"
    ]["current_identifiers"]


@pytest.mark.parametrize(
    "field",
    (
        "source_commit",
        "new_baseline_identifiers",
        "previous_baseline_identifiers",
        "change",
        "movement_fact",
        "reason",
        "approved_by",
        "approved_on",
    ),
)
def test_missing_baseline_history_field_is_red(field: str) -> None:
    """7.7-2 の必須記録を 1 項目でも省く変異を拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _read_contract_asset(relative_path)
    mutated = copy.deepcopy(asset)
    del mutated["baseline_control"]["history"][0][field]

    with pytest.raises(checker.ContractError):
        checker._validate_baseline_control(mutated, relative_path.as_posix())


def test_changed_baseline_history_entry_is_red() -> None:
    """既存記録の書き換えを append-only 比較で拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    current["baseline_control"]["history"][0]["reason"] = "書き換え"

    with pytest.raises(checker.ContractError):
        checker._validate_history_append_only(
            previous,
            current,
            relative_path.as_posix(),
        )


def test_deleted_baseline_history_entry_is_red() -> None:
    """既存記録の削除を append-only 比較で拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    current["contract_revision"] = 6
    current["baseline_control"]["identity"]["current_identifiers"] = [
        "contract_revision:6"
    ]
    current["baseline_control"]["history"].pop()

    with pytest.raises(checker.ContractError):
        checker._validate_history_append_only(
            previous,
            current,
            relative_path.as_posix(),
        )


def test_merge_base_pending_history_is_still_append_only() -> None:
    """merge-base に現にある記録は未承認表示でも書き換えを拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _read_contract_asset(relative_path)
    current = copy.deepcopy(previous)
    current["baseline_control"]["history"][0]["reason"] = "書き換え"

    with pytest.raises(checker.ContractError, match="既存履歴"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=_external_source,
            current_external_loader=_external_source,
        )


def test_first_adoption_previous_identifier_must_be_no_baseline() -> None:
    """merge-base に資産が無い初回受理の直前値を推測値にできない。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _first_adoption_snapshot(relative_path)
    mutated = copy.deepcopy(asset)
    mutated["baseline_control"]["history"][0][
        "previous_baseline_identifiers"
    ] = ["contract_revision:999"]

    with pytest.raises(checker.ContractError, match="NO_BASELINE"):
        checker._validate_baseline_transition(
            None,
            mutated,
            relative_path.as_posix(),
            previous_external_loader=lambda _path: b"",
            current_external_loader=_external_source,
        )


def test_first_history_entry_does_not_imply_no_previous_baseline() -> None:
    """履歴の先頭という理由だけで直前基準なしと推定しない。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _read_contract_asset(relative_path)
    mutated = copy.deepcopy(asset)
    mutated["baseline_control"]["history"][0][
        "previous_baseline_identifiers"
    ] = ["legacy_baseline:1"]

    history = checker._validate_baseline_control(
        mutated,
        relative_path.as_posix(),
    )

    assert history[0]["previous_baseline_identifiers"] == ["legacy_baseline:1"]


def test_reported_pattern_removal_without_revision_or_history_is_red() -> None:
    """禁止 pattern を黙って 1 本削る敵対レビュー再現を射影比較で拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    current["conditions"][0]["patterns"].pop()

    with pytest.raises(checker.ContractError, match="ちょうど 1 件"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=_external_source,
            current_external_loader=_external_source,
        )


def test_history_added_without_projection_movement_is_red() -> None:
    """射影が動いていない受理への不要な履歴追加を拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    extra = copy.deepcopy(current["baseline_control"]["history"][-1])
    extra["source_commit"] = "abcdef1"
    current_identifiers = current["baseline_control"]["identity"][
        "current_identifiers"
    ]
    extra["previous_baseline_identifiers"] = list(current_identifiers)
    extra["new_baseline_identifiers"] = list(current_identifiers)
    current["baseline_control"]["history"].append(extra)

    with pytest.raises(checker.ContractError, match="射影が動いていない"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=_external_source,
            current_external_loader=_external_source,
        )


def test_checker_pass_fail_mapping_change_requires_revision_and_history() -> None:
    """検査器自身の変更も外部凍結射影の移動として検出する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)

    with pytest.raises(checker.ContractError, match="ちょうど 1 件"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=lambda _path: b"old pass/fail mapping",
            current_external_loader=lambda _path: b"new pass/fail mapping",
        )


def test_negative_fixture_ids_are_an_exact_set_and_each_fixture_is_red() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    fixture_ids = {fixture.id for fixture in contract.negative_fixtures}
    assert fixture_ids == EXPECTED_NEGATIVE_IDS
    fixture_sources = {
        fixture.path: _fixture_source(NEGATIVE_ROOT / fixture.path)
        for fixture in contract.negative_fixtures
    }
    reexport_map = checker._build_reexport_map(
        REEXPORT_SUPPORT_SOURCES | fixture_sources
    )

    observed_conditions: set[int] = set()
    for fixture in contract.negative_fixtures:
        source = fixture_sources[fixture.path]
        violations = checker.scan_source_change(
            None,
            source,
            path=fixture.path,
            changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
            contract=contract,
            head_reexport_map=reexport_map,
        )
        codes = {violation.code for violation in violations}
        assert fixture.expected_error in codes, (
            f"{fixture.id} が期待どおり red でない: "
            f"expected={fixture.expected_error}, actual={sorted(codes)}"
        )
        observed_conditions.add(fixture.condition)

    assert observed_conditions == {1, 2, 3, 4, 5}


def test_integrity_secret_default_is_checked_before_allowed_function_scope() -> None:
    """秘密の default capture を許可シンボルの本体免除へ混入させない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = _fixture_source(
        NEGATIVE_ROOT
        / "pitchlog/services/c5_secret_in_default_capture.py"
    )

    violations = checker.scan_source(
        source,
        path="pitchlog/repositories/context.py",
        contract=contract,
    )

    assert [
        (violation.code, violation.symbol, violation.scope)
        for violation in violations
    ] == [
        (
            "TB007",
            "pitchlog.repositories.context._TENANT_CONTEXT_SECRET",
            "pitchlog.repositories.context.<module>",
        )
    ]


def test_relative_tenant_context_import_is_resolved_and_red() -> None:
    """同一 package の相対 import も絶対 constructor として拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative_path = "pitchlog/repositories/c5_context_relative_import.py"
    source = _fixture_source(NEGATIVE_ROOT / relative_path)

    violations = checker.scan_source(
        source,
        path=relative_path,
        contract=contract,
    )

    assert [
        (violation.code, violation.symbol)
        for violation in violations
    ] == [
        (
            "TB007",
            "pitchlog.repositories.context.TenantContext",
        )
    ]


@pytest.mark.parametrize(
    "fixture_id",
    (
        "C5_CONTEXT_REEXPORT_FACADE",
        "C5_CONTEXT_REEXPORT_SUBCLASS",
    ),
)
def test_reexport_fixture_resolves_to_tenant_context_origin(
    fixture_id: str,
) -> None:
    """別名 Context の façade と継承元が canonical 起源へ到達する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    sources = {
        fixture.path: _fixture_source(NEGATIVE_ROOT / fixture.path)
        for fixture in contract.negative_fixtures
    }
    reexport_map = checker._build_reexport_map(
        REEXPORT_SUPPORT_SOURCES | sources
    )
    fixture = next(
        fixture
        for fixture in contract.negative_fixtures
        if fixture.id == fixture_id
    )

    resolution = checker._lookup_reexport_symbol(
        "Context",
        current_module=checker._module_name(fixture.path),
        reexport_map=reexport_map,
    )

    assert resolution is not None
    assert resolution.unresolved is False
    assert contract.tenant_context.constructor_symbol in resolution.origins


@pytest.mark.parametrize(
    "fixture_id",
    (
        "C5_CONTEXT_REEXPORT_DEPTH_LIMIT",
        "C5_CONTEXT_REEXPORT_STAR",
        "C5_CONTEXT_REEXPORT_CYCLE",
        "C5_CONTEXT_REEXPORT_SELF_REFERENCE",
        "C5_CONTEXT_REEXPORT_CONDITIONAL",
        "C5_CONTEXT_REEXPORT_MISSING_MODULE",
        "C5_CONTEXT_REEXPORT_UNSUPPORTED_ASSIGN",
    ),
)
def test_reexport_fixture_records_each_unresolved_cause(
    fixture_id: str,
) -> None:
    """宣言した7種類の解決不能原因を unresolved へ集約する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    sources = {
        fixture.path: _fixture_source(NEGATIVE_ROOT / fixture.path)
        for fixture in contract.negative_fixtures
    }
    reexport_map = checker._build_reexport_map(
        REEXPORT_SUPPORT_SOURCES | sources
    )
    fixture = next(
        fixture
        for fixture in contract.negative_fixtures
        if fixture.id == fixture_id
    )

    resolution = checker._lookup_reexport_symbol(
        "Context",
        current_module=checker._module_name(fixture.path),
        reexport_map=reexport_map,
    )

    assert resolution is not None
    assert resolution.unresolved is True
    if fixture_id == "C5_CONTEXT_REEXPORT_CONDITIONAL":
        assert resolution.origins == frozenset(
            {"external.first.Context", "external.second.Context"}
        )


def test_absent_external_reexport_modules_are_safe_terminal_origins() -> None:
    """写像に無い stdlib・third-party module を欠落扱いしない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/services/external_reexports.py"
    source = '''\
from pathlib import Context as StdlibContext
from third_party.facade import Context as ThirdPartyContext

stdlib_context = StdlibContext("tenant")
third_party_context = ThirdPartyContext("tenant")
'''
    reexport_map = checker._build_reexport_map({relative: source})

    for export_name in ("StdlibContext", "ThirdPartyContext"):
        resolution = checker._lookup_reexport_symbol(
            export_name,
            current_module=checker._module_name(relative),
            reexport_map=reexport_map,
        )
        assert resolution is not None
        assert resolution.unresolved is False

    assert checker.scan_source(
        source,
        path=relative,
        contract=contract,
        reexport_map=reexport_map,
    ) == []


def test_import_module_static_reexport_resolves_to_tenant_context() -> None:
    """import module と属性代入から作る再輸出も canonical 起源へ辿る。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    facade = "pitchlog/services/static_facade.py"
    consumer = "pitchlog/services/static_consumer.py"
    sources = {
        **REEXPORT_SUPPORT_SOURCES,
        facade: '''\
import pitchlog.repositories.context as context_module

Context = context_module.TenantContext
''',
        consumer: '''\
from pitchlog.services.static_facade import Context

context = Context("tenant")
''',
    }
    reexport_map = checker._build_reexport_map(sources)
    resolution = checker._lookup_reexport_symbol(
        "Context",
        current_module=checker._module_name(facade),
        reexport_map=reexport_map,
    )

    assert resolution is not None
    assert resolution.unresolved is False
    assert contract.tenant_context.constructor_symbol in resolution.origins
    assert "TB007" in {
        violation.code
        for violation in checker.scan_source(
            sources[consumer],
            path=consumer,
            contract=contract,
            reexport_map=reexport_map,
        )
    }


def test_bare_tenant_context_suffix_is_red_for_external_callable() -> None:
    """裸の TenantContext 末尾名も既知の外部起源で免除しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/services/external_tenant_context.py"
    source = '''\
from external.facade import TenantContext

context = TenantContext("tenant")
'''

    violations = checker.scan_source(
        source,
        path=relative,
        contract=contract,
    )

    assert [
        (violation.code, violation.symbol) for violation in violations
    ] == [("TB007", "TenantContext")]


def test_unrelated_internal_context_reexport_stays_green() -> None:
    """別モジュールで定義された無関係な同名 Context を拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    consumer = "pitchlog/services/safe_consumer.py"
    sources = {
        "pitchlog/services/safe_context.py": '''\
class Context:
    pass
''',
        consumer: '''\
from pitchlog.services.safe_context import Context

context = Context()
''',
    }
    reexport_map = checker._build_reexport_map(sources)

    assert checker.scan_source(
        sources[consumer],
        path=consumer,
        contract=contract,
        reexport_map=reexport_map,
    ) == []


@pytest.mark.parametrize("condition", (1, 2, 3, 4, 5))
def test_all_negative_fixtures_are_red_through_real_commit_diff(
    tmp_path: Path,
    condition: int,
) -> None:
    """契約済み負例 110 本を条件別の実コミット列で拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    assert {fixture.id for fixture in contract.negative_fixtures} == (
        EXPECTED_NEGATIVE_IDS
    )
    fixtures = tuple(
        fixture
        for fixture in contract.negative_fixtures
        if fixture.condition == condition
    )
    assert fixtures
    baseline_sources = {
        **REEXPORT_SUPPORT_SOURCES,
        **{fixture.path: "pass\n" for fixture in fixtures},
    }
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        baseline_sources,
    )

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0

    mutated_sources = {
        fixture.path: _fixture_source(NEGATIVE_ROOT / fixture.path)
        for fixture in fixtures
    }
    _write_test_repository_sources(repository, mutated_sources)
    _commit_test_repository(repository, "apply all negative fixtures")
    violations = checker.check_repository(repository, base_ref=base_ref)
    observed = {(violation.path, violation.code) for violation in violations}

    for fixture in fixtures:
        assert (fixture.path, fixture.expected_error) in observed, (
            f"{fixture.id} が実コミット列で期待どおり red でない: "
            f"expected={fixture.expected_error}"
        )
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_ci_path_detects_committed_bypass_and_cli_exits_one(
    tmp_path: Path,
) -> None:
    """実コミット差分を check_repository と subprocess の CLI から検査する。"""
    relative = "pitchlog/services/ci_probe.py"
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: "pass\n"},
    )
    bypass = '''\
from sqlalchemy.orm import Session


def read_other_tenant(work: Session) -> object:
    return work.execute("SELECT * FROM games")
'''
    _write_test_repository_sources(repository, {relative: bypass})
    _commit_test_repository(repository, "add tenant boundary bypass")

    violations = checker.check_repository(repository, base_ref=base_ref)

    assert (relative, "TB005") in {
        (violation.path, violation.code) for violation in violations
    }

    result = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / SCRIPT.name),
            "--root",
            str(repository),
            "--base-ref",
            base_ref,
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "TB005" in result.stderr


def test_repository_uses_separate_baseline_and_head_reexport_maps(
    tmp_path: Path,
) -> None:
    """façade と consumer の複合変更を HEAD 写像だけで相殺させない。"""
    facade = "pitchlog/services/context_facade.py"
    consumer = "pitchlog/services/context_consumer.py"
    baseline_facade = "from external.facade import Context\n"
    head_facade = (
        "from pitchlog.repositories.context import "
        "TenantContext as Context\n"
    )
    baseline_consumer = '''\
from pitchlog.services.context_facade import Context

marker = "before"


def build(tenant_id):
    return Context(tenant_id)
'''
    head_consumer = baseline_consumer.replace('marker = "before"', 'marker = "after"')
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {
            **REEXPORT_SUPPORT_SOURCES,
            facade: baseline_facade,
            consumer: baseline_consumer,
        },
    )

    _write_test_repository_sources(
        repository,
        {facade: head_facade, consumer: head_consumer},
    )
    _commit_test_repository(repository, "change facade and consumer marker")

    violations = checker.check_repository(repository, base_ref=base_ref)

    assert (consumer, "TB007") in {
        (violation.path, violation.code) for violation in violations
    }
    assert checker.main(
        ["--root", str(repository), "--base-ref", base_ref]
    ) == 1


def test_repository_always_supplies_reexport_maps_to_source_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本番経路が baseline/head の再輸出写像を必ず供給する。"""
    relative = "pitchlog/services/missing_context_consumer.py"
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: "pass\n"},
    )
    head = '''\
from pitchlog.missing.module import Context

context = Context("tenant")
'''
    _write_test_repository_sources(repository, {relative: head})
    _commit_test_repository(repository, "add missing internal reexport")
    observed_maps: list[tuple[object, object]] = []
    original_scan_source_change = checker.scan_source_change

    def record_reexport_maps(*args: Any, **kwargs: Any) -> list[Any]:
        observed_maps.append(
            (
                kwargs.get("baseline_reexport_map"),
                kwargs.get("head_reexport_map"),
            )
        )
        return original_scan_source_change(*args, **kwargs)

    monkeypatch.setattr(
        checker,
        "scan_source_change",
        record_reexport_maps,
    )

    violations = checker.check_repository(repository, base_ref=base_ref)

    assert observed_maps
    assert all(
        baseline_map is not None
        and head_map is not None
        and baseline_map is not head_map
        for baseline_map, head_map in observed_maps
    )
    assert (relative, "TB007") in {
        (violation.path, violation.code) for violation in violations
    }


def test_repository_does_not_expand_population_to_unchanged_consumer(
    tmp_path: Path,
) -> None:
    """façade だけの変更では保証外の無変更 consumer を走査しない。"""
    facade = "pitchlog/services/context_facade.py"
    consumer = "pitchlog/services/context_consumer.py"
    consumer_source = '''\
from pitchlog.services.context_facade import Context


def build(tenant_id):
    return Context(tenant_id)
'''
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {
            **REEXPORT_SUPPORT_SOURCES,
            facade: "from external.facade import Context\n",
            consumer: consumer_source,
        },
    )

    _write_test_repository_sources(
        repository,
        {
            facade: (
                "from pitchlog.repositories.context import "
                "TenantContext as Context\n"
            )
        },
    )
    _commit_test_repository(repository, "change only facade")

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(
        ["--root", str(repository), "--base-ref", base_ref]
    ) == 0


@pytest.mark.parametrize(
    ("declaration", "expected_error"),
    (
        ("base_ref", r"extra=\['base_ref'\]"),
        ("comparison_ref", r"extra=\['comparison_ref'\]"),
        ("concrete_command", "三点差分 template が必要"),
    ),
)
def test_asset_declared_base_ref_is_contract_error_through_real_commit_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    declaration: str,
    expected_error: str,
) -> None:
    """比較元の自己申告と直接 SQL を同じ commit に置いても no-op にさせない。"""
    relative = "pitchlog/services/impact_probe.py"
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: "pass\n"},
    )
    _point_default_base_ref_at(repository, base_ref)
    impact_probe = '''\
from sqlalchemy.orm import Session


def read_other_tenant(work: Session) -> object:
    return work.execute("SELECT * FROM games")
'''
    _write_test_repository_sources(repository, {relative: impact_probe})
    allowlist_path = repository / checker.DEFAULT_ALLOWLIST
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert isinstance(allowlist, dict)
    diff_contract = allowlist["diff"]
    assert isinstance(diff_contract, dict)
    if declaration == "concrete_command":
        command = diff_contract["command"]
        assert isinstance(command, list)
        command[3] = "HEAD...HEAD"
    else:
        diff_contract[declaration] = "HEAD"
    allowlist_path.write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _commit_test_repository(repository, "attempt self-declared base ref")

    with pytest.raises(checker.ContractError, match=expected_error):
        checker.load_contract(repository)
    assert checker.main(["--root", str(repository)]) == 2
    assert "tenant-boundary contract error" in capsys.readouterr().err


@pytest.mark.parametrize("provide_base_ref", (True, False))
def test_impact_probe_is_red_through_external_or_default_real_commit_cli(
    tmp_path: Path,
    provide_base_ref: bool,
) -> None:
    """外部指定と凍結既定値のどちらでも強制点迂回を拒否する。"""
    relative = "pitchlog/services/impact_probe.py"
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: "pass\n"},
    )
    _point_default_base_ref_at(repository, base_ref)
    impact_probe = '''\
from sqlalchemy.orm import Session


def read_other_tenant(work: Session) -> object:
    return work.execute("SELECT * FROM games")
'''
    _write_test_repository_sources(repository, {relative: impact_probe})
    _commit_test_repository(repository, "add tenant boundary bypass")
    selected_base_ref = base_ref if provide_base_ref else None
    violations = checker.check_repository(
        repository,
        base_ref=selected_base_ref,
    )
    arguments = ["--root", str(repository)]
    if selected_base_ref is not None:
        arguments.extend(("--base-ref", selected_base_ref))

    assert (relative, "TB005") in {
        (violation.path, violation.code) for violation in violations
    }
    assert checker.main(arguments) == 1


@pytest.mark.parametrize("provide_base_ref", (True, False))
def test_safe_change_passes_external_or_default_real_commit_cli(
    tmp_path: Path,
    provide_base_ref: bool,
) -> None:
    """比較元の供給経路にかかわらず正当な変更を過剰拒否しない。"""
    relative = "pitchlog/services/report.py"
    baseline = 'REPORT_LABEL = "before"\n'
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    _point_default_base_ref_at(repository, base_ref)
    _write_test_repository_sources(
        repository,
        {relative: baseline.replace("before", "after")},
    )
    _commit_test_repository(repository, "update non-database report")
    selected_base_ref = base_ref if provide_base_ref else None
    arguments = ["--root", str(repository)]
    if selected_base_ref is not None:
        arguments.extend(("--base-ref", selected_base_ref))

    assert checker.check_repository(
        repository,
        base_ref=selected_base_ref,
    ) == []
    assert checker.main(arguments) == 0


def test_reject_all_mutant_kills_positive_fixture() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_directory(
        POSITIVE_ROOT,
        contract=contract,
        reject_all_db_calls=True,
    )

    assert {violation.code for violation in violations} == {"TB900"}


def test_api_added_outside_sealed_inventory_is_red(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(
        REPOSITORY_ROOT / "contracts" / "tenant_boundary",
        repository / "contracts" / "tenant_boundary",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary",
        repository / "tests" / "fixtures" / "tenant_boundary",
    )
    inventory_path = repository / checker.DEFAULT_INVENTORY
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert isinstance(inventory, dict)
    apis = inventory["apis"]
    assert isinstance(apis, list)
    apis.append(
        {
            "id": "OUTSIDE_INVENTORY_API",
            "symbol": "outside.database.execute",
            "kind": "function",
            "receivers": [],
        }
    )
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(checker.ContractError, match="inventory の集合が封印値と不一致"):
        checker.load_contract(repository)


def test_low_level_execution_surface_and_receiver_origins_are_sealed() -> None:
    """PGconn 実行面・re-export・factory 戻り型を閉集合に固定する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    pgconn_execution_symbols = {
        api.symbol
        for api in contract.apis
        if api.symbol.startswith("psycopg.pq.PGconn.")
    }
    assert pgconn_execution_symbols == {
        "psycopg.pq.PGconn.connect",
        "psycopg.pq.PGconn.connect_start",
        "psycopg.pq.PGconn.exec_",
        "psycopg.pq.PGconn.exec_params",
        "psycopg.pq.PGconn.exec_prepared",
        "psycopg.pq.PGconn.send_prepare",
        "psycopg.pq.PGconn.send_query",
        "psycopg.pq.PGconn.send_query_params",
        "psycopg.pq.PGconn.send_query_prepared",
    }
    assert contract.symbol_aliases["sqlalchemy.Engine"] == (
        "sqlalchemy.engine.Engine"
    )
    factory_returns = {
        item.symbol: item.returns for item in contract.receiver_factories
    }
    assert factory_returns["pitchlog.db.engine.create_database_engine"] == (
        "sqlalchemy.engine.Engine"
    )
    assert factory_returns["sqlalchemy.engine.Engine.connect"] == (
        "sqlalchemy.engine.Connection"
    )


@pytest.mark.parametrize(
    ("source", "expected_error"),
    (
        ('run = getattr(session, "exe" + "cute")\nrun(statement)\n', "TB005"),
        ('eval("session.execute")(statement)\n', "TB005"),
        (
            'driver = __import__("psyco" + "pg")\n'
            'getattr(driver, "connect")(url)\n',
            "TB005",
        ),
        (
            "from pitchlog.db.engine import create_database_engine\n"
            "database = create_database_engine()\n"
            "handle = database.connect()\n"
            'handle.exec_driver_sql("SELECT 1")\n',
            "TB005",
        ),
        (
            "from psycopg.pq import PGconn\n"
            "connection: PGconn\n"
            'connection.exec_(b"SELECT 1")\n',
            "TB005",
        ),
        (
            "from pitchlog.repositories.context import TenantContext\n"
            "object.__new__(TenantContext)\n",
            "TB007",
        ),
    ),
)
def test_reported_dynamic_bypass_examples_are_red(
    source: str,
    expected_error: str,
) -> None:
    """敵対レビューで再現された 6 経路をそのまま拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    violations = checker.scan_source(
        source,
        path="pitchlog/services/adversarial.py",
        contract=contract,
    )

    assert expected_error in {violation.code for violation in violations}


def test_session_factory_return_and_dynamic_object_new_are_red() -> None:
    """Session factory 別名と動的 object.__new__ も閉世界検査で拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    session_source = """\
from sqlalchemy.orm import Session

session_factory = Session
handle = session_factory()
handle.execute(statement)
"""
    context_source = """\
from pitchlog.repositories.context import TenantContext

getattr(object, "__new__")(TenantContext)
"""

    session_violations = checker.scan_source(
        session_source,
        path="pitchlog/services/session_factory_bypass.py",
        contract=contract,
    )
    context_violations = checker.scan_source(
        context_source,
        path="pitchlog/services/context_factory_bypass.py",
        contract=contract,
    )

    assert "TB005" in {item.code for item in session_violations}
    assert "TB007" in {item.code for item in context_violations}


def test_empty_baseline_and_empty_head_pass() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.continuity_violations({}, {}, contract=contract)
    population = checker._inspection_population({}, {}, contract=contract)
    application_violations = checker._application_population_violations(
        {},
        {},
        {},
        contract=contract,
    )

    assert violations == []
    assert population == {}
    assert application_violations == []


def test_removing_symbol_that_existed_in_baseline_is_red() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    baseline = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    violations = checker.continuity_violations(baseline, {}, contract=contract)

    assert {violation.code for violation in violations} == {"TB006"}
    assert {
        violation.symbol for violation in violations
    } == {
        "pitchlog.repositories.base.TenantRepositoryBase._execute_operation"
    }


def test_first_introduction_of_contract_symbol_is_not_a_rollback() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    head = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    violations = checker.continuity_violations({}, head, contract=contract)

    assert violations == []


def test_diff_parser_selects_only_new_side_backend_lines() -> None:
    diff = """\
diff --git a/backend/src/pitchlog/example.py b/backend/src/pitchlog/example.py
--- a/backend/src/pitchlog/example.py
+++ b/backend/src/pitchlog/example.py
@@ -2,0 +3,2 @@
+first = 1
+second = 2
@@ -8 +9 @@
-old = 1
+new = 2
diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -0,0 +1 @@
+ignored
"""

    changed = checker.changed_lines_from_diff(diff)
    changed_files = checker.changed_files_from_diff(diff)

    assert changed == {"pitchlog/example.py": frozenset({3, 4, 9})}
    assert changed_files == {"pitchlog/example.py"}


def test_pure_line_deletion_is_red_through_real_commit_diff(tmp_path: Path) -> None:
    """新側追加行 0 の純粋削除でも ``--base-ref`` 経路で再検査する。"""
    relative = "pitchlog/services/deletion.py"
    baseline = '''\
from sqlalchemy.orm import Session


class Report:
    pass


def handler(work: Session, safe: Report) -> object:
    work = safe
    return work.execute()
'''
    head = baseline.replace("    work = safe\n", "")
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    source_path = repository / "backend" / "src" / relative
    source_path.write_text(head, encoding="utf-8")
    _commit_test_repository(repository, "remove safe rebinding")
    diff = checker._run_git(
        repository,
        ["diff", "-U0", f"{base_ref}...HEAD", "--", "backend/src"],
    )

    assert checker.changed_lines_from_diff(diff) == {relative: frozenset()}
    assert checker.changed_files_from_diff(diff) == {relative}
    violations = checker.check_repository(repository, base_ref=base_ref)

    assert "TB005" in {violation.code for violation in violations}
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_pure_rename_is_conservatively_red_through_real_commit_diff(
    tmp_path: Path,
) -> None:
    """純粋改名は rename 先を新規ファイルとして ``--base-ref`` 検査する。"""
    old_relative = "pitchlog/services/old_handler.py"
    new_relative = "pitchlog/services/new_handler.py"
    source = '''\
from sqlalchemy.orm import Session


def handler(work: Session) -> object:
    return work.execute()
'''
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {old_relative: source},
    )
    checker._run_git(
        repository,
        [
            "mv",
            f"backend/src/{old_relative}",
            f"backend/src/{new_relative}",
        ],
    )
    _commit_test_repository(repository, "rename handler")
    diff = checker._run_git(
        repository,
        ["diff", "-U0", f"{base_ref}...HEAD", "--", "backend/src"],
    )

    assert checker.changed_lines_from_diff(diff) == {}
    assert checker.changed_files_from_diff(diff) == {new_relative}
    violations = checker.check_repository(repository, base_ref=base_ref)

    assert "TB005" in {violation.code for violation in violations}
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_pure_rename_of_non_database_code_passes_real_commit_diff(
    tmp_path: Path,
) -> None:
    """非 DB コードの純粋改名は実コミット列と CLI の経路で通す。"""
    old_relative = "pitchlog/services/old_report.py"
    new_relative = "pitchlog/services/new_report.py"
    source = '''\
class Report:
    def execute(self) -> str:
        return "ready"


def render(report: Report) -> str:
    return report.execute()
'''
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {old_relative: source},
    )

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0

    checker._run_git(
        repository,
        [
            "mv",
            f"backend/src/{old_relative}",
            f"backend/src/{new_relative}",
        ],
    )
    _commit_test_repository(repository, "rename non-database report")

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0


def test_same_violation_moved_between_functions_is_red_through_real_commit_diff(
    tmp_path: Path,
) -> None:
    """同種違反を別関数へ移しても基準版の件数で相殺させない。"""
    relative = "pitchlog/services/moved_violation.py"
    baseline = '''\
from sqlalchemy.orm import Session


def alpha(work: Session) -> object:
    return work.execute()


def beta(work: Session) -> object:
    return None
'''
    head = baseline.replace(
        "def alpha(work: Session) -> object:\n    return work.execute()",
        "def alpha(work: Session) -> object:\n    return None",
    ).replace(
        "def beta(work: Session) -> object:\n    return None",
        "def beta(work: Session) -> object:\n    return work.execute()",
    )
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    source_path = repository / "backend" / "src" / relative
    source_path.write_text(head, encoding="utf-8")
    _commit_test_repository(repository, "move violation")

    violations = checker.check_repository(repository, base_ref=base_ref)

    assert {
        (violation.code, violation.scope)
        for violation in violations
        if violation.code == "TB005"
    } == {("TB005", "pitchlog.services.moved_violation.beta")}
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_terminal_database_rebinding_stays_green_through_real_commit_diff(
    tmp_path: Path,
) -> None:
    """終端分岐だけの DB 再束縛を後続の非 DB receiver へ混入させない。"""
    relative = "pitchlog/services/terminal_rebinding.py"
    baseline = '''\
from sqlalchemy.orm import Session


class Report:
    pass


def handler(work: Report, database: Session, flag: bool) -> object:
    if flag:
        return None
    return work.execute()
'''
    head = baseline.replace(
        "    if flag:\n        return None",
        "    if flag:\n        work = database\n        return None",
    )
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    source_path = repository / "backend" / "src" / relative
    source_path.write_text(head, encoding="utf-8")
    _commit_test_repository(repository, "add terminal rebinding")

    violations = checker.check_repository(repository, base_ref=base_ref)

    assert violations == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0


def test_unchanged_preexisting_violation_is_not_reintroduced() -> None:
    """変更ファイル全体を再走査しても基準版と同じ違反は新規扱いしない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    baseline = """\
def can_cross_tenant() -> bool:
    return True


def ordinary_change() -> bool:
    return False
"""
    head = """\
def can_cross_tenant() -> bool:
    return True


def ordinary_change() -> bool:
    return True
"""

    violations = checker.scan_source_change(
        baseline,
        head,
        path="pitchlog/services/example.py",
        changed_lines=frozenset({6}),
        contract=contract,
    )

    assert violations == []


def test_imported_session_annotation_resolves_arbitrary_receiver_alias() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from sqlalchemy.orm import Session


def load(short_name: Session) -> object:
    return short_name.execute("SELECT 1")
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/typed_alias.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_tenant_context_construction_from_allowlisted_module_passes() -> None:
    """allowlist 内のテストモジュールからの構築が通ることを確認する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from pitchlog.repositories.context import TenantContext


def make_tenant_context(tenant_id):
    return TenantContext(tenant_id)
"""

    violations = checker.scan_source(
        source,
        path="test_authz_tenant_context.py",
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize(
    "source",
    (
        """\
from pitchlog.repositories.context import TenantContext

context = TenantContext(tenant_id)
""",
        """\
import pitchlog.repositories.context as repository_context

context = repository_context.TenantContext(tenant_id)
""",
        """\
from pitchlog.repositories.context import TenantContext as Context

context = Context(tenant_id)
""",
        """\
from pitchlog.repositories.context import TenantContext


class DerivedContext(TenantContext):
    pass


context = DerivedContext(tenant_id)
""",
    ),
)
def test_tenant_context_construction_outside_allowlist_is_red(source: str) -> None:
    """import 形を変えても allowlist 外からの構築を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/api/routers/example.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB007"}


def test_tenant_context_integrity_secret_reference_outside_allowlist_is_red() -> None:
    """発行証跡のプロセス秘密を許可シンボル外から参照できない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from pitchlog.repositories.context import _TENANT_CONTEXT_SECRET

leaked = _TENANT_CONTEXT_SECRET
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/leak_context_secret.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB007"}


def test_tenant_context_integrity_secret_dynamic_reference_is_red() -> None:
    """getattr を使っても発行証跡の秘密へ到達できない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
import pitchlog.repositories.context as context_module

leaked = getattr(context_module, "_TENANT_CONTEXT_SECRET")
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/dynamic_context_secret.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB007"}


def test_known_non_database_receivers_and_unrelated_replace_pass() -> None:
    """由来が既知の非 DB 型にある同名メソッドと DTO 複製は拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
import dataclasses
from pitchlog.clients import ImportedClient


class NonDatabaseClient:
    def execute(self):
        return None

    def connect(self):
        return None

    def delete(self):
        return None

    def copy(self):
        return None

    def merge(self):
        return None


@dataclasses.dataclass(frozen=True)
class FrozenDto:
    value: int


def use_client(client: NonDatabaseClient, dto: FrozenDto):
    client.execute()
    client.connect()
    client.delete()
    client.copy()
    client.merge()
    return dataclasses.replace(dto, value=2)


def use_imported_client(client: ImportedClient):
    client.execute()
    client.connect()


def make_client() -> NonDatabaseClient:
    return NonDatabaseClient()


client = NonDatabaseClient()
factory_client = make_client()
dto = FrozenDto(value=1)
use_client(client, dto)
factory_client.execute()
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/non_database_client.py",
        contract=contract,
    )

    assert violations == []


def test_unresolved_non_constructor_attribute_call_passes() -> None:
    """構築名でない未解決属性 callable は保証外として拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
def build(registry, key, tenant_id):
    return registry[key].make_context(tenant_id)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/context_registry.py",
        contract=contract,
    )

    assert violations == []


def test_known_builtin_bare_calls_pass_when_flow_cannot_resolve_them() -> None:
    """別名表で既知の組み込み裸呼び出しは (iii) の対象外とする。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
def normalize(value):
    return value
    str(value)
    enumerate(value)
    dict(value)
"""
    path = "pitchlog/services/builtin_calls.py"
    tree = ast.parse(source, filename=path)
    scanner = checker._SourceScanner(
        path=path,
        module=checker._module_name(path),
        tree=tree,
        changed_lines=None,
        contract=contract,
        reject_all_db_calls=False,
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    assert {
        node.func.id: scanner.aliases.known_symbols.get(node.func.id)
        for node in calls
        if isinstance(node.func, ast.Name)
    } == {
        "str": "builtins.str",
        "enumerate": "builtins.enumerate",
        "dict": "builtins.dict",
    }
    assert all(scanner.flow.callable_symbol(node) is None for node in calls)

    scanner.visit(tree)
    scanner._validate_call_coverage(tree)

    assert scanner.violations == []


def test_imported_non_constructor_bare_call_without_shadow_is_green() -> None:
    """使用位置が import binding に結び付く対照Bを green に保つ。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from external.helpers import safe


def build(tenant_id):
    return safe(tenant_id)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/imported_safe_factory.py",
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize(
    "source",
    (
        """\
def build(tenant_id):
    from pitchlog.repositories.context import TenantContext
    return TenantContext(tenant_id)
""",
        """\
from pitchlog.repositories.context import TenantContext


def build(tenant_id):
    constructor = TenantContext
    derived_constructor = constructor
    return derived_constructor(tenant_id)
""",
        """\
from external.first import safe


def replace():
    global safe
    from external.second import safe


def build(tenant_id):
    return safe(tenant_id)
""",
        """\
from external.first import safe


def replace(factory):
    global safe
    safe = factory


def build(tenant_id):
    return safe(tenant_id)
""",
    ),
    ids=(
        "function-import",
        "local-static-alias",
        "global-import-writer",
        "global-assignment-writer",
    ),
)
def test_static_constructor_and_global_callable_rebinding_are_red(
    source: str,
) -> None:
    """静的 constructor と module writer は字句 callable の免除へ入れない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/rebound_constructor.py",
        contract=contract,
    )

    assert "TB007" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    "source",
    (
        """\
from pitchlog.domaingen.core import GenerationError
GenerationError = object()
""",
        """\
from pitchlog.domaingen.core import GenerationError


class Shadow:
    GenerationError = object()
""",
        """\
from external.overrides import *
from pitchlog.domaingen.core import GenerationError
observed = GenerationError
""",
        """\
from pitchlog.domaingen.core import GenerationError


def use():
    try:
        raise RuntimeError
    except RuntimeError as GenerationError:
        return GenerationError
""",
        """\
from pitchlog.domaingen.core import GenerationError


def use(value):
    match value:
        case GenerationError:
            return GenerationError
""",
    ),
    ids=(
        "module-assignment",
        "class-assignment",
        "star-import",
        "except-as",
        "match-capture",
    ),
)
def test_condition_2_syntactic_binding_routes_are_red(source: str) -> None:
    """条件 2 は Store / Load の構文名を常に候補にして裁定迂回を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/shadowed_generation_error.py",
        contract=contract,
    )

    assert "TB002" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    "source",
    (
        """\
from external.helpers import safe


def build(safe, tenant_id):
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(safe, /, tenant_id):
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(tenant_id, *, safe):
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(tenant_id, *safe):
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(tenant_id, **safe):
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


build = lambda safe, tenant_id: safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(factory, tenant_id):
    safe = factory
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(other, tenant_id):
    safe += other
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(factory, tenant_id):
    (safe := factory)
    return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(factories, tenant_id):
    for safe in factories:
        return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(manager, tenant_id):
    with manager as safe:
        return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(tenant_id):
    try:
        raise RuntimeError
    except RuntimeError as safe:
        return safe(tenant_id)
""",
        """\
from external.helpers import safe


def build(factories, tenant_id):
    return [safe(tenant_id) for safe in factories]
""",
    ),
    ids=(
        "argument",
        "positional-only-argument",
        "keyword-only-argument",
        "variadic-argument",
        "variadic-keyword-argument",
        "lambda-argument",
        "assignment",
        "augmented-assignment",
        "walrus",
        "for-target",
        "with-as",
        "except-as",
        "comprehension-target",
    ),
)
def test_lexically_bound_bare_callable_is_green(source: str) -> None:
    """関数内の字句束縛 callable は条件 5 の保証範囲外として許可する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/shadowed_safe_factory.py",
        contract=contract,
    )

    assert violations == []


def test_local_reimport_is_a_lexically_bound_callable() -> None:
    """関数内 re-import の裸名呼び出しも保証範囲外として許可する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from external.first import safe


def build(tenant_id):
    from external.second import safe
    return safe(tenant_id)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/reimported_safe_factory.py",
        contract=contract,
    )

    assert violations == []


def test_nonlocal_callable_is_a_lexical_closure_binding() -> None:
    """nonlocal の裸名呼び出しもクロージャ変数として許可する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from external.helpers import safe


def outer(factory, tenant_id):
    safe = factory

    def build():
        nonlocal safe
        return safe(tenant_id)

    return build()
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/nonlocal_safe_factory.py",
        contract=contract,
    )

    assert violations == []


def test_global_keeps_module_import_exemption() -> None:
    """writer の無い global 宣言は再束縛ではないため green にする。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from external.helpers import safe


def build(tenant_id):
    global safe
    return safe(tenant_id)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/global_safe_factory.py",
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize(
    ("source", "expected_code"),
    (
        (
            """\
from external.helpers import safe


def build(safe: safe, tenant_id):
    return safe(tenant_id)
""",
            None,
        ),
        (
            """\
from external.helpers import safe as imported_safe


def outer(factory, tenant_id):
    safe = imported_safe

    def build():
        return safe(tenant_id)

    safe = factory
    return build
""",
            None,
        ),
        (
            """\
from external.helpers import safe


def replace(factory):
    global safe
    safe = factory


def build(tenant_id):
    global safe
    return safe(tenant_id)
""",
            "TB007",
        ),
        (
            """\
from pitchlog.domaingen.core import GenerationError


def use(other):
    GenerationError = other
    return GenerationError
""",
            "TB002",
        ),
        (
            """\
from pitchlog.domaingen.core import GenerationError


def use(other):
    GenerationError: object = other
    return GenerationError
""",
            "TB002",
        ),
        (
            """\
from pitchlog.domaingen.core import GenerationError


def use(other):
    return (GenerationError := other)
""",
            "TB002",
        ),
    ),
    ids=(
        "annotated-parameter",
        "late-binding-closure",
        "global-writer",
        "condition2-assignment",
        "condition2-walrus",
        "condition2-annotated-assignment",
    ),
)
def test_scope_boundary_for_callable_and_condition2_rebinding(
    source: str,
    expected_code: str | None,
) -> None:
    """字句 callable は許可し、global と条件 2 の再束縛は拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/rebound_name.py",
        contract=contract,
    )

    if expected_code is None:
        assert violations == []
    else:
        assert expected_code in {violation.code for violation in violations}


def test_class_attribute_is_not_a_method_closure_binding() -> None:
    """メソッド本体の裸名は同名クラス属性でなく module import を参照する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from external.helpers import safe


class C:
    safe = lambda value: value

    def build(self, tenant_id):
        return safe(tenant_id)
"""
    path = "pitchlog/services/class_attribute_control.py"
    tree = ast.parse(source, filename=path)
    scanner = checker._SourceScanner(
        path=path,
        module=checker._module_name(path),
        tree=tree,
        source=source,
        changed_lines=None,
        contract=contract,
        reject_all_db_calls=False,
    )
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))

    assert scanner.flow.callable_symbol(call) == "external.helpers.safe"
    assert checker.scan_source(source, path=path, contract=contract) == []


def test_subscript_assignment_target_uses_current_flow_environment() -> None:
    """添字代入先の builtin 呼び出しを空環境由来の未知に落とさない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
def update(values, index, value):
    values[str(index)] = value
"""
    path = "pitchlog/services/subscript_assignment.py"
    tree = ast.parse(source, filename=path)
    scanner = checker._SourceScanner(
        path=path,
        module=checker._module_name(path),
        tree=tree,
        source=source,
        changed_lines=None,
        contract=contract,
        reject_all_db_calls=False,
    )
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))

    assert scanner.flow.callable_symbol(call) == "builtins.str"
    assert checker.scan_source(source, path=path, contract=contract) == []


def test_parameter_bare_call_is_outside_condition_5_scope() -> None:
    """known_symbols に無い callable 引数も保証範囲外として許可する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
def forge_context(factory, tenant_id):
    return factory(tenant_id)
"""
    path = "pitchlog/services/parameter_factory.py"
    tree = ast.parse(source, filename=path)
    scanner = checker._SourceScanner(
        path=path,
        module=checker._module_name(path),
        tree=tree,
        changed_lines=None,
        contract=contract,
        reject_all_db_calls=False,
    )

    assert "factory" not in scanner.aliases.known_symbols

    violations = checker.scan_source(
        source,
        path=path,
        contract=contract,
    )

    assert violations == []


def test_unregistered_bare_text_call_remains_red() -> None:
    """別名表へ登録されていない裸名は生テキストだけで解決済みにしない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = "context = missing_factory(tenant_id)\n"
    path = "pitchlog/services/unregistered_factory.py"
    tree = ast.parse(source, filename=path)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))
    scanner = checker._SourceScanner(
        path=path,
        module=checker._module_name(path),
        tree=tree,
        changed_lines=None,
        contract=contract,
        reject_all_db_calls=False,
    )

    assert scanner.aliases.resolve(call.func) == "missing_factory"
    assert "missing_factory" not in scanner.aliases.known_symbols

    violations = checker.scan_source(
        source,
        path=path,
        contract=contract,
    )

    assert [
        (violation.code, violation.symbol)
        for violation in violations
    ] == [("TB007", "missing_factory")]


@pytest.mark.parametrize(
    "target",
    (
        "value",
        "value: TenantContext",
    ),
)
def test_dataclasses_replace_with_unknown_or_context_target_is_red(
    target: str,
) -> None:
    """dataclasses.replace は第1引数が未注釈でも文脈型注釈でも拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f"""\
import dataclasses
from pitchlog.repositories.context import TenantContext


def clone({target}):
    return dataclasses.replace(value, enabled=True)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/dto_clone.py",
        contract=contract,
    )

    assert [
        (violation.code, violation.symbol)
        for violation in violations
    ] == [("TB007", "dataclasses.replace")]


def test_local_database_type_name_shadow_mutation_is_red() -> None:
    """安全なローカル型が DB 型名を shadow する変異だけを拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
class Report:
    pass


def render(work: Report):
    return work.execute("render")
"""
    mutated = source.replace("Report", "Session")
    changed_lines = _changed_lines_containing(
        mutated,
        "class Session",
        "work: Session",
    )
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )
    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/report_renderer.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    "insertion",
    (
        "    work = other\n",
        "    if flag:\n        work = other\n",
    ),
)
def test_non_database_receiver_rebinding_mutation_is_red(insertion: str) -> None:
    """非 DB 注釈を未解決値で上書きする直線・分岐変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
class Report:
    pass


def render(work: Report, other, flag):
    return work.execute("render")
"""
    mutated = source.replace(
        '    return work.execute("render")\n',
        f'{insertion}    return work.execute("render")\n',
    )
    changed_lines = _changed_lines_containing(mutated, "work = other")
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )
    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/report_rebinding.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


def test_attribute_constructor_name_is_red_with_or_without_annotation() -> None:
    """TenantContext 末尾名を receiver provenance に関係なく拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from application.factories import ContextFactory


def make(mod: ContextFactory, tenant_id):
    return mod.TenantContext(tenant_id)
"""
    mutated = source.replace("mod: ContextFactory", "mod")
    changed_lines = _changed_lines_containing(mutated, "def make(mod,")
    assert _changed_lines_containing(mutated, "mod.TenantContext").isdisjoint(
        changed_lines
    )
    baseline_violations = checker.scan_source(
        source,
        path="pitchlog/services/context_factory.py",
        contract=contract,
    )
    head_violations = checker.scan_source(
        mutated,
        path="pitchlog/services/context_factory.py",
        contract=contract,
    )
    change_violations = checker.scan_source_change(
        source,
        mutated,
        path="pitchlog/services/context_factory.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB007" in {violation.code for violation in baseline_violations}
    assert "TB007" in {violation.code for violation in head_violations}
    assert change_violations == []


@pytest.mark.parametrize(
    ("typing_import", "safe_annotation", "database_annotation"),
    (
        ("Optional", "Optional[Report]", "Optional[Session]"),
        (
            "Annotated",
            'Annotated[Report, "dep"]',
            'Annotated[Session, "dep"]',
        ),
        ("Union", "Union[Report, None]", "Union[Session, None]"),
    ),
)
def test_database_type_inside_annotation_wrapper_mutation_is_red(
    typing_import: str,
    safe_annotation: str,
    database_annotation: str,
) -> None:
    """標準ラッパー内の注釈だけを DB 型へ変える変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
from typing import {typing_import}
from sqlalchemy.orm import Session


class Report:
    pass


def render(work: {safe_annotation}):
    return work.execute("render")
'''
    mutated = source.replace(safe_annotation, database_annotation)
    changed_lines = _changed_lines_containing(mutated, database_annotation)
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/wrapped_database_type.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    ("typing_import", "annotation"),
    (
        ("Optional", "Optional[Report]"),
        ("Annotated", 'Annotated[Report, "dep"]'),
        ("Union", "Union[Report, None]"),
    ),
)
def test_non_database_type_inside_annotation_wrapper_passes(
    typing_import: str,
    annotation: str,
) -> None:
    """全構成型が既知の非 DB 型ならラッパー注釈を許可する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
from typing import {typing_import}


class Report:
    pass


def render(work: {annotation}):
    return work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/wrapped_report.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


def test_unknown_union_member_mutation_is_red() -> None:
    """Union に未解決型が混ざる変異は非 DB 証明を失う。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = '''\
from typing import Union


class Report:
    pass


def render(work: Union[Report, None]):
    return work.execute("render")
'''
    mutated = source.replace(
        "Union[Report, None]",
        "Union[Report, UnknownDependency]",
    )
    changed_lines = _changed_lines_containing(
        mutated,
        "Union[Report, UnknownDependency]",
    )
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/unknown_union_member.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


def test_database_typed_class_attribute_mutation_is_red() -> None:
    """非 DB container の属性注釈だけを DB 型へ変える変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = '''\
from sqlalchemy.orm import Session


class Report:
    pass


class Dependencies:
    database: Report


def load(dependencies: Dependencies):
    return dependencies.database.execute(statement)
'''
    mutated = source.replace("database: Report", "database: Session")
    changed_lines = _changed_lines_containing(mutated, "database: Session")
    assert _changed_lines_containing(
        mutated,
        "dependencies.database.execute",
    ).isdisjoint(changed_lines)

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/dependencies.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    "use_expression",
    (
        "    handle = dependencies.make()\n    return handle.execute(statement)\n",
        "    return dependencies.make().execute(statement)\n",
    ),
)
def test_unresolved_method_result_mutation_is_red(use_expression: str) -> None:
    """未解決メソッド結果は代入有無にかかわらず DB 候補として拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


class Dependencies:
    def make(self) -> Report:
        return Report()


def load(dependencies: Dependencies):
{use_expression}'''
    mutated = source.replace(" -> Report", "")
    changed_lines = _changed_lines_containing(mutated, "def make(self):")
    assert _changed_lines_containing(mutated, ".execute(statement)").isdisjoint(
        changed_lines
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/dependency_factory.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    ("receiver_name", "receiver_type", "method"),
    (
        ("session", "Report", "execute"),
        ("connection", "Report", "execute"),
        ("engine", "Pool", "connect"),
        ("db_engine", "Pool", "connect"),
    ),
)
def test_database_receiver_name_on_known_non_database_type_passes(
    receiver_name: str,
    receiver_type: str,
    method: str,
) -> None:
    """inventory の receiver 名だけでは既知の非 DB 型を拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


class Pool:
    pass


def use({receiver_name}: {receiver_type}):
    return {receiver_name}.{method}()
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/named_non_database_receiver.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize(
    "terminal_branch",
    (
        "        return None",
        "        raise ValueError",
    ),
)
def test_terminal_if_branch_does_not_pollute_following_flow(
    terminal_branch: str,
) -> None:
    """return・raise で終端した分岐を後続の由来へ合流しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


def render(work: Report, other, flag):
    if flag:
        work = other
{terminal_branch}
    return work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/terminal_branch.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize("loop_control", ("break", "continue"))
def test_terminal_loop_branch_does_not_pollute_remaining_body(
    loop_control: str,
) -> None:
    """break・continue で終端した分岐を同一 loop body の後続へ合流しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


def render(work: Report, other, items):
    for item in items:
        if item:
            work = other
            {loop_control}
        work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/terminal_loop_branch.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


def test_terminal_try_branches_do_not_pollute_following_flow() -> None:
    """try の return・raise 経路を後続へ合流しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = '''\
class Report:
    pass


def render(work: Report, other, flag):
    try:
        if flag:
            work = other
            return None
    except ValueError:
        work = other
        raise
    return work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/terminal_try_branch.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


def test_database_receiver_from_local_factory_return_is_red() -> None:
    """ローカル factory の戻り型が DB receiver なら迂回を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from sqlalchemy.orm import Session


def make_session() -> Session:
    return Session()


handle = make_session()
handle.execute(statement)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/local_session_factory.py",
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


def test_imported_object_without_non_database_type_proof_is_red() -> None:
    """import だけでは非 DB receiver と証明せず、危険メソッド名を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from application.dependencies import client

client.execute(statement)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/imported_unknown_client.py",
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    ("source", "expected_tb007"),
    (
        ("""\
from pitchlog.repositories.context import _tenant_context_proof as derive

proof_factory = derive
proof_factory(tenant_id)
""", True),
        ("""\
import pitchlog.repositories.context as context_module

module_alias = context_module
derive = module_alias._tenant_context_proof
proof_factory = derive
proof_factory(tenant_id)
""", True),
        ("""\
def forge(factory, tenant_id):
    return factory(tenant_id)
""", False),
    ),
)
def test_proof_factory_aliases_and_lexical_callable_scope(
    source: str,
    expected_tb007: bool,
) -> None:
    """証跡導出の別名は拒否し、字句 callable は保証範囲外とする。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/context_proof_bypass.py",
        contract=contract,
    )

    assert ("TB007" in {violation.code for violation in violations}) is expected_tb007


def test_product_module_cannot_be_added_before_authenticated_entry_exists() -> None:
    """認証入口の導入前に製品モジュールを許可する変異を拒否する。"""
    asset = json.loads(
        (
            REPOSITORY_ROOT / checker.DEFAULT_TENANT_CONTEXT_ALLOWLIST
        ).read_text(encoding="utf-8")
    )
    assert isinstance(asset, dict)
    asset["allowed_product_modules"] = ["pitchlog.api.routers.example"]
    asset["source_digest"] = _contract_digest(asset)

    with pytest.raises(checker.ContractError, match="製品モジュールの生成経路は 0 件"):
        checker._load_tenant_context_allowlist(asset)


@pytest.mark.parametrize("relative_path", PRODUCT_APPLICATION_PATHS)
def test_tenant_repository_product_definition_passes_bypass_scan(
    relative_path: str,
) -> None:
    """現行の製品コードそのものが全行検査を通ることを確認する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source_path = REPOSITORY_ROOT / "backend/src" / relative_path

    violations = checker.scan_source(
        _fixture_source(source_path),
        path=relative_path,
        contract=contract,
    )

    assert violations == []


def test_tenant_binding_symbol_has_only_required_database_apis() -> None:
    """束縛シンボルのDB到達許可を必要な4 APIだけに固定する。"""
    allowlist = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )
    assert isinstance(allowlist, dict)
    allowed_symbols = allowlist["allowed_symbols"]
    assert isinstance(allowed_symbols, list)
    matching_rows = [
        row
        for row in allowed_symbols
        if isinstance(row, dict)
        and row.get("symbol")
        == "pitchlog.repositories.binding._tenant_transaction"
    ]

    assert len(matching_rows) == 1
    assert set(matching_rows[0]["allowed_api_ids"]) == {
        "SQLA_SESSION_BEGIN",
        "SQLA_SESSION_CONNECTION",
        "SQLA_SESSION_EXECUTE",
        "SQLA_TEXT",
    }


def test_repository_base_symbol_has_only_execute_database_api() -> None:
    """基底の非公開実行器に Session.execute だけを許可する。"""
    allowlist = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )
    assert isinstance(allowlist, dict)
    allowed_symbols = allowlist["allowed_symbols"]
    assert isinstance(allowed_symbols, list)
    matching_rows = [
        row
        for row in allowed_symbols
        if isinstance(row, dict)
        and row.get("symbol")
        == "pitchlog.repositories.base.TenantRepositoryBase._execute_operation"
    ]

    assert len(matching_rows) == 1
    assert matching_rows[0]["signature"] == (
        "_execute_operation(self, context: TenantContext, "
        "operation: TenantOperationToken) -> TenantOperationResult"
    )
    assert matching_rows[0]["allowed_api_ids"] == ["SQLA_SESSION_EXECUTE"]


def test_condition4_allows_only_the_declared_request_api_call() -> None:
    """葉が provider の公開型と純粋要求生成器だけを利用できる。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from uuid import UUID

from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationRequest,
    CacheInvalidationTrigger,
    CachePeriod,
    SharedAggregateCacheKey,
    build_cache_invalidation_request,
)


def request_cache_refresh(
    group_id: UUID,
    requester_tenant_id: UUID,
    target_tenant_id: UUID,
) -> CacheInvalidationRequest:
    key = SharedAggregateCacheKey(
        group_id,
        requester_tenant_id,
        target_tenant_id,
        CachePeriod(None, None),
    )
    return build_cache_invalidation_request(
        CacheInvalidationTrigger.GRANT_FLAG_CHANGE,
        (key,),
    )
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/cache_request.py",
        contract=contract,
    )

    assert violations == []


def test_condition4_rejects_nonpublic_provider_import_and_call() -> None:
    """provider に置いただけの非公開実装を葉が迂回利用できない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from pitchlog.repositories.cache_invalidation import CacheInvalidationRequest


def request_cache_refresh() -> CacheInvalidationRequest:
    return CacheInvalidationRequest._create(
        trigger=None,
        keys=(),
        propagation_mode=None,
        affected_tenant_ids=None,
    )
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/cache_request.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB004"}


def test_condition4_allowed_call_symbols_are_an_exact_set() -> None:
    """条件 4 の許可呼び出しを物理キー構築と単一 factory に閉じる。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    assert contract.cache_invalidation.allowed_call_symbols == frozenset(
        {
            "pitchlog.repositories.cache_invalidation.AnalyticsChartCacheKey",
            "pitchlog.repositories.cache_invalidation.CachePeriod",
            "pitchlog.repositories.cache_invalidation.MatchCacheKey",
            "pitchlog.repositories.cache_invalidation.MatchChartSubject",
            "pitchlog.repositories.cache_invalidation.PlayerCareerCacheKey",
            "pitchlog.repositories.cache_invalidation.PlayerChartSubject",
            "pitchlog.repositories.cache_invalidation.SharedAggregateCacheKey",
            "pitchlog.repositories.cache_invalidation.TeamAggregateCacheKey",
            "pitchlog.repositories.cache_invalidation.build_cache_invalidation_request",
        }
    )


def test_repository_application_population_is_nonempty_and_green() -> None:
    """自 PR の実差分を非空母集団として適用し一致 0 を確認する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    diff = checker._run_git(
        REPOSITORY_ROOT,
        ["diff", "-U0", "origin/develop...HEAD", "--", "backend/src"],
    )
    changed_lines = checker.changed_lines_from_diff(diff)
    merge_base = checker._run_git(
        REPOSITORY_ROOT,
        ["merge-base", "origin/develop", "HEAD"],
    ).strip()
    baseline_sources = checker._git_snapshot(REPOSITORY_ROOT, merge_base)
    head_sources = checker._git_snapshot(REPOSITORY_ROOT, "HEAD")
    baseline_definitions, _ = checker._definitions(
        baseline_sources,
        contract,
    )
    head_definitions, _ = checker._definitions(head_sources, contract)
    introduced_symbols = set(head_definitions) - set(baseline_definitions)
    population = checker._inspection_population(
        changed_lines,
        head_sources,
        contract=contract,
    )

    assert population
    if introduced_symbols:
        assert checker._has_changed_lines(changed_lines)
        assert set(PRODUCT_APPLICATION_PATHS) <= {
            path for path, lines in changed_lines.items() if lines
        }
    else:
        assert set(PRODUCT_APPLICATION_PATHS) <= set(head_sources)
    violations = checker.check_repository(REPOSITORY_ROOT)

    assert violations == []


def test_first_product_introduction_with_empty_population_is_red() -> None:
    """製品シンボル導入時に三点差分が空洞化する変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    head = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    violations = checker._application_population_violations(
        {},
        {},
        head,
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB008"}


def test_merged_head_uses_real_contract_symbols_as_nonempty_population() -> None:
    """統合後に三点差分が空でも実製品の強制点を再検査する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    head = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    population = checker._inspection_population({}, head, contract=contract)
    violations = checker.scan_source(
        head[relative],
        path=relative,
        changed_lines=population[relative],
        contract=contract,
    )

    assert population[relative]
    assert violations == []


def test_current_product_contract_is_rechecked_after_merge() -> None:
    """空差分でも実製品の強制点を再検査して通す。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    head_sources = checker._git_snapshot(REPOSITORY_ROOT, "HEAD")
    population = checker._inspection_population(
        {},
        head_sources,
        contract=contract,
    )
    violations = checker._changed_source_violations(
        REPOSITORY_ROOT,
        population,
        contract,
    )

    assert population
    assert violations == []


def test_actual_base_direct_sql_mutation_is_red() -> None:
    """実際の基底の許可関数へ未許可の直接 SQL を足すと拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutated = source.replace(
        "from sqlalchemy.orm import Session",
        "from sqlalchemy import text\nfrom sqlalchemy.orm import Session",
        1,
    ).replace(
        "            execution_result = self._session.execute(\n",
        "            self._session.execute(text(\"SELECT 1\"))\n"
        "            execution_result = self._session.execute(\n",
        1,
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(
            mutated,
            "from sqlalchemy import text",
            'self._session.execute(text("SELECT 1"))',
        ),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_actual_binding_nonlocal_set_config_mutation_is_red() -> None:
    """実際の束縛文を transaction-local でなくす変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/binding.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutated = source.replace(
        "SELECT set_config('app.tenant_id', :tenant_id, true)",
        "SELECT set_config('app.tenant_id', :tenant_id, false)",
        1,
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(mutated, "set_config", "false"),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_actual_base_database_call_outside_allowed_symbol_is_red() -> None:
    """基底でも許可シンボルの外側から DB API を呼ぶ変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutated = source.replace(
        "        _operation_spec(operation)\n",
        "        self._session.execute(operation)\n"
        "        _operation_spec(operation)\n",
        1,
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(
            mutated,
            "self._session.execute(operation)",
        ),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_actual_binding_unlisted_symbol_database_call_is_red() -> None:
    """allowlist に無い新設シンボルからの DB API 呼び出しを拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/binding.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutation = """

def _unlisted_database_access(session: Session) -> None:
    session.execute(text("SELECT 1"))
"""
    mutated = f"{source.rstrip()}{mutation}\n"

    violations = _scan_diff_mutation(
        source,
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(
            mutated,
            "_unlisted_database_access",
            'session.execute(text("SELECT 1"))',
        ),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


@pytest.mark.parametrize(
    "case_id",
    (
        "base-direct-sql",
        "binding-nonlocal-set-config",
        "base-call-outside-allowed-symbol",
        "binding-unlisted-symbol",
    ),
)
def test_actual_implementation_mutation_is_red_through_real_commit_diff(
    tmp_path: Path,
    case_id: str,
) -> None:
    """実製品への 4 変異を実コミット列と CLI の経路で拒否する。"""
    relative, baseline, mutated = _actual_implementation_mutation(case_id)
    baseline_sources = checker._git_snapshot(REPOSITORY_ROOT, "HEAD")
    baseline_sources[relative] = baseline
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        baseline_sources,
    )

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0

    _write_test_repository_sources(repository, {relative: mutated})
    _commit_test_repository(repository, f"apply {case_id} mutation")
    violations = checker.check_repository(repository, base_ref=base_ref)

    assert (relative, "TB005") in {
        (violation.path, violation.code) for violation in violations
    }
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_manifest_rows_keep_the_required_exact_shape() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_NEGATIVE_FIXTURES).read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(manifest, dict)
    fixtures = manifest["fixtures"]
    assert isinstance(fixtures, list)
    for row in fixtures:
        assert isinstance(row, dict)
        assert set(row) == {
            "id",
            "path",
            "condition",
            "mutation",
            "expected_error",
        }


def test_contract_declares_ci_job_without_wiring_it() -> None:
    allowlist: dict[str, Any] = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )

    assert allowlist["ci"] == {
        "job": "tenant-boundary-bypass",
        "command": "uv run python scripts/check_tenant_boundary_bypass.py",
    }


def test_default_base_ref_belongs_only_to_frozen_checker_procedure() -> None:
    """比較元の実値を資産へ戻さず、検査器の変更履歴対象に固定する。"""
    allowlist: dict[str, Any] = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )

    assert allowlist["diff"] == {
        "command": [
            "git",
            "diff",
            "-U0",
            "{base_ref}...HEAD",
            "--",
            "backend/src",
        ]
    }
    assert checker.DEFAULT_BASE_REF == "origin/develop"
    assert allowlist["baseline_control"]["identity"]["frozen_projection"][
        "external_files"
    ] == ["scripts/check_tenant_boundary_bypass.py"]
