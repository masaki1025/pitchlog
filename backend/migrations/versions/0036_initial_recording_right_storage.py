"""初期権の有限4表と旧値を補完しないnullable証拠列を配置する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_initial_recording_right_storage"
down_revision: str | Sequence[str] | None = "0035_rg1_initial_fresh_epoch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAMES = (
    "trusted_devices",
    "game_start_requests",
    "game_start_attempts",
    "recording_right_deliveries",
)
_TABLE_DDL = (
    (
        "\n"
        "CREATE TABLE public.trusted_devices (\n"
        "\tdevice_id UUID NOT NULL, \n"
        "\tcredential_digest BYTEA NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTA"
        "MP NOT NULL, \n"
        "\trevoked_at TIMESTAMP WITH TIME ZONE, \n"
        "\ttenant_id UUID NOT NULL, \n"
        "\tCONSTRAINT pk_trusted_devices PRIMARY KEY (tenant_id, devic"
        "e_id), \n"
        "\tCONSTRAINT fk_trusted_devices_tenant FOREIGN KEY(tenant_id)"
        " REFERENCES public.tenants (id) ON DELETE NO ACTION, \n"
        "\tCONSTRAINT ck_trusted_devices_credential_digest CHECK (octe"
        "t_length(credential_digest) = 32), \n"
        "\tCONSTRAINT ck_trusted_devices_revoked_at CHECK (revoked_at "
        "IS NULL OR revoked_at >= created_at)\n"
        ")\n"
        "\n"
    ),
    (
        "\n"
        "CREATE TABLE public.game_start_requests (\n"
        "\tgame_id UUID NOT NULL, \n"
        "\tstart_request_id UUID NOT NULL, \n"
        "\tdevice_id UUID NOT NULL, \n"
        "\trequest_digest BYTEA NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTA"
        "MP NOT NULL, \n"
        "\ttenant_id UUID NOT NULL, \n"
        "\tCONSTRAINT pk_game_start_requests PRIMARY KEY (tenant_id, g"
        "ame_id, start_request_id), \n"
        "\tCONSTRAINT uq_game_start_requests_owner UNIQUE (tenant_id, "
        "game_id, start_request_id, device_id), \n"
        "\tCONSTRAINT fk_game_start_requests_game FOREIGN KEY(tenant_i"
        "d, game_id) REFERENCES public.games (tenant_id, id) MATCH FU"
        "LL ON DELETE NO ACTION, \n"
        "\tCONSTRAINT fk_game_start_requests_device FOREIGN KEY(tenant"
        "_id, device_id) REFERENCES public.trusted_devices (tenant_id"
        ", device_id) MATCH FULL ON DELETE NO ACTION, \n"
        "\tCONSTRAINT ck_game_start_requests_digest CHECK (octet_lengt"
        "h(request_digest) = 32)\n"
        ")\n"
        "\n"
    ),
    (
        "\n"
        "CREATE TABLE public.game_start_attempts (\n"
        "\tattempt_id UUID NOT NULL, \n"
        "\tgame_id UUID NOT NULL, \n"
        "\tstart_request_id UUID NOT NULL, \n"
        "\tdevice_id UUID NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTA"
        "MP NOT NULL, \n"
        "\tresolved_at TIMESTAMP WITH TIME ZONE, \n"
        "\toutcome TEXT DEFAULT 'pending' NOT NULL, \n"
        "\ttenant_id UUID NOT NULL, \n"
        "\tCONSTRAINT pk_game_start_attempts PRIMARY KEY (tenant_id, a"
        "ttempt_id), \n"
        "\tCONSTRAINT fk_game_start_attempts_request FOREIGN KEY(tenan"
        "t_id, game_id, start_request_id, device_id) REFERENCES publi"
        "c.game_start_requests (tenant_id, game_id, start_request_id,"
        " device_id) MATCH FULL ON DELETE NO ACTION, \n"
        "\tCONSTRAINT ck_game_start_attempts_outcome CHECK (outcome IN"
        " ('pending', 'committed', 'rolled_back')), \n"
        "\tCONSTRAINT ck_game_start_attempts_resolution CHECK ((outcom"
        "e = 'pending' AND resolved_at IS NULL) OR (outcome <> 'pendi"
        "ng' AND resolved_at IS NOT NULL AND resolved_at >= created_a"
        "t))\n"
        ")\n"
        "\n"
    ),
    (
        "CREATE UNIQUE INDEX uq_game_start_attempts_pending ON public"
        ".game_start_attempts (tenant_id, game_id, start_request_id) "
        "WHERE outcome = 'pending'"
    ),
    (
        "\n"
        "CREATE TABLE public.recording_right_deliveries (\n"
        "\tgame_id UUID NOT NULL, \n"
        "\tgeneration BIGINT NOT NULL, \n"
        "\tstart_request_id UUID NOT NULL, \n"
        "\tdevice_id UUID NOT NULL, \n"
        "\tkey_id TEXT NOT NULL, \n"
        "\tnonce BYTEA NOT NULL, \n"
        "\tciphertext BYTEA NOT NULL, \n"
        "\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTA"
        "MP NOT NULL, \n"
        "\trevoked_at TIMESTAMP WITH TIME ZONE, \n"
        "\ttenant_id UUID NOT NULL, \n"
        "\tCONSTRAINT pk_recording_right_deliveries PRIMARY KEY (tenan"
        "t_id, game_id, generation), \n"
        "\tCONSTRAINT uq_recording_right_deliveries_request UNIQUE (te"
        "nant_id, game_id, start_request_id), \n"
        "\tCONSTRAINT fk_recording_right_deliveries_generation FOREIGN"
        " KEY(tenant_id, game_id, generation) REFERENCES public.recor"
        "ding_generations (tenant_id, game_id, generation) MATCH FULL"
        " ON DELETE NO ACTION, \n"
        "\tCONSTRAINT fk_recording_right_deliveries_request FOREIGN KE"
        "Y(tenant_id, game_id, start_request_id, device_id) REFERENCE"
        "S public.game_start_requests (tenant_id, game_id, start_requ"
        "est_id, device_id) MATCH FULL ON DELETE NO ACTION, \n"
        "\tCONSTRAINT ck_recording_right_deliveries_generation CHECK ("
        "generation > 0), \n"
        "\tCONSTRAINT ck_recording_right_deliveries_key_id CHECK (key_"
        "id <> ''), \n"
        "\tCONSTRAINT ck_recording_right_deliveries_envelope CHECK (oc"
        "tet_length(nonce) = 12 AND octet_length(ciphertext) = 48), \n"
        "\tCONSTRAINT ck_recording_right_deliveries_revocation CHECK ("
        "revoked_at IS NULL OR revoked_at >= created_at)\n"
        ")\n"
        "\n"
    ),
)

_INTERNAL_TRIGGER_SQL = (
    "CREATE FUNCTION public.protect_initial_right_storage()\n"
    "RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER\n"
    "SET search_path TO pg_catalog, pg_temp AS $body$\n"
    "DECLARE old_row jsonb; new_row jsonb;\n"
    "BEGIN\n"
    "    IF TG_TABLE_SCHEMA <> 'public' OR TG_TABLE_NAME NOT IN\n"
    "      ('trusted_devices','game_start_requests','game_start_a"
    "ttempts','recording_right_deliveries') THEN\n"
    "        RAISE EXCEPTION 'initial right trigger target mismat"
    "ch';\n"
    "    END IF;\n"
    "    IF TG_OP = 'DELETE' THEN\n"
    "        RAISE EXCEPTION 'initial right storage cannot be phy"
    "sically deleted';\n"
    "    END IF;\n"
    "    old_row := pg_catalog.to_jsonb(OLD);\n"
    "    new_row := pg_catalog.to_jsonb(NEW);\n"
    "    IF TG_TABLE_NAME = 'game_start_requests' THEN\n"
    "        IF new_row IS DISTINCT FROM old_row THEN\n"
    "            RAISE EXCEPTION 'initial request is immutable';\n"
    "        END IF;\n"
    "    ELSIF TG_TABLE_NAME = 'game_start_attempts' THEN\n"
    "        IF (new_row - 'outcome' - 'resolved_at') IS DISTINCT"
    " FROM\n"
    "           (old_row - 'outcome' - 'resolved_at') OR\n"
    "           (old_row->>'outcome' <> 'pending' AND new_row IS "
    "DISTINCT FROM old_row) THEN\n"
    "            RAISE EXCEPTION 'initial attempt owner or resolu"
    "tion is immutable';\n"
    "        END IF;\n"
    "    ELSE\n"
    "        IF (new_row - 'revoked_at') IS DISTINCT FROM (old_ro"
    "w - 'revoked_at') OR\n"
    "           (old_row->'revoked_at' <> 'null'::jsonb AND new_r"
    "ow->'revoked_at' IS DISTINCT FROM old_row->'revoked_at') THE"
    "N\n"
    "            RAISE EXCEPTION 'initial device or delivery is i"
    "mmutable';\n"
    "        END IF;\n"
    "    END IF;\n"
    "    RETURN NEW;\n"
    "END\n"
    "$body$"
)


def upgrade() -> None:
    """表をdefault-denyにし、旧epoch/digestへ仮値を埋めない。"""
    if (
        op.get_bind().execute(sa.text("SELECT current_user")).scalar_one()
        != "pitchlog_owner"
    ):
        raise RuntimeError("初期権migrationには固定ownerが必要")
    op.add_column(
        "recording_generations",
        sa.Column("proof_digest", sa.LargeBinary(), nullable=True),
        schema="public",
    )
    op.add_column(
        "recording_generations",
        sa.Column("recovery_generation", sa.BigInteger(), nullable=True),
        schema="public",
    )
    op.create_check_constraint(
        "ck_recording_generations_proof_digest",
        "recording_generations",
        "proof_digest IS NULL OR octet_length(proof_digest) = 32",
        schema="public",
    )
    op.create_check_constraint(
        "ck_recording_generations_recovery_generation",
        "recording_generations",
        "recovery_generation IS NULL OR recovery_generation > 0",
        schema="public",
    )
    for ddl in _TABLE_DDL:
        op.execute(ddl)
    for table in _TABLE_NAMES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
    # rootの専用9関数/列ACL/RLS供給前は新表をdefault-denyのまま保持する。
    op.execute(_INTERNAL_TRIGGER_SQL)
    op.execute(
        "ALTER FUNCTION public.protect_initial_right_storage() OWNER TO pitchlog_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.protect_initial_right_storage() FROM PUBLIC"
    )
    for table in _TABLE_NAMES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_initial_right_guard "
            f"BEFORE UPDATE OR DELETE ON public.{table} FOR EACH ROW "
            "EXECUTE FUNCTION public.protect_initial_right_storage()"
        )


def downgrade() -> None:
    """資格/配達/attemptの履歴を物理削除する逆適用を拒否する。"""
    raise RuntimeError("初期権の履歴を消す逆適用は許可しない")
