"""ステップ7の未受理候補を既存凍結関数で再生成する。"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

import frozen_history as history
import runner

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).resolve().parent

CI = ".github/workflows/ci.yml"
MANIFEST = "tests/fixtures/frozen-archive-cases/manifest.json"
AUTHORITY = "contracts/tenant_boundary/base-allowlist.json"
DECLARED = {AUTHORITY, "contracts/tenant_boundary/census-baseline.json"}
CI_NEEDLE = "      - run: pnpm test -- --run\n"
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
      - run: docker pull postgres:17.11-bookworm
        working-directory: .
      - run: pnpm exec playwright install --with-deps chromium
      - run: pnpm run test:browser
"""


def encode(value: object) -> bytes:
    """資産の既存 JSON 書式で候補を保存する。"""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def digest(value: bytes) -> str:
    """ファイル・既存射影の SHA-256 を表示する。"""
    return hashlib.sha256(value).hexdigest()


def save_pair(path: str, old: bytes, new: bytes) -> None:
    """元ファイルの bytes と候補 bytes を別々に固定する。"""
    for stage, content in (("before", old), ("after", new)):
        target = OUTPUT / stage / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def write_patch() -> None:
    """前後ファイルと新snapshotから適用可能な統一patchを作る。"""
    chunks: list[str] = []

    def append_lines(lines: Iterable[str]) -> None:
        for line in lines:
            if line.endswith("\n"):
                chunks.append(line)
            else:
                chunks.extend((line + "\n", "\\ No newline at end of file\n"))

    for candidate in sorted((OUTPUT / "after").rglob("*")):
        if not candidate.is_file():
            continue
        name = candidate.relative_to(OUTPUT / "after").as_posix()
        old = (OUTPUT / "before" / name).read_text().splitlines(keepends=True)
        new = candidate.read_text().splitlines(keepends=True)
        chunks.append(f"diff --git a/{name} b/{name}\n")
        append_lines(
            difflib.unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}")
        )
    for snapshot in sorted((OUTPUT / "new-snapshots").iterdir()):
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
    (OUTPUT / "candidate.patch").write_text("".join(chunks))


def state(
    assets: dict[str, object], implementations: dict[str, bytes], location: str
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


def main() -> None:
    """未宣言波及も含む前後候補と検査用メタデータを作る。"""
    before = {
        path.relative_to(ROOT).as_posix(): json.loads(path.read_bytes())
        for path in sorted((ROOT / "contracts/tenant_boundary").glob("*.json"))
    }
    after = copy.deepcopy(before)
    old_ci = (ROOT / CI).read_bytes()
    assert old_ci.count(CI_NEEDLE.encode()) == 1
    new_ci = old_ci.replace(CI_NEEDLE.encode(), (CI_NEEDLE + CI_ADDITION).encode())
    save_pair(CI, old_ci, new_ci)

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
            source = {key: value for key, value in candidate.items() if key != "source_digest"}
            candidate["source_digest"] = digest(
                json.dumps(
                    source, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            )
    assert len(affected) == 8

    targets = {
        path
        for asset in before.values()
        for path in asset["baseline_control"]["identity"]["frozen_projection"]["external_files"]
    }
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
    old_ids = {name: list(old_parts[name].current_identifiers) for name in sorted(before)}
    new_ids = {name: list(new_parts[name].current_identifiers) for name in sorted(after)}
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
        save_pair(name, (ROOT / name).read_bytes(), encode(after[name]))

    snapshot_root = ROOT / "contracts/tenant_boundary/history-snapshots"
    old_snapshot_names = {path.name for path in snapshot_root.iterdir() if path.is_file()}
    snapshot_content = {
        digest(content): content
        for values in (old_impl, new_impl, old_projections, new_projections)
        for content in values.values()
    }
    target_snapshots = OUTPUT / "new-snapshots"
    target_snapshots.mkdir(exist_ok=True)
    for item in (
        old_state["external_snapshots"]
        + old_state["asset_snapshots"]
        + new_state["external_snapshots"]
        + new_state["asset_snapshots"]
    ):
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
    save_pair(MANIFEST, old_manifest, encode(manifest))

    old_history = before[AUTHORITY]["baseline_control"]["history"]
    metadata = {
        "status": "未受理",
        "source_git_base": "8e4698f6dc254439b7d5e0c273cc2aef70cda657",
        "candidate_checkout_head": "a6f9783670d3eeb044b86d49ca61937d63829160",
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
        "external_file_sha256_before": {path: digest(old_impl[path]) for path in sorted(targets)},
        "external_file_sha256_after": {path: digest(new_impl[path]) for path in sorted(targets)},
        "projection_sha256_before": {
            name: digest(old_projections[name]) for name in sorted(before)
        },
        "projection_sha256_after": {name: digest(new_projections[name]) for name in sorted(after)},
        "old_history_length": len(old_history),
        "old_history_last_record_sha256": digest(
            json.dumps(
                old_history[-1],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ),
        "candidate_history_length": len(after[AUTHORITY]["baseline_control"]["history"]),
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
            path.relative_to(OUTPUT / "after").as_posix(): digest(path.read_bytes())
            for path in sorted((OUTPUT / "after").rglob("*"))
            if path.is_file()
        },
    }
    (OUTPUT / "metadata.json").write_bytes(encode(metadata))
    write_patch()
    print(
        f"affected={len(affected)} undeclared={len(metadata['undeclared_asset_scope'])} "
        f"snapshots={len(metadata['new_snapshot_names'])} corpus={corpus_digest}"
    )


if __name__ == "__main__":
    main()
