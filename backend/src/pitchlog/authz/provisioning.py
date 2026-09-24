"""資産の順序と部分原子性に従って認可 DDL を適用する。"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus

from pitchlog.authz.asset_spec import PROBE_SPEC, AuthzAssetSpec
from pitchlog.authz.ddl import DDLStatement, generate_authz_ddl

_OPERATION_HANDLERS = {
    operation.operation_kind: operation.handler_name
    for operation in PROBE_SPEC.operation_handlers
}
_CREATE_OWNER = next(
    kind for kind, handler in _OPERATION_HANDLERS.items() if handler == "_create_roles"
)
_OPEN_SET_PATH = next(
    kind for kind, handler in _OPERATION_HANDLERS.items() if handler == "_open_set_path"
)
_ASSIGN_OBJECTS = next(
    kind
    for kind, handler in _OPERATION_HANDLERS.items()
    if handler == "_assign_objects"
)
_CLOSE_FUNCTION_ACL = next(
    kind
    for kind, handler in _OPERATION_HANDLERS.items()
    if handler == "_close_function_acl"
)
_CLOSE_SET_PATH = next(
    kind
    for kind, handler in _OPERATION_HANDLERS.items()
    if handler == "_close_set_path"
)
_ALTER_FUNCTION_RE = re.compile(r"(?m)^ALTER FUNCTION\b")
_REVOKE_FUNCTION_RE = re.compile(r"(?m)^REVOKE ALL PRIVILEGES\b")
_CREATE_FUNCTION_RE = re.compile(r"(?m)^CREATE FUNCTION\b")
_CREATE_POLICY_RE = re.compile(
    r"(?is)\bCREATE\s+POLICY\s+([a-z_][a-z0-9_]*)\s+"
    r"ON\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b"
)


class ProvisioningError(Exception):
    """DDL 適用を安全に完了できない状態を表す。"""


@dataclass(frozen=True, slots=True)
class ExecutionCheckpoint:
    """SQL 適用位置と資産要素の対応を表す。

    Attributes:
        checkpoint_id: ``<step_id>#<1始まり序数>`` 形式の一意 ID。
        step_id: provisioning claim の手順 ID。
        sequence: 資産が指定する手順の順序。
        ordinal: 同じ手順内の 1 始まり序数。
        operation_kind: 資産が指定する操作種別。
        element_type: SQL の資産要素種別。
        element_id: SQL の資産要素 ID。
    """

    checkpoint_id: str
    step_id: str
    sequence: int
    ordinal: int
    operation_kind: str
    element_type: str
    element_id: str


@dataclass(frozen=True, slots=True)
class ProvisioningResult:
    """DDL 適用で確定した実行ログを保持する。

    Attributes:
        checkpoints: 実際の実行順に並んだ checkpoint ログ。
    """

    checkpoints: tuple[ExecutionCheckpoint, ...]


@dataclass(frozen=True, slots=True)
class _ProvisioningStep:
    """資産から解釈した provisioning 手順を表す。"""

    step_id: str
    sequence: int
    operation_kind: str


@dataclass(frozen=True, slots=True)
class _ProvisioningFaults:
    """負例専用の単独故障を表す。"""

    split_function_transaction: bool = False
    skip_membership_revoke: bool = False
    skip_acl_normalization: bool = False


@dataclass(frozen=True, slots=True)
class _FunctionParts:
    """関数 DDL の部分原子性に必要な三部分を保持する。"""

    create_or_replace: str
    alter_owner: str
    revoke_public: str


class _CheckpointRecorder:
    """手順ごとの連番を発行して実行ログを蓄積する。"""

    def __init__(self) -> None:
        """空の実行ログを初期化する。"""
        self._ordinals: defaultdict[str, int] = defaultdict(int)
        self._checkpoints: list[ExecutionCheckpoint] = []

    def record(self, step: _ProvisioningStep, statement: DDLStatement) -> None:
        """実行済み SQL 単位へ次の checkpoint を割り当てる。"""
        self._ordinals[step.step_id] += 1
        ordinal = self._ordinals[step.step_id]
        self._checkpoints.append(
            ExecutionCheckpoint(
                checkpoint_id=f"{step.step_id}#{ordinal}",
                step_id=step.step_id,
                sequence=step.sequence,
                ordinal=ordinal,
                operation_kind=step.operation_kind,
                element_type=statement.element_type,
                element_id=statement.element_id,
            )
        )

    def result(self) -> ProvisioningResult:
        """確定順を保った不変の実行結果を返す。"""
        return ProvisioningResult(checkpoints=tuple(self._checkpoints))


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    """JSON object を読み、入力不正を単一例外へ変換する。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProvisioningError(f"{label}を読めない: {path}: {error}") from error
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise ProvisioningError(f"{label}はJSON objectでなければならない")
    return raw


def _expect_string(value: object, label: str) -> str:
    """空でない文字列だけを受け入れる。"""
    if not isinstance(value, str) or not value:
        raise ProvisioningError(f"{label}は空でない文字列でなければならない")
    return value


def _expect_bool(value: object, label: str) -> bool:
    """真偽値だけを受け入れる。"""
    if not isinstance(value, bool):
        raise ProvisioningError(f"{label}はbooleanでなければならない")
    return value


def _object_rows(asset: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    """資産の object 配列を型確認して返す。"""
    raw_rows = asset.get(key)
    if not isinstance(raw_rows, list) or not all(
        isinstance(row, dict) for row in raw_rows
    ):
        raise ProvisioningError(f"ddl-elements.{key}はobject配列でなければならない")
    return tuple(row for row in raw_rows if isinstance(row, dict))


def _external_provisioner(asset: dict[str, object]) -> dict[str, object]:
    """資産から外部 provisioner の宣言を一意に導出する。"""
    provisioners = [
        row
        for row in _object_rows(asset, "roles")
        if row.get("role_kind") == "external_provisioner"
    ]
    if len(provisioners) != 1:
        raise ProvisioningError("external_provisionerを一意に導出できない")
    return provisioners[0]


def _validate_external_prerequisites(
    connection: psycopg.Connection[Any], provisioner: dict[str, object]
) -> None:
    """Ordered steps 外から与える認証主体と database 権限を検査する。"""
    role_id = _expect_string(provisioner.get("role_id"), "external_provisioner.role_id")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT session_user,
                   current_user,
                   current_database(),
                   role.rolcanlogin,
                   role.rolbypassrls,
                   role.rolsuper,
                   role.rolcreaterole,
                   role.rolinherit,
                   pg_catalog.has_database_privilege(
                       %s,
                       current_database(),
                       'CREATE'
                   ),
                   pg_catalog.has_database_privilege(
                       %s,
                       current_database(),
                       'CONNECT'
                   )
            FROM pg_catalog.pg_roles AS role
            WHERE role.rolname = %s
            """,
            (role_id, role_id, role_id),
        )
        row = cursor.fetchone()
    connection.rollback()
    if row is None:
        raise ProvisioningError(
            "外部前提が満たされていない: external_provisionerが存在しない"
        )

    session_user, current_user, database_name, *observed = row
    if session_user != role_id or current_user != role_id:
        raise ProvisioningError(
            "外部前提が満たされていない: "
            f'external_provisioner "{role_id}" で直接接続する必要がある'
        )

    attribute_names = ("login", "bypass_rls", "superuser", "create_role", "inherit")
    expected_attributes = tuple(
        _expect_bool(provisioner.get(name), f"external_provisioner.{name}")
        for name in attribute_names
    )
    observed_attributes = tuple(bool(value) for value in observed[:-2])
    if observed_attributes != expected_attributes:
        raise ProvisioningError(
            "外部前提が満たされていない: "
            f'external_provisioner "{role_id}" のロール属性が資産と一致しない'
        )

    privilege_names = ("CREATE", "CONNECT")
    missing_privileges = [
        name
        for name, allowed in zip(privilege_names, observed[-2:], strict=True)
        if not allowed
    ]
    if missing_privileges:
        missing = ", ".join(missing_privileges)
        raise ProvisioningError(
            "外部前提が満たされていない: "
            f'external_provisioner "{role_id}" には接続先データベース '
            f'"{database_name}" の CREATE と CONNECT 権限が必要 '
            f"(不足: {missing})"
        )


def _operation_handlers_for(spec: AuthzAssetSpec) -> dict[str, str]:
    """資産指定が閉じた操作種別と処理関数の対応を返す。"""
    if spec == PROBE_SPEC:
        return _OPERATION_HANDLERS
    return {
        operation.operation_kind: operation.handler_name
        for operation in spec.operation_handlers
    }


def _ordered_steps(
    asset: dict[str, object],
    spec: AuthzAssetSpec = PROBE_SPEC,
) -> tuple[_ProvisioningStep, ...]:
    """資産の sequence から provisioning 手順の実行順を導出する。"""
    claim = asset.get("provisioning_claim")
    if not isinstance(claim, dict):
        raise ProvisioningError("ddl-elements.provisioning_claimがobjectでない")
    raw_steps = claim.get("ordered_steps")
    if not isinstance(raw_steps, list):
        raise ProvisioningError("provisioning_claim.ordered_stepsがarrayでない")

    steps: list[_ProvisioningStep] = []
    for index, raw_step in enumerate(raw_steps):
        label = f"provisioning_claim.ordered_steps[{index}]"
        if not isinstance(raw_step, dict):
            raise ProvisioningError(f"{label}がobjectでない")
        sequence = raw_step.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ProvisioningError(f"{label}.sequenceが正の整数でない")
        steps.append(
            _ProvisioningStep(
                step_id=_expect_string(raw_step.get("step_id"), f"{label}.step_id"),
                sequence=sequence,
                operation_kind=_expect_string(
                    raw_step.get("operation_kind"), f"{label}.operation_kind"
                ),
            )
        )
    steps.sort(key=lambda step: step.sequence)
    if [step.sequence for step in steps] != list(range(1, len(steps) + 1)):
        raise ProvisioningError("provisioning sequenceが1始まりの連番でない")
    if len({step.step_id for step in steps}) != len(steps):
        raise ProvisioningError("provisioning step_idが重複している")
    operation_handlers = _operation_handlers_for(spec)
    if any(step.operation_kind not in operation_handlers for step in steps):
        raise ProvisioningError("未対応のprovisioning operation_kindがある")

    boundaries = _object_rows(asset, "transaction_boundaries")
    step_ids = [step.step_id for step in steps]
    matching_boundaries = [
        boundary
        for boundary in boundaries
        if boundary.get("boundary_kind") == "ordered_application"
        and boundary.get("step_ids") == step_ids
    ]
    if (
        len(matching_boundaries) != 1
        or matching_boundaries[0].get("atomic") is not False
    ):
        raise ProvisioningError(
            "非原子的なprovisioning transaction境界を一意に導出できない"
        )
    return tuple(steps)


def _split_simple_sql(sql_text: str) -> tuple[str, ...]:
    """引用符とコメント内を除くセミコロンで SQL 単位を分ける。"""
    statements: list[str] = []
    start = 0
    index = 0
    quote = ""
    line_comment = False
    block_depth = 0
    while index < len(sql_text):
        current = sql_text[index]
        following = sql_text[index + 1 : index + 2]
        if line_comment:
            if current == "\n":
                line_comment = False
            index += 1
            continue
        if block_depth:
            if current == "/" and following == "*":
                block_depth += 1
                index += 2
            elif current == "*" and following == "/":
                block_depth -= 1
                index += 2
            else:
                index += 1
            continue
        if quote:
            if current == quote and following == quote:
                index += 2
            elif current == quote:
                quote = ""
                index += 1
            else:
                index += 1
            continue
        if current == "-" and following == "-":
            line_comment = True
            index += 2
        elif current == "/" and following == "*":
            block_depth = 1
            index += 2
        elif current in {"'", '"'}:
            quote = current
            index += 1
        elif current == ";":
            statements.append(sql_text[start : index + 1])
            start = index + 1
            index += 1
        else:
            index += 1
    remainder = sql_text[start:]
    if remainder.strip():
        statements.append(remainder)
    return tuple(statement for statement in statements if _contains_sql(statement))


def _contains_sql(sql_text: str) -> bool:
    """コメントを除いた実行対象が存在するか判定する。"""
    without_block = re.sub(r"/\*.*?\*/", "", sql_text, flags=re.DOTALL)
    without_lines = re.sub(r"(?m)--.*$", "", without_block)
    return bool(without_lines.strip())


def _split_function_sql(statement: DDLStatement) -> _FunctionParts:
    """関数 body を作成・所有者変更・PUBLIC 剥奪へ分ける。"""
    alter_match = _ALTER_FUNCTION_RE.search(statement.sql)
    if alter_match is None:
        raise ProvisioningError(
            f"関数DDLにALTER FUNCTIONがない: {statement.element_id}"
        )
    revoke_match = _REVOKE_FUNCTION_RE.search(statement.sql, alter_match.end())
    if revoke_match is None:
        raise ProvisioningError(f"関数DDLにPUBLIC剥奪がない: {statement.element_id}")
    create_sql = statement.sql[: alter_match.start()]
    create_or_replace, replacements = _CREATE_FUNCTION_RE.subn(
        "CREATE OR REPLACE FUNCTION", create_sql, count=1
    )
    if replacements != 1:
        raise ProvisioningError(
            f"関数DDLにCREATE FUNCTIONが1件ない: {statement.element_id}"
        )
    return _FunctionParts(
        create_or_replace=create_or_replace,
        alter_owner=statement.sql[alter_match.start() : revoke_match.start()],
        revoke_public=statement.sql[revoke_match.start() :],
    )


def _execute_ignoring_duplicate(cursor: psycopg.Cursor[Any], statement: str) -> None:
    """CREATE を試み、既存 object だけを savepoint で許容する。"""
    cursor.execute("SAVEPOINT authz_create_attempt")
    try:
        cursor.execute(statement.encode("utf-8"))
    except (
        psycopg.errors.DuplicateObject,
        psycopg.errors.DuplicateSchema,
        psycopg.errors.DuplicateTable,
    ):
        cursor.execute("ROLLBACK TO SAVEPOINT authz_create_attempt")
    cursor.execute("RELEASE SAVEPOINT authz_create_attempt")


class _Application:
    """単一接続上で資産由来の provisioning 手順を実行する。"""

    def __init__(
        self,
        connection: psycopg.Connection[Any],
        asset: dict[str, object],
        statements: tuple[DDLStatement, ...],
        on_function_created: Callable[[DDLStatement], None] | None,
        faults: _ProvisioningFaults,
        operation_handlers: dict[str, str],
    ) -> None:
        """適用に必要な接続・資産・SQL・観測フックを保持する。"""
        self.connection = connection
        self.asset = asset
        self.statements = statements
        self.on_function_created = on_function_created
        self.faults = faults
        self.operation_handlers = operation_handlers
        self.recorder = _CheckpointRecorder()
        self.pending_function_revokes: list[tuple[DDLStatement, str]] = []
        self.roles = _object_rows(asset, "roles")
        self.schemas = _object_rows(asset, "schemas")
        self.tables = _object_rows(asset, "tables")
        self.functions = _object_rows(asset, "functions")
        provisioner = _external_provisioner(asset)
        self.provisioner_id = _expect_string(
            provisioner.get("role_id"), "external_provisioner.role_id"
        )
        owner_ids = {
            _expect_string(row.get("owner_role_id"), "owner_role_id")
            for row in (*self.schemas, *self.tables, *self.functions)
        }
        self.owner_ids = tuple(
            role_id
            for role in self.roles
            if (role_id := _expect_string(role.get("role_id"), "roles.role_id"))
            in owner_ids
        )
        self.role_statements = {
            statement.element_id: statement
            for statement in statements
            if statement.element_type == "role"
        }

    def run(self, steps: tuple[_ProvisioningStep, ...]) -> ProvisioningResult:
        """Sequence 順の手順を operation_kind で dispatch する。"""
        try:
            for step in steps:
                handler_name = self.operation_handlers[step.operation_kind]
                handler = getattr(self, handler_name)
                handler(step)
        except ProvisioningError:
            self._rollback_after_error()
            raise
        except psycopg.Error as error:
            self._rollback_after_error()
            raise ProvisioningError(
                f"provisioning SQLの実行に失敗した: {error}"
            ) from error
        return self.recorder.result()

    def _create_roles(self, step: _ProvisioningStep) -> None:
        """全ロールを作成し、属性を常に資産値へ正規化する。"""
        rows_by_id = {
            _expect_string(row.get("role_id"), "roles.role_id"): row
            for row in self.roles
        }
        for statement in self.statements:
            if statement.element_type != "role":
                continue
            if statement.element_id == self.provisioner_id:
                continue
            with self.connection.cursor() as cursor:
                # 非 superuser は BYPASSRLS 付き CREATE ROLE を実行できないため、
                # まず既定属性で作り、自身が持つ BYPASSRLS を ALTER で付与する。
                _execute_ignoring_duplicate(
                    cursor,
                    sql.SQL("CREATE ROLE {}")
                    .format(sql.Identifier(statement.element_id))
                    .as_string(self.connection),
                )
                self.recorder.record(step, statement)
                cursor.execute(self._alter_role_sql(rows_by_id[statement.element_id]))
                self.recorder.record(step, statement)
        self.connection.commit()

    def _alter_role_sql(self, role: dict[str, object]) -> sql.Composed:
        """ロール属性を資産から完全な ALTER ROLE へ変換する。"""
        role_id = _expect_string(role.get("role_id"), "roles.role_id")
        options = (
            "LOGIN" if _expect_bool(role.get("login"), "roles.login") else "NOLOGIN",
            "BYPASSRLS"
            if _expect_bool(role.get("bypass_rls"), "roles.bypass_rls")
            else "NOBYPASSRLS",
            "CREATEROLE"
            if _expect_bool(role.get("create_role"), "roles.create_role")
            else "NOCREATEROLE",
            "INHERIT"
            if _expect_bool(role.get("inherit"), "roles.inherit")
            else "NOINHERIT",
        )
        if _expect_bool(role.get("superuser"), "roles.superuser"):
            raise ProvisioningError(
                "external_provisionerはSUPERUSERロールを作成・正規化できない"
            )
        return sql.SQL("ALTER ROLE {} WITH {}").format(
            sql.Identifier(role_id), sql.SQL(" ").join(map(sql.SQL, options))
        )

    def _open_set_path(self, step: _ProvisioningStep) -> None:
        """全 object 所有ロールへの一時 SET membership を開く。"""
        for owner_id in self.owner_ids:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT TRUE").format(
                        sql.Identifier(owner_id),
                        sql.Identifier(self.provisioner_id),
                    )
                )
                self.recorder.record(step, self.role_statements[owner_id])
        self.connection.commit()

    def _assign_objects(self, step: _ProvisioningStep) -> None:
        """非 ACL object を作成し、関数の PUBLIC 剥奪を保留する。"""
        schemas_by_id = {
            _expect_string(row.get("schema_id"), "schemas.schema_id"): row
            for row in self.schemas
        }
        for statement in self.statements:
            if statement.element_type == "role" or statement.element_type.endswith(
                "acl_expectation"
            ):
                continue
            if statement.element_type == "function":
                self._create_function(step, statement)
                continue
            commands = _split_simple_sql(statement.sql)
            with self.connection.cursor() as cursor:
                if statement.element_type == "policy":
                    self._replace_policy(cursor, step, statement, commands)
                elif commands:
                    _execute_ignoring_duplicate(cursor, commands[0])
                    self.recorder.record(step, statement)
                    for command in commands[1:]:
                        cursor.execute(command.encode("utf-8"))
                        self.recorder.record(step, statement)
                if statement.element_type == "schema":
                    schema = schemas_by_id[statement.element_id]
                    owner_id = _expect_string(
                        schema.get("owner_role_id"), "schemas.owner_role_id"
                    )
                    cursor.execute(
                        sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(
                            sql.Identifier(statement.element_id),
                            sql.Identifier(owner_id),
                        )
                    )
                    self.recorder.record(step, statement)

    def _replace_policy(
        self,
        cursor: psycopg.Cursor[Any],
        step: _ProvisioningStep,
        statement: DDLStatement,
        commands: tuple[str, ...],
    ) -> None:
        """既存 policy を除去して資産 body の定義へ完全に置換する。"""
        if len(commands) != 1:
            raise ProvisioningError(
                f"policy bodyが単一SQL文でない: {statement.element_id}"
            )
        matches = tuple(_CREATE_POLICY_RE.finditer(commands[0]))
        if len(matches) != 1:
            raise ProvisioningError(
                f"policy bodyから識別子を一意に導出できない: {statement.element_id}"
            )
        policy_id, schema_id, table_id = matches[0].groups()
        cursor.execute(
            sql.SQL("DROP POLICY IF EXISTS {} ON {}.{}").format(
                sql.Identifier(policy_id),
                sql.Identifier(schema_id),
                sql.Identifier(table_id),
            )
        )
        self.recorder.record(step, statement)
        cursor.execute(commands[0].encode("utf-8"))
        self.recorder.record(step, statement)

    def _create_function(
        self, step: _ProvisioningStep, statement: DDLStatement
    ) -> None:
        """関数を置換作成し、PUBLIC 剥奪前の観測点を発行する。"""
        parts = _split_function_sql(statement)
        with self.connection.cursor() as cursor:
            cursor.execute(parts.create_or_replace.encode("utf-8"))
            self.recorder.record(step, statement)
            cursor.execute(parts.alter_owner.encode("utf-8"))
            self.recorder.record(step, statement)
        if self.faults.split_function_transaction:
            self.connection.commit()
        if self.on_function_created is not None:
            self.on_function_created(statement)
        self.pending_function_revokes.append((statement, parts.revoke_public))

    def _close_function_acl(self, step: _ProvisioningStep) -> None:
        """PUBLIC 剥奪と名前付き ACL 正規化を同じ transaction で閉じる。"""
        for statement, revoke_sql in self.pending_function_revokes:
            with self.connection.cursor() as cursor:
                cursor.execute(revoke_sql.encode("utf-8"))
                self.recorder.record(step, statement)
        if not self.faults.skip_acl_normalization:
            for statement in self.statements:
                if not statement.element_type.endswith("acl_expectation"):
                    continue
                with self.connection.cursor() as cursor:
                    for command in _split_simple_sql(statement.sql):
                        cursor.execute(command.encode("utf-8"))
                        self.recorder.record(step, statement)
        self.connection.commit()

    def _close_set_path(self, step: _ProvisioningStep) -> None:
        """再適用用 ADMIN を残し、一時 SET・INHERIT 経路を閉じる。"""
        if self.faults.skip_membership_revoke:
            return
        for owner_id in self.owner_ids:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("REVOKE SET OPTION FOR {} FROM {}").format(
                        sql.Identifier(owner_id),
                        sql.Identifier(self.provisioner_id),
                    )
                )
                self.recorder.record(step, self.role_statements[owner_id])
                cursor.execute(
                    sql.SQL("REVOKE INHERIT OPTION FOR {} FROM {}").format(
                        sql.Identifier(owner_id),
                        sql.Identifier(self.provisioner_id),
                    )
                )
                self.recorder.record(step, self.role_statements[owner_id])
        self.connection.commit()

    def _rollback_after_error(self) -> None:
        """失敗 transaction を戻す。"""
        self.connection.rollback()


def _apply_authz_ddl(
    connection: psycopg.Connection[Any],
    root: Path,
    *,
    spec: AuthzAssetSpec = PROBE_SPEC,
    on_function_created: Callable[[DDLStatement], None] | None = None,
    faults: _ProvisioningFaults | None = None,
) -> ProvisioningResult:
    """テスト用故障を任意に注入して認可 DDL を適用する。"""
    if connection.closed:
        raise ProvisioningError("閉じた接続ではprovisioningできない")
    if connection.autocommit:
        raise ProvisioningError("部分原子性のためautocommit無効の接続が必要")
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ProvisioningError("未完了transactionを持つ接続ではprovisioningできない")
    asset = _read_json_object(
        root.resolve() / spec.ddl_elements_path,
        "ddl-elements",
    )
    steps = _ordered_steps(asset) if spec == PROBE_SPEC else _ordered_steps(asset, spec)
    _validate_external_prerequisites(connection, _external_provisioner(asset))
    try:
        statements = generate_authz_ddl(root, spec)
    except Exception as error:
        raise ProvisioningError(f"DDLを生成できない: {error}") from error
    application = _Application(
        connection,
        asset,
        statements,
        on_function_created,
        faults or _ProvisioningFaults(),
        _operation_handlers_for(spec),
    )
    return application.run(steps)


def apply_authz_ddl(
    connection: psycopg.Connection[Any],
    root: Path,
    spec: AuthzAssetSpec = PROBE_SPEC,
) -> ProvisioningResult:
    """資産順に認可 DDL を適用し、checkpoint ログを返す。

    Args:
        connection: external_provisioner で直接認証した autocommit 無効の接続。
        root: 認可資産を含むリポジトリルート。
        spec: 読み取る資産と許可する操作種別の指定。

    Returns:
        実行順の checkpoint ログを保持する結果。

    Raises:
        ProvisioningError: 資産不正または SQL 適用失敗の場合。
    """
    return _apply_authz_ddl(connection, root, spec=spec)
