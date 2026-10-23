"""毎球・成績CSVで共有する無害化と遅延直列化。"""

from __future__ import annotations

import codecs
import csv
import io
import unicodedata
from collections.abc import Iterable, Iterator, Sequence

type CsvCell = str | int | None


class CsvSerializationError(ValueError):
    """CSVの構造・セルを安全に直列化できない場合。"""


def _text_cell(value: str) -> str:
    """元の文字列を保持し、数式に見えるテキストだけを無害化する。"""
    if any(
        (ord(char) < 32 and char not in "\t\r\n") or char == "\x7f" for char in value
    ):
        raise CsvSerializationError("CSVセルに未対応の制御文字がある")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise CsvSerializationError("CSVセルをUTF-8へ変換できない") from error

    offset = 0
    leading_control = False
    for char in value:
        if not (char.isspace() or char == "\ufeff"):
            break
        leading_control |= char in "\t\r\n"
        offset += 1
    probe = unicodedata.normalize("NFKC", value[offset : offset + 1])
    if leading_control or probe in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _cell(value: CsvCell) -> str:
    """欠損・整数・テキストを区別して、計算せずに出力値へ写す。"""
    if value is None:
        return ""
    if type(value) is str:
        return _text_cell(value)
    if type(value) is int:
        try:
            return str(value)
        except ValueError as error:
            raise CsvSerializationError("CSV整数を文字列化できない") from error
    raise CsvSerializationError("CSVセルは文字列・整数・Noneに限る")


def _encode_row(values: Sequence[CsvCell], width: int) -> bytes:
    """一行だけを検証・引用し、後続行を消費せずに符号化する。"""
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CsvSerializationError("CSV行はセルの配列でなければならない")
    cells = tuple(values)
    if len(cells) != width:
        raise CsvSerializationError("CSV行の列数がヘッダと一致しない")
    with io.StringIO(newline="") as buffer:
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerow(_cell(value) for value in cells)
        return buffer.getvalue().encode("utf-8")


def stream_csv(
    headers: Sequence[str],
    rows: Iterable[Sequence[CsvCell]],
    *,
    chunk_size: int = 65536,
) -> Iterator[bytes]:
    """BOM付きCSVを行単位で読み、上限付きバイト列として返す。

    ヘッダの検証は呼出時、各行の検証は消費時に行う。後続の不正行は例外として
    伝播するため、呼出側は途中の出力を成功済みファイルとして扱わないこと。
    chunk境界はUTF-8文字の途中に置かれ得る。連結後のバイト列がCSVである。

    Args:
        headers: 空でないヘッダ配列。ラベルにもテキスト無害化を適用する。
        rows: 供給済みのセル配列。計算・全行収集・並べ替えは行わない。
        chunk_size: 一回の送出バイト数の上限。正の整数。

    Returns:
        UTF-8 BOMを先頭一回だけ含むCSVバイト列の反復子。

    Raises:
        CsvSerializationError: ヘッダ・設定が不正、または消費した行が不正な場合。
    """
    if type(chunk_size) is not int or chunk_size < 1:
        raise CsvSerializationError("CSV chunk_sizeは正の整数でなければならない")
    if isinstance(headers, (str, bytes, bytearray)) or not isinstance(
        headers, Sequence
    ):
        raise CsvSerializationError("CSVヘッダは文字列の配列でなければならない")
    columns = tuple(headers)
    if not columns or any(type(column) is not str for column in columns):
        raise CsvSerializationError("CSVヘッダは空でない文字列配列に限る")
    first = codecs.BOM_UTF8 + _encode_row(columns, len(columns))

    def generate() -> Iterator[bytes]:
        for offset in range(0, len(first), chunk_size):
            yield first[offset : offset + chunk_size]
        for row in rows:
            encoded = _encode_row(row, len(columns))
            for offset in range(0, len(encoded), chunk_size):
                yield encoded[offset : offset + chunk_size]

    return generate()
