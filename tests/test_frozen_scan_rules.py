"""凍結基準候補の走査とallow-list遷移の正常系を検証する。"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frozen_scan_fixtures import (  # noqa: E402
    REPOSITORY_ROOT,
    assert_synthetic_scan_green,
    make_normal_scan_fixture,
    make_scan_entry,
    make_scan_root,
    write_scan_allowlist,
    write_scan_source,
)


def test_synthetic_scan_bootstrap_accepts_exact_pending_set(tmp_path: Path) -> None:
    """baseに台帳とallow-listが無い初回は残存4組のexact-setを許す。"""
    root = make_scan_root(tmp_path)
    pending_pairs = (
        (
            "backend/tests/db/authz/mutation_composition.py",
            "099a8fa20595c25f553b46de" + "dcaaa9660dd03c2e",
        ),
        (
            "scripts/check_docs_status.py",
            "523ecfd1db94c0c494b9b722b05cf4b3"
            + "c7d4562a1a6f2648fd9b76d5074a8e52",
        ),
        (
            "tests/test_check_authz_catalog.py",
            "56c281c409e972927940fad8" + "30aa38352df32f1e",
        ),
        (
            "tests/test_core_guard.py",
            "56c281c409e972927940fad8" + "30aa38352df32f1e",
        ),
    )
    entries = [
        make_scan_entry(path, value, pending_removal=True)
        for path, value in pending_pairs
    ]
    for path, value in pending_pairs:
        write_scan_source(root, path, f'VALUE = "{value}"\n')
    head_allowlist = root / "head-allowlist.json"
    write_scan_allowlist(head_allowlist, entries)

    assert_synthetic_scan_green(
        root,
        head_allowlist,
        occurrences=4,
        pairs=4,
    )


def test_synthetic_scan_normal_transition_accepts_inheritance_and_deletion(
    tmp_path: Path,
) -> None:
    """通常規則は同一継承とソース消去を伴うエントリ削除だけを許す。"""
    fixture = make_normal_scan_fixture(tmp_path)
    permanent_value = str(fixture.entries[0]["value"])
    write_scan_source(
        fixture.root,
        "scripts/permanent.py",
        "".join(f'VALUE_{index} = "{permanent_value}"\n' for index in range(5)),
    )

    assert_synthetic_scan_green(
        fixture.root,
        fixture.head_allowlist,
        occurrences=6,
        pairs=2,
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )

    (fixture.root / "tests/pending.py").unlink()
    write_scan_allowlist(fixture.head_allowlist, fixture.entries[:1])
    assert_synthetic_scan_green(
        fixture.root,
        fixture.head_allowlist,
        occurrences=5,
        pairs=1,
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )


def test_synthetic_scan_covers_check_docs_status_64_digit_digest(
    tmp_path: Path,
) -> None:
    """64桁走査がcheck_docs_statusの免除digestを合成fixtureで検出する。"""
    root = make_scan_root(tmp_path)
    path_text = "scripts/check_docs_status.py"
    source_path = REPOSITORY_ROOT / path_text
    destination = root / path_text
    destination.write_bytes(source_path.read_bytes())
    digest = (
        "523ecfd1db94c0c494b9b722b05cf4b3"
        + "c7d4562a1a6f2648fd9b76d5074a8e52"
    )
    entries = [make_scan_entry(path_text, digest, pending_removal=False)]
    base_allowlist = root / "base-allowlist.json"
    head_allowlist = root / "head-allowlist.json"
    write_scan_allowlist(base_allowlist, copy.deepcopy(entries))
    write_scan_allowlist(head_allowlist, entries)

    assert_synthetic_scan_green(
        root,
        head_allowlist,
        occurrences=1,
        pairs=1,
        base_allowlist=base_allowlist,
        base_ledger_present=True,
    )
