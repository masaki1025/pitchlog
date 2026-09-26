"""リポジトリ基底の公開面と不変戻り値規約を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 6
ASSET_KIND = "tenant_repository_contract"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/repository-contract.json"
SOURCE_DIGEST = "db918963f8ccef259c278947a978a419c98f80141780760dd69571caed5e70eb"

REPOSITORY_TYPE = "pitchlog.repositories.base.TenantRepositoryBase"
CONTEXT_BINDING_ENTRY = "pitchlog.repositories.base.TenantRepositoryBase.execute"
CROSS_TENANT_FUNCTION_ENTRY = "pitchlog.repositories.base.TenantRepositoryBase.execute"
OPERATION_TOKEN_TYPE = "pitchlog.repositories.tokens.TenantOperationToken"
OPERATION_RESULT_TYPE = "pitchlog.repositories.tokens.TenantOperationResult"
CROSS_TENANT_FUNCTION_REGISTRY_SYMBOL = (
    "pitchlog.repositories.base.CROSS_TENANT_FUNCTION_REGISTRY"
)
TRANSACTION_SCOPE_ENTRY = "pitchlog.repositories.transaction.tenant_transaction_scope"
EXECUTOR_SYMBOL = "pitchlog.repositories.base.TenantRepositoryBase._execute_operation"
EXECUTOR_SIGNATURE = (
    "_execute_operation(self, context: TenantContext, "
    "operation: TenantOperationToken) -> TenantOperationResult"
)

ALLOWED_DTOS = ("pitchlog.repositories.tokens.TenantOperationResult",)
SCALAR_TYPE_MATCH = "exact"
CONTAINER_TYPE_MATCH = "exact"
IMMUTABLE_SCALAR_TYPES = (
    "builtins.NoneType",
    "builtins.bool",
    "builtins.int",
    "builtins.float",
    "builtins.str",
    "builtins.bytes",
    "uuid.UUID",
    "decimal.Decimal",
    "datetime.date",
    "datetime.datetime",
    "datetime.time",
)
IMMUTABLE_CONTAINER_GRAMMAR = ("tuple[T, ...]", "frozenset[T]")
FORBIDDEN_TYPES = (
    "typing.Any",
    "builtins.object",
    "collections.abc.Callable",
    "collections.abc.Iterator",
    "collections.abc.Generator",
    "sqlalchemy.engine.Result",
    "sqlalchemy.engine.ScalarResult",
    "sqlalchemy.orm.Query",
    "sqlalchemy.orm.DeclarativeBase",
    "sqlalchemy.sql.Executable",
    "sqlalchemy.sql.Select",
    "sqlalchemy.sql.schema.Table",
    "non_frozen_dataclass",
)

PRODUCT_CAPABILITY_IDS: tuple[str, ...] = ()
PRODUCT_OPERATION_TOKEN_TYPES: tuple[str, ...] = ()
CROSS_TENANT_FUNCTIONS: tuple[str, ...] = ()
