-- ELEMENT-TYPE: table
-- ELEMENT-ID: probe_memberships

-- TYPE-DESIGN: group_id と tenant_id は probe fixture で決定的な値を扱える BIGINT とする。
-- TYPE-DESIGN: status と group_role は列挙値が資産にないため TEXT とする。
CREATE TABLE probe_data.probe_memberships (
    group_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    group_role TEXT NOT NULL
);

ALTER TABLE probe_data.probe_memberships OWNER TO table_owner;
ALTER TABLE probe_data.probe_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_data.probe_memberships FORCE ROW LEVEL SECURITY;
