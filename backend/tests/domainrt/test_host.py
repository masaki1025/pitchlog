"""製品の常駐 Node ホストの失敗閉鎖を検証する。"""

import hashlib
import json
import os
import signal
import subprocess
from pathlib import Path

import pytest

from pitchlog.domainrt import DomainRuntimeError, NodeDomainHost, open_domain_host

_FIXTURE = Path(__file__).parent / "fixtures/synthetic_artifact.js"


def _fixture_files(tmp_path: Path) -> tuple[Path, Path]:
    """合成 artifact と対応する宣言を一時配置する。"""
    artifact = tmp_path / "pitchlog-domain.js"
    declaration = tmp_path / "pitchlog-domain.json"
    content = _FIXTURE.read_bytes()
    artifact.write_bytes(content)
    declaration.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "fileName": artifact.name,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return artifact, declaration


def _request(mode: str, value: str = "0") -> str:
    """整数を文字列で持つ試験要求を作る。"""
    return json.dumps({"mode": mode, "value": value})


def test_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    """① 宣言と異なる artifact を起動時に拒否する。"""
    artifact, declaration = _fixture_files(tmp_path)
    artifact.write_text("changed", encoding="utf-8")
    with pytest.raises(DomainRuntimeError, match="SHA-256") as caught:
        NodeDomainHost(artifact, declaration)
    assert caught.value.code == "HASH_MISMATCH"


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    """② artifact 不在では起動しない。"""
    artifact, declaration = _fixture_files(tmp_path)
    artifact.unlink()
    with pytest.raises(DomainRuntimeError) as caught:
        NodeDomainHost(artifact, declaration)
    assert caught.value.code == "ARTIFACT_UNAVAILABLE"


def test_invalid_declaration_fails_closed(tmp_path: Path) -> None:
    """不正な宣言は起動時に拒否する。"""
    artifact, declaration = _fixture_files(tmp_path)
    declaration.write_text("{}", encoding="utf-8")
    with pytest.raises(DomainRuntimeError) as caught:
        NodeDomainHost(artifact, declaration)
    assert caught.value.code == "INVALID_DECLARATION"


def test_time_limit_restarts_process(tmp_path: Path) -> None:
    """③ VM の時間上限超過を拒否し次の要求に備える。"""
    with NodeDomainHost(*_fixture_files(tmp_path)) as host:
        with pytest.raises(DomainRuntimeError) as caught:
            host.call("probe", _request("loop"))
        assert caught.value.code == "TIME_LIMIT"
        assert json.loads(host.call("probe", _request("echo", "-1"))) == {
            "ok": True,
            "value": "-1",
        }


def test_python_reply_timeout_restarts_process(tmp_path: Path) -> None:
    """Python 側の応答待ち上限でも未完了要求を失敗にする。"""
    with NodeDomainHost(*_fixture_files(tmp_path), reply_timeout_seconds=0.2) as host:
        with pytest.raises(DomainRuntimeError) as caught:
            host.call("probe", _request("never"))
        assert caught.value.code == "PROCESS_FAILURE"
        assert json.loads(host.call("probe", _request("echo", "3")))["value"] == "3"


def test_memory_limit_restarts_process(tmp_path: Path) -> None:
    """④ Node のヒープ上限超過を失敗とし再起動する。"""
    with NodeDomainHost(
        *_fixture_files(tmp_path), vm_timeout_ms=10000, reply_timeout_seconds=5
    ) as host:
        with pytest.raises(DomainRuntimeError) as caught:
            host.call("probe", _request("memory"))
        assert caught.value.code == "PROCESS_FAILURE"
        assert json.loads(host.call("probe", _request("echo", "1")))["value"] == "1"


@pytest.mark.parametrize("mode", ["eval", "newFunction", "constructor"])
def test_string_code_generation_is_rejected(tmp_path: Path, mode: str) -> None:
    """⑤⑥ eval と二経路の Function 構築を拒否する。"""
    with NodeDomainHost(*_fixture_files(tmp_path)) as host:
        with pytest.raises(DomainRuntimeError) as caught:
            host.call("probe", _request(mode))
        assert caught.value.code == "GUEST_ERROR"


def test_dynamic_import_is_rejected(tmp_path: Path) -> None:
    """⑦ ローダーなしの動的 import を拒否する。"""
    with NodeDomainHost(*_fixture_files(tmp_path)) as host:
        with pytest.raises(DomainRuntimeError) as caught:
            host.call("probe", _request("import"))
        assert caught.value.code == "DYNAMIC_IMPORT_DISABLED"


def test_undeclared_host_globals_are_absent(tmp_path: Path) -> None:
    """⑧ ゲストからホスト能力を参照できない。"""
    with NodeDomainHost(*_fixture_files(tmp_path)) as host:
        result = json.loads(host.call("probe", _request("globals")))
    assert result == {
        "require": "undefined",
        "process": "undefined",
        "fs": "undefined",
        "console": "undefined",
    }


@pytest.mark.parametrize("value", ["18446744073709551621", "-18446744073709551621"])
def test_real_artifact_ping_roundtrips_decimal_strings(value: str) -> None:
    """⑨ 実 artifact で 2^64 超と負数を十進文字列のまま返す。"""
    with open_domain_host() as host:
        response = host.call("ping", json.dumps({"value": value}))
    assert response == json.dumps({"ok": True, "value": value}, separators=(",", ":"))


def test_dead_process_restarts_for_next_request(tmp_path: Path) -> None:
    """⑩ プロセスの異常終了後に再起動する。"""
    with NodeDomainHost(*_fixture_files(tmp_path)) as host:
        process = host._process
        assert process is not None
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
        with pytest.raises(DomainRuntimeError) as caught:
            host.call("probe", _request("echo"))
        assert caught.value.code == "PROCESS_FAILURE"
        assert json.loads(host.call("probe", _request("echo", "2")))["value"] == "2"


def test_json_number_is_rejected_before_guest(tmp_path: Path) -> None:
    """境界の数値型を Node に渡さず拒否する。"""
    with NodeDomainHost(*_fixture_files(tmp_path)) as host:
        with pytest.raises(DomainRuntimeError) as caught:
            host.call("probe", '{"value":9007199254740993}')
        assert caught.value.code == "INVALID_BOUNDARY"


def test_wrong_node_version_fails_before_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """指定外の Node 版で起動しない。"""
    artifact, declaration = _fixture_files(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "v0.0.0\n"),
    )
    with pytest.raises(DomainRuntimeError) as caught:
        NodeDomainHost(artifact, declaration)
    assert caught.value.code == "NODE_VERSION"
