"""同期プロトコル設計の伝播突合検査を検証する。"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_design_propagation.py"
INVARIANT_EVALUATOR_SCRIPT = REPOSITORY_ROOT / "scripts" / "doc_check_invariants.py"
FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "sync-protocol-source.txt"
STRUCTURAL_REASON_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "structural-reasons-expected.json"
)
DESIGN = REPOSITORY_ROOT / "docs" / "design" / "sync-protocol.md"
REQUIREMENTS = (
    REPOSITORY_ROOT / "docs" / "requirements" / "requirements-pitchlog-2026-07-22.md"
)
PROFILE = (
    REPOSITORY_ROOT
    / "scripts"
    / "design_relations"
    / "profiles"
    / "sync-protocol.json"
)
SAMPLE_PROFILE = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "profile-sample"
    / "profiles"
    / "data-model-like.json"
)

P3_RESULTS = (
    "変更受理",
    "B8:期待版不一致",
    "B9:記録権不保持",
    "B10:一時障害",
    "B11:認証失効",
    "B12:認可・テナント不一致",
    "B13:D5衝突",
    "B14:変更内容拒否",
)
STEP38_P3_ORDER_ELEMENTS = (
    "I1:P3のD5照合位置=③認可後+RG1後+復旧世代照合後+V12前+V11前",
    "I2:P3の既存D5・同一内容=保存済み結果を再掲+再適用しない",
    "I3:P3の既存D5・異なる内容=B13",
    "I4:P3の未使用D5=現復旧世代+V12・V11照合対象",
)
STEP37_P3_INVALIDATION_ELEMENTS = (
    "I5:P3の無効化発火=未使用D5の変更受理でT7に無効化意図を永続化+"
    "配信完了まで冪等再試行+保存済み結果再掲では意図を重複作成しない",
)
STEP38_P3_RETENTION_ELEMENTS = (
    "I6:P3受理結果の端末保持=端末永続化まで成立した対象参照+V11の版+D5+"
    "確定内容+accepted_atを起点+同期済みと同じ24時間保持+"
    "保存済み結果の再掲で延長しない+サーバー確定から端末永続化まで保護なし+"
    "RG1中は自動破棄停止+退避・閲覧・書き出し対象+復元規則なし",
)
STEP38_RECOVERY_GATE_ELEMENTS = (
    "RG1:復元調整中のfail-closed共通ゲート=③認可後+D5照合前+"
    "全通常書き込み・内部ジョブ停止+P1・P2・P4・通常/緊急引き継ぎはB7+"
    "P3はB10+D5消費なし+コミット直前再検証+サービス再開fail-closed+"
    "解除・新D4開始不可分+復旧制御面だけ許可",
)
STEP37_V12_RECOVERY_ELEMENT = (
    "VF6:V12の復旧世代結合=現D4+現復旧世代+保持端末"
)
STEP37_T7_ELEMENT = "T7:V11照合・対象確定版更新・無効化意図保存"
STEP32_B3_BRANCH_ELEMENTS = (
    "B3a:未使用D5の内容拒否=P5+T9",
    "B3b:既存D5との衝突=先着原本との比較+B3+T9開始なし",
)
STEP32_D1_D5_ELEMENTS = (
    "DI1:D1付き経路のD5照合位置=③認可後+V12前",
    "DI2:D1付き経路の既存D5・同一内容=保存済み結果を再掲+再適用しない",
    "DI3:D1付き経路の既存D5・異なる内容=B3b",
    "DI4:D1付き経路の未使用D5=V12・prefix・内容検査対象",
    "DI5:混在バッチのA5=D5内部先行分類+既存同一D5は保存済み結果候補+"
    "既存異内容D5はB3b候補+未使用D5は後段結果候補+"
    "外部はD1昇順の最初のB2・B3+以降は事前分類済みB3bを含め未処理+同一ACK",
)
STEP40_TEMP_ID_ELEMENTS = (
    "C1:選手登録イベント+一時ID+正式ID+写像を返す",
    "C2:後続イベントの参照+同じ正式ID+決定的に解決",
    "C3:ACK消失後の再送+別の正式ID+重複生成しない",
    "C4:写像が確定するまで+同期済みとして扱わない",
)
STEP40_ORDER_ELEMENTS = (
    "O1:D2の採番・再採番+原子的な操作+直列化",
    "O2:隙間が尽きたとき+同じ原子的操作+局所再採番",
    "O4:永続化済みの同値+B3+A5の拒否+要操作+自動再送を止める",
)
STEP40_CHANGE_ELEMENTS = (
    "W1:確定済みイベントの修正・削除+新しい変更イベントとして追記+"
    "既存イベントを書き換えない",
    "W2:D6墓標・D7改訂+確定済みイベントの修正・削除に流用しない",
    "W3:P3+D1+持たない",
    "W3-a:V11+対象の期待版+一致するときだけ受理+対象の確定版を進める",
    "W3-b:変更版順+D1+D2+別の順序+論理再生順に使わない",
    "W3-c:P3+prefixコミットの対象外+欠番検知が要らない",
    "W4:進行中の変更操作ではV12を照合+終了後の変更操作ではV12を前提にしない",
)
STEP40_EVENT_FIELD_ELEMENTS = (
    "V1:べき等キーD5+全イベントで無条件",
    "V2:イベント連番D1+P1・P2・P4に必須+P3は持たない",
    "V3:記録権世代D4+P1・P2・P4に必須+P3は持たず",
    "V4:試合の識別+全イベントで無条件",
    "V5:イベント種別+全イベントで無条件",
    "V6:論理位置を定める値D2+種別条件付き+P3自身は持たず",
    "V7:ペイロード+全イベントで無条件",
    "V8:状態差分+取消可能な操作に限る+P3は持たない",
    "V9:置換・墓標の状態+墓標・改訂に限る+P3は持たない",
    "V10:対象イベントの参照+種別条件付き+P3は必須",
    "V11:対象の期待版+P3に必須",
    "V12:記録権証明+要求レベル+P1・P2・P4+進行中のP3+終了後のP3には不要",
)


def _load_checker() -> Any:
    """テスト対象をsys.pathの変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(
        "check_design_propagation_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _load_invariant_evaluator() -> Any:
    """宣言評価器をsys.pathの変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(
        "doc_check_invariants_under_test",
        INVARIANT_EVALUATOR_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


invariant_evaluator = _load_invariant_evaluator()


@pytest.fixture(scope="module")
def manifest() -> dict[str, checker.ManifestRelation]:
    """検査用に実マニフェストを読む。"""
    return checker.load_manifest(REPOSITORY_ROOT / checker.DEFAULT_MANIFEST)


@pytest.fixture(scope="module")
def defects() -> dict[str, checker.Defect]:
    """検査用に実欠陥oracleを読む。"""
    return checker.load_defects(REPOSITORY_ROOT / checker.DEFAULT_DEFECTS)


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _finding_ids(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {
        line.split(":", 1)[0]
        for line in result.stderr.splitlines()
        if ": [" in line
    }


def _write_json(path: Path, value: Any) -> None:
    """CLI負例用のJSONをUTF-8で書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_sample_profile() -> Any:
    """データモデル型サンプルプロファイルを読む。"""
    return checker.doc_check_profile.load_profile(
        SAMPLE_PROFILE,
        root=REPOSITORY_ROOT,
        schema_dir=REPOSITORY_ROOT / "scripts/design_relations/schemas",
    )


def _sample_check_inputs() -> tuple[Any, Any, str, dict[str, Any], Any]:
    """新検査の適合サンプル入力一式を返す。"""
    profile = _load_sample_profile()
    assets = checker.doc_check_profile.load_assets(profile)
    text = profile.document.read_text(encoding="utf-8")
    raw_manifest = checker.doc_check_profile.load_json(profile.manifest)
    invariants = checker.doc_check_profile.load_invariants(
        profile.invariants,
        schema_dir=profile.schema_dir,
    )
    return profile, assets, text, raw_manifest, invariants


def _replace_sample_asset(
    profile: Any,
    tmp_path: Path,
    asset_name: str,
    value: Any,
) -> Any:
    """合成資産1本を一時JSONに差し替えたProfileを返す。"""
    asset_path = tmp_path / f"{asset_name}.json"
    _write_json(asset_path, value)
    raw = json.loads(json.dumps(profile.raw))
    raw["assets"][asset_name]["path"] = str(asset_path)
    return replace(profile, raw=raw)


def _make_staging_registry(tmp_path: Path, document: Path) -> Path:
    """文書だけを差し替えた外部stagingレジストリを作る。"""
    profiles_dir = tmp_path / "profiles"
    profile_path = profiles_dir / "x.json"
    profile_value = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_value["name"] = "x"
    profile_value["document"] = str(document.resolve())
    _write_json(profile_path, profile_value)

    gating = {
        key: profile_value[key]
        for key in checker.doc_check_profile.GATING_KEYS
        if key in profile_value
    }
    registry = {
        "schema_version": 1,
        "profiles": [
            {
                "name": "x",
                "file": str(profile_path.resolve()),
                "document": str(document.resolve()),
                "must_require": profile_value["required_checks"],
                "pins": {
                    "profile_gating_digest": (
                        checker.doc_check_profile.canonical_digest(gating)
                    ),
                    "invariants_digest": checker.doc_check_profile.canonical_digest(
                        checker.doc_check_profile.load_json(
                            REPOSITORY_ROOT / profile_value["invariants"]
                        )
                    ),
                    "asset_digests": {},
                },
            }
        ],
    }
    registry_path = profiles_dir / "registry.json"
    _write_json(registry_path, registry)
    return registry_path


def _corpus_document(sections: dict[str, tuple[str, ...]]) -> str:
    """節IDと本文行から構造corpus用Markdownを組み立てる。"""
    return "".join(
        f"### {section_id}. corpus\n" + "".join(f"{line}\n" for line in lines)
        for section_id, lines in sections.items()
    )


def _replace_in_section(text: str, section_id: str, old: str, new: str) -> str:
    """指定節に最初に現れる文字列だけを置換する。"""
    section = checker._heading_section(text, section_id)
    assert old in section, f"{section_id} に置換対象がない: {old}"
    changed_section = section.replace(old, new, 1)
    return text.replace(section, changed_section, 1)


def _element_row(element: str) -> str:
    """manifest要素を同じ行にIDと意味部がある表行へ変換する。"""
    identifier, separator, description = element.partition(":")
    if separator:
        return f"| {identifier} | {description} |"
    return f"| 要素 | {element} |"


def _route_row(route: str, elements: frozenset[str]) -> str:
    """経路IDとmanifest由来のT要素集合から表行を作る。"""
    ordered = sorted(elements, key=lambda element: int(element.removeprefix("T")))
    return f"| {route} | {'・'.join(ordered)} |"


def _build_structural_check_cases(
    manifest: dict[str, checker.ManifestRelation],
) -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    """実manifestから構造宣言15件の正常・異常・変異corpusを作る。"""
    routes = invariant_evaluator.expected_route_elements(
        manifest, "R-TXN-ROUTE", prefix="T"
    )

    sp01_valid = _corpus_document(
        {
            "6-3": ("| B4 | A5 が退避を返す |",),
            "7-1": (),
            "7-2": ("| 未送信 → 退避済み | ACK の A5 が退避を返す |",),
        }
    )
    sp01_invalid = _replace_in_section(
        sp01_valid, "6-3", "| B4 | A5 が退避を返す |", "| B4 | 退避を返す |"
    )
    sp01_selector_mutation = _replace_in_section(
        sp01_valid,
        "7-2",
        "| 未送信 → 退避済み | ACK の A5 が退避を返す |",
        "| 未送信 | ACK の A5 が退避を返す |\n| 別状態 | 退避済み |",
    )
    sp01_row_mutation = _replace_in_section(
        sp01_valid,
        "6-3",
        "| B4 | A5 が退避を返す |",
        "| B4 | 応答を返す |\n| 補足 | A5 の退避 |",
    )
    sp01_boundary_selector_mutation = _replace_in_section(
        sp01_valid,
        "6-3",
        "| B4 | A5 が退避を返す |",
        "| 境界 | B4 | A5 が退避を返す |",
    )

    ack_elements = manifest["R-ACK-STATE"].source_elements
    ack_source_row = f"| A5 | {'・'.join(ack_elements)} |"
    sp02_valid = _corpus_document(
        {
            "6-3": tuple(
                f"| 境界-{index} | {element} |"
                for index, element in enumerate(ack_elements, start=1)
            ),
            "7-1": (ack_source_row,),
            "7-2": tuple(
                f"| 遷移-{index} | {element} |"
                for index, element in enumerate(ack_elements, start=1)
            ),
        }
    )
    sp02_invalid = _replace_in_section(
        sp02_valid, "7-2", f"| 遷移-1 | {ack_elements[0]} |", "| 遷移-1 | 欠落 |"
    )
    sp02_selector_mutation = _replace_in_section(
        sp02_valid,
        "7-1",
        ack_source_row,
        f"| ACK | A5 |\n| 結果集合 | {'・'.join(ack_elements)} |",
    )
    sp02_row_mutation = _replace_in_section(
        sp02_valid,
        "7-1",
        ack_source_row,
        f"| A5 | {'・'.join(ack_elements[:-1])} |\n| 補足 | {ack_elements[-1]} |",
    )
    sp02_section_mutation = _replace_in_section(
        sp02_valid,
        "6-3",
        f"| 境界-{len(ack_elements)} | {ack_elements[-1]} |",
        "| 境界外へ移動 | 欠落 |",
    )

    queue_elements = manifest["R-QUEUE-LIFE"].source_elements
    queue_rows = tuple(_element_row(element) for element in queue_elements)
    queue_semantic = next(element for element in queue_elements if element.startswith("I6:"))
    sp03_valid = _corpus_document(
        {"6-3": queue_rows, "7-2": queue_rows, "9-5": queue_rows}
    )
    sp03_invalid = _replace_in_section(
        sp03_valid, "6-3", _element_row(queue_elements[0]), "| 状態 | 欠落 |"
    )
    sp03_section_mutation = _replace_in_section(
        sp03_valid, "6-3", _element_row(queue_elements[1]), "| 状態 | 別節へ移動 |"
    )
    sp03_meaning_mutation = _replace_in_section(
        sp03_valid, "6-3", _element_row(queue_semantic), "| I6 | 意味部欠落 |"
    )

    route_rows = tuple(_route_row(route, routes[route]) for route in ("P1", "P2", "P3"))
    sp06_valid = _corpus_document(
        {"8-1": route_rows, "10-2": route_rows, "11-2": route_rows}
    )
    sp06_invalid = _replace_in_section(
        sp06_valid, "8-1", _route_row("P3", routes["P3"]), "| P3 | T1・T2 |"
    )
    sp06_id_mutation = _replace_in_section(
        sp06_valid,
        "10-2",
        _route_row("P1", routes["P1"]),
        _route_row("P1", routes["P1"]).replace("T6", "T8"),
    )

    p4_route_row = _route_row("P4", routes["P4"])
    sp07_valid = _corpus_document(
        {
            "8-1": (p4_route_row,),
            "9-2": ("| P4 | 旧世代・退避・B4・原子性 |",),
            "10-2": ("| P4 | 退避・B4・原子性 |",),
            "11-2": ("| P4 | 退避・B4 |",),
        }
    )
    sp07_invalid = _replace_in_section(
        sp07_valid, "10-2", "| P4 | 退避・B4・原子性 |", "| P4 | 退避・B4 |"
    )
    sp07_selector_mutation = _replace_in_section(
        sp07_valid, "8-1", p4_route_row, "| 経路 | P4 |\n| 処理 | T8 |"
    )
    sp07_id_mutation = _replace_in_section(
        sp07_valid, "8-1", p4_route_row, p4_route_row.replace("T8", "T9")
    )

    t6_element = next(
        element
        for element in manifest["R-TXN-ROUTE"].source_elements
        if element.startswith("T6:")
    )
    t6_row = _element_row(t6_element)
    t6_semantic = t6_element.split(":", 1)[1]
    sp08_valid = _corpus_document(
        {
            "4-4": ("一時 ID の写像を保存する。",),
            "7-1": ("D5 ごとの確定結果を保存する。",),
            "8-1": (t6_row, *route_rows),
        }
    )
    sp08_invalid = _replace_in_section(
        sp08_valid,
        "7-1",
        "D5 ごとの確定結果を保存する。",
        "D5 ごとの結果を保存する。",
    )
    sp08_lookup_mutation = _replace_in_section(
        sp08_valid,
        "8-1",
        t6_row,
        f"| T6 | 保存要素 |\n| 補足 | {t6_semantic} |",
    )
    sp08_id_mutation = _replace_in_section(
        sp08_valid,
        "8-1",
        _route_row("P1", routes["P1"]),
        _route_row("P1", routes["P1"]).replace("T6", "T8"),
    )
    sp08_section_mutation = _replace_in_section(
        sp08_valid, "4-4", "一時 ID の写像を保存する。", "一時 ID を保存する。"
    )
    sp08_section_mutation = _replace_in_section(
        sp08_section_mutation,
        "7-1",
        "D5 ごとの確定結果を保存する。",
        "D5 ごとの確定結果を保存する。\n写像の説明はこの節へ移す。",
    )

    p3_route_row = _route_row("P3", routes["P3"])
    sp09_valid = _corpus_document(
        {
            "4-3-A": ("W3 は D1 を持たない変更イベントを定める。",),
            "5-5": ("P3 は従属区分である。",),
            "8-1": ("| T5 | 局所再採番 |", p3_route_row),
        }
    )
    sp09_invalid = _replace_in_section(
        sp09_valid, "8-1", p3_route_row, p3_route_row.replace("T7", "T5")
    )
    sp09_selector_mutation = _replace_in_section(
        sp09_valid, "8-1", p3_route_row, p3_route_row.replace("| P3 |", "| 経路 | **P3** |")
    )
    sp09_t5_mutation = _replace_in_section(
        sp09_valid, "8-1", "| T5 | 局所再採番 |\n", ""
    )
    sp09_t5_mutation = _replace_in_section(
        sp09_t5_mutation,
        "8-1",
        p3_route_row,
        p3_route_row.replace("T7", "T5"),
    )
    sp09_any_of_mutation = _replace_in_section(
        sp09_valid,
        "8-1",
        p3_route_row,
        f"{p3_route_row.replace('T7', '')}\n| T7 | 別の行へ移動 |",
    )
    sp09_id_mutation = _replace_in_section(
        sp09_valid, "8-1", p3_route_row, p3_route_row.replace("T7", "T8")
    )

    sp10_valid = _corpus_document(
        {
            "4-3-A": (),
            "6-3": (),
            "7-1": ("| P3 | 独立した応答契約 |",),
            "8-1": ("| P3 | 変更イベント経路 |",),
        }
    )
    sp10_invalid = _replace_in_section(
        sp10_valid, "7-1", "| P3 | 独立した応答契約 |", "| P3 | 独立した通知契約 |"
    )
    sp10_route_selector_mutation = _replace_in_section(
        sp10_valid, "8-1", "| P3 | 変更イベント経路 |", "| 経路 | **P3** | 変更イベント |"
    )
    sp10_response_selector_mutation = _replace_in_section(
        sp10_valid,
        "7-1",
        "| P3 | 独立した応答契約 |",
        "| P3 | 独立契約 |\n| 補足 | 応答 |",
    )

    sp11_valid = _corpus_document(
        {
            "4-3-A": (),
            "6-2": ("| 結果 | 期待版不一致 |",),
            "6-3": ("| 結果 | 期待版不一致 |",),
            "8-3": ("| 結果 | 期待版不一致 |",),
        }
    )
    sp11_invalid = _replace_in_section(
        sp11_valid, "8-3", "| 結果 | 期待版不一致 |", "| 結果 | 通知なし |"
    )
    sp11_selector_mutation = _replace_in_section(
        sp11_valid, "6-2", "| 結果 | 期待版不一致 |", "期待版不一致は表外の別行へ移す。"
    )

    exclusion = "D1 を持たない変更イベントの D5 衝突は対象外"
    sp12_valid = _corpus_document(
        {
            "4-4": ("経路別 D5 衝突を定める。",),
            "6-3": (f"| B3 | {exclusion} |",),
            "6-4": (f"| 再開2択 | {exclusion} |",),
        }
    )
    sp12_invalid = _replace_in_section(
        sp12_valid,
        "6-3",
        f"| B3 | {exclusion} |",
        "| B3 | D1 を持たない変更イベントの D5 衝突 |",
    )
    sp12_boundary_selector_mutation = _replace_in_section(
        sp12_valid,
        "6-3",
        f"| B3 | {exclusion} |",
        f"| 境界 | B3 | {exclusion} |",
    )
    sp12_exclusion_mutation = _replace_in_section(
        sp12_valid,
        "6-3",
        f"| B3 | {exclusion} |",
        "| B3 | D1 を持たない変更イベントの D5 衝突 |\n| 補足 | 対象外 |",
    )
    sp12_row_selector_mutation = _replace_in_section(
        sp12_valid,
        "6-4",
        f"| 再開2択 | {exclusion} |",
        "| 再開2択 | D1 を持たない変更イベント |\n| 補足 | D5 衝突は対象外 |",
    )

    event_elements = manifest["R-EVENT-FIELD"].source_elements
    event_rows = tuple(_element_row(element) for element in event_elements)
    sp13_valid = _corpus_document(
        {
            "4-3": event_rows,
            "4-3-A": event_rows,
            "6-2": (),
            "7-1": (),
            "11-2": event_rows,
        }
    )
    sp13_invalid = _replace_in_section(
        sp13_valid, "4-3", _element_row(event_elements[-1]), "| V12-欠落 | 定義なし |"
    )
    sp13_section_mutation = _replace_in_section(
        sp13_valid, "4-3-A", _element_row(event_elements[1]), "| V2-移動 | 別節にのみ存在 |"
    )
    sp13_meaning_mutation = _replace_in_section(
        sp13_valid,
        "11-2",
        _element_row(event_elements[2]),
        "| V3 | 記録権世代 D4 の意味部が欠落 |",
    )

    sp14_valid = _corpus_document(
        {
            "4-3-A": ("| W3-a | 期待版一致 |", "| W3-b | 変更版順 |"),
            "5-5": ("| 変更版順 | D1・D2 とは別で論理再生順に使わない |",),
            "11-2": ("| 変更版順 | D1・D2 とは別で論理再生順に使わない |",),
        }
    )
    sp14_invalid = _replace_in_section(
        sp14_valid, "4-3-A", "| W3-b | 変更版順 |", "| 規則 | 変更版順 |"
    )
    sp14_section_mutation = _replace_in_section(
        sp14_valid,
        "5-5",
        "| 変更版順 | D1・D2 とは別で論理再生順に使わない |",
        "| 処理順 | D1・D2 とは別で論理再生順に使わない |",
    )
    sp14_meaning_mutation = _replace_in_section(
        sp14_valid,
        "11-2",
        "| 変更版順 | D1・D2 とは別で論理再生順に使わない |",
        "| 変更版順 | D1・D2 とは別である |",
    )

    prefix_exclusion = "D1 を持たない変更イベントは prefix の対象外である。"
    sp16_valid = _corpus_document(
        {
            "2-4": (),
            "4-3-A": ("変更イベント規則。",),
            "6-1": (prefix_exclusion,),
            "6-2": (prefix_exclusion,),
            "8-1": (),
        }
    )
    sp16_invalid = _replace_in_section(
        sp16_valid,
        "6-2",
        prefix_exclusion,
        "D1 を持たない変更イベントの prefix を説明する。",
    )
    sp16_section_mutation = _replace_in_section(
        sp16_valid, "6-1", prefix_exclusion, "prefix の算出手順を定める。"
    )
    sp16_section_mutation = _replace_in_section(
        sp16_section_mutation,
        "4-3-A",
        "変更イベント規則。",
        f"変更イベント規則。\n{prefix_exclusion}",
    )

    sp18_valid = _corpus_document(
        {
            "4-3-A": (
                "説明文の ** は表外なので検査対象にしない。",
                "| W3 | **対象の D2 に従う** |",
            )
        }
    )
    sp18_invalid = _replace_in_section(
        sp18_valid, "4-3-A", "| W3 | **対象の D2 に従う** |", "| W3 | **対象の D2 に従う |"
    )
    sp18_two_odd_rows_mutation = _corpus_document(
        {"4-3-A": ("| W3 | **対象の D2 に従う |", "| W4 | **記録権を照合する |")}
    )
    sp18_header_mutation = _corpus_document(
        {"4-3-A": ("| **規則 | 内容 |", "| --- | --- |", "| W3 | **対象** |")}
    )

    d1_definition = (
        "| D1 | 同期連番 | 用途は順序と欠落の判定・undo の逆順。"
        "再送の重複排除は D5 の用途であり、D1 の用途ではない。 |"
    )
    d1_role = "| イベント連番 | D1 | 順序と欠落の判定 |"
    d5_role = "| べき等キー | D5 | 再送の二重適用を防ぐ |"
    sp20_valid = _corpus_document(
        {"2-1": (d1_definition,), "4-2": (d5_role, d1_role)}
    )
    sp20_invalid = _replace_in_section(
        sp20_valid,
        "2-1",
        d1_definition,
        "| D1 | 同期連番 | 用途は欠落の判定と undo の逆順に限る。 |",
    )
    sp20_definition_selector_mutation = _replace_in_section(
        sp20_valid,
        "2-1",
        d1_definition,
        d1_definition.replace("| D1 |", "| 識別子 | **D1** |"),
    )
    sp20_role_selector_mutation = _replace_in_section(
        sp20_valid,
        "4-2",
        d1_role,
        "| イベント連番 | D1 | 順序の判定 |\n| 補足 | 欠落の判定 |",
    )
    sp20_row_mutation = _replace_in_section(
        sp20_valid,
        "2-1",
        d1_definition,
        d1_definition.replace("・undo の逆順", "") + "\n| 補足 | undo の逆順 |",
    )
    sp20_conditional_mutation = _replace_in_section(
        sp20_valid,
        "2-1",
        d1_definition,
        d1_definition.replace("D5 の用途であり、", "") + "\n| D5 | D5 の用途 |",
    )

    return (
        (
            "SP-01",
            sp01_valid,
            sp01_invalid,
            (
                sp01_selector_mutation,
                sp01_row_mutation,
                sp01_boundary_selector_mutation,
            ),
        ),
        (
            "SP-02",
            sp02_valid,
            sp02_invalid,
            (sp02_selector_mutation, sp02_row_mutation, sp02_section_mutation),
        ),
        (
            "SP-03",
            sp03_valid,
            sp03_invalid,
            (sp03_section_mutation, sp03_meaning_mutation),
        ),
        ("SP-06", sp06_valid, sp06_invalid, (sp06_id_mutation,)),
        (
            "SP-07",
            sp07_valid,
            sp07_invalid,
            (sp07_selector_mutation, sp07_id_mutation),
        ),
        (
            "SP-08",
            sp08_valid,
            sp08_invalid,
            (sp08_lookup_mutation, sp08_id_mutation, sp08_section_mutation),
        ),
        (
            "SP-09",
            sp09_valid,
            sp09_invalid,
            (
                sp09_selector_mutation,
                sp09_t5_mutation,
                sp09_any_of_mutation,
                sp09_id_mutation,
            ),
        ),
        (
            "SP-10",
            sp10_valid,
            sp10_invalid,
            (sp10_route_selector_mutation, sp10_response_selector_mutation),
        ),
        ("SP-11", sp11_valid, sp11_invalid, (sp11_selector_mutation,)),
        (
            "SP-12",
            sp12_valid,
            sp12_invalid,
            (
                sp12_boundary_selector_mutation,
                sp12_exclusion_mutation,
                sp12_row_selector_mutation,
            ),
        ),
        (
            "SP-13",
            sp13_valid,
            sp13_invalid,
            (sp13_section_mutation, sp13_meaning_mutation),
        ),
        (
            "SP-14",
            sp14_valid,
            sp14_invalid,
            (sp14_section_mutation, sp14_meaning_mutation),
        ),
        ("SP-16", sp16_valid, sp16_invalid, (sp16_section_mutation,)),
        (
            "SP-18",
            sp18_valid,
            sp18_invalid,
            (sp18_two_odd_rows_mutation, sp18_header_mutation),
        ),
        (
            "SP-20",
            sp20_valid,
            sp20_invalid,
            (
                sp20_definition_selector_mutation,
                sp20_role_selector_mutation,
                sp20_row_mutation,
                sp20_conditional_mutation,
            ),
        ),
    )


STRUCTURAL_CHECK_CASES = _build_structural_check_cases(
    checker.load_manifest(REPOSITORY_ROOT / checker.DEFAULT_MANIFEST)
)


def _mt01_corpus_document(*lines: str) -> str:
    """MT-01の全scope見出しを持つcorpus文書を組み立てる。"""
    section_ids = (
        "2-2",
        "3-1",
        "3-2",
        "6-4",
        "7-3",
        "7-4",
        "10-1",
        "10-3",
        "11-1",
        "11-3",
        "11-4",
    )
    return _corpus_document(
        {
            section_id: lines if section_id == "2-2" else ()
            for section_id in section_ids
        }
    )


FORBIDDEN_CHECK_CASES = (
    (
        "SP-19",
        _corpus_document({"2-1": (), "5-5": (), "8-2": (), "10-2": ("D1 は同期順に使う。",)}),
        _corpus_document(
            {
                "2-1": (),
                "5-5": (),
                "8-2": (),
                "10-2": ("墓標を `D1=5` の位置には配置しない。",),
            }
        ),
    ),
    (
        "MT-01",
        _mt01_corpus_document("同期プロトコルの設計を定める。"),
        _mt01_corpus_document("本書は「候補案」であり「決定」ではない。"),
    ),
)

ABSENT_SECTION_CHECK_CASE = (
    "MT-01",
    _mt01_corpus_document("同期プロトコルの設計を定める。"),
    "## 1. corpus\n" + _mt01_corpus_document("同期プロトコルの設計を定める。"),
    (),
)
STRUCTURAL_CORPUS_CASES = (*STRUCTURAL_CHECK_CASES, ABSENT_SECTION_CHECK_CASE)

_STRUCTURAL_CASE_BY_ID = {case[0]: case for case in STRUCTURAL_CHECK_CASES}
_FORBIDDEN_CASE_BY_ID = {case[0]: case for case in FORBIDDEN_CHECK_CASES}
_LEGACY_CASE_ORDER = ("SP-01", "SP-02", "SP-07", "SP-08", "SP-16", "SP-20", "SP-18")

DEFECT_CHECK_CASES = (
    tuple(_STRUCTURAL_CASE_BY_ID[defect_id][:3] for defect_id in _LEGACY_CASE_ORDER)
    + (_FORBIDDEN_CASE_BY_ID["MT-01"],)
    + tuple(case[:3] for case in STRUCTURAL_CHECK_CASES if case[0] not in _LEGACY_CASE_ORDER)
    + (_FORBIDDEN_CASE_BY_ID["SP-19"],)
)

DEFECT_CHECK_CASE_IDS = (
    "condition-key",
    "enum-propagation",
    "route-matrix",
    "element-coverage",
    "scope-declaration",
    "order-use",
    "emphasis",
    "draft-metadata",
    "enum-propagation-SP-03",
    "route-matrix-SP-06",
    "route-matrix-SP-09",
    "route-matrix-SP-10",
    "enum-propagation-SP-11",
    "scope-declaration-SP-12",
    "enum-propagation-SP-13",
    "enum-propagation-SP-14",
    "order-use-SP-19",
)


@pytest.mark.parametrize(
    ("defect_id", "valid_text", "invalid_text"),
    DEFECT_CHECK_CASES,
    ids=DEFECT_CHECK_CASE_IDS,
)
def test_defect_backed_checks_have_normal_and_abnormal_cases(
    defect_id: str,
    valid_text: str,
    invalid_text: str,
    manifest: dict[str, checker.ManifestRelation],
    defects: dict[str, checker.Defect],
) -> None:
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    assert checker.defect_violation_reason(
        defects[defect_id],
        valid_text,
        manifest,
        invariants=invariants,
        profile=profile,
    ) is None
    assert checker.defect_violation_reason(
        defects[defect_id],
        invalid_text,
        manifest,
        invariants=invariants,
        profile=profile,
    )


def test_sp19_remains_detected_by_forbidden_literal_without_declaration(
    manifest: dict[str, checker.ManifestRelation],
    defects: dict[str, checker.Defect],
) -> None:
    """SP-19を宣言や旧分岐でなくforbidden literalだけで検出する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text = _FORBIDDEN_CASE_BY_ID["SP-19"]

    assert not any(
        declaration["defect_id"] == "SP-19"
        for declaration in invariants.declarations
    )
    assert checker.defect_violation_reason(
        defects["SP-19"],
        valid_text,
        manifest,
        invariants=invariants,
        profile=profile,
    ) is None
    assert checker.defect_violation_reason(
        defects["SP-19"],
        invalid_text,
        manifest,
        invariants=invariants,
        profile=profile,
    ) == "禁止literalが残存: `D1=5` の位置には"


STRUCTURAL_DEFECT_IDS = frozenset(
    {
        "SP-01",
        "SP-02",
        "SP-03",
        "SP-06",
        "SP-07",
        "SP-08",
        "SP-09",
        "SP-10",
        "SP-11",
        "SP-12",
        "SP-13",
        "SP-14",
        "SP-16",
        "SP-18",
        "SP-20",
    }
)
ROW_SELECTOR_MIGRATED_IDS = frozenset({"SP-10", "SP-11"})
SECTION_CONTAINS_MIGRATED_IDS = frozenset({"SP-02", "SP-03", "SP-13", "SP-14"})
EXACT_SET_MIGRATED_IDS = frozenset({"SP-06", "SP-07"})
REQUIRED_EXCLUSION_MIGRATED_IDS = frozenset({"SP-12", "SP-16"})


def _scope_section_ids(scope: str) -> tuple[str, ...]:
    """checker.extract_scopeと同じ規則でscopeから節IDを得る。"""
    section_ids: list[str] = []
    for raw_token in scope.split("、"):
        token = raw_token.strip()
        if token == "冒頭":
            continue
        token = token.split(" の", 1)[0].removesuffix("節").strip()
        if re.fullmatch(r"\d+(?:-\d+(?:-[A-Z])?)?", token) is not None:
            section_ids.append(token)
    return tuple(section_ids)


def test_structural_corpus_covers_all_15_ids() -> None:
    corpus_ids = [case[0] for case in STRUCTURAL_CHECK_CASES]

    assert len(corpus_ids) == 15
    assert frozenset(corpus_ids) == STRUCTURAL_DEFECT_IDS


def test_structural_corpus_has_mt01_as_sixteenth_case() -> None:
    """旧15件にabsent-sectionのMT-01を加えたcorpus総体を固定する。"""
    corpus_ids = [case[0] for case in STRUCTURAL_CORPUS_CASES]

    assert len(corpus_ids) == 16
    assert frozenset(corpus_ids) == STRUCTURAL_DEFECT_IDS | {"MT-01"}


def test_structural_abnormal_texts_contain_no_forbidden_literal(
    defects: dict[str, checker.Defect],
) -> None:
    for defect_id, _, invalid_text, mutations in STRUCTURAL_CORPUS_CASES:
        invariant = defects[defect_id].invariant
        assert invariant is not None
        for text in (invalid_text, *mutations):
            for forbidden in invariant.forbidden:
                assert forbidden not in text, f"{defect_id}: {forbidden}"


def test_structural_texts_contain_all_scope_headings(
    defects: dict[str, checker.Defect],
) -> None:
    for defect_id, valid_text, invalid_text, mutations in STRUCTURAL_CORPUS_CASES:
        invariant = defects[defect_id].invariant
        assert invariant is not None
        for text in (valid_text, invalid_text, *mutations):
            for section_id in _scope_section_ids(invariant.scope):
                heading = rf"^#{{1,6}}\s+{re.escape(section_id)}[.\s(]"
                assert re.search(heading, text, re.MULTILINE), f"{defect_id}: {section_id}"


def test_structural_cases_do_not_raise(
    manifest: dict[str, checker.ManifestRelation],
    defects: dict[str, checker.Defect],
) -> None:
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    for defect_id, valid_text, invalid_text, mutations in STRUCTURAL_CORPUS_CASES:
        for text in (valid_text, invalid_text, *mutations):
            checker.defect_violation_reason(
                defects[defect_id],
                text,
                manifest,
                invariants=invariants,
                profile=profile,
            )
    for defect_id, valid_text, invalid_text in FORBIDDEN_CHECK_CASES:
        for text in (valid_text, invalid_text):
            checker.defect_violation_reason(
                defects[defect_id],
                text,
                manifest,
                invariants=invariants,
                profile=profile,
            )


def test_scope_with_invalid_token_is_rejected(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    defect = checker.Defect(
        id="TEST-01",
        detection="machine",
        check="draft-metadata",
        invariant=checker.Invariant(
            positive="test",
            forbidden=(),
            scope="2-2、付録A",
            mapping=None,
        ),
    )

    with pytest.raises(
        checker.CheckError,
        match="scope のトークン『付録A』が節 ID の文法に一致しない",
    ):
        checker.defect_violation_reason(
            defect,
            "### 2-2. corpus\n本文\n",
            manifest,
        )


def test_scope_with_missing_section_is_rejected_but_preamble_is_not(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    missing = checker.Defect(
        id="TEST-02",
        detection="machine",
        check="draft-metadata",
        invariant=checker.Invariant(
            positive="test",
            forbidden=(),
            scope="冒頭、2-2、3-1",
            mapping=None,
        ),
    )
    preamble_only = replace(
        missing,
        invariant=replace(missing.invariant, scope="冒頭"),
    )
    text = "冒頭の本文\n### 2-2. corpus\n本文\n"

    assert checker.defect_violation_reason(preamble_only, text, manifest) is None
    with pytest.raises(
        checker.CheckError,
        match="scope の節『3-1』が文書に無い",
    ):
        checker.defect_violation_reason(missing, text, manifest)


def test_structural_mutations_fail(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    for defect_id, _, _, mutations in STRUCTURAL_CHECK_CASES:
        assert mutations, defect_id
        for mutation in mutations:
            reason, _ = _evaluate_declared_defect(
                defect_id,
                mutation,
                manifest=manifest,
                invariants=invariants,
                profile=profile,
            )
            assert reason, defect_id


def test_binding_rule_six_has_no_legacy_ids_or_source_branches() -> None:
    """規則6としてlegacy空と旧ID別分岐0件を同時に固定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    source = SCRIPT.read_text(encoding="utf-8")

    assert not invariants.legacy_structural
    assert not checker.LEGACY_STRUCTURAL_BRANCH_IDS
    assert "defect_id == " not in source
    assert not hasattr(checker, "_structural_reason")


def test_sync_invariants_conform_to_fifteen_structural_ids() -> None:
    """同期宣言資産の構造必須集合と骨格状態をexactに固定する。"""
    invariants_path = (
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    invariants = checker.doc_check_profile.load_invariants(invariants_path)

    assert invariants.structural_required == STRUCTURAL_DEFECT_IDS
    assert not invariants.legacy_structural
    assert invariants.required_declarations == {"MT-01"}
    assert frozenset(
        declaration["defect_id"] for declaration in invariants.declarations
    ) == STRUCTURAL_DEFECT_IDS | {"MT-01"}


def _reason_fixture_case_texts() -> dict[str, str]:
    """静的reason fixtureのcase_idを実入力本文へ対応付ける。"""
    texts: dict[str, str] = {}
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    approved_text = DESIGN.read_text(encoding="utf-8")
    for defect_id, valid_text, invalid_text, mutations in STRUCTURAL_CHECK_CASES:
        texts[f"{defect_id}:corpus-valid"] = valid_text
        texts[f"{defect_id}:corpus-invalid"] = invalid_text
        for index, mutation in enumerate(mutations, start=1):
            texts[f"{defect_id}:corpus-mutation:{index}"] = mutation
        texts[f"{defect_id}:fixture"] = fixture_text
        texts[f"{defect_id}:approved"] = approved_text
    defect_id, valid_text, invalid_text, _ = ABSENT_SECTION_CHECK_CASE
    texts[f"{defect_id}:corpus-valid"] = valid_text
    texts[f"{defect_id}:corpus-invalid"] = invalid_text
    texts[f"{defect_id}:fixture"] = fixture_text
    texts[f"{defect_id}:approved"] = approved_text
    return texts


def _document_sections(text: str) -> dict[str, str]:
    """宣言評価用に文書中の節IDを既存抽出器で解決する。"""
    section_ids = {
        match.group(1)
        for line in text.splitlines()
        if (match := re.match(r"^#{2,6}\s+(\d+(?:-\d+(?:-[A-Z])?)?)[.\s(]", line))
    }
    return {
        section_id: checker._heading_section(text, section_id)
        for section_id in section_ids
    }


def _evaluate_declarations(
    declarations: tuple[dict[str, Any], ...],
    text: str,
    *,
    manifest: dict[str, checker.ManifestRelation],
    profile: Any,
) -> tuple[Any, Any]:
    """指定された宣言列を新評価器だけでfirst-failure評価する。"""
    context = invariant_evaluator.EvaluationContext()
    reason = None
    for declaration in declarations:
        reason = invariant_evaluator.evaluate_declaration(
            declaration,
            text=text,
            manifest=manifest,
            profile=profile,
            sections=_document_sections(text),
            context=context,
        )
        if reason is not None:
            break
    return reason, context


def _evaluate_declared_defect(
    defect_id: str,
    text: str,
    *,
    manifest: dict[str, checker.ManifestRelation],
    invariants: Any,
    profile: Any,
) -> tuple[Any, Any]:
    """指定欠陥の宣言列を新評価器だけでfirst-failure評価する。"""
    declarations = tuple(
        declaration
        for declaration in invariants.declarations
        if declaration["defect_id"] == defect_id
    )
    return _evaluate_declarations(
        declarations,
        text,
        manifest=manifest,
        profile=profile,
    )


def _write_cross_reference_case(
    tmp_path: Path,
    *,
    from_section: str = "| source | version=7 |",
    to_section: str = "| target | version=7 |",
    extract: str = r"version=(\d+)",
) -> tuple[str, tuple[dict[str, Any], ...]]:
    """合成文書とcross-reference宣言列を一時ファイルへ書いて読む。"""
    text = (
        f"### 2-1. source\n{from_section}\n"
        f"### 2-2. target\n{to_section}\n"
    )
    declarations = (
        {
            "defect_id": "SP-X",
            "kind": "row-selector",
            "id": "source-row",
            "section": "2-1",
            "mode": "needle",
            "keys": ["source"],
        },
        {
            "defect_id": "SP-X",
            "kind": "row-selector",
            "id": "target-row",
            "section": "2-2",
            "mode": "needle",
            "keys": ["target"],
        },
        {
            "defect_id": "SP-X",
            "kind": "cross-reference",
            "from": {"row": "source-row"},
            "to": {"row": "target-row"},
            "extract": extract,
        },
    )
    document_path = tmp_path / "document.md"
    declarations_path = tmp_path / "declarations.json"
    document_path.write_text(text, encoding="utf-8")
    declarations_path.write_text(
        json.dumps(declarations, ensure_ascii=False),
        encoding="utf-8",
    )
    return (
        document_path.read_text(encoding="utf-8"),
        tuple(json.loads(declarations_path.read_text(encoding="utf-8"))),
    )


def test_cross_reference_accepts_equal_extracted_values(
    tmp_path: Path,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """両方の選択行から抽出した値が同じなら適合させる。"""
    text, declarations = _write_cross_reference_case(tmp_path)
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)

    reason, _ = _evaluate_declarations(
        declarations,
        text,
        manifest=manifest,
        profile=profile,
    )

    assert reason is None


def test_cross_reference_rejects_different_extracted_values(
    tmp_path: Path,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """fromとtoで抽出値が異なる場合に構造化違反を返す。"""
    text, declarations = _write_cross_reference_case(
        tmp_path,
        to_section="| target | version=8 |",
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)

    reason, _ = _evaluate_declarations(
        declarations,
        text,
        manifest=manifest,
        profile=profile,
    )

    assert reason == invariant_evaluator.StructuredReason(
        violated=True,
        kind="cross-reference",
        section="2-1",
        expected="7",
        actual="8",
        token=None,
    )


def test_cross_reference_rejects_extraction_failure(
    tmp_path: Path,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """どちらかの行から値を抽出できなければ違反にする。"""
    text, declarations = _write_cross_reference_case(
        tmp_path,
        from_section="| source | version missing |",
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)

    reason, _ = _evaluate_declarations(
        declarations,
        text,
        manifest=manifest,
        profile=profile,
    )

    assert reason is not None
    assert reason.kind == "cross-reference"
    assert reason.expected is None
    assert reason.actual == "7"


def test_cross_reference_rejects_undefined_row_reference(
    tmp_path: Path,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """先行selectorが定義していないrow参照をfail-closedにする。"""
    text, declarations = _write_cross_reference_case(tmp_path)
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    declarations = (declarations[0], declarations[2])

    with pytest.raises(
        invariant_evaluator.doc_check_profile.ProfileError,
        match="to 参照先 row が未定義.*target-row",
    ):
        _evaluate_declarations(
            declarations,
            text,
            manifest=manifest,
            profile=profile,
        )


@pytest.mark.parametrize(
    ("extract", "message"),
    (("(", "正規表現が不正"), (r"version=\d+", "捕捉グループを1個")),
    ids=("invalid-regex", "no-capture-group"),
)
def test_cross_reference_rejects_invalid_extract_pattern(
    tmp_path: Path,
    manifest: dict[str, checker.ManifestRelation],
    extract: str,
    message: str,
) -> None:
    """不正または捕捉グループ数が1でない正規表現を拒否する。"""
    text, declarations = _write_cross_reference_case(tmp_path, extract=extract)
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)

    with pytest.raises(
        invariant_evaluator.doc_check_profile.ProfileError,
        match=message,
    ):
        _evaluate_declarations(
            declarations,
            text,
            manifest=manifest,
            profile=profile,
        )


def test_cross_reference_rejects_value_moved_to_another_row(
    tmp_path: Path,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """from値の同節別行移動でselectorを不成立にし、違反にする。"""
    valid_text, declarations = _write_cross_reference_case(tmp_path)
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    declarations[0]["keys"] = ["source", "version="]
    moved_text = valid_text.replace(
        "| source | version=7 |",
        "| source | value moved |\n| note | version=7 |",
    )

    valid_reason, _ = _evaluate_declarations(
        declarations,
        valid_text,
        manifest=manifest,
        profile=profile,
    )
    moved_reason, _ = _evaluate_declarations(
        declarations,
        moved_text,
        manifest=manifest,
        profile=profile,
    )

    assert valid_reason is None
    assert moved_reason is not None
    assert moved_reason.kind == "row-selector"


def test_rule_six_prerequisite_legacy_structural_is_empty() -> None:
    """規則6前段として同期宣言資産のlegacy集合が空であることを固定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )

    assert not invariants.legacy_structural


def test_rule_six_prerequisite_declaration_ids_exactly_cover_required_ids() -> None:
    """宣言ID集合を構造必須15件とrequired MT-01の和集合へexactにする。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    declaration_ids = {
        declaration["defect_id"] for declaration in invariants.declarations
    }
    expected_ids = set(invariants.structural_required) | set(
        invariants.required_declarations
    )

    assert declaration_ids == expected_ids
    assert len(declaration_ids) == 16


def test_rule_six_prerequisite_structural_corpus_uses_new_evaluator_only(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """構造corpus 16件を旧分岐なしの宣言評価器だけで判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)

    for defect_id, valid_text, invalid_text, mutations in STRUCTURAL_CORPUS_CASES:
        valid_reason, _ = _evaluate_declared_defect(
            defect_id,
            valid_text,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert valid_reason is None, defect_id
        for abnormal_text in (invalid_text, *mutations):
            reason, _ = _evaluate_declared_defect(
                defect_id,
                abnormal_text,
                manifest=manifest,
                invariants=invariants,
                profile=profile,
            )
            assert reason is not None, defect_id
            assert reason.violated, defect_id


def test_rule_six_prerequisite_expected_fixture_matches_new_evaluator_only(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """期待fixture全行を旧分岐・shadowなしで宣言評価器へ突合する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    expected_rows = json.loads(
        STRUCTURAL_REASON_FIXTURE.read_text(encoding="utf-8")
    )
    case_texts = _reason_fixture_case_texts()

    for expected in expected_rows:
        reason, _ = _evaluate_declared_defect(
            expected["defect_id"],
            case_texts[expected["case_id"]],
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        actual_exit = 0 if reason is None else 1
        actual_violated = False if reason is None else reason.violated
        expected_reason = expected["reason"]
        expected_violated = (
            False if expected_reason is None else expected_reason["violated"]
        )
        assert actual_exit == expected["expected_exit"], expected["case_id"]
        assert actual_violated is expected_violated, expected["case_id"]


@pytest.mark.parametrize("defect_id", sorted(ROW_SELECTOR_MIGRATED_IDS))
def test_row_selector_evaluator_handles_corpus_and_mutations(
    defect_id: str,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """row-selector単独で正常・異常・同値変異を判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID[defect_id]

    valid_reason, valid_context = _evaluate_declared_defect(
        defect_id,
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    selector_ids = {
        declaration["id"]
        for declaration in invariants.declarations
        if declaration["defect_id"] == defect_id
    }
    assert set(valid_context.selected_rows) == selector_ids

    invalid_reason, _ = _evaluate_declared_defect(
        defect_id,
        invalid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert invalid_reason is not None
    assert invalid_reason.kind == "row-selector"
    for mutation in mutations:
        mutation_reason, _ = _evaluate_declared_defect(
            defect_id,
            mutation,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert mutation_reason is not None
        assert mutation_reason.kind == "row-selector"


def test_row_contains_evaluator_handles_sp01_corpus_and_mutations(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """SP-01宣言単独で正常・異常・別行移動・selector変異を判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID["SP-01"]

    valid_reason, valid_context = _evaluate_declared_defect(
        "SP-01",
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    assert set(valid_context.selected_rows) == {
        "sp01-transition",
        "sp01-boundary",
    }

    invalid_reason, _ = _evaluate_declared_defect(
        "SP-01",
        invalid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert invalid_reason is not None
    assert invalid_reason.kind == "row-contains"
    assert invalid_reason.section == "6-3"
    assert invalid_reason.token == "A5"

    expected_kinds = ("row-selector", "row-contains", "row-selector")
    for mutation, expected_kind in zip(mutations, expected_kinds, strict=True):
        mutation_reason, _ = _evaluate_declared_defect(
            "SP-01",
            mutation,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert mutation_reason is not None
        assert mutation_reason.kind == expected_kind


def test_row_contains_rejects_undefined_row_reference(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """先行selectorが定義していないrow参照をfail-closedにする。"""
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    declaration = {
        "defect_id": "SP-01",
        "kind": "row-contains",
        "row": "missing-row",
        "literals": ["A5"],
    }

    with pytest.raises(
        invariant_evaluator.doc_check_profile.ProfileError,
        match=r"参照先 row が未定義.*missing-row",
    ):
        invariant_evaluator.evaluate_declaration(
            declaration,
            text="",
            manifest=manifest,
            profile=profile,
            sections={},
            context=invariant_evaluator.EvaluationContext(),
        )


@pytest.mark.parametrize("defect_id", sorted(SECTION_CONTAINS_MIGRATED_IDS))
def test_section_contains_evaluator_handles_corpus_and_mutations(
    defect_id: str,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """4モードとrow要素参照で正常・異常・同値変異を直接判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID[defect_id]

    valid_reason, _ = _evaluate_declared_defect(
        defect_id,
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    for abnormal_text in (invalid_text, *mutations):
        reason, _ = _evaluate_declared_defect(
            defect_id,
            abnormal_text,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert reason is not None


def test_section_contains_declarations_cover_all_four_modes() -> None:
    """移行宣言がtext・identifier・identified-row・rowを全て使用する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    modes = {
        declaration["as"]
        for declaration in invariants.declarations
        if declaration["defect_id"] in SECTION_CONTAINS_MIGRATED_IDS
        and declaration["kind"] == "section-contains"
    }
    assert modes == {"text", "identifier", "identified-row", "row"}


def test_manifest_element_reference_is_fail_closed(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """存在しないrelationを参照する要素宣言をProfileErrorにする。"""
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    declaration = {
        "defect_id": "SP-03",
        "kind": "section-contains",
        "sections": ["6-3"],
        "elements": {"relation": "R-NOT-FOUND", "field": "source_elements"},
        "as": "identifier",
    }

    with pytest.raises(
        invariant_evaluator.doc_check_profile.ProfileError,
        match="relation がマニフェストにありません",
    ):
        invariant_evaluator.evaluate_declaration(
            declaration,
            text="",
            manifest=manifest,
            profile=profile,
            sections={"6-3": "### 6-3. test\n"},
            context=invariant_evaluator.EvaluationContext(),
        )


@pytest.mark.parametrize("defect_id", sorted(EXACT_SET_MIGRATED_IDS))
def test_exact_set_evaluator_handles_corpus_and_mutations(
    defect_id: str,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """exact-set宣言単独で正常・異常・ID交換変異を判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID[defect_id]

    valid_reason, _ = _evaluate_declared_defect(
        defect_id,
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    for abnormal_text in (invalid_text, *mutations):
        reason, _ = _evaluate_declared_defect(
            defect_id,
            abnormal_text,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert reason is not None


@pytest.mark.parametrize("section_id", ("8-1", "10-2", "11-2"))
def test_exact_set_checks_each_declared_section(
    section_id: str,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """SP-06の3節はどの1節だけを壊してもexact-set違反になる。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, _, _ = _STRUCTURAL_CASE_BY_ID["SP-06"]
    routes = invariant_evaluator.expected_route_elements(
        manifest, "R-TXN-ROUTE", prefix="T"
    )
    changed = _replace_in_section(
        valid_text,
        section_id,
        _route_row("P2", routes["P2"]),
        _route_row("P2", routes["P2"]).replace("T5", "T9"),
    )

    reason, _ = _evaluate_declared_defect(
        "SP-06",
        changed,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert reason is not None
    assert reason.kind == "exact-set"
    assert reason.section == section_id


def test_exact_set_uses_only_the_declared_relation(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """同一manifestの別関係でなく宣言したrelationから期待集合を導く。"""
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    alternate = replace(
        manifest["R-TXN-ROUTE"],
        id="R-ALTERNATE-ROUTE",
        source_elements=("P1:別経路=T9",),
    )
    synthetic_manifest = {**manifest, alternate.id: alternate}
    declaration = {
        "defect_id": "SP-06",
        "kind": "exact-set",
        "sections": ["8-1"],
        "relation": alternate.id,
        "routes": ["P1"],
    }
    original_row = _route_row(
        "P1",
        invariant_evaluator.expected_route_elements(
            manifest, "R-TXN-ROUTE", prefix="T"
        )["P1"],
    )

    reason = invariant_evaluator.evaluate_declaration(
        declaration,
        text="",
        manifest=synthetic_manifest,
        profile=profile,
        sections={"8-1": original_row},
        context=invariant_evaluator.EvaluationContext(),
    )
    assert reason is not None
    assert reason.expected == "P1: T9"


def test_exact_set_can_evaluate_a_selected_row(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """row形式では先行selectorが保存した1行の集合を比較する。"""
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    row = _route_row(
        "P1",
        invariant_evaluator.expected_route_elements(
            manifest, "R-TXN-ROUTE", prefix="T"
        )["P1"],
    )
    context = invariant_evaluator.EvaluationContext(
        selected_rows={"route": row},
        selected_sections={"route": "8-1"},
    )
    declaration = {
        "defect_id": "SP-06",
        "kind": "exact-set",
        "row": "route",
        "relation": "R-TXN-ROUTE",
        "routes": ["P1"],
    }

    reason = invariant_evaluator.evaluate_declaration(
        declaration,
        text="",
        manifest=manifest,
        profile=profile,
        sections={},
        context=context,
    )
    assert reason is None


def test_element_lookup_evaluator_handles_corpus_and_mutations(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """SP-08宣言単独で正常・異常・意味部別行移動を判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID["SP-08"]

    valid_reason, _ = _evaluate_declared_defect(
        "SP-08",
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    reasons = []
    for abnormal_text in (invalid_text, *mutations):
        reason, _ = _evaluate_declared_defect(
            "SP-08",
            abnormal_text,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert reason is not None
        reasons.append(reason)
    lookup_reason = reasons[1]
    assert lookup_reason.kind == "element-lookup"
    assert lookup_reason.token == "T6:"
    assert lookup_reason.actual == "| T6 | 保存要素 |"

    declarations = [
        declaration
        for declaration in invariants.declarations
        if declaration["defect_id"] == "SP-08"
    ]
    assert declarations[0] == {
        "defect_id": "SP-08",
        "kind": "element-lookup",
        "relation": "R-TXN-ROUTE",
        "prefix": "T6:",
        "section": "8-1",
        "row_identifier": "T6",
    }


def test_row_scoped_forbidden_evaluator_and_separate_row_mutation(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """禁止語を選択行だけで拒否し、同じ節の別行なら適合させる。"""
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    selector = {
        "defect_id": "SP-09",
        "kind": "row-selector",
        "id": "sp09-route",
        "section": "8-1",
        "mode": "identifier",
        "keys": ["P3"],
    }
    declaration = {
        "defect_id": "SP-09",
        "kind": "row-scoped-forbidden",
        "row": "sp09-route",
        "literals": ["T5"],
    }

    def evaluate(section: str) -> Any:
        context = invariant_evaluator.EvaluationContext()
        selector_reason = invariant_evaluator.evaluate_declaration(
            selector,
            text="",
            manifest=manifest,
            profile=profile,
            sections={"8-1": section},
            context=context,
        )
        assert selector_reason is None
        return invariant_evaluator.evaluate_declaration(
            declaration,
            text="",
            manifest=manifest,
            profile=profile,
            sections={"8-1": section},
            context=context,
        )

    assert evaluate("| P3 | T1・T2・T4・T6・T7 |") is None
    violation = evaluate("| P3 | T1・T2・T4・T5・T6・T7 |")
    assert violation is not None
    assert violation.kind == "row-scoped-forbidden"
    assert violation.token == "T5"
    assert (
        evaluate("| P3 | T1・T2・T4・T6・T7 |\n| 補足 | T5 は別行 |")
        is None
    )


def test_sp09_declaration_chain_handles_corpus_and_mutations(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """SP-09の4宣言列で正常・異常・全同値変異を判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID["SP-09"]

    valid_reason, _ = _evaluate_declared_defect(
        "SP-09",
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    for abnormal_text in (invalid_text, *mutations):
        reason, _ = _evaluate_declared_defect(
            "SP-09",
            abnormal_text,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert reason is not None


def test_sp09_each_declaration_has_an_independent_negative_case(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """selector・集合・禁止・選言を各宣言単独の負例で検証する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    declarations = {
        declaration["kind"]: declaration
        for declaration in invariants.declarations
        if declaration["defect_id"] == "SP-09"
    }
    _, _, _, mutations = _STRUCTURAL_CASE_BY_ID["SP-09"]

    selector_reason = invariant_evaluator.evaluate_declaration(
        declarations["row-selector"],
        text=mutations[0],
        manifest=manifest,
        profile=profile,
        sections=_document_sections(mutations[0]),
        context=invariant_evaluator.EvaluationContext(),
    )
    assert selector_reason is not None
    assert selector_reason.kind == "row-selector"

    expected_kinds = (
        ("exact-set", mutations[3]),
        ("row-scoped-forbidden", mutations[1]),
        ("any-of", mutations[2]),
    )
    for kind, text in expected_kinds:
        row = invariant_evaluator.identified_row(
            checker._heading_section(text, "8-1"), "P3"
        )
        assert row is not None
        context = invariant_evaluator.EvaluationContext(
            selected_rows={"sp09-route": row},
            selected_sections={"sp09-route": "8-1"},
        )
        reason = invariant_evaluator.evaluate_declaration(
            declarations[kind],
            text=text,
            manifest=manifest,
            profile=profile,
            sections=_document_sections(text),
            context=context,
        )
        assert reason is not None
        assert reason.kind == kind


@pytest.mark.parametrize("defect_id", sorted(REQUIRED_EXCLUSION_MIGRATED_IDS))
def test_required_exclusion_evaluator_handles_corpus_and_mutations(
    defect_id: str,
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """row/sections除外宣言で正常・異常・別行/別節変異を判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID[defect_id]

    valid_reason, _ = _evaluate_declared_defect(
        defect_id,
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    for abnormal_text in (invalid_text, *mutations):
        reason, _ = _evaluate_declared_defect(
            defect_id,
            abnormal_text,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert reason is not None


def test_required_exclusion_supports_one_and_two_terms() -> None:
    """SP-12の宣言列でterms 1件形と2件形を固定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    term_counts = {
        len(declaration["terms"])
        for declaration in invariants.declarations
        if declaration["defect_id"] == "SP-12"
        and declaration["kind"] == "required-exclusion"
    }
    assert term_counts == {1, 2}


def test_required_exclusion_uses_profile_exclusion_vocabulary(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """プロファイルの除外語彙を変えると同じSP-16本文の判定が変わる。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    changed_profile = replace(
        profile,
        raw={**profile.raw, "exclusion_vocabulary": ["除外済み"]},
    )
    _, valid_text, _, _ = _STRUCTURAL_CASE_BY_ID["SP-16"]

    default_reason, _ = _evaluate_declared_defect(
        "SP-16",
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    changed_reason, _ = _evaluate_declared_defect(
        "SP-16",
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=changed_profile,
    )
    assert default_reason is None
    assert changed_reason is not None
    assert changed_reason.kind == "required-exclusion"


def test_sp20_declaration_chain_handles_corpus_and_mutations(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """SP-20宣言列で正常・異常・selector/行/含意変異を判定する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID["SP-20"]

    valid_reason, _ = _evaluate_declared_defect(
        "SP-20",
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    assert valid_reason is None
    for abnormal_text in (invalid_text, *mutations):
        reason, _ = _evaluate_declared_defect(
            "SP-20",
            abnormal_text,
            manifest=manifest,
            invariants=invariants,
            profile=profile,
        )
        assert reason is not None


def test_conditional_forbidden_covers_both_sides_of_implication(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """literalなし・unless完備を適合、unless欠落を違反にする。"""
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    declaration = {
        "defect_id": "SP-20",
        "kind": "conditional-forbidden",
        "row": "definition",
        "literal": "再送の重複排除",
        "unless": ["D5 の用途", "D1 の用途ではない"],
    }

    def evaluate(row: str) -> Any:
        context = invariant_evaluator.EvaluationContext(
            selected_rows={"definition": row},
            selected_sections={"definition": "2-1"},
        )
        return invariant_evaluator.evaluate_declaration(
            declaration,
            text="",
            manifest=manifest,
            profile=profile,
            sections={},
            context=context,
        )

    assert evaluate("| D1 | 順序と欠落・undo の逆順 |") is None
    assert (
        evaluate(
            "| D1 | 再送の重複排除はD5 の用途でありD1 の用途ではない |"
        )
        is None
    )
    assert evaluate("| D1 | 再送の重複排除はD5 の用途 |") is not None


def test_well_formedness_handles_three_equivalent_mutations(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """2行不整合・ヘッダ不整合を拒否し、表外の奇数強調は許可する。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    _, valid_text, invalid_text, mutations = _STRUCTURAL_CASE_BY_ID["SP-18"]

    valid_reason, _ = _evaluate_declared_defect(
        "SP-18",
        valid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    invalid_reason, _ = _evaluate_declared_defect(
        "SP-18",
        invalid_text,
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    two_rows_reason, _ = _evaluate_declared_defect(
        "SP-18",
        mutations[0],
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )
    header_reason, _ = _evaluate_declared_defect(
        "SP-18",
        mutations[1],
        manifest=manifest,
        invariants=invariants,
        profile=profile,
    )

    assert valid_reason is None
    assert invalid_reason is not None
    assert invalid_reason.actual == "強調不整合行: 3"
    assert two_rows_reason is not None
    assert two_rows_reason.actual == "強調不整合行: 2,3"
    assert header_reason is not None
    assert header_reason.actual == "強調不整合行: 2"


def test_mt01_absent_section_uses_declaration_path(
    manifest: dict[str, checker.ManifestRelation],
    defects: dict[str, checker.Defect],
) -> None:
    """MT-01を節不在時は適合、節1存在時は宣言違反にする。"""
    invariants = checker.doc_check_profile.load_invariants(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    declaration = invariants.declarations[0]
    _, valid_text, invalid_text, _ = ABSENT_SECTION_CHECK_CASE

    assert invariant_evaluator.evaluate_declaration(
        declaration,
        text=valid_text,
        manifest=manifest,
        profile=profile,
        sections={},
    ) is None
    reason = invariant_evaluator.evaluate_declaration(
        declaration,
        text=invalid_text,
        manifest=manifest,
        profile=profile,
        sections={},
    )
    assert reason == invariant_evaluator.StructuredReason(
        violated=True,
        kind="absent-section",
        section="1",
        expected="節が存在しない",
        actual="節が存在する",
        token=None,
    )
    assert checker.defect_violation_reason(
        defects["MT-01"],
        valid_text,
        manifest,
        invariants=invariants,
        profile=profile,
    ) is None
    assert checker.defect_violation_reason(
        defects["MT-01"],
        invalid_text,
        manifest,
        invariants=invariants,
        profile=profile,
    ) == "節が存在する"


def test_forbidden_element_declaration_evaluator_is_fail_closed(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """実装済みkindを評価し、それ以外のkindを黙って通さない。"""
    declaration = {
        "defect_id": "SP-01",
        "kind": "forbidden-element",
        "literals": ["禁止語"],
        "sections": ["2-1"],
    }
    profile = checker.doc_check_profile.load_profile(PROFILE, root=REPOSITORY_ROOT)
    reason = invariant_evaluator.evaluate_declaration(
        declaration,
        text="### 2-1. corpus\n禁止語\n",
        manifest=manifest,
        profile=profile,
        sections={"2-1": "### 2-1. corpus\n禁止語"},
    )

    assert reason == invariant_evaluator.StructuredReason(
        violated=True,
        kind="forbidden-element",
        section="2-1",
        expected="literal が対象範囲に無い",
        actual="禁止literalが残存: 禁止語",
        token="禁止語",
    )
    assert invariant_evaluator.evaluate_declaration(
        declaration,
        text="### 2-1. corpus\n適合\n",
        manifest=manifest,
        profile=profile,
        sections={"2-1": "### 2-1. corpus\n適合"},
    ) is None
    with pytest.raises(
        invariant_evaluator.doc_check_profile.ProfileError,
        match="未実装の kind",
    ):
        invariant_evaluator.evaluate_declaration(
            {
                "defect_id": "SP-09",
                "kind": "required-element",
                "sections": ["2-1"],
                "literals": ["必須語"],
            },
            text="",
            manifest=manifest,
            profile=profile,
            sections={},
        )


def _manifest_document(relation: checker.ManifestRelation) -> str:
    targets = json.dumps(relation.targets, ensure_ascii=False, separators=(",", ":"))
    source_elements = json.dumps(
        relation.source_elements, ensure_ascii=False, separators=(",", ":")
    )
    expected_elements = json.dumps(
        dict(relation.expected_elements), ensure_ascii=False, separators=(",", ":")
    )
    return (
        "### 2-5. 表間参照宣言\n"
        "| 関係 ID | 正本の表 | 伝播先の表 | 比較キー | 正本の要素全集合 | "
        "伝播先ごとの期待部分集合 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        f"| **{relation.id}** | `{relation.source_table}` | `{targets}` | "
        f"`{relation.compare_key}` | `{source_elements}` | `{expected_elements}` |\n"
    )


def _manifest_relation(
    relation_id: str = "R-ONE",
    source_table: str = "2-1",
    targets: tuple[str, ...] = ("4-1",),
    compare_key: str = "ID",
    source_elements: tuple[str, ...] = ("E1",),
    expected_elements: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> checker.ManifestRelation:
    """6フィールドを持つ最小の関係宣言を作る。"""
    if expected_elements is None:
        expected_elements = tuple((target, source_elements) for target in targets)
    return checker.ManifestRelation(
        relation_id,
        source_table,
        targets,
        compare_key,
        source_elements,
        expected_elements,
    )


def test_manifest_consistency_accepts_all_six_fields() -> None:
    relation = _manifest_relation()
    assert checker.check_manifest_consistency(
        _manifest_document(relation), {relation.id: relation}
    ) == ()


@pytest.mark.parametrize(
    "changed",
    (
        _manifest_relation(relation_id="R-TWO"),
        _manifest_relation(source_table="2-2"),
        _manifest_relation(targets=("4-2",)),
        _manifest_relation(compare_key="name"),
        _manifest_relation(source_elements=("E2",)),
        _manifest_relation(
            expected_elements=(("4-1", ("E1", "E2")),),
        ),
    ),
    ids=(
        "id",
        "source-table",
        "targets",
        "compare-key",
        "source-elements",
        "expected-elements",
    ),
)
def test_manifest_consistency_rejects_each_changed_field(
    changed: checker.ManifestRelation,
) -> None:
    expected = _manifest_relation()
    declared = replace(changed, id="R-ONE") if changed.id == "R-TWO" else changed
    document = _manifest_document(declared)
    if changed.id == "R-TWO":
        document = document.replace("R-ONE", "R-TWO")
    assert checker.check_manifest_consistency(document, {expected.id: expected})


def test_element_coverage_is_manifest_driven_and_accepts_target_subsets() -> None:
    relation = _manifest_relation(
        relation_id="R-NEW",
        source_table="2-1 の正本表",
        targets=("3-1 の表", "4-1 の表"),
        source_elements=("E1", "E2"),
        expected_elements=(("3-1 の表", ("E1",)), ("4-1 の表", ("E2",))),
    )
    document = """### 2-1. 正本
| E1 | 一つ目 |
| E2 | 二つ目 |
### 3-1. 伝播先A
| E1 | 一つ目 |
### 4-1. 伝播先B
| E2 | 二つ目 |
"""

    assert checker.check_element_coverage(document, {relation.id: relation}) == ()


def test_element_coverage_detects_missing_element_for_new_relation() -> None:
    relation = _manifest_relation(
        relation_id="R-NEW",
        source_table="2-1 の正本表",
        targets=("3-1 の表",),
        source_elements=("E1", "E2"),
    )
    document = """### 2-1. 正本
| E1 | 一つ目 |
| E2 | 二つ目 |
### 3-1. 伝播先
| E1 | 一つ目 |
"""

    reasons = checker.check_element_coverage(document, {relation.id: relation})

    assert reasons == ("R-NEW: 3-1 の表 にない要素: E2",)


def test_element_coverage_detects_replaced_right_hand_meaning() -> None:
    """識別子を残した意味反転でも右辺の不一致を検出する。"""
    relation = _manifest_relation(
        source_table="2-1 の参加区分表",
        targets=("3-1 の経路表",),
        source_elements=("1:毎球入力=論理位置を持つ",),
    )
    valid = """### 2-1. 参加区分
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
### 3-1. 経路
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
"""
    mutated = valid.replace(
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 論理位置を持つ |",
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 同期順のみ |",
    )

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の経路表 にない要素: 1:毎球入力=論理位置を持つ",
    )


def test_element_coverage_detects_swapped_right_hand_categories() -> None:
    """両識別子と両区分が節内に残る入れ替えを行対応で検出する。"""
    elements = (
        "1:毎球入力=論理位置を持つ",
        "2:undo=従属",
    )
    relation = _manifest_relation(
        source_table="2-1 の参加区分表",
        targets=("3-1 の経路表",),
        source_elements=elements,
    )
    valid = """### 2-1. 参加区分
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
| 2 | undo | 従属 |
### 3-1. 経路
| # | 種別 | 区分 |
| --- | --- | --- |
| 1 | 毎球入力 | 論理位置を持つ |
| 2 | undo | 従属 |
"""
    mutated = valid.replace(
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 論理位置を持つ |\n| 2 | undo | 従属 |",
        "### 3-1. 経路\n| # | 種別 | 区分 |\n| --- | --- | --- |\n"
        "| 1 | 毎球入力 | 従属 |\n| 2 | undo | 論理位置を持つ |",
    )

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    reasons = checker.check_element_coverage(mutated, {relation.id: relation})
    assert reasons == (
        "R-ONE: 3-1 の経路表 にない要素: "
        "1:毎球入力=論理位置を持つ,2:undo=従属",
    )


@pytest.mark.parametrize(
    "mutated_target",
    (
        "| P1 | D1付きイベント | T1・T2・T3・T4 |",
        "| P1 | D1付きイベント | T1・T2・T3・T4 |\n"
        "\n"
        "| 別表の要素 | 内容 |\n"
        "| --- | --- |\n"
        "| T6 | 確定結果 |",
    ),
    ids=("missing", "moved-to-another-row"),
)
def test_element_coverage_detects_missing_or_moved_set_member(
    mutated_target: str,
) -> None:
    """右辺のT要素を欠落させても別行へ移しても検出する。"""
    element = "P1:D1付きイベント=T1,T2,T3,T4,T6"
    relation = _manifest_relation(
        source_table="2-1 の経路表",
        targets=("3-1 の経路表",),
        source_elements=(element,),
    )
    source = """### 2-1. 経路
| 経路 ID | 経路 | T 要素 |
| --- | --- | --- |
| P1 | D1付きイベント | T1・T2・T3・T4・T6 |
"""
    valid = source + """### 3-1. 経路
| 経路 ID | 経路 | T 要素 |
| --- | --- | --- |
| P1 | D1付きイベント | T1・T2・T3・T4・T6 |
"""
    mutated = source + """### 3-1. 経路
| 経路 ID | 経路 | T 要素 |
| --- | --- | --- |
""" + mutated_target + "\n"

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        f"R-ONE: 3-1 の経路表 にない要素: {element}",
    )


def _v12_identifier_case(target_rows: str) -> tuple[checker.ManifestRelation, str]:
    """V12境界の行ID変異に使う関係と文書を作る。"""
    elements = (
        "VF1:P1・P2・P4=V12必須",
        "VF4:P1・P2・P4のV12不成立=B4",
    )
    relation = _manifest_relation(
        source_table="2-1 の V12 条件・結果写像",
        targets=("3-1 の境界表",),
        source_elements=elements,
    )
    source = """### 2-1. V12 条件・結果写像
| 条件 ID | 条件 | 結果 |
| --- | --- | --- |
| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |
"""
    target = f"""### 3-1. 境界
| 条件 ID | 条件 | 結果 |
| --- | --- | --- |
{target_rows}
"""
    return relation, source + target


def test_element_coverage_detects_deleted_identifier_with_meanings_preserved() -> None:
    """左辺・右辺を残して行IDだけを削除しても検出する。"""
    valid_rows = """| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    relation, valid = _v12_identifier_case(valid_rows)
    mutated_rows = """|  | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    _, mutated = _v12_identifier_case(mutated_rows)

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の境界表 にない要素: VF1:P1・P2・P4=V12必須",
    )


def test_element_coverage_detects_swapped_identifiers_with_meanings_preserved() -> None:
    """文書内のID集合を保った行IDの交換でも対応違反を検出する。"""
    valid_rows = """| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    relation, valid = _v12_identifier_case(valid_rows)
    mutated_rows = """| VF4 | P1・P2・P4 | V12 必須 |
| VF1 | P1・P2・P4 の V12 不成立 | B4 |"""
    _, mutated = _v12_identifier_case(mutated_rows)

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の境界表 にない要素: "
        "VF1:P1・P2・P4=V12必須,VF4:P1・P2・P4のV12不成立=B4",
    )


def test_element_coverage_detects_unknown_identifier_with_meanings_preserved() -> None:
    """左辺・右辺を残した未知IDへの置換でも検出する。"""
    valid_rows = """| VF1 | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    relation, valid = _v12_identifier_case(valid_rows)
    mutated_rows = """| VFX | P1・P2・P4 | V12 必須 |
| VF4 | P1・P2・P4 の V12 不成立 | B4 |"""
    _, mutated = _v12_identifier_case(mutated_rows)

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-ONE: 3-1 の境界表 にない要素: VF1:P1・P2・P4=V12必須",
    )


def test_element_coverage_requires_identifier_for_named_element() -> None:
    """``ID:意味句`` も意味句だけではIDの出現を代替できない。"""
    element = "B10:一時障害"
    relation = _manifest_relation(
        source_table="2-1 の境界結果表",
        targets=("3-1 の通知表",),
        source_elements=(element,),
    )
    source = """### 2-1. 境界結果
| ID | 結果 |
| --- | --- |
| B10 | 一時障害 |
"""
    valid = source + """### 3-1. 通知
| ID | 結果 |
| --- | --- |
| B10 | 一時障害 |
"""
    mutated = source + """### 3-1. 通知
| ID | 結果 |
| --- | --- |
|  | 一時障害 |
"""

    assert checker.check_element_coverage(valid, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        f"R-ONE: 3-1 の通知表 にない要素: {element}",
    )


def test_manifest_rejects_source_element_without_any_target(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "R-NEW": {
                    "id": "R-NEW",
                    "source_table": "2-1 の正本表",
                    "targets": ["3-1 の表"],
                    "compare_key": "ID",
                    "source_elements": ["E1", "E2"],
                    "expected_elements": {"3-1 の表": ["E1"]},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(checker.CheckError, match="どこへも伝播しない要素ID.*E2"):
        checker.load_manifest(manifest_path)


@pytest.mark.parametrize(
    ("text", "is_valid"),
    (
        ("要件書 FR-012/E0 を参照する。", True),
        ("docs/legacy/research/data-layer.md:287 を参照する。", True),
        ("docs/legacy/research/data-layer.md:287・同 :288 を参照する。", True),
        ("REQ:287 を参照する。", False),
        ("docs/requirements/a.md:287 を参照する。", False),
        ("docs/requirements/a.md:287・同 :288 を参照する。", False),
        ("要件書:287 を参照する。", False),
    ),
)
def test_citation_format_has_normal_and_abnormal_cases(
    text: str, is_valid: bool
) -> None:
    assert (checker.check_citation_format(text) == ()) is is_valid


def test_citation_format_bare_line_inherits_immediately_preceding_path() -> None:
    legacy = "[原典](../legacy/research/data-layer.md)・同 :287"
    mutable = "[要件](../requirements/requirements.md)・同 :287"
    unknown = "直前の参照先なし :287"

    assert checker.check_citation_format(legacy) == ()
    assert checker.check_citation_format(mutable) == ("裸の行番号",)
    assert checker.check_citation_format(unknown) == ("裸の行番号",)


def test_citation_format_reports_mutable_path_and_inherited_bare_line() -> None:
    text = "docs/requirements/a.md:287・同 :288"

    assert checker.check_citation_format(text) == (
        "<パス>.md:<行番号>",
        "裸の行番号",
    )


def test_citation_format_requirement_line_is_always_invalid() -> None:
    text = "docs/legacy/research/data-layer.md:287・REQ:288"

    assert checker.check_citation_format(text) == ("REQ:<行番号>",)


def test_noncanonical_reference_has_normal_and_abnormal_cases() -> None:
    valid = "## 2. 本文\n要件書 FR-012/E0 を参照する。\n"
    invalid = "## 2. 本文\n[plan](../features/example/plan.md) を正とする。\n"
    assert checker.check_noncanonical_reference(valid) == ()
    assert checker.check_noncanonical_reference(invalid) == (2,)


def test_citation_vocabulary_changes_legacy_path_judgment() -> None:
    text = "custom/archive/evidence.md:12"

    assert checker.check_citation_format(text) == ("<パス>.md:<行番号>",)
    assert checker.check_citation_format(
        text,
        legacy_prefixes=("custom/archive/",),
        legacy_infix="/custom/archive/",
    ) == ()


def test_noncanonical_scan_start_changes_scanned_chapter() -> None:
    text = (
        "## 2. 本文\n"
        "[plan](docs/features/example/plan.md) を参照する。\n"
        "## 3. 後続章\n"
        "要件書を参照する。\n"
    )

    assert checker.check_noncanonical_reference(text) == (2,)
    assert checker.check_noncanonical_reference(
        text,
        scan_start=r"^##\s+3(?:[.\s]|$)",
    ) == ()


def test_declaration_section_changes_manifest_judgment(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    relation = next(iter(manifest.values()))
    document = _manifest_document(relation)

    assert checker.check_manifest_consistency(
        document,
        {relation.id: relation},
    ) == ()
    assert checker.check_manifest_consistency(
        document,
        {relation.id: relation},
        declaration_section="9-9",
    )[0] == "9-9の表間参照宣言表がない"


def test_narrow_section_grammar_rejects_existing_scope(
    manifest: dict[str, checker.ManifestRelation],
    defects: dict[str, checker.Defect],
) -> None:
    valid_text = _FORBIDDEN_CASE_BY_ID["SP-19"][1]

    with pytest.raises(
        checker.CheckError,
        match="scope のトークン『2-1』が節 ID の文法に一致しない",
    ):
        checker.defect_violation_reason(
            defects["SP-19"],
            valid_text,
            manifest,
            section_id_grammar=r"\d+",
        )


def test_link_target_has_normal_and_abnormal_cases(tmp_path: Path) -> None:
    design_dir = tmp_path / "docs" / "design"
    design_dir.mkdir(parents=True)
    (design_dir / "target.md").write_text("target\n", encoding="utf-8")
    assert checker.check_link_targets("[target](target.md)", tmp_path) == ()
    assert checker.check_link_targets("[missing](missing.md)", tmp_path) == (
        "missing.md",
    )


def test_fixture_reports_exact_machine_defect_set(
    defects: dict[str, checker.Defect],
) -> None:
    expected = {key for key, defect in defects.items() if defect.detection == "machine"}
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--defects",
        ",".join(sorted(expected)),
    )
    assert result.returncode == 1
    assert _finding_ids(result) == expected


def test_fixture_default_adds_global_findings(
    defects: dict[str, checker.Defect],
) -> None:
    machine = {key for key, defect in defects.items() if defect.detection == "machine"}
    expected = machine | {
        "citation-format",
        "element-coverage",
        "manifest-consistency",
        "noncanonical-reference",
    }
    result = _run_cli(
        "--document", str(FIXTURE.relative_to(REPOSITORY_ROOT))
    )
    assert result.returncode == 1
    assert _finding_ids(result) == expected


def test_defect_selector_filters_findings() -> None:
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--defects",
        "SP-20",
    )
    assert result.returncode == 1
    assert _finding_ids(result) == {"SP-20"}


def test_check_selector_filters_findings() -> None:
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--checks",
        "order-use",
    )
    assert result.returncode == 1
    assert _finding_ids(result) == {"SP-19", "SP-20"}


def test_combined_selectors_use_intersection() -> None:
    result = _run_cli(
        "--document",
        str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "--defects",
        "SP-02,SP-20",
        "--checks",
        "order-use",
    )
    assert result.returncode == 1
    assert _finding_ids(result) == {"SP-20"}


@pytest.mark.parametrize(
    ("arguments", "message"),
    (
        (("--defects", "SP-99"), "未知の欠陥ID"),
        (("--checks", "unknown-check"), "未知の検査ID"),
        (("--defects", "CI-01"), "人間照合の欠陥ID"),
    ),
    ids=("unknown-defect", "unknown-check", "human-defect"),
)
def test_invalid_selectors_fail(arguments: tuple[str, ...], message: str) -> None:
    result = _run_cli(*arguments)
    assert result.returncode == 2
    assert message in result.stderr


def test_profile_and_default_cli_routes_have_identical_findings() -> None:
    """既定・文書上書き・selector単独を明示profile経路と突合する。"""
    profile_argument = str(PROFILE.relative_to(REPOSITORY_ROOT))
    fixture_argument = str(FIXTURE.relative_to(REPOSITORY_ROOT))

    default_result = _run_cli()
    explicit_profile_result = _run_cli("--profile", profile_argument)
    assert default_result.returncode == explicit_profile_result.returncode == 0
    assert _finding_ids(default_result) == _finding_ids(explicit_profile_result) == set()

    document_result = _run_cli("--document", fixture_argument)
    profile_document_result = _run_cli(
        "--profile",
        profile_argument,
        "--document",
        fixture_argument,
    )
    assert document_result.returncode == profile_document_result.returncode == 1
    assert _finding_ids(document_result) == _finding_ids(profile_document_result)
    assert len(_finding_ids(document_result)) == 21

    checks_result = _run_cli("--checks", "manifest-consistency")
    profile_checks_result = _run_cli(
        "--profile",
        profile_argument,
        "--checks",
        "manifest-consistency",
    )
    assert checks_result.returncode == profile_checks_result.returncode == 0
    assert _finding_ids(checks_result) == _finding_ids(profile_checks_result) == set()


def test_staging_registry_uses_its_profile_document(
    tmp_path: Path,
    defects: dict[str, checker.Defect],
) -> None:
    """外部レジストリが指定したfixtureを実際の検査対象にする。"""
    registry_path = _make_staging_registry(tmp_path, FIXTURE)
    result = _run_cli("--registry", str(registry_path))
    default_result = _run_cli()
    machine = {key for key, defect in defects.items() if defect.detection == "machine"}

    assert result.returncode == 1
    assert default_result.returncode == 0
    assert machine <= _finding_ids(result)
    assert len(machine) == 17
    assert _finding_ids(result) != _finding_ids(default_result)


def test_staging_profile_supplies_link_base_directory(tmp_path: Path) -> None:
    """run_checks経由のリンク検査がprofileのlink_base_dirを使う。"""
    document = tmp_path / "document.md"
    document.write_text("[target](sync-protocol-source.txt)\n", encoding="utf-8")
    link_base_dir = FIXTURE.parent
    registry_path = _make_staging_registry(tmp_path / "staging", document)
    profile_path = registry_path.parent / "x.json"
    profile_value = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_value["link_base_dir"] = str(link_base_dir.resolve())
    _write_json(profile_path, profile_value)

    result = _run_cli(
        "--registry",
        str(registry_path),
        "--checks",
        "link-target",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("option", "default_path"),
    (
        ("--manifest", checker.DEFAULT_MANIFEST),
        ("--defects-file", checker.DEFAULT_DEFECTS),
    ),
    ids=("manifest", "defects-file"),
)
def test_oracle_path_overrides_accept_defaults_and_reject_broken_json(
    tmp_path: Path,
    option: str,
    default_path: Path,
) -> None:
    """manifestとdefects-fileの上書きパスを読み込む。"""
    fixture_argument = str(FIXTURE.relative_to(REPOSITORY_ROOT))
    expected = _run_cli("--document", fixture_argument)
    same = _run_cli(
        "--document",
        fixture_argument,
        option,
        str(default_path),
    )
    assert same.returncode == expected.returncode == 1
    assert _finding_ids(same) == _finding_ids(expected)

    broken = tmp_path / f"broken-{option.removeprefix('--')}.json"
    broken.write_text("{\n", encoding="utf-8")
    invalid = _run_cli(option, str(broken))
    assert invalid.returncode == 2
    assert "check_design_propagation.py:" in invalid.stderr


def test_missing_and_schema_invalid_profiles_fail(tmp_path: Path) -> None:
    """欠落profileと未知フィールドを持つprofileを終了2にする。"""
    missing = _run_cli("--profile", str(tmp_path / "missing.json"))
    assert missing.returncode == 2
    assert "check_design_propagation.py:" in missing.stderr

    profile_value = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile_value["unknown_field"] = True
    invalid_profile = tmp_path / "invalid-profile.json"
    _write_json(invalid_profile, profile_value)
    invalid = _run_cli("--profile", str(invalid_profile))
    assert invalid.returncode == 2
    assert "未知フィールド" in invalid.stderr


def test_registry_with_unregistered_json_fails(tmp_path: Path) -> None:
    """staging profiles内の未登録JSONを終了2にする。"""
    registry_path = _make_staging_registry(tmp_path, DESIGN)
    _write_json(registry_path.parent / "unregistered.json", {})

    result = _run_cli("--registry", str(registry_path))
    assert result.returncode == 2
    assert "未登録" in result.stderr


def test_cli_always_enforces_invariant_binding_rules(tmp_path: Path) -> None:
    """pinが一致していても宣言結合違反なら終了2にする。"""
    registry_path = _make_staging_registry(tmp_path / "staging", DESIGN)
    profile_path = registry_path.parent / "x.json"
    profile_value = json.loads(profile_path.read_text(encoding="utf-8"))
    relation_tree = tmp_path / "relations"
    invariants_path = relation_tree / "invariants" / "x.json"
    schema_path = relation_tree / "schemas" / "invariant.schema.json"
    invariants = checker.doc_check_profile.load_json(
        REPOSITORY_ROOT
        / "scripts"
        / "design_relations"
        / "invariants"
        / "sync-protocol.json"
    )
    invariants["legacy_structural"].append("SP-19")
    _write_json(invariants_path, invariants)
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        (
            REPOSITORY_ROOT
            / "scripts"
            / "design_relations"
            / "schemas"
            / "invariant.schema.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    profile_value["invariants"] = str(invariants_path.resolve())
    _write_json(profile_path, profile_value)
    registry_value = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_value["profiles"][0]["pins"]["invariants_digest"] = (
        checker.doc_check_profile.canonical_digest(invariants)
    )
    _write_json(registry_path, registry_value)

    result = _run_cli("--registry", str(registry_path))
    assert result.returncode == 2
    assert "結合規則3" in result.stderr
    assert "SP-19" in result.stderr


def test_profile_with_unsupported_preamble_fails(tmp_path: Path) -> None:
    """未対応の冒頭切り出し方式をProfileErrorによる終了2にする。"""
    registry_path = _make_staging_registry(tmp_path, DESIGN)
    profile_path = registry_path.parent / "x.json"
    profile_value = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_value["preamble"] = "whole-document"
    _write_json(profile_path, profile_value)

    result = _run_cli("--registry", str(registry_path))
    assert result.returncode == 2
    assert "preamble" in result.stderr


def test_corrected_document_is_green_for_step_four_defects() -> None:
    result = _run_cli("--document", str(DESIGN), "--defects", "SP-20,MT-01")
    assert result.returncode == 0, result.stderr


def test_current_manifest_declaration_is_green() -> None:
    result = _run_cli(
        "--document", str(DESIGN), "--checks", "manifest-consistency"
    )
    assert result.returncode == 0, result.stderr


def test_current_manifest_all_relations_have_element_coverage() -> None:
    result = _run_cli("--document", str(DESIGN), "--checks", "element-coverage")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("relation_id", "source_elements", "expected_elements"),
    (
        (
            "R-TEMP-ID-MAPPING",
            STEP40_TEMP_ID_ELEMENTS,
            {
                "7-1 の A4・A5": (
                    STEP40_TEMP_ID_ELEMENTS[0],
                    STEP40_TEMP_ID_ELEMENTS[2],
                    STEP40_TEMP_ID_ELEMENTS[3],
                ),
                "7-2 の写像確定": (
                    STEP40_TEMP_ID_ELEMENTS[0],
                    STEP40_TEMP_ID_ELEMENTS[3],
                ),
                "8-1 の T6": STEP40_TEMP_ID_ELEMENTS,
                "11-2 のデータモデル影響差分": STEP40_TEMP_ID_ELEMENTS,
            },
        ),
        (
            "R-ORDER-ASSIGN",
            STEP40_ORDER_ELEMENTS,
            {
                "5-3 の隙間・再採番": STEP40_ORDER_ELEMENTS[:2],
                "6-3 の O4境界結果": (STEP40_ORDER_ELEMENTS[2],),
                "7-1 の A5": (STEP40_ORDER_ELEMENTS[2],),
                "7-2 のキュー状態遷移": (STEP40_ORDER_ELEMENTS[2],),
                "8-1 の T5・経路 P2": STEP40_ORDER_ELEMENTS,
                "10-2 の故障系観点": (STEP40_ORDER_ELEMENTS[2],),
                "11-2 のデータモデル影響差分": STEP40_ORDER_ELEMENTS,
            },
        ),
    ),
)
def test_step26_relations_keep_complete_source_and_target_subsets(
    manifest: dict[str, checker.ManifestRelation],
    relation_id: str,
    source_elements: tuple[str, ...],
    expected_elements: dict[str, tuple[str, ...]],
) -> None:
    """追加関係の正本全集合と伝播先別部分集合を固定する。"""
    relation = manifest[relation_id]

    assert relation.source_elements == source_elements
    assert dict(relation.expected_elements) == expected_elements
    assert relation.targets == tuple(expected_elements)


@pytest.mark.parametrize(
    ("relation_id", "source_elements", "expected_elements"),
    (
        (
            "R-EVENT-FIELD",
            STEP40_EVENT_FIELD_ELEMENTS,
            {
                "4-3-A の W3": STEP40_EVENT_FIELD_ELEMENTS,
                "11-2 のデータモデル影響差分": STEP40_EVENT_FIELD_ELEMENTS,
            },
        ),
        (
            "R-P3-BOUNDARY",
            P3_RESULTS
            + STEP38_P3_ORDER_ELEMENTS
            + STEP37_P3_INVALIDATION_ELEMENTS
            + STEP38_P3_RETENTION_ELEMENTS
            + STEP38_RECOVERY_GATE_ELEMENTS,
            {
                "6-2 の P3 処理段階": STEP38_P3_ORDER_ELEMENTS
                + STEP38_RECOVERY_GATE_ELEMENTS,
                "7-1 の P3 応答契約": P3_RESULTS
                + STEP38_P3_ORDER_ELEMENTS
                + STEP37_P3_INVALIDATION_ELEMENTS
                + STEP38_P3_RETENTION_ELEMENTS,
                "8-1 の経路表": (
                    "B8:期待版不一致",
                    "B9:記録権不保持",
                ),
                "8-3 の補正通知": (
                    P3_RESULTS[1:]
                    + STEP38_P3_ORDER_ELEMENTS
                ),
                "8-5 の無効化発火": STEP37_P3_INVALIDATION_ELEMENTS,
                "9-2 の境界表": P3_RESULTS
                + STEP38_P3_ORDER_ELEMENTS
                + STEP37_P3_INVALIDATION_ELEMENTS
                + STEP38_P3_RETENTION_ELEMENTS
                + STEP38_RECOVERY_GATE_ELEMENTS,
                "9-5 の復元時保持・共通前段ゲート": (
                    STEP38_P3_RETENTION_ELEMENTS + STEP38_RECOVERY_GATE_ELEMENTS
                ),
                "10-2 の故障系観点": P3_RESULTS
                + STEP38_P3_ORDER_ELEMENTS
                + STEP37_P3_INVALIDATION_ELEMENTS
                + STEP38_P3_RETENTION_ELEMENTS
                + STEP38_RECOVERY_GATE_ELEMENTS,
                "11-2 のデータモデル影響差分": (
                    STEP37_P3_INVALIDATION_ELEMENTS
                    + STEP38_P3_RETENTION_ELEMENTS
                    + STEP38_RECOVERY_GATE_ELEMENTS
                ),
            },
        ),
    ),
)
def test_step27_relations_keep_complete_source_and_target_subsets(
    manifest: dict[str, checker.ManifestRelation],
    relation_id: str,
    source_elements: tuple[str, ...],
    expected_elements: dict[str, tuple[str, ...]],
) -> None:
    """記録権証明とP3拒否結果の伝播集合を固定する。"""
    relation = manifest[relation_id]

    assert relation.source_elements == source_elements
    assert dict(relation.expected_elements) == expected_elements
    assert relation.targets == tuple(expected_elements)


def test_step27_tombstone_generation_stays_in_queued_participation_group(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """墓標の事前確認条件がD1付きキュー経路から脱落しないことを守る。"""
    relation = manifest["R-PARTICIPATION"]
    tombstone_rule = "K5:墓標生成=オンライン記録権確認後+D1付きキュー"
    tombstone_participation = "8:墓標=同期順のみ"
    revision_participation = "9:改訂版=元イベントの参加区分を継承"

    assert tombstone_rule in relation.source_elements
    assert dict(relation.expected_elements)["6-4 の再開2択"] == (
        tombstone_participation,
        revision_participation,
        tombstone_rule,
    )
    assert dict(relation.expected_elements)["7-2 のキュー状態遷移"] == (
        tombstone_participation,
        revision_participation,
        tombstone_rule,
    )
    assert all(tombstone_rule in elements for _, elements in relation.expected_elements)


def test_step29_manifest_keeps_new_routes_and_required_target_subsets(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """ステップ29で追加・拡張した期待部分集合を弱められないように固定する。"""
    transaction = manifest["R-TXN-ROUTE"]
    rejection_route = "P5:未使用D5の内容拒否=T9"
    rejection_atomic = "T9:未使用D5の内容拒否原本・D5・拒否結果・理由の保存"
    assert rejection_route in transaction.source_elements
    assert rejection_atomic in transaction.source_elements
    assert all(
        rejection_route in elements and rejection_atomic in elements
        for target, elements in transaction.expected_elements
        if target != "10-3 の故障系資産契約"
    )

    change = dict(manifest["R-CHANGE-RULE"].expected_elements)
    for target in (
        "6-2 の P3 処理段階",
        "6-3 の境界結果表",
        "7-1 の P3 応答契約",
        "8-1 の経路表",
        "10-2 の故障系観点",
        "11-2 のデータモデル影響差分",
    ):
        assert STEP40_CHANGE_ELEMENTS[6] in change[target]
    assert STEP40_CHANGE_ELEMENTS[5] in change["6-3 の境界結果表"]

    v12 = manifest["R-V12-BOUNDARY"]
    v12_elements = (
        "VF1:P1・P2・P4=V12必須",
        "VF2:進行中P3=V12必須",
        "VF3:終了後P3=V12不要",
        "VF4:P1・P2・P4のV12不成立=B4",
        "VF5:進行中P3のV12不成立=B9",
    )
    assert v12.source_elements == v12_elements + (STEP37_V12_RECOVERY_ELEMENT,)
    v12_expected = dict(v12.expected_elements)
    assert v12_expected["7-7 のローカル取り込み"] == (
        v12_elements[0],
        v12_elements[3],
    )
    for target in (
        "6-2 の P3 処理段階",
        "6-3 の境界結果表",
        "7-1 の P3 応答契約",
    ):
        assert v12_expected[target] == v12_elements
    for target in ("8-1 の経路表", "9-2 の境界表", "10-2 の故障系観点"):
        assert v12_expected[target] == v12_elements + (
            STEP37_V12_RECOVERY_ELEMENT,
        )
    assert v12_expected["11-2 のデータモデル影響差分"] == (
        STEP37_V12_RECOVERY_ELEMENT,
    )

    participation = manifest["R-PARTICIPATION"]
    participation_expected = dict(participation.expected_elements)
    assert (
        participation_expected["11-2 のデータモデル影響差分"]
        == participation.source_elements
    )


def test_step27_recording_right_proof_keeps_semantic_physical_boundary() -> None:
    """記録権証明が個人IDや未決の物理方式へ置き換わらないことを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    contract = checker._reference_section(document, "4-3 の V1〜V12")
    boundary = checker._reference_section(document, "9-2 の境界表")

    assert "V12 は個人利用者 ID ではない" in contract
    assert all(
        undecided in contract
        for undecided in ("物理形式", "寿命", "端末内の格納先", "更新方法")
    )
    assert "同一テナント・現 D4 でも" in boundary
    assert "V12 が保持端末を証明しない要求を拒否する" in boundary


def test_step27_tombstone_rule_propagates_to_generation_and_queue() -> None:
    """墓標の事前確認とD1付きキュー経路が三つの規範節で一致することを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    for reference in (
        "5-5 の参加区分表",
        "6-4 の再開2択",
        "7-2 のキュー状態遷移",
    ):
        section = checker._reference_section(document, reference)
        assert "K5" in section
        assert "V12" in section
    participation = checker._reference_section(document, "5-5 の参加区分表")
    assert "群 A: D1 付きで端末内キューに載る種別" in participation
    assert "改訂版は群 A のまま、ローカル生成を許す" in participation


def test_step32_all_routes_check_d5_after_authorization_before_versions() -> None:
    """全経路が認可後、記録権・版より先にD5を照合することを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, "6-2 の処理段階")
    d1_routes = section[section.index("P1・P2・P4 の境界結果") :]
    d1_routes = d1_routes[: d1_routes.index("P3 は D1・D3")]

    authorization = d1_routes.index("③ 認可(テナント)")
    idempotency = d1_routes.index("④ D5 の照合")
    recording_right = d1_routes.index("⑤ 記録権(D4・V12)")
    prefix = d1_routes.index("⑥ 連番(D1)の連続性")
    content = d1_routes.index("⑦ 内容の検証")
    assert authorization < idempotency < recording_right < prefix < content
    assert "P1・P2・P4" in d1_routes
    assert "既存 D5・同一内容なら保存済み結果を再掲" in d1_routes


def test_step32_active_p3_checks_d5_after_authorization_before_versions() -> None:
    """P3が認可後、記録権・期待版より先にD5を照合することを守る。"""
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, "6-2 の処理段階")
    active_p3 = section[section.index("P3 は D1・D3") :]

    authorization = active_p3.index("③ 認可(テナント)")
    idempotency = active_p3.index("④ D5 の照合")
    recording_right = active_p3.index("⑤ 記録権証明")
    expected_version = active_p3.index("⑦ V11 の期待版照合")
    assert authorization < idempotency < recording_right < expected_version
    assert "B9 記録権不保持" in active_p3


def test_step35_removed_mechanism_is_absent_and_manifest_is_reduced(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """除去対象が本文とマニフェストへ復活しないことを固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    removed_markers = ("凍結", "リース", "FS", "FT", "B15", "B16", "O3")
    # 本文だけは「リース」を直前の「リ」を除外して照合する。除去対象は
    # 「凍結リース」の状態機械であり、素の部分一致では要件書 8 章の正式名称
    # 「完了条件・リリース判定基準」の引用にも当たって誤検知するため。
    # マニフェスト側は要件書を引用しないので、素の部分一致のまま維持する。
    document_markers = tuple(m for m in removed_markers if m != "リース")
    assert all(marker not in document for marker in document_markers)
    assert re.search(r"(?<!リ)リース", document) is None

    manifest_text = repr(
        [
            (
                relation.id,
                relation.source_table,
                relation.targets,
                relation.source_elements,
                relation.expected_elements,
            )
            for relation in manifest.values()
        ]
    )
    assert all(marker not in manifest_text for marker in removed_markers)

    ack = manifest["R-ACK-STATE"]
    assert ack.source_elements == ("受理", "重複", "拒否", "退避", "未処理")
    assert all(
        elements == ack.source_elements
        for elements in dict(ack.expected_elements).values()
    )

    queue = manifest["R-QUEUE-LIFE"]
    assert queue.source_elements == (
        "未送信",
        "要操作",
        "同期済み",
        "退避済み",
    ) + STEP38_P3_RETENTION_ELEMENTS
    queue_expected = dict(queue.expected_elements)
    for target in ("7-2 の遷移表", "6-3 の保持の記述", "9-5 の回収対象"):
        assert queue_expected[target] == queue.source_elements
    assert queue_expected["11-2 のデータモデル影響差分"] == (
        STEP38_P3_RETENTION_ELEMENTS
    )

    order = manifest["R-ORDER-ASSIGN"]
    assert order.source_elements == STEP40_ORDER_ELEMENTS
    assert dict(order.expected_elements) == {
        "5-3 の隙間・再採番": STEP40_ORDER_ELEMENTS[:2],
        "6-3 の O4境界結果": (STEP40_ORDER_ELEMENTS[2],),
        "7-1 の A5": (STEP40_ORDER_ELEMENTS[2],),
        "7-2 のキュー状態遷移": (STEP40_ORDER_ELEMENTS[2],),
        "8-1 の T5・経路 P2": STEP40_ORDER_ELEMENTS,
        "10-2 の故障系観点": (STEP40_ORDER_ELEMENTS[2],),
        "11-2 のデータモデル影響差分": STEP40_ORDER_ELEMENTS,
    }

    boundary = manifest["R-BOUNDARY"]
    assert boundary.source_elements[:7] == (
        "B1:要求終端",
        "B2:gap",
        "B3:恒久的な内容拒否",
        "B4:記録権不一致",
        "B5:認証失効",
        "B6:認可・テナント不一致",
        "B7:一時障害",
    )
    p3_boundary = manifest["R-P3-BOUNDARY"]
    assert p3_boundary.source_elements == (
        P3_RESULTS
        + STEP38_P3_ORDER_ELEMENTS
        + STEP37_P3_INVALIDATION_ELEMENTS
        + STEP38_P3_RETENTION_ELEMENTS
        + STEP38_RECOVERY_GATE_ELEMENTS
    )


@pytest.mark.parametrize(
    ("before", "after"),
    (
        ("同期済みと同じ 24 時間保持", "同期済みと同じ 48 時間保持"),
        ("退避・閲覧・書き出し対象", "退避・閲覧・書き出し対象外"),
        ("復元規則なし", "復元規則あり"),
    ),
    ids=("retention-period", "escrow-scope", "restore-rule"),
)
def test_step39_queue_life_detects_reversed_i6_contract(
    manifest: dict[str, checker.ManifestRelation], before: str, after: str
) -> None:
    """I6の保持時間・退避・復元規則の反転を完全要素照合で検出する。"""
    relation = manifest["R-QUEUE-LIFE"]
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, "6-3 の保持の記述")
    assert before in section
    mutated_section = section.replace(before, after, 1)
    mutated = document.replace(section, mutated_section, 1)

    assert checker.check_element_coverage(document, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        "R-QUEUE-LIFE: 6-3 の保持の記述 にない要素: "
        f"{STEP38_P3_RETENTION_ELEMENTS[0]}",
    )


def test_step40_manifest_has_no_standalone_identifier_elements(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """単独ID宣言を全関係から排除した状態を固定する。"""
    identifier = re.compile(r"(?:[A-Z]+\d+(?:-[a-z])?|#\d+)")
    standalone = [
        (relation.id, element)
        for relation in manifest.values()
        for element in relation.source_elements
        if identifier.fullmatch(element)
    ]

    assert standalone == []


def test_step40_change_rule_keeps_complete_meaning_elements(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """W1〜W4の定義意味と伝播先別部分集合を完全要素で固定する。"""
    relation = manifest["R-CHANGE-RULE"]

    assert relation.source_elements == STEP40_CHANGE_ELEMENTS
    assert dict(relation.expected_elements) == {
        "5-3 の実行前提": (STEP40_CHANGE_ELEMENTS[6],),
        "5-5 の参加区分表": (
            STEP40_CHANGE_ELEMENTS[0],
            STEP40_CHANGE_ELEMENTS[2],
            STEP40_CHANGE_ELEMENTS[3],
            STEP40_CHANGE_ELEMENTS[4],
        ),
        "6-2 の P3 処理段階": (STEP40_CHANGE_ELEMENTS[6],),
        "6-3 の境界結果表": (
            STEP40_CHANGE_ELEMENTS[3],
            STEP40_CHANGE_ELEMENTS[5],
            STEP40_CHANGE_ELEMENTS[6],
        ),
        "6-4 の再開2択": (STEP40_CHANGE_ELEMENTS[1],),
        "7-1 の P3 応答契約": (STEP40_CHANGE_ELEMENTS[6],),
        "8-1 の経路表": (
            STEP40_CHANGE_ELEMENTS[2],
            STEP40_CHANGE_ELEMENTS[3],
            STEP40_CHANGE_ELEMENTS[5],
            STEP40_CHANGE_ELEMENTS[6],
        ),
        "10-2 の故障系観点": (STEP40_CHANGE_ELEMENTS[6],),
        "11-2 のデータモデル影響差分": (
            STEP40_CHANGE_ELEMENTS[0],
            STEP40_CHANGE_ELEMENTS[2],
            STEP40_CHANGE_ELEMENTS[3],
            STEP40_CHANGE_ELEMENTS[4],
            STEP40_CHANGE_ELEMENTS[5],
            STEP40_CHANGE_ELEMENTS[6],
        ),
    }


@pytest.mark.parametrize(
    ("relation_id", "target", "before", "after", "element"),
    (
        (
            "R-TEMP-ID-MAPPING",
            "7-1 の A4・A5",
            "- **C3**: **ACK 消失後の再送**でも**別の正式 ID**を**重複生成しない**",
            "- **C3**: **ACK 消失後の再送**でも**別の正式 ID**を**重複生成する**",
            STEP40_TEMP_ID_ELEMENTS[2],
        ),
        (
            "R-ORDER-ASSIGN",
            "5-3 の隙間・再採番",
            "局所再採番",
            "末尾採番",
            STEP40_ORDER_ELEMENTS[1],
        ),
        (
            "R-CHANGE-RULE",
            "5-3 の実行前提",
            "**終了後の変更操作**では **V12 を前提にしない**規則",
            "**終了後の変更操作**では **V12 を前提にする**規則",
            STEP40_CHANGE_ELEMENTS[6],
        ),
        (
            "R-EVENT-FIELD",
            "4-3-A の W3",
            "- **V5**: **イベント種別**。**全イベントで無条件**",
            "- **V5**: **イベント種別**。**種別条件付き**",
            STEP40_EVENT_FIELD_ELEMENTS[4],
        ),
    ),
    ids=("temporary-id", "order-assignment", "change-rule", "event-field"),
)
def test_step40_meaning_reversal_is_detected_for_every_relation(
    manifest: dict[str, checker.ManifestRelation],
    relation_id: str,
    target: str,
    before: str,
    after: str,
    element: str,
) -> None:
    """IDを残した意味反転を4関係すべてで検出する。"""
    relation = manifest[relation_id]
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, target)
    assert before in section
    mutated_section = section.replace(before, after)
    mutated = document.replace(section, mutated_section, 1)

    assert checker.check_element_coverage(document, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        f"{relation.id}: {target} にない要素: {element}",
    )


def test_step42_change_rule_detects_swapped_w4_subjects(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """W4の進行中・終了後とV12述語の入れ替えを検出する。"""
    relation = manifest["R-CHANGE-RULE"]
    target = "5-3 の実行前提"
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, target)
    before = (
        "**W4** は、**進行中の変更操作**では **V12 を照合**し、"
        "**終了後の変更操作**では **V12 を前提にしない**規則"
    )
    after = (
        "**W4** は、**進行中の変更操作**では **V12 を前提にせず**、"
        "**終了後の変更操作**では **V12 を照合**する規則"
    )
    assert before in section
    mutated_section = section.replace(before, after, 1)
    mutated = document.replace(section, mutated_section, 1)

    assert checker.check_element_coverage(document, {relation.id: relation}) == ()
    assert checker.check_element_coverage(mutated, {relation.id: relation}) == (
        f"{relation.id}: {target} にない要素: {STEP40_CHANGE_ELEMENTS[6]}",
    )


@pytest.mark.parametrize(
    ("relation_id", "target", "replacement"),
    (
        ("R-QUEUE-LIFE", "7-2 の遷移表", "端末保存時刻を起点"),
        (
            "R-P3-BOUNDARY",
            "7-1 の P3 応答契約",
            "保存済み結果の再掲時刻を起点",
        ),
    ),
    ids=("terminal-persisted-at", "saved-result-replay-at"),
)
def test_step42_i6_detects_changed_retention_origin(
    manifest: dict[str, checker.ManifestRelation],
    relation_id: str,
    target: str,
    replacement: str,
) -> None:
    """I6の保持起点を端末時刻・再掲時刻へ変える変異を検出する。"""
    relation = manifest[relation_id]
    document = DESIGN.read_text(encoding="utf-8")
    section = checker._reference_section(document, target)
    before = "サーバー確定時刻(応答が返す `accepted_at`)を起点"
    assert before in section
    mutated_section = section.replace(before, replacement, 1)
    mutated = document.replace(section, mutated_section, 1)

    assert checker.check_element_coverage(document, {relation.id: relation}) == ()
    errors = checker.check_element_coverage(mutated, {relation.id: relation})
    assert (
        f"{relation.id}: {target} にない要素: {STEP38_P3_RETENTION_ELEMENTS[0]}"
        in errors
    )


def test_step42_recovery_control_plane_includes_atomic_completion() -> None:
    """RG1中に完了遷移だけが条件付きで通る第4群を固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    recovery = checker._reference_section(document, "9-5 の回収対象")
    fault = checker._reference_section(document, "10-2 の故障系観点")

    assert "復旧制御面の **4 群" in recovery
    assert "復旧制御面の完了遷移" in recovery
    assert "未回収 0・期限切れによる欠落なし・退避と閲覧・書き出しの確認完了" in recovery
    assert "RG1 の解除と新しい D4 の開始を不可分に確定" in recovery
    assert "復旧制御面4群" in fault


def test_step42_admin_operation_log_attribution_points_to_real_contract() -> None:
    """管理者操作ログの帰属先を実在する6-5の契約へ固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    attribution = checker._reference_section(document, "11-3")

    assert "| 6.1/管理者操作ログ（Should） | 境界として参照 | 6-5 |" in attribution
    assert "| 6.1/管理者操作ログ（Should） | 境界として参照 | 4-3-A・9-4 |" not in attribution


def test_step35_keeps_fr013_must_and_declares_deferred_should() -> None:
    """退避のMustと現行世代への投入を分離して固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    escrow = document[document.index("### 9-4.") : document.index("### 9-5.")]
    handoff = document[document.index("### 11-4.") : document.index("### 11-5.")]

    assert "旧世代のイベントは**適用されないが破棄されず退避される**" in escrow
    assert "管理コンソール" in escrow
    assert "閲覧・書き出しができる" in escrow
    assert "**Must**" in escrow

    assert "**U-2**" in handoff
    assert "退避イベントの現行世代への取り込み(挿入位置の指定・採番)" in handoff
    assert "**Should**" in handoff
    assert "v0.1 の射程外" in handoff
    assert "退避・非破棄・管理コンソールでの閲覧・書き出し" in handoff
    assert "**RR-1**" in handoff
    assert "**TSK-267**" in handoff
    assert "同一の確定ゲートで一括検証" in handoff

    assert all(element in document for element in ("D8", "B4", "P4", "T8"))
    assert all(element in document for element in ("O1", "O2", "O4"))
    assert "P3" in document


def test_step37_restore_scope_stops_at_fence_and_escrow() -> None:
    """復元時に端末資料から正史へ戻す規則を再導入させない。"""
    document = DESIGN.read_text(encoding="utf-8")
    restore = checker._reference_section(document, "9-5")
    attribution = checker._reference_section(document, "11-3")
    handoff = checker._reference_section(document, "11-4")

    assert "再構成" not in restore
    assert "正史照合" not in restore
    assert "全試合の既存 D4 を失効" in restore
    assert "B4/P4" in restore
    assert "破棄せず退避" in restore
    assert "管理コンソールで閲覧・書き出し" in restore
    assert "復元前に受理済みだったイベントを正史へ戻す規則は v0.1 では決めない" in restore
    assert "端末ストレージは書き換え得る" in restore
    assert "| NFR-009 | 同期側で決める | 9-5・11-4 |" in attribution
    assert "**U-4**" in handoff
    assert "**RR-2**" in handoff
    assert "復元前に受理済みだったイベントを正史へ戻す規則が未定義" in handoff
    assert "起動時刻、担当者、端末回収順、復元調整の解除判断" in handoff
    assert "**NFR-009 の復旧手順**(運用ドキュメント)" in handoff


def test_step37_p3_invalidation_intent_is_atomic_and_eventually_delivered(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """P3確定と無効化意図を分離せず、未配信分を完了まで再試行する。"""
    document = DESIGN.read_text(encoding="utf-8")
    transaction = checker._reference_section(document, "8-1")
    invalidation = checker._reference_section(document, "8-5")
    failures = checker._reference_section(document, "10-2")
    fixture_contract = checker._reference_section(document, "10-3")
    relation = manifest["R-P3-BOUNDARY"]
    transaction_relation = manifest["R-TXN-ROUTE"]

    assert STEP37_P3_INVALIDATION_ELEMENTS[0] in relation.source_elements
    assert dict(relation.expected_elements)["8-5 の無効化発火"] == (
        STEP37_P3_INVALIDATION_ELEMENTS
    )
    assert STEP37_T7_ELEMENT in transaction_relation.source_elements
    assert dict(transaction_relation.expected_elements)[
        "10-3 の故障系資産契約"
    ] == (STEP37_T7_ELEMENT,)
    assert (
        "T7 の無効化意図は P3 の変更イベント・対象確定版更新と同じトランザクション"
        in transaction
    )
    assert "配信完了まで冪等に再試行" in invalidation
    assert "保存済み結果再掲では意図を重複作成しない" in invalidation
    assert "T7 の確定後・無効化配信前" in failures
    assert "消費側反映後・配信完了記録前" in failures
    assert "安定した意図 ID" in failures
    assert "同じ論理無効化" in failures
    assert "故障注入には **T7 確定後・無効化配信前**" in fixture_contract
    assert "保存済み結果再掲後の意図件数" in fixture_contract
    assert "消費側反映状態・配信完了記録状態" in fixture_contract
    assert "同じ安定した意図 ID" in fixture_contract
    assert "p3-invalidation-consumed-before-complete" in fixture_contract
    assert "新しいフィールド・永続化の器・経路を追加しない" in fixture_contract


def test_step38_p3_retention_starts_after_device_persistence(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """I6の開始点、未保護窓、保持期間、退避先を固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    response = checker._reference_section(document, "7-1 の P3 応答契約")
    queue = checker._reference_section(document, "7-2 のキュー状態遷移")
    restore = checker._reference_section(document, "9-5")
    model = checker._reference_section(document, "11-2")
    p3_relation = manifest["R-P3-BOUNDARY"]
    queue_relation = manifest["R-QUEUE-LIFE"]

    for section in (response, queue, restore, model):
        assert all(
            field in section for field in ("対象参照", "V11 の版", "D5", "確定内容")
        )
    assert "初回の変更受理から 24 時間" in response
    assert "端末永続化まで成立した P3 受理結果だけ" in response
    assert "窓は保護しない" in response
    assert "同期済み(P3 受理結果) → 退避済み" in queue
    assert "RG1 中でないことを確認済み" in queue
    assert "期限清掃より先に RG1 を確認" in queue
    assert "P3 として再送せず退避資料として保存" in restore
    assert "管理コンソールで閲覧・書き出し" in restore
    assert "復元規則なし" in restore
    assert STEP38_P3_RETENTION_ELEMENTS[0] in p3_relation.source_elements
    assert dict(p3_relation.expected_elements)[
        "9-5 の復元時保持・共通前段ゲート"
    ][0] == STEP38_P3_RETENTION_ELEMENTS[0]
    assert STEP38_P3_RETENTION_ELEMENTS[0] in queue_relation.source_elements


def test_step37_d4_is_never_reused_after_rollback(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """D4非再利用とV12の復旧世代結合を、物理方式を固定せず保証する。"""
    document = DESIGN.read_text(encoding="utf-8")
    definitions = checker._reference_section(document, "2-1")
    boundary = checker._reference_section(document, "9-2")
    implementation = checker._reference_section(document, "10-1")
    failures = checker._reference_section(document, "10-2")
    fixture_contract = checker._reference_section(document, "10-3")
    v12 = manifest["R-V12-BOUNDARY"]

    assert "ロールバック後も再利用しない識別子" in definitions
    assert "nonce・UUID・バックアップ対象外の単調カウンタ" in definitions
    assert "物理形式は本書で決めず" in definitions
    assert "D4 の非再利用" in boundary
    assert "現 D4・現復旧世代・保持端末" in boundary
    assert "生成アルゴリズム・物理形式" in implementation
    assert "どれを使ったかは期待値に固定しない" in failures
    assert "D4 = 2・4・7" in failures
    assert "過去発行 D4 集合のどの値にも属さない" in failures
    assert "連続した 2 回目の復元" in failures
    assert "過去発行 D4 集合" in fixture_contract
    assert "restore-d4-issued-set" in fixture_contract
    assert "restore-d4-consecutive-rollbacks" in fixture_contract
    assert STEP37_V12_RECOVERY_ELEMENT in v12.source_elements


def test_step39_attribution_follows_restore_contracts() -> None:
    """8周目の追加箇所とDoD ⑥の決定主体を帰属表へ追随させる。"""
    attribution = checker._reference_section(
        DESIGN.read_text(encoding="utf-8"), "11-3"
    )

    assert "| 同期側で決める | 38 |" in attribution
    assert "| 境界として参照 | 82 |" in attribution
    assert "| 対象外 | 92 |" in attribution
    assert "| FR-035 | 境界として参照 | 4-4・9-4・9-5 |" in attribution
    assert (
        "| NFR-015 | 同期側で決める | 6-3・7-1・7-4・8-3・9-2・9-5 |"
        in attribution
    )
    assert "| 8章DoD/6 | 同期側で決める | 9-5・11-4 |" in attribution


def test_step38_recovery_adjustment_gate_is_fail_closed_for_every_write(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """全変更を事前・コミット直前で止め、全数表の空セルを許さない。"""
    document = DESIGN.read_text(encoding="utf-8")
    processing = checker._reference_section(document, "6-2 の処理段階")
    restore = checker._reference_section(document, "9-5")
    boundary = manifest["R-BOUNDARY"]
    p3_boundary = manifest["R-P3-BOUNDARY"]
    gate = STEP38_RECOVERY_GATE_ELEMENTS[0]

    d1 = processing[processing.index("P1・P2・P4 の境界結果") :]
    d1 = d1[: d1.index("P3 は D1・D3")]
    p3 = processing[processing.index("P3 は D1・D3") :]
    for route in (d1, p3):
        assert route.index("③ 認可(テナント)") < route.index("③-a 復元調整ゲート")
        assert route.index("③-a 復元調整ゲート") < route.index("④ D5 の照合")
    assert "進行中・終了後 P3" in restore
    assert "D5 を消費せず" in restore
    assert "通常・緊急の記録権遷移" in restore
    assert "コミット直前にも同じ状態を検証" in restore
    assert "復元調整解除と、過去に発行した値を再利用しない新しい D4" in restore

    table = restore[restore.index("| 変更経路群 | 含む操作 | RG1 中の結果") :]
    table = table[: table.index("\n\n")]
    rows = [
        tuple(cell.strip() for cell in line.strip("|").split("|"))
        for line in table.splitlines()[2:]
    ]
    assert [row[0].strip("*") for row in rows] == [
        "D1 付き同期",
        "変更イベント",
        "試合作成",
        "選手・スタメン・試合設定の変更",
        "通常の管理変更",
        "状態変更を伴う内部ジョブ",
        "通常引き継ぎ",
        "緊急引き継ぎ",
        "復旧制御面の退避",
        "復旧制御面のログ・通知",
        "復旧制御面の閲覧・書き出し",
        "復旧制御面の完了遷移",
    ]
    assert all(len(row) == 4 and all(row) for row in rows)
    assert gate in boundary.source_elements
    assert gate in p3_boundary.source_elements
    for target in (
        "6-2 の D1付き処理段階",
        "9-2 の境界表",
        "10-2 の故障系観点",
        "11-2 のデータモデル影響差分",
    ):
        assert gate in dict(boundary.expected_elements)[target]


def test_step38_all_p3_requests_are_bound_to_the_existing_recovery_generation(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """進行中・終了後P3を既存の復旧世代へ結合し、旧要求を適用しない。"""
    document = DESIGN.read_text(encoding="utf-8")
    change_rule = checker._reference_section(document, "4-3-A")
    processing = checker._reference_section(document, "6-2 の処理段階")
    restore = checker._reference_section(document, "9-5")
    relation = manifest["R-P3-BOUNDARY"]

    assert "全 P3 要求は既存の復旧世代へ結合" in change_rule
    assert "復旧世代は V1〜V12 に追加する新しいイベント値ではない" in change_rule
    assert "③-b 復旧世代の照合" in processing
    assert "旧復旧世代なら、終了後を含め B9" in processing
    assert "復元調整解除後も、復元前の復旧世代を伴う P3" in restore
    assert all(element in relation.source_elements for element in STEP38_P3_ORDER_ELEMENTS)


def test_step37_fr013_must_is_limited_to_escrow_and_admin_access() -> None:
    """FR-013のMustが二つのShouldを無条件に昇格させないことを固定する。"""
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    fr013 = requirements[requirements.index("#### FR-013:") :]
    fr013 = fr013[: fr013.index("#### FR-014:")]
    history = requirements[: requirements.index("## 1.")]

    must_line = next(
        line
        for line in fr013.splitlines()
        if "旧世代の記録権を持つ元端末" in line
    )
    assert "適用されず、破棄されず退避され" in must_line
    assert "管理コンソールで内容を閲覧・書き出しできる" in must_line
    assert "ローカル書き出しは FR-012 の補足 **Should** を採用した場合" in must_line
    assert "退避イベントの取り込みは本条の後段 **Should** を採用した場合" in must_line
    assert "どちらも無条件には要求しない" in must_line
    assert "FR-013 の無注記 Must 基準を優先度どおりに分離" in history
    assert "| 2.4 | 2026-08-30 |" in history


def test_step36_o4_reuses_the_existing_rejection_and_action_state(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """O4が既存の結果値とキュー状態で閉じることを固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    order = checker._reference_section(document, "5-5 の O1・O2・O4")
    boundary = checker._reference_section(document, "6-3 の O4境界結果")
    ack = checker._reference_section(document, "7-1 の A5")
    queue = checker._reference_section(document, "7-2 のキュー状態遷移")

    assert "O4: B3 + A5「拒否」" in order
    assert "要操作(管理者対応待ち)" in order
    assert "O4 の外部結果は B3 と A5「拒否」" in boundary
    assert "理由コード O4" in ack
    assert "O4 では管理者による D2 一意性の是正確認" in queue
    assert "同じ D1 スロットの内容を変えず" in order
    assert "新しい D1 は採番しない" in order

    ack_relation = manifest["R-ACK-STATE"]
    queue_relation = manifest["R-QUEUE-LIFE"]
    order_relation = manifest["R-ORDER-ASSIGN"]
    assert ack_relation.source_elements == ("受理", "重複", "拒否", "退避", "未処理")
    assert queue_relation.source_elements[:4] == (
        "未送信",
        "要操作",
        "同期済み",
        "退避済み",
    )
    for target in (
        "6-3 の O4境界結果",
        "7-1 の A5",
        "7-2 のキュー状態遷移",
        "10-2 の故障系観点",
    ):
        assert dict(order_relation.expected_elements)[target] == (
            STEP40_ORDER_ELEMENTS[2],
        )


def test_step34_d1_order_uniquely_decides_the_external_stop_boundary(
    manifest: dict[str, checker.ManifestRelation],
) -> None:
    """D5先行分類がgap後のB3bを外部結果へ漏らさないことを固定する。"""
    document = DESIGN.read_text(encoding="utf-8")
    boundary = manifest["R-BOUNDARY"]

    assert tuple(
        element for element in boundary.source_elements if element.startswith("DI")
    ) == STEP32_D1_D5_ELEMENTS
    for target in (
        "4-5 の D5衝突分岐",
        "6-2 の D1付き処理段階",
        "7-1 の A5",
        "10-2 の故障系観点",
    ):
        assert tuple(
            element
            for element in dict(boundary.expected_elements)[target]
            if element.startswith("DI")
        ) == STEP32_D1_D5_ELEMENTS

    decision = checker._reference_section(document, "6-3 の境界結果表")
    ack = checker._reference_section(document, "7-1 の A5")
    failures = checker._reference_section(document, "10-2 の故障系観点")
    assert "D5 の全件先行照合は内部候補の分類" in decision
    assert "外部の A5 と停止境界を先取りしない" in decision
    assert "最初に現れる B2 または B3" in decision
    assert "既に B3b と分かっているイベントもすべて「未処理」" in decision
    assert "最初の B2 または B3 で停止" in ack
    assert "gap より後ろの B3b" in failures
    assert "D3 = 4" in failures
    assert "D1 = 6 と D1 = 7 をともに「未処理」" in failures
    assert "B3b を返さず T9 も開始しない" in failures


def test_step34_failure_fixture_contract_can_express_both_p5_branches() -> None:
    """NFR-019(d)のJSON契約でP5・B3a・B3bを明示できることを守る。"""
    section = checker._reference_section(DESIGN.read_text(), "10-3")

    assert "`適用経路`(**P1〜P5**)" in section
    assert "`P5分岐` に **B3a または B3b** を必須" in section
    assert "B3a では未使用 D5 と内容拒否になる原本" in section
    assert "B3b では先着の不変な原本" in section
    assert "同じ D5・異なる内容の後着入力" in section


@pytest.mark.parametrize(
    ("mutation", "reason_part"),
    (
        ("manifest-missing", "left-only=['R-SAMPLE']"),
        ("manifest-extra", "right-only=['R-EXTRA']"),
        ("forbidden-mixed", "forbidden-disjoint-manifest"),
        ("subset", "direct-requirements-subset-claims"),
    ),
)
def test_collection_consistency_reports_exact_subset_and_disjoint_differences(
    tmp_path: Path,
    mutation: str,
    reason_part: str,
) -> None:
    """collection-consistencyの3関係と差集合reasonを固定する。"""
    profile, assets, _, manifest_value, _ = _sample_check_inputs()
    raw_manifest = json.loads(json.dumps(manifest_value))
    if mutation == "manifest-missing":
        raw_manifest["relations"] = []
    elif mutation == "manifest-extra":
        raw_manifest["relations"].append(
            {"id": "R-EXTRA", "source_id": "orders", "target_ids": ["app_role"]}
        )
    elif mutation == "forbidden-mixed":
        raw_manifest["relations"].append(
            {"id": "FORB-REL", "source_id": "orders", "target_ids": ["app_role"]}
        )
    else:
        direct = {
            "schema_version": 1,
            "asset_kind": "direct_requirements",
            "oracle_context": {},
            "ids": ["FR-MISSING"],
        }
        profile = _replace_sample_asset(
            profile,
            tmp_path,
            "direct_requirements",
            direct,
        )
        assets = checker.doc_check_profile.load_assets(profile)

    findings = checker.check_collection_consistency(
        profile,
        assets,
        raw_manifest,
    )
    assert findings
    assert reason_part in "\n".join(finding.reason for finding in findings)


def test_collection_consistency_sample_is_green_and_sync_is_not_applicable() -> None:
    """適合サンプルはgreen、同期は理由付き対象外にする。"""
    profile, assets, _, raw_manifest, _ = _sample_check_inputs()
    assert not checker.check_collection_consistency(profile, assets, raw_manifest)

    result = _run_cli("--checks", "collection-consistency")
    assert result.returncode == 0
    assert "collection-consistency: 対象なし:" in result.stdout


def _forbidden_relation(
    *,
    direction: str,
) -> dict[str, Any]:
    """別名を使った合成禁止関係を返す。"""
    return {
        "id": "FORB-REL",
        "kind": "relation",
        "source": {"namespace": "source", "id": "legacy_orders"},
        "target": {"namespace": "target", "id": "legacy_role"},
        "direction": direction,
        "participants": [
            {"namespace": "source", "id": "legacy_orders"},
            {"namespace": "target", "id": "legacy_role"},
        ],
    }


@pytest.mark.parametrize(
    ("direction", "violated"),
    (("source->target", True), ("target->source", False), ("both", True)),
)
def test_forbidden_structure_normalizes_aliases_and_distinguishes_direction(
    tmp_path: Path,
    direction: str,
    violated: bool,
) -> None:
    """別名で同一の構造を検出し、方向反転だけは区別する。"""
    profile, _, text, raw_manifest, _ = _sample_check_inputs()
    raw = json.loads(json.dumps(profile.raw))
    aliases = raw["assets"]["claims"]["normalize"]["aliases"]
    aliases["source"] = {"legacy_orders": "orders"}
    aliases["target"] = {"legacy_role": "app_role"}
    profile = replace(profile, raw=raw)
    forbidden = checker.doc_check_profile.load_json(
        profile.root / "tests/fixtures/profile-sample/assets/forbidden.json"
    )
    forbidden["entries"][0] = _forbidden_relation(direction=direction)
    profile = _replace_sample_asset(profile, tmp_path, "forbidden", forbidden)
    assets = checker.doc_check_profile.load_assets(profile)

    findings = checker.check_forbidden_structures(
        profile,
        assets,
        text=text,
        raw_manifest=raw_manifest,
    )
    assert bool(findings) is violated
    assert "legacy_orders" not in text
    assert "legacy_role" not in text


def test_forbidden_structure_rejects_zero_extractor_and_sync_is_not_applicable() -> None:
    """抽出0件は入力不正、同期は理由付き対象外にする。"""
    profile, assets, text, raw_manifest, _ = _sample_check_inputs()
    raw_manifest["relations"] = []
    with pytest.raises(checker.doc_check_profile.ProfileError, match="1件も得られません"):
        checker.check_forbidden_structures(
            profile,
            assets,
            text=text,
            raw_manifest=raw_manifest,
        )

    result = _run_cli("--checks", "forbidden-structure")
    assert result.returncode == 0
    assert "forbidden-structure: 対象なし:" in result.stdout


@pytest.mark.parametrize(
    "mutation",
    (
        "empty-map",
        "map-id-missing",
        "map-id-extra",
        "refs-empty",
        "structures-empty",
        "structure-missing",
        "participants-different",
    ),
)
def test_cross_consistency_rejects_auth_map_shape_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    """AUTH mapの空、ID脱落過剰、refs/structures差分をredにする。"""
    profile, _, text, raw_manifest, _ = _sample_check_inputs()
    auth_map = checker.doc_check_profile.load_json(
        profile.root / "tests/fixtures/profile-sample/assets/auth-ddl-map.json"
    )
    entry = auth_map["entries"][0]
    if mutation == "empty-map":
        auth_map["entries"] = []
    elif mutation == "map-id-missing":
        entry["catalog_entry_id"] = "AUTH-MISSING"
    elif mutation == "map-id-extra":
        auth_map["entries"].append(
            {**json.loads(json.dumps(entry)), "catalog_entry_id": "AUTH-EXTRA"}
        )
    elif mutation == "refs-empty":
        entry["ddl_ids"] = []
    elif mutation in {"structures-empty", "structure-missing"}:
        entry["structures"] = []
    else:
        entry["structures"][0]["participants"] = [
            {"namespace": "table", "id": "orders"}
        ]
    profile = _replace_sample_asset(profile, tmp_path, "auth_ddl_map", auth_map)
    assets = checker.doc_check_profile.load_assets(profile)

    assert checker.check_cross_consistency(
        profile,
        assets,
        text=text,
        raw_manifest=raw_manifest,
    )


def test_cross_consistency_checks_wait_text_auth_manifest_and_normal_case() -> None:
    """WAITの本文実在とAUTHのmanifest実在を独立に検査する。"""
    profile, assets, text, raw_manifest, _ = _sample_check_inputs()
    assert not checker.check_cross_consistency(
        profile,
        assets,
        text=text,
        raw_manifest=raw_manifest,
    )

    without_wait = text.replace("orders", "missing")
    wait_findings = checker.check_cross_consistency(
        profile,
        assets,
        text=without_wait,
        raw_manifest=raw_manifest,
    )
    assert any("本文にない" in finding.reason for finding in wait_findings)

    changed_manifest = json.loads(json.dumps(raw_manifest))
    changed_manifest["relations"][0]["target_ids"] = ["other_role"]
    auth_findings = checker.check_cross_consistency(
        profile,
        assets,
        text=text,
        raw_manifest=changed_manifest,
    )
    assert any("射影後AUTH refがmanifestにない" in finding.reason for finding in auth_findings)

    sync_result = _run_cli("--checks", "cross-consistency")
    assert sync_result.returncode == 0
    assert "cross-consistency: 対象なし:" in sync_result.stdout


@pytest.mark.parametrize(
    ("direction", "violated"),
    (("source->target", True), ("target->source", False)),
)
def test_cross_consistency_compares_projected_forbidden_direction(
    tmp_path: Path,
    direction: str,
    violated: bool,
) -> None:
    """製品IDへ射影後の禁止方向だけをredにする。"""
    profile, _, text, raw_manifest, _ = _sample_check_inputs()
    forbidden = checker.doc_check_profile.load_json(
        profile.root / "tests/fixtures/profile-sample/assets/forbidden.json"
    )
    forbidden["entries"][0] = {
        "id": "FORB-REL",
        "kind": "reference",
        "source": {"namespace": "table", "id": "orders"},
        "target": {"namespace": "role", "id": "app_role"},
        "direction": direction,
        "participants": [
            {"namespace": "table", "id": "orders"},
            {"namespace": "role", "id": "app_role"},
        ],
    }
    profile = _replace_sample_asset(profile, tmp_path, "forbidden", forbidden)
    assets = checker.doc_check_profile.load_assets(profile)
    findings = checker.check_cross_consistency(
        profile,
        assets,
        text=text,
        raw_manifest=raw_manifest,
    )
    collided = any("禁止構造と衝突" in finding.reason for finding in findings)
    assert collided is violated


@pytest.mark.parametrize(
    "mutation",
    ("missing-asset", "unmapped", "extra", "ambiguous"),
)
def test_cross_consistency_probe_projection_is_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    """probe-only DDLのproduct写像欠落・過剰・曖昧さを入力不正にする。"""
    profile, _, text, raw_manifest, _ = _sample_check_inputs()
    ddl = checker.doc_check_profile.load_json(
        profile.root / "tests/fixtures/profile-sample/assets/ddl-elements.json"
    )
    ddl["scope"]["product_schema"] = False
    profile = _replace_sample_asset(profile, tmp_path, "ddl_elements", ddl)
    if mutation == "missing-asset":
        raw = json.loads(json.dumps(profile.raw))
        del raw["assets"]["product_ddl_map"]
        profile = replace(profile, raw=raw)
    else:
        product_map = checker.doc_check_profile.load_json(
            profile.root / "tests/fixtures/profile-sample/assets/product-ddl-map.json"
        )
        if mutation == "unmapped":
            product_map["entries"].pop()
        elif mutation == "extra":
            product_map["entries"].append(
                {"ddl_id": "extra", "product_id": "extra"}
            )
        else:
            product_map["entries"].append(
                {"ddl_id": "orders", "product_id": "other_orders"}
            )
        profile = _replace_sample_asset(
            profile,
            tmp_path,
            "product_ddl_map",
            product_map,
        )
    assets = checker.doc_check_profile.load_assets(profile)
    with pytest.raises(checker.doc_check_profile.ProfileError):
        checker.check_cross_consistency(
            profile,
            assets,
            text=text,
            raw_manifest=raw_manifest,
        )


def test_cross_consistency_probe_projection_normal_case(tmp_path: Path) -> None:
    """probe-only DDLで完全なproduct写像を通す。"""
    profile, _, text, raw_manifest, _ = _sample_check_inputs()
    ddl = checker.doc_check_profile.load_json(
        profile.root / "tests/fixtures/profile-sample/assets/ddl-elements.json"
    )
    ddl["scope"]["product_schema"] = False
    profile = _replace_sample_asset(profile, tmp_path, "ddl_elements", ddl)
    assets = checker.doc_check_profile.load_assets(profile)
    assert not checker.check_cross_consistency(
        profile,
        assets,
        text=text,
        raw_manifest=raw_manifest,
    )


def _with_ledger(
    profile: Any,
    invariants: Any,
    tmp_path: Path,
    entries: Any,
) -> Any:
    """global invariantのledgerパスを合成台帳へ差し替える。"""
    path = tmp_path / "ledger.json"
    _write_json(path, entries)
    declaration = dict(invariants.global_invariants[0])
    declaration["ledger"] = str(path)
    return replace(invariants, global_invariants=(declaration,))


@pytest.mark.parametrize("field", checker.doc_check_profile.ASSET_IMMUTABLE_FIELDS)
def test_baseline_digest_detects_every_immutable_field(
    tmp_path: Path,
    field: str,
) -> None:
    """immutable exact-setの各フィールド改変をredにする。"""
    profile, assets, _, _, invariants = _sample_check_inputs()
    entry = next(iter(checker.doc_check_profile.load_json(profile.defects).values()))
    entry = json.loads(json.dumps(entry))
    if field.startswith("invariant."):
        key = field.split(".", 1)[1]
        entry["invariant"][key] = f"changed-{key}"
    elif field == "baseline":
        entry[field] = not entry[field]
    else:
        entry[field] = f"changed-{field}"
    changed = _with_ledger(profile, invariants, tmp_path, [entry])
    assert checker.check_baseline_digest(profile, assets, changed)


@pytest.mark.parametrize("field", checker.doc_check_profile.ASSET_MUTABLE_FIELDS)
def test_baseline_digest_ignores_mutable_fields(tmp_path: Path, field: str) -> None:
    """mutableフィールドの改変はbaseline digestを変えない。"""
    profile, assets, _, _, invariants = _sample_check_inputs()
    entry = next(iter(checker.doc_check_profile.load_json(profile.defects).values()))
    entry = json.loads(json.dumps(entry))
    entry[field] = f"changed-{field}"
    changed = _with_ledger(profile, invariants, tmp_path, [entry])
    assert not checker.check_baseline_digest(profile, assets, changed)


def test_baseline_digest_is_independent_of_json_order_and_rejects_duplicate_key(
    tmp_path: Path,
) -> None:
    """JSONのキー順・空白を無視し、重複キーは入力不正にする。"""
    profile, assets, _, _, invariants = _sample_check_inputs()
    entry = next(iter(checker.doc_check_profile.load_json(profile.defects).values()))
    changed = _with_ledger(profile, invariants, tmp_path, [dict(reversed(entry.items()))])
    assert not checker.check_baseline_digest(profile, assets, changed)

    duplicate = tmp_path / "duplicate-ledger.json"
    duplicate.write_text(
        '{"DEFECT-001":{"id":"DEFECT-001"},'
        '"DEFECT-001":{"id":"DEFECT-001"}}',
        encoding="utf-8",
    )
    declaration = dict(invariants.global_invariants[0])
    declaration["ledger"] = str(duplicate)
    changed = replace(invariants, global_invariants=(declaration,))
    with pytest.raises(checker.doc_check_profile.ProfileError, match="重複"):
        checker.check_baseline_digest(profile, assets, changed)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("duplicate", "重複"),
        ("missing", "expected_idsと不一致"),
        ("extra", "expected_idsと不一致"),
        ("owner", "owner_stepが許可集合外"),
    ),
)
def test_unique_owner_rejects_duplicate_missing_extra_and_invalid_owner(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    """unique-ownerのID集合・重複・owner_step制約を検査する。"""
    profile, assets, _, _, invariants = _sample_check_inputs()
    entry = next(iter(checker.doc_check_profile.load_json(profile.defects).values()))
    entry = json.loads(json.dumps(entry))
    if mutation == "duplicate":
        entries = [entry, json.loads(json.dumps(entry))]
    elif mutation == "missing":
        entries = []
    elif mutation == "extra":
        extra = json.loads(json.dumps(entry))
        extra["id"] = "DEFECT-EXTRA"
        entries = [entry, extra]
    else:
        entry["owner_step"] = "forbidden-step"
        entries = [entry]
    changed = _with_ledger(profile, invariants, tmp_path, entries)
    findings = checker.check_unique_owner(profile, assets, changed)
    assert reason in "\n".join(finding.reason for finding in findings)


def test_unique_owner_requires_global_declaration_expected_ids_and_baseline() -> None:
    """required・global宣言・独立資産の3者不足を入力不正にする。"""
    profile, assets, _, _, invariants = _sample_check_inputs()
    without_global = replace(invariants, global_invariants=())
    with pytest.raises(checker.doc_check_profile.ProfileError, match="global_invariants"):
        checker.check_unique_owner(profile, assets, without_global)

    for missing in ("expected_ids", "baseline_digest"):
        reduced = replace(
            assets,
            assets={name: asset for name, asset in assets.assets.items() if name != missing},
        )
        with pytest.raises(checker.doc_check_profile.ProfileError, match=missing):
            checker.check_unique_owner(profile, reduced, invariants)


def test_unique_owner_rejects_empty_expected_ids_and_sample_is_green(
    tmp_path: Path,
) -> None:
    """空の独立期待集合を拒否し、サンプル適合を固定する。"""
    profile, assets, _, _, invariants = _sample_check_inputs()
    assert not checker.check_unique_owner(profile, assets, invariants)
    empty = {
        "schema_version": 1,
        "asset_kind": "expected_ids",
        "oracle_context": {},
        "ids": [],
    }
    changed_profile = _replace_sample_asset(
        profile,
        tmp_path,
        "expected_ids",
        empty,
    )
    changed_assets = checker.doc_check_profile.load_assets(changed_profile)
    declaration = dict(invariants.global_invariants[0])
    declaration["expected_ids"] = changed_profile.raw["assets"]["expected_ids"]["path"]
    changed_invariants = replace(invariants, global_invariants=(declaration,))
    with pytest.raises(checker.doc_check_profile.ProfileError, match="空"):
        checker.check_unique_owner(
            changed_profile,
            changed_assets,
            changed_invariants,
        )


def test_sample_profile_runs_all_five_new_propagation_checks() -> None:
    """今回実装したデータモデル型のPROP新5検査が適合する。"""
    for check_id in (
        "collection-consistency",
        "forbidden-structure",
        "cross-consistency",
        "baseline-digest",
        "unique-owner",
    ):
        result = _run_cli("--profile", str(SAMPLE_PROFILE), "--checks", check_id)
        assert result.returncode == 0, (check_id, result.stderr)


@pytest.mark.parametrize(
    "check_id",
    ("baseline-digest", "unique-owner"),
)
def test_sync_baseline_and_owner_checks_are_not_applicable(check_id: str) -> None:
    """同期プロファイルは台帳資産なしで理由付き対象外にする。"""
    result = _run_cli("--checks", check_id)
    assert result.returncode == 0
    assert f"{check_id}: 対象なし:" in result.stdout


@pytest.mark.parametrize(
    "target",
    (
        "docs/features/example.md",
        "docs/worklog/example.md",
        "docs/legacy/example.md",
    ),
    ids=("feature", "worklog", "legacy"),
)
def test_reference_class_rejects_unapproved_normative_targets(
    tmp_path: Path,
    target: str,
) -> None:
    """feature・worklog・legacyをnormativeにすると未承認先として拒否する。"""
    profile = checker.doc_check_profile.load_profile(
        SAMPLE_PROFILE,
        root=REPOSITORY_ROOT,
    )
    destination = tmp_path / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("---\nstatus: draft\n---\n", encoding="utf-8")
    document = tmp_path / "document.md"
    raw = json.loads(json.dumps(profile.raw))
    raw["reference_policy"] = {
        "rules": [{"target_pattern": "**", "role": "normative"}]
    }
    changed = replace(profile, root=tmp_path, document=document, raw=raw)

    findings = checker.check_reference_classes(
        f"## 2. test\n\n[参照]({target})\n",
        profile=changed,
        document_path=document,
        root=tmp_path,
    )

    assert len(findings) == 1
    assert "approvedでない" in findings[0].reason


def test_reference_class_uses_first_matching_fragment_rule_in_same_section(
    tmp_path: Path,
) -> None:
    """同一節のリンクをfragmentで分け、最初の一致規則だけを採用する。"""
    profile = checker.doc_check_profile.load_profile(
        SAMPLE_PROFILE,
        root=REPOSITORY_ROOT,
    )
    target = tmp_path / "target.md"
    target.write_text("---\nstatus: draft\n---\n", encoding="utf-8")
    document = tmp_path / "document.md"
    raw = json.loads(json.dumps(profile.raw))
    raw["reference_policy"] = {
        "rules": [
            {
                "source_section": "4-2",
                "target_pattern": "target.md",
                "fragment": "norm-*",
                "role": "normative",
            },
            {
                "source_section": "4-2",
                "target_pattern": "target.md",
                "fragment": "info-*",
                "role": "informative",
            },
            {"target_pattern": "**", "role": "evidence"},
        ]
    }
    changed = replace(profile, root=tmp_path, document=document, raw=raw)
    text = (
        "### 4-2. test\n\n"
        "[規範](target.md#norm-rule) / [情報](target.md#info-rule)\n"
    )

    findings = checker.check_reference_classes(
        text,
        profile=changed,
        document_path=document,
        root=tmp_path,
    )

    assert len(findings) == 1
    assert findings[0].check == "reference-class"


def test_reference_class_rejects_unmatched_external_reference(
    tmp_path: Path,
) -> None:
    """外部URLを含む未分類参照を入力不正にする。"""
    profile = checker.doc_check_profile.load_profile(
        SAMPLE_PROFILE,
        root=REPOSITORY_ROOT,
    )
    raw = json.loads(json.dumps(profile.raw))
    raw["reference_policy"] = {
        "rules": [{"target_pattern": "docs/**", "role": "evidence"}]
    }
    changed = replace(profile, root=tmp_path, raw=raw)

    with pytest.raises(checker.CheckError, match="一致する規則がありません"):
        checker.check_reference_classes(
            "## 2. test\n\n[外部](https://example.com/spec)\n",
            profile=changed,
            document_path=tmp_path / "document.md",
            root=tmp_path,
        )


def test_reference_class_keeps_noncanonical_reference_result_unchanged() -> None:
    """新分類を追加しても既存の非正本参照検査を変更しない。"""
    text = "## 2. test\n\n[候補](docs/features/example.md)\n"
    assert checker.check_noncanonical_reference(text) == (3,)


def test_reference_class_sample_is_green_and_sync_is_not_applicable() -> None:
    """データモデル型では実行し、同期では理由付き対象外にする。"""
    sample = _run_cli("--profile", str(SAMPLE_PROFILE), "--checks", "reference-class")
    sync = _run_cli("--checks", "reference-class")

    assert sample.returncode == 0, sample.stderr
    assert sync.returncode == 0
    assert "reference-class: 対象なし:" in sync.stdout
