-- ELEMENT-TYPE: table
-- ELEMENT-ID: substitution_write_receipts

ALTER TABLE sync_fence.substitution_write_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.substitution_write_receipts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.substitution_write_receipts FROM PUBLIC,pitchlog_app;
