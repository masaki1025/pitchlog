"""新5の隔離候補で再交付・端末境界・復旧世代停止を検証する。"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest

from pitchlog.recording_rights.initial_grant import (
    InitialGrantConflict,
    InitialGrantRecord,
    InitialGrantUnavailable,
    ProofEnvelope,
    ReservedGeneration,
    V12Box,
    assert_write_recovery_generation,
    issue_initial_recording_right,
)

if TYPE_CHECKING:
    from db_fixtures import DisposablePostgres

pytest_plugins = ("db_fixtures",)

_GAME = UUID("00000000-0000-0000-0000-000000000392")
_TENANT = UUID("00000000-0000-0000-0000-000000000013")
_OTHER_TENANT = UUID("00000000-0000-0000-0000-000000000014")
_DEVICE = UUID("00000000-0000-0000-0000-000000000001")
_OTHER_DEVICE = UUID("00000000-0000-0000-0000-000000000002")
_KEY = bytes(range(32))  # 隔離試験専用。製品設定には使わない。


class _Ledger:
    """取消された予約も戻さない隔離台帳。"""

    def __init__(self) -> None:
        """世代を初期化する。"""
        self.epoch = 1
        self.next_generation = 1
        self.unavailable = False
        self.reservations = 0
        self.attempts: dict[UUID, ReservedGeneration] = {}
        self.claimed: set[UUID] = set()
        self.lose_reservation_response = False
        self.lose_claim_response = False

    def current_recovery_generation(self) -> int:
        """障害時は現値を推測しない。"""
        if self.unavailable:
            raise InitialGrantUnavailable("台帳を読めない")
        return self.epoch

    def reserve(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> ReservedGeneration:
        """試行ごとに別のD4を予約する。"""
        assert type(attempt_id) is UUID
        if self.unavailable:
            raise InitialGrantUnavailable("台帳を読めない")
        reserved = self.attempts.get(attempt_id)
        if reserved is None:
            reserved = ReservedGeneration(
                self.next_generation, self.epoch, tenant_id, game_id, start_request_id
            )
            self.attempts[attempt_id] = reserved
            self.next_generation += 1
            self.reservations += 1
        if self.lose_reservation_response:
            self.lose_reservation_response = False
            raise InitialGrantUnavailable("予約応答不明")
        if (reserved.tenant_id, reserved.game_id, reserved.start_request_id) != (
            tenant_id,
            game_id,
            start_request_id,
        ):
            raise InitialGrantConflict("D4予約の所有要求が一致しない")
        return reserved

    def claim(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> None:
        """使用を耐久確定し、同じattemptによる二度目の業務投入を拒否する。"""
        reserved = self.attempts.get(attempt_id)
        if reserved is None or (
            reserved.tenant_id,
            reserved.game_id,
            reserved.start_request_id,
        ) != (tenant_id, game_id, start_request_id):
            raise InitialGrantConflict("D4予約の所有要求が一致しない")
        if attempt_id in self.claimed or attempt_id not in self.attempts:
            raise InitialGrantConflict("D4予約は既に消費済み")
        self.claimed.add(attempt_id)
        if self.lose_claim_response:
            self.lose_claim_response = False
            raise InitialGrantUnavailable("消費応答不明")


class _Fence:
    """外部epoch行の共有ロック保持を表す隔離代役。"""

    def __init__(self, ledger: _Ledger) -> None:
        """取得時の現世代を固定する。"""
        self.generation = ledger.epoch
        self.held = True

    def assert_held(self) -> None:
        """早期解放された候補を拒否する。"""
        if not self.held:
            raise InitialGrantUnavailable("外部復旧世代のロックがない")


class _Scope:
    """同一transactionの閉じたDB操作を表す隔離候補。"""

    def __init__(self) -> None:
        """有効な端末と空の試合を準備する。"""
        self.devices = {_DEVICE: "credential-a", _OTHER_DEVICE: "credential-b"}
        self.record: InitialGrantRecord | None = None
        self.epoch = 1
        self.open = True
        self.preparing = True
        self.calls: list[str] = []
        self.fail_after_insert = False
        self.revoke_before_lock = False
        self.misbind_before_lock = False

    def assert_bound_tenant(self, tenant_id: UUID) -> None:
        """実行器が固定したtenantと異なる入力を拒否する。"""
        if tenant_id != _TENANT:
            raise InitialGrantUnavailable("テナントが一致しない")

    def verify_device(self, device_id: UUID, credential: str) -> bool:
        """同一tenantに属する有効資格だけを受理する。"""
        self.calls.append("device")
        return self.devices.get(device_id) == credential

    def lock_valid_device(self, device_id: UUID, credential: str) -> bool:
        """隔離候補で資格の共有ロック取得点を記録する。"""
        self.calls.append("device_lock")
        return self.verify_device(device_id, credential)

    def existing_start(
        self, game_id: UUID, start_request_id: UUID
    ) -> InitialGrantRecord | None:
        """同じ要求の現世代だけを返す。"""
        self.calls.append("existing")
        record = self.record
        if (
            record
            and record.game_id == game_id
            and record.start_request_id == start_request_id
        ):
            return record
        return None

    def precheck_open_and_game(self, game_id: UUID) -> None:
        """予約前に試合とRG1を確認する。"""
        self.calls.append("precheck")
        if game_id != _GAME or not self.open:
            raise InitialGrantUnavailable("試合または復元ゲートを確認できない")

    def lock_preparing_game(self, game_id: UUID) -> None:
        """世代追加前に試合行をロックする。"""
        self.calls.append("game_lock")
        if game_id != _GAME or not self.preparing or self.record:
            raise InitialGrantConflict("試合を開始できない")

    def lock_current_start(
        self, game_id: UUID, start_request_id: UUID
    ) -> InitialGrantRecord | None:
        """再交付前に試合・世代・配達を再照合してロックする。"""
        self.calls.append("current_lock")
        if self.revoke_before_lock:
            self.record = None
        record = self.record
        if (
            record
            and record.game_id == game_id
            and record.start_request_id == start_request_id
        ):
            if self.misbind_before_lock:
                return replace(record, start_request_id=uuid4())
            return record
        return None

    def assert_recovery_generation(self, value: int) -> None:
        """業務DBの復旧世代と比べる。"""
        self.calls.append("epoch")
        if self.epoch != value:
            raise InitialGrantUnavailable("復旧世代が一致しない")

    def insert_initial_grant(self, record: InitialGrantRecord) -> None:
        """世代と配達値を同じ仮transactionへ置く。"""
        self.calls.append("insert")
        if self.record is not None:
            raise InitialGrantConflict("記録権が既にある")
        self.record = record
        if self.fail_after_insert:
            self.record = None
            raise InitialGrantUnavailable("業務transaction取消")

    def assert_open_before_commit(self) -> None:
        """直前に閉じたRG1を拒否する。"""
        self.calls.append("commit_gate")
        if not self.open:
            self.record = None
            raise InitialGrantUnavailable("復元ゲートが閉じている")


def _issue(
    scope: _Scope,
    ledger: _Ledger,
    box: V12Box,
    request_id: UUID,
    *,
    device_id: UUID = _DEVICE,
    credential: str = "credential-a",
    attempt_id: UUID | None = None,
):
    """隔離候補の初期付与を呼ぶ。"""
    return issue_initial_recording_right(
        scope,
        tenant_id=_TENANT,
        game_id=_GAME,
        device_id=device_id,
        device_credential=credential,
        start_request_id=request_id,
        reservation_attempt_id=attempt_id or uuid4(),
        source=ledger,
        fence=_Fence(ledger),
        box=box,
    )


def test_lost_response_reissues_same_proof_without_second_generation() -> None:
    """commit後の応答消失は同じV12を追加発行なしで返す。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    first = _issue(scope, ledger, box, request_id)
    second = _issue(scope, ledger, box, request_id)
    assert first == second
    assert first.recording_right_proof == second.recording_right_proof
    assert ledger.reservations == 1
    assert scope.record is not None
    assert first.recording_right_proof not in repr(scope.record)
    assert first.recording_right_proof not in repr(first)
    assert scope.calls.index("game_lock") < scope.calls.index("insert")


def test_unknown_reservation_response_retries_same_attempt_without_second_d4() -> None:
    """台帳応答消失後は同じattempt IDで同じD4を回収する。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    attempt_id = uuid4()
    ledger.lose_reservation_response = True
    with pytest.raises(InitialGrantUnavailable, match="予約応答不明"):
        _issue(scope, ledger, box, request_id, attempt_id=attempt_id)
    assert ledger.reservations == 1 and scope.record is None
    result = _issue(scope, ledger, box, request_id, attempt_id=attempt_id)
    assert result.generation == 1
    assert ledger.reservations == 1


def test_attempt_cannot_be_reused_for_another_start_or_after_rollback() -> None:
    """所有要求の変更と業務取消後の再投入に同じD4を使わない。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    attempt_id = uuid4()
    ledger.lose_reservation_response = True
    with pytest.raises(InitialGrantUnavailable, match="予約応答不明"):
        _issue(scope, ledger, box, request_id, attempt_id=attempt_id)
    with pytest.raises(InitialGrantConflict, match="所有要求"):
        _issue(scope, ledger, box, uuid4(), attempt_id=attempt_id)
    scope.fail_after_insert = True
    with pytest.raises(InitialGrantUnavailable, match="取消"):
        _issue(scope, ledger, box, request_id, attempt_id=attempt_id)
    assert ledger.reservations == 1 and scope.record is None
    scope.fail_after_insert = False
    with pytest.raises(InitialGrantConflict, match="消費済み"):
        _issue(scope, ledger, box, request_id, attempt_id=attempt_id)
    assert scope.record is None
    assert _issue(scope, ledger, box, request_id).generation == 2


def test_unknown_claim_response_never_enters_business_scope_twice() -> None:
    """消費応答不明のD4は未投入でも再使用しない。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    attempt_id = uuid4()
    ledger.lose_claim_response = True
    with pytest.raises(InitialGrantUnavailable, match="消費応答不明"):
        _issue(scope, ledger, box, request_id, attempt_id=attempt_id)
    assert scope.record is None and ledger.reservations == 1
    with pytest.raises(InitialGrantConflict, match="消費済み"):
        _issue(scope, ledger, box, request_id, attempt_id=attempt_id)
    assert scope.record is None


def test_other_device_and_self_reported_id_cannot_retrieve_proof() -> None:
    """別端末と自己申告の端末IDだけでは再交付しない。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    _issue(scope, ledger, box, request_id)
    with pytest.raises(InitialGrantUnavailable, match="端末資格"):
        _issue(scope, ledger, box, request_id, device_id=_OTHER_DEVICE)
    with pytest.raises(InitialGrantConflict, match="別端末"):
        _issue(
            scope,
            ledger,
            box,
            request_id,
            device_id=_OTHER_DEVICE,
            credential="credential-b",
        )
    scope.devices.pop(_DEVICE)
    with pytest.raises(InitialGrantUnavailable, match="端末資格"):
        _issue(scope, ledger, box, request_id)
    assert ledger.reservations == 1


def test_revocation_between_precheck_and_lock_blocks_reissue() -> None:
    """非ロック照合の後に失効した旧証明を返さない。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    _issue(scope, ledger, box, request_id)
    scope.revoke_before_lock = True
    with pytest.raises(InitialGrantConflict, match="現権利"):
        _issue(scope, ledger, box, request_id)
    assert "current_lock" in scope.calls
    assert ledger.reservations == 1


def test_adapter_misbound_locked_start_blocks_reissue() -> None:
    """誤った要求行を返すadapterでも証明を再交付しない。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    _issue(scope, ledger, box, request_id)
    scope.misbind_before_lock = True
    with pytest.raises(InitialGrantConflict, match="現権利"):
        _issue(scope, ledger, box, request_id)
    assert ledger.reservations == 1


def test_different_request_and_rollback_never_reuse_d4() -> None:
    """取消済みD4を戻さず、異なる開始IDを再交付扱いにしない。"""
    scope, ledger, box = _Scope(), _Ledger(), V12Box("k1", _KEY)
    scope.fail_after_insert = True
    with pytest.raises(InitialGrantUnavailable, match="取消"):
        _issue(scope, ledger, box, uuid4())
    assert ledger.reservations == 1 and scope.record is None
    scope.fail_after_insert = False
    _issue(scope, ledger, box, uuid4())
    assert scope.record is not None and scope.record.generation == 2
    with pytest.raises(InitialGrantConflict):
        _issue(scope, ledger, box, uuid4())
    assert ledger.reservations == 3


def test_epoch_mismatch_or_unknown_stops_existing_right() -> None:
    """復旧世代不一致と台帳障害は既存の再交付も止める。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    _issue(scope, ledger, box, request_id)
    ledger.epoch = 2
    with pytest.raises(InitialGrantUnavailable, match="復旧世代"):
        _issue(scope, ledger, box, request_id)
    ledger.unavailable = True
    with pytest.raises(InitialGrantUnavailable, match="台帳"):
        _issue(scope, ledger, box, request_id)
    assert ledger.reservations == 1


def test_restored_preparing_game_waits_until_start_for_new_d4() -> None:
    """準備中への復元解除では発行せず、開始時に旧D4を再利用しない。"""
    ledger, box = _Ledger(), V12Box("k1", _KEY)
    before_restore = _Scope()
    first = _issue(before_restore, ledger, box, uuid4())
    assert first.generation == 1

    # 業務DBだけを準備中のバックアップへ戻し、外部発行元は巻き戻さない。
    restored_preparing = _Scope()
    ledger.epoch = 2
    assert restored_preparing.record is None
    assert ledger.reservations == 1
    with pytest.raises(InitialGrantUnavailable, match="復旧世代"):
        assert_write_recovery_generation(restored_preparing, ledger, _Fence(ledger), 1)
    assert ledger.reservations == 1

    # 解除後に業務DBの復旧世代が外部現値へ一致した状態だけを模す。
    restored_preparing.epoch = 2
    started = _issue(restored_preparing, ledger, box, uuid4())
    assert started.generation == 2
    assert started.recovery_generation == "2"
    assert started.recording_right_proof != first.recording_right_proof
    assert ledger.reservations == 2


def test_ciphertext_is_bound_to_all_values_and_key() -> None:
    """要求・端末・世代の付替えと鍵欠損では復号しない。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    _issue(scope, ledger, box, request_id)
    record = scope.record
    assert record is not None
    for forged in (
        replace(record, tenant_id=_OTHER_TENANT),
        replace(record, device_id=_OTHER_DEVICE),
        replace(record, start_request_id=uuid4()),
        replace(record, generation=record.generation + 1),
        replace(record, recovery_generation=record.recovery_generation + 1),
        replace(
            record,
            envelope=ProofEnvelope(
                "missing", record.envelope.nonce, record.envelope.ciphertext
            ),
        ),
        replace(record, proof_digest=b"0" * 32),
    ):
        with pytest.raises(InitialGrantUnavailable, match="再交付"):
            box.reopen(forged)


def test_cross_tenant_aad_and_direct_scope_reject_spoofing() -> None:
    """同じUUID組でもtenantを変えた暗号文と直接入力を拒否する。"""
    scope, ledger, box, request_id = _Scope(), _Ledger(), V12Box("k1", _KEY), uuid4()
    _issue(scope, ledger, box, request_id)
    assert scope.record is not None
    with pytest.raises(InitialGrantUnavailable, match="再交付"):
        box.reopen(replace(scope.record, tenant_id=_OTHER_TENANT))
    with pytest.raises(InitialGrantUnavailable, match="テナント"):
        issue_initial_recording_right(
            scope,
            tenant_id=_OTHER_TENANT,
            game_id=_GAME,
            device_id=_DEVICE,
            device_credential="credential-a",
            start_request_id=request_id,
            reservation_attempt_id=uuid4(),
            source=ledger,
            fence=_Fence(ledger),
            box=box,
        )
    assert ledger.reservations == 1


def test_key_rotation_reissues_with_retained_old_key_only() -> None:
    """新鍵へ切替後も旧鍵保持中だけ同じ証明を再交付する。"""
    scope, ledger, old_box, request_id = (
        _Scope(),
        _Ledger(),
        V12Box("k1", _KEY),
        uuid4(),
    )
    first = _issue(scope, ledger, old_box, request_id)
    new_key = bytes(reversed(range(32)))
    rotated = V12Box("k2", new_key, previous_keys={"k1": _KEY})
    assert _issue(scope, ledger, rotated, request_id).recording_right_proof == (
        first.recording_right_proof
    )
    with pytest.raises(InitialGrantUnavailable, match="再交付"):
        _issue(scope, ledger, V12Box("k2", new_key), request_id)


def test_rg1_closed_and_invalid_credential_fail_before_reservation() -> None:
    """事前閉鎖と内部直接実行の不正端末ではD4を消費しない。"""
    scope, ledger, box = _Scope(), _Ledger(), V12Box("k1", _KEY)
    scope.open = False
    with pytest.raises(InitialGrantUnavailable):
        _issue(scope, ledger, box, uuid4())
    assert ledger.reservations == 0
    scope.open = True
    with pytest.raises(InitialGrantUnavailable, match="端末資格"):
        _issue(scope, ledger, box, uuid4(), credential="forged")
    assert ledger.reservations == 0


def test_write_epoch_fence_is_required_and_unknown_stops_write() -> None:
    """外部共有ロックの早期解放・現値不明を通常書込で拒否する。"""
    scope, ledger, fence = _Scope(), _Ledger(), _Fence(_Ledger())
    fence.held = False
    with pytest.raises(InitialGrantUnavailable, match="ロック"):
        assert_write_recovery_generation(scope, ledger, fence, 1)
    assert "commit_gate" not in scope.calls
    fence.held = True
    ledger.unavailable = True
    with pytest.raises(InitialGrantUnavailable, match="台帳"):
        assert_write_recovery_generation(scope, ledger, fence, 1)


def test_external_epoch_lock_and_d4_counter_are_independent_rows(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """epoch共有保持中にD4を予約でき、復元epoch更新はcommitまで待つ。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            admin.execute(
                "CREATE TABLE recovery_epoch ("
                "singleton_id integer PRIMARY KEY CHECK (singleton_id = 1), "
                "current_generation bigint NOT NULL)"
            )
            admin.execute(
                "CREATE TABLE d4_counter ("
                "singleton_id integer PRIMARY KEY CHECK (singleton_id = 1), "
                "next_generation bigint NOT NULL)"
            )
            admin.execute("INSERT INTO recovery_epoch VALUES (1, 1)")
            admin.execute("INSERT INTO d4_counter VALUES (1, 1)")
        with (
            psycopg.connect(cluster.admin_dsn) as writer,
            psycopg.connect(cluster.admin_dsn) as reservation,
            psycopg.connect(cluster.admin_dsn) as restoration,
        ):
            assert writer.execute(
                "SELECT current_generation FROM recovery_epoch "
                "WHERE singleton_id = 1 FOR SHARE"
            ).fetchone() == (1,)
            reservation.execute(
                "UPDATE d4_counter SET next_generation = 2 WHERE singleton_id = 1"
            )
            reservation.commit()
            restoration.execute("SET LOCAL lock_timeout = '100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                restoration.execute(
                    "UPDATE recovery_epoch SET current_generation = 2 "
                    "WHERE singleton_id = 1"
                )
            restoration.rollback()
            writer.commit()
            restoration.execute(
                "UPDATE recovery_epoch SET current_generation = 2 "
                "WHERE singleton_id = 1"
            )
            restoration.commit()
            assert restoration.execute(
                "SELECT current_generation FROM recovery_epoch WHERE singleton_id = 1"
            ).fetchone() == (2,)


def test_external_claim_sql_rejects_other_owner_and_second_use(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """隔離台帳の所有tupleと一度限りclaimをSQL条件で拘束する。"""
    attempt_id, request_id = uuid4(), uuid4()
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            admin.execute(
                "CREATE TABLE d4_reservations ("
                "attempt_id uuid PRIMARY KEY, tenant_id uuid NOT NULL, "
                "game_id uuid NOT NULL, start_request_id uuid NOT NULL, "
                "generation bigint NOT NULL UNIQUE, "
                "status text NOT NULL CHECK (status IN ('reserved', 'claimed')))"
            )
            admin.execute(
                "INSERT INTO d4_reservations VALUES (%s, %s, %s, %s, 1, 'reserved')",
                (attempt_id, _TENANT, _GAME, request_id),
            )
        statement = (
            "UPDATE d4_reservations SET status = 'claimed' "
            "WHERE attempt_id = %s AND tenant_id = %s AND game_id = %s "
            "AND start_request_id = %s AND status = 'reserved' "
            "RETURNING generation"
        )
        with (
            psycopg.connect(cluster.admin_dsn) as first,
            psycopg.connect(cluster.admin_dsn) as racing,
        ):
            assert (
                first.execute(
                    statement, (attempt_id, _OTHER_TENANT, _GAME, request_id)
                ).fetchone()
                is None
            )
            assert (
                first.execute(
                    statement, (attempt_id, _TENANT, _GAME, uuid4())
                ).fetchone()
                is None
            )
            assert first.execute(
                statement, (attempt_id, _TENANT, _GAME, request_id)
            ).fetchone() == (1,)
            racing.execute("SET LOCAL lock_timeout = '100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                racing.execute(statement, (attempt_id, _TENANT, _GAME, request_id))
            racing.rollback()
            first.commit()
            assert (
                racing.execute(
                    statement, (attempt_id, _TENANT, _GAME, request_id)
                ).fetchone()
                is None
            )


def test_external_reservation_is_recovered_by_owner_after_lost_response(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """予約確定後の応答消失では所有要求で同じD4を再照会する。"""
    request_id, first_attempt, next_attempt = uuid4(), uuid4(), uuid4()
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            admin.execute(
                "CREATE TABLE d4_counter ("
                "singleton_id integer PRIMARY KEY CHECK (singleton_id = 1), "
                "next_generation bigint NOT NULL)"
            )
            admin.execute("INSERT INTO d4_counter VALUES (1, 1)")
            admin.execute(
                "CREATE TABLE d4_reservations ("
                "attempt_id uuid PRIMARY KEY, tenant_id uuid NOT NULL, "
                "game_id uuid NOT NULL, start_request_id uuid NOT NULL, "
                "generation bigint NOT NULL UNIQUE, "
                "status text NOT NULL CHECK (status IN ('reserved', 'claimed')))"
            )
            admin.execute(
                "CREATE UNIQUE INDEX one_reserved_start "
                "ON d4_reservations (tenant_id, game_id, start_request_id) "
                "WHERE status = 'reserved'"
            )
        with psycopg.connect(cluster.admin_dsn) as reservation:
            generation = reservation.execute(
                "UPDATE d4_counter SET next_generation = next_generation + 1 "
                "WHERE singleton_id = 1 RETURNING next_generation - 1"
            ).fetchone()
            assert generation == (1,)
            reservation.execute(
                "INSERT INTO d4_reservations VALUES (%s, %s, %s, %s, %s, 'reserved')",
                (first_attempt, _TENANT, _GAME, request_id, generation[0]),
            )
            reservation.commit()
        with psycopg.connect(cluster.admin_dsn) as retry:
            assert retry.execute(
                "SELECT attempt_id, generation FROM d4_reservations "
                "WHERE tenant_id = %s AND game_id = %s "
                "AND start_request_id = %s AND status = 'reserved'",
                (_TENANT, _GAME, request_id),
            ).fetchone() == (first_attempt, 1)
            assert (
                retry.execute(
                    "SELECT attempt_id FROM d4_reservations "
                    "WHERE tenant_id = %s AND game_id = %s "
                    "AND start_request_id = %s AND status = 'reserved'",
                    (_OTHER_TENANT, _GAME, request_id),
                ).fetchone()
                is None
            )
            assert retry.execute(
                "SELECT next_generation FROM d4_counter WHERE singleton_id = 1"
            ).fetchone() == (2,)
            retry.execute(
                "UPDATE d4_reservations SET status = 'claimed' "
                "WHERE attempt_id = %s AND status = 'reserved'",
                (first_attempt,),
            )
            retry.commit()
        with psycopg.connect(cluster.admin_dsn) as after_business_rollback:
            next_generation = after_business_rollback.execute(
                "UPDATE d4_counter SET next_generation = next_generation + 1 "
                "WHERE singleton_id = 1 RETURNING next_generation - 1"
            ).fetchone()
            assert next_generation == (2,)
            after_business_rollback.execute(
                "INSERT INTO d4_reservations VALUES (%s, %s, %s, %s, %s, 'reserved')",
                (next_attempt, _TENANT, _GAME, request_id, next_generation[0]),
            )
            after_business_rollback.commit()
            assert after_business_rollback.execute(
                "SELECT generation FROM d4_reservations "
                "WHERE attempt_id = %s AND status = 'claimed'",
                (first_attempt,),
            ).fetchone() == (1,)


def test_external_reservation_rejects_parallel_attempt_for_same_start(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """同じ開始要求の未消費予約は別attemptでも同時に作れない。"""
    request_id = uuid4()
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            admin.execute(
                "CREATE TABLE d4_reservations ("
                "attempt_id uuid PRIMARY KEY, tenant_id uuid NOT NULL, "
                "game_id uuid NOT NULL, start_request_id uuid NOT NULL, "
                "generation bigint NOT NULL UNIQUE, "
                "status text NOT NULL CHECK (status IN ('reserved', 'claimed')))"
            )
            admin.execute(
                "CREATE UNIQUE INDEX one_reserved_start "
                "ON d4_reservations (tenant_id, game_id, start_request_id) "
                "WHERE status = 'reserved'"
            )
        with (
            psycopg.connect(cluster.admin_dsn) as first,
            psycopg.connect(cluster.admin_dsn) as second,
        ):
            first.execute(
                "INSERT INTO d4_reservations VALUES (%s, %s, %s, %s, 1, 'reserved')",
                (uuid4(), _TENANT, _GAME, request_id),
            )
            second.execute("SET LOCAL lock_timeout = '100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                second.execute(
                    "INSERT INTO d4_reservations "
                    "VALUES (%s, %s, %s, %s, 2, 'reserved')",
                    (uuid4(), _TENANT, _GAME, request_id),
                )
            second.rollback()
            first.commit()
            with pytest.raises(psycopg.errors.UniqueViolation):
                second.execute(
                    "INSERT INTO d4_reservations "
                    "VALUES (%s, %s, %s, %s, 2, 'reserved')",
                    (uuid4(), _TENANT, _GAME, request_id),
                )


def test_device_credential_lock_serializes_revocation(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """資格の共有ロックを確定まで保持し、失効UPDATEを先へ通さない。"""
    with disposable_postgres_cluster() as cluster:
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as admin:
            admin.execute(
                "CREATE TABLE trusted_devices ("
                "tenant_id uuid NOT NULL, device_id uuid NOT NULL, "
                "credential text NOT NULL, revoked_at timestamptz, "
                "PRIMARY KEY (tenant_id, device_id))"
            )
            admin.execute(
                "INSERT INTO trusted_devices VALUES (%s, %s, 'credential-a', NULL)",
                (_TENANT, _DEVICE),
            )
        with (
            psycopg.connect(cluster.admin_dsn) as delivery,
            psycopg.connect(cluster.admin_dsn) as revocation,
        ):
            assert delivery.execute(
                "SELECT device_id FROM trusted_devices "
                "WHERE tenant_id = %s AND device_id = %s "
                "AND credential = 'credential-a' AND revoked_at IS NULL FOR SHARE",
                (_TENANT, _DEVICE),
            ).fetchone() == (_DEVICE,)
            revocation.execute("SET LOCAL lock_timeout = '100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                revocation.execute(
                    "UPDATE trusted_devices SET revoked_at = CURRENT_TIMESTAMP "
                    "WHERE tenant_id = %s AND device_id = %s",
                    (_TENANT, _DEVICE),
                )
            revocation.rollback()
            delivery.commit()
            revocation.execute(
                "UPDATE trusted_devices SET revoked_at = CURRENT_TIMESTAMP "
                "WHERE tenant_id = %s AND device_id = %s",
                (_TENANT, _DEVICE),
            )
            revocation.commit()
            assert (
                delivery.execute(
                    "SELECT device_id FROM trusted_devices "
                    "WHERE tenant_id = %s AND device_id = %s "
                    "AND credential = 'credential-a' AND revoked_at IS NULL FOR SHARE",
                    (_TENANT, _DEVICE),
                ).fetchone()
                is None
            )


@pytest.mark.parametrize("start_mode", [False, True])
def test_real_scope_calls_closed_start_hook_only_after_game_lock(
    start_mode: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """純scope配線だけを確認し、代役transactionを認証/DB成功と呼ばない。"""
    from test_authz_tenant_context import make_tenant_context
    from test_initial_game_start_components import _bind

    from pitchlog.repositories import game_start, transaction
    from pitchlog.repositories.initial_recording_right import (
        _SCOPE_BINDINGS,
        _SCOPE_CREATION,
        InitialRecordingRightScope,
    )
    from pitchlog.repositories.tokens import TenantOperationResult

    bound = _bind()
    seen = []

    class Tx:
        def run_function(self, token):
            seen.append("game_lock")
            return TenantOperationResult(((True,),))

    monkeypatch.setattr(
        transaction, "_assert_initial_actor_transaction", lambda *args: None
    )

    def initialize(scope, payload):
        assert scope._game_locked and scope._device_valid
        assert payload is bound
        seen.append("closed_start")
        return object()

    monkeypatch.setattr(game_start, "_initialize_start", initialize)
    scope = InitialRecordingRightScope(
        make_tenant_context(bound.owner.tenant_id),
        cast(Any, Tx()),
        bound.owner,
        _SCOPE_CREATION,
        bound if start_mode else None,
    )
    try:
        scope._device_valid = True
        scope._outcome = "pending"
        scope.lock_preparing_game(bound.owner.game_id)
        assert seen == (["game_lock", "closed_start"] if start_mode else ["game_lock"])
    finally:
        _SCOPE_BINDINGS.pop(scope, None)


def test_start_business_reuses_the_single_issuer_and_commit_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新入口は既commit所有本体1回であり、独自発行器を選択しない。"""
    from datetime import datetime, timezone

    from test_initial_game_start_components import _bind

    from pitchlog.recording_rights import initial_grant_broker as broker
    from pitchlog.repositories.game_start import InitialStartReceipt

    bound = _bind()
    seen = []
    saved = InitialStartReceipt(
        bound.owner,
        datetime(2026, 10, 26, tzinfo=timezone.utc),
        UUID(int=9),
        UUID(int=10),
    )
    grant = object()

    def body(*args):
        seen.append(args)
        return grant, saved

    monkeypatch.setattr(broker, "_issue_initial_grant_impl", body)
    result = broker._start_initial_game(
        cast(Any, object()),
        object(),
        bound,
        "synthetic",
        cast(Any, object()),
        cast(Any, object()),
    )
    assert result.receipt is saved and result.grant is grant and len(seen) == 1
    assert seen[0][-1] is bound and seen[0][2] is bound.owner
    seen.clear()
    assert (
        broker._issue_initial_grant(
            cast(Any, object()),
            object(),
            bound.owner,
            "synthetic",
            cast(Any, object()),
            cast(Any, object()),
        )
        is grant
    )
    assert len(seen) == 1 and len(seen[0]) == 6


def _transport_start():
    """公開合成値だけで通信外形を作る。発行やcommitの証拠ではない。"""
    from pydantic import SecretStr
    from test_initial_game_start_components import _CREDENTIAL, _bind

    from pitchlog.recording_rights import initial_grant_broker as b

    bound = _bind()
    identity = b._BrokerIdentity(
        bound.owner.tenant_id, UUID(int=901), SecretStr("test-cookie")
    )
    return b._StartInitialGameCommand(
        identity,
        bound.owner.game_id,
        bound.owner.start_request_id,
        bound.owner.device_id,
        SecretStr(_CREDENTIAL),
        bound.payload,
    )


def _transport_postcommit_shape():
    """同戻り値の投影テスト用。実_start_initial_gameを実行したとはしない。"""
    from datetime import datetime, timezone

    from test_initial_game_start_components import _bind

    from pitchlog.recording_rights import initial_grant_broker as b
    from pitchlog.recording_rights.initial_grant import InitialGrant
    from pitchlog.repositories.game_start import InitialStartReceipt

    owner = _bind().owner
    grant = InitialGrant(owner.game_id, 17, "2", owner.device_id, "test-proof")
    receipt = InitialStartReceipt(
        owner, datetime(2026, 10, 26, tzinfo=timezone.utc), UUID(int=31), UUID(int=32)
    )
    return owner, b._InitialStartedGame(grant, receipt)


@pytest.mark.parametrize("generation", [1, 2, 255, 256, 2**53, 2**63 - 1])
def test_broker_private_d4_codec_has_exact_owner_and_bigint_range(generation) -> None:
    """D4はopaque往復だけを扱い、parseを権利照合にしない。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    value = b._broker_d4(_TENANT, _GAME, generation)
    assert len(value) == 60 and not value.isdecimal()
    assert b._broker_generation(value, _TENANT, _GAME) == generation
    for bad in [value + "=", value + "\n", value[:-1], "d4.2." + value[5:]]:
        with pytest.raises(b.InitialBrokerUnavailable):
            b._broker_generation(bad, _TENANT, _GAME)
    with pytest.raises(b.InitialBrokerUnavailable):
        b._broker_generation(value, _OTHER_TENANT, _GAME)
    with pytest.raises(b.InitialBrokerUnavailable):
        b._broker_generation(value, _TENANT, UUID(int=999))


@pytest.mark.parametrize("generation", [True, False, 0, -1, 1.0, "1", 2**63, None])
def test_broker_d4_never_coerces_or_reuses_invalid_generation(generation) -> None:
    """数値coercion/overflowをcodec内で拒否する。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    with pytest.raises(b.InitialBrokerUnavailable):
        b._broker_d4(_TENANT, _GAME, generation)


@pytest.mark.parametrize("operation", ["enroll", "start", "resolve"])
def test_broker_command_dispatch_only_roundtrips_immutable_shape(
    operation, monkeypatch
) -> None:
    """dispatchがissuer/SQLを呼ばず、deep frozen要求だけへ分類する。"""
    from dataclasses import FrozenInstanceError

    from pitchlog.recording_rights import initial_grant_broker as b

    def forbidden(*args, **kwargs):
        raise AssertionError("A dispatch must not execute a worker")

    monkeypatch.setattr(b, "_start_initial_game", forbidden)
    monkeypatch.setattr(b, "_issue_initial_grant", forbidden)
    start = _transport_start()
    command = (
        b._EnrollDeviceCommand(start.identity)
        if operation == "enroll"
        else b._ResolveStartCommand(start)
        if operation == "resolve"
        else start
    )
    frame = b._encode_initial_command(command)
    decoded = b._decode_initial_command(frame)
    assert type(decoded) is type(command) and decoded == command
    assert b._encode_initial_command(decoded) == frame
    assert "test-cookie" not in repr(command)
    assert start.device_credential.get_secret_value() not in repr(command)
    with pytest.raises(FrozenInstanceError):
        start.game_id = UUID(int=999)
    with pytest.raises(FrozenInstanceError):
        start.payload.away[0].batting_order = 3


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "version_bool",
        "version_float",
        "unknown",
        "tenant_upper",
        "cookie_number",
        "request_extra",
        "order_bool",
        "role_extra",
        "device_upper",
        "empty_cookie",
        "oversize_cookie",
    ],
)
def test_broker_command_rejects_all_unknown_and_normalized_wire_values(
    mutation,
) -> None:
    """閉member/整数/UUIDの正規化穴をwire逆射影で閉じる。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    value: dict[str, Any] = b._broker_command_source(_transport_start())
    if mutation == "extra":
        value["tenant_context"] = {"valid": True}
    elif mutation == "version_bool":
        value["version"] = True
    elif mutation == "version_float":
        value["version"] = 1.0
    elif mutation == "unknown":
        value["command"] = "advance"
    elif mutation == "tenant_upper":
        value["expected_tenant_id"] = "{00000000-0000-0000-0000-000000000001}"
    elif mutation == "cookie_number":
        value["cookie"] = 1
    elif mutation == "request_extra":
        value["request"]["attempt_id"] = str(UUID(int=8))
    elif mutation == "order_bool":
        value["request"]["away"][0]["batting_order"] = True
    elif mutation == "role_extra":
        value["request"]["away"][0]["fielding_position"]["trusted"] = True
    elif mutation == "device_upper":
        value["request"]["device_id"] = "00000000000000000000000000000005"
    elif mutation == "empty_cookie":
        value["cookie"] = ""
    elif mutation == "oversize_cookie":
        value["cookie"] = "x" * 4097
    with pytest.raises(b.InitialBrokerUnavailable) as caught:
        b._decode_initial_command(b._broker_frame(value))
    assert "test-cookie" not in str(caught.value) and caught.value.__context__ is None


@pytest.mark.parametrize(
    "body",
    [
        b'{"cookie":"sensitive","cookie":"again"}',
        b'{"cookie":NaN}',
        b'{"cookie":Infinity}',
        b'{"cookie":1e999}',
        b"[]",
        b"{",
        b'{"cookie":"sensitive"}\n',
        b'{ "cookie": "sensitive" }',
        b"{}{}",
        b"\xff",
    ],
)
def test_broker_frame_rejects_duplicate_nonfinite_and_ambiguous_json(body) -> None:
    """資格を含む壊れJSONの元例外を露出しない。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    with pytest.raises(b.InitialBrokerUnavailable) as caught:
        b._decode_initial_command(len(body).to_bytes(4, "big") + body)
    assert "sensitive" not in str(caught.value) and caught.value.__context__ is None


@pytest.mark.parametrize(
    "frame", [b"", b"\0\0\0\0", b"\0\0\0\x02{", b"\xff" * 4, b"\0\0\0\x02{}x"]
)
def test_broker_frame_requires_exact_single_bounded_length(frame) -> None:
    """不足/余剰/過大のframeを先拒否する。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    with pytest.raises(b.InitialBrokerUnavailable):
        b._broker_object(frame)


@pytest.mark.parametrize(
    "owner_field",
    [
        "tenant_id",
        "game_id",
        "start_request_id",
        "device_id",
        "attempt_id",
        "request_digest",
    ],
)
def test_broker_postcommit_projection_requires_entire_server_resolved_owner(
    owner_field,
) -> None:
    """receiptに無いgeneration等を仮定せず、実在owner全値を照合する。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    owner, result = _transport_postcommit_shape()
    response = b._postcommit_start_response(result, owner)
    assert (
        b._broker_generation(response.d4, owner.tenant_id, owner.game_id)
        == result.grant.generation
    )
    bad = replace(
        owner,
        **{
            owner_field: b"x" * 32 if owner_field == "request_digest" else UUID(int=999)
        },
    )
    with pytest.raises(b.InitialBrokerUnavailable):
        b._postcommit_start_response(result, bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("game_id", UUID(int=999)),
        ("holder_device_id", UUID(int=999)),
        ("generation", True),
        ("generation", 0),
        ("recovery_generation", "02"),
    ],
)
def test_broker_postcommit_projection_reads_only_same_result_grant(
    field, value
) -> None:
    """独立に渡す世代はなく、同戻り値の共通game/deviceも再照合する。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    owner, result = _transport_postcommit_shape()
    with pytest.raises(b.InitialBrokerUnavailable):
        b._postcommit_start_response(
            replace(result, grant=replace(result.grant, **{field: value})), owner
        )


def test_broker_reply_secret_output_is_explicit_and_same_owner() -> None:
    """合成codec往復だけを検査し、これを実start/commitと呼ばない。"""
    from pydantic import SecretStr

    from pitchlog.api.schemas.game_start import InitialDeviceEnrollmentResponse
    from pitchlog.recording_rights import initial_grant_broker as b

    start = _transport_start()
    owner, result = _transport_postcommit_shape()
    response = b._postcommit_start_response(result, owner)
    for command in [start, b._ResolveStartCommand(start)]:
        reply = b._BrokerReply("started", response)
        frame = b._encode_initial_reply(command, reply)
        assert b._decode_initial_reply(frame, command) == reply
        assert b"test-proof" in frame and "test-proof" not in repr(reply)
        assert "test-proof" not in response.model_dump_json()
    enroll = b._EnrollDeviceCommand(start.identity)
    model = InitialDeviceEnrollmentResponse(
        tenant_id=owner.tenant_id,
        device_id=owner.device_id,
        device_credential=SecretStr("device-secret"),
    )
    frame = b._encode_initial_reply(enroll, b._BrokerReply("enrolled", model))
    assert b"device-secret" in frame and "device-secret" not in model.model_dump_json()
    assert b._decode_initial_reply(frame, enroll).value == model


@pytest.mark.parametrize(
    "mutation",
    [
        "challenge",
        "command",
        "tenant_id",
        "game_id",
        "start_request_id",
        "device_id",
        "d4",
        "extra",
        "epoch_bool",
        "proof_number",
        "unknown_status",
        "failure_with_value",
        "datetime_normalization",
    ],
)
def test_broker_reply_rejects_stale_foreign_extra_and_normalized_values(
    mutation,
) -> None:
    """同frame対応/owner/閉bodyを照合し、未知結果を成功へ落とさない。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    command = _transport_start()
    owner, result = _transport_postcommit_shape()
    value: dict[str, Any] = b._initial_reply_source(
        command, b._BrokerReply("started", b._postcommit_start_response(result, owner))
    )
    if mutation in ("challenge", "command"):
        value[mutation] = str(UUID(int=999))
    elif mutation in ("tenant_id", "game_id", "start_request_id", "device_id"):
        value["value"][mutation] = str(UUID(int=999))
    elif mutation == "d4":
        value["value"]["d4"] += "="
    elif mutation == "extra":
        value["value"]["recordingRight"] = True
    elif mutation == "epoch_bool":
        value["value"]["recovery_generation"] = True
    elif mutation == "proof_number":
        value["value"]["recording_right_proof"] = 123
    elif mutation == "unknown_status":
        value["status"] = "ready"
    elif mutation == "failure_with_value":
        value["status"] = "unresolved"
    elif mutation == "datetime_normalization":
        value["value"]["started_at"] = value["value"]["started_at"].replace(
            "Z", "+00:00"
        )
    with pytest.raises(b.InitialBrokerUnavailable) as caught:
        b._decode_initial_reply(b._broker_frame(value), command)
    assert "test-proof" not in str(caught.value) and caught.value.__context__ is None


@pytest.mark.parametrize("status", ["denied", "conflict", "unavailable", "unresolved"])
def test_broker_failure_and_unknown_preserve_no_value_or_new_attempt(status) -> None:
    """結果不明は型のまま返し、再発行や自動再送へ変換しない。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    command = _transport_start()
    reply = b._BrokerReply(status)
    assert (
        b._decode_initial_reply(b._encode_initial_reply(command, reply), command)
        == reply
    )
    assert reply.value is None


def test_broker_real_unix_peer_credential_and_eof_are_enforced(monkeypatch) -> None:
    """実socketpairの資格/終端を検査。20002配置/製品worker成功ではない。"""
    import os
    import socket
    import threading
    from time import monotonic

    from pitchlog.recording_rights import initial_grant_broker as b

    left, right = socket.socketpair()
    try:
        if os.getuid() != 20002 or os.getgid() != 20002:
            with pytest.raises(b.InitialBrokerUnavailable):
                b._check_broker_peer(left)
        # helperの実peer照合を実UID/GIDで確認。製品固定値はmonkeypatch終了時に戻る。
        monkeypatch.setattr(b, "_BROKER_SERVER_UID", os.getuid())
        monkeypatch.setattr(b, "_BROKER_SERVER_GID", os.getgid())
        b._check_broker_peer(left)
        wire = b._encode_initial_reply(_transport_start(), b._BrokerReply("unresolved"))

        def write():
            for part in [wire[:2], wire[2:5], wire[5:]]:
                right.sendall(part)
            right.shutdown(socket.SHUT_WR)

        sender = threading.Thread(target=write)
        sender.start()
        try:
            assert b._broker_receive(left, monotonic() + 1) == wire
        finally:
            sender.join(timeout=2)
        assert not sender.is_alive()
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize("kind", ["early_eof", "extra", "deadline"])
def test_broker_actual_socket_rejects_eof_extra_and_expired_deadline(kind) -> None:
    """Owned socketだけで失敗を実観測し、待機期限を延長しない。"""
    import socket
    from time import monotonic

    from pitchlog.recording_rights import initial_grant_broker as b

    left, right = socket.socketpair()
    try:
        wire = b._encode_initial_reply(_transport_start(), b._BrokerReply("unresolved"))
        if kind == "early_eof":
            right.sendall(wire[:-1])
            right.shutdown(socket.SHUT_WR)
        elif kind == "extra":
            right.sendall(wire + b"x")
            right.shutdown(socket.SHUT_WR)
        with pytest.raises(b.InitialBrokerUnavailable):
            b._broker_receive(
                left, monotonic() - 1 if kind == "deadline" else monotonic() + 1
            )
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize(
    "kind,delay,budget,failure",
    [
        ("start", 3.0, 10.0, None),
        ("enroll", 3.0, 2.0, "timeout"),
        ("resolve", 3.0, 2.0, "timeout"),
        ("start", 10.0, 10.0, "timeout"),
        ("start", 0.1, 10.0, "early_eof"),
        ("start", 0.1, 10.0, "extra"),
    ],
)
def test_broker_client_uses_one_operation_deadline_through_partial_response(
    monkeypatch, kind, delay, budget, failure
) -> None:
    """実call/codec/peer/受信を通し、固定時計で部分受信と総期限を検査する。"""
    import struct

    from pitchlog.recording_rights import initial_grant_broker as b

    start = _transport_start()
    command = (
        b._EnrollDeviceCommand(start.identity)
        if kind == "enroll"
        else b._ResolveStartCommand(start)
        if kind == "resolve"
        else start
    )
    reply = b._BrokerReply("unavailable" if kind == "enroll" else "unresolved")
    wire = b._encode_initial_reply(command, reply)
    chunks = [wire[:2], wire[2:4], wire[4:], b""]
    if failure == "early_eof":
        chunks = [wire[:2], b""]
    elif failure == "extra":
        chunks[-1] = b"x"
    clock = [100.0]
    timeouts: list[float] = []
    deadlines: list[float] = []
    events: list[str] = []

    class Channel:
        """socket期限に従う一回通信を、実時間を待たずに供給する。"""

        def __enter__(self):
            events.append("open")
            return self

        def __exit__(self, *_):
            events.append("close")

        def settimeout(self, value):
            timeouts.append(value)
            deadlines.append(clock[0] + value)

        def connect(self, path):
            assert path == "/owned/initial.sock"
            events.append("connect")
            clock[0] += 0.25

        def getsockopt(self, *_):
            events.append("peer")
            return struct.pack("3i", 123, 20002, 20002)

        def sendall(self, frame):
            assert frame == b._encode_initial_command(command)
            events.append("send")
            clock[0] += 0.25

        def shutdown(self, _):
            events.append("shutdown")

        def recv(self, wanted):
            wait = delay if len(chunks) == 4 else 0.1
            if wait >= timeouts[-1]:
                clock[0] += timeouts[-1]
                raise TimeoutError
            clock[0] += wait
            part = chunks.pop(0)
            assert len(part) <= wanted
            return part

    endpoint = b._BrokerEndpoint(Path("/owned/initial.sock"), 1, 2, 20003)
    monkeypatch.setattr(b, "_load_broker_endpoint", lambda: endpoint)
    monkeypatch.setattr(b, "_check_broker_socket", lambda _: events.append("socket"))
    monkeypatch.setattr(b, "monotonic", lambda: clock[0])
    monkeypatch.setattr(b.socket, "socket", lambda *_: Channel())
    client = b._InitialBrokerClient()
    if failure is None:
        assert client.call(command) == reply
        assert not chunks
        assert clock[0] > 102.0
    else:
        with pytest.raises(b.InitialBrokerUnavailable):
            client.call(command)
    assert timeouts[0] == budget
    assert deadlines == pytest.approx([100.0 + budget] * len(deadlines))
    assert all(0 < value <= budget for value in timeouts)
    assert all(a > z for a, z in zip(timeouts, timeouts[1:], strict=False))
    assert events == [
        "socket",
        "open",
        "connect",
        "peer",
        "socket",
        "send",
        "shutdown",
        "close",
    ]


def test_broker_client_rejects_changed_start_before_opening_socket(monkeypatch) -> None:
    """開始待機の延長も閉codec拒否を迂回せず、送信や再試行を起こさない。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    command = _transport_start()
    object.__setattr__(command.payload.away[0], "batting_order", True)
    endpoint = b._BrokerEndpoint(Path("/owned/initial.sock"), 1, 2, 20003)
    monkeypatch.setattr(b, "_load_broker_endpoint", lambda: endpoint)
    monkeypatch.setattr(
        b.socket, "socket", lambda *_: pytest.fail("codec拒否後にsocketを作らない")
    )
    with pytest.raises(b.InitialBrokerUnavailable):
        b._InitialBrokerClient().call(command)


def test_broker_endpoint_and_client_fail_closed_without_root_supply(
    tmp_path, monkeypatch
) -> None:
    """所有uid1000配置をroot設定として採用せず、任意path引数も受けない。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    target = tmp_path / "endpoint.json"
    target.write_text("{}")
    monkeypatch.setattr(b, "_BROKER_ENDPOINT_PATH", target)
    with pytest.raises(b.InitialBrokerUnavailable):
        b._InitialBrokerClient()
    with pytest.raises(TypeError):
        cast(Any, b._InitialBrokerClient)(target)
    with pytest.raises(b.InitialBrokerUnavailable):
        b._broker_trusted_parents(Path("relative.sock"))


def test_broker_forced_nested_changes_never_bypass_wire_revalidation() -> None:
    """model_construct/低水準改変もcodec全wire照合で成功へ採用しない。"""
    from pitchlog.api.schemas.game_start import InitialGameStartResponse
    from pitchlog.recording_rights import initial_grant_broker as b

    start = _transport_start()
    object.__setattr__(start.payload.away[0], "batting_order", True)
    with pytest.raises(b.InitialBrokerUnavailable):
        b._encode_initial_command(start)
    start = _transport_start()
    owner, result = _transport_postcommit_shape()
    good = b._postcommit_start_response(result, owner)
    bad = cast(Any, InitialGameStartResponse.model_construct)(
        **{**vars(good), "recovery_generation": True}
    )
    with pytest.raises(b.InitialBrokerUnavailable):
        b._encode_initial_reply(start, b._BrokerReply("started", bad))


def test_broker_actual_socket_inode_mode_owner_and_replacement(
    tmp_path, monkeypatch
) -> None:
    """実statで対向検査。uid1000の低層機構確認でroot配置成功を主張しない。"""
    import os
    import socket

    from pitchlog.recording_rights import initial_grant_broker as b

    path = tmp_path / "peer.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            # owned pytest pathの長さをAF_UNIX制限へ持ち込まない。
            peer.bind(f"/proc/self/fd/{directory}/peer.sock")
        finally:
            os.close(directory)
        path.chmod(0o660)
        info = path.stat(follow_symlinks=False)
        endpoint = b._BrokerEndpoint(path, info.st_dev, info.st_ino, info.st_gid)
        if os.getuid() != 20002:
            with pytest.raises(b.InitialBrokerUnavailable):
                b._validate_broker_socket_observation(info, endpoint)
        monkeypatch.setattr(b, "_BROKER_SERVER_UID", os.getuid())
        b._validate_broker_socket_observation(info, endpoint)
        for change in [
            dict(inode=info.st_ino + 1),
            dict(device=info.st_dev + 1),
            dict(group=info.st_gid + 1),
        ]:
            with pytest.raises(b.InitialBrokerUnavailable):
                b._validate_broker_socket_observation(info, replace(endpoint, **change))
        path.chmod(0o666)
        with pytest.raises(b.InitialBrokerUnavailable):
            b._validate_broker_socket_observation(path.stat(), endpoint)
        path.unlink()
        path.write_text("replacement")
        with pytest.raises(b.InitialBrokerUnavailable):
            b._validate_broker_socket_observation(path.stat(), endpoint)


def test_broker_forced_raw_secret_response_never_reaches_warning_or_log(
    recwarn,
) -> None:
    """低水準型すり抜けをserializer前に拒否し、警告への原値流出も防ぐ。"""
    from pitchlog.api.schemas.game_start import InitialGameStartResponse
    from pitchlog.recording_rights import initial_grant_broker as b

    command = _transport_start()
    owner, result = _transport_postcommit_shape()
    good = b._postcommit_start_response(result, owner)
    bad = cast(Any, InitialGameStartResponse.model_construct)(
        **{**vars(good), "recording_right_proof": "raw-private-value"}
    )
    with pytest.raises(b.InitialBrokerUnavailable) as caught:
        b._encode_initial_reply(command, b._BrokerReply("started", bad))
    assert not recwarn.list and "raw-private-value" not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "inner",
    [True, 123, {"secret": "raw-private-value"}, ["raw-private-value"], "\ud800"],
)
def test_broker_secret_wrapper_does_not_make_invalid_inner_types_valid(inner) -> None:
    """SecretStrの直接構築/不正Unicodeでも固定外形で拒否する。"""
    from pydantic import SecretStr

    from pitchlog.recording_rights import initial_grant_broker as b

    with pytest.raises(b.InitialBrokerUnavailable) as caught:
        b._BrokerIdentity(UUID(int=1), UUID(int=2), cast(Any, SecretStr)(inner))
    assert "raw-private-value" not in str(caught.value)


def _b1_verifier_config():
    """資格を含まない検証専用接続の純fixtureを作る。"""
    from datetime import UTC, datetime

    from pitchlog.recording_rights import initial_grant_broker as b

    return b._ActorConfiguration(
        (
            "postgresql+psycopg://pitchlog_initial_actor@/fixture?ho"
            "st=%2Fowned-socket&sslmode=disable"
        ),
        "123",
        42,
        "fixture",
        datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize("index", range(15))
def test_b1_verifier_rejects_every_changed_checkout_identity(index) -> None:
    """role7属性/membership/GUC/実DB identityを全欄厳密に照合する。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    config = _b1_verifier_config()
    row = (
        [b._INITIAL_AUTH_VERIFIER_ROLE] * 2
        + [True]
        + [False] * 6
        + [0, None, "fixture", 42, config.postmaster_started_at, 3]
    )
    b._validate_auth_verifier_observation(tuple(row), config)
    bad = row.copy()
    bad[index] = 0 if type(row[index]) is bool else "invalid"
    with pytest.raises(b.InitialBrokerUnavailable):
        b._validate_auth_verifier_observation(tuple(bad), config)


@pytest.mark.parametrize(
    "url",
    [
        (
            "postgresql+psycopg://pitchlog_app@/fixture?host=%2Fowne"
            "d-socket&sslmode=disable"
        ),
        (
            "postgresql+psycopg://pitchlog_initial_actor:private@/fi"
            "xture?host=%2Fowned-socket&sslmode=disable"
        ),
        (
            "postgresql+psycopg://pitchlog_initial_actor@127.0.0.1/f"
            "ixture?sslmode=disable"
        ),
        (
            "postgresql+psycopg://pitchlog_initial_actor@/fixture?ho"
            "st=%2Fowned-socket&service=evil"
        ),
        (
            "postgresql+psycopg://pitchlog_initial_actor@/other?host"
            "=%2Fowned-socket&sslmode=disable"
        ),
    ],
)
def test_b1_verifier_cannot_change_endpoint_or_use_app_password_tcp(url) -> None:
    """Root actorと同じUnix endpointの専用user以外は拒否する。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    with pytest.raises(b.InitialBrokerUnavailable):
        b._initial_auth_verifier_url(replace(_b1_verifier_config(), database_url=url))


def test_b1_verifier_runtime_requires_root_active_signer_and_expires(
    monkeypatch,
) -> None:
    """pureでは実認証を偽装せず、runtime発行/失効だけを検査する。"""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from pydantic import SecretStr

    from pitchlog.authz import verified_tenant
    from pitchlog.authz.token_presentation import TokenPresentation
    from pitchlog.recording_rights import initial_grant_broker as b

    signer = TokenPresentation(bytes(range(32)))
    monkeypatch.setattr(verified_tenant, "_ACTIVE_PRESENTATION", (signer, signer._key))
    monkeypatch.setattr(b.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        b,
        "_actor_state",
        lambda _: SimpleNamespace(configuration=_b1_verifier_config()),
    )
    engine = MagicMock()
    monkeypatch.setattr(b, "create_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(b.event, "listen", lambda *args: None)
    with pytest.raises(b.InitialBrokerUnavailable):
        b._load_initial_auth_verifier_runtime(
            object(), TokenPresentation(bytes(range(32)))
        )
    runtime = b._load_initial_auth_verifier_runtime(object(), signer)
    assert "pitchlog_initial_auth_verifier" in b._initial_auth_verifier_url(
        _b1_verifier_config()
    )
    monkeypatch.setattr(verified_tenant, "verify_tenant_id", lambda *args: None)
    assert b._verify_initial_cookie(runtime, SecretStr("invalid-cookie")) is None
    b._close_initial_auth_verifier_runtime(runtime)
    engine.dispose.assert_called_once()
    with pytest.raises(b.InitialBrokerUnavailable):
        b._verify_initial_cookie(runtime, SecretStr("private-sentinel"))
    with pytest.raises(b.InitialBrokerUnavailable):
        b._verify_initial_cookie(object(), SecretStr("private-sentinel"))
    monkeypatch.setattr(b.os, "geteuid", lambda: 20002)
    with pytest.raises(b.InitialBrokerUnavailable):
        b._load_initial_auth_verifier_runtime(object(), signer)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "binding",
        "precheck",
        "insert",
        "wrong_result",
        "commit_check",
        "commit_unknown",
        "after_commit",
    ],
)
def test_b2_broker_generates_once_and_never_returns_before_commit(
    fault: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定順序/確定取消/commit不明を分け、資格とdriver例外を表示しない。"""
    import traceback
    from contextlib import contextmanager

    from pydantic import SecretStr
    from test_authz_tenant_context import make_tenant_context

    from pitchlog.recording_rights import initial_grant_broker as broker
    from pitchlog.repositories import rg1, transaction
    from pitchlog.repositories.tokens import TenantOperationResult

    context = make_tenant_context(_TENANT)
    actor = cast(Any, object())
    order = []
    secret = "PUBLIC-SYNTHETIC-DEVICE-CREDENTIAL-SENTINEL"
    monkeypatch.setattr(broker, "_initial_actor_engine", lambda runtime: None)
    monkeypatch.setattr(broker, "uuid4", lambda: _DEVICE)
    generated = []

    def generate(size):
        generated.append(size)
        return secret

    monkeypatch.setattr(broker.secrets, "token_urlsafe", generate)

    def step(name):
        order.append(name)
        if fault == name:
            raise RuntimeError(secret)

    class Handle:
        """型付き戻り値と実呼出順だけを観測する代役。"""

        def run_function(self, token):
            step("insert")
            assert token.device_id == _DEVICE
            assert token.credential_digest == broker._credential_digest(secret)
            return TenantOperationResult(
                ((_OTHER_DEVICE if fault == "wrong_result" else _DEVICE,),)
            )

    @contextmanager
    def scope(binding):
        assert binding.context is context and binding.runtime is actor
        yield Handle()
        binding.commit_attempted = True
        step("commit_unknown")
        binding.commit_completed = True
        step("after_commit")

    monkeypatch.setattr(transaction, "_initial_enrollment_transaction_scope", scope)
    monkeypatch.setattr(
        broker, "_verify_business_binding", lambda *args: step("binding")
    )
    monkeypatch.setattr(rg1, "read_rg1_open", lambda *args: step("precheck"))
    monkeypatch.setattr(
        rg1, "assert_rg1_open_before_commit", lambda *args: step("commit_check")
    )
    if fault is None:
        response = broker._enroll_initial_device(context, actor)
        assert response.tenant_id == _TENANT and response.device_id == _DEVICE
        assert type(response.device_credential) is SecretStr
        assert response.device_credential.get_secret_value() == secret
        assert secret not in repr(response)
        assert order == [
            "binding",
            "precheck",
            "insert",
            "commit_check",
            "commit_unknown",
            "after_commit",
        ]
    else:
        error_type = (
            broker._InitialEnrollmentOutcomeUnknown
            if fault in {"commit_unknown", "after_commit"}
            else InitialGrantUnavailable
        )
        with pytest.raises(error_type) as caught:
            broker._enroll_initial_device(context, actor)
        assert secret not in "".join(traceback.format_exception(caught.value))
        assert caught.value.__context__ is None
    assert generated == [32]


@pytest.mark.parametrize(
    "operation",
    [
        "enroll",
        "start",
        "resolve",
        "pending",
        "denied",
        "enroll_unknown",
        "start_unknown",
    ],
)
def test_worker_dispatch_closed_real_entry_selection(operation, monkeypatch):
    """純代役は分岐/起源だけを検査し、DB認可/commit成功の証拠にはしない。"""
    from contextlib import contextmanager
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from test_authz_tenant_context import make_tenant_context

    from pitchlog.recording_rights import initial_grant_broker as b
    from pitchlog.repositories import tenant_context_issuance
    from pitchlog.repositories.game_start import InitialStartReceipt

    command = _transport_start()
    context = make_tenant_context(command.identity.expected_tenant_id)
    calls = []

    class Fence:
        generation = 1

        def assert_held(self):
            calls.append("held")

    class Source:
        @contextmanager
        def recovery_fence(self):
            calls.append("fence")
            yield Fence()

    state = SimpleNamespace(actor=object(), verifier=object(), source=Source())
    monkeypatch.setattr(b, "_worker_state", lambda runtime: state)

    def verify(cookie, tenant, runtime):
        calls.append("cookie")
        assert tenant == context.tenant_id
        return None if operation == "denied" else (context, datetime.now(UTC))

    monkeypatch.setattr(
        tenant_context_issuance, "_issue_initial_broker_context", verify
    )

    def enroll(ctx, runtime):
        calls.append("enroll")
        if operation == "enroll_unknown":
            raise b._InitialEnrollmentOutcomeUnknown("synthetic")
        return b.InitialDeviceEnrollmentResponse(
            tenant_id=ctx.tenant_id,
            device_id=_DEVICE,
            device_credential=__import__("pydantic").SecretStr(
                "synthetic-enrollment-raw"
            ),
        )

    monkeypatch.setattr(b, "_enroll_initial_device", enroll)

    def result(owner):
        return b._InitialStartedGame(
            b.InitialGrant(owner.game_id, 1, "1", owner.device_id, "synthetic-proof"),
            InitialStartReceipt(owner, datetime.now(UTC), UUID(int=90), UUID(int=91)),
        )

    def start(ctx, runtime, bound, *args):
        calls.append("start")
        if operation == "start_unknown":
            raise RuntimeError("synthetic-private-driver")
        # intentが実解決したattemptは候補と異なり得る。
        return result(replace(bound.owner, attempt_id=UUID(int=999)))

    monkeypatch.setattr(b, "_start_initial_game", start)

    def resolve(original, ctx, state, fence):
        calls.append("resolve")
        if operation == "pending":
            return None
        return result(
            b._worker_start_bound(original, ctx.tenant_id, UUID(int=999)).owner
        )

    monkeypatch.setattr(b, "_worker_resolve_start", resolve)
    if operation in {"enroll", "enroll_unknown"}:
        command = b._EnrollDeviceCommand(command.identity)
    elif operation in {"resolve", "pending"}:
        command = b._ResolveStartCommand(command)
        monkeypatch.setattr(
            b, "uuid4", lambda: pytest.fail("resolve generated new UUID")
        )
    if operation == "enroll_unknown":
        with pytest.raises(b.InitialBrokerUnavailable):
            b._dispatch_initial_command(command, object())
        assert calls == ["cookie", "enroll"]
        return
    reply = b._dispatch_initial_command(command, object())
    expected = {
        "enroll": "enrolled",
        "start": "started",
        "resolve": "started",
        "pending": "unresolved",
        "denied": "denied",
        "start_unknown": "unresolved",
    }[operation]
    assert reply.status == expected
    assert calls[0] == "cookie"
    if operation in {"pending", "start_unknown", "denied"}:
        assert reply.value is None
    if operation == "resolve":
        assert "start" not in calls and "enroll" not in calls
    if reply.value is not None:
        frame = b._encode_initial_reply(command, reply)
        assert b._decode_initial_reply(frame, command).status == expected


@pytest.mark.parametrize("queued_seconds", [0.0, 1.01])
@pytest.mark.parametrize("fault", [False, True])
def test_worker_socket_one_frame_and_queue_expiry(
    queued_seconds, fault, monkeypatch, capsys
):
    """純socket対向でqueue期限前DB0と例外非露出を確認する。peer実証はPG側。"""
    import socket

    from pitchlog.recording_rights import initial_grant_broker as b

    command = b._EnrollDeviceCommand(_transport_start().identity)
    left, right = socket.socketpair()
    calls = []
    monkeypatch.setattr(b, "_worker_peer", lambda *_: calls.append("peer"))
    monkeypatch.setattr(b, "_check_broker_socket", lambda *_: None)

    def dispatch(command, runtime):
        calls.append("dispatch")
        if fault:
            raise RuntimeError("PRIVATE-WORKER-SENTINEL")
        return b._BrokerReply("denied")

    monkeypatch.setattr(b, "_dispatch_initial_command", dispatch)
    try:
        right.sendall(b._encode_initial_command(command))
        right.shutdown(socket.SHUT_WR)
        b._worker_connection(
            left, cast(Any, object()), object(), b.monotonic() - queued_seconds
        )
        try:
            received = right.recv(4096)
        except ConnectionResetError:
            assert queued_seconds > 1
            received = b""
        if queued_seconds > 1 or fault:
            assert not received
        else:
            assert b._decode_initial_reply(received, command).status == "denied"
        assert ("dispatch" in calls) == (queued_seconds < 1)
        assert "PRIVATE-WORKER-SENTINEL" not in str(capsys.readouterr())
    finally:
        left.close()
        right.close()


def test_worker_root_and_runtime_are_closed(monkeypatch):
    """非root起動/偽runtimeを実設定読取やSQLより先に拒否する。"""
    from pitchlog.recording_rights import initial_grant_broker as b

    monkeypatch.setattr(b.os, "geteuid", lambda: 20003)
    with pytest.raises(b.InitialBrokerUnavailable):
        b.serve_initial_broker(Path("/not-read"), object(), cast(Any, object()))
    with pytest.raises(b.InitialBrokerUnavailable):
        b._worker_state(object())


def test_worker_queue_expiration_does_not_wait_for_busy_workers(monkeypatch):
    """処理slot3つがbusyでも、mainは期限切れqueueを閉じてDB0を保つ。"""
    import queue

    from pitchlog.recording_rights import initial_grant_broker as b

    class Channel:
        closed = False

        def close(self):
            self.closed = True

    expired, fresh = Channel(), Channel()
    pending = queue.Queue(maxsize=3)
    pending.put((expired, 0))
    pending.put((fresh, 1.5))
    monkeypatch.setattr(b, "monotonic", lambda: 2)
    b._expire_initial_queue(pending)
    assert expired.closed and not fresh.closed
    assert pending.get_nowait() == (fresh, 1.5)
    pending.task_done()
    pending.join()


def test_worker_bootstrap_configures_rg1_after_real_subject_drop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """実serveの順序をOS代役で検査する。実peer/DB成功はこの純対向で証明しない。"""
    from types import SimpleNamespace

    from pitchlog import durable_rights_ledger
    from pitchlog.authz.token_presentation import TokenPresentation
    from pitchlog.recording_rights import initial_grant_broker as b
    from pitchlog.recording_rights import rg1_lifecycle as rg1

    uid = [0]
    gid = [0]
    priv = [False]
    configured = [False]
    events = []
    endpoint = tmp_path / "endpoint.json"
    sock = tmp_path / "broker.sock"

    def root_event(name):
        assert uid[0] == 0
        events.append(name)

    def config(_):
        root_event("root_config")
        return dict(
            socket_path=str(sock),
            actor_config="/root-actor",
            ledger_endpoint="/root-ledger",
            rg1_client_config="/root-rg1",
        )

    def actor(*_):
        root_event("root_actor")
        return object()

    def verifier(*_):
        root_event("root_verifier")
        return object()

    def ledger(*_):
        assert uid[0] == gid[0] == 20002 and priv[0] and configured[0]
        events.append("ledger_subject_check")
        return object()

    def setuid(value):
        uid[0] = value
        events.append("drop_uid")

    def setgid(value):
        gid[0] = value

    def prctl(*_):
        assert uid[0] == gid[0] == 20002
        priv[0] = True
        events.append("no_new_privs")
        return 0

    def configure(path):
        assert path == Path("/root-rg1")
        assert uid[0] == 20002 and priv[0]
        assert endpoint.exists()
        configured[0] = True
        events.append("rg1_subject_check")

    class Listener:
        """socket作成を行わず、bindとlistenの実呼出順だけを観測する。"""

        def bind(self, path):
            root_event("root_bind")
            Path(path).touch()

        def listen(self, count):
            assert (
                count == 3 and uid[0] == gid[0] == 20002 and priv[0] and configured[0]
            )
            events.append("listen_after_drop")

        def settimeout(self, _):
            pass

        def accept(self):
            raise RuntimeError("synthetic service end")

        def close(self):
            pass

    class Thread:
        """workerを起動せず、閉3slotの生成だけを数える。"""

        def __init__(self, **kwargs):
            assert kwargs["daemon"] is True

        def start(self):
            events.append("worker_slot")

        def join(self, timeout):
            assert timeout == 2

    monkeypatch.setattr(b, "_worker_configuration", config)
    monkeypatch.setattr(b, "_load_initial_actor_runtime", actor)
    monkeypatch.setattr(b, "_load_initial_auth_verifier_runtime", verifier)
    monkeypatch.setattr(durable_rights_ledger, "DurableLedger", ledger)
    monkeypatch.setattr(rg1, "configure_runtime", configure)
    monkeypatch.setattr(b, "_BROKER_ENDPOINT_PATH", endpoint)
    monkeypatch.setattr(b, "_broker_trusted_parents", lambda _: None)
    monkeypatch.setattr(
        b, "_check_broker_socket", lambda _: root_event("root_socket_check")
    )
    monkeypatch.setattr(b.socket, "socket", lambda *_: Listener())
    monkeypatch.setattr(b.os, "geteuid", lambda: uid[0])
    monkeypatch.setattr(b.os, "getegid", lambda: gid[0])
    monkeypatch.setattr(b.os, "setuid", setuid)
    monkeypatch.setattr(b.os, "setgid", setgid)
    monkeypatch.setattr(
        b.os,
        "setgroups",
        lambda groups: (
            root_event("drop_groups") if groups == [] else pytest.fail("groups")
        ),
    )
    monkeypatch.setattr(b.os, "chown", lambda *_: root_event("root_socket_owner"))
    monkeypatch.setattr(b.os, "chmod", lambda *_: root_event("root_socket_mode"))
    monkeypatch.setattr(b.ctypes, "CDLL", lambda *a, **kw: SimpleNamespace(prctl=prctl))
    monkeypatch.setattr(b.threading, "Thread", Thread)
    monkeypatch.setattr(b, "_close_initial_actor_runtime", lambda _: None)
    monkeypatch.setattr(b, "_close_initial_auth_verifier_runtime", lambda _: None)
    before = set(b._WORKER_STATES)
    with pytest.raises(b.InitialBrokerUnavailable):
        b.serve_initial_broker(
            Path("/root-config"),
            TokenPresentation(bytes(range(32))),
            V12Box("public-vector", bytes(range(32))),
        )
    assert set(b._WORKER_STATES) == before
    assert events.index("root_actor") < events.index("drop_uid")
    assert events.index("root_verifier") < events.index("drop_uid")
    assert events.index("root_socket_check") < events.index("drop_uid")
    assert (
        events.index("drop_uid")
        < events.index("no_new_privs")
        < events.index("rg1_subject_check")
        < events.index("listen_after_drop")
    )
    assert events.index("rg1_subject_check") < events.index("ledger_subject_check")
    assert events.index("ledger_subject_check") < events.index("listen_after_drop")
    assert events.count("worker_slot") == 3


@pytest.mark.parametrize(
    "uid,gid,valid",
    [(0, 0, False), (20002, 0, False), (0, 20002, False), (20002, 20002, True)],
)
def test_worker_actual_ledger_constructor_subject_requirements(
    uid, gid, valid, monkeypatch, tmp_path
):
    """実constructor/endpointの主体条件を検査する。rootFS/peerの成功証拠は別実走。"""
    import os
    import stat
    from types import SimpleNamespace

    from pitchlog.durable_rights_ledger import (
        DurableLedger,
        LedgerUnavailable,
        authority,
    )

    endpoint = dict(
        schema_version=2,
        authority_uid=20001,
        authority_gid=20001,
        client_uid=20002,
        client_gid=20002,
        role="generation",
        socket_path="/owned/ledger.sock",
        timeout=1.0,
    )
    monkeypatch.setattr(authority, "_read_root_json", lambda *args: dict(endpoint))
    monkeypatch.setattr(authority.os, "geteuid", lambda: uid)
    monkeypatch.setattr(authority.os, "getegid", lambda: gid)
    original_stat = os.stat

    def directory(_):
        return os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    def metadata(path, *args, **kwargs):
        if path == "ledger.sock" and "dir_fd" in kwargs:
            return SimpleNamespace(
                st_mode=stat.S_IFSOCK | 0o660, st_uid=0, st_gid=20002
            )
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(authority, "_trusted_directory", directory)
    monkeypatch.setattr(authority.os, "stat", metadata)
    if valid:
        ledger = DurableLedger(Path("/owned/endpoint.json"))
        assert (
            ledger._target["client_uid"] == uid and ledger._target["client_gid"] == gid
        )
    else:
        with pytest.raises(LedgerUnavailable):
            DurableLedger(Path("/owned/endpoint.json"))


@pytest.mark.parametrize("mismatch", [False, True])
def test_business_binding_static_import_preserves_identity_check(
    monkeypatch: pytest.MonkeyPatch, mismatch: bool
) -> None:
    """固定RG1型で実scopeのDB識別全値を照合し、不一致を拒否する。"""
    import json
    from types import SimpleNamespace

    from pitchlog.recording_rights import initial_grant_broker as broker

    config = _b1_verifier_config()
    body = json.dumps(
        {
            "system_identifier": "124" if mismatch else config.system_identifier,
            "database_oid": config.database_oid,
            "database_name": config.database_name,
            "postmaster_started_at": config.postmaster_started_at.isoformat(),
            "backend_pid": 1,
        }
    )

    class Scope:
        def run_function(self, token: object) -> object:
            assert token is not None
            return SimpleNamespace(rows=((body,),))

    monkeypatch.setattr(
        broker, "_actor_state", lambda runtime: SimpleNamespace(configuration=config)
    )
    if mismatch:
        with pytest.raises(InitialGrantUnavailable, match="実scope binding"):
            broker._verify_business_binding(cast(Any, Scope()), object())
    else:
        broker._verify_business_binding(cast(Any, Scope()), object())
