"""共有CSVの出力構造・無害化・遅延消費を検証する。"""

from __future__ import annotations

import codecs
import csv
import io
from collections.abc import Iterator

import pytest

from pitchlog.exports.csv import CsvSerializationError, stream_csv


def _read(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline="")))


def test_exact_bytes_and_round_trip_preserve_supplied_values() -> None:
    """引用・欠損・日本語と供給済み数値を正確なバイト列へ写す。"""
    rows = [("山田,太郎", 0, None), ('引用"名前\n次行', -2, ".333(3打数)")]
    actual = b"".join(stream_csv(("選手", "計数", "表示"), rows))

    expected = (
        '\ufeff"選手","計数","表示"\r\n'
        '"山田,太郎","0",""\r\n'
        '"引用""名前\n次行","-2",".333(3打数)"\r\n'
    ).encode()
    assert actual == expected
    assert actual.count(codecs.BOM_UTF8) == 1
    assert _read(actual)[1:] == [
        ["山田,太郎", "0", ""],
        ['引用"名前\n次行', "-2", ".333(3打数)"],
    ]


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+cmd",
        "-2+3",
        "@SUM(A1)",
        "\t名前",
        "\r名前",
        "\n名前",
        " =1+1",
        "\u3000+cmd",
        "\ufeff@SUM(A1)",
        " \ufeff =1+1",
        "＝1+1",
        "＋cmd",
        "－2+3",
        "＠SUM(A1)",
        '=1+2";=1+2',
        "=1+2'\" ;,=1+2",
        "\t",
        "\r\n",
    ],
)
def test_untrusted_text_is_neutralized_before_csv_quoting(value: str) -> None:
    """ヘッダとセルの数式開始文字を引用前に無害化する。"""
    actual = b"".join(stream_csv((value,), [(value,)]))

    assert _read(actual) == [["'" + value], ["'" + value]]
    assert len(_read(actual)) == 2
    assert all(len(row) == 1 for row in _read(actual))


@pytest.mark.parametrize("value", ["山田", "001", "−(0打数)", ".333", "", "  名前"])
def test_ordinary_text_is_not_trimmed_or_reformatted(value: str) -> None:
    """安全な文字列・分母ゼロ表示・先頭ゼロは変更しない。"""
    assert _read(b"".join(stream_csv(("値",), [(value,)])))[1] == [value]


@pytest.mark.parametrize(
    "value", [True, False, 0.333, b"name", object(), "\x00", "\x01", "\x7f", "\ud800"]
)
def test_invalid_cells_fail_without_silent_conversion(value: object) -> None:
    """不正型や制御文字を空欄・数値へ黙って変換しない。"""
    stream = stream_csv(("値",), [(value,)])  # ty: ignore[invalid-argument-type]
    next(stream)
    with pytest.raises(CsvSerializationError):
        next(stream)


@pytest.mark.parametrize("row", [(), ("a", "b"), "a", b"a", None])
def test_invalid_rows_fail_when_consumed(row: object) -> None:
    """行幅の不一致とセル配列以外の行を消費時に拒否する。"""
    stream = stream_csv(("値",), [row])  # ty: ignore[invalid-argument-type]
    next(stream)
    with pytest.raises(CsvSerializationError):
        next(stream)


def test_row_length_hint_cannot_hide_an_extra_cell() -> None:
    """独自配列の不正な長さ情報でも余分なセルを見逃さない。"""

    class WrongLength(list[str]):
        def __len__(self) -> int:
            return 1

    stream = stream_csv(("値",), [WrongLength(["正常", "追加セル"])])
    next(stream)
    with pytest.raises(CsvSerializationError, match="列数"):
        next(stream)


@pytest.mark.parametrize("headers", [(), "name", (1,), ("\x00",), ("\ud800",)])
def test_invalid_headers_fail_before_returning_a_stream(headers: object) -> None:
    """ヘッダ不正はストリームを返す前に拒否する。"""
    with pytest.raises(CsvSerializationError):
        stream_csv(headers, [])  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("size", [0, -1, True, 1.5, "8"])
def test_invalid_chunk_size_is_rejected_immediately(size: object) -> None:
    """非整数・非正数の送出上限を呼出時に拒否する。"""
    with pytest.raises(CsvSerializationError):
        stream_csv(("値",), [], chunk_size=size)  # ty: ignore[invalid-argument-type]


def test_large_input_remains_lazy_and_chunks_stay_bounded() -> None:
    """一万行の先読みをせず、UTF-8途中の分割でも全体を復元できる。"""
    consumed = 0

    def rows() -> Iterator[tuple[str, int]]:
        nonlocal consumed
        for index in range(10000):
            consumed += 1
            yield ("日" * 100, index)

    stream = stream_csv(("名前", "番号"), rows(), chunk_size=7)
    first = next(stream)
    assert consumed == 0
    chunks = [first]
    for chunk in stream:
        assert 0 < len(chunk) <= 7
        chunks.append(chunk)
    decoded = _read(b"".join(chunks))
    assert consumed == 10000
    assert len(decoded) == 10001
    assert decoded[1] == ["日" * 100, "0"]
    assert decoded[-1] == ["日" * 100, "9999"]


def test_empty_input_still_exports_one_header_and_one_bom() -> None:
    """ゼロ件でもヘッダとBOMを一回だけ出力する。"""
    assert b"".join(stream_csv(("値",), [], chunk_size=1)) == '\ufeff"値"\r\n'.encode()


def test_source_failure_propagates_after_the_last_valid_row() -> None:
    """供給失敗を黙殺せず、部分ファイルを完了扱いしない。"""

    def rows() -> Iterator[tuple[str]]:
        yield ("正常",)
        raise RuntimeError("供給失敗")

    stream = stream_csv(("値",), rows())
    assert _read(next(stream)) == [["値"]]
    assert next(stream).decode() == '"正常"\r\n'
    with pytest.raises(RuntimeError, match="供給失敗"):
        next(stream)
