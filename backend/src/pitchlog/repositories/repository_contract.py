"""リポジトリ基底の公開面と不変戻り値規約を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 18
ASSET_KIND = "tenant_repository_contract"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/repository-contract.json"
SOURCE_DIGEST = "a62ebc5af7ba6397965f39f0dbbb1bdd55ad932a2d9f6cab2d686b441b866249"

REPOSITORY_TYPE = "pitchlog.repositories.base.TenantRepositoryBase"
CONTEXT_BINDING_ENTRY = "pitchlog.repositories.base.TenantRepositoryBase.execute"
CROSS_TENANT_FUNCTION_ENTRY = "pitchlog.repositories.base.TenantRepositoryBase.execute"
OPERATION_TOKEN_TYPE = "pitchlog.repositories.tokens.TenantOperationToken"
OPERATION_RESULT_TYPE = "pitchlog.repositories.tokens.TenantOperationResult"
CROSS_TENANT_FUNCTION_REGISTRY_SYMBOL = (
    "pitchlog.repositories.base.CROSS_TENANT_FUNCTION_REGISTRY"
)
TRANSACTION_SCOPE_ENTRY = "pitchlog.repositories.transaction.tenant_transaction_scope"
FUNCTION_REGISTRATION_TYPE = (
    "pitchlog.repositories.function_operations.FunctionOperationRegistration"
)
FUNCTION_TRANSACTION_ENTRY = (
    "pitchlog.repositories.transaction._TenantTransaction.run_function"
)
FUNCTION_OPERATION_REGISTRY = (
    "pitchlog.repositories.operation_registry.PRODUCT_FUNCTION_OPERATIONS"
)
FUNCTION_EXECUTOR_SYMBOL = FUNCTION_TRANSACTION_ENTRY
FUNCTION_EXECUTOR_SIGNATURE = (
    "run_function(self, operation: TenantOperationToken) -> TenantOperationResult"
)
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
IMMUTABLE_CONTAINER_GRAMMAR = (
    "tuple[T, ...]",
    "frozenset[T]",
    "mappingproxy[str, T]",
)
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

PRODUCT_CAPABILITY_IDS: tuple[str, ...] = (
    "CAP:players:read",
    "CAP:players:insert",
    "CAP:players:update",
    "CAP:team_records:read",
    "CAP:team_records:insert",
    "CAP:team_records:update",
    "CAP:games:read",
    "CAP:invalidation_intents:insert",
    "CAP:lineup_memories:read",
    "CAP:lineup_memories:insert",
    "CAP:lineup_memories:update",
)
PRODUCT_OPERATION_TOKEN_TYPES: tuple[str, ...] = (
    "pitchlog.repositories.roster.PlayerReadToken",
    "pitchlog.repositories.roster.PlayerCreateToken",
    "pitchlog.repositories.roster.PlayerUpdateToken",
    "pitchlog.repositories.roster.PlayerRosterStatusUpdateToken",
    "pitchlog.repositories.roster.PlayerRosterLabelUpdateToken",
    "pitchlog.repositories.roster.TeamRecordReadToken",
    "pitchlog.repositories.roster.TeamRecordCreateToken",
    "pitchlog.repositories.roster.TeamRecordUpdateToken",
    "pitchlog.repositories.roster.TeamRecordDeleteToken",
    "pitchlog.repositories.roster.GameTeamLinkReadToken",
    "pitchlog.repositories.invalidation_intents.InvalidationIntentInsertToken",
    "pitchlog.repositories.lineup_memory._SelfTeamLockToken",
    "pitchlog.repositories.lineup_memory._ActiveLineupPlayerLockToken",
    "pitchlog.repositories.lineup_memory.LineupMemoryReadToken",
    "pitchlog.repositories.lineup_memory._LineupMemoryInsertToken",
    "pitchlog.repositories.lineup_memory._LineupMemoryUpdateToken",
)
CROSS_TENANT_FUNCTIONS: tuple[str, ...] = ()
PRODUCT_FUNCTION_OPERATION_IDS: tuple[str, ...] = ()
