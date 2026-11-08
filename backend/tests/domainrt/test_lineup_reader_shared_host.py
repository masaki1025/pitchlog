"""有界readのhost起動共有と全行再計算・失効時停止を検査する。"""

import copy
import json
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest

from pitchlog.domainrt import host as runtime
from pitchlog.repositories import ordinary_prefix_read as reader
from pitchlog.repositories import past_correction_source as source
from pitchlog.repositories.transaction import _TenantTransaction

ROOT = Path(__file__).resolve().parents[3]


def _payload():
    """既検査済み現行metadata fixtureを原値のまま使う。"""
    import hashlib

    raw = copy.deepcopy(
        json.loads(
            (
                ROOT / "frontend/src/api/fixtures/currentLineupPrefixPayload.v1.json"
            ).read_text()
        )["cases"][0]["V7"]
    )
    actual = hashlib.sha256(
        (ROOT / "frontend/public/domain/pitchlog-domain.js").read_bytes()
    ).hexdigest()
    assert raw["calculation"]["artifactSha256"] == actual
    return raw


@pytest.mark.parametrize("fail_after", [None, 1])
def test_bounded_read_opens_once_recalculates_every_row_and_closes_on_failure(
    monkeypatch, fail_after
):
    """同じ保存行でも再callし、途中失効は同例外のままreadを止める。"""
    raw = _payload()
    opened = []
    calls = []
    error = RuntimeError("試験用の資格失効")
    original_open = runtime.open_domain_host

    @contextmanager
    def counted_open():
        with original_open() as host:
            opened.append(host)
            original_call = host.call

            def call(operation, body):
                calls.append(operation)
                return original_call(operation, body)

            monkeypatch.setattr(host, "call", call)
            yield host

    def read_rows(*_args, host, row_progress):
        result = []
        for index in range(3):
            if row_progress is not None:
                row_progress()
            if index == fail_after:
                raise error
            result.append(reader._evaluate_lineup_payload(raw, _host=host))
            if row_progress is not None:
                row_progress()
        return result

    monkeypatch.setattr(runtime, "open_domain_host", counted_open)
    monkeypatch.setattr(reader, "_read_lineup_projection_with_host", read_rows)
    args = (None,) * 13
    if fail_after is None:
        values = reader._read_lineup_projection(*args)
        assert len(values) == 3
        assert all(value == values[0] for value in values)
        assert len(calls) == 3
    else:
        with pytest.raises(RuntimeError) as caught:
            reader._read_lineup_projection(*args)
        assert caught.value is error
        assert len(calls) == 1
    assert len(opened) == 1
    assert opened[0]._process is None


def test_shared_payload_still_rejects_modified_response(monkeypatch):
    """同実hostを使っても保存応答の数学を期待値として流用しない。"""
    raw = _payload()
    flags = raw["calculation"]["response"]["value"]["t1"]["statFlags"]
    key = next(iter(flags))
    flags[key] = 1 - flags[key]
    with runtime.open_domain_host() as host:
        with pytest.raises((reader.OrdinaryPrefixError, ValueError)):
            reader._evaluate_lineup_payload(raw, _host=host)


def test_private_shared_reader_rejects_fake_host_before_inner_read(monkeypatch):
    """自由host objectをread原本検証の迂回へ使えない。"""
    called = []
    monkeypatch.setattr(
        reader,
        "_read_lineup_projection_with_host",
        lambda *_a, **_k: called.append(True),
    )
    with pytest.raises(reader.OrdinaryPrefixError):
        reader._read_lineup_projection(*((None,) * 13), _host=object())
    assert called == []


def test_paged_source_progress_failure_propagates_before_public_reader(monkeypatch):
    """同scopeへ束縛した真正確認の失効を、原本既定値で補わない。"""
    from uuid import UUID

    class Scope:
        def run(self, _token):
            return {"generation": 1, "confirmed_watermark": 26}

    error = RuntimeError("試験用の資格失効")
    called = []

    def progress():
        raise error

    monkeypatch.setattr(source, "_TenantTransaction", Scope)
    monkeypatch.setattr(source, "_one", lambda value, _columns: value)
    monkeypatch.setattr(
        source, "read_lineup_prefix", lambda *_a, **_k: called.append(True)
    )
    with pytest.raises(RuntimeError) as caught:
        source.visit_past_correction_v3_source_pages(
            cast(_TenantTransaction, Scope()),
            UUID(int=1),
            26,
            lambda *_a: None,
            _progress=progress,
        )
    assert caught.value is error
    assert called == []


def test_borrowed_actual_host_is_not_reopened_or_closed_by_reader(monkeypatch):
    """P3所有の実hostはreaderが起動し直さず、貸借後も元所有者が保持する。"""
    with runtime.open_domain_host() as host:
        observed = []

        def inner(*_args, host, row_progress):
            observed.append(host)
            return reader._evaluate_lineup_payload(_payload(), _host=host)

        def forbidden():
            raise AssertionError("借用中の二重起動")

        monkeypatch.setattr(reader, "_read_lineup_projection_with_host", inner)
        monkeypatch.setattr(runtime, "open_domain_host", forbidden)
        result = reader._read_lineup_projection(*((None,) * 13), _host=host)
        assert result.calculation.response.ok
        assert observed == [host]
        assert host._process is not None and host._process.poll() is None
    assert host._process is None
