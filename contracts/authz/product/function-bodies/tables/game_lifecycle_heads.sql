-- ELEMENT-TYPE: table
-- ELEMENT-ID: game_lifecycle_heads

ALTER TABLE sync_fence.game_lifecycle_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_fence.game_lifecycle_heads FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sync_fence.game_lifecycle_heads FROM PUBLIC,pitchlog_app;
