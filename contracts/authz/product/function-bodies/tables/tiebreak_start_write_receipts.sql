-- ELEMENT-TYPE: table
-- ELEMENT-ID: tiebreak_start_write_receipts

ALTER TABLE sync_fence.tiebreak_start_write_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.tiebreak_start_write_receipts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.tiebreak_start_write_receipts FROM PUBLIC,pitchlog_app;
