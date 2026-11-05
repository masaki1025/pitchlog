-- ELEMENT-TYPE: table
-- ELEMENT-ID: stats_primitive_facts

ALTER TABLE sync_fence.stats_primitive_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.stats_primitive_facts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.stats_primitive_facts FROM PUBLIC,pitchlog_app;
