"""通常49試験driverの既挙動維持・有限実行範囲をDBなしで確認する。"""

import ast
import hashlib
import inspect

from db.test_d03_normal49_http import normal49_script
from db.test_stats_appearance_http import _lifecycle_appearance_script

_R20_DRIVER_SHA256 = "dd7092273b5fa6dfef2ef6f968565ab2cbca96f95b931f4cb1394aaf10b776b4"


def test_r20_candidate_script_is_byte_identical_after_pure_extraction():
    """旧候補の実操作scriptを変更せず、配置前提だけ別testへ分離する。"""
    script = _lifecycle_appearance_script()
    assert hashlib.sha256(script.encode()).hexdigest() == _R20_DRIVER_SHA256
    compile(script, "original-r20-driver", "exec")


def test_normal49_script_is_deterministic_and_compiles_all_observation_stages():
    """同一試合の三観測点と既終了/再開操作を固定して実行可能にする。"""
    script = normal49_script()
    assert script == normal49_script()
    compile(script, "normal49-driver", "exec")
    assert script.count('print("D03_NORMAL49:"') == 3
    for stage in ("start-zero", "before-sub", "after-sub"):
        assert script.count(repr(stage)) == 1
    assert "assert pitch_count(first_stats) == 3" in script
    assert "assert pitch_count(final_stats) == 4" in script
    assert 'assert reloaded["checkpoint"] == final["checkpoint"]' in script
    assert 'assert reloaded["lifecycle"] == final["lifecycle"]' in script


def test_normal49_test_never_installs_a_candidate_or_extra_permissions():
    """正規配置を読取検査し、既候補installをno-op化する経路も持たない。"""
    from db import test_d03_normal49_http as source

    tree = ast.parse(inspect.getsource(source))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    forbidden = {"_install_candidate", "_install_csv_candidate"}
    assert not any(
        isinstance(n.func, ast.Name) and n.func.id in forbidden for n in calls
    )
    literals = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    assert not any(
        value.lstrip()
        .upper()
        .startswith(
            ("GRANT ", "REVOKE ", "CREATE ", "ALTER ", "INSERT INTO PUBLIC.GAMES")
        )
        for value in literals
    )
