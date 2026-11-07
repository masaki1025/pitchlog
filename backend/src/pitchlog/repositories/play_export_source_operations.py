"""CSV source読取1関数の登録候補と真正scope専用実行。"""

from __future__ import annotations

from itertools import islice
from typing import Any
from uuid import UUID

from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    FunctionOperationRegistration,
)
from pitchlog.repositories.play_export_source_codec import (
    _INPUTS,
    _OUTPUTS,
    CAPABILITY_ID,
    FUNCTION_ID,
    OPERATION_ID,
    ReadExportSourcePageToken,
    SourceVersion,
    build_source_read_call,
    decode_source_page,
)
from pitchlog.repositories.stats_native_operations import (
    _same_metadata,
    _same_statement,
)
from pitchlog.repositories.tokens import TenantOperationResult

_REGISTRATION: FunctionOperationRegistration | None = None


def _deny_generic_decode(_result):
    """汎用関数経路からCSV read資格を発行しない。"""
    raise FunctionOperationError("CSV source readは実RR scope専用です")


def registration_shape() -> dict[str, Any]:
    """SQL/型/有限行数を一つの閉宣言から構成する。"""
    call = build_source_read_call(ReadExportSourcePageToken(UUID(int=0)))
    return {
        "operation_id": OPERATION_ID,
        "token_type": ReadExportSourcePageToken,
        "capability_id": CAPABILITY_ID,
        "function_id": FUNCTION_ID,
        "statement": call.statement,
        "input_fields": tuple((name, kind.python_type) for name, kind in _INPUTS),
        "result_fields": tuple((name, kind.python_type) for name, kind in _OUTPUTS),
        "min_rows": 1,
        "max_rows": 500,
        "decoder": _deny_generic_decode,
        "nonempty_inputs": (),
        "nullable_results": tuple(name for name, _ in _OUTPUTS[6:]),
        "aware_datetime_results": (),
    }


def validate_registration(registration: object) -> None:
    """同時書換えで偽SQL/型/能力を登録できないよう全値を比較する。"""
    if type(registration) is not FunctionOperationRegistration:
        raise FunctionOperationError("CSV source登録の実型が不正")
    expected = registration_shape()
    for key, value in expected.items():
        observed = getattr(registration, key)
        if key == "statement":
            if not _same_statement(observed, value):
                raise FunctionOperationError("CSV source SQLが不一致")
        elif not _same_metadata(observed, value):
            raise FunctionOperationError("CSV source登録値が不一致")
    object.__setattr__(registration, "statement", expected["statement"])


def source_read_operation() -> FunctionOperationRegistration:
    """rootの予約family登録後だけ唯一の登録原本を返す。"""
    global _REGISTRATION
    if _REGISTRATION is None:
        _REGISTRATION = FunctionOperationRegistration(**registration_shape())
    validate_registration(_REGISTRATION)
    return _REGISTRATION


def run_qualified_source_read(handle, operation) -> TenantOperationResult:
    """実RR/RO CSV scopeの同Sessionだけで登録済1関数を実行する。"""
    from pitchlog.repositories import operation_registry, transaction

    transaction._require_play_export_scope(handle)
    if type(operation) is not ReadExportSourcePageToken:
        raise FunctionOperationError("CSV source token型が不正")
    spec = source_read_operation()
    if operation_registry.FUNCTION_OPERATION_REGISTRY.get(type(operation)) is not spec:
        raise FunctionOperationError("CSV source関数が未登録又は置換済み")
    call = build_source_read_call(operation)
    if not _same_statement(spec.statement, call.statement):
        raise FunctionOperationError("CSV source呼出SQLが不一致")
    runtime = transaction._TRANSACTION_RUNTIMES.get(handle._state_key)
    if runtime is None:
        raise FunctionOperationError("CSV source scopeが失効済み")
    session, _ = runtime
    with session.execute(call.statement, call.parameters) as result:
        rows = tuple(tuple(row) for row in islice(result, operation.page_size + 1))
    decode_source_page(rows, operation)
    return TenantOperationResult(rows)


class ReadPlayExportSources:
    """一つの実CSV scopeから全pageを有限に読み、版と件数を固定する。"""

    __slots__ = ("_handle", "_state_key", "_game", "_started", "_version")

    def __init__(self, handle, game_id: UUID):
        """自由なexecutorやSessionを受けず、真正scopeだけを所有する。"""
        from pitchlog.repositories.transaction import _require_play_export_scope

        _require_play_export_scope(handle)
        ReadExportSourcePageToken(game_id)
        self._handle = handle
        self._state_key = handle._state_key
        self._game = game_id
        self._started = False
        self._version: SourceVersion | None = None

    @property
    def version(self) -> SourceVersion:
        """最初の実page前に架空の版を返さない。"""
        if self._version is None:
            raise FunctionOperationError("CSV source版は未取得です")
        return self._version

    def pages(self, *, page_size: int = 500):
        """同じ版/snapshotのkeysetを一度だけ最後まで取得する。"""
        from pitchlog.repositories.transaction import _require_play_export_scope

        if self._started:
            raise FunctionOperationError("CSV source readerは再利用できません")
        self._started = True
        cursor = None
        count = 0
        while True:
            _require_play_export_scope(self._handle)
            if self._handle._state_key is not self._state_key:
                raise FunctionOperationError("CSV source readerが別scopeです")
            token = ReadExportSourcePageToken(
                self._game,
                cursor[0] if cursor else None,
                cursor[1] if cursor else None,
                page_size,
            )
            result = self._handle.run(token)
            if type(result) is not TenantOperationResult:
                raise FunctionOperationError("CSV sourceの実戻り型が不正")
            page = decode_source_page(result.rows, token, self._version)
            if self._version is None:
                self._version = page.version
            count += len(page.rows)
            if count > self.version.source_count:
                raise FunctionOperationError("CSV source件数が上限を超えました")
            final = len(page.rows) < page_size
            if final and count != self.version.source_count:
                raise FunctionOperationError("CSV sourceが欠落しています")
            if page.rows:
                cursor = page.rows[-1].ordering_key
                yield page.rows
            if final:
                return
