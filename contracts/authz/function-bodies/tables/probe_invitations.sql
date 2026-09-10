-- ELEMENT-TYPE: table
-- ELEMENT-ID: probe_invitations

-- TYPE-DESIGN: group_id と invited_tenant_id は決定的な probe 値を扱える BIGINT とする。
-- TYPE-DESIGN: status は列挙値が資産にないため、DB enum を新設せず TEXT とする。
CREATE TABLE probe_data.probe_invitations (
    group_id BIGINT NOT NULL,
    invited_tenant_id BIGINT NOT NULL,
    status TEXT NOT NULL
);

ALTER TABLE probe_data.probe_invitations OWNER TO table_owner;
ALTER TABLE probe_data.probe_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_data.probe_invitations FORCE ROW LEVEL SECURITY;
