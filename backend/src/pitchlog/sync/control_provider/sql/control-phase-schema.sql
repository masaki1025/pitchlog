-- F2制御9表の構造候補。別PG専用。role/固定保存器/正式受理は未提供。

CREATE SCHEMA sync_control;

REVOKE ALL ON SCHEMA sync_control FROM PUBLIC;

CREATE TABLE sync_control.authorities (
	authority_id UUID NOT NULL,
	control_instance UUID NOT NULL,
	business_instance UUID NOT NULL,
	restore_epoch UUID NOT NULL,
	control_version BIGINT NOT NULL,
	state TEXT NOT NULL,
	CONSTRAINT pk_authorities PRIMARY KEY (authority_id),
	CONSTRAINT uq_authorities_0 UNIQUE (business_instance, restore_epoch),
	CONSTRAINT ck_authorities_0 CHECK (control_version > 0),
	CONSTRAINT ck_authorities_1 CHECK (state IN ('closed', 'active'))
);

CREATE UNIQUE INDEX ix_sync_one_active_authority ON sync_control.authorities (business_instance) WHERE state = 'active';

ALTER TABLE sync_control.authorities ENABLE ROW LEVEL SECURITY;

ALTER TABLE sync_control.authorities FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE sync_control.authorities FROM PUBLIC;

CREATE TABLE sync_control.attempts (
	tenant_id UUID NOT NULL,
	attempt_id UUID NOT NULL,
	device_id UUID NOT NULL,
	game_id UUID NOT NULL,
	authority_id UUID NOT NULL,
	wire_d4 TEXT NOT NULL,
	internal_generation BIGINT NOT NULL,
	codec_version BIGINT NOT NULL,
	request_fingerprint TEXT NOT NULL,
	event_count BIGINT NOT NULL,
	record_version BIGINT NOT NULL,
	CONSTRAINT pk_attempts PRIMARY KEY (tenant_id, attempt_id),
	CONSTRAINT fk_attempts_0 FOREIGN KEY(authority_id) REFERENCES sync_control.authorities (authority_id) MATCH FULL ON DELETE NO ACTION,
	CONSTRAINT ck_attempts_0 CHECK (wire_d4 <> ''),
	CONSTRAINT ck_attempts_1 CHECK (internal_generation > 0),
	CONSTRAINT ck_attempts_2 CHECK (codec_version > 0),
	CONSTRAINT ck_attempts_3 CHECK (request_fingerprint <> ''),
	CONSTRAINT ck_attempts_4 CHECK (event_count > 0),
	CONSTRAINT ck_attempts_5 CHECK (record_version = 1)
);

ALTER TABLE sync_control.attempts ENABLE ROW LEVEL SECURITY;

ALTER TABLE sync_control.attempts FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE sync_control.attempts FROM PUBLIC;

CREATE TABLE sync_control.event_phases (
	tenant_id UUID NOT NULL,
	attempt_id UUID NOT NULL,
	phase_id UUID NOT NULL,
	event_position BIGINT NOT NULL,
	d1 BIGINT,
	d5 UUID NOT NULL,
	event_fingerprint TEXT NOT NULL,
	CONSTRAINT pk_event_phases PRIMARY KEY (tenant_id, attempt_id, phase_id),
	CONSTRAINT fk_event_phases_0 FOREIGN KEY(tenant_id, attempt_id) REFERENCES sync_control.attempts (tenant_id, attempt_id) MATCH FULL ON DELETE NO ACTION,
	CONSTRAINT uq_event_phases_0 UNIQUE (tenant_id, attempt_id, phase_id, d1, d5, event_fingerprint),
	CONSTRAINT ck_event_phases_0 CHECK (event_position > 0),
	CONSTRAINT ck_event_phases_1 CHECK (d1 IS NULL OR d1 > 0),
	CONSTRAINT ck_event_phases_2 CHECK (event_fingerprint <> '')
);

CREATE INDEX ix_sync_control_phase_d5 ON sync_control.event_phases (tenant_id, d5);

ALTER TABLE sync_control.event_phases ENABLE ROW LEVEL SECURITY;

ALTER TABLE sync_control.event_phases FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE sync_control.event_phases FROM PUBLIC;

