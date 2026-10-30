"""未適用SQL候補の固定境界を確認する。DB成功試験ではない。

後半(S01〜S12)は、書込印を発行するbind_device/check_current_rightの2 bodyと、
印の表へ書く全definer body(上記2つとunit Aの`_ADMIT`)の静的契約を固定する。
実PGでの成功は`tests/db/test_first_ball_stamp_issuance.py`が別に確かめる。
"""

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from pitchlog.authz import first_ball_product
from pitchlog.authz.first_ball_write_stamp import (
    _ADMIT,
    STATE_TRANSITIONS,
    TERMINAL_STATES,
    formal_profile,
)
from pitchlog.authz.sync_right_sql import (
    _BIND_HEAD,
    _RIGHT_EXISTS,
    _RIGHT_HEAD,
    render_stamped_function_sql,
)
from pitchlog.sync.control_provider.writer_binding_models import (
    FirstBallWriteAdmission,
)

_ROOT = Path(__file__).resolve().parents[2]


def _historical_unstamped_sql() -> str:
    """旧0037の試験専用fixtureを読む。製品コードでは使用しない。"""
    return (
        Path(__file__).parent / "fixtures/sync_right_unstamped_0037.sql"
    ).read_text()


def test_exact_sql_boundary() -> None:
    """有限関数/秘密非射影/未供給binding参照を保持する。"""
    sql = _historical_unstamped_sql()
    assert sql.count("CREATE FUNCTION sync_right_api.") == 2
    assert sql.count("PERFORM sync_fence_api.assert_writer_binding(") == 2
    assert sql.count("SECURITY DEFINER") == 2
    assert sql.count("SET search_path = pg_catalog,pg_temp") == 2
    assert "FOR SHARE" in sql
    assert "UPDATE (revoked_at)" in sql
    assert "UPDATE (credential_digest)" not in sql
    assert "CREATE FUNCTION sync_fence_api." not in sql
    assert "pitchlog_initial_actor" not in sql
    assert "recording_right_deliveries" not in sql
    assert "ciphertext" not in sql
    assert "WHEN OTHERS" not in sql
    assert "RETURNS TABLE (device_matches boolean)" in sql
    assert "RETURNS TABLE (recovery_matches boolean,right_matches boolean)" in sql
    assert (
        "p_internal_generation bigint,p_recovery_generation bigint,p_proof_digest bytea"
        in sql
    )
    assert "p_binding_nonce) <> 32" in sql
    assert "p_proof_digest) <> 32" in sql
    assert sql.count("GRANT EXECUTE ON FUNCTION sync_right_api.") == 2
    assert "NOBYPASSRLS" in sql and "FORCE ROW LEVEL SECURITY" in sql


# ---------------------------------------------------------------------------
# 書込印を発行する2 bodyの静的契約(S01〜S12)
# ---------------------------------------------------------------------------

# 既存の描画(render_sync_right_sql)の出力。変えない(S01)。
_OLD_RENDER_SHA256 = "55ff49bc530e55325c2f9e7ad1f17fbe41b8f40071431777bf6efc8641bf705e"
# 印付き2 bodyの文字列そのもの。意図した変更のときだけ更新する(S03)。
_STAMPED_SHA256 = {
    "bind_device": "8994f14153a7ff696e932b60a1e44785d27420412c7e9a35f407727192d383bf",
    "check_current_right": (
        "0088634a6910663565944b7c4d80b469a2416218e0a50a7912bc397f67aeb86c"
    ),
}
_STAMP_TABLE = "sync_fence.first_ball_write_admissions"
_DOLLAR = re.compile(r"\$[A-Za-z_]*\$")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_WRITE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE)\s+sync_fence\.first_ball_write_admissions\b", re.I
)
_CHECK = re.compile(r"\bIF\s+NOT\s+FOUND\s+OR\s+row_xmin\b[\s\S]*?END\s+IF\s*;", re.I)


def _strip_literals(sql: str) -> str:
    """文字列・コメントを同じ長さの空白へ置き換える(位置を保つ)。"""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(" " * (j - i))
            i = j
        elif sql[i] == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and sql[j + 1 : j + 2] == "'":
                    j += 2
                elif sql[j] == "'":
                    j += 1
                    break
                else:
                    j += 1
            out.append(" " * (j - i))
            i = j
        else:
            out.append(sql[i])
            i += 1
    return "".join(out)


def _body_of(function_sql: str) -> str:
    """CREATE FUNCTION文から最外のdollar quote本文を返す(文字列・コメントは空白)。"""
    return _raw_body(_strip_literals(function_sql))


def _raw_body(function_sql: str) -> str:
    """CREATE FUNCTION文から最外のdollar quote本文を、文字列を残したまま返す。"""
    match = _DOLLAR.search(function_sql)
    assert match, "dollar quoteが無い"
    tag = match.group(0)
    return function_sql[match.end() : function_sql.index(tag, match.end())]


def _scan_blocks(body: str) -> list[dict]:
    """本文をBEGIN/EXCEPTION/ENDの入れ子として走査する。

    `CASE ... END`(式)と`END IF`/`END LOOP`はblockの終端と取り違えない。`END;`の
    直後の`IF`は`END IF`と誤認しない(空白だけで続く次語のみを見る)。
    `RAISE EXCEPTION`はEXCEPTION節と取り違えない。

    Returns:
        各blockの{start,end,exception}。
    """
    toks = [(m.group(0).upper(), m.start()) for m in _TOKEN.finditer(body)]
    blocks: list[dict] = []
    stack: list[dict] = []
    for idx, (tok, pos) in enumerate(toks):
        prev = toks[idx - 1][0] if idx else ""
        nxt = ""
        if idx + 1 < len(toks):
            gap = body[pos + len(tok) : toks[idx + 1][1]]
            nxt = toks[idx + 1][0] if gap.strip() == "" else ""
        if tok == "BEGIN":
            block = {"start": pos, "end": None, "exception": False, "kind": "BLOCK"}
            blocks.append(block)
            stack.append(block)
        elif tok == "CASE":
            stack.append({"kind": "CASE"})
        elif tok == "EXCEPTION" and prev != "RAISE":
            top = next((x for x in reversed(stack) if x["kind"] == "BLOCK"), None)
            assert top is not None, "EXCEPTIONがblockの外にある"
            top["exception"] = True
        elif tok == "END":
            if nxt in ("IF", "LOOP"):
                continue
            top = stack.pop()
            if top["kind"] == "BLOCK":
                top["end"] = pos
    assert not stack, "BEGIN/ENDが釣り合わない"
    return blocks


def _enclosing(blocks: list[dict], pos: int) -> list[dict]:
    """posを含むblockを内側から外側の順で返す。"""
    inside = [b for b in blocks if b["start"] <= pos < b["end"]]
    return sorted(inside, key=lambda b: -b["start"])


def _stamp_violations(function_sql: str) -> tuple[list[str], int]:
    """印の表へ書くbodyの契約違反と書込数を返す(第3.4-1・3)。

    印への書込と、そのRETURNING xminのtop-level照合(`IF NOT FOUND ... row_xmin`)は、
    EXCEPTION節を持つblockに囲まれてはならない(囲まれるとxminがsubxidになり照合が
    常に失敗する)。照合IFは`NOT FOUND`・`row_xmin IS NULL`・top-level xidとの不一致を
    全て含み、固定42501で閉じる。読取・他行のxmin参照は対象外。
    """
    body = _body_of(function_sql)
    blocks = _scan_blocks(body)
    found: list[str] = []
    writes = list(_WRITE.finditer(body))
    checks = list(_CHECK.finditer(body))
    for match in writes:
        stmt = body[match.start() : body.index(";", match.end())]
        if not re.search(r"RETURNING[\s\S]*xmin[\s\S]*INTO\s+row_xmin", stmt, re.I):
            found.append("write-without-returning-xmin")
        if any(b["exception"] for b in _enclosing(blocks, match.start())):
            found.append("write-in-exception-block")
    for match in checks:
        if any(b["exception"] for b in _enclosing(blocks, match.start())):
            found.append("xmin-check-in-exception-block")
        text = re.sub(r"\s+", " ", match.group(0))
        if not text.startswith("IF NOT FOUND OR row_xmin IS NULL OR"):
            found.append("xmin-check-weakened")
        if "pg_catalog.mod(own_xid::numeric,4294967296::numeric)" not in text:
            found.append("xmin-check-missing-comparison")
    if writes and not checks:
        found.append("xmin-check-missing")
    # 照合は全ての書込より後ろにある(書込を照合の後へ移さない)。
    if (
        writes
        and checks
        and min(c.start() for c in checks) < max(w.start() for w in writes)
    ):
        found.append("xmin-check-before-write")
    return found, len(writes)


def _stamped_functions() -> dict[str, str]:
    return render_stamped_function_sql()


def _definer_bodies() -> dict[str, str]:
    """印の表へ書くdefiner bodyの全部(unit Aの`_ADMIT`とBの2関数)。"""
    stamped = _stamped_functions()
    return {
        "A._ADMIT": _ADMIT,
        "B.bind_device": stamped["bind_device"],
        "B.check_current_right": stamped["check_current_right"],
    }


def _header(function_sql: str, name: str) -> str:
    """CREATE [OR REPLACE] FUNCTION文の宣言部(DECLAREの前)を返す。"""
    pattern = (
        rf"FUNCTION sync_right_api\.{name}\((.*?)\)\nRETURNS TABLE \((.*?)\)"
        rf" (LANGUAGE plpgsql VOLATILE SECURITY DEFINER\nSET search_path ="
        rf" pg_catalog,pg_temp) AS \$function\$"
    )
    match = re.search(pattern, function_sql, re.S)
    assert match, name
    return "|".join(match.groups())


def test_s01_existing_render_is_unchanged() -> None:
    """S01: 既存の_historical_unstamped_sql()の出力はbyte単位で変わらない。"""
    digest = hashlib.sha256(_historical_unstamped_sql().encode()).hexdigest()
    assert digest == _OLD_RENDER_SHA256


@pytest.mark.parametrize("name", ["bind_device", "check_current_right"])
def test_s02_stamped_body_keeps_the_abi(name: str) -> None:
    """S02: 印付きbodyの署名(引数・戻り・security・search_path)は既存と同じ。"""
    stamped = _stamped_functions()[name]
    assert stamped.startswith(f"CREATE OR REPLACE FUNCTION sync_right_api.{name}(")
    assert _header(stamped, name) == _header(_historical_unstamped_sql(), name)
    # 入口のassert(別phase/nonce/tenantを通さない既存の検査)をそのまま先頭に持つ。
    from pitchlog.authz.sync_right_sql import _ASSERT

    assert f"BEGIN\n{_ASSERT}" in stamped
    assert "ALTER FUNCTION" not in stamped and "GRANT" not in stamped


@pytest.mark.parametrize("name", ["bind_device", "check_current_right"])
def test_s03_stamped_body_sha256_is_pinned(name: str) -> None:
    """S03: 印付き2 bodyの文字列を固定する。意図した変更のときだけ固定値を更新する。"""
    digest = hashlib.sha256(_stamped_functions()[name].encode()).hexdigest()
    assert digest == _STAMPED_SHA256[name]


def test_s04_block_rule_holds_for_all_three_definer_bodies() -> None:
    """S04: 印へ書く3 body全部で、書込とxmin照合がEXCEPTION節付きblockの外にある。"""
    for label, sql in _definer_bodies().items():
        found, writes = _stamp_violations(sql)
        assert found == [], (label, found)
        assert writes == (1 if label == "A._ADMIT" else 2), (label, writes)


def test_s04_scanner_detects_the_three_block_mutations() -> None:
    """S04対向: 走査器が3種の変異を赤にする(走査器自体の検査)。"""
    bind = _stamped_functions()["bind_device"]
    # (i) Bの書込をEXCEPTION付きblockで包む
    mutated = bind.replace(
        "own_xid := pg_catalog.pg_current_xact_id()::text;",
        "BEGIN\nown_xid := pg_catalog.pg_current_xact_id()::text;",
        1,
    ).replace(
        "RETURN QUERY SELECT matches;",
        "EXCEPTION WHEN others THEN RAISE;\nEND;\nRETURN QUERY SELECT matches;",
        1,
    )
    assert "write-in-exception-block" in _stamp_violations(mutated)[0]
    # (ii) Aの外側UPDATEを内側block(EXCEPTION付き)へ移す
    start = _ADMIT.index("UPDATE sync_fence.first_ball_write_admissions")
    end = _ADMIT.index(";", _ADMIT.index("RETURNING", start)) + 1
    moved = _ADMIT[:start] + _ADMIT[end:]
    moved = moved.replace(
        "EXCEPTION WHEN no_data_found",
        _ADMIT[start:end] + "\n EXCEPTION WHEN no_data_found",
        1,
    )
    assert "write-in-exception-block" in _stamp_violations(moved)[0]
    # (iii) 最外blockにEXCEPTION節を足す
    outer = _ADMIT.replace(
        "RETURN NEW;\nEND;\n$stamp$",
        "RETURN NEW;\nEXCEPTION WHEN others THEN RAISE;\nEND;\n$stamp$",
        1,
    )
    assert outer != _ADMIT
    assert "write-in-exception-block" in _stamp_violations(outer)[0]


def test_s04_scanner_ignores_expression_case_end_and_raise_exception() -> None:
    """S04補助: CASE式のENDとRAISE EXCEPTIONをblockの終端・節と取り違えない。"""
    sql = """CREATE FUNCTION f() RETURNS int LANGUAGE plpgsql AS $function$
BEGIN
 x := CASE WHEN a THEN 1 ELSE 2 END;
 IF b THEN RAISE EXCEPTION 'EXCEPTION BEGIN END'; END IF;
 BEGIN
  y := 1;
 END;
 IF c THEN y := 2; END IF;
END;
$function$;"""
    blocks = _scan_blocks(_body_of(sql))
    assert len(blocks) == 2 and not any(b["exception"] for b in blocks)


def _insert_columns(sql: str) -> list[str]:
    match = re.search(
        r"INSERT INTO sync_fence\.first_ball_write_admissions\(([^)]*)\)", sql
    )
    assert match
    return match.group(1).split(",")


def test_s05_b_bodies_have_the_closed_write_shape() -> None:
    """S05: Bの2 bodyはEXCEPTION・UPSERT・state以外のSETを持たず、書込は各1箇所。"""
    model_cols = [c.name for c in FirstBallWriteAdmission.__table__.c]
    immutable = model_cols[:27]
    assert model_cols[27:] == ["state", "source_event_id", "play_row_id", "consumed_at"]
    for name in ("bind_device", "check_current_right"):
        sql = _stamped_functions()[name]
        body = _body_of(sql)
        assert not any(blk["exception"] for blk in _scan_blocks(body)), name
        raw = _raw_body(sql)
        assert not re.search(r"\bON\s+CONFLICT\b", body, re.I), name
        assert len(re.findall(r"INSERT\s+INTO", body, re.I)) == 1, name
        assert len(re.findall(r"\bUPDATE\s+sync_fence", body, re.I)) == 1, name
        assert not re.search(r"\bDELETE\b|\bTRUNCATE\b", body, re.I), name
        assert _insert_columns(sql) == [*immutable, "state"], name
        # UPDATEのSETはstateだけ(消費3列を書くのはunit Aのguardだけ)。
        update = re.search(
            r"UPDATE sync_fence\.first_ball_write_admissions s SET (.*?)\n WHERE ",
            raw,
            re.S,
        )
        assert update and update.group(1).startswith("state=CASE")
        assert raw.count(" SET ") == 1
        assert not re.search(
            r"\b(source_event_id|play_row_id|consumed_at)\s*=", update.group(1)
        ), name
        # 不変27列は呼び出し引数からでなくwriter_bindingsの行から写す。
        assert "FROM sync_fence.writer_bindings b" in raw
        assert "b.transaction_id=own_xid" in raw
        # 例外の文言は固定で秘密値を含めない。
        assert "first ball stamp rejected" in sql
        for secret in ("p_binding_nonce", "p_credential_digest", "p_proof_digest"):
            raise_texts = re.findall(r"RAISE EXCEPTION[^;]*;", sql)
            assert not any(secret in text for text in raise_texts), (name, secret)


def _in_list(text: str) -> set[str]:
    match = re.search(r"IN \(([^)]*)\)", text)
    assert match, text
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def test_s06_b_case_branches_follow_the_unit_a_transition_table() -> None:
    """S06: Bのstate遷移(CASE)を、Aの宣言から導いた期待と突き合わせる。"""
    bodies = _stamped_functions()
    # (前状態, 事象, 次状態)をAの宣言から取り出す。consume(A guardだけ)はBの対象外。
    by_event: dict[str, list[tuple[str, str]]] = {}
    for prev, event, nxt in STATE_TRANSITIONS:
        by_event.setdefault(event, []).append((prev, nxt))
    assert set(by_event) == {"device_true", "right_true", "consume"}
    # bind: absent→device_verified(INSERT)、device_verified→device_verified(UPDATE)
    bind = _raw_body(bodies["bind_device"])
    assert ("absent", "device_verified") in by_event["device_true"]
    assert "CASE WHEN matches THEN 'device_verified' ELSE 'invalid' END" in bind
    stay = [p for p, n in by_event["device_true"] if p != "absent" and n == p]
    assert stay == ["device_verified"]
    assert "WHEN s.state='device_verified' AND matches THEN 'device_verified'" in bind
    # right: device_verified/right_verified→right_verified
    prevs = {p for p, n in by_event["right_true"] if n == "right_verified"}
    assert prevs == {"device_verified", "right_verified"}
    right = _raw_body(bodies["check_current_right"])
    cond = re.search(r"WHEN s\.state IN \(([^)]*)\) AND recovery_ok", right)
    assert cond and _in_list("IN (" + cond.group(1) + ")") == prevs
    assert "THEN 'right_verified'" in right
    # 終端(invalid/consumed)は据え置き、それ以外はinvalid
    for text in (bind, right):
        term = re.search(r"WHEN s\.state IN \(([^)]*)\) THEN s\.state", text)
        assert term and _in_list("IN (" + term.group(1) + ")") == set(TERMINAL_STATES)
        assert "ELSE 'invalid' END" in text
    # Bはconsumedを書かない(消費はA guardだけ)
    assert "THEN 'consumed'" not in bind and "THEN 'consumed'" not in right
    assert "state='consumed'" not in bind and "state='consumed'" not in right


@pytest.mark.parametrize(
    ("label", "old", "new"),
    [
        (
            "xmin照合のIFを外す",
            "IF NOT FOUND OR row_xmin IS NULL\n OR row_xmin::numeric<>"
            "pg_catalog.mod(own_xid::numeric,4294967296::numeric) THEN\n"
            " RAISE EXCEPTION 'first ball stamp rejected' "
            "USING ERRCODE='42501';\nEND IF;\n",
            "",
        ),
        (
            "照合を弱める",
            "IF NOT FOUND OR row_xmin IS NULL\n OR",
            "IF row_xmin IS NOT NULL AND",
        ),
        (
            "UPSERTにする",
            "AND b.transaction_id=own_xid\n RETURNING xmin",
            "AND b.transaction_id=own_xid\n ON CONFLICT DO NOTHING\n RETURNING xmin",
        ),
        (
            "SETにstate以外を足す",
            "UPDATE sync_fence.first_ball_write_admissions s SET state=",
            "UPDATE sync_fence.first_ball_write_admissions s "
            "SET consumed_at=NULL,state=",
        ),
    ],
)
def test_s07_structure_tests_catch_mutations_without_the_sha_pin(
    label: str, old: str, new: str
) -> None:
    """S07: sha固定を外しても、構造の検査だけで変異を検出できる。"""
    for name in ("bind_device", "check_current_right"):
        sql = _stamped_functions()[name]
        assert old in sql, (label, name)
        mutated = sql.replace(old, new, 1)
        found, _ = _stamp_violations(mutated)
        body = _raw_body(mutated)
        structural = (
            bool(found)
            or bool(re.search(r"\bON\s+CONFLICT\b", body, re.I))
            or not re.search(r"SET state=", body)
            or len(re.findall(r"\bSET\b", body)) != 1
            or bool(re.search(r"SET [a-z_]+=NULL,", body))
        )
        assert structural, (label, name)
    # EXCEPTION節を足す変異はS04(block規則)とS05(EXCEPTION無し)が検出する。
    sql = _stamped_functions()["bind_device"].replace(
        "RETURN QUERY SELECT matches;",
        "RETURN QUERY SELECT matches;\nEXCEPTION WHEN others THEN RAISE;",
        1,
    )
    assert any(blk["exception"] for blk in _scan_blocks(_body_of(sql)))
    assert "write-in-exception-block" in _stamp_violations(sql)[0]


def _load_json(relative: str) -> dict:
    return json.loads((_ROOT / relative).read_text(encoding="utf-8"))


def test_s08_registration_follow_ups_are_consistent() -> None:
    """S08: 新表の登録追随(manifest・分類・表要素・runtime契約)が揃っている。"""
    table = "first_ball_write_admissions"
    manifest = _load_json("contracts/db/schema-manifest.json")
    assert table in {t["name"] for t in manifest["tables"]}
    classification = _load_json("contracts/authz/product/table-classification.json")
    assert any(
        r.get("table") == table and r.get("profile") == "function_only"
        for r in _walk_rows(classification)
    )
    ddl = _load_json("contracts/authz/product/ddl-elements.json")
    assert any(
        t["table_id"] == table
        and t["schema_name"] == "sync_fence"
        and t["enable_row_level_security"] is True
        and t["force_row_level_security"] is True
        for t in ddl["tables"]
    )
    bodies = _load_json("contracts/authz/product/function-bodies/manifest.json")
    assert any(
        e.get("element_type") == "table" and e.get("element_id") == table
        for e in _walk_rows(bodies)
    )
    assert table in first_ball_product.TABLES
    assert f"table|{table}" in first_ball_product.BODIES
    from pitchlog.authz.runtime_contract import PROTECTED_TABLES

    assert ("sync_fence", table) in PROTECTED_TABLES


def _walk_rows(value: object) -> list[dict]:
    """入れ子のJSONから辞書をすべて集める(分類・manifestの構造差を吸収する)。"""
    rows: list[dict] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            rows.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return rows


def test_s09_formal_profile_is_registered_exactly() -> None:
    """S09: 正式profileの全宣言がinstaller資産へ過不足なく存在する。"""
    from pitchlog.authz.first_ball_write_stamp import formal_declarations

    profile = formal_profile()
    assert profile["runtime_registered"] is True
    assert profile["stamp_issuance"] == "STAMPED_BIND_RIGHT"
    ddl = _load_json("contracts/authz/product/ddl-elements.json")
    assert first_ball_product.validate(ddl)
    for section, rows in formal_declarations().items():
        for row in rows:
            assert ddl[section].count(row) == 1


def test_s10_old_and_stamped_bodies_come_from_the_same_template() -> None:
    """S10: 既存の描画と印付き描画は同じ共有断片から生成される(重複実装を作らない)。"""
    old = _historical_unstamped_sql()
    stamped = _stamped_functions()
    for fragment in (_BIND_HEAD, _RIGHT_HEAD, _RIGHT_EXISTS):
        assert fragment in old, fragment[:40]
    assert _BIND_HEAD in stamped["bind_device"]
    assert _RIGHT_HEAD in stamped["check_current_right"]
    assert _RIGHT_EXISTS in stamped["check_current_right"]


def test_s11_formal_bodies_are_the_single_stamped_source() -> None:
    """S11: 正式bind/right本文は単一stamped描画と一致する。"""
    for name, source in _stamped_functions().items():
        row = next(
            row
            for row in first_ball_product.ADDITIONS["functions"]
            if row["schema_name"] == "sync_right_api" and row["function_name"] == name
        )
        key = "function|" + row["function_id"]
        value = first_ball_product.BODIES[key]
        assert (
            source.replace("CREATE OR REPLACE FUNCTION", "CREATE FUNCTION", 1) in value
        )
        assert "first_ball_write_admissions" in value
        path = (
            _ROOT
            / "contracts/authz/product/function-bodies/functions"
            / (row["function_id"] + ".sql")
        )
        assert path.read_text() == value


def test_s12_old_production_renderer_is_removed() -> None:
    """S12: 旧描画の並走を終了し、旧SQLは製品が読まないfixtureへ閉じる。"""
    import inspect

    from pitchlog.authz import sync_right_sql

    assert not hasattr(sync_right_sql, "render_sync_right_sql")
    assert (
        hashlib.sha256(_historical_unstamped_sql().encode()).hexdigest()
        == _OLD_RENDER_SHA256
    )
    assert "_historical_unstamped_sql" not in inspect.getsource(sync_right_sql)


# ---------------------------------------------------------------------------
# 呼び出し側の前提(示せることと示せないこと)の固定(S13〜S15)
#
# 製品コードにはbind/rightの呼び出し元がまだ無い。以下は「いま成り立つ事実」を
# 変更検知として固定するだけで、配線(U09/E-1 3B)が正しいことを示すものではない。
# ---------------------------------------------------------------------------

_SRC = _ROOT / "backend" / "src" / "pitchlog"


def _called_names(node: ast.AST) -> list[tuple[int, str]]:
    """ノード内の呼び出しを(行, 呼び出し式)で返す。"""
    return sorted(
        (c.lineno, ast.unparse(c.func))
        for c in ast.walk(node)
        if isinstance(c, ast.Call)
    )


def _function_node(path: Path, name: str, cls: str | None = None) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    scope: ast.AST = tree
    if cls is not None:
        scope = next(
            n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls
        )
    return next(
        n for n in ast.walk(scope) if isinstance(n, ast.FunctionDef) and n.name == name
    )


def test_s13_run_in_savepoint_never_reaches_function_tokens() -> None:
    """S13: run_in_savepointはself.run(DML registry)だけを呼び、run_functionに届かない。

    製品のbegin_nestedはrun_in_savepointの中の1箇所だけである。bind/rightの
    tokenは関数registryにあるので、製品APIの上でsavepoint内では実行されない。
    """
    node = _function_node(
        _SRC / "repositories" / "transaction.py",
        "run_in_savepoint",
        "_TenantTransaction",
    )
    names = [name for _, name in _called_names(node)]
    assert "self.run" in names and "session.begin_nested" in names
    assert not any("run_function" in name for name in names), names
    hits = [
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if "begin_nested" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["repositories/transaction.py"], hits


def test_s14_port_writer_has_no_function_path_yet() -> None:
    """S14: PortWriterはDML registryのrunしか持たず、Portからbind/rightへ届かない。

    D09=αの本線(Portがwriter経由でbind/rightを呼ぶ)は、現行のPortWriterでは到達
    不能である。届かせる拡張(sync/ports.py=core)は本stepの範囲外で、U09/E-1 3Bの
    入口条件として残す。この試験は拡張が入ったときに赤くなり、見直しを促す。
    """
    from pitchlog.sync.ports import PortWriter

    assert PortWriter.__slots__ == ("_execute", "_active")
    public = {name for name in vars(PortWriter) if not name.startswith("_")}
    assert public == {"run"}, public


def test_s15_apply_locked_call_order_for_the_caller_windows() -> None:
    """S15: P1/P2の_apply_lockedで、⑤⑦はD5台帳の最初のsavepointより前にある。

    対象はprefix_path._apply_lockedが呼ぶ単一の_apply_locked_in_scope本体である
    (rejection.pyとchange_path.pyは印を
    書かないTX/別経路で対象外)。呼び出し位置は、⑤ holds_recording_right → ⑦ validate
    → D5台帳(recheck_and_insert_result) → 投影(projection.apply) → intent
    (record_d1_intents)の順で、_apply_locked自身はrun_in_savepointを直接呼ばない。
    """
    wrapper = _function_node(_SRC / "sync" / "prefix_path.py", "_apply_locked")
    assert any(name == "_apply_locked_in_scope" for _, name in _called_names(wrapper))
    node = _function_node(_SRC / "sync" / "prefix_path.py", "_apply_locked_in_scope")
    calls = _called_names(node)

    def first(suffix: str) -> int:
        return next(line for line, name in calls if name.endswith(suffix))

    order = [
        first("holds_recording_right"),
        first("validator.validate"),
        first("recheck_and_insert_result"),
        first("projection.apply"),
        first("record_d1_intents"),
    ]
    assert order == sorted(order) and len(set(order)) == 5, order
    assert not any(name.endswith("run_in_savepoint") for _, name in calls)


def test_device_state_read_single_source_and_old_wrapper_bytes():
    """E1既wrapperのbyteを保ち、正式CREATEは同じ本文の一部だけを使う。"""
    from pitchlog.authz.sync_right_sql import (
        render_device_state_read_create_sql,
        render_device_state_read_sql,
    )

    sql = render_device_state_read_sql()
    create = render_device_state_read_create_sql()
    assert (
        hashlib.sha256(sql.encode()).hexdigest()
        == "a54b9e6e5b1416db84cc110112e82f687b4987a35f42a7fc1826a891b07695a1"
    )
    assert create in sql
    assert create.startswith(
        "CREATE OR REPLACE FUNCTION sync_right_api.read_device_state("
    )
    assert create.count("CREATE OR REPLACE FUNCTION") == 1
    assert "ALTER FUNCTION" not in create and "GRANT " not in create
    assert "p_tenant_id IS NULL OR p_device_id IS NULL" in create
    assert "session_user <> 'pitchlog_app'" in create
    assert "current_user <> 'pitchlog_sync_right_fn_owner'" in create
    assert "current_setting('app.tenant_id',true)" in create
    assert "d.tenant_id=p_tenant_id AND d.device_id=p_device_id" in create
    assert "d.revoked_at IS NULL" in create
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", create)
    assert "credential" not in create and "nonce" not in create
    assert "write_admissions" not in create


def test_unregistered_device_state_reader_has_no_write_lock_or_binding_dependency():
    """②は状態読取のみでbinding/credential/印発行を先取りしない。"""
    from pitchlog.authz.sync_right_sql import render_device_state_read_sql

    sql = render_device_state_read_sql()
    upper = sql.upper()
    assert "SECURITY DEFINER" in upper
    assert "SET SEARCH_PATH=PG_CATALOG,PG_TEMP" in upper
    assert "SESSION_USER <> 'PITCHLOG_APP'" in upper
    assert "CURRENT_USER <> 'PITCHLOG_SYNC_RIGHT_FN_OWNER'" in upper
    assert "P_TENANT_ID IS DISTINCT FROM" in upper
    assert "D.TENANT_ID=P_TENANT_ID AND D.DEVICE_ID=P_DEVICE_ID" in upper
    assert "D.REVOKED_AT IS NULL" in upper
    for forbidden in (
        "FOR SHARE",
        "FOR UPDATE",
        "BINDING_NONCE",
        "CREDENTIAL_DIGEST",
        "ASSERT_WRITER_BINDING",
        "INSERT INTO",
        "UPDATE PUBLIC",
        "DELETE FROM",
        "GRANT SELECT",
        "CREATE ROLE",
        "CREATE POLICY",
    ):
        assert forbidden not in upper
    assert upper.count("GRANT EXECUTE") == 1
