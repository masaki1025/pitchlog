"""ランタイム契約の切り替え拘束と再実行性を検証する。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from test_authz_runtime_contract_repository import provisional_reference_revision

from pitchlog.authz import runtime_contract_generator as generator
from pitchlog.authz.runtime_contract_dryrun import (
    _verify_pr_acceptance,
    build_dryrun,
)
from pitchlog.authz.runtime_contract_dryrun import (
    main as dryrun_main,
)
from pitchlog.authz.runtime_contract_state import (
    GENERATED_MODULE,
    PRODUCT_ASSET,
    RUNTIME_CONTRACT_ASSET,
    STAGED_PRODUCT_ASSET,
    RuntimeContractState,
    evaluate_repository,
    render_runtime_contract,
)

_ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *arguments: str) -> str:
    """試験リポジトリで Git を実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_json(path: Path, asset: dict[str, Any]) -> None:
    """試験資産を読みやすい JSON として保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _read_json(path: Path) -> dict[str, Any]:
    """試験資産の JSON object を読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


@pytest.fixture
def switch_repository(tmp_path: Path) -> tuple[Path, str, str]:
    """比較元と作業 HEAD を持つ最小 Git リポジトリを作る。"""
    root = tmp_path / "repository"
    _git(tmp_path, "init", str(root))
    reference = provisional_reference_revision(_ROOT)
    for path in (RUNTIME_CONTRACT_ASSET, STAGED_PRODUCT_ASSET):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _git(_ROOT, "show", f"{reference}:{path.as_posix()}") + "\n",
            encoding="utf-8",
        )
    module_path = root / GENERATED_MODULE
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        render_runtime_contract(_read_json(root / RUNTIME_CONTRACT_ASSET)),
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "commit",
        "-m",
        "base",
    )
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/develop", base)
    (root / "marker.txt").write_text("head\n", encoding="utf-8")
    _git(root, "add", "marker.txt")
    _git(
        root,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "commit",
        "-m",
        "head",
    )
    head = _git(root, "rev-parse", "HEAD")
    staged = _read_json(root / STAGED_PRODUCT_ASSET)
    staged.pop("pending_switch")
    staged.pop("provisional_contract_additions")
    _write_json(root / PRODUCT_ASSET, staged)
    (root / STAGED_PRODUCT_ASSET).unlink()
    return root, base, head


def test_switch_converges_and_second_run_has_no_diff(
    switch_repository: tuple[Path, str, str],
) -> None:
    """切り替え後は製品状態となり、再実行でバイトが変わらない。"""
    root, base, _ = switch_repository
    assert generator.switch_repository(root, base)
    assert evaluate_repository(root) == (RuntimeContractState.PRODUCT, set())
    before = (
        (root / RUNTIME_CONTRACT_ASSET).read_bytes(),
        (root / GENERATED_MODULE).read_bytes(),
    )
    assert not generator.switch_repository(root, base)
    assert generator.main(["switch", "--base", base], repository_root=root) == 0
    assert before == (
        (root / RUNTIME_CONTRACT_ASSET).read_bytes(),
        (root / GENERATED_MODULE).read_bytes(),
    )


@pytest.mark.parametrize("base_kind", ["head", "unrelated", "old_ancestor"])
def test_switch_rejects_wrong_base_without_writes(
    switch_repository: tuple[Path, str, str],
    base_kind: str,
) -> None:
    """先端でない比較元と無関係な commit を拒否する。"""
    root, base, head = switch_repository
    if base_kind == "old_ancestor":
        _git(root, "update-ref", "refs/remotes/origin/develop", head)
        candidate = base
    elif base_kind == "unrelated":
        candidate = _git(
            root,
            "-c",
            "user.name=Contract Test",
            "-c",
            "user.email=contract@example.invalid",
            "commit-tree",
            _git(root, "rev-parse", "HEAD^{tree}"),
            "-m",
            "unrelated",
        )
        _git(root, "update-ref", "refs/remotes/origin/develop", candidate)
    else:
        candidate = head
    before = (root / RUNTIME_CONTRACT_ASSET).read_bytes()
    with pytest.raises(ValueError):
        generator.switch_repository(root, candidate)
    assert (root / RUNTIME_CONTRACT_ASSET).read_bytes() == before


@pytest.mark.parametrize(
    "mutation", ["revision_plus_two", "current_tampered", "u1", "final_mismatch"]
)
def test_switch_self_checks_fail_before_writing(
    switch_repository: tuple[Path, str, str],
    mutation: str,
) -> None:
    """自己検証の不一致ではどちらの生成物も変更しない。"""
    root, base, _ = switch_repository
    if mutation == "revision_plus_two":
        path = root / RUNTIME_CONTRACT_ASSET
        asset = _read_json(path)
        asset["runtime_contract_revision"] += 2
        _write_json(path, asset)
    elif mutation == "current_tampered":
        path = root / RUNTIME_CONTRACT_ASSET
        asset = _read_json(path)
        asset["provisional"] = False
        _write_json(path, asset)
    elif mutation == "u1":
        staged = _git(root, "show", f"{base}:{STAGED_PRODUCT_ASSET.as_posix()}")
        asset = json.loads(staged)
        asset["provisional_contract_additions"].pop()
        _git(
            root,
            "update-ref",
            "refs/remotes/origin/develop",
            _git(root, "rev-parse", "HEAD"),
        )
        _write_json(root / STAGED_PRODUCT_ASSET, asset)
        (root / PRODUCT_ASSET).unlink()
        _git(root, "add", ".")
        _git(
            root,
            "-c",
            "user.name=Contract Test",
            "-c",
            "user.email=contract@example.invalid",
            "commit",
            "-m",
            "bad staged",
        )
        base = _git(root, "rev-parse", "HEAD")
        _git(root, "update-ref", "refs/remotes/origin/develop", base)
        _write_json(root / PRODUCT_ASSET, _read_json(root / STAGED_PRODUCT_ASSET))
        (root / STAGED_PRODUCT_ASSET).unlink()
    else:
        path = root / PRODUCT_ASSET
        asset = _read_json(path)
        asset["scope"]["product_schema"] = False
        _write_json(path, asset)
    before = (
        (root / RUNTIME_CONTRACT_ASSET).read_bytes(),
        (root / GENERATED_MODULE).read_bytes(),
    )
    with pytest.raises(ValueError):
        generator.switch_repository(root, base)
    assert before == (
        (root / RUNTIME_CONTRACT_ASSET).read_bytes(),
        (root / GENERATED_MODULE).read_bytes(),
    )


def test_switch_recovers_after_first_replacement(
    switch_repository: tuple[Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """資産だけの置き換え後に失敗しても再実行で収束する。"""
    root, base, _ = switch_repository
    original_write = generator._atomic_write

    def fail_module(target: Path, content: str) -> None:
        """生成モジュールへの書き込みだけを失敗させる。"""
        if target == root / GENERATED_MODULE:
            raise OSError("試験用の中断")
        original_write(target, content)

    monkeypatch.setattr(generator, "_atomic_write", fail_module)
    with pytest.raises(OSError, match="試験用の中断"):
        generator.switch_repository(root, base)
    assert evaluate_repository(root)[1]
    monkeypatch.setattr(generator, "_atomic_write", original_write)
    assert generator.switch_repository(root, base)
    assert evaluate_repository(root) == (RuntimeContractState.PRODUCT, set())


def test_switch_restores_originals_if_written_revision_is_wrong(
    switch_repository: tuple[Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """書き込み後の revision 自己検証に失敗したら元の 2 ファイルへ戻す。"""
    root, base, _ = switch_repository
    originals = (
        (root / RUNTIME_CONTRACT_ASSET).read_bytes(),
        (root / GENERATED_MODULE).read_bytes(),
    )
    original_write = generator._atomic_write
    injected = False

    def write_wrong_revision(target: Path, content: str) -> None:
        """最初の資産書き込みだけ revision を 1 つ余分に進める。"""
        nonlocal injected
        if target == root / RUNTIME_CONTRACT_ASSET and not injected:
            injected = True
            asset = json.loads(content)
            asset["runtime_contract_revision"] += 1
            content = json.dumps(asset, ensure_ascii=False, indent=2) + "\n"
        original_write(target, content)

    monkeypatch.setattr(generator, "_atomic_write", write_wrong_revision)
    with pytest.raises(ValueError, match="書き込み後"):
        generator.switch_repository(root, base)
    assert originals == (
        (root / RUNTIME_CONTRACT_ASSET).read_bytes(),
        (root / GENERATED_MODULE).read_bytes(),
    )


def test_dryrun_tree_is_deterministic(tmp_path: Path) -> None:
    """同一 HEAD からの 2 回のドライランは同一 tree を作る。"""
    if evaluate_repository(_ROOT)[0] is RuntimeContractState.PRODUCT:
        pytest.skip("製品化済みのリポジトリでは切り替えドライランを行わない")
    source = tmp_path / "source"
    _git(tmp_path, "clone", "--local", "--no-hardlinks", str(_ROOT), str(source))
    base = _git(source, "rev-parse", "HEAD")
    _git(source, "update-ref", "refs/remotes/origin/develop", base)
    first = build_dryrun(source, tmp_path / "first")
    second = build_dryrun(source, tmp_path / "second")
    assert first.base_sha == second.base_sha
    assert first.head_sha == second.head_sha
    assert first.tree_sha == second.tree_sha
    _verify_pr_acceptance(first)


def test_dryrun_refuses_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """リポジトリ外からのドライラン CLI は終了コード 2 で拒否する。"""
    monkeypatch.chdir(tmp_path)
    assert dryrun_main([]) == 2
