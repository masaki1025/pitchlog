"""同じ実hostの再利用でも入力・artifact・全応答検査を省かない。"""

import copy
import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from test_lineup_play_prefix_continuation import CASES, current_case

from pitchlog.domainrt import lineup_play_prefix_continuation as caller
from pitchlog.domainrt.host import DomainRuntimeError, open_domain_host


def _request():
    return caller.decode_lineup_prefix_request(
        json.dumps(current_case(CASES[0])["request"])
    )


def test_one_real_host_recalculates_every_normative_row_without_result_cache(
    monkeypatch,
):
    """34行を同じ実processで再計算し、各応答を規範の全値と比較する。"""
    calls = []
    with open_domain_host() as host:
        original = host.call

        def counted(operation, raw):
            calls.append((operation, raw))
            return original(operation, raw)

        monkeypatch.setattr(host, "call", counted)
        for source in CASES:
            case = current_case(source)
            request = caller.decode_lineup_prefix_request(json.dumps(case["request"]))
            actual = caller._evaluate_lineup_prefix_with_host(request, host)
            assert (
                actual.model_dump(mode="json", by_alias=True, exclude_unset=True)
                == case["expected"]
            )
        assert len(calls) == len(CASES)
        assert {operation for operation, _ in calls} == {
            "deriveLineupPlayPrefixWithContinuation"
        }
        # 同じ入力も再度実行し、前回結果で成功を代替しない。
        caller._evaluate_lineup_prefix_with_host(_request(), host)
        assert len(calls) == len(CASES) + 1


def test_shared_host_rejects_callable_fake_before_host_call():
    """同じ属性を持つ自由objectを実hostへ昇格しない。"""
    calls = []
    fake = SimpleNamespace(
        artifact_sha256="0" * 64, call=lambda *args: calls.append(args)
    )
    with pytest.raises(TypeError):
        caller._evaluate_lineup_prefix_with_host(_request(), fake)
    assert calls == []


def test_shared_host_rejects_wrong_artifact_before_call(monkeypatch):
    """実hostでもrequestの実行pin不一致を呼出前に拒否する。"""
    case = copy.deepcopy(current_case(CASES[0]))
    case["request"]["source"]["executionArtifactSha256"] = "0" * 64
    request = caller.decode_lineup_prefix_request(json.dumps(case["request"]))
    with open_domain_host() as host:
        calls = []
        monkeypatch.setattr(host, "call", lambda *args: calls.append(args))
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller._evaluate_lineup_prefix_with_host(request, host)
        assert calls == []


def test_shared_host_failure_keeps_original_exception_identity(monkeypatch):
    """途中のhost失敗を前回成功や空応答で補わない。"""
    error = DomainRuntimeError("HOST_TEST", "試験中断")
    with open_domain_host() as host:

        def failed(*_args):
            raise error

        monkeypatch.setattr(host, "call", failed)
        with pytest.raises(DomainRuntimeError) as caught:
            caller._evaluate_lineup_prefix_with_host(_request(), host)
        assert caught.value is error


def test_shared_host_response_is_strictly_decoded(monkeypatch):
    """同じprocessでも不正応答を成功型へ補正しない。"""
    with open_domain_host() as host:
        monkeypatch.setattr(host, "call", lambda *_args: '{"ok":true}')
        with pytest.raises(caller.LineupPrefixProtocolError):
            caller._evaluate_lineup_prefix_with_host(_request(), host)


def test_closed_shared_host_cannot_reuse_previous_success():
    """close後の実hostは同じrequestでも閉拒否する。"""
    with open_domain_host() as host:
        request = _request()
        assert caller._evaluate_lineup_prefix_with_host(request, host).ok
        host.close()
        with pytest.raises(DomainRuntimeError):
            caller._evaluate_lineup_prefix_with_host(request, host)


def test_public_invalid_input_does_not_open_host(monkeypatch):
    """既public入口の入力拒否をprocess起動前に維持する。"""
    calls = []
    monkeypatch.setattr(caller, "open_domain_host", lambda: calls.append(True))
    with pytest.raises(TypeError):
        caller.evaluate_lineup_prefix_continuation(cast(Any, object()))
    assert calls == []


@pytest.mark.parametrize("fail", [False, True])
def test_public_opens_once_and_closes_on_success_or_original_failure(monkeypatch, fail):
    """既public APIは共有せず自前の一回起動と例外時cleanupを保つ。"""
    from contextlib import contextmanager

    hosts = []
    error = DomainRuntimeError("HOST_TEST", "試験中断")

    @contextmanager
    def opened():
        with open_domain_host() as host:
            hosts.append(host)
            if fail:

                def failed(*_args):
                    raise error

                monkeypatch.setattr(host, "call", failed)
            yield host

    monkeypatch.setattr(caller, "open_domain_host", opened)
    if fail:
        with pytest.raises(DomainRuntimeError) as caught:
            caller.evaluate_lineup_prefix_continuation(_request())
        assert caught.value is error
    else:
        assert caller.evaluate_lineup_prefix_continuation(_request()).ok
    assert len(hosts) == 1
    assert hosts[0]._process is None
