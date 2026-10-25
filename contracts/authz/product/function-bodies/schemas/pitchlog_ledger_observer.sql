-- ELEMENT-TYPE: schema
-- ELEMENT-ID: pitchlog_ledger_observer

CREATE SCHEMA pitchlog_ledger_observer AUTHORIZATION pitchlog_ledger_identity_owner;
REVOKE ALL PRIVILEGES ON SCHEMA pitchlog_ledger_observer FROM PUBLIC;
GRANT USAGE ON SCHEMA pitchlog_ledger_observer TO pitchlog_ledger_identity_probe;
