"""実flush後の単一故障で、owned新規試合の業務13表の原状を観測する。"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

from . import test_ordinary_pitch_vertical_http as ordinary
from .test_ordinary_pitch_vertical_http import (
    admin_connection as admin_connection,
)
from .test_ordinary_pitch_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_ordinary_pitch_vertical_http import (
    product_node_binary as product_node_binary,
)
from .test_ordinary_pitch_vertical_http import (
    tested_role_connection as tested_role_connection,
)
from .test_ordinary_pitch_vertical_http import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db

# game列の無い2表は同owned tenant全行。旧要求/controlの終結はこの集合に含めない。
_TABLES = (
    ("public", "games", "id"),
    ("public", "recording_generations", "game_id"),
    ("public", "idempotency_ledger", None),
    ("public", "operation_events", "game_id"),
    ("public", "event_slots", "game_id"),
    ("public", "play_rows", "game_id"),
    ("public", "play_runners", None),
    ("sync_fence", "ordinary_pitch_history", "game_id"),
    ("sync_fence", "ordinary_pitch_checkpoints", "game_id"),
    ("sync_fence", "ordinary_pitch_write_admissions", "game_id"),
    ("sync_fence", "stats_fact_versions", "game_id"),
    ("sync_fence", "stats_primitive_sources", "game_id"),
    ("sync_fence", "stats_primitive_facts", "game_id"),
)
_KEYS = frozenset(schema + "." + table for schema, table, _ in _TABLES)
type _Snapshot = dict[str, tuple[str, ...]]


@dataclass(repr=False)
class _Observation:
    """原payload入りsnapshotをrepr/出力に載せずRAMだけに保持する。"""

    game: UUID | None = None
    before: _Snapshot | None = field(default=None, repr=False)
    error_kind: str | None = None


def _check_snapshot(value: _Snapshot) -> None:
    """13表・全row型を検査し、部分一致や欠落を成功としない。"""
    if type(value) is not dict or set(value) != _KEYS:
        raise AssertionError("snapshotの固定13表集合が不一致です")
    for key, rows in value.items():
        if type(key) is not str or type(rows) is not tuple:
            raise AssertionError("snapshotの表又は行集合型が不正です")
        if any(type(row) is not str for row in rows):
            raise AssertionError("snapshotのcanonical行型が不正です")
        if tuple(sorted(rows)) != rows:
            raise AssertionError("snapshot行のcanonical順序が不正です")
        try:
            valid = all(type(json.loads(row)) is dict for row in rows)
        except (ValueError, TypeError):
            raise AssertionError("snapshotのcanonical行が不正です") from None
        if not valid:
            raise AssertionError("snapshotのcanonical行はobjectが必要です")


def _snapshot_summary(value: _Snapshot) -> dict[str, dict[str, int | str]]:
    """原値を出力せず、全行の件数とdigestだけを返す。"""
    _check_snapshot(value)
    return {
        key: {
            "count": len(rows),
            "sha256": hashlib.sha256(
                json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        for key, rows in value.items()
    }


def _require_unchanged(before: _Snapshot, after: _Snapshot) -> None:
    """digestだけでなく全canonical行を比較し、失敗にも原値を表示しない。"""
    _check_snapshot(before)
    _check_snapshot(after)
    if before != after:
        raise AssertionError("故障前後の業務13表全行が不一致です")


def _read_snapshot(
    dsn: str, tenant: UUID, game: UUID, stop: threading.Event | None = None
) -> _Snapshot:
    """別adminのread-only repeatable-readで固定13表全列を限定取得する。"""
    deadline = time.monotonic() + 30
    result: _Snapshot = {}
    try:
        with psycopg.connect(dsn, connect_timeout=10, autocommit=True) as connection:
            with connection.transaction():
                connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                connection.execute("SET LOCAL statement_timeout = '15000ms'")
                for schema, table, game_column in _TABLES:
                    if time.monotonic() >= deadline or (
                        stop is not None and stop.is_set()
                    ):
                        raise RuntimeError("snapshotの有限待機を終了しました")
                    predicate = sql.SQL("tenant_id=%s")
                    parameters = (tenant,)
                    if game_column is not None:
                        predicate += sql.SQL(" AND {}=%s").format(
                            sql.Identifier(game_column)
                        )
                        parameters = (tenant, game)
                    query = sql.SQL(
                        "SELECT to_jsonb(t)::text FROM {}.{} AS t WHERE {} "
                        'ORDER BY to_jsonb(t)::text COLLATE "C"'
                    ).format(sql.Identifier(schema), sql.Identifier(table), predicate)
                    # canonical JSON全行はこのRAM内だけ。ファイルへはsummaryのみを出す。
                    rows = connection.execute(query, parameters).fetchall()
                    result[schema + "." + table] = tuple(row[0] for row in rows)
        _check_snapshot(result)
    except Exception:
        raise RuntimeError("owned admin snapshotを完了できません") from None
    return result


def _continue(directory: Path) -> None:
    """失敗/停止時にもapp側の有限barrierを解放する。"""
    (directory / "continue").write_text("continue\n", encoding="utf-8")


def _observe_before(
    directory: Path,
    stop: threading.Event,
    observed: _Observation,
    dsn: str,
    tenant: UUID,
    *,
    timeout: float = 180,
) -> None:
    """公開game markerを有限待機し、最初record前の全行を採る。"""
    try:
        deadline = time.monotonic() + timeout
        marker = directory / "started.json"
        while not marker.is_file():
            if stop.wait(0.02):
                raise RuntimeError("marker停止")
            if time.monotonic() >= deadline:
                raise TimeoutError("marker有限待機")
        value = json.loads(marker.read_text(encoding="utf-8"))
        if (
            type(value) is not dict
            or set(value) != {"game"}
            or type(value["game"]) is not str
        ):
            raise ValueError("公開marker形不一致")
        game = UUID(value["game"])
        if str(game) != value["game"]:
            raise ValueError("公開game UUID形不一致")
        observed.game = game
        observed.before = _read_snapshot(dsn, tenant, game, stop)
    except Exception as error:
        # 例外原値/DSN/原行は保持・表示しない。
        observed.error_kind = type(error).__name__
    finally:
        _continue(directory)


def _instrument_script(original: str) -> str:
    """真正HTTP処理を保ち、markerと元flush後の固定故障だけを足す。"""
    additions = r"""
from pathlib import Path as AtomicPath
from pitchlog.sync import stats_native_flush as atomic_flush
_atomic = {"flush_completions": 0, "injected_faults": 0,
           "fault_seen": False, "success_ack": False}
_atomic_fault = RuntimeError("stats-native-atomicity-after-flush")
_original_flush = atomic_flush._flush_native_stats

def _fault_after_actual_flush(*args, **kwargs):
    _original_flush(*args, **kwargs)
    _atomic["flush_completions"] += 1
    _atomic["injected_faults"] += 1
    raise _atomic_fault

atomic_flush._flush_native_stats = _fault_after_actual_flush
"""
    marker = r"""
        atomic_directory = AtomicPath("/atomicity-sync")
        atomic_pending = atomic_directory / "started-writing.json"
        atomic_pending.write_text(json.dumps({"game": game}), encoding="utf-8")
        atomic_pending.replace(atomic_directory / "started.json")
        atomic_deadline = asyncio.get_running_loop().time() + 60
        while not (atomic_directory / "continue").is_file():
            if asyncio.get_running_loop().time() >= atomic_deadline:
                raise RuntimeError("stats-native-atomicity-marker-timeout")
            await asyncio.sleep(0.02)
"""
    substitutions = (
        ("runtime_diagnostics = {}", additions + "\nruntime_diagnostics = {}"),
        (
            "    except Exception as error:\n        original =",
            "    except Exception as error:\n"
            '        _atomic["fault_seen"] = error is _atomic_fault\n'
            "        original =",
        ),
        (
            "        current = read.json()\n        previous_d5 = []",
            "        current = read.json()\n" + marker + "\n        previous_d5 = []",
        ),
        (
            "            assert posted.status_code == 200, (",
            '            _atomic["success_ack"] = posted.status_code == 200 and any(\n'
            '                r.get("a5Result") == "受理"\n'
            '                for r in posted.json().get("eventResults", [])\n'
            "            )\n            assert posted.status_code == 200, (",
        ),
        (
            "print(json.dumps(out))",
            r"""
# 元例外/原payload/資格はpublic resultへ出さない。元関数の失敗assertは保持する。
atomic_result = dict(_atomic, game=game, request_failed="exception" in out,
                    fault_type=runtime_diagnostics.get("exception_type"))
if "exception" in out:
    atomic_result["exception"] = "request_failed"
print(json.dumps(atomic_result))
""",
        ),
    )
    for before, after in substitutions:
        if original.count(before) != 1:
            raise AssertionError("元HTTP scriptの固定接合点が不一致です")
        original = original.replace(before, after, 1)
    compile(original, "<stats-native-atomicity-http>", "exec")
    return original


def _require_fault_result(result: object, game: UUID) -> None:
    """本物flush完了→固定故障→失敗をstrictに要求し、成功ACKを拒否する。"""
    expected = {
        "game": str(game),
        "flush_completions": 1,
        "injected_faults": 1,
        "fault_seen": True,
        "success_ack": False,
        "request_failed": True,
        "fault_type": "RuntimeError",
        "exception": "request_failed",
    }
    if (
        type(result) is not dict
        or set(result) != set(expected)
        or any(type(key) is not str for key in result)
    ):
        raise AssertionError("故障HTTP結果の閉集合が不一致です")
    typed_result = cast(dict[str, object], result)
    if any(
        type(typed_result[key]) is not type(value) or typed_result[key] != value
        for key, value in expected.items()
    ):
        raise AssertionError("元flush後の固定故障又は成功ACK無しを確認できません")


def test_stats_native_after_flush_fault_restores_business_rows(
    vertical_database, monkeypatch, tmp_path: Path
) -> None:
    """開始後/初球前の13表と故障後を比較する。旧要求終結/新D5可否は未観測。"""
    db = vertical_database
    directory = tmp_path / "atomicity-sync"
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)  # 容器の製品UID20003とmarker/continueだけを共有する。
    observed = _Observation()
    stop = threading.Event()
    observer = threading.Thread(
        target=_observe_before,
        args=(
            directory,
            stop,
            observed,
            db.authority.database.business_admin,
            db.tenant_id,
        ),
        daemon=True,
        name="stats-native-atomicity-observer",
    )
    original_arguments = ordinary._app_arguments

    def mounted_arguments(database, case):
        args = original_arguments(database, case)
        args[1:1] = ["--volume", f"{directory}:/atomicity-sync:rw"]
        return args

    failure_kind = None
    observer.start()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(ordinary, "_SCRIPT", _instrument_script(ordinary._SCRIPT))
            patch.setattr(ordinary, "_app_arguments", mounted_arguments)
            # module bindingだけを差替え、共有tempfile/subprocessは改変しない。
            patch.setattr(
                ordinary, "tempfile", SimpleNamespace(gettempdir=lambda: str(tmp_path))
            )
            try:
                ordinary.test_actual_http_create_start_three_pitches_replay_and_prefix_reload(
                    db
                )
            except Exception as error:
                failure_kind = type(error).__name__
    finally:
        stop.set()
        _continue(directory)
        observer.join(timeout=30)
    if observer.is_alive() or observed.error_kind is not None:
        raise AssertionError("保存前observerを安全に完了できません")
    if observed.game is None or observed.before is None or observed.game == db.game_id:
        raise AssertionError("実POST新規gameの保存前snapshotがありません")
    if failure_kind != "AssertionError":
        raise AssertionError("元HTTP関数の失敗結果assertを確認できません")
    path = tmp_path / (
        "pitchlog/ordinary37-runtime-source-candidate-20261030/newAPI-last-result.json"
    )
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise AssertionError("元tmp writerの故障結果を読めません") from None
    _require_fault_result(result, observed.game)
    after = _read_snapshot(
        db.authority.database.business_admin, db.tenant_id, observed.game
    )
    evidence = {
        "scope": "owned ordinary first record / after genuine stats flush fault only",
        "game": str(observed.game),
        "failure": result,
        "before": _snapshot_summary(observed.before),
        "after": _snapshot_summary(after),
        "not_observed": [
            "old_request_termination",
            "new_d5_eligibility",
            "other_profiles",
        ],
    }
    (tmp_path / "stats-native-atomicity-observed.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _require_unchanged(observed.before, after)
