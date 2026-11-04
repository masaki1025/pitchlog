"""全CSVとmanifestの完成後だけ渡す、一時ディスク上のZIP生成。"""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO
from uuid import UUID

from pitchlog.exports.csv import stream_csv
from pitchlog.exports.play_rows import (
    CSV_HEADERS,
    PlayExportSupplyError,
    SavedCsvRow,
    _bounded_mapping,
    saved_values,
    validate_snapshot_id,
)


class PlayExportArchiveError(ValueError):
    """出力容量または完成ZIPの整合に問題がある場合。"""


@dataclass(frozen=True, slots=True)
class ExportLimits:
    """一試合出力の資源上限。行を全件RAMへ集めない。"""

    max_rows_per_file: int = 1_000_000
    max_cell_chars: int = 65_536
    max_row_chars: int = 1_048_576
    max_file_bytes: int = 134_217_728
    max_total_bytes: int = 268_435_456
    max_archive_bytes: int = 268_435_456
    chunk_size: int = 65_536

    def __post_init__(self) -> None:
        """boolや無制限指定を拒否する。"""
        for value in (
            self.max_rows_per_file,
            self.max_cell_chars,
            self.max_row_chars,
            self.max_file_bytes,
            self.max_total_bytes,
            self.max_archive_bytes,
            self.chunk_size,
        ):
            if type(value) is not int or value < 1:
                raise PlayExportArchiveError("出力上限は正の整数が必要です")


@dataclass(frozen=True, slots=True)
class ExportSnapshot:
    """業務資格を含まない、caller供給の同一読取版の識別。"""

    game_id: UUID
    snapshot_id: str
    source_versions: str
    exported_at: str

    def __post_init__(self) -> None:
        """UUID・digestと供給済みJST日時の形を検証する。"""
        if type(self.game_id) is not UUID:
            raise PlayExportSupplyError("試合識別子が不正です")
        validate_snapshot_id(self.snapshot_id)
        validate_snapshot_id(self.source_versions)
        if type(self.exported_at) is not str:
            raise PlayExportSupplyError("出力日時が不正です")
        try:
            parsed = datetime.strptime(self.exported_at, "%Y-%m-%d %H:%M:%S")
        except ValueError as error:
            raise PlayExportSupplyError("出力日時が不正です") from error
        if parsed.strftime("%Y-%m-%d %H:%M:%S") != self.exported_at:
            raise PlayExportSupplyError("出力日時が非正準です")


@dataclass(frozen=True, slots=True)
class CompletedPlayArchive:
    """context内だけで利用できる、検証済みZIPのハンドル。"""

    file: BinaryIO
    filename: str
    byte_length: int
    sha256: str

    def chunks(self, chunk_size: int = 65_536) -> Iterator[bytes]:
        """先頭から有限サイズで読み、全送出時にもhashを確認する。"""
        if type(chunk_size) is not int or chunk_size < 1:
            raise PlayExportArchiveError("chunkの上限が不正です")
        self.file.seek(0)
        digest = hashlib.sha256()
        remaining = self.byte_length
        while remaining:
            data = self.file.read(min(chunk_size, remaining))
            if not data:
                raise PlayExportArchiveError("完成ZIPが途中で失われました")
            digest.update(data)
            remaining -= len(data)
            yield data
        if self.file.read(1) or digest.hexdigest() != self.sha256:
            raise PlayExportArchiveError("完成ZIPの整合が失われました")


def _check_archive_size(file: BinaryIO, maximum: int) -> None:
    """書込位置が上限を超えたら即座に失敗する。"""
    if file.tell() > maximum:
        raise PlayExportArchiveError("ZIP容量の上限を超えました")


@contextmanager
def prepare_play_archive(
    snapshot: ExportSnapshot,
    tables: Mapping[str, Iterable[SavedCsvRow]],
    *,
    limits: ExportLimits = ExportLimits(),
) -> Iterator[CompletedPlayArchive]:
    """全10CSVを一時ファイルに完成し、manifestと全ZIPを検証する。

    成功応答前の生成器でありHTTPを登録しない。失敗・切断・取消を含め、呼出側が
    contextを抜けたら一時ファイルを閉じる。ファイル名に利用者入力を使わない。

    Args:
        snapshot: callerが確定した同一読取版。
        tables: 88列本体と全9サイドカー。実在0行も明示的に渡す。
        limits: 行・文字・展開後バイト・ZIPバイトの上限。

    Yields:
        完成ZIPのcontext限定ハンドル。

    Raises:
        PlayExportSupplyError: 欠測・列・版・型が不正な場合。
        PlayExportArchiveError: 容量・完成ZIPの整合が不正な場合。
        OSError: 一時ディスク・書込・読取が失敗した場合。
    """
    if type(snapshot) is not ExportSnapshot or type(limits) is not ExportLimits:
        raise PlayExportSupplyError("出力の版または設定が不正です")
    if not isinstance(tables, Mapping):
        raise PlayExportSupplyError("全ファイルの供給が必要です")
    sources = _bounded_mapping(tables, tuple(CSV_HEADERS))
    # TemporaryFileはディスク上に作り、例外時も自動closeする。
    with tempfile.TemporaryFile(mode="w+b") as spool:
        file_records: list[dict[str, str | int]] = []
        total = 0
        with zipfile.ZipFile(spool, mode="w", compression=zipfile.ZIP_STORED) as bundle:
            for name, headers in CSV_HEADERS.items():
                count = 0

                def counted_rows() -> Iterator[tuple[str | int | None, ...]]:
                    """検証済み行を一行ずつ数え、全行保存を避ける。"""
                    nonlocal count
                    for row in saved_values(
                        name,
                        sources[name],
                        snapshot.snapshot_id,
                        game_id=snapshot.game_id,
                        max_rows=limits.max_rows_per_file,
                        max_cell_chars=limits.max_cell_chars,
                        max_row_chars=limits.max_row_chars,
                    ):
                        count += 1
                        yield row

                digest = hashlib.sha256()
                size = 0
                with bundle.open(name, mode="w", force_zip64=True) as member:
                    for chunk in stream_csv(
                        headers, counted_rows(), chunk_size=limits.chunk_size
                    ):
                        size += len(chunk)
                        total += len(chunk)
                        if (
                            size > limits.max_file_bytes
                            or total > limits.max_total_bytes
                        ):
                            raise PlayExportArchiveError("CSV容量の上限を超えました")
                        member.write(chunk)
                        digest.update(chunk)
                        _check_archive_size(spool, limits.max_archive_bytes)
                file_records.append(
                    {
                        "name": name,
                        "sha256": digest.hexdigest(),
                        "byte_length": size,
                        "data_row_count": count,
                    }
                )
            manifest = json.dumps(
                {
                    "format_version": "pitchlog-play-export-v1-candidate",
                    "game_id": str(snapshot.game_id),
                    "snapshot_id": snapshot.snapshot_id,
                    "source_versions": snapshot.source_versions,
                    "exported_at": snapshot.exported_at,
                    "timezone": "Asia/Tokyo",
                    "files": file_records,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if (
                len(manifest) > limits.max_file_bytes
                or total + len(manifest) > limits.max_total_bytes
            ):
                raise PlayExportArchiveError("manifest容量の上限を超えました")
            bundle.writestr("manifest.json", manifest)
        _check_archive_size(spool, limits.max_archive_bytes)
        spool.flush()
        size = spool.tell()
        spool.seek(0)
        with zipfile.ZipFile(spool, mode="r") as verified:
            if verified.testzip() is not None:
                raise PlayExportArchiveError("ZIPのCRCが不正です")
        spool.seek(0)
        digest = hashlib.sha256()
        while data := spool.read(limits.chunk_size):
            digest.update(data)
        spool.seek(0)
        yield CompletedPlayArchive(
            file=spool,
            filename=f"pitchlog-plays-{snapshot.game_id}.zip",
            byte_length=size,
            sha256=digest.hexdigest(),
        )
