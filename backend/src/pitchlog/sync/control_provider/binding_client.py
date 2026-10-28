"""同期HTTP入口が使う binding client 設定の厳格な読み取り。

authority3 は秘密ではない識別子だが、制御主体の同一性を決める値なので、
root配置の非秘密JSONだけから読み、型・形式・重複・symlinkを閉じて検査する。
この設定の存在は権利・成功の証拠ではなく、未設定は書込入口を閉じる。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

_KEYS = frozenset(
    {
        "schema_version",
        "socket_path",
        "control_instance",
        "business_instance",
        "restore_epoch",
        "control_version",
    }
)


class BindingClientConfigurationError(RuntimeError):
    """設定が閉形式に合わない。元例外や設定値を表示しない。"""


@dataclass(frozen=True, slots=True, repr=False)
class BindingClientConfiguration:
    """binding broker への接続先と authority3 を固定する。"""

    socket_path: Path
    control_instance: UUID
    business_instance: UUID
    restore_epoch: UUID
    control_version: int


def _uuid(value: object) -> UUID:
    """正規UUID文字列だけをUUIDへ変換する。"""
    if type(value) is not str:
        raise BindingClientConfigurationError("binding client 設定のUUIDが不正")
    try:
        parsed = UUID(value)
    except ValueError:
        raise BindingClientConfigurationError(
            "binding client 設定のUUIDが不正"
        ) from None
    if str(parsed) != value:
        raise BindingClientConfigurationError("binding client 設定のUUIDが不正")
    return parsed


def load_binding_client_configuration(
    path: Path,
) -> BindingClientConfiguration:
    """root配置の非秘密JSONを読み、閉じた設定値だけを返す。

    Args:
        path: 設定ファイルの絶対パス。

    Returns:
        検査済みの接続先と authority3。

    Raises:
        BindingClientConfigurationError: 不在・symlink・余剰キー・型不正の場合。
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise BindingClientConfigurationError(
            "binding client 設定を開けません"
        ) from None
    try:
        body = os.read(descriptor, 65536)
        if len(body) >= 65536:
            raise BindingClientConfigurationError("binding client 設定が大きすぎます")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BindingClientConfigurationError(
            "binding client 設定がJSONではありません"
        ) from None
    if not isinstance(value, dict) or set(value) != _KEYS:
        raise BindingClientConfigurationError("binding client 設定のキー集合が不正")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise BindingClientConfigurationError("binding client 設定の版が不正")
    socket_name = value["socket_path"]
    if (
        type(socket_name) is not str
        or not socket_name
        or "\0" in socket_name
        or not os.path.isabs(socket_name)
        or not 0 < len(os.fsencode(socket_name)) < 108
    ):
        raise BindingClientConfigurationError("binding broker のsocketパスが不正")
    version = value["control_version"]
    if type(version) is not int or not 0 < version < 2**63:
        raise BindingClientConfigurationError("control_version が不正")
    return BindingClientConfiguration(
        socket_path=Path(socket_name),
        control_instance=_uuid(value["control_instance"]),
        business_instance=_uuid(value["business_instance"]),
        restore_epoch=_uuid(value["restore_epoch"]),
        control_version=version,
    )
