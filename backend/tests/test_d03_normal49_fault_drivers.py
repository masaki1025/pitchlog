"""通常49故障driverの限定操作/真正処理呼出を確認する。"""

import ast

import pytest
from db.test_d03_normal49_faults import fault_script


@pytest.mark.parametrize("kind", ("native", "substitution"))
def test_fault_driver_compiles_and_keeps_real_original_calls(kind):
    """候補SQLを差し込まず、原関数完了後の同TXでのみ故障させる。"""
    script = fault_script(kind)
    compile(script, kind, "exec")
    assert script == fault_script(kind)
    assert script.count('print("D03_FAULT:"') == 2
    assert "result = _fault_original_native(handle, writer, *args, **kwargs)" in script
    assert "result = _fault_original_run(handle, operation, *args, **kwargs)" in script
    assert "runtime[0].get_transaction() is top" in script
    assert "_install_candidate" not in script
    assert "_install_csv_candidate" not in script
    literals = [
        n.value
        for n in ast.walk(ast.parse(script))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    assert not any(
        s.upper().startswith(("ALTER FUNCTION", "GRANT ", "CREATE OR REPLACE"))
        for s in literals
    )


def test_unknown_fault_writer_is_closed():
    """未知writerを既成功経路へ補完しない。"""
    with pytest.raises(ValueError):
        fault_script("other")


@pytest.mark.parametrize(
    "mutation",
    (
        "old",
        "open",
        "close_id",
        "d5",
        "attempt_id",
        "event_fingerprint",
        "request_fingerprint",
        "extra",
        "missing",
    ),
)
def test_binding_audit_rejects_nonterminal_or_mismatched_new_request(mutation):
    """監査を一律無視せず、新要求との一致/終結/旧行不変を個別に拒否する。"""
    import json

    from db.test_d03_normal49_faults import _assert_closed_binding_audit

    output = {
        "game": "game",
        "d5": "d5",
        "attempt": "attempt",
        "event_fp": "event",
        "request_fp": "request",
    }
    old = json.dumps({"state": "closed", "close_id": "old", "id": "old"})
    new = {
        "game_id": "game",
        "d5": "d5",
        "attempt_id": "attempt",
        "event_fingerprint": "event",
        "request_fingerprint": "request",
        "state": "closed",
        "close_id": "close",
    }
    name = "sync_fence.writer_bindings"
    observed = {"before": {name: [old]}, "after": {name: [old, json.dumps(new)]}}
    _assert_closed_binding_audit(observed, output)
    if mutation == "old":
        observed["after"][name][0] = json.dumps(
            {"state": "closed", "close_id": "changed"}
        )
    elif mutation == "extra":
        observed["after"][name].append(json.dumps({**new, "phase_id": "other"}))
    elif mutation == "missing":
        observed["after"][name].pop()
    else:
        key = "state" if mutation == "open" else mutation
        new[key] = None if mutation == "close_id" else "wrong"
        observed["after"][name][1] = json.dumps(new)
    with pytest.raises(AssertionError):
        _assert_closed_binding_audit(observed, output)
