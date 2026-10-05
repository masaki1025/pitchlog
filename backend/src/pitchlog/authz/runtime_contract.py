"""テナント境界のランタイム認可契約を提供する生成モジュール。"""

from dataclasses import dataclass

SCHEMA_VERSION = 1
RUNTIME_CONTRACT_REVISION = 9
PROVISIONAL = False
SUPERSEDED_BY = None
SOURCE_ASSET = "contracts/tenant_boundary/runtime-authz-contract.json"
SOURCE_DIGEST = "c849cdbaf77b9f60e8073dd563e2be31698ab497d6c8764484ee5dffddc9559d"
DERIVED_FROM = "contracts/authz/product/ddl-elements.json"


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

PROTECTED_SCHEMAS = ("authn", "authn_crypto", "authz_private", "public")
PROTECTED_TABLES = (
    ("public", "admin_credentials"),
    ("public", "admin_operation_logs"),
    ("public", "admin_sessions"),
    ("public", "admin_vocabularies"),
    ("public", "analysis_groups"),
    ("public", "evacuated_event_originals"),
    ("public", "event_slots"),
    ("public", "game_lineups"),
    ("public", "game_type_rule_defaults"),
    ("public", "games"),
    ("public", "group_invitations"),
    ("public", "group_memberships"),
    ("public", "idempotency_ledger"),
    ("public", "invalidation_intents"),
    ("public", "lineup_memories"),
    ("public", "medical_note_versions"),
    ("public", "medical_notes"),
    ("public", "migrated_final_lineups"),
    ("public", "migration_quarantine"),
    ("public", "migration_resolution_reports"),
    ("public", "migration_runs"),
    ("public", "migration_warning_reports"),
    ("public", "operation_events"),
    ("public", "participation_intervals"),
    ("public", "pdf_export_records"),
    ("public", "play_rows"),
    ("public", "play_runners"),
    ("public", "player_merge_events"),
    ("public", "player_move_records"),
    ("public", "players"),
    ("public", "rate_limit_counters"),
    ("public", "recording_generations"),
    ("public", "rejected_event_originals"),
    ("public", "rule_sets"),
    ("public", "sharing_grants"),
    ("public", "system_settings"),
    ("public", "system_vocabularies"),
    ("public", "team_records"),
    ("public", "temporary_player_id_mappings"),
    ("public", "tenant_auth_subjects"),
    ("public", "tenant_credentials"),
    ("public", "tenant_tokens"),
    ("public", "tenant_vocabularies"),
    ("public", "tenants"),
    ("public", "tournament_rule_assignments"),
)
PROTECTED_FUNCTIONS = (
    ("authn", "change_password", "uuid, text, text"),
    ("authn", "issue_initial_password", "uuid, text"),
    ("authn", "login", "text, text"),
    ("authn", "logout", "uuid"),
    ("authn", "password_policy_ok", "text"),
    ("authn", "record_admin_login_failure", "text"),
    ("authn", "record_failure", "text, bigint, bigint, bigint, boolean"),
    ("authn", "reset_password", "uuid, text"),
    ("authn", "revoke_tenant_tokens", "uuid"),
    ("authn", "setting_positive_integer", "text"),
    ("authn", "verify_token", "uuid"),
    ("authz_private", "tenant_has_effective_membership", "uuid, boolean"),
    ("public", "authn_normalize_team_name", "text"),
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
    ("public", "prevent_invalidation_intents_target_update", ""),
    ("public", "prevent_medical_note_versions_content_update", ""),
    ("public", "prevent_medical_notes_identity_update", ""),
    ("public", "prevent_migrated_final_lineups_source_update", ""),
    ("public", "prevent_migration_quarantine_mutation", ""),
    ("public", "prevent_migration_resolution_reports_mutation", ""),
    ("public", "prevent_migration_runs_source_update", ""),
    ("public", "prevent_migration_warning_reports_mutation", ""),
    ("public", "prevent_operation_events_content_update", ""),
    ("public", "prevent_pdf_export_records_mutation", ""),
    ("public", "prevent_play_rows_projection_identity_update", ""),
    ("public", "prevent_player_merge_events_content_update", ""),
    ("public", "prevent_player_move_records_mutation", ""),
    ("public", "prevent_players_identity_update", ""),
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
