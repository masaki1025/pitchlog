"""実owned DBの同期世代読取列とアプリ権限を検査する。"""

from uuid import UUID

import pytest

from .test_sync_writer_binding import (
    admin_connection as admin_connection,
)
from .test_sync_writer_binding import (
    initial_scope_database as initial_scope_database,
)
from .test_sync_writer_binding import (
    tested_role_connection as tested_role_connection,
)

pytestmark = pytest.mark.requires_db


def test_owned_generation_read_projection_and_app_privileges(initial_scope_database):
    """実appの三読取が同じ12列を返し、保護列は権限を持たない。"""
    import psycopg

    from .sync_writer_binding_support import (
        binding_app,
        binding_broker,
    )

    owner = initial_scope_database
    issued = owner.actor("grant=issue(); print(json.dumps(receipt(grant)))")
    token, subject = UUID(int=8201), UUID(int=8202)
    with psycopg.connect(owner.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.system_settings(key,value) VALUES "
            "('auth.token_ttl_seconds','3600') ON CONFLICT(key) "
            "DO UPDATE SET value=EXCLUDED.value"
        )
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(tenant_id,id) VALUES (%s,%s)",
            (owner.tenant_id, subject),
        )
        admin.execute(
            "INSERT INTO public.tenant_credentials(auth_subject_id,password_hash,"
            "generation) VALUES (%s,'public-unused-login-vector',1)",
            (subject,),
        )
        admin.execute(
            "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subject_id,"
            "credential_generation,expires_at,last_used_at) VALUES "
            "(%s,%s,%s,1,clock_timestamp()+interval '1 hour',clock_timestamp())",
            (owner.tenant_id, token, subject),
        )
    body = f"""
from pitchlog.sync.tokens import (RECORDING_GENERATION_READ_COLUMNS,
 RecordingGenerationReadToken,RecordingGenerationByNumberReadToken,
 RecordingGenerationLockToken)
with tenant_transaction_scope(context) as tx:
 game=UUID('{owner.game_id}')
 generation={issued["generation"]}
 rows=[tx.run(token).rows for token in (RecordingGenerationReadToken(game),
  RecordingGenerationByNumberReadToken(game,generation),
  RecordingGenerationLockToken(game,generation))]
 assert all(len(result)==1 and len(result[0])==12 for result in rows)
 assert rows[0]==rows[1]==rows[2]
 assert rows[0][0][RECORDING_GENERATION_READ_COLUMNS.index('generation')]==generation
print(json.dumps(dict(three_real_reads=True)))
"""
    with binding_broker(owner, token):
        assert binding_app(owner, body) == {"three_real_reads": True}
    with psycopg.connect(owner.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT has_column_privilege('pitchlog_app', "
            "'public.recording_generations', 'proof_digest', 'SELECT'), "
            "has_column_privilege('pitchlog_app', "
            "'public.recording_generations', 'recovery_generation', 'SELECT')"
        ).fetchone() == (False, False)
