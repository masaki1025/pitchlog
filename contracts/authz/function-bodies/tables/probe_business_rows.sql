-- ELEMENT-TYPE: table
-- ELEMENT-ID: probe_business_rows

-- TYPE-DESIGN: tenant_id は probe fixture で決定的な値を簡潔に扱える BIGINT とする。
-- TYPE-DESIGN: 分類値は列挙値が資産にないため、DB enum を新設せず TEXT とする。
-- TYPE-DESIGN: payload は構造化した業務値を型付きで保持できる JSONB とする。
CREATE TABLE probe_data.probe_business_rows (
    tenant_id BIGINT NOT NULL,
    resource_kind TEXT NOT NULL,
    ownership_kind TEXT NOT NULL,
    payload JSONB NOT NULL
);

ALTER TABLE probe_data.probe_business_rows OWNER TO table_owner;
ALTER TABLE probe_data.probe_business_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_data.probe_business_rows FORCE ROW LEVEL SECURITY;
