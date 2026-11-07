-- ELEMENT-TYPE: table
-- ELEMENT-ID: stats_fact_versions

ALTER TABLE sync_fence.stats_fact_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.stats_fact_versions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.stats_fact_versions FROM PUBLIC,pitchlog_app;
