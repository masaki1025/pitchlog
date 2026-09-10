-- ELEMENT-TYPE: table
-- ELEMENT-ID: probe_grants

-- TYPE-DESIGN: group_id と tenant_id は probe fixture で決定的な値を扱える BIGINT とする。
-- TYPE-DESIGN: grant_kind は列挙値が資産にないため TEXT とする。
-- TYPE-DESIGN: enabled は二値の認可状態を表すため BOOLEAN とする。
CREATE TABLE probe_data.probe_grants (
    group_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    grant_kind TEXT NOT NULL,
    enabled BOOLEAN NOT NULL
);

ALTER TABLE probe_data.probe_grants OWNER TO table_owner;
ALTER TABLE probe_data.probe_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_data.probe_grants FORCE ROW LEVEL SECURITY;
