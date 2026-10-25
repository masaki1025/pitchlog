"""新5の隔離候補で再交付・端末境界・復旧世代停止を検証する。"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace
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
