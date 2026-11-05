-- ELEMENT-TYPE: table
-- ELEMENT-ID: stats_primitive_sources

ALTER TABLE sync_fence.stats_primitive_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.stats_primitive_sources FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.stats_primitive_sources FROM PUBLIC,pitchlog_app;
