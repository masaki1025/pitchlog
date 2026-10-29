"""リポジトリ基底の公開面と不変戻り値規約を提供する生成モジュール。"""

SCHEMA_VERSION = 1
CONTRACT_REVISION = 33
ASSET_KIND = "tenant_repository_contract"
CANONICALIZATION = "json-sort-keys-utf8-v1"
SOURCE_ASSET = "contracts/tenant_boundary/repository-contract.json"
SOURCE_DIGEST = "0fdaa85d2614de4973b6674dff8b862ad1c28f755f420d1c9543c251f8dd473d"

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
    "CAP:recording_generations:read",
    "CAP:recording_generations:update",
    "CAP:event_slots:read",
    "CAP:event_slots:insert",
    "CAP:event_slots:update",
    "CAP:operation_events:read",
    "CAP:operation_events:insert",
    "CAP:operation_events:update",
    "CAP:temporary_player_id_mappings:read",
    "CAP:temporary_player_id_mappings:insert",
    "CAP:idempotency_ledger:read",
    "CAP:idempotency_ledger:insert",
    "CAP:rejected_event_originals:read",
    "CAP:rejected_event_originals:insert",
    "CAP:invalidation_intents:read",
    "CAP:invalidation_intents:update",
    "CAP:evacuated_event_originals:read",
    "CAP:evacuated_event_originals:insert",
    "CAP:tenants:read",
    "CAP:game_lineups:read",
    "CAP:play_rows:read",
    "CAP:play_rows:insert",
    "CAP:games:insert",
    "CAP:tenant_vocabularies:insert",
    "CAP:tenant_vocabularies:read",
)
PRODUCT_OPERATION_TOKEN_TYPES: tuple[str, ...] = (
    "pitchlog.repositories.roster.PlayerReadToken",
    "pitchlog.repositories.roster.PlayerCreateToken",
    "pitchlog.repositories.roster.PlayerUpdateToken",
    "pitchlog.repositories.roster.PlayerRosterStatusUpdateToken",
    "pitchlog.repositories.roster.PlayerRosterLabelUpdateToken",
    "pitchlog.repositories.roster.TeamRecordReadToken",
    "pitchlog.repositories.roster.SelfTeamRecordReadToken",
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
    "pitchlog.sync.tokens.GameReadToken",
    "pitchlog.sync.tokens.GameLockToken",
    "pitchlog.sync.tokens.RecordingGenerationReadToken",
    "pitchlog.sync.tokens.RecordingGenerationByNumberReadToken",
    "pitchlog.sync.tokens.RecordingGenerationLockToken",
    "pitchlog.sync.tokens.RecordingPrefixUpdateToken",
    "pitchlog.sync.tokens.EventSlotReadToken",
    "pitchlog.sync.tokens.EventSlotInsertToken",
    "pitchlog.sync.tokens.EventSlotVersionUpdateToken",
    "pitchlog.sync.tokens.OperationEventReadToken",
    "pitchlog.sync.tokens.OperationEventOrderReadToken",
    "pitchlog.sync.tokens.OperationEventInsertToken",
    "pitchlog.sync.tokens.OperationEventOrderUpdateToken",
    "pitchlog.sync.tokens.OperationEventReplaceToken",
    "pitchlog.sync.tokens.TemporaryPlayerMappingReadToken",
    "pitchlog.sync.tokens.TemporaryPlayerMappingInsertToken",
    "pitchlog.sync.tokens.IdempotencyLedgerReadToken",
    "pitchlog.sync.tokens.IdempotencyLedgerInsertToken",
    "pitchlog.sync.tokens.RejectedOriginalReadToken",
    "pitchlog.sync.tokens.RejectedOriginalInsertToken",
    "pitchlog.sync.tokens.InvalidationIntentReadToken",
    "pitchlog.sync.tokens.InvalidationIntentPendingToken",
    "pitchlog.sync.tokens.SyncInvalidationIntentInsertToken",
    "pitchlog.sync.tokens.SyncSharedInvalidationIntentInsertToken",
    "pitchlog.sync.tokens.InvalidationIntentDeliveredToken",
    "pitchlog.sync.tokens.EvacuatedOriginalReadToken",
    "pitchlog.sync.tokens.EvacuatedOriginalInsertToken",
    "pitchlog.repositories.tenant_profile.TenantProfileReadToken",
    "pitchlog.repositories.games.PreparingGameListToken",
    "pitchlog.repositories.games.PreparingGameDetailToken",
    "pitchlog.repositories.started_snapshot_operations.StartedLineupsReadToken",
    "pitchlog.repositories.started_snapshot_operations.StartedEventSlotsExistenceToken",
    "pitchlog.repositories.started_snapshot_operations.StartedOperationEventsExistenceToken",
    "pitchlog.repositories.started_snapshot_operations.StartedPlayRowsExistenceToken",
    "pitchlog.sync.first_ball_tokens.FirstBallPlayRowInsertToken",
    "pitchlog.sync.first_ball_tokens.FirstBallPlayRowReadToken",
    "pitchlog.repositories.recorded_snapshot_operations.RecordedEventRowsReadToken",
    "pitchlog.repositories.recorded_snapshot_operations.RecordedEventSlotsReadToken",
    "pitchlog.repositories.recorded_snapshot_operations.RecordedPlayRowsReadToken",
    "pitchlog.repositories.preparing_game_creation.PreparingGameInsertToken",
    "pitchlog.repositories.preparing_game_creation.PreparingTournamentInsertToken",
    "pitchlog.repositories.preparing_game_creation.PreparingTournamentOptionsToken",
    "pitchlog.repositories.preparing_game_creation.PreparingTournamentNameExistsToken",
    "pitchlog.repositories.preparing_game_creation.PreparingTournamentParentToken",
    "pitchlog.repositories.preparing_game_creation.PreparingSelfTeamLockToken",
    "pitchlog.repositories.preparing_game_creation.PreparingOpponentTeamLockToken",
)
CROSS_TENANT_FUNCTIONS: tuple[str, ...] = ()
PRODUCT_FUNCTION_OPERATION_IDS: tuple[str, ...] = (
    "RG1:precheck",
    "RG1:commit_check",
    "RG1:scope_binding",
    "RULE:resolve_stage_a",
    "SYNC_FIRST_BALL:bind_device",
    "SYNC_FIRST_BALL:check_current_right",
    "SYNC_WRITER_BINDING:read_writer_identity",
    "SYNC_WRITER_BINDING:assert_writer_binding",
)
