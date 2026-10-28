"""初球書込印の実PG試験の補助。候補の適用・scaffold・実peerを集める。

ここで行う適用は「候補の適用」であり、正式installerでの成功ではない。
(1) unit Aのcandidate_profile()の全キーを機械的にSQLへ描画し(手で権限を足さない)、
(2) 印を発行するbind_device/check_current_rightの本文を`CREATE OR REPLACE`で
置き換える。印(sync_fence.first_ball_write_admissions)の行をadminが直接
INSERT/UPDATEすることは一切ない(scaffoldの台帳で全statementを記録し、0件を表明する)。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any, LiteralString, cast
from uuid import uuid4

import psycopg
from psycopg import sql

from pitchlog.authz.first_ball_write_stamp import candidate_profile, require_candidate
from pitchlog.authz.sync_right_sql import render_stamped_function_sql

from .rg1_lifecycle_support import PeerSession
from .sync_writer_binding_support import (
    ACTOR,
    APP,
    BindingDatabase,
    _literal,
    assert_statement,
)

STAMP_TABLE = "sync_fence.first_ball_write_admissions"
RIGHT_OWNER = "pitchlog_sync_right_fn_owner"
STAMP_REJECT = "first ball write admission rejected"
BIND_REJECT = "first ball stamp rejected"

_META_KEYS = (
    "status",
    "state_transitions",
    "terminal_states",
    "stamp_issuance",
    "runtime_registered",
)
_RENDERED_KEYS = (
    "roles",
    "schemas",
    "table",
    "functions",
    "triggers",
    "table_acls",
    "column_acls",
    "policies",
)
# 印の表へのDMLを検出する(adminの直接投入=scaffold印を0件に保つため)。
_STAMP_DML = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(\s+TABLE)?)\s+"
    r"(ONLY\s+)?sync_fence\.first_ball_write_admissions\b",
    re.I,
)


class StderrPeer(PeerSession):
    """実peer LOGIN。拒否文の検査のためpsqlのstderrだけ保持する。"""

    def __init__(self, container: str, database: str, role: str) -> None:
        """製品で登録済みの2role以外は開かない。"""
        if role not in {ACTOR, APP}:
            raise ValueError("対象外role")
        uid = 20005 if role == ACTOR else 20003
        self._err = tempfile.TemporaryFile()
        self._err_offset = 0
        self._process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                "--user",
                f"{uid}:{uid}",
                container,
                "psql",
                "-X",
                "-A",
                "-t",
                "-q",
                "-h",
                "/var/run/postgresql",
                "-U",
                role,
                "-d",
                database,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._err,
        )
        self._buffer = b""
        self._sequence = 0
        try:
            assert self.query("SELECT session_user,current_user") == (f"{role}|{role}",)
            self.query("\\set VERBOSITY verbose\nSELECT 1")
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> StderrPeer:
        """所有sessionを返す(型をStderrPeerに保つ)。"""
        return self

    def run(self, statement: str) -> tuple[tuple[str, ...], str, str]:
        """(行, SQLSTATE, この文が出したstderr)を返す。"""
        rows, state = self.execute(statement)
        time.sleep(0.05)
        self._err.seek(self._err_offset)
        raw = self._err.read()
        self._err_offset += len(raw)
        return rows, state, raw.decode(errors="replace")


def peer(db: BindingDatabase, role: str = APP) -> StderrPeer:
    """実LOGIN主体の独立接続を返す。"""
    return StderrPeer(db.owner.authority.database.business, db.database, role)


def _grant_option(item: dict[str, Any]) -> sql.SQL:
    if item["grantable"] is True:
        return sql.SQL(" WITH GRANT OPTION")
    if item["grantable"] is False:
        return sql.SQL("")
    raise ValueError("grantable不明")


def profile_statements(profile: dict[str, Any]) -> list[tuple[str, sql.Composable]]:
    """candidate_profile()の全キーを機械的にSQLへ描画する。手で権限を足さない。

    未知キーがあれば失敗する(描画漏れを作らない)。metaキーはコメント、tableキーは
    既migration成果との一致を検査するSELECT(変更なし)として描画する。

    Args:
        profile: candidate_profile()の返す辞書。

    Returns:
        (キー名, SQL)の列。
    """
    unknown = set(profile) - set(_META_KEYS) - set(_RENDERED_KEYS)
    assert not unknown, f"描画器の未対応キー: {sorted(unknown)}"
    assert set(profile) == set(_META_KEYS) | set(_RENDERED_KEYS), sorted(profile)
    out: list[tuple[str, sql.Composable]] = []
    for key in _META_KEYS:
        text = json.dumps(profile[key], ensure_ascii=False, sort_keys=True)
        # 改行・コメント終端を含まない1行のSQLコメントにする。
        out.append(
            (
                "meta:" + key,
                sql.SQL(cast(LiteralString, "-- profile." + key + " = " + text[:200])),
            )
        )
    assert profile["roles"] == [], profile["roles"]
    for item in profile["schemas"]:
        out.append(
            (
                "schemas",
                sql.SQL("GRANT {} ON SCHEMA {} TO {}{}").format(
                    sql.SQL(item["privilege"]),
                    sql.Identifier(item["schema_name"]),
                    sql.Identifier(item["grantee"]),
                    _grant_option(item),
                ),
            )
        )
    table = profile["table"]
    assert set(table) == {
        "schema_name",
        "table_id",
        "owner",
        "enable_rls",
        "force_rls",
        "physical_delete_allowed",
        "truncate_allowed",
    }, sorted(table)
    out.append(
        (
            "table",
            sql.SQL(
                "SELECT pg_get_userbyid(c.relowner)={} AS owner_ok,"
                "c.relrowsecurity={} AS enable_rls_ok,"
                "c.relforcerowsecurity={} AS force_rls_ok "
                "FROM pg_class c WHERE c.oid={}::regclass"
            ).format(
                sql.Literal(table["owner"]),
                sql.Literal(table["enable_rls"]),
                sql.Literal(table["force_rls"]),
                sql.Literal(table["schema_name"] + "." + table["table_id"]),
            ),
        )
    )
    for item in profile["functions"]:
        out.append(("functions", sql.SQL(item["sql"])))
    for item in profile["triggers"]:
        out.append(("triggers", sql.SQL(item["sql"])))
    for item in profile["table_acls"]:
        out.append(
            (
                "table_acls",
                sql.SQL("GRANT {} ON TABLE {}.{} TO {}{}").format(
                    sql.SQL(item["privilege"]),
                    sql.Identifier(item["schema_name"]),
                    sql.Identifier(item["table_id"]),
                    sql.Identifier(item["grantee"]),
                    _grant_option(item),
                ),
            )
        )
    for item in profile["column_acls"]:
        out.append(
            (
                "column_acls",
                sql.SQL("GRANT {}({}) ON {}.{} TO {}{}").format(
                    sql.SQL(item["privilege"]),
                    sql.SQL(",").join(sql.Identifier(c) for c in item["columns"]),
                    sql.Identifier(item["schema_name"]),
                    sql.Identifier(item["table_id"]),
                    sql.Identifier(item["grantee"]),
                    _grant_option(item),
                ),
            )
        )
    for item in profile["policies"]:
        out.append(("policies", sql.SQL(item["sql"])))
    return out


def apply_candidates(owner: Any, *, stamped_bodies: bool = True) -> dict[str, int]:
    """Aのcandidate_profile(全キー)とBの2 bodyを、admin接続で適用する。

    正式installerの成功ではない(適用後の正式catalog照合はdriftを報告する)。

    Args:
        owner: InitialGrantDatabase(owned DB一式)。
        stamped_bodies: Falseならprofileだけを適用する(Bの本文は入れない)。

    Returns:
        キーごとの適用文数。
    """
    profile = candidate_profile()
    require_candidate(profile)
    counts: dict[str, int] = {}
    with psycopg.connect(owner.authority.database.business_admin) as admin:
        for key, statement in profile_statements(profile):
            counts[key] = counts.get(key, 0) + 1
            if key.startswith("meta:") or key == "table":
                continue
            admin.execute(cast(sql.Composed, statement))
        if stamped_bodies:
            for name, text in render_stamped_function_sql().items():
                admin.execute(cast(LiteralString, text))
                counts["stamped:" + name] = 1
        admin.commit()
    return counts


_BINDING_COLS = (
    "tenant_id,attempt_id,phase_id,authority_id,control_instance,business_instance,"
    "restore_epoch,control_version,issuer,lease_id,device_id,game_id,wire_d4,"
    "internal_generation,recovery_generation,codec_version,request_fingerprint,d5,"
    "event_fingerprint,system_identifier,database_oid,postmaster_started_at,"
    "backend_pid,backend_start,transaction_id,nonce_digest,expires_at"
).split(",")


def exec_text(conn: psycopg.Connection, text: str) -> None:
    """試験が組み立てた固定のSQL文字列を1文実行する(型検査のためのcast)。"""
    conn.execute(cast(LiteralString, text))


def stamp_dml_statements(statements: list[str]) -> list[str]:
    """記録された文のうち、印の表へのINSERT/UPDATE/DELETE/TRUNCATEを返す。"""
    return [text for text in statements if _STAMP_DML.search(text)]


class Ctx:
    """DB一式の共有状態。adminの全statementを記録する(scaffold印0件の表明用)。"""

    def __init__(self, db: BindingDatabase, issued: dict[str, Any]) -> None:
        """発行済みの記録権(世代・epoch・proof)を束ねる。"""
        self.db = db
        self.admin_dsn = db.owner.authority.database.business_admin
        self.tenant = db.owner.tenant_id
        self.game = db.owner.game_id
        self.device = db.owner.device_id
        self.generation = int(issued["generation"])
        self.epoch = int(issued["epoch"])
        self.proof = bytes.fromhex(issued["proof_digest"])
        self.slot = 0
        self.admin_log: list[str] = []
        self.scaffold: list[str] = []

    def admin(
        self,
        statement: str,
        params: tuple[Any, ...] | None = None,
        *,
        fetch: bool = False,
        label: str | None = None,
    ) -> list[tuple[Any, ...]] | None:
        """admin接続で1文実行し、文をscaffoldの台帳へ記録する。"""
        self.admin_log.append(statement)
        with psycopg.connect(self.admin_dsn, autocommit=True) as conn:
            cur = conn.execute(cast(LiteralString, statement), params)
            if label:
                self.scaffold.append(label)
            return cur.fetchall() if fetch else None

    def event(
        self, *, legacy: str | None = None, fingerprint: str = "public-event-fp"
    ) -> dict[str, Any]:
        """scaffold: accepted play_input event・ledger・slot(adminが直接投入)。

        製品では同じTXの先行statementが作る行を、試験では代わりに入れる。印ではない。
        """
        self.slot += 1
        d1 = self.slot
        d5, event_id = uuid4(), uuid4()
        self.admin(
            "INSERT INTO public.event_slots(tenant_id,game_id,generation,d1) "
            "VALUES (%s,%s,%s,%s)",
            (self.tenant, self.game, self.generation, d1),
            label="event_slots 1行",
        )
        self.admin(
            "INSERT INTO public.idempotency_ledger(tenant_id,d5,kind,"
            "source_fingerprint,result) VALUES (%s,%s,'accepted',%s,'{}'::jsonb)",
            (self.tenant, d5, fingerprint),
            label="idempotency_ledger accepted 1行",
        )
        self.admin(
            "INSERT INTO public.operation_events(tenant_id,id,game_id,generation,d1,"
            "d2,d5,ledger_kind,event_kind,payload,state_diff,legacy_row_identifier)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,'accepted','play_input','{}'::jsonb,"
            "'{}'::jsonb,%s)",
            (self.tenant, event_id, self.game, self.generation, d1, d1, d5, legacy),
            label="operation_events accepted/play_input 1行",
        )
        return {"d5": d5, "id": event_id, "fingerprint": fingerprint, "d1": d1}

    def begin(self, writer: StderrPeer) -> None:
        """TXを開き、tenant GUCをTX局所に設定する。"""
        writer.query("BEGIN")
        writer.query(
            "SELECT set_config('app.tenant_id'," + _literal(str(self.tenant)) + ",true)"
        )

    def publish(
        self, writer: StderrPeer, event: dict[str, Any], *, ttl: int = 25
    ) -> dict[str, Any]:
        """実writer自己観測→実actor LOGINのpublish(既存試験と同じ流儀)。"""
        attempt, phase = uuid4(), uuid4()
        identity = json.loads(
            writer.query(
                "SELECT row_to_json(i) FROM sync_fence_api.read_writer_identity("
                + _literal(self.tenant)
                + ") i"
            )[0]
        )
        nonce = os.urandom(32)
        binding = {
            "authority_id": str(uuid4()),
            "control_instance": str(uuid4()),
            "business_instance": str(uuid4()),
            "restore_epoch": str(uuid4()),
            "control_version": 1,
            "issuer": str(uuid4()),
            "lease_id": str(uuid4()),
            "device_id": str(self.device),
            "game_id": str(self.game),
            "wire_d4": "fixture-one",
            "internal_generation": self.generation,
            "recovery_generation": self.epoch,
            "codec_version": 1,
            "request_fingerprint": "public-request-fp",
            "d5": str(event["d5"]),
            "event_fingerprint": event["fingerprint"],
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=ttl)
            ).isoformat(),
            **identity,
        }
        with peer(self.db, ACTOR) as actor:
            actor.query(
                sql.SQL(
                    "SELECT sync_fence_api.publish_writer_binding("
                    "{},{},{},{}::jsonb,{})"
                )
                .format(
                    *(
                        sql.Literal(v)
                        for v in (
                            self.tenant,
                            attempt,
                            phase,
                            json.dumps(binding),
                            hashlib.sha256(nonce).digest(),
                        )
                    )
                )
                .as_string()
            )
        return {
            "attempt": attempt,
            "phase": phase,
            "nonce": nonce,
            "binding": binding,
            "event": event,
        }

    def assert_(
        self, writer: StderrPeer, b: dict[str, Any]
    ) -> tuple[tuple[str, ...], str, str]:
        """既存のassert_writer_bindingだけを呼ぶ(印は作らない)。"""
        return writer.run(
            assert_statement(
                self.tenant,
                b["attempt"],
                b["phase"],
                b["nonce"],
                self.device,
                self.game,
            )
        )

    def stamp_row(self, b: dict[str, Any]) -> list[list[Any]]:
        """印の行を読む(adminのSELECT。書込ではない)。"""
        rows = self.admin(
            "SELECT state,source_event_id::text,play_row_id::text,"
            "consumed_at IS NOT NULL FROM " + STAMP_TABLE + " "
            "WHERE tenant_id=%s AND attempt_id=%s AND phase_id=%s",
            (self.tenant, b["attempt"], b["phase"]),
            fetch=True,
        )
        return [list(r) for r in rows or []]

    def stamp_count(self) -> int:
        """印の表の全行数(adminのSELECT)。"""
        rows = self.admin("SELECT count(*) FROM " + STAMP_TABLE, fetch=True)
        assert rows is not None
        return int(rows[0][0])

    def insert_sql(
        self,
        event_id: Any,
        row_id: Any,
        *,
        legacy: str | None = None,
        unverified: bool = False,
        batch: Any = None,
        game: Any = None,
    ) -> str:
        """appがPlayRowを1行INSERTする文。"""
        return (
            "INSERT INTO public.play_rows(tenant_id,id,game_id,source_event_id,"
            "play_number,event_kind,legacy_row_identifier,migration_unverified,"
            "import_batch_id) VALUES ("
            + ",".join(
                _literal(v)
                for v in (
                    self.tenant,
                    row_id,
                    game or self.game,
                    event_id,
                    1,
                    "pitch",
                    legacy,
                    unverified,
                    batch,
                )
            )
            + ")"
        )

    def common_args(self, b: dict[str, Any], *, device: Any = None, game: Any = None):
        """bind/right共通の6引数リテラル。"""
        return ",".join(
            _literal(v)
            for v in (
                self.tenant,
                b["attempt"],
                b["phase"],
                b["nonce"],
                device or self.device,
                game or self.game,
            )
        )

    def bind_sql(self, b: dict[str, Any], credential: bytes, **kw: Any) -> str:
        """appが呼ぶbind_deviceの実ABIのSELECT(run_functionが出す文と同形)。"""
        return (
            "SELECT device_matches FROM sync_right_api.bind_device("
            + self.common_args(b, **kw)
            + ","
            + _literal(credential)
            + ")"
        )

    def right_sql(
        self,
        b: dict[str, Any],
        proof: bytes | None = None,
        *,
        generation: int | None = None,
        epoch: int | None = None,
        **kw: Any,
    ) -> str:
        """appが呼ぶcheck_current_rightの実ABIのSELECT。"""
        return (
            "SELECT recovery_matches,right_matches FROM "
            "sync_right_api.check_current_right("
            + self.common_args(b, **kw)
            + ","
            + ",".join(
                _literal(v)
                for v in (
                    generation or self.generation,
                    epoch or self.epoch,
                    proof or self.proof,
                )
            )
            + ")"
        )

    def sensitive(self, b: dict[str, Any], extra: tuple[Any, ...] = ()) -> list[str]:
        """拒否文に出てはならない値(識別子・nonce・digest・xid)。"""
        values = [
            str(self.tenant),
            str(self.game),
            str(self.device),
            str(b["attempt"]),
            str(b["phase"]),
            b["binding"]["lease_id"],
            b["nonce"].hex(),
            hashlib.sha256(b["nonce"]).hexdigest(),
            str(b["event"]["d5"]),
            str(b["event"]["id"]),
            b["binding"]["transaction_id"],
            b["event"]["fingerprint"],
            "public-request-fp",
            b["binding"]["system_identifier"],
        ]
        values += [str(v) for v in extra]
        return values


def leaks(text: str, values: list[str]) -> list[str]:
    """textに現れてしまった機微値を返す。"""
    return [v for v in values if v and v in text]


def error_lines(text: str) -> list[str]:
    """psql(VERBOSITY verbose)のstderrからERROR行だけを返す。"""
    return [line for line in text.splitlines() if line.startswith("ERROR")]
