"""版別入力の閉じた対応と、意味caseを維持する境界を検査する。"""
import copy
import importlib.util
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_frozen_archive_case_runner import MANIFEST, REPOSITORY_ROOT, runner

_PATH = REPOSITORY_ROOT / "tests/fixtures/frozen-archive-cases/generation_runner.py"
_SPEC = importlib.util.spec_from_file_location("generation_runner_under_test", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
generation = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(generation)
PREVIOUS = runner.load_manifest(_PATH.with_name("manifest.previous.json"))


def test_profiles_preserve_all_eleven_semantic_cases() -> None:
    """case/期待全fieldは両世代で同一、履歴prefixは版ごとに保持する。"""
    generation._validate_pair(runner, MANIFEST, PREVIOUS)
    assert (generation._case_signature(runner, MANIFEST)
            == generation._case_signature(runner, PREVIOUS))
    assert PREVIOUS.corpus_inputs.pinned_prefixes.history_record_count == 5
    assert len(PREVIOUS.corpus_inputs.pinned_prefixes.snapshot_names) == 73
    assert MANIFEST.corpus_inputs.pinned_prefixes.history_record_count == 6
    assert PREVIOUS.corpus_inputs.digest != MANIFEST.corpus_inputs.digest


@pytest.mark.parametrize("fault", ["action", "expected", "parameter", "revision", "repository"])
def test_profile_mismatch_is_rejected(fault: str) -> None:
    """旧側のcase/期待/対象版だけを書換えて一致を作れない。"""
    previous = copy.deepcopy(PREVIOUS)
    if fault in {"action", "expected", "parameter"}:
        first = previous.cases[0]
        if fault == "action":
            first = replace(first, action="recorded_movement")
        elif fault == "expected":
            first.expected["previous"] = "red"
        else:
            first.parameters["unknown"] = 1
        previous = replace(previous, cases=(first,) + previous.cases[1:])
    elif fault == "revision":
        previous = replace(previous, comparison_revision="f" * 40)
    else:
        previous = replace(previous, repository_full_name="unknown/repository")
    with pytest.raises(ValueError, match="不一致"):
        generation._validate_pair(runner, MANIFEST, previous)


@pytest.mark.parametrize("labels", [("unknown",), ("previous", "previous")])
def test_unknown_or_duplicate_generation_is_rejected_before_execution(
    labels: tuple[str, ...],
) -> None:
    """未知版と重複版をprocess起動前に拒否する。"""
    specs = tuple(runner.CheckerSpec(label, REPOSITORY_ROOT) for label in labels)
    with pytest.raises(ValueError, match="世代ラベル"):
        generation.run_generations(runner, MANIFEST, specs, REPOSITORY_ROOT, None)


def test_previous_staging_uses_old_bytes_and_only_shared_runner(tmp_path: Path) -> None:
    """旧原典を変えず共有runnerだけを別原典として供給する。"""
    old, shared = tmp_path / "old", tmp_path / "shared"
    relative = Path("scripts/check_tenant_boundary_bypass.py")
    common = Path("tests/fixtures/frozen-archive-cases/runner.py")
    for root, values in [(old, [(relative, "old"), (common, "unavailable-old")]),
                         (shared, [(relative, "new"), (common, "shared")])]:
        for path, text in values:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text)
    manifest = SimpleNamespace(corpus_inputs=SimpleNamespace(trees=(), files=(relative, common)))
    staged = tmp_path / "staged"
    generation._stage_previous(old, shared, manifest, staged)
    assert (staged / relative).read_text() == "old"
    assert (staged / common).read_text() == "shared"
    assert (old / common).read_text() == "unavailable-old"
    (old / relative).unlink()
    with pytest.raises(FileNotFoundError):
        generation._stage_previous(old, shared, manifest, tmp_path / "missing")


def test_empty_selection_returns_no_cases_without_preparing_or_spawning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空集合はNoneの全件指定と異なり、構築やprocessを起動しない。"""
    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("空集合から構築・子processへ到達した")

    monkeypatch.setattr(generation, "_validate_pair", unexpected)
    monkeypatch.setattr(generation.subprocess, "run", unexpected)
    specs = (runner.CheckerSpec("previous", REPOSITORY_ROOT),)
    assert generation.run_generations(
        runner, MANIFEST, specs, REPOSITORY_ROOT, frozenset()
    ) == ()
