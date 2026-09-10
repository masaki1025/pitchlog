-- ELEMENT-TYPE: column_acl_expectation
-- ELEMENT-ID: COLUMN-ACL:ALL-PROBE-TABLES:NO-EXPLICIT-GRANTS

-- expected_entries が空なので、全対象ロールの明示的な列 ACL を除去する。
REVOKE ALL PRIVILEGES (tenant_id, resource_kind, ownership_kind, payload)
    ON TABLE probe_data.probe_business_rows
    FROM provisioner, table_owner, app_role, shared_fn_owner,
        management_fn_owner, outsider_role, management_caller;

REVOKE ALL PRIVILEGES (group_id, status)
    ON TABLE probe_data.probe_groups
    FROM provisioner, table_owner, app_role, shared_fn_owner,
        management_fn_owner, outsider_role, management_caller;

REVOKE ALL PRIVILEGES (group_id, tenant_id, status, group_role)
    ON TABLE probe_data.probe_memberships
    FROM provisioner, table_owner, app_role, shared_fn_owner,
        management_fn_owner, outsider_role, management_caller;

REVOKE ALL PRIVILEGES (group_id, tenant_id, grant_kind, enabled)
    ON TABLE probe_data.probe_grants
    FROM provisioner, table_owner, app_role, shared_fn_owner,
        management_fn_owner, outsider_role, management_caller;

REVOKE ALL PRIVILEGES (group_id, invited_tenant_id, status)
    ON TABLE probe_data.probe_invitations
    FROM provisioner, table_owner, app_role, shared_fn_owner,
        management_fn_owner, outsider_role, management_caller;

REVOKE ALL PRIVILEGES (group_id, tenant_id, effect_kind)
    ON TABLE probe_data.probe_management_effects
    FROM provisioner, table_owner, app_role, shared_fn_owner,
        management_fn_owner, outsider_role, management_caller;
