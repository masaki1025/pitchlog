-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:writer_bindings:binding_owner

CREATE POLICY binding_owner ON sync_fence.writer_bindings FOR ALL TO pitchlog_sync_binding_fn_owner USING (true) WITH CHECK (true);
