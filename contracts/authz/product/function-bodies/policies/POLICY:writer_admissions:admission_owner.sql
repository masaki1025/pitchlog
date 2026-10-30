-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:writer_admissions:admission_owner

CREATE POLICY admission_owner ON sync_fence.writer_admissions FOR ALL TO pitchlog_sync_binding_fn_owner USING (true) WITH CHECK (true);
