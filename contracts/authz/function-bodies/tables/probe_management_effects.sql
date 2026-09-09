-- ELEMENT-TYPE: table
-- ELEMENT-ID: probe_management_effects

-- TYPE-DESIGN: group_id と tenant_id は probe fixture で決定的な値を扱える BIGINT とする。
-- TYPE-DESIGN: effect_kind は列挙値が資産にないため TEXT とする。
CREATE TABLE probe_data.probe_management_effects (
    group_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    effect_kind TEXT NOT NULL
);

ALTER TABLE probe_data.probe_management_effects OWNER TO table_owner;
ALTER TABLE probe_data.probe_management_effects ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_data.probe_management_effects FORCE ROW LEVEL SECURITY;
