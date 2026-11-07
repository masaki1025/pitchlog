"""正式凍結projectionのCI固定期待を閉じたschemaで検証する。"""

import copy
import json
from pathlib import Path

import pytest
from first_ball_expected_source_pins import SourcePinError, read_ci_followup_inputs


def _document():
    return {
        "schema_version": 1,
        "pins": {
            "catalog_before_revision": "a" * 40,
            "catalog_after_revision": "b" * 40,
            "ratio_ast_sha256": "c" * 64,
            "rate_ast_sha256": "d" * 64,
        },
    }


@pytest.mark.parametrize(
    ("case", "value"),
    (
        ("bool_version", True),
        ("missing", None),
        ("extra", None),
        ("bool_pin", True),
        ("integer_pin", 1),
        ("uppercase", "A" * 40),
        ("git_width", "a" * 64),
        ("ast_width", "c" * 40),
        ("nonhex", "g" * 40),
        ("root_extra", None),
    ),
)
def test_ci_input_rejects_open_or_noncanonical_shapes(tmp_path, case, value):
    """既知4key以外や曖昧な型/桁を補修して受理しない。"""
    data = copy.deepcopy(_document())
    if case == "bool_version":
        data["schema_version"] = value
    elif case == "missing":
        data["pins"].pop("rate_ast_sha256")
    elif case == "extra":
        data["pins"]["extra"] = "e" * 64
    elif case == "root_extra":
        data["extra"] = None
    elif case == "ast_width":
        data["pins"]["ratio_ast_sha256"] = value
    else:
        data["pins"]["catalog_before_revision"] = value
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(data))
    with pytest.raises(SourcePinError):
        read_ci_followup_inputs(path=path)


def test_duplicate_and_missing_file_are_rejected(tmp_path):
    """JSONの補修・最後勝ちや未存在の補完をしない。"""
    path = tmp_path / "inputs.json"
    with pytest.raises(SourcePinError):
        read_ci_followup_inputs(path=path)
    path.write_text('{"schema_version":1,"schema_version":1,"pins":{}}')
    with pytest.raises(SourcePinError):
        read_ci_followup_inputs(path=path)


def test_symlink_is_rejected(tmp_path):
    """別入力へのsymlink置換を読取前に拒否する。"""
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_document()))
    path = tmp_path / "inputs.json"
    path.symlink_to(target)
    with pytest.raises(SourcePinError):
        read_ci_followup_inputs(path=path)


def test_fixture_is_registered_in_the_formal_projection():
    """固定入力をPython走査外へ移すだけでなく正式統制へ含める。"""
    root = Path(__file__).resolve().parents[2]
    asset = json.loads(
        (root / "contracts/tenant_boundary/frozen-inputs.json").read_text()
    )
    paths = asset["baseline_control"]["identity"]["frozen_projection"]["external_files"]
    assert paths.count("backend/tests/fixtures/pr197_ci_followup_inputs_v1.json") == 1
    pins = read_ci_followup_inputs()
    assert len(pins) == 4
    assert (
        len(pins["catalog_before_revision"])
        == len(pins["catalog_after_revision"])
        == 40
    )
    assert len(pins["ratio_ast_sha256"]) == len(pins["rate_ast_sha256"]) == 64
