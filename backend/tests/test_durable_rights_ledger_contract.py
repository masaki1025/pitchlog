"""単一Protocol、固定DDL/ACL、有限取消と拒否境界を検査する。"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
from time import sleep
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from pitchlog.durable_rights_ledger import (
    DurableLedger,
    LedgerEndpoints,
    LedgerOutcomeUnconfirmed,
    LedgerUnavailable,
    adapter,
)
from pitchlog.recording_rights.initial_grant import (
    DurableGenerationSource,
    RecoveryEpochFence,
    ReservedGeneration,
)

_PACKAGE = Path(adapter.__file__).parent


def test_fixed_manifest_and_single_supplier_protocol() -> None:
    """固定DDLと全API/roleを照合し、Protocol/DTOコピーを拒否する。"""
    manifest = json.loads((_PACKAGE / "manifest.json").read_text())
    ddl = (_PACKAGE / "schema.sql").read_bytes()
    assert hashlib.sha256(ddl).hexdigest() == manifest["ddl_sha256"]
    assert set(manifest) == {
        "schema_version",
        "postgres_version",
        "schema",
        "ddl_sha256",
        "tables",
        "roles",
        "functions",
        "synchronous_peer",
        "client",
        "boundaries",
        "protocol_source",
        "required_settings",
        "identity",
        "timeout_seconds",
        "witness",
        "authority",
    }
    assert manifest["tables"] == ["state", "highwater", "reservations"]
    assert manifest["required_settings"] == {
        "fsync": "on",
        "full_page_writes": "on",
        "synchronous_commit": "on",
        "synchronous_standby_names": "FIRST 1 (ledger_standby)",
    }
    assert manifest["client"] == {
        "psycopg": "3.3.4",
        "minimum_libpq": 170000,
        "cancel_safe_required": True,
    }
    assert manifest["identity"]["timeline"] == 1
    assert manifest["timeout_seconds"]["reconnect_cancelled_connection"] is False
    assert set(manifest["functions"]) == {
        "identity()",
        "epoch_fence()",
        "reservation(uuid,uuid,uuid,uuid)",
        "reserve(uuid,uuid,uuid,uuid)",
        "claim(uuid,uuid,uuid,uuid)",
        "advance_epoch(bigint)",
        "audit_page(bigint,integer)",
        "confirm_state(bigint,bigint,bigint)",
        "reconcile(uuid,uuid,uuid,uuid,bigint,bigint,boolean,boolean,bigint)",
    }
    assert manifest["boundaries"]["business_restart_without_close_proof"] is False
    assert manifest["boundaries"]["public_epoch_advance"] is False
    assert (
        hashlib.sha256((_PACKAGE / "business_identity.sql").read_bytes()).hexdigest()
        == manifest["authority"]["business_identity_ddl_sha256"]
    )
    for filename, key in (
        ("adapter.py", "adapter_sha256"),
        ("authority.py", "source_sha256"),
    ):
        assert (
            hashlib.sha256((_PACKAGE / filename).read_bytes()).hexdigest()
            == (manifest["authority"][key])
        )
    assert manifest["boundaries"]["promotion_issuance"] is False
    assert adapter.ReservedGeneration is ReservedGeneration
    assert adapter.RecoveryEpochFence is RecoveryEpochFence
    assert DurableGenerationSource in DurableLedger.__bases__
    source = Path(inspect.getfile(ReservedGeneration)).read_bytes()
    assert hashlib.sha256(source).hexdigest() == manifest["protocol_source"]["sha256"]
    assert b"FOR SHARE" in ddl and b"FOR UPDATE" in ddl
    assert (
        ddl.count(
            b"SECURITY DEFINER SET search_path = pg_catalog, "
            b"pitchlog_ledger, pg_temp AS"
        )
        == 9
    )
    assert b"REVOKE ALL ON ALL TABLES" in ddl
    tree = ast.parse(Path(adapter.__file__).read_text())
    assert not any(
        isinstance(n, ast.ClassDef)
        and n.name
        in {"ReservedGeneration", "RecoveryEpochFence", "DurableGenerationSource"}
        for n in ast.walk(tree)
    )


@pytest.mark.parametrize("value", [True, False, 0, -1, 2**63, 1.0, "1", None])
def test_bigint_boundary_rejects_untyped_values(value: object) -> None:
    """bool・float・上限越えをbigintとして再解釈しない。"""
    with pytest.raises(LedgerUnavailable):
        adapter._positive(value)


@pytest.mark.parametrize("value", [True, 0, -1, float("inf"), float("nan"), "1", 31])
def test_endpoint_timeout_is_finite_and_redacted(value: Any) -> None:
    """資格をreprへ出さず、未対応期限を接続前に拒否する。"""
    with pytest.raises(LedgerUnavailable):
        LedgerEndpoints(
            "test-primary", "test-standby", "test-business", "test-control", value
        )
    endpoints = LedgerEndpoints(
        "test-primary", "test-standby", "test-business", "test-control"
    )
    assert "test-primary" not in repr(endpoints)


@pytest.mark.parametrize("version,capable", [(160000, True), (180000, False)])
def test_legacy_cancel_is_refused_before_connection(
    monkeypatch: pytest.MonkeyPatch, version: int, capable: bool
) -> None:
    """旧libpqのlegacy fallbackは接続前に失敗閉鎖する。"""
    monkeypatch.setattr(adapter.pq, "version", lambda: version)
    monkeypatch.setattr(adapter.capabilities, "has_cancel_safe", lambda: capable)
    calls = []
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(LedgerUnavailable, match="^ledger unavailable$"):
        adapter._connect("not-an-operational-dsn", 1)
    assert calls == []


def test_cancelled_commit_success_return_remains_unconfirmed() -> None:
    """取消発行後の見かけの成功を成功応答に戻さない。"""
    calls = []

    class Connection:
        def commit(self) -> None:
            sleep(0.06)

        def cancel_safe(self, *, timeout: float) -> None:
            calls.append(timeout)

    with pytest.raises(LedgerOutcomeUnconfirmed, match="^ledger outcome unconfirmed$"):
        adapter._commit(cast(psycopg.Connection[Any], Connection()), 0.01)
    assert calls == [0.01]


def test_unknown_query_and_owner_are_rejected_before_execution() -> None:
    """任意SQL/未知操作/UUID風の文字列を実行口へ流さない。"""
    with pytest.raises(LedgerUnavailable):
        adapter._query(
            cast(psycopg.Connection[Any], object()),
            cast(adapter.Operation, "DROP TABLE x"),
        )
    with pytest.raises(LedgerUnavailable):
        adapter._owner((UUID(int=1), UUID(int=2), UUID(int=3), str(UUID(int=4))))


def test_post_commit_primary_read_failure_is_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COMMIT後最初のprimary再読故障も未確定へ写し、内部原因を秘匿する。"""

    def broken_identity(connection: psycopg.Connection[Any]) -> dict[str, Any]:
        raise RuntimeError("private internal transport detail")

    monkeypatch.setattr(adapter, "_identity", broken_identity)
    with pytest.raises(
        LedgerOutcomeUnconfirmed, match="^ledger outcome unconfirmed$"
    ) as captured:
        adapter._PgLedgerPair._confirmed(
            cast(adapter._PgLedgerPair, None),
            cast(psycopg.Connection[Any], None),
            None,
            (),
        )
    assert captured.value.__suppress_context__ is True


def test_elapsed_deadline_is_unconfirmed_even_when_timer_callback_is_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消threadのschedule遅延が期限越えの成功を作らない。"""

    class DelayedTimer:
        def __init__(self, *args: object) -> None:
            pass

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            pass

        def join(self, timeout: float) -> None:
            pass

        def is_alive(self) -> bool:
            return False

    class Connection:
        def commit(self) -> None:
            sleep(0.02)

    monkeypatch.setattr(adapter, "Timer", DelayedTimer)
    with pytest.raises(LedgerOutcomeUnconfirmed):
        adapter._commit(cast(psycopg.Connection[Any], Connection()), 0.001)


# 汎用frameの単体試験はkernel保護の成功証拠へ代用しない。
@pytest.mark.parametrize(
    "change", ["magic", "version", "ordinal", "link", "digest", "tail", "length"]
)
def test_witness_frame_corruption_is_rejected(tmp_path: Path, change: str) -> None:
    """完全frame以外を読取成功や末尾切捨てへ写さない。"""
    import os

    from pitchlog.durable_rights_ledger import witness

    data, _ = witness._encoded(1, bytes(32), b"payload")
    broken = bytearray(data)
    index = {
        "magic": 0,
        "version": 8,
        "length": 9,
        "ordinal": 13,
        "link": 21,
        "digest": -1,
    }
    if change == "tail":
        broken = broken[:-1]
    else:
        broken[index[change]] ^= 0xFF
    path = tmp_path / "frame"
    path.write_bytes(broken)
    with path.open("rb") as stream:
        with pytest.raises(witness.WitnessUnavailable):
            list(witness._frames(stream.fileno(), os.fstat(stream.fileno()).st_size))
    assert path.read_bytes() == bytes(broken)


@pytest.mark.parametrize(
    "ordinal,previous,payload",
    [
        (True, bytes(32), b"a"),
        (0, bytes(32), b"a"),
        (2**64, bytes(32), b"a"),
        (1, b"bad", b"a"),
        (1, bytes(32), b""),
        (1, bytes(32), b"x" * 65537),
        (1, bytes(32), bytearray(b"a")),
    ],
)
def test_witness_frame_input_has_exact_bounded_types(
    ordinal: Any, previous: Any, payload: Any
) -> None:
    """frame境界はbool/巨大値/可変payloadを受理しない。"""
    from pitchlog.durable_rights_ledger import witness

    with pytest.raises(witness.WitnessUnavailable):
        witness._encoded(ordinal, previous, payload)


def test_witness_open_never_creates_unprotected_enrollment(tmp_path: Path) -> None:
    """通常openの失敗からenrollmentやjournalを生成しない。"""
    from pitchlog.durable_rights_ledger import witness

    with pytest.raises(witness.WitnessUnavailable):
        witness.ProtectedJournal.open(tmp_path)
    assert list(tmp_path.iterdir()) == []


_WITNESS_LOAD = """
import importlib.util, sys, os, stat, json, uuid, fcntl, array, struct, errno
from pathlib import Path
spec = importlib.util.spec_from_file_location("tested_witness", "/witness.py")
w = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = w
spec.loader.exec_module(w)
"""

_WITNESS_PROVISION = (
    _WITNESS_LOAD
    + """
uid = 20001
cases = ("good", "short", "zero", "eio", "sync", "dir_sync", "busy", "cap",
         "no_append", "no_dir_append", "no_immutable", "mode", "owner",
         "inode", "missing", "symlink", "partial", "unknown", "checksum", "duplicate")
request = (1 << 30) | (struct.calcsize("l") << 16) | (ord("f") << 8) | 2
def change_flags(fd, value):
    fcntl.ioctl(fd, request, array.array("I", [value]), True)
os.chmod('/w', 0o755)
for case in cases:
    path = Path('/w') / case
    path.mkdir()
    os.chown(path, 0, uid)
    os.chmod(path, 0o750)
    descriptors = [os.open(path / name, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                   for name in ('enrollment.json', 'journal', 'writer.lock')]
    descriptor, journal, lock = descriptors
    os.fchown(descriptor, 0, uid)
    os.fchmod(descriptor, 0o640)
    for fd in (journal, lock):
        os.fchown(fd, uid, uid)
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    value = dict(schema_version=1, authority_id='11111111-1111-4111-8111-111111111111',
                 writer_uid=uid, writer_gid=uid, device=os.fstat(directory).st_dev,
                 filesystem_id=os.fstatvfs(directory).f_fsid,
                 directory_inode=os.fstat(directory).st_ino,
                 journal_inode=os.fstat(journal).st_ino,
                 lock_inode=os.fstat(lock).st_ino,
                 descriptor_inode=os.fstat(descriptor).st_ino)
    if case == 'inode': value['journal_inode'] += 1
    encoded = json.dumps(value).encode()
    if case == 'duplicate': encoded = encoded[:-1] + b', "schema_version":1}'
    os.write(descriptor, encoded)
    if case in ('partial', 'unknown', 'checksum'):
        data, _ = w._encoded(1, bytes(32), b'payload')
        if case == 'partial': data = data[:-1]
        if case == 'unknown': data = data[:8] + bytes([2]) + data[9:]
        if case == 'checksum': data = data[:-1] + bytes([data[-1] ^ 255])
        os.write(journal, data)
    if case == 'mode': os.fchmod(journal, 0o640)
    if case == 'owner': os.fchown(journal, 20002, uid)
    if case == 'missing': os.unlink(path / 'journal')
    if case == 'symlink':
        os.rename(path / 'journal', path / 'actual')
        os.symlink('actual', path / 'journal')
    if case != 'no_immutable': change_flags(descriptor, w._flags(descriptor) | 0x10)
    if case != 'no_append': change_flags(journal, w._flags(journal) | 0x20)
    if case != 'no_dir_append': change_flags(directory, w._flags(directory) | 0x20)
    for fd in (*descriptors, directory):
        os.fsync(fd)
        os.close(fd)
print('PROVISIONED', flush=True)
"""
)

_WITNESS_CLEANUP = (
    _WITNESS_LOAD
    + """
request = (1 << 30) | (struct.calcsize("l") << 16) | (ord("f") << 8) | 2
for directory, dirs, files in os.walk('/w'):
    for path in [Path(directory), *(Path(directory) / name for name in files)]:
        if path.is_symlink(): continue
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        fcntl.ioctl(fd, request, array.array('I', [w._flags(fd) & ~0x30]), True)
        os.close(fd)
"""
)


class _WitnessContainers:
    """専用volumeとPython runtimeだけを隔離containerへ渡す。"""

    def __init__(self) -> None:
        import subprocess
        from uuid import uuid4

        self.volume = "pitchlog-witness-" + uuid4().hex[:12]
        self.names: list[str] = []
        result = subprocess.run(
            [
                "docker",
                "volume",
                "create",
                "--label",
                "pitchlog.owner=witness-test",
                self.volume,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, "real witness volume unavailable"

    def command(
        self, *, root: bool = False, uid: int = 20001, capable: bool = False
    ) -> list[str]:
        import sys
        from uuid import uuid4

        name = self.volume + "-" + uuid4().hex[:6]
        self.names.append(name)
        args = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--pull=never",
            "--network",
            "none",
            "--name",
            name,
            "--label",
            "pitchlog.owner=witness-test",
            "--mount",
            f"type=volume,src={self.volume},dst=/w",
            "--mount",
            f"type=bind,src={sys.base_prefix},dst=/runtime,readonly",
            "--mount",
            f"type=bind,src={_PACKAGE / 'witness.py'},dst=/witness.py,readonly",
        ]
        if root:
            args += ["--cap-add", "LINUX_IMMUTABLE"]
        else:
            args += ["--user", f"{uid}:{uid}", "--security-opt", "no-new-privileges"]
            args += (
                ["--cap-add", "LINUX_IMMUTABLE"] if capable else ["--cap-drop", "ALL"]
            )
        return [*args, "postgres:17.11-bookworm", "/runtime/bin/python3.12", "-"]

    def run(
        self, code: str, *, root: bool = False, uid: int = 20001, capable: bool = False
    ) -> str:
        import subprocess

        result = subprocess.run(
            self.command(root=root, uid=uid, capable=capable),
            input=code,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            "real witness protection trial failed: " + result.stderr[-1500:]
        )
        return result.stdout

    def cleanup(self) -> None:
        import subprocess

        try:
            self.run(_WITNESS_CLEANUP, root=True)
        finally:
            for name in self.names:
                subprocess.run(
                    ["docker", "rm", "--force", name], capture_output=True, timeout=20
                )
            result = subprocess.run(
                ["docker", "volume", "rm", self.volume], capture_output=True, timeout=20
            )
            assert result.returncode == 0, "owned witness volume cleanup failed"


@pytest.fixture(scope="module")
def protected_witness() -> Any:
    """実保護を要求し、未提供時にskipせず不足として失敗させる。"""
    resources = _WitnessContainers()
    try:
        resources.run(_WITNESS_PROVISION, root=True)
        yield resources
    finally:
        resources.cleanup()


def test_witness_real_protection_fsync_shortwrite_and_reopen(
    protected_witness: Any,
) -> None:
    """実capなしworkerで保護/完全書込/fsync/正常再openを確認する。"""
    code = (
        _WITNESS_LOAD
        + """
path = Path('/w/short')
real_sync, real_write = os.fsync, os.write
calls = []
def sync(fd):
    calls.append(stat.S_ISDIR(os.fstat(fd).st_mode))
    real_sync(fd)
os.fsync = sync
with w.ProtectedJournal.open(path) as journal:
    assert calls == [False, False, False, True]
    interrupted = [False]
    def short(fd, data):
        if not interrupted[0]:
            interrupted[0] = True
            raise InterruptedError
        return real_write(fd, data[:7])
    os.write = short
    first = journal.append(b'first')
    second = journal.append(b'second')
    assert first.ordinal == 1 and second.ordinal == 2
    assert [r.payload for r in journal.records()] == [b'first', b'second']
    assert calls[-2:] == [False, False]
    request = (1 << 30) | (struct.calcsize('l') << 16) | (ord('f') << 8) | 2
    fd = os.open(path / 'journal', os.O_RDONLY)
    try:
        try:
            fcntl.ioctl(fd, request, array.array('I', [0]), True)
            raise AssertionError('append protection cleared')
        except OSError as e: assert e.errno == errno.EPERM
    finally: os.close(fd)
    for action in (lambda: os.open(path / 'journal', os.O_WRONLY | os.O_TRUNC),
                   lambda: os.unlink(path / 'journal')):
        try:
            action()
            raise AssertionError('protected file changed')
        except OSError as e: assert e.errno in (errno.EPERM, errno.EACCES)
os.write, os.fsync = real_write, real_sync
with w.ProtectedJournal.open(path) as journal:
    assert [r.payload for r in journal.records()] == [b'first', b'second']
print('REAL_PROTECTION_AND_DURABILITY_OK')
"""
    )
    assert "REAL_PROTECTION_AND_DURABILITY_OK" in protected_witness.run(code)


@pytest.mark.parametrize(
    "case",
    [
        "no_append",
        "no_dir_append",
        "no_immutable",
        "mode",
        "owner",
        "inode",
        "missing",
        "symlink",
        "partial",
        "unknown",
        "checksum",
        "duplicate",
    ],
)
def test_witness_real_invalid_protection_or_frame_is_refused(
    protected_witness: Any, case: str
) -> None:
    """欠落/置換/権限/破損/未知形式を実保護された資産で拒否する。"""
    code = (
        _WITNESS_LOAD
        + f"""
try:
    w.ProtectedJournal.open(Path('/w/{case}'))
    raise AssertionError('invalid witness accepted')
except w.WitnessUnavailable: pass
"""
    )
    protected_witness.run(code)


def test_witness_real_capability_or_app_uid_is_refused(protected_witness: Any) -> None:
    """別app UIDと解除能力を残したprocessをkernel観測で拒否する。"""
    code = (
        _WITNESS_LOAD
        + """
try:
    w.ProtectedJournal.open(Path('/w/good'))
    raise AssertionError('untrusted subject accepted')
except w.WitnessUnavailable: pass
"""
    )
    protected_witness.run(code, uid=20002)
    protected_witness.run(code, capable=True)


@pytest.mark.parametrize("case", ["zero", "eio", "sync", "dir_sync"])
def test_witness_real_io_failure_never_acknowledges(
    protected_witness: Any, case: str
) -> None:
    """実保護workerの書込/fsync故障は成功/同一writer再使用に戻さない。"""
    code = (
        _WITNESS_LOAD
        + f"""
case = '{case}'
path = Path('/w') / case
real_sync, real_write = os.fsync, os.write
if case == 'dir_sync':
    def broken(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode): raise OSError(errno.EIO, 'injected')
        real_sync(fd)
    os.fsync = broken
    try:
        w.ProtectedJournal.open(path)
        raise AssertionError('directory fsync failed open acknowledged')
    except w.WitnessUnavailable: pass
    os.fsync = real_sync
    with w.ProtectedJournal.open(path): pass
else:
    with w.ProtectedJournal.open(path) as journal:
        if case == 'sync':
            def broken(fd): raise OSError(errno.EIO, 'injected')
            os.fsync = broken
        else:
            count = [0]
            def broken(fd, data):
                count[0] += 1
                if case == 'zero': return 0
                if count[0] == 1: return real_write(fd, data[:5])
                raise OSError(errno.EIO, 'injected')
            os.write = broken
        try:
            journal.append(b'uncertain')
            raise AssertionError('I/O failure acknowledged')
        except w.WitnessOutcomeUnconfirmed: pass
        try:
            journal.append(b'next')
            raise AssertionError('broken writer reused')
        except w.WitnessUnavailable: pass
    os.fsync, os.write = real_sync, real_write
    if case == 'eio':
        size = (path / 'journal').stat().st_size
        try:
            w.ProtectedJournal.open(path)
            raise AssertionError('partial frame accepted')
        except w.WitnessUnavailable: pass
        assert (path / 'journal').stat().st_size == size
"""
    )
    protected_witness.run(code)


def test_witness_real_process_flock_excludes_second_writer(
    protected_witness: Any,
) -> None:
    """別container/processの同一inode writerを期限付き実flockで拒否する。"""
    import select
    import subprocess

    holder = (
        _WITNESS_LOAD
        + """
with w.ProtectedJournal.open(Path('/w/busy')) as journal:
    journal.append(b'held')
    print('READY', flush=True)
    assert sys.stdin.readline().strip() == 'release'
"""
    )
    command = protected_witness.command()
    command[-1:] = ["-c", holder]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        ready, _, _ = select.select([process.stdout], [], [], 20)
        assert ready and process.stdout.readline().strip() == "READY"
        contender = (
            _WITNESS_LOAD
            + """
from time import monotonic
start = monotonic()
try:
    w.ProtectedJournal.open(Path('/w/busy'), timeout=0.1)
    raise AssertionError('second writer accepted')
except w.WitnessBusy: pass
assert monotonic() - start < 2
"""
        )
        protected_witness.run(contender)
        _, error = process.communicate(input="release\n", timeout=10)
        assert process.returncode == 0, error
        protected_witness.run(
            _WITNESS_LOAD
            + """
with w.ProtectedJournal.open(Path('/w/busy')) as journal:
    assert [r.payload for r in journal.records()] == [b'held']
"""
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_witness_manifest_matches_component_and_keeps_product_boundary() -> None:
    """単一journalの保護/formatを保持し、接合を全製品完成へ広げない。"""
    from pitchlog.durable_rights_ledger import witness

    entry = json.loads((_PACKAGE / "manifest.json").read_text())["witness"]
    assert entry["component"] == "protected_journal_and_unix_authority"
    assert entry["authority_connected"] is True
    assert (
        entry["source_sha256"]
        == hashlib.sha256(Path(witness.__file__).read_bytes()).hexdigest()
    )
    assert entry["files"] == ["enrollment.json", "journal", "writer.lock"]
    assert entry["frame"] == {
        "magic": "PLWIT001",
        "version": 1,
        "header_bytes": witness._HEADER.size,
        "checksum_bytes": 32,
        "maximum_payload_bytes": 65536,
        "checksum": "sha256",
        "chain": "previous_frame_digest",
    }
    assert entry["capability_sets_empty"] == [
        "CapEff",
        "CapPrm",
        "CapInh",
        "CapAmb",
        "CapBnd",
    ]
    assert entry["no_new_privileges"] is True
    assert entry["directory_flag"] == "FS_APPEND_FL"
    assert entry["journal_flag"] == "FS_APPEND_FL"
    assert entry["descriptor_flag"] == "FS_IMMUTABLE_FL"
    assert entry["file_and_directory_fsync"] is True
    assert not any(
        entry[key]
        for key in (
            "automatic_enroll",
            "rotation",
            "truncate_or_repair",
            "secret_fields",
        )
    )


@pytest.mark.parametrize(
    "bad",
    [
        True,
        (),
        [str(UUID(int=1))] * 3,
        [str(UUID(int=1))] * 3 + [1],
        [str(UUID(int=1)).upper()] * 4,
    ],
)
def test_authority_rejects_untyped_or_noncanonical_owner(bad: object) -> None:
    """transportの型/要素数/非canonical UUIDを実行前に拒否する。"""
    # 数字だけのUUIDはupperでも同値なので英字を含む入力に置き換える。
    if type(bad) is list and len(bad) == 4 and all(type(v) is str for v in bad):
        bad = ["AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"] * 4
    with pytest.raises(LedgerUnavailable):
        adapter._params(bad)


@pytest.mark.parametrize(
    "response",
    [
        b"",
        b"not-json\n",
        b'{"status":"ok","result":1,"extra":0}\n',
        b'{"status":"ok","status":"ok","result":1}\n',
    ],
)
def test_mutation_transport_loss_or_malformed_ack_is_unconfirmed(
    response: bytes,
) -> None:
    """実socket上のEOF/破損ACKを未使用や成功へ再解釈しない。"""
    import socket
    from threading import Thread

    client, server = socket.socketpair()

    def reply() -> None:
        with server:
            while server.recv(1) != b"\n":
                pass
            server.sendall(response)

    thread = Thread(target=reply)
    thread.start()
    try:
        with client, pytest.raises(LedgerOutcomeUnconfirmed):
            adapter._request(client, {"operation": "reserve"}, mutation=True)
    finally:
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_public_constructor_does_not_accept_uncontrolled_pg_endpoints() -> None:
    """public呼出元に資格/期待集合を渡してfresh newする抜け道を作らない。"""
    endpoints = LedgerEndpoints("primary", "standby", "business", "control")
    with pytest.raises(LedgerUnavailable):
        DurableLedger(cast(Path, endpoints))


@pytest.mark.parametrize(
    "field,value",
    [
        ("authority_id", str(UUID(int=1))),
        ("activation_ordinal", True),
        ("activation_ordinal", 1.0),
        ("activation_ordinal", 0),
        ("activation_ordinal", 2**64),
        ("business_system_id", ["123"]),
        ("database", ["ledger_fixture"]),
        ("postmaster_started_at", None),
        ("pair_epoch", True),
        ("pair_epoch", 2),
        ("highwater", False),
        ("highwater", 1),
        ("reservation_count", 0.0),
    ],
)
def test_fresh_attestation_direct_construction_has_exact_types(
    field: str,
    value: Any,
) -> None:
    """型付きDTOにもbool/float/非fresh状態を通さず、認証証拠とは混同しない。"""
    from pitchlog.durable_rights_ledger import FreshActivationAttestation

    fields: dict[str, Any] = dict(
        authority_id=UUID(int=1),
        activation_ordinal=3,
        business_system_id="123",
        database="ledger_fixture",
        postmaster_started_at="actual-postmaster",
        pair_epoch=1,
        highwater=0,
        reservation_count=0,
    )
    fields[field] = value
    with pytest.raises(LedgerUnavailable):
        FreshActivationAttestation(**fields)


def test_fresh_attestation_codec_is_closed_and_immutable() -> None:
    """検証済みmetadata以外のfield/型を補完せず、単一Protocolのfenceを使う。"""
    from dataclasses import FrozenInstanceError

    from pitchlog.durable_rights_ledger import FreshActivationAttestation

    value = FreshActivationAttestation(
        UUID(int=1), 3, "123", "ledger_fixture", "postmaster", 1, 0, 0
    )
    assert adapter._activation_from(adapter._activation_wire(value)) == value
    with pytest.raises(FrozenInstanceError):
        setattr(value, "database", "forged")
    for changed in (
        {**adapter._activation_wire(value), "extra": True},
        {**adapter._activation_wire(value), "database": ["ledger_fixture"]},
        {**adapter._activation_wire(value), "pair_epoch": True},
        {
            k: v
            for k, v in adapter._activation_wire(value).items()
            if k != "authority_id"
        },
    ):
        with pytest.raises(LedgerUnavailable):
            adapter._activation_from(changed)


def _dual_config() -> dict[str, Any]:
    """正規v2の閉fieldだけを持つ非秘密の構造試験vector。実配置ではない。"""
    return dict(
        schema_version=2,
        authority_uid=20001,
        authority_gid=20001,
        application_uid=20003,
        application_gid=20003,
        database_uid=999,
        database_gid=999,
        witness_path="/w/state",
        timeout=2.0,
        primary_dsn="fixture-primary",
        standby_dsn="fixture-standby",
        business_dsn="fixture-business",
        control_dsn="fixture-control",
        enrollment_state="enrolled",
        peers=[
            dict(
                role="generation",
                client_uid=20002,
                client_gid=20002,
                socket_path="/control/run/generation.sock",
                endpoint_path="/control/public/generation.json",
            ),
            dict(
                role="fresh_controller",
                client_uid=20004,
                client_gid=20004,
                socket_path="/control/run/controller.sock",
                endpoint_path="/control/public/controller.json",
            ),
        ],
    )


def _config_read_boundary(
    monkeypatch: pytest.MonkeyPatch, value: dict[str, Any]
) -> Path:
    """構造試験だけでroot読取済み値を供給する。実file保護の証拠にはしない。"""
    from types import SimpleNamespace

    from pitchlog.durable_rights_ledger import authority

    path = Path("/control/settings/config.json")
    original = authority.os.stat
    monkeypatch.setattr(authority, "_read_root_json", lambda *_: value)
    monkeypatch.setattr(
        authority.os,
        "stat",
        lambda name, *a, **kw: (
            SimpleNamespace(st_gid=20001) if name == path else original(name, *a, **kw)
        ),
    )
    return path


def test_dual_config_exact_roles_and_v1_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v2はexact二主体、v1は旧閉field/単一peerのまま受理する。"""
    from pitchlog.durable_rights_ledger import authority

    value = _dual_config()
    path = _config_read_boundary(monkeypatch, value)
    assert authority._config(path) == value
    assert tuple(p["role"] for p in authority._listener_peers(value)) == (
        "generation",
        "fresh_controller",
    )
    generation = value["peers"][0]
    legacy = {
        k: v
        for k, v in value.items()
        if k
        not in {
            "peers",
            "application_uid",
            "application_gid",
            "database_uid",
            "database_gid",
        }
    }
    legacy.update({k: v for k, v in generation.items() if k != "role"})
    legacy["schema_version"] = 1
    with monkeypatch.context() as patch:
        _config_read_boundary(patch, legacy)
        assert authority._config(path) == legacy
        assert authority._listener_peers(legacy)[0]["role"] is None
    legacy["peers"] = value["peers"]
    with monkeypatch.context() as patch:
        _config_read_boundary(patch, legacy)
        with pytest.raises(authority.AuthorityUnavailable):
            authority._config(path)


@pytest.mark.parametrize(
    "change",
    [
        "version_bool",
        "version_float",
        "unknown",
        "missing",
        "one",
        "three",
        "tuple",
        "role",
        "role_list",
        "duplicate_role",
        "uid",
        "gid",
        "bool_uid",
        "actor_uid",
        "authority_uid",
        "authority_gid",
        "app_uid",
        "app_gid",
        "db_uid",
        "db_gid",
        "unknown_peer",
        "missing_peer",
        "socket",
        "endpoint",
        "cross_path",
        "relative",
        "parent",
        "null",
        "long",
        "config",
        "witness",
        "run_config_directory",
        "run_endpoint_directory",
        "path_type",
        "witness_type",
        "run_ancestor",
        "application_gid",
    ],
)
def test_dual_config_rejects_partial_collisions_and_unknowns(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    """型/主体/role/配置衝突をPG/journalの構築より先に拒否する。"""
    from pitchlog.durable_rights_ledger import authority

    value = _dual_config()
    first, second = value["peers"]
    mutations = {
        "version_bool": lambda: value.update(schema_version=True),
        "version_float": lambda: value.update(schema_version=2.0),
        "unknown": lambda: value.update(extra=True),
        "missing": lambda: value.pop("application_gid"),
        "one": lambda: value.update(peers=[first]),
        "three": lambda: value["peers"].append(dict(second)),
        "tuple": lambda: value.update(peers=tuple(value["peers"])),
        "role": lambda: second.update(role="administrator"),
        "role_list": lambda: second.update(role=["fresh_controller"]),
        "duplicate_role": lambda: second.update(role="generation"),
        "uid": lambda: second.update(client_uid=20002),
        "gid": lambda: second.update(client_gid=20002),
        "bool_uid": lambda: second.update(client_uid=True),
        "actor_uid": lambda: first.update(client_uid=20005),
        "authority_uid": lambda: second.update(client_uid=20001),
        "authority_gid": lambda: second.update(client_gid=20001),
        "app_uid": lambda: second.update(client_uid=20003),
        "app_gid": lambda: second.update(client_gid=20003),
        "db_uid": lambda: second.update(client_uid=999),
        "db_gid": lambda: second.update(client_gid=999),
        "unknown_peer": lambda: second.update(operations=["reserve"]),
        "missing_peer": lambda: second.pop("role"),
        "socket": lambda: second.update(socket_path=first["socket_path"]),
        "endpoint": lambda: second.update(endpoint_path=first["endpoint_path"]),
        "cross_path": lambda: second.update(endpoint_path=first["socket_path"]),
        "relative": lambda: second.update(socket_path="relative.sock"),
        "parent": lambda: second.update(socket_path="/control/run/../evil.sock"),
        "null": lambda: second.update(socket_path="/control/run/a\0b"),
        "long": lambda: second.update(socket_path="/control/run/" + "a" * 108),
        "config": lambda: second.update(endpoint_path="/control/settings/config.json"),
        "witness": lambda: second.update(endpoint_path="/w/state/journal"),
        "run_config_directory": lambda: second.update(
            socket_path="/control/settings/a.sock"
        ),
        "run_endpoint_directory": lambda: second.update(
            socket_path="/control/public/a.sock"
        ),
        "path_type": lambda: second.update(
            socket_path=["/control/run/controller.sock"]
        ),
        "witness_type": lambda: value.update(witness_path=[]),
        "run_ancestor": lambda: second.update(socket_path="/control/ancestor.sock"),
        "application_gid": lambda: value.update(application_gid=20005),
    }
    mutations[change]()
    path = _config_read_boundary(monkeypatch, value)
    with pytest.raises(authority.AuthorityUnavailable):
        authority._config(path)


@pytest.mark.parametrize(
    "role,operation",
    [
        ("generation", "fresh_activation_open"),
        ("fresh_controller", "epoch"),
        ("fresh_controller", "reserve"),
        ("fresh_controller", "claim"),
        ("fresh_controller", "fence_open"),
        ("generation", "fence_check"),
        ("fresh_controller", "fence_close"),
        ("generation", "advance"),
        ("unknown", "epoch"),
        ("generation", ["epoch"]),
        ("generation", {"operation": "epoch", "role": "fresh_controller"}),
        ("generation", {"operation": "reserve", "params": ["bad"] * 4}),
        ("fresh_controller", {"operation": "fresh_activation_open", "highwater": 0}),
    ],
)
def test_dual_runtime_denies_before_pg_or_journal(role: str, operation: Any) -> None:
    """実socket要求の能力拒否はruntimeのPG/journal/lockへ到達しない。"""
    import socket
    from threading import Thread

    # __init__は実PGに接続する。負例は明示trapで不要なアクセス自体を記録する。
    # 単なる未初期化AttributeErrorによるunavailableでは検査を通さない。
    accessed = []

    class ForbiddenRuntimeAccess:
        """負例のPG/排他/journalアクセスを成功応答に置換せず記録する。"""

        def __getattr__(self, name: str) -> Any:
            """未承認アクセスを必ず外側のassertへ残す。"""
            accessed.append(name)
            raise AssertionError("rejected role reached runtime/PG/journal")

    runtime = object.__new__(adapter._AuthorityRuntime)
    runtime._blocked = False
    runtime._active = set()
    runtime._value = {"timeout": 2.0}
    runtime._mutex = cast(Any, ForbiddenRuntimeAccess())
    runtime._pair = cast(Any, ForbiddenRuntimeAccess())
    runtime._journal = cast(Any, ForbiddenRuntimeAccess())
    client, server = socket.socketpair()
    thread = Thread(target=runtime.handle, args=(server,), kwargs={"role": role})
    thread.start()
    try:
        with client:
            adapter._send(
                client,
                operation if type(operation) is dict else {"operation": operation},
            )
            assert adapter._receive(client) == {"status": "unavailable"}
    finally:
        server.close()
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert accessed == []
    assert runtime._blocked is False and runtime._active == set()


@pytest.mark.parametrize(
    "role,operation",
    [
        ("generation", "epoch"),
        ("generation", "reserve"),
        ("generation", "claim"),
        ("generation", "fence_open"),
        ("fresh_controller", "fresh_activation_open"),
    ],
)
def test_dual_operation_exact_positive_set(role: str, operation: str) -> None:
    """新能力の正例集合は二役割のexact五操作だけである。"""
    adapter._authorize_operation(role, operation)
    # v1は従来のdispatch/leaseループへ判断を委ねる。
    adapter._authorize_operation(None, operation)


@pytest.mark.parametrize("operation", ["epoch", "reserve", "claim", "fence", "fresh"])
def test_dual_client_rejects_wrong_role_before_connect(operation: str) -> None:
    """公開clientでも権限外をsocket接続/結果不明へ変換する前に拒否する。"""
    ledger = object.__new__(DurableLedger)
    ledger._target = {
        "role": "generation" if operation == "fresh" else "fresh_controller"
    }
    methods = {
        "epoch": lambda: ledger.current_recovery_generation(),
        "reserve": lambda: ledger.reserve(*(UUID(int=1) for _ in range(4))),
        "claim": lambda: ledger.claim(*(UUID(int=1) for _ in range(4))),
        "fence": lambda: ledger.recovery_fence().__enter__(),
        "fresh": lambda: ledger.fresh_activation().__enter__(),
    }
    with pytest.raises(LedgerUnavailable):
        methods[operation]()


@pytest.mark.parametrize(
    "change",
    [
        "valid",
        "legacy",
        "extra",
        "role",
        "role_type",
        "uid",
        "gid",
        "authority_gid",
        "missing_role",
        "version",
        "socket_type",
        "socket_relative",
        "v1_extra_role",
    ],
)
def test_dual_endpoint_remains_closed_and_subject_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    """root読取後の形/主体検査を試す。実immutable/peer検査は実DB群で別証明する。"""
    import os
    import stat
    from types import SimpleNamespace

    from pitchlog.durable_rights_ledger import authority

    value: dict[str, Any] = dict(
        schema_version=2,
        role="generation",
        authority_uid=20001,
        authority_gid=20001,
        client_uid=20002,
        client_gid=20002,
        socket_path="/control/run/service.sock",
        timeout=2.0,
    )
    changes = {
        "valid": lambda: None,
        "legacy": lambda: (
            value.update(schema_version=1),
            value.pop("role"),
            value.pop("authority_gid"),
        ),
        "extra": lambda: value.update(extra=1),
        "role": lambda: value.update(role="unknown"),
        "role_type": lambda: value.update(role=["generation"]),
        "uid": lambda: value.update(client_uid=20004),
        "gid": lambda: value.update(client_gid=20004),
        "authority_gid": lambda: value.update(authority_gid=20002),
        "missing_role": lambda: value.pop("role"),
        "version": lambda: value.update(schema_version=True),
        "socket_type": lambda: value.update(socket_path=["/control/run/service.sock"]),
        "socket_relative": lambda: value.update(socket_path="relative"),
        "v1_extra_role": lambda: (
            value.update(schema_version=1),
            value.pop("authority_gid"),
        ),
    }
    changes[change]()
    monkeypatch.setattr(authority, "_read_root_json", lambda *_: value)
    monkeypatch.setattr(
        authority, "_trusted_directory", lambda _: os.open(tmp_path, os.O_RDONLY)
    )
    original = authority.os.stat
    monkeypatch.setattr(
        authority.os,
        "stat",
        lambda name, *args, **kwargs: (
            SimpleNamespace(st_mode=stat.S_IFSOCK | 0o660, st_uid=0, st_gid=20002)
            if name == "service.sock"
            else original(name, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(authority.os, "geteuid", lambda: 20002)
    monkeypatch.setattr(authority.os, "getegid", lambda: 20002)
    if change in {"valid", "legacy"}:
        assert authority._endpoint(Path("/control/public/endpoint.json")) == value
    else:
        with pytest.raises(authority.AuthorityUnavailable):
            authority._endpoint(Path("/control/public/endpoint.json"))


@pytest.mark.parametrize("changed", ["uid", "gid"])
def test_dual_business_identity_checks_real_socket_peer_before_query(
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    """v2設定の自己申告だけではDB主体にせず、実kernel不一致をSQL前に拒否する。"""
    import socket
    import struct
    from contextlib import contextmanager
    from types import SimpleNamespace

    left, right = socket.socketpair()
    _, uid, gid = struct.unpack(
        "3i", left.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    )
    pair = object.__new__(adapter._PgLedgerPair)
    pair._endpoints = LedgerEndpoints("p", "s", "b", "c")
    pair._business_peer = (uid + 1, gid) if changed == "uid" else (uid, gid + 1)

    @contextmanager
    def connection(*_: object):
        yield SimpleNamespace(fileno=left.fileno)

    def forbidden_query(*_: object) -> None:
        raise AssertionError("kernel identity rejection reached SQL")

    monkeypatch.setattr(adapter, "_connection", connection)
    monkeypatch.setattr(adapter, "_query", forbidden_query)
    try:
        with pytest.raises(LedgerUnavailable):
            pair._observe_business()
    finally:
        left.close()
        right.close()
