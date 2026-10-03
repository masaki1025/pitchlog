"""手作業fixtureの初回凍結と追記のみの更新履歴を検査する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import frozen_history

ROOT = Path(__file__).resolve().parents[1]
class FixtureBaselineError(ValueError):
    """手作業fixtureの凍結基準違反を表す。"""


def _object(value: object, location: str) -> dict[str, Any]:
    """値をJSONオブジェクトとして検査する。

    Args:
        value: 検査対象。
        location: 違反位置。

    Returns:
        JSONオブジェクト。
    """
    if not isinstance(value, dict):
        raise FixtureBaselineError(f"{location}: object が必要")
    return value


def _keys(value: Mapping[str, Any], required: set[str], location: str) -> None:
    """必須・未知キーを検査する。

    Args:
        value: 検査対象。
        required: 必須キーの集合。
        location: 違反位置。
    """
    actual = set(value)
    if actual != required:
        raise FixtureBaselineError(
            f"{location}: キー不一致: 不足={sorted(required - actual)} "
            f"余分={sorted(actual - required)}"
        )


def _read_json(path: Path) -> dict[str, Any]:
    """JSON資産を読み、読めない場合は不合格にする。

    Args:
        path: 資産の絶対パス。

    Returns:
        JSONオブジェクト。
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureBaselineError(f"{path}: 宣言を読めない: {error}") from error
    return _object(value, str(path))


def _resolved_file(root: Path, relative: str) -> Path:
    """リポジトリ内の通常ファイルを解決する。

    Args:
        root: リポジトリルート。
        relative: 宣言された相対パス。

    Returns:
        検証済みの絶対パス。
    """
    candidate = root / relative
    if (
        not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or candidate.is_symlink()
        or not candidate.is_file()
        or not candidate.resolve().is_relative_to(root.resolve())
    ):
        raise FixtureBaselineError(f"外部凍結対象を解決できない: {relative}")
    return candidate


def _previous_assets(root: Path, relative: str) -> list[dict[str, Any]]:
    """既存の履歴をHEADと比較元から取得する。

    Args:
        root: リポジトリルート。
        relative: fixture資産の相対パス。

    Returns:
        既存の凍結履歴を持つ資産。まだ無ければ空配列。
    """
    previous_assets: list[dict[str, Any]] = []
    for revision in ("HEAD", "origin/develop"):
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative}"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        try:
            previous = _object(json.loads(result.stdout), f"{revision}:{relative}")
        except (json.JSONDecodeError, FixtureBaselineError) as error:
            raise FixtureBaselineError(
                f"{revision}:{relative}: 比較元を読めない: {error}"
            ) from error
        if "baseline_control" in previous:
            previous_assets.append(previous)
    return previous_assets


def _projection_digest(root: Path, asset: dict[str, Any], location: str) -> str:
    """宣言された凍結射影を既存の正規化方式で計算する。

    Args:
        root: リポジトリルート。
        asset: fixture資産。
        location: 違反位置。

    Returns:
        SHA-256の16進表現。
    """
    control = _object(asset.get("baseline_control"), f"{location}.baseline_control")
    identity = _object(control.get("identity"), f"{location}.identity")
    projection = _object(identity.get("frozen_projection"), f"{location}.frozen_projection")
    if projection.get("excluded") != ["baseline_control"]:
        raise FixtureBaselineError(f"{location}: 凍結対象からはbaseline_controlだけを除く")
    external = projection.get("external_files")
    if (
        not isinstance(external, list)
        or not external
        or not all(isinstance(item, str) for item in external)
        or len(external) != len(set(external))
    ):
        raise FixtureBaselineError(f"{location}: 外部凍結対象の宣言が不正")
    implementations: dict[str, bytes] = {}
    for relative in external:
        if not isinstance(relative, str):
            raise FixtureBaselineError(f"{location}: 外部凍結対象のパスが不正")
        try:
            implementations[relative] = _resolved_file(root, relative).read_bytes()
        except OSError as error:
            raise FixtureBaselineError(
                f"{location}: 外部凍結対象を読めない: {relative}: {error}"
            ) from error
    try:
        content = frozen_history.frozen_projection_content(
            asset, implementations, location=location
        )
    except frozen_history.ContractError as error:
        raise FixtureBaselineError(f"{location}: 凍結射影が不正: {error}") from error
    return hashlib.sha256(content).hexdigest()


def validate_asset(
    root: Path,
    relative: str,
    asset: dict[str, Any],
    previous: dict[str, Any] | None,
) -> None:
    """fixture資産の凍結宣言・digest・追記履歴を検査する。

    Args:
        root: リポジトリルート。
        relative: fixture資産の相対パス。
        asset: 現在のfixture資産。
        previous: 既存の凍結履歴を持つ比較元。
    """
    location = relative
    control = _object(asset.get("baseline_control"), f"{location}.baseline_control")
    _keys(control, {"identity", "movement_policy", "history_authority", "history"}, location)
    if control["history_authority"] is not True:
        raise FixtureBaselineError(f"{location}: 履歴authorityが必要")
    identity = _object(control["identity"], f"{location}.identity")
    _keys(
        identity,
        {
            "scheme", "identifier_prefix", "current_identifiers",
            "no_baseline_marker", "frozen_projection",
        },
        f"{location}.identity",
    )
    policy = _object(control["movement_policy"], f"{location}.movement_policy")
    _keys(
        policy,
        {
            "acceptance_unit", "previous_state", "new_state",
            "intermediate_commits_are_records", "movement_triggers",
            "affected_baselines", "history_append_only",
            "pending_approval_marker", "pending_source_commit_marker",
        },
        f"{location}.movement_policy",
    )
    if (
        policy["history_append_only"] is not True
        or policy["intermediate_commits_are_records"] is not False
    ):
        raise FixtureBaselineError(f"{location}: 追記のみの受理単位が必要")
    digest = _projection_digest(root, asset, location)
    expected_id = f"{identity['identifier_prefix']}{digest}"
    if identity["current_identifiers"] != [expected_id]:
        raise FixtureBaselineError(f"{location}: 識別値と凍結射影のdigestが不一致")
    history = control["history"]
    if not isinstance(history, list) or not history:
        raise FixtureBaselineError(f"{location}: 凍結履歴が無い")
    record = _object(history[-1], f"{location}.history[-1]")
    required_record = {
        "source_commit", "new_baseline_identifiers", "previous_baseline_identifiers",
        "change", "movement_fact", "reason", "approved_by", "approved_on",
    }
    record_keys = set(record)
    if record_keys != required_record and record_keys != required_record | {"acceptance_id"}:
        raise FixtureBaselineError(f"{location}: 履歴記録のキーが不正")
    if record["new_baseline_identifiers"] != [expected_id]:
        raise FixtureBaselineError(f"{location}: 履歴の新識別値が不一致")
    change = _object(record["change"], f"{location}.history[-1].change")
    _keys(change, {"subject", "before", "after"}, f"{location}.history[-1].change")
    after = _object(change["after"], f"{location}.history[-1].change.after")
    if after != {"state": "PRESENT", "frozen_projection_sha256": digest}:
        raise FixtureBaselineError(f"{location}: 履歴のdigestが不一致")
    if not all(isinstance(record[key], str) and record[key] for key in ("movement_fact", "reason")):
        raise FixtureBaselineError(f"{location}: 更新事実と理由が必要")
    if previous is None:
        marker = identity["no_baseline_marker"]
        if (
            len(history) != 1
            or "acceptance_id" in record
            or record["previous_baseline_identifiers"] != [marker]
            or change["before"] != {
                "state": marker, "frozen_projection_sha256": marker,
            }
            or record["source_commit"] != policy["pending_source_commit_marker"]
            or record["approved_by"] != policy["pending_approval_marker"]
            or record["approved_on"] != policy["pending_approval_marker"]
        ):
            raise FixtureBaselineError(f"{location}: 未承認bootstrap記録が不正")
    else:
        old_control = _object(previous["baseline_control"], f"{location}.previous")
        old_history = old_control.get("history")
        if not isinstance(old_history, list) or history[: len(old_history)] != old_history:
            raise FixtureBaselineError(f"{location}: 凍結履歴が追記のみでない")
        if len(history) > len(old_history) + 1:
            raise FixtureBaselineError(f"{location}: 1行為に複数記録を追加できない")
        old_ids = _object(old_control["identity"], f"{location}.previous.identity")[
            "current_identifiers"
        ]
        if len(history) == len(old_history):
            if identity["current_identifiers"] != old_ids:
                raise FixtureBaselineError(f"{location}: 記録なしで基準を変更できない")
        else:
            if record["previous_baseline_identifiers"] != old_ids:
                raise FixtureBaselineError(f"{location}: 直前の識別値が不一致")
            if (
                not isinstance(record.get("acceptance_id"), str)
                or not record["acceptance_id"]
                or record["source_commit"] == policy["pending_source_commit_marker"]
                or record["approved_by"] == policy["pending_approval_marker"]
                or record["approved_on"] == policy["pending_approval_marker"]
            ):
                raise FixtureBaselineError(f"{location}: 更新受理記録の承認情報が不正")


def check_repository(
    root: Path,
    coverage_relative: str,
    *,
    asset_overrides: Mapping[str, dict[str, Any]] | None = None,
) -> None:
    """資産側の対象宣言を読んで全fixture凍結を検査する。

    Args:
        root: リポジトリルート。
        coverage_relative: 資産側の対象宣言への相対パス。
        asset_overrides: 負例用のfixture資産差し替え。
    """
    coverage = _read_json(_resolved_file(root, coverage_relative))
    sources = coverage.get("fixtureSources")
    pattern = coverage.get("fixtureDiscoveryPattern")
    if not isinstance(sources, list) or not isinstance(pattern, str):
        raise FixtureBaselineError("手作業fixtureの対象宣言を読めない")
    source_paths = [source.get("fixturePath") for source in sources if isinstance(source, dict)]
    discovered = {
        path.relative_to(root).as_posix() for path in root.glob(pattern)
    }
    if (
        not source_paths
        or len(source_paths) != len(sources)
        or not all(isinstance(path, str) for path in source_paths)
        or set(source_paths) != discovered
    ):
        raise FixtureBaselineError("手作業fixtureの対象宣言が実資産と不一致")
    for relative in source_paths:
        if not isinstance(relative, str):
            raise FixtureBaselineError("手作業fixtureのパスが不正")
        asset = (
            asset_overrides[relative]
            if asset_overrides is not None and relative in asset_overrides
            else _read_json(_resolved_file(root, relative))
        )
        previous_assets = _previous_assets(root, relative)
        if not previous_assets:
            validate_asset(root, relative, asset, None)
        for previous in previous_assets:
            validate_asset(root, relative, asset, previous)


def main(argv: list[str] | None = None) -> int:
    """CLIで凍結の合否を返す。

    Args:
        argv: コマンドライン引数。

    Returns:
        合格なら0、それ以外は1。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--coverage", required=True)
    args = parser.parse_args(argv)
    try:
        check_repository(args.root.resolve(), args.coverage)
    except (FixtureBaselineError, OSError) as error:
        print(f"manual-fixture-baselines: 違反: {error}", file=sys.stderr)
        return 1
    print("manual-fixture-baselines: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
