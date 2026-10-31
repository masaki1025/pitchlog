"""API 器が非コアの規約を守ることを検証する。"""

import ast
import base64
import hashlib
import io
import json
import re
import secrets
import subprocess
import sys
import token
import tokenize
from functools import cache
from pathlib import Path
from typing import Final

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from pitchlog.api.app import ROUTERS, create_app
from pitchlog.api.schemas.base import ErrorDetail, ErrorEnvelope, ErrorField

_REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_API_SOURCE_ROOT: Final[Path] = (
    _REPOSITORY_ROOT / "backend" / "src" / "pitchlog" / "api"
)
_ROUTE_REGISTRY_PATH: Final[Path] = (
    _REPOSITORY_ROOT / "contracts" / "authz" / "route-registry.json"
)
_DATABASE_TERMS: Final[tuple[str, ...]] = (
    "sqlalchemy",
    "Session",
    "engine",
    "session.execute",
    "select(",
    "text(",
    "raw_connection",
)
_SYNCHRONIZATION_TERMS: Final[tuple[str, ...]] = (
    "idempotenc",
    "seq_no",
    "tombstone",
    "revision_no",
    "generation",
)
_REQUEST_ACCESS_PATTERNS: Final[tuple[str, ...]] = (
    "request.headers",
    "request.body",
    "request.query_params",
    "cookies",
)
_ALLOWED_DATABASE_TERM_IDENTIFIERS: Final[tuple[str, ...]] = ("AuthSessionResponse",)


def _has_database_term(source_text: str) -> bool:
    """承認済みDTO名だけを除き、従来どおり部分一致でDB語彙を探す。"""
    inspected = source_text
    for identifier in _ALLOWED_DATABASE_TERM_IDENTIFIERS:
        inspected = re.sub(rf"\b{re.escape(identifier)}\b", "", inspected)
    return any(term in inspected for term in _DATABASE_TERMS)


_INITIAL_RESPONSE_PATH: Final[Path] = Path(
    "backend/src/pitchlog/api/schemas/game_start.py"
)
_INITIAL_RESPONSE_REVISION: Final[str] = json.loads(
    (_REPOSITORY_ROOT / "contracts/tenant_boundary/frozen-inputs.json").read_text(
        encoding="utf-8"
    )
)["frozen_inputs"]["initial_response_revision"]["value"]


def _transport_nodes(
    source: str,
) -> tuple[ast.Name, ast.Constant, ast.AnnAssign, ast.FunctionDef]:
    """単一DTOのfieldと既validatorを曖昧な候補なしで特定する。"""
    tree = ast.parse(source)
    classes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "InitialGameStartResponse"
    ]
    assert len(classes) == 1 and classes[0] in tree.body
    fields = [
        n
        for n in classes[0].body
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "recovery_generation"
    ]
    methods = [
        n
        for n in classes[0].body
        if isinstance(n, ast.FunctionDef) and n.name == "_epoch_present"
    ]
    assert len(fields) == len(methods) == 1
    field, method = fields[0], methods[0]
    assert isinstance(field.target, ast.Name)
    decorators = [
        n
        for n in method.decorator_list
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "field_validator"
    ]
    assert len(decorators) == 1
    decorator = decorators[0]
    assert len(decorator.args) == 1 and not decorator.keywords
    literal = decorator.args[0]
    assert isinstance(literal, ast.Constant) and literal.value == "recovery_generation"
    return field.target, literal, field, method


def _ast_digest(node: ast.AST) -> str:
    """位置や整形に依存しない承認済み構造のdigestを求める。"""
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


@cache
def _approved_transport_hashes() -> tuple[str, str]:
    """固定Gitの承認済みDTOからだけ2構造を導出し、現在値を正解にしない。"""
    source = subprocess.check_output(
        [
            "git",
            "show",
            f"{_INITIAL_RESPONSE_REVISION}:{_INITIAL_RESPONSE_PATH.as_posix()}",
        ],
        cwd=_REPOSITORY_ROOT,
        text=True,
    )
    _, _, field, method = _transport_nodes(source)
    return _ast_digest(field), _ast_digest(method)


def _node_span(source: str, node: ast.AST) -> tuple[int, int]:
    """ASTのUTF-8列位置をsource文字単位の半開区間へ直す。"""
    lines = source.splitlines(keepends=True)
    start_line, end_line = getattr(node, "lineno"), getattr(node, "end_lineno")
    start_column, end_column = (
        getattr(node, "col_offset"),
        getattr(node, "end_col_offset"),
    )
    assert start_line is not None and end_line is not None
    assert start_column is not None and end_column is not None

    def offset(line: int, column: int) -> int:
        prefix = lines[line - 1].encode("utf-8")[:column].decode("utf-8")
        return sum(map(len, lines[: line - 1])) + len(prefix)

    return offset(start_line, start_column), offset(end_line, end_column)


def _without_transport_tokens(path: Path, source: str) -> str | None:
    """exact2tokenだけを空白化し、他の全文字と従来の禁止語を残す。"""
    if path != _REPOSITORY_ROOT / _INITIAL_RESPONSE_PATH:
        return source
    try:
        name, literal, field, method = _transport_nodes(source)
        if (_ast_digest(field), _ast_digest(method)) != _approved_transport_hashes():
            return None
        spans = (_node_span(source, name), _node_span(source, literal))
        lines = source.splitlines(keepends=True)
        matched = []
        for item in tokenize.generate_tokens(io.StringIO(source).readline):
            start = sum(map(len, lines[: item.start[0] - 1])) + item.start[1]
            end = sum(map(len, lines[: item.end[0] - 1])) + item.end[1]
            if (start, end) in spans:
                assert item.type == (
                    token.NAME if (start, end) == spans[0] else token.STRING
                )
                matched.append((start, end))
        assert sorted(matched) == sorted(spans) and len(set(spans)) == 2
        for start, end in sorted(spans, reverse=True):
            source = source[:start] + " " * (end - start) + source[end:]
        return source
    except (AssertionError, SyntaxError, ValueError, UnicodeError, tokenize.TokenError):
        return None


def _has_synchronization_term(path: Path, source: str) -> bool:
    """許可不能な形を閉じ、exact2token以外は全5語の部分一致を保つ。"""
    inspected = _without_transport_tokens(path, source)
    return inspected is None or any(
        term in inspected for term in _SYNCHRONIZATION_TERMS
    )


@pytest.fixture(autouse=True)
def _configure_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """アプリ生成試験へ CSPRNG 由来の署名鍵を与える。"""
    encoded_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    monkeypatch.setenv("PITCHLOG_TOKEN_SIGNING_KEY_B64", encoded_key)


def _api_source_files() -> tuple[Path, ...]:
    """API 配下の Python ソースファイルを列挙する。

    Returns:
        検査対象のソースファイル。
    """
    assert _API_SOURCE_ROOT.is_dir()
    source_files = tuple(sorted(_API_SOURCE_ROOT.rglob("*.py")))
    assert source_files
    return source_files


def _api_source_text() -> str:
    """API 配下の Python ソースを連結して返す。

    Returns:
        検査対象の全ソーステキスト。
    """
    return "\n".join(
        source_file.read_text(encoding="utf-8") for source_file in _api_source_files()
    )


def _router_routes() -> tuple[APIRoute, ...]:
    """静的登録したルータから API 経路を抽出する。

    Returns:
        静的登録した API 経路。
    """
    return tuple(
        route
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
    )


def _registry_operation_ids() -> set[str]:
    """認可経路レジストリの操作識別子を取得する。

    Returns:
        認可経路レジストリに定義された操作識別子。
    """
    assert _ROUTE_REGISTRY_PATH.is_file()
    registry = json.loads(_ROUTE_REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(registry, dict)
    enums = registry.get("enums")
    assert isinstance(enums, dict)
    operation_ids = enums.get("operation_ids")
    assert isinstance(operation_ids, list)
    assert all(isinstance(operation_id, str) for operation_id in operation_ids)
    return {
        operation_id for operation_id in operation_ids if isinstance(operation_id, str)
    }


def test_api_source_has_no_database_terms() -> None:
    """API ソースにデータベース接続の語彙が無いことを確認する。"""
    source_text = _api_source_text()

    assert not _has_database_term(source_text)


@pytest.mark.parametrize("term", _DATABASE_TERMS)
def test_database_term_guard_rejects_each_forbidden_term(term: str) -> None:
    """禁止したDB語彙を判定器が個別に見逃さないことを確認する。"""
    assert _has_database_term(f"before\n{term}\nafter")


def test_database_term_guard_allows_only_the_approved_dto_identifier() -> None:
    """承認済みDTO名だけはSession部分文字列による誤検出から除く。"""
    assert not _has_database_term("AuthSessionResponse")


@pytest.mark.parametrize(
    "source_text",
    (
        "AsyncSession",
        "DatabaseSession",
        "sqlalchemy_session",
        "db_engine",
        "sqlalchemy2",
        "AuthSessionResponse.Session.execute",
    ),
)
def test_database_term_guard_rejects_embedded_forbidden_terms(
    source_text: str,
) -> None:
    """複合識別子に埋め込まれた従来の禁止語彙も拒否する。"""
    assert _has_database_term(source_text)


def test_api_source_has_no_synchronization_terms() -> None:
    """API ソースに同期セマンティクスの語彙が無いことを確認する。"""
    assert all(
        not _has_synchronization_term(path, path.read_text(encoding="utf-8"))
        for path in _api_source_files()
    )


@pytest.mark.anyio
async def test_forbidden_response_is_hidden_as_not_found() -> None:
    """403 が 404 と完全に同一の本文へ写ることを確認する。"""
    app = create_app()

    @app.get("/forbidden")
    async def raise_forbidden() -> None:
        """403 の HTTP 例外を送出する。"""
        raise HTTPException(status_code=403)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        not_found_response = await client.get("/missing")
        forbidden_response = await client.get("/forbidden")

    assert forbidden_response.status_code == 404
    assert forbidden_response.content == not_found_response.content


def test_router_routes_are_static_login_roster_and_meta() -> None:
    """静的登録したメタ情報・認証・選手・チーム・試合の23本を照合する。"""
    routes = _router_routes()

    assert len(routes) == 23
    assert tuple((route.path, frozenset(route.methods or ())) for route in routes) == (
        ("/health", frozenset({"GET"})),
        ("/version", frozenset({"GET"})),
        ("/auth/login", frozenset({"POST"})),
        ("/auth/session", frozenset({"GET"})),
        ("/auth/logout", frozenset({"POST"})),
        ("/auth/password", frozenset({"PATCH"})),
        ("/players", frozenset({"POST"})),
        ("/players", frozenset({"GET"})),
        ("/players/{player_id:uuid}", frozenset({"GET"})),
        ("/players/{player_id:uuid}", frozenset({"PATCH"})),
        ("/players/status-preview", frozenset({"POST"})),
        ("/players/status-apply", frozenset({"POST"})),
        ("/team-records", frozenset({"POST"})),
        ("/team-records", frozenset({"GET"})),
        ("/team-records/self", frozenset({"GET"})),
        ("/team-records/{team_record_id:uuid}", frozenset({"PATCH"})),
        ("/team-records/{team_record_id:uuid}", frozenset({"DELETE"})),
        ("/team-records/{team_record_id:uuid}/lineup-memory", frozenset({"GET"})),
        ("/games", frozenset({"GET"})),
        ("/games/{game_id}", frozenset({"GET"})),
        ("/devices/enroll", frozenset({"POST"})),
        ("/games/{game_id}/start", frozenset({"POST"})),
        ("/games/{game_id}/start/resolve", frozenset({"POST"})),
    )
    assert all(route.response_model is not None for route in routes)


def test_error_envelope_models_have_no_code_field() -> None:
    """エラー封筒と入れ子モデルが理由コードを持たないことを確認する。"""
    error_models = (ErrorEnvelope, ErrorDetail, ErrorField)

    assert all("code" not in error_model.model_fields for error_model in error_models)


def test_api_operation_ids_do_not_overlap_authz_registry() -> None:
    """API の operation ID が認可経路レジストリと重ならないことを確認する。"""
    routes = _router_routes()
    assert all(route.operation_id is not None for route in routes)
    operation_ids = {
        route.operation_id for route in routes if route.operation_id is not None
    }

    assert operation_ids.isdisjoint(_registry_operation_ids())


def test_error_handlers_do_not_access_request_data() -> None:
    """例外ハンドラが要求の機密情報を参照しないことを確認する。"""
    error_source_path = _API_SOURCE_ROOT / "errors.py"
    assert error_source_path.is_file()
    source_text = error_source_path.read_text(encoding="utf-8")

    assert all(pattern not in source_text for pattern in _REQUEST_ACCESS_PATTERNS)


def _transport_source() -> tuple[Path, str]:
    """対向へ渡す承認済みの実DTOと正確なパスを得る。"""
    path = _REPOSITORY_ROOT / _INITIAL_RESPONSE_PATH
    return path, path.read_text(encoding="utf-8")


def test_sync_term_guard_allows_exact_two_approved_transport_tokens() -> None:
    """既2token以外のsource文字は日本語・コメントも含め変更しない。"""
    path, source = _transport_source()
    inspected = _without_transport_tokens(path, source)
    assert inspected is not None and len(inspected) == len(source)
    name, literal, field, method = _transport_nodes(source)
    assert (_ast_digest(field), _ast_digest(method)) == _approved_transport_hashes()
    spans = [_node_span(source, node) for node in (name, literal)]
    assert source[spans[0][0] : spans[0][1]] == "recovery_generation"
    assert source[spans[1][0] : spans[1][1]] == '"recovery_generation"'
    for index, (original, result) in enumerate(zip(source, inspected, strict=True)):
        assert result == (
            " " if any(start <= index < end for start, end in spans) else original
        )
    assert not _has_synchronization_term(path, source)


@pytest.mark.parametrize("term", _SYNCHRONIZATION_TERMS)
@pytest.mark.parametrize(
    "location", ("module", "field-line", "validator", "comment", "string")
)
def test_sync_term_guard_keeps_all_five_terms_red_outside_exact_tokens(
    term: str,
    location: str,
) -> None:
    """他の全位置ではコメント/文字列/行末も従来の部分一致で拒否する。"""
    path, source = _transport_source()
    if location == "module":
        source += f"\n{term} = 1\n"
    elif location == "field-line":
        source = source.replace(
            "    recovery_generation: str", f"    recovery_generation: str  # {term}"
        )
    elif location == "validator":
        source = source.replace(
            "            or int(value) > 2**63 - 1",
            f"            or int(value) > 2**63 - 1  # {term}",
        )
    elif location == "comment":
        source += f"\n# {term}\n"
    else:
        source += f'\nextra = "{term}"\n'
    assert _has_synchronization_term(path, source)


@pytest.mark.parametrize("term", _SYNCHRONIZATION_TERMS)
def test_sync_term_guard_preserves_other_api_file_rejection(term: str) -> None:
    """通常APIの同じ語をDTO例外へ巻き込まない。"""
    path = _API_SOURCE_ROOT / "routers/games.py"
    assert _has_synchronization_term(path, f"before_{term}_after = 1\n")


@pytest.mark.parametrize(
    "mutation",
    (
        "other-path",
        "other-class",
        "other-method",
        "unknown-field",
        "reference",
        "field-annotation",
        "decorator-extra",
        "decorator-alias",
        "calculation",
        "duplicate-field",
        "duplicate-method",
        "duplicate-class",
        "syntax",
        "adjacent-string",
        "same-line-expression",
    ),
)
def test_sync_term_guard_rejects_unknown_owners_and_modified_validator(
    mutation: str,
) -> None:
    """承認済み構造の変更/重複/未知場所/任意計算を例外で隠さない。"""
    path, source = _transport_source()
    _, _, _, method = _transport_nodes(source)
    if mutation == "other-path":
        path = _API_SOURCE_ROOT / "schemas/other.py"
    elif mutation == "other-class":
        source = source.replace(
            "class InitialGameStartResponse(", "class OtherResponse("
        )
    elif mutation == "other-method":
        source = source.replace("def _epoch_present(", "def _other_epoch_present(")
    elif mutation == "unknown-field":
        source += "\n    unknown_generation: str\n"
    elif mutation == "reference":
        source += "\n    def other(self):\n        return self.recovery_generation\n"
    elif mutation == "field-annotation":
        source = source.replace(
            "recovery_generation: str", "recovery_generation: object"
        )
    elif mutation == "decorator-extra":
        source = source.replace(
            '@field_validator("recovery_generation")',
            '@field_validator("recovery_generation", "d4")',
        )
    elif mutation == "decorator-alias":
        source = source.replace(
            '@field_validator("recovery_generation")',
            '@validator_alias("recovery_generation")',
        )
    elif mutation == "calculation":
        source = source.replace(
            "or int(value) > 2**63 - 1", "or int(value) > 2**62 - 1"
        )
    elif mutation == "duplicate-field":
        source += "\n    recovery_generation: str\n"
    elif mutation == "duplicate-method":
        lines = source.splitlines(keepends=True)
        assert method.end_lineno is not None
        source += "\n" + "".join(
            lines[method.decorator_list[0].lineno - 1 : method.end_lineno]
        )
    elif mutation == "duplicate-class":
        source += "\nclass InitialGameStartResponse:\n    pass\n"
    elif mutation == "syntax":
        source += "\n(\n"
    elif mutation == "adjacent-string":
        source = source.replace(
            '@field_validator("recovery_generation")',
            '@field_validator("recovery_" "generation")',
        )
    else:
        source = source.replace(
            "recovery_generation: str", "recovery_generation: str; extra_generation = 1"
        )
    assert _has_synchronization_term(path, source)


def test_sync_term_guard_converts_utf8_columns_without_losing_source_text() -> None:
    """AST byte列とtokenize文字列の差を非ASCIIの同一行で確かめる。"""
    source = 'label = "球"; recovery_generation\n'
    expression = ast.parse(source).body[1]
    assert isinstance(expression, ast.Expr)
    start, end = _node_span(source, expression.value)
    assert source[start:end] == "recovery_generation"


def test_sync_term_guard_unknown_position_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AST構造が同じでもtokenの位置照合を一意にできなければ拒否する。"""
    path, source = _transport_source()
    monkeypatch.setattr(sys.modules[__name__], "_node_span", lambda *_: (0, 1))
    assert _has_synchronization_term(path, source)
