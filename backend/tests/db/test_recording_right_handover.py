"""通常引き継ぎを実台帳・実actor・実SQLで一度だけ確定する。"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from db_fixtures import _dsn_names

from pitchlog.sync.d4_reference import encode_d4_reference

from .initial_recording_right_scope_support import (
    InitialGrantDatabase,
    isolated_initial_grant_database,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture
def initial_scope_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InitialGrantDatabase]:
    """既初期権fixtureのowned 3PG/authority/controllerをそのまま使う。"""
    with isolated_initial_grant_database(monkeypatch) as database:
        admin_name, role_name = _dsn_names()
        monkeypatch.setenv(admin_name, database.authority.database.primary_admin)
        monkeypatch.setenv(role_name, database.authority.database.endpoints.primary_dsn)
        yield database


def _mark_in_progress(database: InitialGrantDatabase) -> None:
    """引き継ぎ対象を製品の進行中状態へ進める。開始HTTPの成功主張ではない。"""
    with psycopg.connect(database.authority.database.business_admin) as admin:
        admin.execute(
            "UPDATE public.games SET status='in_progress', "
            "started_at=CURRENT_TIMESTAMP WHERE tenant_id=%s AND id=%s",
            (database.tenant_id, database.game_id),
        )


def test_real_normal_handover_rotates_d4_and_rejects_old_holder(
    initial_scope_database: InitialGrantDatabase,
) -> None:
    """旧世代を失効し、新端末へD3=0の新世代を発行し、旧保持端末を拒否する。"""
    database = initial_scope_database
    database.actor("print(json.dumps(receipt(issue())))")
    _mark_in_progress(database)
    other = str(database.other_device_id)
    result = database.actor(f"""
first=issue()
request_id=uuid4()
release=release_handover(UUID('{other}'),request_id,first)
acquired=acquire_handover(UUID('{other}'),request_id)
try:
    release_handover(UUID('{other}'),uuid4(),first)
except Exception as error:
    old_rejected=type(error).__name__
else:
    old_rejected='accepted'
print(json.dumps({{
    'first':receipt(first),
    'release':{{'from_generation':release.from_generation,
                'to_device_id':str(release.to_device_id),
                'last_d1':release.last_d1}},
    'acquired':handover_receipt(acquired),
    'old_rejected':old_rejected,
}}))
""")
    assert result["release"] == {
        "from_generation": "1",
        "to_device_id": other,
        "last_d1": 0,
    }
    assert result["acquired"]["device_id"] == other
    assert result["acquired"]["epoch"] == "1"
    assert result["acquired"]["d4"] != encode_d4_reference(
        database.tenant_id, database.game_id, result["first"]["generation"]
    )
    assert result["acquired"]["proof_digest"] != result["first"]["proof_digest"]
    assert result["old_rejected"] != "accepted"

    saved = database.storage()
    generations = sorted(
        saved["recording_generations"], key=lambda row: row["issuance_order"]
    )
    assert len(generations) == 2
    old, new = generations
    assert old["generation"] == 1
    assert old["holder_device"] == str(database.device_id)
    assert old["revoked_at"] is not None
    assert new["generation"] == 2
    assert new["issuance_order"] == 2
    assert new["holder_device"] == other
    assert new["revoked_at"] is None
    assert new["confirmed_watermark"] == new["applied_prefix"] == 0
    assert new["recovery_generation"] == 1
    assert new["proof_digest"] == "\\x" + result["acquired"]["proof_digest"]
    deliveries = saved["recording_right_deliveries"]
    assert len(deliveries) == 2
    assert sorted(row["generation"] for row in deliveries) == [1, 2]
    attempts = saved["game_start_attempts"]
    assert [row["outcome"] for row in attempts].count("committed") == 2
    # B4 の権利述語と同じ条件: 旧保持端末・旧V12は現世代に一致しない。
    with psycopg.connect(database.authority.database.business_admin) as admin:
        old_right = admin.execute(
            "SELECT EXISTS (SELECT 1 FROM public.recording_generations r "
            "WHERE r.tenant_id=%s AND r.game_id=%s AND r.generation=%s "
            "AND r.kind='normal' AND r.holder_device=%s AND r.revoked_at IS NULL "
            "AND r.retired_at IS NULL AND r.recovery_generation=1 "
            "AND r.proof_digest=%s)",
            (
                database.tenant_id,
                database.game_id,
                result["first"]["generation"],
                str(database.device_id),
                bytes.fromhex(result["first"]["proof_digest"]),
            ),
        ).fetchone()
        new_right = admin.execute(
            "SELECT EXISTS (SELECT 1 FROM public.recording_generations r "
            "WHERE r.tenant_id=%s AND r.game_id=%s AND r.kind='normal' "
            "AND r.holder_device=%s AND r.revoked_at IS NULL "
            "AND r.retired_at IS NULL AND r.recovery_generation=1 "
            "AND r.proof_digest=%s)",
            (
                database.tenant_id,
                database.game_id,
                other,
                bytes.fromhex(result["acquired"]["proof_digest"]),
            ),
        ).fetchone()
    assert old_right == (False,)
    assert new_right == (True,)


def test_real_normal_handover_refuses_unsynced_watermark(
    initial_scope_database: InitialGrantDatabase,
) -> None:
    """旧端末の最終連番がD3を超える解放を拒否し、現世代を維持する。"""
    database = initial_scope_database
    database.actor("print(json.dumps(receipt(issue())))")
    _mark_in_progress(database)
    other = str(database.other_device_id)
    result = database.actor(f"""
first=issue()
try:
    release_handover(UUID('{other}'),uuid4(),first,last_d1=1)
except Exception as error:
    refused=type(error).__name__
else:
    refused='accepted'
print(json.dumps({{'refused':refused,'first':receipt(first)}}))
""")
    assert result["refused"] != "accepted"
    saved = database.storage()
    generations = saved["recording_generations"]
    assert len(generations) == 1
    assert generations[0]["revoked_at"] is None
    assert generations[0]["holder_device"] == str(database.device_id)
    # 初期付与の配達1件だけが残り、引き継ぎの新規配達は増えない。
    assert len(saved["recording_right_deliveries"]) == 1
    assert saved["recording_right_deliveries"][0]["generation"] == 1
    with psycopg.connect(database.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT count(*) FROM public.recording_generations "
            "WHERE tenant_id=%s AND game_id=%s AND kind='normal' "
            "AND revoked_at IS NULL AND holder_device=%s",
            (database.tenant_id, database.game_id, str(database.device_id)),
        ).fetchone() == (1,)
