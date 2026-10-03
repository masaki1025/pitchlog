"""凍結基準候補の走査とallow-list遷移に対する負例を固定する。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frozen_scan_fixtures import (  # noqa: E402
    CHANGED_VALUE,
    EMBEDDED_VALUE,
    PENDING_VALUE,
    PERMANENT_VALUE,
    assert_normal_scan_baseline_green,
    assert_synthetic_scan_red,
    make_normal_scan_fixture,
    make_scan_entry,
    write_scan_allowlist,
    write_scan_source,
)


@pytest.mark.frozen_negative
def test_added_allowlist_entry_is_red(tmp_path: Path) -> None:
    """N23: 通常遷移でallow-listへエントリを追加できない。"""
    fixture = make_normal_scan_fixture(tmp_path)
    assert_normal_scan_baseline_green(fixture)
    path_text = "tests/added.py"
    write_scan_source(fixture.root, path_text, f'VALUE = "{CHANGED_VALUE}"\n')
    fixture.entries.append(
        make_scan_entry(
            path_text,
            CHANGED_VALUE,
            pending_removal=False,
            reason="変異で追加した項目",
        )
    )
    write_scan_allowlist(fixture.head_allowlist, fixture.entries)

    assert_synthetic_scan_red(
        fixture.root,
        fixture.head_allowlist,
        "allow-list通常規則: エントリ追加は禁止: "
        f"[({path_text}, {CHANGED_VALUE})]",
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )


@pytest.mark.frozen_negative
def test_changed_allowlist_value_is_red(tmp_path: Path) -> None:
    """N24: pendingエントリの値を別の基準へすり替えられない。"""
    fixture = make_normal_scan_fixture(tmp_path)
    assert_normal_scan_baseline_green(fixture)
    path_text = str(fixture.entries[1]["path"])
    fixture.entries[1]["value"] = CHANGED_VALUE
    write_scan_source(fixture.root, path_text, f'VALUE = "{CHANGED_VALUE}"\n')
    write_scan_allowlist(fixture.head_allowlist, fixture.entries)

    assert_synthetic_scan_red(
        fixture.root,
        fixture.head_allowlist,
        "allow-list通常規則: エントリ追加は禁止: "
        f"[({path_text}, {CHANGED_VALUE})]",
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )


@pytest.mark.frozen_negative
def test_changed_allowlist_path_is_red(tmp_path: Path) -> None:
    """N25: pendingエントリのパスを別の場所へすり替えられない。"""
    fixture = make_normal_scan_fixture(tmp_path)
    assert_normal_scan_baseline_green(fixture)
    old_path = fixture.root / str(fixture.entries[1]["path"])
    old_path.unlink()
    path_text = "scripts/moved.py"
    fixture.entries[1]["path"] = path_text
    write_scan_source(fixture.root, path_text, f'VALUE = "{PENDING_VALUE}"\n')
    write_scan_allowlist(fixture.head_allowlist, fixture.entries)

    assert_synthetic_scan_red(
        fixture.root,
        fixture.head_allowlist,
        "allow-list通常規則: エントリ追加は禁止: "
        f"[({path_text}, {PENDING_VALUE})]",
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )


@pytest.mark.frozen_negative
def test_permanent_entry_cannot_become_pending_is_red(tmp_path: Path) -> None:
    """N26: 恒久項目のpending_removalをfalseからtrueへ変えられない。"""
    fixture = make_normal_scan_fixture(tmp_path)
    assert_normal_scan_baseline_green(fixture)
    fixture.entries[0]["pending_removal"] = True
    write_scan_allowlist(fixture.head_allowlist, fixture.entries)
    path_text = str(fixture.entries[0]["path"])

    assert_synthetic_scan_red(
        fixture.root,
        fixture.head_allowlist,
        "allow-list通常規則: pending_removal false→trueは禁止: "
        f"[({path_text}, {PERMANENT_VALUE})]",
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )


@pytest.mark.frozen_negative
def test_pending_entry_cannot_become_permanent_is_red(tmp_path: Path) -> None:
    """N27: 直書きを残してpending_removalをtrueからfalseへ変えられない。"""
    fixture = make_normal_scan_fixture(tmp_path)
    assert_normal_scan_baseline_green(fixture)
    fixture.entries[1]["pending_removal"] = False
    write_scan_allowlist(fixture.head_allowlist, fixture.entries)
    path_text = str(fixture.entries[1]["path"])

    assert_synthetic_scan_red(
        fixture.root,
        fixture.head_allowlist,
        "allow-list通常規則: pending_removal true→falseは禁止: "
        f"[({path_text}, {PENDING_VALUE})]",
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )


@pytest.mark.frozen_negative
def test_embedded_docstring_and_fstring_values_are_red(tmp_path: Path) -> None:
    """N28: docstringとf-stringへ埋め込んだ未登録値も本文走査で拒否する。"""
    fixture = make_normal_scan_fixture(tmp_path)
    assert_normal_scan_baseline_green(fixture)
    path_text = "tests/embedded.py"
    write_scan_source(
        fixture.root,
        path_text,
        f'"""docstring prefix {CHANGED_VALUE} suffix。"""\n'
        f'TEXT = f"f-string prefix {EMBEDDED_VALUE} suffix"\n',
    )

    assert_synthetic_scan_red(
        fixture.root,
        fixture.head_allowlist,
        "走査で見つかったがallow-listにない(path, value): "
        f"[({path_text}, {CHANGED_VALUE}), ({path_text}, {EMBEDDED_VALUE})]",
        base_allowlist=fixture.base_allowlist,
        base_ledger_present=True,
    )
