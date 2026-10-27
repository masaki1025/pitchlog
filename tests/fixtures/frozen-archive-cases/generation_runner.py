"""同じ意味ケースを原典世代別の入力と隔離processで構築する。"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

_SHARED = {"tests/fixtures/frozen-archive-cases/runner.py",
           "tests/fixtures/frozen-archive-cases/generation_runner.py"}


def _case_signature(runner, manifest):
    """caseの全fieldを入力世代と独立に照合する。"""
    return json.loads(runner._normalized_manifest_input(manifest))["cases"]


def _validate_pair(runner, current, previous):
    """旧版だけcaseや期待を差し替えることを拒否する。"""
    if (current.comparison_revision != previous.comparison_revision
            or current.repository_full_name != previous.repository_full_name
            or current.pull_request_number != previous.pull_request_number
            or _case_signature(runner, current) != _case_signature(runner, previous)):
        raise ValueError("入力世代間の規範caseまたは比較元が不一致")


def _stage_previous(source, shared_source, manifest, destination):
    """旧原典を読取コピーし、当時未存在の共有runnerだけを明示供給する。"""
    destination.mkdir()
    for tree in manifest.corpus_inputs.trees:
        shutil.copytree(source / tree, destination / tree)
    for path in manifest.corpus_inputs.files:
        origin = shared_source if path.as_posix() in _SHARED else source
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin / path, target)


def _manifest_payload(runner, manifest):
    """検証済みmanifestを子processへ全値で渡す。"""
    payload = json.loads(runner._normalized_manifest_input(manifest))
    payload["corpus_inputs"]["digest"] = manifest.corpus_inputs.digest
    return payload


def run_generations(runner, manifest, specs, source_root, selected_case_ids):
    """旧・現の同caseを世代ごとに別processへ渡す。"""
    labels = [spec.label for spec in specs]
    if len(labels) != len(set(labels)) or not set(labels) <= {"previous", "current"}:
        raise ValueError("世代ラベルが未知または重複")
    if selected_case_ids is not None and not selected_case_ids <= runner.EXPECTED_CASE_IDS:
        raise ValueError("指定されたcase IDがmanifestに存在しない")
    selected_ids = (runner.EXPECTED_CASE_IDS if selected_case_ids is None
                    else selected_case_ids)
    if not selected_ids:
        return ()
    previous = runner.load_manifest(Path(runner.__file__).with_name("manifest.previous.json"))
    _validate_pair(runner, manifest, previous)
    runner.validate_corpus_inputs(source_root, manifest)
    results = []
    with tempfile.TemporaryDirectory(prefix="frozen-generations-") as raw:
        root = Path(raw)
        for spec in specs:
            runner.validate_checker_spec(spec, manifest)
            profile = previous if spec.label == "previous" else manifest
            staged = source_root
            if spec.label == "previous":
                staged = root / "previous-input"
                _stage_previous(spec.root, source_root, profile, staged)
            runner.validate_corpus_inputs(staged, profile)
            profile_path = root / f"{spec.label}-manifest.json"
            profile_path.write_text(json.dumps(_manifest_payload(runner, profile)))
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment.pop("PYTHONPATH", None)
            environment.pop("GIT_DIR", None)
            environment.pop("GIT_WORK_TREE", None)
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker",
                 str(Path(runner.__file__).resolve()), str(profile_path), str(staged),
                 str(spec.root), spec.label,
                 json.dumps(sorted(selected_ids))],
                cwd=staged, env=environment, capture_output=True, text=True, check=False,
            )
            if process.returncode:
                raise RuntimeError(f"世代別構築が失敗: {spec.label}: {process.stderr}")
            payload = json.loads(process.stdout)
            rows = payload["results"]
            expected_ids = selected_ids
            if (len(rows) != len(expected_ids)
                    or {row["case_id"] for row in rows} != set(expected_ids)):
                raise ValueError("世代別結果のcase集合が不一致")
            for row in rows:
                if (row["checker"] != spec.label
                        or row["input_generation"] != spec.label
                        or row["input_digest"] != profile.corpus_inputs.digest):
                    raise ValueError("世代別結果の対象版が不一致")
                # 生成側のexpected/matchesを信用せず親の規範caseから再構成する。
                definition = next(c for c in manifest.cases if c.id == row["case_id"])
                results.append(runner.RunResult(
                    row["case_id"], spec.label, definition.expected[spec.label],
                    definition.recorded_exit_codes[spec.label], row["exit_code"],
                    row["stdout"], row["stderr"], spec.label,
                    profile.corpus_inputs.digest, row["input_revision"],
                ))
    return tuple(results)


def _worker(arguments):
    """世代に対応するhelper/importだけをロードして合成PRを作る。"""
    runner_path, manifest_path, source, checker, label, selected = arguments
    if label not in {"previous", "current"}:
        raise ValueError("未知の入力世代")
    source_root = Path(source).resolve()
    sys.path[:0] = [str(source_root / "tests"), str(source_root)]
    spec = importlib.util.spec_from_file_location("_generation_case_runner", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("共有runnerをロードできない")
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    manifest = runner.load_manifest(Path(manifest_path))
    runner.validate_checker_spec(runner.CheckerSpec(label, Path(checker)), manifest)
    helpers = runner._load_repository_helpers(source_root)
    if helpers.REPOSITORY_ROOT.resolve() != source_root:
        raise ValueError("別世代のhelper rootが混入")
    dependencies = [helpers.checker, helpers.checker.frozen_history]
    if label == "current":
        dependencies.append(helpers.checker.frozen_archive)
    elif hasattr(helpers.checker, "frozen_archive"):
        raise ValueError("旧版に存在しない依存が混入")
    for relative in manifest.corpus_inputs.files:
        if relative.parts[0] == "scripts":
            if (source_root / relative).read_bytes() != (Path(checker) / relative).read_bytes():
                raise ValueError("実checkerと入力世代の実装byteが不一致")
    for module in dependencies:
        if Path(module.__file__).resolve().parent != source_root / "scripts":
            raise ValueError("別世代のchecker依存が混入")
    selected_ids = set(json.loads(selected))
    if not selected_ids <= runner.EXPECTED_CASE_IDS:
        raise ValueError("未知のcase ID")
    results = []
    with tempfile.TemporaryDirectory(prefix="frozen-generation-cases-") as raw:
        for definition in manifest.cases:
            if definition.id not in selected_ids:
                continue
            monkeypatch = runner.pytest.MonkeyPatch()
            try:
                prepared = runner.prepare_case(
                    definition, Path(raw) / f"case-{definition.id:02d}",
                    source_root, manifest, monkeypatch,
                )
                result = runner.run_checker(prepared, runner.CheckerSpec(label, Path(checker)))
                revision = (manifest.comparison_revision if label == "previous"
                            else runner._git(Path(checker), ["rev-parse", "HEAD"]).stdout.strip())
                results.append(replace(result, input_generation=label,
                                       input_digest=manifest.corpus_inputs.digest,
                                       input_revision=revision))
            finally:
                monkeypatch.undo()
    print(json.dumps(runner._result_payload(tuple(results)), ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 8 or sys.argv[1] != "--worker":
        raise SystemExit("世代別runnerは親runnerからのみ起動する")
    _worker(sys.argv[2:])
