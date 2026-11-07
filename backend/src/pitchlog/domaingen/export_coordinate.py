"""B-7の有限整数座標宣言からPython/TypeScript targetを生成する。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from pitchlog.domaingen.core import _canonical_hash, _format_typed_target

_ROOT = Path(__file__).resolve().parents[4]
_MODEL = "backend/domain/play-export-display.model.json"
_SCHEMA = "backend/domain/play-export-display.schema.json"
_GEOMETRY = "contracts/display_geometry_263_v1.json"
_MANIFEST = "backend/domain/play-export-display.manifest.json"


class ExportCoordinateDeclarationError(ValueError):
    """未知の座標式・単位・型を生成対象へ拡張しない。"""


def _declaration(model: Mapping[str, Any]) -> tuple[int, str, str, str]:
    """唯一のcourse画面変換を閉じた宣言から読む。"""
    if type(model) is not dict or set(model) != {
        "schemaVersion",
        "geometryPath",
        "geometrySha256",
        "exportTransforms",
        "elapsedTransform",
        "fieldingPositionLabels",
        "plateResultDisplay",
    }:
        raise ExportCoordinateDeclarationError("B-7 root宣言が不正")
    elapsed = model["elapsedTransform"]
    if type(elapsed) is not dict or elapsed != {
        "id": "serverAcceptedElapsed",
        "kind": "whole-minutes-h-mm",
        "startSource": "games.started_at",
        "endSource": "pg_catalog.clock_timestamp",
        "runtime": "python-server-only",
        "precision": "postgres-timestamptz-microsecond",
        "negative": "reject",
    }:
        raise ExportCoordinateDeclarationError("経過時間の有限宣言が不正")
    labels = model["fieldingPositionLabels"]
    if (
        type(labels) is not dict
        or set(labels) != {str(value) for value in range(1, 10)} | {"designated-hitter"}
        or any(
            type(value) is not str or not value or len(value) > 4
            for value in labels.values()
        )
        or len(set(labels.values())) != 10
    ):
        raise ExportCoordinateDeclarationError("守備位置表示の有限宣言が不正")
    plate = model["plateResultDisplay"]
    if (
        type(plate) is not dict
        or set(plate)
        != {"kind", "aliases", "fielderFormats", "otherwise", "unfinished"}
        or plate["kind"] != "finite-legacy-label"
        or plate["otherwise"] != "source-label"
        or plate["unfinished"] != "null"
        or type(plate["aliases"]) is not dict
        or set(plate["aliases"])
        != {"見逃し三振", "空振り三振", "三振ゲッツー", "振り逃げ", "ファールフライ"}
        or any(
            type(value) is not str or not value for value in plate["aliases"].values()
        )
        or plate["fielderFormats"]
        != {
            "併殺打": "fielder-balltype-double",
            "ライナー併殺": "fielder-line-double",
            "凡打死": "fielder-balltype",
            "凡打出塁": "fielder-balltype",
        }
    ):
        raise ExportCoordinateDeclarationError("打席結果表示の有限宣言が不正")
    transforms = model.get("exportTransforms")
    if type(transforms) is not list or len(transforms) != 1:
        raise ExportCoordinateDeclarationError("座標変換宣言が一意でない")
    transform = transforms[0]
    if type(transform) is not dict or set(transform) != {
        "id",
        "kind",
        "sourceUnit",
        "size",
        "axes",
    }:
        raise ExportCoordinateDeclarationError("座標変換宣言の列が不正")
    size = transform["size"]
    axes = transform["axes"]
    if (
        model["schemaVersion"] != 1
        or model["geometryPath"] != _GEOMETRY
        or transform["id"] != "courseScreen"
        or transform["kind"] != "bounded-integer-axis-map"
        or type(size) is not int
        or size != 263
        or transform["sourceUnit"] != f"1/{size}"
        or type(axes) is not dict
        or set(axes) != {"x", "y"}
        or axes["x"] != "identity"
        or axes["y"] != "complement"
    ):
        raise ExportCoordinateDeclarationError("B-7の有限宣言ではない")
    return size, transform["sourceUnit"], axes["x"], axes["y"]


def _generate_course_export_targets(
    model: Mapping[str, Any], source_hash: str, geometry: Mapping[str, Any]
) -> dict[str, str]:
    """bundle検査済み単一宣言から両言語の固定小数点整数だけを生成する。

    Args:
        model: T5共通式から独立した唯一のB-7宣言。
        source_hash: 宣言の全値から正準導出したhash。
        geometry: 束縛済み画面scaleの参照契約。

    Returns:
        生成されたPython/TypeScript targetの正規pathと内容。

    Raises:
        ExportCoordinateDeclarationError: 未知式や対象版の場合。
    """
    size, unit, x_axis, y_axis = _declaration(model)
    labels = model["fieldingPositionLabels"]
    if (
        type(source_hash) is not str
        or source_hash != _canonical_hash(model)
        or type(geometry) is not dict
        or geometry.get("size") != size
        or geometry.get("version") != "display_263_top_left_v1"
        or geometry.get("origin") != "top_left"
        or geometry.get("x_direction") != "right"
        or geometry.get("y_direction") != "down"
    ):
        raise ExportCoordinateDeclarationError("model hashが不正")
    py_x = "x_value" if x_axis == "identity" else "SIZE - x_value"
    py_y = "y_value" if y_axis == "identity" else "SIZE - y_value"
    ts_x = "xValue" if x_axis == "identity" else "SIZE - xValue"
    ts_y = "yValue" if y_axis == "identity" else "SIZE - yValue"
    py_labels = {str(value): labels[str(value)] for value in range(1, 10)}
    ts_labels = json.dumps(py_labels, ensure_ascii=False, sort_keys=True)
    dh_label = labels["designated-hitter"]
    plate_aliases = model["plateResultDisplay"]["aliases"]
    py_plate_aliases = repr(plate_aliases)
    ts_plate_aliases = json.dumps(plate_aliases, ensure_ascii=False, sort_keys=True)
    python = f'''"""自動生成。B-7の正準座標から画面整数への一方向写像。"""

import re
from datetime import datetime, timezone

SOURCE_MODEL_HASH = {source_hash!r}
SIZE = {size}
UNIT = {unit!r}
_PATTERN = re.compile(r"(?:0|[1-9][0-9]{{0,3}})\\Z")


def _number(value: str) -> int:
    """非正準・範囲外を整数化前に拒否する。"""
    if type(value) is not str or _PATTERN.fullmatch(value) is None:
        raise ValueError("正準整数座標が必要です")
    number = int(value)
    if number > SIZE:
        raise ValueError("画面座標の範囲外です")
    return number


def course_screen(
    x: str | None, y: str | None, unit: str | None
) -> tuple[str | None, str | None]:
    """保存k/263を画面整数へ写し、欠測は両軸同時だけ保持する。"""
    if x is None and y is None and unit is None:
        return None, None
    if unit != UNIT or type(x) is not str or type(y) is not str:
        raise ValueError("正準座標単位が不一致です")
    x_value = _number(x)
    y_value = _number(y)
    return str({py_x}), str({py_y})


def server_accepted_elapsed(start: datetime, accepted: datetime) -> str:
    """試合開始からサーバー受理までの完了分をh:mmで返す。"""
    if (
        type(start) is not datetime
        or type(accepted) is not datetime
        or start.utcoffset() is None
        or accepted.utcoffset() is None
    ):
        raise ValueError("開始/受理時刻が不正です")
    try:
        first = start.astimezone(timezone.utc)
        last = accepted.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ValueError("開始/受理時刻が不正です") from None
    if last < first:
        raise ValueError("開始/受理時刻が不正です")
    elapsed = last - first
    minutes = elapsed.days * 1440 + elapsed.seconds // 60
    hours, minute = divmod(minutes, 60)
    return f"{{hours}}:{{minute:02d}}"


FIELDING_POSITION_LABELS = {py_labels!r}
DH_LABEL = {dh_label!r}


def fielding_position_label(role: dict[str, str]) -> str:
    """保存された有限守備roleを旧表示欄へ写す。"""
    if type(role) is not dict:
        raise ValueError("守備位置roleが不正です")
    if role == {{"kind": "designated-hitter"}}:
        return DH_LABEL
    if set(role) != {{"kind", "position"}} or role.get("kind") != "fielding":
        raise ValueError("守備位置roleが不正です")
    position = role["position"]
    if type(position) is not str or position not in FIELDING_POSITION_LABELS:
        raise ValueError("守備位置roleが不正です")
    return FIELDING_POSITION_LABELS[position]


PLATE_RESULT_ALIASES = {py_plate_aliases}


def plate_result_display(
    label: str | None, pa_ended: bool, fielder: str | None, ball_type: str | None
) -> str | None:
    """確定打席結果だけを旧有限表示へ写す。"""
    if type(pa_ended) is not bool or (label is not None and type(label) is not str):
        raise ValueError("打席結果原本が不正です")
    if not pa_ended:
        return None
    if not label:
        raise ValueError("完了打席の結果が欠測です")
    if label in PLATE_RESULT_ALIASES:
        return PLATE_RESULT_ALIASES[label]
    if label in ("併殺打", "ライナー併殺", "凡打死", "凡打出塁"):
        if type(fielder) is not str or fielder not in tuple(
            str(n) for n in range(1, 10)
        ):
            raise ValueError("捕球選手が欠測です")
        if label == "ライナー併殺":
            return f"{{fielder}}ライナー併"
        if type(ball_type) is not str or not ball_type:
            raise ValueError("打球種類が欠測です")
        return f"{{fielder}}{{ball_type}}" + ("併" if label == "併殺打" else "")
    return label
'''
    typescript = f"""/** 自動生成。B-7の正準座標から画面整数への一方向写像。 */
export const SOURCE_MODEL_HASH = {source_hash!r}
const SIZE = {size}
const UNIT = {unit!r}
const PATTERN = /^(?:0|[1-9][0-9]{{0,3}})$/

function number(value: string): number {{
  if (typeof value !== 'string' || !PATTERN.test(value))
    throw new Error('正準整数座標が必要です')
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed) || parsed > SIZE)
    throw new Error('画面座標の範囲外です')
  return parsed
}}

/** 保存k/263を画面整数へ写し、欠測は両軸同時だけ保持する。 */
export function courseScreen(
  x: string | null,
  y: string | null,
  unit: string | null,
): readonly [string | null, string | null] {{
  if (x === null && y === null && unit === null) return [null, null]
  if (unit !== UNIT || x === null || y === null)
    throw new Error('正準座標単位が不一致です')
  const xValue = number(x)
  const yValue = number(y)
  return [String({ts_x}), String({ts_y})]
}}

const FIELDING_POSITION_LABELS: Readonly<Record<string, string>> = {ts_labels}
const DH_LABEL = {dh_label!r}

/** 保存された有限守備roleを旧表示欄へ写す。 */
export function fieldingPositionLabel(role: Record<string, unknown>): string {{
  if (role === null || typeof role !== 'object' || Array.isArray(role))
    throw new Error('守備位置roleが不正です')
  if (Object.keys(role).length === 1 && role.kind === 'designated-hitter')
    return DH_LABEL
  if (
    Object.keys(role).length !== 2 || role.kind !== 'fielding' ||
    typeof role.position !== 'string' ||
    !Object.prototype.hasOwnProperty.call(FIELDING_POSITION_LABELS, role.position)
  ) throw new Error('守備位置roleが不正です')
  return FIELDING_POSITION_LABELS[role.position]!
}}

const PLATE_RESULT_ALIASES: Readonly<Record<string, string>> = {ts_plate_aliases}

/** 確定打席結果だけを旧有限表示へ写す。 */
export function plateResultDisplay(
  label: string | null,
  paEnded: boolean,
  fielder: string | null,
  ballType: string | null,
): string | null {{
  if (typeof paEnded !== 'boolean' || (label !== null && typeof label !== 'string'))
    throw new Error('打席結果原本が不正です')
  if (!paEnded) return null
  if (!label) throw new Error('完了打席の結果が欠測です')
  if (Object.prototype.hasOwnProperty.call(PLATE_RESULT_ALIASES, label))
    return PLATE_RESULT_ALIASES[label]!
  if (['併殺打', 'ライナー併殺', '凡打死', '凡打出塁'].includes(label)) {{
    if (typeof fielder !== 'string' || !/^[1-9]$/.test(fielder))
      throw new Error('捕球選手が欠測です')
    if (label === 'ライナー併殺') return `${{fielder}}ライナー併`
    if (typeof ballType !== 'string' || !ballType)
      throw new Error('打球種類が欠測です')
    return `${{fielder}}${{ballType}}${{label === '併殺打' ? '併' : ''}}`
  }}
  return label
}}
"""
    return {
        "backend/src/pitchlog/exports/generated/coordinate_transform.py": python,
        "frontend/src/lib/generated/playExportCoordinate.ts": typescript,
    }


def generate_course_export_bundle(root: Path = _ROOT) -> tuple[dict[str, str], dict]:
    """参照geometry全byteと閉schemaを確認し、二対象と束縛台帳を導出する。

    Args:
        root: 読み取る単一repository root。

    Returns:
        公式生成二対象とその全入力・出力hash台帳。

    Raises:
        ExportCoordinateDeclarationError: 入力/参照元/出力集合が閉契約外の場合。
    """
    from jsonschema import Draft202012Validator

    try:
        model_bytes = (root / _MODEL).read_bytes()
        schema_bytes = (root / _SCHEMA).read_bytes()
        geometry_bytes = (root / _GEOMETRY).read_bytes()
        model = json.loads(model_bytes)
        schema = json.loads(schema_bytes)
        geometry = json.loads(geometry_bytes)
        Draft202012Validator(schema).validate(model)
        if (
            type(model) is not dict
            or set(model)
            != {
                "schemaVersion",
                "geometryPath",
                "geometrySha256",
                "exportTransforms",
                "elapsedTransform",
                "fieldingPositionLabels",
                "plateResultDisplay",
            }
            or model["geometryPath"] != _GEOMETRY
            or model["geometrySha256"] != hashlib.sha256(geometry_bytes).hexdigest()
        ):
            raise ExportCoordinateDeclarationError("B-7参照元が不一致")
        source_hash = _canonical_hash(model)
        bundle = _generate_course_export_targets(model, source_hash, geometry)
        bundle = {
            path: _format_typed_target(path, content)
            for path, content in bundle.items()
        }
        manifest = {
            "schemaVersion": 1,
            "status": "candidate-formal-acceptance-pending",
            "modelSha256": source_hash,
            "inputs": {
                path: hashlib.sha256(content).hexdigest()
                for path, content in (
                    (_MODEL, model_bytes),
                    (_SCHEMA, schema_bytes),
                    (_GEOMETRY, geometry_bytes),
                    (
                        "backend/src/pitchlog/domaingen/export_coordinate.py",
                        (
                            root / "backend/src/pitchlog/domaingen/export_coordinate.py"
                        ).read_bytes(),
                    ),
                )
            },
            "generatedFiles": {
                path: hashlib.sha256(content.encode()).hexdigest()
                for path, content in bundle.items()
            },
            "t5ModelUnchanged": True,
        }
        return bundle, manifest
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ExportCoordinateDeclarationError("B-7生成入力が不正") from error


def main() -> None:
    """公式宣言から生成物と候補台帳を一括出力又は全byte検査する。"""
    parser = argparse.ArgumentParser(description="B-7毎球CSV表示target生成")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    bundle, manifest = generate_course_export_bundle()
    expected = {
        **bundle,
        _MANIFEST: json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    }
    for path, content in expected.items():
        target = _ROOT / path
        if args.write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        elif not target.is_file() or target.read_text() != content:
            raise ExportCoordinateDeclarationError("B-7生成targetが不一致")


if __name__ == "__main__":
    main()
