"""専用クラスタを作り直し、越境試験の接続先まで確かめる。

実行例: ``uv run --project backend python -m scripts.product_rls_real_schema.runner``
接続情報は環境変数からのみ読む。失敗時は対象を推測せず、最初から再実行する。
共有開発 DB のサービスを起動しておくこと。停止中は共有クラスタを識別できず中止する。
Compose の解釈には共有側の ``POSTGRES_USER`` / ``POSTGRES_PASSWORD`` /
``POSTGRES_DB`` と専用側の ``PITCHLOG_PRODUCT_RLS_POSTGRES_*`` 4 変数が必要。
共有側の値は Compose の解釈にだけ使うため、実コンテナと一致しなくてよい。
共有クラスタの識別値はコンテナ内の環境変数で ``psql`` を実行して読む。
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import SplitResult, parse_qsl, quote, unquote, urlsplit, urlunsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TARGETS_PATH = REPOSITORY_ROOT / "scripts/product-rls-real-schema-targets.json"
CONTROL_QUERY = (
    "SELECT (SELECT system_identifier FROM pg_control_system()), "
    "current_database(), current_user, "
    "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
)
CONTAINER_CONTROL_QUERY = (
    'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 '
    '-U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc '
    '"SELECT system_identifier FROM pg_control_system()"'
)
ROLE_ID_PATTERN = re.compile(r"(?m)^-- ELEMENT-ID: ([A-Za-z_][A-Za-z0-9_]*)$")
OBSERVED_CONNECTIONS_PER_NODE = 2


class RunnerError(RuntimeError):
    """接続情報を含めずに報告できる準備中断。"""


@dataclass(frozen=True)
class TargetsConfig:
    """接続先の値を含まない対象定義。"""

    compose_project: str
    compose_service: str
    shared_compose_service: str
    compose_volume: str
    expected_test_nodes: int
    admin_dsn_env: str
    target_db_env: str
    test_role_dsn_env: str
    initial_db_env: str
    role_assets_dir: Path
    owner_role_asset: Path
    temporary_role_source: Path
    temporary_role_constant: str


@dataclass(frozen=True, repr=False)
class PreparedTarget:
    """作り直した対象の非公開接続と、出力可能な識別値。"""

    generation_id: str
    target_digest: str
    migration_head: str
    owner_dsn: str


@dataclass(frozen=True, repr=False)
class TargetEvidence:
    """同じ管理接続の読み取りで得た対象検査の材料。"""

    connected_cluster: str | None
    deployed_cluster: str | None
    shared_cluster: str | None
    operand_database: str | None
    approved_database: str | None
    test_role_database: str | None
    connected_database: str | None
    initial_database: str | None
    admin_user: str | None
    admin_is_superuser: bool | None


@dataclass(frozen=True)
class RoleNames:
    """DDL 資産・越境テスト・接続設定から読んだロール集合。"""

    owner: str
    privileges: tuple[str, ...]
    tested: str
    temporary: str

    @property
    def ordered(self) -> tuple[str, ...]:
        """運用正本 2-4 の撤去順を返す。"""
        return (self.owner, *self.privileges, self.tested, self.temporary)


def validate_target(evidence: TargetEvidence) -> None:
    """運用正本 2-1 の対象条件と管理接続の前提を検査する。

    Args:
        evidence: 同じ管理接続の読み取りと独立したコンテナ観測。

    Raises:
        RunnerError: 値を得られない、または対象条件を満たさない場合。
    """
    required = (
        evidence.connected_cluster,
        evidence.deployed_cluster,
        evidence.shared_cluster,
        evidence.operand_database,
        evidence.approved_database,
        evidence.test_role_database,
        evidence.connected_database,
        evidence.initial_database,
        evidence.admin_user,
    )
    if any(not value for value in required) or evidence.admin_is_superuser is None:
        raise RunnerError("対象の識別値を判定できない")
    if evidence.connected_cluster != evidence.deployed_cluster:
        raise RunnerError("接続先と専用コンテナのクラスタ実体が一致しない")
    if evidence.connected_cluster == evidence.shared_cluster:
        raise RunnerError("共有開発クラスタに接続している")
    if evidence.operand_database != evidence.approved_database:
        raise RunnerError("操作対象の名前が承認された対象名と一致しない")
    if evidence.test_role_database != evidence.approved_database:
        raise RunnerError("被検査ロールの接続先が承認された対象名と一致しない")
    if (
        evidence.connected_database != evidence.initial_database
        or evidence.connected_database == evidence.approved_database
    ):
        raise RunnerError("管理接続が初期化時のデータベースを指していない")
    if not evidence.admin_is_superuser:
        raise RunnerError("管理接続が superuser ではない")


def guard_drop(
    evidence: TargetEvidence,
    other_connections: int | None,
    drop: Callable[[], None],
) -> None:
    """対象と接続数を検査し、通過時だけ最初の DROP を呼ぶ。

    Args:
        evidence: 撤去直前に取得した対象識別値。
        other_connections: 本手順以外の対象 DB 接続数。
        drop: 最初の ``DROP DATABASE`` を行う関数。

    Raises:
        RunnerError: 対象が不正、または接続数が 0 でない場合。
    """
    validate_target(evidence)
    if other_connections is None or other_connections < 0:
        raise RunnerError("他の利用者の接続数を判定できない")
    if other_connections != 0:
        raise RunnerError("対象データベースに他の利用者が接続している")
    drop()


def _asset_path(relative: str) -> Path:
    """設定資産の相対パスをリポジトリ内に限定する。"""
    path = (REPOSITORY_ROOT / relative).resolve()
    if not path.is_relative_to(REPOSITORY_ROOT) or not path.is_file():
        raise RunnerError("指定された資産を読めない")
    return path


def _load_targets() -> TargetsConfig:
    """接続値を含まない設定資産を読む。"""
    try:
        raw = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RunnerError("対象定義を読めない") from error
    string_keys = {
        "compose_project",
        "compose_service",
        "shared_compose_service",
        "compose_volume",
        "admin_dsn_env",
        "target_db_env",
        "test_role_dsn_env",
        "initial_db_env",
        "role_assets_dir",
        "owner_role_asset",
        "temporary_role_source",
        "temporary_role_constant",
    }
    if not isinstance(raw, dict) or set(raw) != {*string_keys, "expected_test_nodes"}:
        raise RunnerError("対象定義の項目が不正")
    if any(not isinstance(raw[key], str) or not raw[key] for key in string_keys):
        raise RunnerError("対象定義の値が不正")
    expected_test_nodes = raw["expected_test_nodes"]
    if type(expected_test_nodes) is not int or expected_test_nodes <= 0:
        raise RunnerError("試験 node 数の期待値が不正")
    role_dir = (REPOSITORY_ROOT / raw["role_assets_dir"]).resolve()
    if not role_dir.is_relative_to(REPOSITORY_ROOT) or not role_dir.is_dir():
        raise RunnerError("ロール資産の場所が不正")
    return TargetsConfig(
        compose_project=raw["compose_project"],
        compose_service=raw["compose_service"],
        shared_compose_service=raw["shared_compose_service"],
        compose_volume=raw["compose_volume"],
        expected_test_nodes=expected_test_nodes,
        admin_dsn_env=raw["admin_dsn_env"],
        target_db_env=raw["target_db_env"],
        test_role_dsn_env=raw["test_role_dsn_env"],
        initial_db_env=raw["initial_db_env"],
        role_assets_dir=role_dir,
        owner_role_asset=_asset_path(raw["owner_role_asset"]),
        temporary_role_source=_asset_path(raw["temporary_role_source"]),
        temporary_role_constant=raw["temporary_role_constant"],
    )


def _required_environment(name: str) -> str:
    """空でない環境変数を読み、値をエラーへ含めない。"""
    value = os.environ.get(name)
    if not value:
        raise RunnerError(f"必須の環境変数が未設定: {name}")
    return value


def _split_dsn(dsn: str) -> SplitResult:
    """libpq URL の接続先を解釈し、上書き可能なクエリ指定を拒否する。"""
    try:
        parsed = urlsplit(dsn)
        valid = (
            parsed.scheme in {"postgresql", "postgres"}
            and parsed.username is not None
            and parsed.hostname is not None
            and parsed.port is not None
            and bool(parsed.path.removeprefix("/"))
        )
        query_keys = {key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    except ValueError as error:
        raise RunnerError("接続 URL を解釈できない") from error
    if not valid or query_keys & {"dbname", "user", "password", "host", "hostaddr", "port"}:
        raise RunnerError("接続 URL の指定が不正")
    return parsed


def _dsn_user_and_database(dsn: str) -> tuple[str, str]:
    """被検査ロールの URL から利用者名と DB 名を読む。"""
    parsed = _split_dsn(dsn)
    user = unquote(parsed.username or "")
    database = unquote(parsed.path.removeprefix("/"))
    if not user or not database:
        raise RunnerError("被検査ロールの接続 URL が不完全")
    return user, database


def _database_dsn(admin_dsn: str, database: str) -> str:
    """管理接続の libpq URL の DB 部分だけを対象へ替える。"""
    parsed = _split_dsn(admin_dsn)
    return urlunsplit(parsed._replace(path=f"/{quote(database, safe='')}"))


def _test_environment(
    admin_dsn: str, test_role_dsn: str, database: str
) -> dict[str, str]:
    """凍結済み資産の変数名へ専用対象の接続値を割り当てる。"""
    path = REPOSITORY_ROOT / "backend/tests/db/environment-expectations.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        variables = raw["dsn_environment_variables"]
        admin_name = variables["admin_connection"]["expected_name"]
        role_name = variables["tested_role_connection"]["expected_name"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise RunnerError("試験の接続変数名を判定できない") from error
    if (
        not isinstance(admin_name, str)
        or not admin_name
        or not isinstance(role_name, str)
        or not role_name
        or admin_name == role_name
    ):
        raise RunnerError("試験の接続変数名が不正")
    if _dsn_user_and_database(test_role_dsn)[1] != database:
        raise RunnerError("被検査ロールの接続先が対象 DB と一致しない")
    return {
        admin_name: _database_dsn(admin_dsn, database),
        role_name: test_role_dsn,
    }


def _validate_test_observations(
    observations: list[tuple[str, str]],
    cluster: str,
    database: str,
    expected_test_nodes: int,
) -> None:
    """各 node の接続が同じ専用クラスタ・対象 DB を指すか確かめる。"""
    if len(observations) != expected_test_nodes * OBSERVED_CONNECTIONS_PER_NODE:
        raise RunnerError("製品越境試験の接続観測が期待 node 数分そろっていない")
    if any(item != (cluster, database) for item in observations):
        raise RunnerError("製品越境試験の接続先が専用対象と一致しない")


def _run_product_tests(
    config: TargetsConfig,
    admin_dsn: str,
    owner_dsn: str,
    test_role_dsn: str,
    database: str,
    target_digest: str,
) -> None:
    """同一プロセスの外部供給で試験を実行し、接続先だけを照合する。"""
    cluster = _container_cluster(config, config.compose_service)
    if _target_digest(cluster, database) != target_digest:
        raise RunnerError("作り直した対象と試験対象の要約値が一致しない")
    test_environment = _test_environment(admin_dsn, test_role_dsn, database)
    tests_dir = REPOSITORY_ROOT / "backend/tests"
    original_path = tuple(sys.path)
    previous_environment = {name: os.environ.get(name) for name in test_environment}
    previous_directory = Path.cwd()
    try:
        sys.path.insert(0, str(tests_dir))
        os.environ.update(test_environment)
        os.chdir(REPOSITORY_ROOT / "backend")
        fixtures = importlib.import_module("db_fixtures")
        pytest = importlib.import_module("pytest")
        handle = fixtures.DisposablePostgres(
            container_name=_container_id(config, config.compose_service),
            admin_dsn=admin_dsn,
            role_dsn_template=test_role_dsn,
        )
        with fixtures.supply_external_product_catalog(
            cluster=handle,
            applicator_dsn=_database_dsn(admin_dsn, database),
            owner_dsn=owner_dsn,
        ) as observations:
            # ステップ 4 は接続先だけを見るため、DDL 未適用による失敗出力を捨てる。
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                pytest.main(
                    [
                        "-c",
                        "pyproject.toml",
                        "--tb=no",
                        "--show-capture=no",
                        "-q",
                        "tests/db/test_product_authz_tenant_owned.py",
                        "tests/db/test_product_authz_cross_cutting.py",
                        "tests/db/test_product_authz_other_profiles.py",
                    ]
                )
        _validate_test_observations(
            observations.connections, cluster, database, config.expected_test_nodes
        )
    finally:
        os.chdir(previous_directory)
        sys.path[:] = original_path
        for name, value in previous_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _migration_url(admin_dsn: str, database: str, owner: str, password: str) -> str:
    """管理接続の到達先で所有者として移行する SQLAlchemy URL を作る。"""
    parsed = _split_dsn(admin_dsn)
    host_and_port = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    owner_authority = f"{quote(owner, safe='')}:{quote(password, safe='')}@{host_and_port}"
    return urlunsplit(
        parsed._replace(
            scheme="postgresql+psycopg",
            netloc=owner_authority,
            path=f"/{quote(database, safe='')}",
        )
    )


def _role_from_asset(path: Path) -> str:
    """DDL 資産の ELEMENT-ID をロール名として読む。"""
    matches = ROLE_ID_PATTERN.findall(path.read_text(encoding="utf-8"))
    if len(matches) != 1 or matches[0] != path.stem:
        raise RunnerError("DDL のロール識別子が不正")
    return matches[0]


def _temporary_role(path: Path, constant: str) -> str:
    """越境テストの文字列定数から一時ロール名を読む。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == constant for target in node.targets)
    ]
    if len(values) != 1 or not isinstance(values[0], ast.Constant):
        raise RunnerError("越境テストの一時ロール名を判定できない")
    value = values[0].value
    if not isinstance(value, str) or not value:
        raise RunnerError("越境テストの一時ロール名が不正")
    return value


def _roles(config: TargetsConfig, tested_user: str) -> RoleNames:
    """3 経路からロール名を集め、重複と取り違えを拒否する。"""
    owner = _role_from_asset(config.owner_role_asset)
    assets = sorted(config.role_assets_dir.glob("*.sql"))
    if not assets or config.owner_role_asset not in assets:
        raise RunnerError("所有者ロール資産を判定できない")
    privileges = tuple(
        _role_from_asset(asset) for asset in assets if asset != config.owner_role_asset
    )
    temporary = _temporary_role(config.temporary_role_source, config.temporary_role_constant)
    names = (owner, *privileges, tested_user, temporary)
    if len(names) != len(set(names)):
        raise RunnerError("撤去対象のロール名が重複している")
    for name in names:
        _quote_identifier(name)
    return RoleNames(owner, privileges, tested_user, temporary)


def _quote_identifier(name: str) -> str:
    """PostgreSQL の識別子を切り詰めなく引用する。"""
    if not name or "\x00" in name or len(name.encode("utf-8")) > 63:
        raise RunnerError("対象の識別子が不正")
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    """生成したロール用パスワードを SQL リテラルへ変換する。"""
    return "'" + value.replace("'", "''") + "'"


def _command(
    arguments: list[str], *, cwd: Path = REPOSITORY_ROOT, env: Mapping[str, str] | None = None
) -> str:
    """外部コマンドを実行し、失敗時の出力に接続情報を含めない。"""
    try:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            env=None if env is None else dict(env),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RunnerError("外部コマンドを実行できない") from error
    if result.returncode != 0:
        raise RunnerError("外部コマンドが失敗した")
    return result.stdout.strip()


def _compose_args(config: TargetsConfig) -> list[str]:
    """`.env` を読まずに固定の Compose プロジェクトと定義を使う。"""
    return [
        "docker",
        "compose",
        "-p",
        config.compose_project,
        "-f",
        str(REPOSITORY_ROOT / "docker-compose.yml"),
        "--env-file",
        "/dev/null",
        "--profile",
        "product-rls",
    ]


def _container_id(config: TargetsConfig, service: str) -> str:
    """compose サービスの稼働中コンテナを一意に特定する。"""
    output = _command([*_compose_args(config), "ps", "--status", "running", "-q", service])
    ids = output.splitlines()
    if len(ids) != 1 or not ids[0]:
        raise RunnerError("compose サービスの実コンテナを一意に特定できない")
    return ids[0]


def _check_product_volume(config: TargetsConfig, container_id: str) -> None:
    """実コンテナの PGDATA が専用の名前付きボリュームか確かめる。"""
    compose = json.loads(_command([*_compose_args(config), "config", "--format", "json"]))
    try:
        volume_name = compose["volumes"][config.compose_volume]["name"]
        mounts = json.loads(
            _command(["docker", "inspect", "--format", "{{json .Mounts}}", container_id])
        )
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RunnerError("専用ボリュームを判定できない") from error
    if not any(
        mount.get("Type") == "volume"
        and mount.get("Name") == volume_name
        and mount.get("Destination") == "/var/lib/postgresql/data"
        for mount in mounts
    ):
        raise RunnerError("実コンテナの PGDATA が専用ボリュームではない")


def _container_cluster(config: TargetsConfig, service: str) -> str:
    """compose の実コンテナ内でクラスタ識別値を独立に読む。"""
    container_id = _container_id(config, service)
    if service == config.compose_service:
        _check_product_volume(config, container_id)
    identifier = _command(["docker", "exec", container_id, "sh", "-c", CONTAINER_CONTROL_QUERY])
    if not identifier.isdecimal():
        raise RunnerError("コンテナのクラスタ識別値を判定できない")
    return identifier


def _driver() -> Any:
    """backend 側環境の psycopg を実行時だけ読み込む。"""
    try:
        return cast(Any, importlib.import_module("psycopg"))
    except ImportError as error:
        raise RunnerError("backend 側の psycopg が利用できない") from error


def _fetch_one(connection: Any, statement: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    """管理接続から 1 行を読み、欠落時に中止する。"""
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        row = cursor.fetchone()
    if row is None:
        raise RunnerError("データベースから判定値を取得できない")
    return tuple(row)


def _execute(connection: Any, statement: str) -> None:
    """自動コミットの管理接続で SQL を 1 文だけ実行する。"""
    with connection.cursor() as cursor:
        cursor.execute(statement)


def _evidence(
    config: TargetsConfig,
    connection: Any,
    approved_database: str,
    test_role_database: str,
    initial_database: str,
    operand_database: str,
    *,
    with_connections: bool = False,
) -> tuple[TargetEvidence, int | None]:
    """TCP と 2 実コンテナを読み、必要なら接続数も同じ SQL で読む。"""
    deployed = _container_cluster(config, config.compose_service)
    shared = _container_cluster(config, config.shared_compose_service)
    query = CONTROL_QUERY
    params: tuple[Any, ...] = ()
    if with_connections:
        query += (
            ", (SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid())"
        )
        params = (approved_database,)
    row = _fetch_one(connection, query, params)
    identifier = None if row[0] is None else str(row[0])
    evidence = TargetEvidence(
        connected_cluster=identifier,
        deployed_cluster=deployed,
        shared_cluster=shared,
        operand_database=operand_database,
        approved_database=approved_database,
        test_role_database=test_role_database,
        connected_database=row[1],
        initial_database=initial_database,
        admin_user=row[2],
        admin_is_superuser=row[3],
    )
    count = None if not with_connections or row[4] is None else int(row[4])
    return evidence, count


def _checked_admin_sql(
    config: TargetsConfig,
    connection: Any,
    approved_database: str,
    test_role_database: str,
    initial_database: str,
    statement: str,
    *,
    database_operand: str | None = None,
    role_operand: str | None = None,
    allowed_roles: frozenset[str] = frozenset(),
) -> None:
    """各管理操作の直前にクラスタ実体とオペランドを照合する。"""
    operand = approved_database if database_operand is None else database_operand
    evidence, _ = _evidence(
        config, connection, approved_database, test_role_database, initial_database, operand
    )
    validate_target(evidence)
    if role_operand is not None and role_operand not in allowed_roles:
        raise RunnerError("操作するロール名が許可集合に無い")
    _execute(connection, statement)


def _role_exists(connection: Any, role: str) -> bool:
    """ロールが存在するかだけを調べる。"""
    return bool(
        _fetch_one(
            connection, "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = %s)", (role,)
        )[0]
    )


def _target_digest(cluster: str, database: str) -> str:
    """クラスタと対象名を含む一方向の対象要約値を返す。"""
    return hashlib.sha256(f"{cluster}\0{database}".encode("utf-8")).hexdigest()


def _assert_target_connection(
    config: TargetsConfig, connection: Any, cluster: str, database: str
) -> None:
    """移行に使う対象 DB 接続のクラスタと接続中 DB 名を照合する。"""
    deployed = _container_cluster(config, config.compose_service)
    shared = _container_cluster(config, config.shared_compose_service)
    row = _fetch_one(
        connection,
        "SELECT (SELECT system_identifier FROM pg_control_system()), current_database()",
    )
    if (
        row[0] is None
        or str(row[0]) != cluster
        or str(row[0]) != deployed
        or str(row[0]) == shared
        or row[1] != database
    ):
        raise RunnerError("移行の対象接続が確認済みのクラスタ・データベースと不一致")


def _prepare_target() -> PreparedTarget:
    """運用正本 2-2 の手順 1〜4 を先頭から一度だけ実行する。"""
    config = _load_targets()
    admin_dsn = _required_environment(config.admin_dsn_env)
    approved_database = _required_environment(config.target_db_env)
    test_role_dsn = _required_environment(config.test_role_dsn_env)
    initial_database = _required_environment(config.initial_db_env)
    _quote_identifier(approved_database)
    tested_user, test_role_database = _dsn_user_and_database(test_role_dsn)
    roles = _roles(config, tested_user)
    _split_dsn(admin_dsn)
    driver = _driver()
    with driver.connect(admin_dsn, autocommit=True) as admin:
        initial, _ = _evidence(
            config,
            admin,
            approved_database,
            test_role_database,
            initial_database,
            approved_database,
        )
        validate_target(initial)
        if initial.admin_user in roles.ordered:
            raise RunnerError("管理者ロールが撤去対象に含まれている")
        if initial.connected_cluster is None:
            raise RunnerError("クラスタ識別値を判定できない")
        cluster = initial.connected_cluster
        generation = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + secrets.token_hex(8)
        )
        digest = _target_digest(cluster, approved_database)
        allowed_roles = frozenset(roles.ordered)

        # 接続数とクラスタ実体を同じ読み取りで確かめ、直後に最初の DROP を打つ。
        before_drop, other_connections = _evidence(
            config,
            admin,
            approved_database,
            test_role_database,
            initial_database,
            approved_database,
            with_connections=True,
        )
        if before_drop.connected_cluster != cluster:
            raise RunnerError("確認後にクラスタ実体が変わった")
        guard_drop(
            before_drop,
            other_connections,
            lambda: _execute(
                admin, f"DROP DATABASE IF EXISTS {_quote_identifier(approved_database)}"
            ),
        )

        for role in roles.ordered:
            if _role_exists(admin, role):
                _checked_admin_sql(
                    config,
                    admin,
                    approved_database,
                    test_role_database,
                    initial_database,
                    f"DROP OWNED BY {_quote_identifier(role)}",
                    role_operand=role,
                    allowed_roles=allowed_roles,
                )
            _checked_admin_sql(
                config,
                admin,
                approved_database,
                test_role_database,
                initial_database,
                f"DROP ROLE IF EXISTS {_quote_identifier(role)}",
                role_operand=role,
                allowed_roles=allowed_roles,
            )

        owner_password = secrets.token_urlsafe(24)
        _checked_admin_sql(
            config,
            admin,
            approved_database,
            test_role_database,
            initial_database,
            f"CREATE ROLE {_quote_identifier(roles.owner)} WITH "
            "NOSUPERUSER NOBYPASSRLS LOGIN NOCREATEROLE NOCREATEDB "
            f"NOREPLICATION NOINHERIT PASSWORD {_quote_literal(owner_password)}",
            role_operand=roles.owner,
            allowed_roles=allowed_roles,
        )
        _checked_admin_sql(
            config,
            admin,
            approved_database,
            test_role_database,
            initial_database,
            f"CREATE DATABASE {_quote_identifier(approved_database)} "
            f"OWNER {_quote_identifier(roles.owner)}",
            database_operand=approved_database,
            role_operand=roles.owner,
            allowed_roles=allowed_roles,
        )

    migration_url = _migration_url(admin_dsn, approved_database, roles.owner, owner_password)
    owner_dsn = migration_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with driver.connect(owner_dsn) as target:
        _assert_target_connection(config, target, cluster, approved_database)

    migration_env = dict(os.environ)
    migration_env["PITCHLOG_MIGRATION_DATABASE_URL"] = migration_url
    _command(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPOSITORY_ROOT / "backend",
        env=migration_env,
    )
    target_dsn = _database_dsn(admin_dsn, approved_database)
    with driver.connect(target_dsn) as target:
        _assert_target_connection(config, target, cluster, approved_database)
        with target.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            revisions = cursor.fetchall()
    if len(revisions) != 1 or not isinstance(revisions[0][0], str):
        raise RunnerError("migration head を一意に判定できない")
    return PreparedTarget(
        generation_id=generation,
        target_digest=digest,
        migration_head=revisions[0][0],
        owner_dsn=owner_dsn,
    )


def main(run: Callable[[], PreparedTarget] | None = None) -> int:
    """準備と試験接続先の照合を実行し、接続情報を表示しない。

    Args:
        run: 単体試験で準備処理を差し替えるための関数。

    Returns:
        接続先の照合成功時 0、判定不能・不一致・実行失敗時 1。
        試験本体の合否はこの段階の終了コードへ反映しない。
    """
    try:
        prepared = (run or _prepare_target)()
        config = _load_targets()
        _run_product_tests(
            config,
            _required_environment(config.admin_dsn_env),
            prepared.owner_dsn,
            _required_environment(config.test_role_dsn_env),
            _required_environment(config.target_db_env),
            prepared.target_digest,
        )
    except RunnerError as error:
        print(f"製品 RLS 対象準備を中止: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("製品 RLS 対象準備を中止: 予期しない実行失敗", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "generation_id": prepared.generation_id,
                "target_digest": prepared.target_digest,
                "migration_head": prepared.migration_head,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
