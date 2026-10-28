"""binding client 設定の閉じた読み取りを固定する。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from pitchlog.sync.control_provider.binding_client import (
    BindingClientConfigurationError,
    load_binding_client_configuration,
)


def _write(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "binding-client.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _valid() -> dict[str, object]:
    return {
        "schema_version": 1,
        "broker_endpoint": "/run/pitchlog/binding-endpoint.json",
        "control_instance": str(uuid4()),
        "business_instance": str(uuid4()),
        "restore_epoch": str(uuid4()),
        "control_version": 3,
    }


def test_valid_configuration_is_loaded(tmp_path: Path) -> None:
    """閉形式の設定だけを読み、値をそのまま返す。"""
    value = _valid()
    config = load_binding_client_configuration(_write(tmp_path, value))
    assert str(config.control_instance) == value["control_instance"]
    assert config.control_version == 3
    assert str(config.broker_endpoint) == value["broker_endpoint"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: v.update(extra=1),
        lambda v: v.pop("restore_epoch"),
        lambda v: v.update(schema_version=2),
        lambda v: v.update(control_version=0),
        lambda v: v.update(broker_endpoint="relative.json"),
        lambda v: v.update(control_instance="not-a-uuid"),
        lambda v: v.update(control_instance=str(uuid4()).upper()),
        lambda v: v.update(business_instance=123),
    ],
)
def test_malformed_configuration_is_rejected(tmp_path: Path, mutate) -> None:
    """余剰・欠落・型不正・非正規UUIDを拒否する。"""
    value = _valid()
    mutate(value)
    with pytest.raises(BindingClientConfigurationError):
        load_binding_client_configuration(_write(tmp_path, value))


def test_missing_or_symlinked_configuration_is_rejected(tmp_path: Path) -> None:
    """不在とsymlinkを設定として受理しない。"""
    with pytest.raises(BindingClientConfigurationError):
        load_binding_client_configuration(tmp_path / "absent.json")
    target = _write(tmp_path, _valid())
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(BindingClientConfigurationError):
        load_binding_client_configuration(link)
