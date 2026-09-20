"""テナント境界のランタイム認可契約を提供する生成モジュール。"""

from dataclasses import dataclass

SCHEMA_VERSION = 1
RUNTIME_CONTRACT_REVISION = 1
PROVISIONAL = True
SUPERSEDED_BY = "contracts/authz/product/ddl-elements.json"
SOURCE_ASSET = "contracts/tenant_boundary/runtime-authz-contract.json"
SOURCE_DIGEST = "c62b191c12757b390c47e7914a2ab653093f6d03d9daa389a3d42f9ee511057a"


@dataclass(frozen=True, slots=True)
class ApplicationRoleAttributes:
    """PostgreSQL アプリ用ロールの期待属性を保持する。"""

    rolsuper: bool
    rolbypassrls: bool
    rolcanlogin: bool
    rolcreaterole: bool
    rolcreatedb: bool
    rolreplication: bool
    rolinherit: bool


APPLICATION_ROLE_NAME = "pitchlog_app"
APPLICATION_ROLE_ATTRIBUTES = ApplicationRoleAttributes(
    rolsuper=False,
    rolbypassrls=False,
    rolcanlogin=True,
    rolcreaterole=False,
    rolcreatedb=False,
    rolreplication=False,
    rolinherit=False,
)

PROTECTED_SCHEMAS = ("public",)
PROTECTED_TABLES = (
    ("public", "tenants"),
    ("public", "team_records"),
    ("public", "players"),
    ("public", "games"),
    ("public", "lineup_memories"),
    ("public", "game_lineups"),
    ("public", "participation_intervals"),
    ("public", "rule_sets"),
    ("public", "game_type_rule_defaults"),
    ("public", "tournament_rule_assignments"),
    ("public", "event_slots"),
    ("public", "operation_events"),
    ("public", "play_rows"),
    ("public", "play_runners"),
    ("public", "temporary_player_id_mappings"),
    ("public", "idempotency_ledger"),
    ("public", "rejected_event_originals"),
    ("public", "evacuated_event_originals"),
    ("public", "recording_generations"),
    ("public", "medical_notes"),
    ("public", "medical_note_versions"),
    ("public", "pdf_export_records"),
    ("public", "system_vocabularies"),
    ("public", "admin_vocabularies"),
    ("public", "tenant_vocabularies"),
    ("public", "system_settings"),
    ("public", "tenant_auth_subjects"),
    ("public", "tenant_credentials"),
    ("public", "admin_credentials"),
    ("public", "admin_sessions"),
    ("public", "tenant_tokens"),
    ("public", "admin_operation_logs"),
    ("public", "player_merge_events"),
    ("public", "player_move_records"),
    ("public", "rate_limit_counters"),
    ("public", "analysis_groups"),
    ("public", "group_memberships"),
    ("public", "sharing_grants"),
    ("public", "group_invitations"),
    ("public", "invalidation_intents"),
    ("public", "migration_quarantine"),
    ("public", "migrated_final_lineups"),
    ("public", "migration_runs"),
    ("public", "migration_resolution_reports"),
    ("public", "migration_warning_reports"),
)
PROTECTED_FUNCTIONS = (
    ("public", "prevent_admin_credentials_id_update", ""),
    ("public", "prevent_admin_operation_logs_mutation", ""),
    ("public", "prevent_admin_sessions_identity_update", ""),
    ("public", "prevent_admin_vocabularies_identity_update", ""),
    ("public", "prevent_analysis_groups_id_update", ""),
    ("public", "prevent_evacuated_event_originals_identity_update", ""),
    ("public", "prevent_event_slots_key_update", ""),
    ("public", "prevent_game_lineups_entries_update", ""),
    ("public", "prevent_group_invitations_identity_update", ""),
    ("public", "prevent_group_memberships_identity_update", ""),
    ("public", "prevent_idempotency_ledger_result_update", ""),
    ("public", "prevent_medical_note_versions_content_update", ""),
    ("public", "prevent_medical_notes_identity_update", ""),
    ("public", "prevent_migration_resolution_reports_mutation", ""),
    ("public", "prevent_migration_runs_source_update", ""),
    ("public", "prevent_migration_warning_reports_mutation", ""),
    ("public", "prevent_operation_events_content_update", ""),
    ("public", "prevent_pdf_export_records_mutation", ""),
    ("public", "prevent_play_rows_projection_identity_update", ""),
    ("public", "prevent_player_merge_events_content_update", ""),
    ("public", "prevent_player_move_records_mutation", ""),
    ("public", "prevent_rate_limit_counters_identity_update", ""),
    ("public", "prevent_rejected_event_originals_content_update", ""),
    ("public", "prevent_sharing_grants_membership_update", ""),
    ("public", "prevent_system_settings_key_update", ""),
    ("public", "prevent_system_vocabularies_update", ""),
    ("public", "prevent_team_records_kind_update", ""),
    ("public", "prevent_temporary_player_id_mappings_identity_update", ""),
    ("public", "prevent_tenant_auth_subjects_update", ""),
    ("public", "prevent_tenant_credentials_subject_update", ""),
    ("public", "prevent_tenant_tokens_identity_update", ""),
    ("public", "prevent_tenant_vocabularies_identity_update", ""),
    ("public", "protect_recording_generations_updates", ""),
)

DANGEROUS_ENDPOINT_FIXTURES = (
    ("superuser", "DANGER_SUPERUSER"),
    ("bypassrls", "DANGER_BYPASSRLS"),
    ("schema_owner", "DANGER_SCHEMA_OWNER"),
    ("table_owner", "DANGER_TABLE_OWNER"),
    ("function_owner", "DANGER_FUNCTION_OWNER"),
)
