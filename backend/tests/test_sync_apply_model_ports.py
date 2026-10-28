"""同期要求型とポートの fail-closed 境界を DB なしで検査する。"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast, get_args

import pytest
from sqlalchemy import select, text
from test_sync_apply_port_engine import EngineProjection
from test_sync_apply_port_safe import SafeProjection
from test_sync_apply_port_token_only import TokenOnlyOperation, TokenOnlyProjection
from test_sync_apply_port_transitive import TransitiveProjection

from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync import port_guard, ports
from pitchlog.sync.model import (
    ABSENT,
    A5Result,
    A5State,
    AcceptedChangeResult,
    AckResult,
    BoundaryResult,
    RejectedChangeResult,
    RequestShapeError,
    SyncEvent,
    SyncRequest,
)

GAME = "123e4567-e89b-12d3-a456-426614174000"
OTHER_GAME = "123e4567-e89b-12d3-a456-426614174001"
D5 = "123e4567-e89b-12d3-a456-426614174002"


def _event(**overrides: object) -> SyncEvent:
    """S-1 を満たす D1 付きイベントを作る。"""
    values: dict[str, object] = {"d5": D5, "game_id": GAME, "d1": 1, "d4": "epoch"}
    values.update(overrides)
    return SyncEvent(**values)  # type: ignore[arg-type]


def _request(**overrides: object) -> SyncRequest:
    """S-1 を満たす D1 付き要求を作る。"""
    values: dict[str, object] = {
        "path": "P1",
        "game_id": GAME,
        "events": (_event(),),
        "d4": "epoch",
    }
    values.update(overrides)
    return cast(Any, SyncRequest)(**values)


class _Token(TenantOperationToken):
    """書き手の単体試験用 token。"""

    @property
    def capability_id(self) -> str:
        """合成 capability を返す。"""
        return "test"


def test_stage_values_preserve_missing_null_and_malformed_json() -> None:
    """V5〜V11・V12 は型で拒否せず、欠落と null を区別する。"""
    payload: dict[str, object] = {"nested": [False, {"raw": None}]}
    event = _event(v5=False, v7=payload)
    request = _request(events=(event,), v12={"not": "a proof"})
    assert event.v6 is ABSENT
    assert event.v5 is False
    assert event.v7 == {"nested": (False, {"raw": None})}
    assert event.v11 is ABSENT
    p3_event = SyncEvent(D5, GAME, v11=["unexpected"])
    p3_request = SyncRequest("P3", GAME, (p3_event,), recovery_generation="opaque")
    assert p3_request.events[0].v11 == ("unexpected",)
    assert request.recovery_generation is ABSENT
    assert isinstance(request.v12, MappingProxyType)
    cast(list[object], payload["nested"]).append("changed")
    assert event.v7 == {"nested": (False, {"raw": None})}
    with pytest.raises(TypeError):
        cast(dict[str, object], event.v7)["nested"] = ()
    with pytest.raises(FrozenInstanceError):
        setattr(event, "d5", "new")
    assert _event(v7=None).v7 is None
    assert _event().v7 is ABSENT
    assert _request(v12=None).v12 is None
    assert _request().v12 is ABSENT


def test_ack_and_change_results_use_canonical_vocabulary() -> None:
    """A5・境界結果と P3 の語彙を正本の集合に合わせる。"""
    assert set(get_args(A5State.__value__)) == {
        "受理",
        "重複",
        "拒否",
        "退避",
        "未処理",
    }
    assert set(get_args(BoundaryResult.__value__)) == {
        *(f"B{number}" for number in range(1, 15))
    }
    mapping = {"temporary": "official"}
    ack = AckResult(
        "B1", 2, (A5Result("d4", 2, D5, "受理"),), temporary_id_mapping=mapping
    )
    mapping["temporary"] = "changed"
    assert ack.temporary_id_mapping["temporary"] == "official"
    assert ack.a5[0].state == "受理"
    content = {"a": [1]}
    accepted = AcceptedChangeResult(
        {"試合": GAME, "対象の D4": "epoch", "対象の D1": 1},
        2,
        D5,
        content,
        "2026-10-14T12:00:00+09:00",
    )
    content["a"].append(2)
    assert accepted.boundary == "変更受理"
    assert accepted.target_reference["試合"] == GAME
    assert accepted.expected_version == 2
    assert accepted.confirmed_content == {"a": (1,)}
    assert accepted.accepted_at.endswith("+09:00")
    assert RejectedChangeResult("B9", D5).boundary == "B9"
    with pytest.raises(ValueError):
        RejectedChangeResult(cast(Any, "変更受理"), D5)
    with pytest.raises(TypeError):
        cast(Any, AcceptedChangeResult)({"試合": GAME}, 2, D5, content)
    with pytest.raises(ValueError):
        AcceptedChangeResult({"試合": GAME}, ABSENT, D5, content, "now")


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": "unknown"},
        {"game_id": "bad"},
        {"d4": None},
        {"d4": 1},
        {"events": "bad"},
        {"events": ()},
        {"events": (_event(game_id=OTHER_GAME),)},
        {"events": (_event(d1=None),)},
        {"events": (_event(d1=True),)},
        {"events": (_event(d1=2**53),)},
        {"events": (_event(d4="other"),)},
        {"events": (_event(), _event(d5=OTHER_GAME))},
        {"recovery_generation": "opaque"},
        {"events": (_event(v11=None),)},
        {"path": "P3", "events": (SyncEvent(D5, GAME),)},
        {"path": "P3", "events": (SyncEvent(D5, GAME),), "recovery_generation": 3},
        {
            "path": "P3",
            "events": (SyncEvent(D5, GAME),),
            "recovery_generation": "opaque",
        },
        {
            "path": "P3",
            "events": (SyncEvent(D5, GAME, v6=None),),
            "recovery_generation": "opaque",
            "d4": None,
        },
        {"path": "P3", "events": (), "recovery_generation": "opaque"},
        {
            "path": "P3",
            "events": (SyncEvent(D5, GAME), SyncEvent(OTHER_GAME, GAME)),
            "recovery_generation": "opaque",
        },
    ],
)
def test_s1_rejects_invalid_constructor_shapes(overrides: dict[str, object]) -> None:
    """経路・識別・世代・イベント列の S-1 違反を生成境界で拒否する。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        _request(**overrides)


@pytest.mark.parametrize("bad_d5", ["BAD", "123E4567-e89b-12d3-a456-426614174002"])
def test_s1_rejects_noncanonical_event_id(bad_d5: str) -> None:
    """D5 の非正規 UUID は型を作れない。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        SyncEvent(bad_d5, GAME)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"events": [], "extra": 1},
        {"events": "bad"},
        {
            "events": [
                {"d5": D5, "game_id": GAME, "d1": 1, "d4": "epoch", "unknown": 1}
            ],
        },
        {"events": []},
        {
            "events": [
                {
                    "d5": D5,
                    "game_id": GAME,
                    "d1": 1,
                    "d4": "epoch",
                    "expected_version": 1,
                }
            ]
        },
    ],
)
def test_s1_rejects_invalid_payload_object(payload: object) -> None:
    """本文・イベントの未知キーと配列の外形を拒否する。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        SyncRequest.from_payload("P1", GAME, payload)


def test_s1_payload_keeps_s2_values() -> None:
    """S-1 を満たす本文では V12 と V5〜V11 の異形値を保持する。"""
    request = SyncRequest.from_payload(
        "P3",
        GAME,
        {
            "change": {
                "d5": D5,
                "game_id": GAME,
                "expected_version": {"unexpected": True},
            },
            "recovery_generation": "opaque",
            "recording_right_proof": [False],
        },
    )
    assert request.events[0].v11 == {"unexpected": True}
    assert request.v12 == (False,)

    d1_request = SyncRequest.from_payload(
        "P1",
        GAME,
        {
            "events": [
                {
                    "d5": D5,
                    "game_id": GAME,
                    "d1": 1,
                    "d4": "opaque",
                    "event_kind": {"invalid": True},
                    "payload": None,
                }
            ],
            "recording_right_proof": 12,
        },
    )
    assert d1_request.events[0].v5 == {"invalid": True}
    assert d1_request.events[0].v7 is None
    assert d1_request.v12 == 12


def test_duplicate_d5_is_left_for_processing() -> None:
    """D5 の重複は S-1 で拒否せず、処理段階へ渡す。"""
    request = _request(events=(_event(), _event(d1=2)))
    assert request.events[0].d5 == request.events[1].d5


@pytest.mark.parametrize(
    "payload",
    [
        {"change": {"d5": D5, "game_id": GAME}},
        {"recovery_generation": "opaque", "change": []},
        {
            "recovery_generation": "opaque",
            "change": {"d5": D5, "game_id": GAME, "d1": 1},
        },
        {"recovery_generation": "opaque", "change": {"d5": D5, "game_id": OTHER_GAME}},
    ],
)
def test_s1_p3_payload_shape(payload: object) -> None:
    """P3 の復旧世代・変更イベント 1 件・試合の一致を検査する。"""
    with pytest.raises(RequestShapeError, match="S-1"):
        SyncRequest.from_payload("P3", GAME, payload)


def test_port_writer_is_issued_and_invalidated_by_apply_kernel() -> None:
    """任意 callable での公開発行を拒否し、閉鎖後の run も拒否する。"""
    received: list[TenantOperationToken] = []

    def execute(token: TenantOperationToken) -> TenantOperationResult:
        received.append(token)
        return TenantOperationResult(())

    with pytest.raises(PermissionError):
        ports.PortWriter(execute, object())
    writer = ports._issue_port_writer(execute)
    with pytest.raises(TypeError, match="operation token"):
        writer.run(cast(TenantOperationToken, select(text("1"))))
    writer.run(_Token())
    assert len(received) == 1
    writer._close()
    with pytest.raises(RuntimeError, match="閉じている"):
        writer.run(_Token())
    assert len(received) == 1


def _register(monkeypatch: pytest.MonkeyPatch, port_type: type[object]) -> None:
    """テスト中だけ module の属性にあるクラスを登録する。"""
    monkeypatch.setattr(
        ports,
        "PORT_IMPLEMENTATIONS",
        frozenset({(port_type.__module__, port_type.__name__)}),
    )


def test_unregistered_port_is_rejected_before_call() -> None:
    """未登録のポートは実装呼び出し前に失敗する。"""
    assert ports.PORT_IMPLEMENTATIONS == frozenset(
        {
            ("pitchlog.sync.first_ball_ports", "FirstBallContentValidationPort"),
        }
    )
    from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort

    ports.require_registered_port(FirstBallContentValidationPort())
    port = SafeProjection()
    with pytest.raises(ports.PortRegistrationError, match="未登録"):
        ports.require_registered_port(port)
        port.apply(
            _event(), ports._issue_port_writer(lambda _: TenantOperationResult(()))
        )
    assert port.calls == 0


def test_port_entry_fails_closed_without_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登録検査器の導入前にポート呼び出しを許さない。"""
    monkeypatch.setattr(ports, "_PORT_VERIFIER", None)
    with pytest.raises(ports.PortRegistrationError, match="未接続"):
        ports.require_registered_port(SafeProjection())


def test_registered_safe_port_passes_static_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """テスト中だけ登録した安全な合成実装を許可する。"""
    _register(monkeypatch, SafeProjection)
    port = SafeProjection()
    ports.require_registered_port(port)
    port.apply(_event(), ports._issue_port_writer(lambda _: TenantOperationResult(())))
    assert port.calls == 1


@pytest.mark.parametrize("kind", ["spoofed_module", "dynamic", "subclass"])
def test_class_identity_rejects_spoofed_and_derived_ports(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """__module__ 詐称・動的同名クラス・サブクラスは登録クラスではない。"""
    _register(monkeypatch, SafeProjection)
    if kind == "subclass":

        class Impostor(SafeProjection):
            """継承だけで登録したように見せる。"""

        candidate: object = Impostor()
    elif kind == "dynamic":
        candidate = type(
            "SafeProjection", (), {"__module__": SafeProjection.__module__}
        )()
    else:

        class Impostor:
            """登録モジュール名だけを詐称する。"""

        Impostor.__module__ = SafeProjection.__module__
        candidate = Impostor()
    with pytest.raises(ports.PortRegistrationError, match="未登録"):
        ports.require_registered_port(candidate)


@pytest.mark.parametrize("port_type", (EngineProjection, TransitiveProjection))
def test_forbidden_port_imports_are_rejected(
    monkeypatch: pytest.MonkeyPatch, port_type: type[object]
) -> None:
    """直接 DB 接続と pitchlog 内の推移的な禁止 import を拒否する。"""
    _register(monkeypatch, port_type)
    with pytest.raises(ports.PortRegistrationError, match="禁止"):
        ports.require_registered_port(port_type())


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\ngetattr(importlib, 'import_module')('pitchlog.db.engine')",
        "import builtins\nbuiltins.__import__('pitchlog.db.engine')",
        "import pkgutil\npkgutil.resolve_name('pitchlog.db.engine')",
        "import sys\nsys.modules['pitchlog.db.engine']",
        "import sqlalchemy",
        "import os",
        "import subprocess",
        "import socket",
        "import ctypes",
        "import threading",
        "import asyncio",
        "import multiprocessing",
        "import concurrent.futures",
        "import psycopg",
        "import typing\ntyping.sys.modules['pitchlog.db.engine']",
        "from typing import sys as hidden_sys\n"
        "hidden_sys.modules['pitchlog.db.engine']",
        "from pitchlog.db import engine",
        "from pitchlog.repositories import transaction",
        "from pitchlog.sync import port_guard",
        "from pitchlog.sync import ports\nports._issue_port_writer(lambda x: x)",
        "from pitchlog.sync.ports import _WRITER_CREATION_TOKEN",
        "from pitchlog.sync import ports\nports.PORT_IMPLEMENTATIONS",
        "from pitchlog.sync import ports\nports._PORT_VERIFIER",
        "writer._active = True",
        "writer._execute(token)",
        "writer._close()",
        "exec('pass')",
        "eval('1')",
        "compile('pass', 'x', 'exec')",
        "__import__('pitchlog.db.engine')",
        "globals()",
        "locals()",
        "vars()",
        "__builtins__",
        "__loader__",
        "__spec__",
    ],
)
def test_static_allowlist_rejects_each_dynamic_or_external_route(source: str) -> None:
    """動的 import・外部 package・権限付き module への各経路を拒否する。"""
    with pytest.raises(ports.PortRegistrationError, match="禁止|ソースのない|書き手"):
        port_guard.validate_port_source(source)


@pytest.mark.parametrize(
    "source",
    [
        (
            "from typing import get_type_hints\n"
            "class Event:\n"
            "    target: \"__import__('pitchlog.db.engine')\"\n"
            "get_type_hints(Event)"
        ),
        "import typing\ntyping.get_type_hints(Event)",
        'import typing\ngetattr(typing, "get_type_hints")(Event)',
        "from collections import namedtuple",
        "from dataclasses import make_dataclass",
        "import dataclasses\ndataclasses.make_dataclass('Unsafe', [])",
        'import dataclasses\ngetattr(dataclasses, "make_dataclass")',
        "from functools import singledispatch",
        "from typing import ForwardRef",
        "from typing import _eval_type",
        "from typing import evaluate_forward_ref",
        "import typing as t\nt.get_type_hints(Event)",
        "import typing\ntyping.ForwardRef('unsafe')",
        'import typing\ngetattr(typing, "Proto" + "col")',
        "import typing\nmodule_alias = typing",
    ],
)
def test_standard_name_allowlist_rejects_string_evaluation_routes(source: str) -> None:
    """文字列注釈の評価とモジュールオブジェクトの迂回取得を拒否する。"""
    with pytest.raises(ports.PortRegistrationError, match="禁止|受け渡し"):
        port_guard.validate_port_source(source)


@pytest.mark.parametrize(
    "source",
    [
        "from typing import Protocol, Literal, final, cast, TYPE_CHECKING, Any",
        "import typing as t\n_safe = t.Protocol",
        'import typing\n_safe = getattr(typing, "Protocol")',
        "from collections import abc as cabc\n_safe = cabc.Mapping",
        "import collections.abc\n_safe = collections.abc.Mapping",
    ],
)
def test_standard_name_allowlist_accepts_only_declared_names(source: str) -> None:
    """許可した import 形式と定数名の getattr は通す。"""
    port_guard.validate_port_source(source)


@pytest.mark.parametrize(
    "source",
    [
        "import pitchlog\npitchlog.db.engine.create_database_engine()",
        "from pitchlog import db",
        "from pitchlog.db import engine",
        "import pitchlog.sync.model as m",
        "from pitchlog.sync import model as m",
        "from pitchlog.sync import ports",
        "from pitchlog.sync.model import *",
        "from . import model",
    ],
)
def test_pitchlog_module_objects_are_rejected(source: str) -> None:
    """Pitchlog のモジュールオブジェクトを import する全形式を拒否する。"""
    with pytest.raises(ports.PortRegistrationError, match="禁止"):
        port_guard.validate_port_source(source, module_name="pitchlog.sync.synthetic")


@pytest.mark.parametrize(
    "source",
    [
        "from pitchlog.sync.model import SyncEvent",
        "from pitchlog.sync.ports import PortWriter",
        "from pitchlog.repositories.tokens import TenantOperationToken",
        "from pitchlog.sync.model import ABSENT",
        "from .model import SyncEvent",
    ],
)
def test_pitchlog_nonmodule_names_are_allowed(source: str) -> None:
    """Pitchlog の型・値だけを取得する from import は許可する。"""
    port_guard.validate_port_source(source, module_name="pitchlog.sync.synthetic")


def test_pitchlog_reexported_module_objects_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """子ファイルがなくても module object の再輸出は許可しない。"""
    original = port_guard._pitchlog_module_file
    fixture = Path(__file__).with_name("test_sync_apply_port_reexport.py")

    def module_file(name: str) -> Path | None:
        """合成 Pitchlog モジュールだけを試験ファイルへ対応させる。"""
        if name == "pitchlog.synthetic":
            return fixture
        return original(name)

    monkeypatch.setattr(port_guard, "_pitchlog_module_file", module_file)
    for exported in (
        "exported_typing",
        "exported_collections_abc",
        "exported_nested",
    ):
        with pytest.raises(ports.PortRegistrationError, match="禁止"):
            port_guard.validate_port_source(
                f"from pitchlog.synthetic import {exported}"
            )
    port_guard.validate_port_source("from pitchlog.synthetic import ExportedProtocol")


def test_token_only_module_is_allowed_but_sql_token_module_is_not() -> None:
    """Token 単独のモジュールを許し、SQL を import する token を拒否する。"""
    port_guard.validate_port_modules(("pitchlog.repositories.tokens",))
    with pytest.raises(ports.PortRegistrationError, match="禁止"):
        port_guard.validate_port_modules(("pitchlog.repositories.roster",))


def test_token_only_synthetic_port_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token の型だけを import する実装は登録検査を通る。"""
    _register(monkeypatch, TokenOnlyProjection)
    seen: list[TenantOperationToken] = []

    def execute(token: TenantOperationToken) -> TenantOperationResult:
        seen.append(token)
        return TenantOperationResult(())

    port = TokenOnlyProjection()
    ports.require_registered_port(port)
    port.apply(_event(), ports._issue_port_writer(execute))
    assert len(seen) == 1
    assert type(seen[0]) is TokenOnlyOperation


def test_port_signatures_do_not_expose_context_handle_or_session() -> None:
    """全ポートの公開メソッドに独立スコープの材料がない。"""
    for protocol in (
        ports.RecordingRightsPort,
        ports.ProjectionPort,
        ports.ContentValidationPort,
        ports.InvalidationSinkPort,
    ):
        for name, method in vars(protocol).items():
            if name.startswith("_") or not inspect.isfunction(method):
                continue
            signature = inspect.signature(method)
            assert not {"context", "tenant_context", "handle", "session"} & set(
                signature.parameters
            )
            assert not any(
                forbidden in str(annotation)
                for annotation in method.__annotations__.values()
                for forbidden in ("TenantContext", "_TenantTransaction", "Session")
            )
