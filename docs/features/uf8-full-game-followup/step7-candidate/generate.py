"""ステップ7の未受理候補を既存凍結関数で再生成する。"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from argparse import ArgumentParser
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import frozen_history as history
import runner
from pitchlog.authz.runtime_contract_state import asset_digest, render_runtime_contract

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).resolve().parent

CI = ".github/workflows/ci.yml"
MANIFEST = "tests/fixtures/frozen-archive-cases/manifest.json"
AUTHORITY = "contracts/tenant_boundary/base-allowlist.json"
DECLARED = {AUTHORITY, "contracts/tenant_boundary/census-baseline.json"}
CI_NEEDLE = "      - run: pnpm test -- --run\n"
FRONTEND_FILTER_NEEDLE = (
    "              - 'backend/src/pitchlog/domaincheck/runners/**'\n"
)
FRONTEND_FILTER_ADDITION = (
    "              - 'backend/**'\n"
    "              - 'docs/features/uf8-full-game-followup/"
    "step7-candidate/generate.py'\n"
    "              - 'pyproject.toml'\n"
    "              - 'uv.lock'\n"
    "              - 'mise.toml'\n"
    "              - '.github/workflows/ci.yml'\n"
)
FRONTEND_JOB_NEEDLE = "  frontend:\n    needs: frontend-changes\n"
CI_ADDITION = """      # 製品 App と認証 fixture は使い捨て PostgreSQL にだけ接続する。
      - uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
        with:
          version: "0.8.13"
          enable-cache: true
          prune-cache: true
      - run: uv python install
        working-directory: .
      - run: uv sync --project backend --locked --dev
        working-directory: .
      - run: >-
          backend/.venv/bin/ruff check --config backend/pyproject.toml
          frontend/src/screens/GameScreenE2eSupport.py
          docs/features/uf8-full-game-followup/step7-candidate/generate.py
        working-directory: .
      - run: >-
          backend/.venv/bin/ty check --project backend
          --extra-search-path backend/src --extra-search-path backend/tests
          --extra-search-path scripts
          --extra-search-path tests/fixtures/frozen-archive-cases
          frontend/src/screens/GameScreenE2eSupport.py
          docs/features/uf8-full-game-followup/step7-candidate/generate.py
        working-directory: .
      - run: docker pull postgres:17.11-bookworm
        working-directory: .
      - run: pnpm exec playwright install --with-deps chromium
      - run: pnpm run test:browser
"""
GENERATED_SOURCE_ASSETS = {
    "contracts/tenant_boundary/runtime-authz-contract.json": (
        "backend/src/pitchlog/authz/runtime_contract.py"
    ),
    "contracts/tenant_boundary/repository-contract.json": (
        "backend/src/pitchlog/repositories/repository_contract.py"
    ),
    "contracts/tenant_boundary/tenant-context-allowlist.json": (
        "backend/src/pitchlog/repositories/tenant_context_contract.py"
    ),
}


def encode(value: object) -> bytes:
    """資産の既存 JSON 書式で候補を保存する。"""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def digest(value: bytes) -> str:
    """ファイル・既存射影の SHA-256 を表示する。"""
    return hashlib.sha256(value).hexdigest()


def save_pair(output: Path, path: str, old: bytes, new: bytes) -> None:
    """元ファイルの bytes と候補 bytes を別々に固定する。"""
    for stage, content in (("before", old), ("after", new)):
        target = output / stage / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def write_patch(output: Path) -> None:
    """前後ファイルと新snapshotから適用可能な統一patchを作る。"""
    chunks: list[str] = []

    def append_lines(lines: Iterable[str]) -> None:
        for line in lines:
            if line == " \n":
                chunks.append("\n")
            elif line.endswith("\n"):
                chunks.append(line)
            else:
                chunks.extend((line + "\n", "\\ No newline at end of file\n"))

    for candidate in sorted((output / "after").rglob("*")):
        if not candidate.is_file():
            continue
        name = candidate.relative_to(output / "after").as_posix()
        old = (output / "before" / name).read_text().splitlines(keepends=True)
        new = candidate.read_text().splitlines(keepends=True)
        chunks.append(f"diff --git a/{name} b/{name}\n")
        append_lines(
            difflib.unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}")
        )
    for snapshot in sorted((output / "new-snapshots").iterdir()):
        name = f"contracts/tenant_boundary/history-snapshots/{snapshot.name}"
        chunks.append(f"diff --git a/{name} b/{name}\nnew file mode 100644\n")
        append_lines(
            difflib.unified_diff(
                [],
                snapshot.read_text().splitlines(keepends=True),
                fromfile="/dev/null",
                tofile=f"b/{name}",
            )
        )
    (output / "candidate.patch").write_text("".join(chunks))


def state(
    assets: dict[str, dict[str, Any]],
    implementations: dict[str, bytes],
    location: str,
) -> tuple[dict[str, object], dict[str, bytes]]:
    """既存の射影・snapshot 導出だけで7.7の実状態を作る。"""
    parts = history._repository_components(assets, location)
    targets = sorted({path for part in parts.values() for path in part.external_files})
    projections, contents = history._asset_projection_snapshots(
        assets, implementations, location
    )
    return (
        {
            "declaration": {name: parts[name].declaration for name in sorted(assets)},
            "movement_policy": {
                name: parts[name].movement_policy for name in sorted(assets)
            },
            "external_snapshots": history._implementation_snapshots(
                targets, implementations, location
            ),
            "asset_snapshots": projections,
        },
        contents,
    )


def git_bytes(*args: str) -> bytes:
    """Git が固定した内容だけを読む。"""
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError("候補入力の Git 出所を確認できない")
    return result.stdout


def git_text(*args: str) -> str:
    """Git の単一識別子を読む。"""
    return git_bytes(*args).decode().strip()


def prove_before(
    paths: set[str], previous: dict[str, Any] | None, *, check: bool
) -> dict[str, object]:
    """現HEAD・公表develop・生成時HEADで正式入力の同一bytesを証明する。"""
    head = git_text("rev-parse", "HEAD")
    published = git_text("rev-parse", "origin/develop")
    source_sha = digest(Path(__file__).read_bytes())
    blobs: dict[str, str] = {}
    for path in sorted(paths):
        current = (ROOT / path).read_bytes()
        if current != git_bytes("show", f"{head}:{path}"):
            raise AssertionError(f"正式入力が dirty: {path}")
        if current != git_bytes("show", f"{published}:{path}"):
            raise AssertionError(f"公表済み origin/develop と前値が異なる: {path}")
        blobs[path] = git_text("rev-parse", f"{head}:{path}")
    if (
        previous is not None
        and previous.get("provenance_schema_version") == 2
        and previous.get("published_develop_head") == published
        and previous.get("generator_source_sha256") == source_sha
        and previous.get("before_git_blobs") == blobs
    ):
        recorded_head = previous.get("candidate_checkout_head")
        recorded_base = previous.get("source_git_base")
        if not isinstance(recorded_head, str) or not isinstance(
            recorded_base, str
        ):
            raise AssertionError("候補の生成時Git出所が不正")
        if git_text("merge-base", recorded_head, published) != recorded_base:
            raise AssertionError("候補の生成時merge-baseが不正")
        for path in sorted(paths):
            if (ROOT / path).read_bytes() != git_bytes(
                "show", f"{recorded_head}:{path}"
            ):
                raise AssertionError(f"生成時 Git blob と前値が異なる: {path}")
        return {
            "provenance_schema_version": 2,
            "source_git_base": recorded_base,
            "published_develop_head": published,
            "candidate_checkout_head": recorded_head,
            "generator_source_sha256": source_sha,
            "before_git_blobs": blobs,
        }
    if check:
        raise AssertionError("候補の生成出所または正式入力の鮮度が失われた")
    return {
        "provenance_schema_version": 2,
        "source_git_base": git_text("merge-base", head, published),
        "published_develop_head": published,
        "candidate_checkout_head": head,
        "generator_source_sha256": source_sha,
        "before_git_blobs": blobs,
    }


def reverse_dependencies(
    affected: list[str], before: dict[str, dict[str, Any]]
) -> dict[str, object]:
    """非secret・非legacyの全tracked fileから固定識別値の利用先を探す。"""
    paths = [name.decode() for name in git_bytes("ls-files", "-z").split(b"\0") if name]
    discovered: dict[str, list[str]] = {path: [] for path in GENERATED_SOURCE_ASSETS}
    digest_references: dict[str, list[str]] = {path: [] for path in affected}
    path_references: dict[str, list[str]] = {path: [] for path in affected}
    scanned = 0
    for path in paths:
        pieces = Path(path).parts
        if (
            path.startswith("docs/legacy/")
            or path.startswith("docs/features/uf8-full-game-followup/step7-candidate/")
            or any(
                piece == ".env"
                or (piece.startswith(".env.") and piece != ".env.example")
                for piece in pieces
            )
            or Path(path).suffix in {".key", ".pem", ".p12"}
        ):
            continue
        content = (ROOT / path).read_bytes()
        scanned += 1
        for asset in affected:
            if asset.encode() in content:
                path_references[asset].append(path)
            old_digest = before[asset].get("source_digest")
            if isinstance(old_digest, str) and old_digest.encode() in content:
                digest_references[asset].append(path)
        if not path.endswith(".py"):
            continue
        for asset in discovered:
            marker = f'SOURCE_ASSET = "{asset}"'.encode()
            if marker in content:
                if not re.search(rb"(?m)^SOURCE_DIGEST = \"[0-9a-f]{64}\"$", content):
                    raise AssertionError(f"生成コードのdigest宣言が不正: {path}")
                discovered[asset].append(path)
    for asset, expected in GENERATED_SOURCE_ASSETS.items():
        if discovered[asset] != [expected]:
            raise AssertionError(f"生成コードの逆依存が既知集合と異なる: {asset}")
    generated = set(GENERATED_SOURCE_ASSETS.values())
    for paths_for_asset in digest_references.values():
        for path in paths_for_asset:
            if path.endswith((".py", ".ts", ".js", ".vue")) and path not in generated:
                raise AssertionError(f"未候補のコード固定digest参照: {path}")
    return {
        "tracked_nonsecret_nonlegacy_files_scanned": scanned,
        "generated_modules": discovered,
        "asset_path_reference_paths": {
            path: sorted(items) for path, items in sorted(path_references.items())
        },
        "fixed_digest_reference_paths": {
            path: sorted(items) for path, items in sorted(digest_references.items())
        },
    }


def functional_references(scan: dict[str, object]) -> dict[str, object]:
    """情報用の文書件数と、実装コードの逆依存閉包を分ける。"""
    roots = ("backend/src/", "frontend/src/", "scripts/")
    return {
        field: {
            asset: [path for path in paths if path.startswith(roots)]
            for asset, paths in cast(dict[str, list[str]], scan[field]).items()
        }
        for field in (
            "generated_modules",
            "asset_path_reference_paths",
            "fixed_digest_reference_paths",
        )
    }


def constant_module_after(
    old: bytes, original: dict[str, object], updated: dict[str, object]
) -> bytes:
    """既存配布モジュールの版とcanonical digestの二定数だけ追随する。"""
    source = old.decode()
    for field, line_name in (
        ("contract_revision", "CONTRACT_REVISION"),
        ("source_digest", "SOURCE_DIGEST"),
    ):
        before_value = original[field]
        after_value = updated[field]
        old_line = f"{line_name} = {json.dumps(before_value)}\n"
        new_line = f"{line_name} = {json.dumps(after_value)}\n"
        if source.count(old_line) != 1:
            raise AssertionError(f"生成コードの固定値が一意でない: {line_name}")
        source = source.replace(old_line, new_line)
    return source.encode()


def verified_previous_output() -> bool:
    """前回の未受理生成物が全hash・空の人間欄を保つ場合だけ再生成を許す。"""
    metadata_path = OUTPUT / "metadata.json"
    if not metadata_path.is_file():
        return False
    try:
        previous = json.loads(metadata_path.read_bytes())
        if previous.get("status") != "未受理" or any(
            previous.get(key)
            for key in ("accepted_by", "accepted_date", "accepted_on", "signature")
        ):
            return False
        for stage, key in (
            ("before", "before_file_sha256"),
            ("after", "candidate_file_sha256"),
        ):
            hashes = previous[key]
            actual = {
                path.relative_to(OUTPUT / stage).as_posix(): digest(path.read_bytes())
                for path in (OUTPUT / stage).rglob("*")
                if path.is_file()
            }
            if hashes != actual:
                return False
        snapshots = previous["new_snapshot_names"]
        if (
            sorted(path.name for path in (OUTPUT / "new-snapshots").iterdir())
            != snapshots
        ):
            return False
        if any(
            digest((OUTPUT / "new-snapshots" / name).read_bytes()) != name
            for name in snapshots
        ):
            return False
        return (
            digest((OUTPUT / "candidate.patch").read_bytes())
            == previous["patch_sha256"]
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False


def verify_patch_application(stage: Path) -> None:
    """候補beforeだけの隔離copyへpatchを実適用し全after bytesを比較する。"""
    with tempfile.TemporaryDirectory(prefix="pitchlog-step7-apply-") as directory:
        checkout = Path(directory)
        for source in (stage / "before").rglob("*"):
            if source.is_file():
                target = checkout / source.relative_to(stage / "before")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        patch = stage / "candidate.patch"
        for arguments in (("apply", "--check", str(patch)), ("apply", str(patch))):
            result = subprocess.run(
                ["git", *arguments], cwd=checkout, capture_output=True, check=False
            )
            if result.returncode != 0:
                raise AssertionError("候補patchを隔離copyへ適用できない")
        for expected in (stage / "after").rglob("*"):
            if (
                expected.is_file()
                and (checkout / expected.relative_to(stage / "after")).read_bytes()
                != expected.read_bytes()
            ):
                raise AssertionError("候補patch適用後bytesがafterと異なる")
        for snapshot in (stage / "new-snapshots").iterdir():
            applied = (
                checkout / "contracts/tenant_boundary/history-snapshots" / snapshot.name
            )
            if applied.read_bytes() != snapshot.read_bytes():
                raise AssertionError("候補patch適用後snapshotがafterと異なる")


def publish_stage(stage: Path, *, check: bool) -> None:
    """所有する生成物だけを照合・更新し、他の資料は保持する。"""
    names = ("before", "after", "new-snapshots", "candidate.patch", "metadata.json")
    previous_owned = verified_previous_output()
    for name in names:
        existing = OUTPUT / name
        proposed = stage / name
        old_files = (
            {
                item.relative_to(existing).as_posix(): item
                for item in existing.rglob("*")
                if item.is_file()
            }
            if existing.is_dir()
            else ({"": existing} if existing.is_file() else {})
        )
        new_files = (
            {
                item.relative_to(proposed).as_posix(): item
                for item in proposed.rglob("*")
                if item.is_file()
            }
            if proposed.is_dir()
            else ({"": proposed} if proposed.is_file() else {})
        )
        if check and (
            old_files.keys() != new_files.keys()
            or any(
                old_files[key].read_bytes() != new_files[key].read_bytes()
                for key in old_files
            )
        ):
            raise AssertionError(f"候補の鮮度が失われた: {name}")
        if check:
            continue
        for relative, old_path in old_files.items():
            if (
                relative in new_files
                and old_path.read_bytes() == new_files[relative].read_bytes()
            ):
                continue
            path = f"{OUTPUT.relative_to(ROOT).as_posix()}/{name}"
            if relative:
                path = f"{path}/{relative}"
            if not previous_owned and old_path.read_bytes() != git_bytes(
                "show", f"HEAD:{path}"
            ):
                raise AssertionError(f"人が変更した候補生成物は上書きしない: {path}")
        if existing.is_dir():
            shutil.rmtree(existing)
            shutil.copytree(proposed, existing)
        else:
            shutil.copy2(proposed, existing)


def generate(
    output: Path, previous: dict[str, Any] | None, *, check: bool
) -> None:
    """未宣言波及を含む前後候補を隔離stagingへ構成する。"""
    before: dict[str, dict[str, Any]] = {
        path.relative_to(ROOT).as_posix(): json.loads(path.read_bytes())
        for path in sorted((ROOT / "contracts/tenant_boundary").glob("*.json"))
    }
    after = copy.deepcopy(before)
    old_ci = (ROOT / CI).read_bytes()
    assert old_ci.count(CI_NEEDLE.encode()) == 1
    assert old_ci.count(FRONTEND_FILTER_NEEDLE.encode()) == 1
    assert old_ci.count(FRONTEND_JOB_NEEDLE.encode()) == 1
    new_ci = old_ci.replace(CI_NEEDLE.encode(), (CI_NEEDLE + CI_ADDITION).encode())
    new_ci = new_ci.replace(
        FRONTEND_FILTER_NEEDLE.encode(),
        (FRONTEND_FILTER_NEEDLE + FRONTEND_FILTER_ADDITION).encode(),
    )
    new_ci = new_ci.replace(
        FRONTEND_JOB_NEEDLE.encode(),
        "  frontend:\n    timeout-minutes: 40\n    needs: frontend-changes\n".encode(),
    )
    save_pair(output, CI, old_ci, new_ci)

    affected: list[str] = []
    for name, original in before.items():
        identity = original["baseline_control"]["identity"]
        if CI not in identity["frozen_projection"]["external_files"]:
            continue
        affected.append(name)
        candidate = after[name]
        next_identity = candidate["baseline_control"]["identity"]
        field = next_identity["field"]
        candidate[field] += 1
        next_identity["current_identifiers"] = [f"{field}:{candidate[field]}"]
        if "source_digest" in candidate:
            candidate["source_digest"] = asset_digest(candidate)
    assert len(affected) == 8
    generated_paths = set(GENERATED_SOURCE_ASSETS.values())
    targets = {
        path
        for asset in before.values()
        for path in asset["baseline_control"]["identity"]["frozen_projection"][
            "external_files"
        ]
    }
    manifest_input = json.loads((ROOT / MANIFEST).read_bytes())
    snapshot_root = ROOT / "contracts/tenant_boundary/history-snapshots"
    old_snapshot_paths = {
        path.relative_to(ROOT).as_posix()
        for path in snapshot_root.iterdir()
        if path.is_file()
    }
    formal_paths = {
        CI,
        MANIFEST,
        *before,
        *generated_paths,
        *targets,
        *manifest_input["corpus_inputs"]["files"],
        *old_snapshot_paths,
        *(
            path.relative_to(ROOT).as_posix()
            for tree in manifest_input["corpus_inputs"]["trees"]
            for path in (ROOT / tree).rglob("*")
            if path.is_file()
        ),
    }
    provenance = prove_before(formal_paths, previous, check=check)
    current_reverse_scan = reverse_dependencies(affected, before)
    reusable_scan = (
        previous is not None
        and previous.get("provenance_schema_version") == 2
        and previous.get("candidate_checkout_head")
        == provenance["candidate_checkout_head"]
        and previous.get("generator_source_sha256")
        == provenance["generator_source_sha256"]
    )
    if reusable_scan:
        recorded_scan = previous.get("reverse_dependency_scan")
        if not isinstance(recorded_scan, dict) or functional_references(
            current_reverse_scan
        ) != functional_references(recorded_scan):
            raise AssertionError("現在の実装コード逆依存閉包が候補記録と異なる")
        reverse_scan = recorded_scan
    else:
        reverse_scan = current_reverse_scan

    for asset, path in GENERATED_SOURCE_ASSETS.items():
        old = (ROOT / path).read_bytes()
        if asset.endswith("runtime-authz-contract.json"):
            if old != render_runtime_contract(before[asset]).encode():
                raise AssertionError("既存runtime生成コードとcanonical描画が一致しない")
            new = render_runtime_contract(after[asset]).encode()
        else:
            new = constant_module_after(old, before[asset], after[asset])
        save_pair(output, path, old, new)

    old_impl = {path: (ROOT / path).read_bytes() for path in targets}
    new_impl = dict(old_impl)
    new_impl[CI] = new_ci
    old_parts = history._repository_components(before, "候補前")
    new_parts = history._repository_components(after, "候補後")
    movement = history.evaluate_repository_movement(
        history._repository_movement_states(before, old_parts, old_impl, "候補前"),
        history._repository_movement_states(after, new_parts, new_impl, "候補後"),
    )
    assert set(movement.affected_assets) == set(affected)
    old_state, old_projections = state(before, old_impl, "候補前")
    new_state, new_projections = state(after, new_impl, "候補後")
    old_ids = {
        name: list(old_parts[name].current_identifiers) for name in sorted(before)
    }
    new_ids = {
        name: list(new_parts[name].current_identifiers) for name in sorted(after)
    }
    aspects = sorted(history.derive_aspects(old_state, new_state))
    record = {
        "record_schema_version": 2,
        "acceptance_id": "",
        "previous_baseline_identifiers": old_ids,
        "new_baseline_identifiers": new_ids,
        "change": {
            "subject": "U-F8 ステップ7 CI ブラウザ検査候補。正式受理前",
            "aspect": aspects,
            "before": old_state,
            "after": new_state,
        },
        "movement_fact": (
            "必須 frontend job への封鎖ブラウザ検査追加候補で"
            "CI bytesが8資産の外部凍結対象を動かす。"
        ),
        "reason": "実App・認証・専用DBのブラウザ封鎖検査を必須jobに組み込むため。",
        "approved_by": "",
        "approved_on": "",
    }
    after[AUTHORITY]["baseline_control"]["history"].append(record)
    assert (
        before[AUTHORITY]["baseline_control"]["history"]
        == after[AUTHORITY]["baseline_control"]["history"][:-1]
    )
    for name in affected:
        save_pair(output, name, (ROOT / name).read_bytes(), encode(after[name]))

    old_snapshot_names = {
        path.name for path in snapshot_root.iterdir() if path.is_file()
    }
    snapshot_content = {
        digest(content): content
        for values in (old_impl, new_impl, old_projections, new_projections)
        for content in values.values()
    }
    target_snapshots = output / "new-snapshots"
    target_snapshots.mkdir(exist_ok=True)
    snapshot_rows = [
        *cast(list[dict[str, str]], old_state["external_snapshots"]),
        *cast(list[dict[str, str]], old_state["asset_snapshots"]),
        *cast(list[dict[str, str]], new_state["external_snapshots"]),
        *cast(list[dict[str, str]], new_state["asset_snapshots"]),
    ]
    for item in snapshot_rows:
        name = item["sha256"]
        if name not in old_snapshot_names:
            (target_snapshots / name).write_bytes(snapshot_content[name])

    old_manifest = (ROOT / MANIFEST).read_bytes()
    manifest = json.loads(old_manifest)
    with tempfile.TemporaryDirectory(prefix="pitchlog-step7-corpus-") as directory:
        overlay = Path(directory)
        for path in manifest["corpus_inputs"]["files"]:
            target = overlay / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)
        for tree in manifest["corpus_inputs"]["trees"]:
            shutil.copytree(ROOT / tree, overlay / tree, dirs_exist_ok=True)
        (overlay / CI).write_bytes(new_ci)
        for name in affected:
            (overlay / name).write_bytes(encode(after[name]))
        manifest["corpus_inputs"]["digest"] = "0" * 64
        manifest_path = overlay / MANIFEST
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(encode(manifest))
        corpus_digest = runner.corpus_input_digest(
            overlay, runner.load_manifest(manifest_path)
        )
    manifest["corpus_inputs"]["digest"] = corpus_digest
    save_pair(output, MANIFEST, old_manifest, encode(manifest))

    old_history = before[AUTHORITY]["baseline_control"]["history"]
    metadata = {
        "status": "未受理",
        **provenance,
        "review_acceptance_unit": "Draft 6〜7の同一PR。PR番号・受理前後SHAは未割当",
        "accepted_by": "",
        "accepted_date": "",
        "accepted_on": "",
        "signature": "",
        "declared_asset_scope": sorted(DECLARED),
        "asset_set": sorted(before),
        "frozen_target_set": sorted(targets),
        "affected_assets": list(movement.affected_assets),
        "undeclared_asset_scope": sorted(set(affected) - DECLARED),
        "undeclared_generated_scope": sorted(generated_paths),
        "reverse_dependency_scan": reverse_scan,
        "triggered_tokens": sorted(movement.triggered_tokens),
        "aspects": aspects,
        "identifier_interpretation": {
            name: {
                "scheme": old_parts[name].identity_scheme,
                "field": before[name]["baseline_control"]["identity"]["field"],
                "before": old_ids[name],
                "after": new_ids[name],
                "declaration_location": f"{name}.baseline_control",
            }
            for name in sorted(before)
        },
        "external_file_sha256_before": {
            path: digest(old_impl[path]) for path in sorted(targets)
        },
        "external_file_sha256_after": {
            path: digest(new_impl[path]) for path in sorted(targets)
        },
        "projection_sha256_before": {
            name: digest(old_projections[name]) for name in sorted(before)
        },
        "projection_sha256_after": {
            name: digest(new_projections[name]) for name in sorted(after)
        },
        "old_history_length": len(old_history),
        "old_history_last_record_sha256": digest(
            json.dumps(
                old_history[-1],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ),
        "candidate_history_length": len(
            after[AUTHORITY]["baseline_control"]["history"]
        ),
        "old_snapshot_count": len(old_snapshot_names),
        "new_snapshot_names": sorted(path.name for path in target_snapshots.iterdir()),
        "corpus_digest_before": json.loads(old_manifest)["corpus_inputs"]["digest"],
        "corpus_digest_after": corpus_digest,
        "corpus_input_files": manifest["corpus_inputs"]["files"],
        "corpus_input_trees": manifest["corpus_inputs"]["trees"],
        "pinned_prefix_history_record_count": (
            manifest["corpus_inputs"]["pinned_prefixes"]["history_record_count"]
        ),
        "pinned_prefix_snapshot_names": (
            manifest["corpus_inputs"]["pinned_prefixes"]["snapshot_names"]
        ),
        "candidate_file_sha256": {
            path.relative_to(output / "after").as_posix(): digest(path.read_bytes())
            for path in sorted((output / "after").rglob("*"))
            if path.is_file()
        },
        "before_file_sha256": {
            path.relative_to(output / "before").as_posix(): digest(path.read_bytes())
            for path in sorted((output / "before").rglob("*"))
            if path.is_file()
        },
    }
    write_patch(output)
    metadata["patch_sha256"] = digest((output / "candidate.patch").read_bytes())
    (output / "metadata.json").write_bytes(encode(metadata))
    print(
        "affected={} undeclared={} snapshots={} corpus={}".format(
            len(affected),
            len(metadata["undeclared_asset_scope"]),
            len(metadata["new_snapshot_names"]),
            corpus_digest,
        )
    )


def main() -> None:
    """正式入力の出所を確認し、再現可能な隔離候補を生成または検査する。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="現候補の鮮度・全bytesを照合"
    )
    options = parser.parse_args()
    previous_path = OUTPUT / "metadata.json"
    previous = (
        cast(dict[str, Any], json.loads(previous_path.read_bytes()))
        if previous_path.is_file()
        else None
    )
    with tempfile.TemporaryDirectory(prefix="pitchlog-step7-stage-") as directory:
        stage = Path(directory)
        generate(stage, previous, check=options.check)
        verify_patch_application(stage)
        publish_stage(stage, check=options.check)


if __name__ == "__main__":
    main()
