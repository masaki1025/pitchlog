-- ELEMENT-TYPE: policy
-- ELEMENT-ID: POLICY:attempt_retirements:attempt_retirement_owner

CREATE POLICY attempt_retirement_owner ON sync_fence.attempt_retirements FOR ALL TO pitchlog_sync_binding_fn_owner USING (true) WITH CHECK (true);
