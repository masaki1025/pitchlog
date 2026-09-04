"""単一の文書検査プロファイルを22検査へ通すコンフォーマンスランナー。"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any, Never, Sequence


class RunnerError(Exception):
    """ランナーの引数または入力資産の不正を表す。"""


class _ArgumentParser(argparse.ArgumentParser):
    """argparseの終了をランナーの終了コード2へ写す。"""

    def error(self, message: str) -> Never:
        raise RunnerError(f"コマンドライン引数が不正です: {message}")


def _load_module(name: str, filename: str) -> Any:
    """隣接Pythonモジュールをsys.path変更なしで読み込む。"""
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"モジュールを読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


doc_check_profile = _load_module(
    "check_doc_profiles_doc_check_profile",
    "doc_check_profile.py",
)
design_checker = _load_module(
    "check_doc_profiles_design_checker",
    "check_design_propagation.py",
)
coverage_checker = _load_module(
    "check_doc_profiles_coverage_checker",
    "check_doc_coverage.py",
)

COVERAGE_CHECK_IDS = frozenset(
    {
        "attribution",
        "ledger",
        "attribution-destination",
        "attribution-direct",
    }
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コンフォーマンスランナーの引数を解釈する。"""
    parser = _ArgumentParser(description="文書検査プロファイルの全検査を実行する")
    parser.add_argument("--profile", type=Path, required=True, help="検査するプロファイル")
    parser.add_argument("--registry", type=Path, help="照合するプロファイルレジストリ")
    parser.add_argument("--checks", help="実行する検査IDのカンマ区切り")
    parser.add_argument("--json", action="store_true", help="JSON envelopeを出力する")
    return parser.parse_args(argv)


def _selected_checks(value: str | None) -> frozenset[str]:
    """選択検査を解析し、未知IDを拒否する。"""
    if value is None:
        return frozenset(doc_check_profile.CHECK_IDS_ALL)
    selected = frozenset(part.strip() for part in value.split(",") if part.strip())
    if not selected:
        raise RunnerError("--checks に検査IDがありません")
    unknown = selected - set(doc_check_profile.CHECK_IDS_ALL)
    if unknown:
        raise RunnerError(f"--checks に未知IDがあります: {sorted(unknown)}")
    return selected


def _check_result(
    check_id: str,
    status: str,
    *,
    reason: str | None = None,
    findings: Sequence[str] = (),
) -> dict[str, Any]:
    """1検査分のenvelope要素を作る。"""
    result: dict[str, Any] = {
        "check_id": check_id,
        "status": status,
        "findings": list(findings),
    }
    if reason:
        result["reason"] = reason
    return result


def _invoke_check(profile: Any, check_id: str) -> tuple[int, tuple[str, ...]]:
    """所有する検査モジュールを1 IDだけ実行して出力行を返す。"""
    checker = coverage_checker if check_id in COVERAGE_CHECK_IDS else design_checker
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = checker.main(
            ["--profile", str(profile.path), "--checks", check_id]
        )
    lines = tuple(
        line
        for line in (*stderr.getvalue().splitlines(), *stdout.getvalue().splitlines())
        if line
    )
    return exit_code, lines


def _load_profile(args: argparse.Namespace, root: Path) -> tuple[Any, str]:
    """任意のレジストリ照合を行って指定プロファイルを返す。"""
    profile_path = args.profile if args.profile.is_absolute() else root / args.profile
    if args.registry is None:
        return doc_check_profile.load_profile(profile_path, root=root), ""
    registry_path = args.registry if args.registry.is_absolute() else root / args.registry
    registry = doc_check_profile.load_registry(registry_path, root=root)
    profiles = doc_check_profile.resolve_profiles(registry, root=root)
    matches = tuple(profile for profile in profiles if profile.path == profile_path.resolve())
    if len(matches) != 1:
        raise RunnerError(f"指定プロファイルがレジストリに一意に登録されていません: {profile_path}")
    return matches[0], str(registry.path)


def _empty_checks() -> list[dict[str, Any]]:
    """入力不正envelope用の22件の未実行結果を返す。"""
    return [
        _check_result(check_id, "not_run")
        for check_id in doc_check_profile.CHECK_IDS_ALL
    ]


def _run(argv: Sequence[str] | None) -> tuple[int, dict[str, Any], bool]:
    """検査を実行し、終了コード・envelope・JSON指定有無を返す。"""
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in raw_arguments
    partial = "--checks" in raw_arguments
    profile_label = "<未指定>"
    registry_label = ""
    try:
        args = parse_args(raw_arguments)
        profile_label = str(args.profile)
        registry_label = str(args.registry) if args.registry is not None else ""
        selected = _selected_checks(args.checks)
        root = Path.cwd().resolve()
        profile, registry_label = _load_profile(args, root)
        profile_label = profile.name
        if profile.invariants is not None:
            doc_check_profile.load_invariants(
                profile.invariants,
                schema_dir=profile.schema_dir,
            )
        checks: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for check_id in doc_check_profile.CHECK_IDS_ALL:
            if check_id not in selected:
                checks.append(_check_result(check_id, "not_run"))
                continue
            if check_id in profile.not_applicable:
                checks.append(
                    _check_result(
                        check_id,
                        "not_applicable",
                        reason=profile.not_applicable[check_id],
                    )
                )
                continue
            exit_code, findings = _invoke_check(profile, check_id)
            if exit_code == 0:
                checks.append(_check_result(check_id, "pass"))
            elif exit_code == 1:
                checks.append(
                    _check_result(
                        check_id,
                        "fail",
                        reason=findings[0] if findings else "検査違反",
                        findings=findings,
                    )
                )
            else:
                message = findings[0] if findings else f"{check_id} の入力が不正です"
                checks.append(
                    _check_result(
                        check_id,
                        "fail",
                        reason=message,
                        findings=findings,
                    )
                )
                errors.append(
                    {"code": "check-input-error", "message": message, "path": str(profile.path)}
                )
        exit_code = 2 if errors else (1 if any(c["status"] == "fail" for c in checks) else 0)
        envelope = {
            "schema_version": 1,
            "profile": profile_label,
            "registry": registry_label,
            "exit_code": exit_code,
            "partial": args.checks is not None,
            "checks": checks,
            "errors": errors,
        }
        return exit_code, envelope, args.json
    except (RunnerError, doc_check_profile.ProfileError) as error:
        envelope = {
            "schema_version": 1,
            "profile": profile_label,
            "registry": registry_label,
            "exit_code": 2,
            "partial": partial,
            "checks": _empty_checks(),
            "errors": [{"code": "input-error", "message": str(error)}],
        }
        return 2, envelope, json_output


def main(argv: Sequence[str] | None = None) -> int:
    """指定プロファイルを実行し0・1・2の終了コードを返す。"""
    exit_code, envelope, json_output = _run(argv)
    if json_output:
        print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
    else:
        for check in envelope["checks"]:
            for finding in check["findings"]:
                print(finding, file=sys.stderr)
        for error in envelope["errors"]:
            print(f"check_doc_profiles.py: {error['message']}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
