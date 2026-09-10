-- ELEMENT-TYPE: table
-- ELEMENT-ID: probe_groups

-- TYPE-DESIGN: group_id は probe fixture で決定的な値を簡潔に扱える BIGINT とする。
-- TYPE-DESIGN: status は列挙値が資産にないため、DB enum を新設せず TEXT とする。
CREATE TABLE probe_data.probe_groups (
    group_id BIGINT NOT NULL,
    status TEXT NOT NULL
);

ALTER TABLE probe_data.probe_groups OWNER TO table_owner;
ALTER TABLE probe_data.probe_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE probe_data.probe_groups FORCE ROW LEVEL SECURITY;
