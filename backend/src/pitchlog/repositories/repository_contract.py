"""リポジトリ基底の公開面と不変戻り値規約を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 20
ASSET_KIND = "tenant_repository_contract"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/repository-contract.json"
SOURCE_DIGEST = "7107695162edb95e9fda99400f7a0b70347988908df85e987b18751d21f4952c"

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
IMMUTABLE_CONTAINER_GRAMMAR = (
    "tuple[T, ...]",
    "frozenset[T]",
    "mappingproxy[str, T]",
)
CANONICAL_TABLE = "orm_metadata_table_identity_for_registration_and_statement"
UPDATE_IDENTITY = "actual_complete_primary_key_equalities_for_all_updates"
UPDATE_BIND_NAMES = "primary_key_disjoint_from_target_columns_and_set_bindings"
TENANT_PRIMARY_KEY_BIND = "injected_context_bind_only"
ROW_LOCK = (
    "declared_plain_for_update_with_complete_primary_key_and_explicit_specialized_shape"
)
UNLOCKED_READ = "for_update_absent_when_undeclared"
SYNC_APPLY_SCOPE = "contextvar_rejects_new_tenant_transaction_scope"
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
