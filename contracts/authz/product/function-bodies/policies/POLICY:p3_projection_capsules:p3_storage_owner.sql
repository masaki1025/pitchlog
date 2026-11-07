-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:p3_projection_capsules:p3_storage_owner

CREATE POLICY p3_storage_owner ON sync_fence.p3_projection_capsules FOR ALL TO pitchlog_owner USING (true) WITH CHECK (true);
