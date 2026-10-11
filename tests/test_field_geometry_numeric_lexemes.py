"""フィールド領域と表示座標の契約 JSON の数値リテラルを検査する。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIRECTORIES = (
    "contracts/field-regions",
    "contracts/display-geometry",
)
NUMBER_TOKEN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*)?(?:[eE][+-]?[0-9]*)?")
NONFINITE_TOKENS = ("-Infinity", "Infinity", "NaN")


def _check_numeric_lexemes(path: Path) -> None:
    """JSON を parse せず、文字列の外にある数値リテラルを検査する。

    Args:
        path: 検査対象の JSON ファイル。

    Raises:
        AssertionError: 小数・指数・負のゼロ・非有限値が見つかった場合。
    """
    source = path.read_text(encoding="utf-8")
    in_string = False
    escaped = False
    index = 0

    while index < len(source):
        character = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            index += 1
            continue

        for token in NONFINITE_TOKENS:
            if source.startswith(token, index):
                raise AssertionError(f"{path}: 禁止された数値リテラル {token}")

        if character == "-" or "0" <= character <= "9":
            match = NUMBER_TOKEN.match(source, index)
            if match is not None:
                token = match.group()
                if token == "-0" or "." in token or "e" in token.lower():
                    raise AssertionError(f"{path}: 禁止された数値リテラル {token}")
                index = match.end()
                continue

        index += 1


def _check_contract_directories(root: Path) -> None:
    """両契約ディレクトリの既存 JSON をすべて検査する。

    Args:
        root: 契約ディレクトリを含むルート。
    """
    for directory in CONTRACT_DIRECTORIES:
        for path in sorted((root / directory).rglob("*.json")):
            _check_numeric_lexemes(path)


def test_repository_contract_numeric_lexemes() -> None:
    """既存の契約 JSON に非正規の数値リテラルが無いことを検査する。"""
    _check_contract_directories(REPOSITORY_ROOT)


def test_empty_contract_directories_pass(tmp_path: Path) -> None:
    """契約ディレクトリが空でも検査が成功する。"""
    for directory in CONTRACT_DIRECTORIES:
        (tmp_path / directory).mkdir(parents=True)
    _check_contract_directories(tmp_path)


def test_integer_literals_and_quoted_text_pass(tmp_path: Path) -> None:
    """整数は許容し、文字列内の数値らしい文字列は無視する。"""
    path = tmp_path / "valid.json"
    path.write_text(
        '{"text":"quoted \\"1.0\\" -0 NaN Infinity -Infinity",'
        '"values":[-10,0,10,1000]}',
        encoding="utf-8",
    )
    _check_numeric_lexemes(path)


@pytest.mark.parametrize(
    "token",
    ("1.0", "1e3", "1E+3", "-0", "-0.0", "-0e0", "NaN", "Infinity", "-Infinity"),
)
def test_noncanonical_numeric_literal_is_rejected(tmp_path: Path, token: str) -> None:
    """合成 JSON の禁止トークンを字句検査が拒否する。"""
    path = tmp_path / "invalid.json"
    path.write_text('{"value": ' + token + ', "scale": 10}', encoding="utf-8")

    with pytest.raises(AssertionError, match=re.escape(token)):
        _check_numeric_lexemes(path)
