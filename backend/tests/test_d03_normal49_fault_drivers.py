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
