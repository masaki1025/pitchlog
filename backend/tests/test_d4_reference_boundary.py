"""d4参照の符号化が単一実装で、brokerの出力とbyte一致することを検査する。

権利・失効・世代の実在は検査しない。符号化の型と範囲、固定ベクタ、brokerが
複製実装を持たないことだけを閉じる。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from pitchlog.recording_rights import initial_grant_broker as broker
from pitchlog.sync import d4_reference
from pitchlog.sync.d4_reference import D4ReferenceInvalid, encode_d4_reference

_TENANT = UUID("11111111-1111-4111-8111-111111111111")
_GAME = UUID("22222222-2222-4222-8222-222222222222")
_NIL = UUID(int=0)
_MAX = UUID(int=2**128 - 1)
_BROKER_SOURCE = Path(broker.__file__)

# 41byteの原本を標準base64からurlsafeへ写して手で固定した値。実装から導いていない。
_VECTORS = (
    (_TENANT, _GAME, 1, "d4.1.AREREREREUERgREREREREREiIiIiIiJCIoIiIiIiIiIiAAAAAAAAAAE"),
    (
        _TENANT,
        _GAME,
        17,
        "d4.1.AREREREREUERgREREREREREiIiIiIiJCIoIiIiIiIiIiAAAAAAAAABE",
    ),
    (
        _TENANT,
        _GAME,
        2**63 - 1,
        "d4.1.AREREREREUERgREREREREREiIiIiIiJCIoIiIiIiIiIif_________8",
    ),
    (_NIL, _MAX, 1, "d4.1.AQAAAAAAAAAAAAAAAAAAAAD_____________________AAAAAAAAAAE"),
    (_NIL, _MAX, 17, "d4.1.AQAAAAAAAAAAAAAAAAAAAAD_____________________AAAAAAAAABE"),
    (
        _NIL,
        _MAX,
        2**63 - 1,
        "d4.1.AQAAAAAAAAAAAAAAAAAAAAD_____________________f_________8",
    ),
)


@pytest.mark.parametrize(("tenant", "game", "value", "expected"), _VECTORS)
def test_encode_matches_fixed_vectors_and_broker_bytes(
    tenant: UUID, game: UUID, value: int, expected: str
) -> None:
    """固定ベクタ・公開関数・brokerの私有関数が同じ60文字を返す。"""
    assert encode_d4_reference(tenant, game, value) == expected
    assert broker._broker_d4(tenant, game, value) == expected
    assert len(expected) == 60 and "=" not in expected


@pytest.mark.parametrize(("tenant", "game", "value", "expected"), _VECTORS)
def test_broker_parse_roundtrips_the_shared_encoding(
    tenant: UUID, game: UUID, value: int, expected: str
) -> None:
    """broker側の解読は、共有符号化の出力だけを同じ世代へ戻す。"""
    assert broker._broker_generation(expected, tenant, game) == value


class _UuidChild(UUID):
    """UUIDの派生型。型の厳密一致で拒否される。"""


class _IntChild(int):
    """intの派生型。型の厳密一致で拒否される。"""


@pytest.mark.parametrize(
    "arguments",
    [
        ("tenant-as-string", _GAME, 1),
        (_TENANT, str(_GAME), 1),
        (None, _GAME, 1),
        (_TENANT, None, 1),
        (_UuidChild(int=_TENANT.int), _GAME, 1),
        (_TENANT, _UuidChild(int=_GAME.int), 1),
        (_TENANT, _GAME, True),
        (_TENANT, _GAME, False),
        (_TENANT, _GAME, 1.0),
        (_TENANT, _GAME, "1"),
        (_TENANT, _GAME, None),
        (_TENANT, _GAME, _IntChild(1)),
        (_TENANT, _GAME, 0),
        (_TENANT, _GAME, -1),
        (_TENANT, _GAME, 2**63),
        (_TENANT, _GAME, 2**64),
    ],
)
def test_wrong_type_or_range_is_rejected_by_both_entrances(
    arguments: tuple[Any, Any, Any],
) -> None:
    """型違いと範囲外は、公開関数で例外、brokerで固定外形の通信不確定になる。"""
    with pytest.raises(D4ReferenceInvalid) as direct:
        encode_d4_reference(*arguments)
    assert direct.value.args == ("d4参照の入力が不正",)
    with pytest.raises(broker.InitialBrokerUnavailable) as via_broker:
        broker._broker_d4(*arguments)
    assert via_broker.value.__cause__ is None
    assert via_broker.value.__suppress_context__ is True


def test_invalid_error_is_a_value_error_without_input_values() -> None:
    """拒否の外形は固定で、入力値を含まない。"""
    assert issubclass(D4ReferenceInvalid, ValueError)
    with pytest.raises(D4ReferenceInvalid) as error:
        encode_d4_reference(_TENANT, _GAME, 2**63)
    assert str(2**63) not in str(error.value)
    assert str(_TENANT) not in str(error.value)


def test_encoding_is_defined_only_in_the_shared_module() -> None:
    """brokerは符号化の部品を持たず、公開関数へ委譲するだけである。"""
    tree = ast.parse(_BROKER_SOURCE.read_text(encoding="utf-8"))
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_broker_d4"
    ]
    assert len(functions) == 1
    names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Attribute | ast.Name)
    }
    assert "encode_d4_reference" in names
    assert not names & {"urlsafe_b64encode", "to_bytes", "base64"}
    strings = {
        node.value
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not any("d4.1." in value for value in strings)
    assert d4_reference.encode_d4_reference is encode_d4_reference


def test_shared_module_has_no_runtime_dependency_on_the_broker() -> None:
    """共有module側からbrokerをimportしない(循環と複製の双方を避ける)。"""
    tree = ast.parse(Path(d4_reference.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    assert imported == {"__future__", "base64", "uuid"}
