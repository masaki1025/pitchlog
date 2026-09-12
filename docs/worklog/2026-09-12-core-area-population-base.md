---
date: 2026-09-12
topic: core-areas 全件登録検査の母集団がブランチに依存し、マージ後の develop で空洞化する欠陥の修正
branch: fix/core-area-population-base
---

# 作業ログ: 2026-09-12 検査の母集団がブランチに依存していた

## やったこと

TSK-343(PR #55)のマージ直後に **develop の `harness` ジョブが red** になったので、
`fix/core-area-population-base` を `origin/develop`(`5b928cb`)から切って直した。

**fast path で実行**(人間の事前 OK を 2026-09-12 に取得)。

## 何が起きていたか

`tests/test_core_guard.py` の `schema_contract_asset_paths()` が `backend/tests/` の母集団を
**版管理の差分**で導出していた。

```python
task_test_files = (
    path
    for path in core_guard.changed_paths(REPO, "origin/develop", "HEAD")
    if path.startswith("backend/tests/")
)
```

**マージ後の develop では `HEAD` が `origin/develop` そのものなので差分が空**になる。実測:

| | 母集団 | うち `backend/tests/` |
| --- | --- | --- |
| feature ブランチ上 | 66 件 | 20 件 |
| develop 上(マージ後) | 46 件 | **0 件** |

つまり **`backend/tests/` について何も検査しなくなる**。負例が `DID NOT RAISE` で落ちて露見した。

## 負例が仕事をした

落ちたのは `test_unregistered_task_test_is_rejected_from_version_control_population` で、
「登録から 1 本外すと red になるはず」を確かめる負例である。

**母集団が空になったため「外しても何も起きない」状態になり、負例が落ちた。**
**負例が無ければ、検査が空洞化したまま誰も気づけなかった。**

PR #55 の差し戻しで「本タスクが新設したテストを 1 つ未登録にすると red になることを
確かめてください」と要求したものが、そのまま自分の欠陥を捕まえた形になった。

## なぜ見落としたか

差し戻しで母集団の切り方を 3 候補から選ばせ、Codex が「版管理の差分から導出」を選んだ。
**私はそれをフィーチャーブランチ上でしか検証しなかった。**

`backend/tests/` の 20 件が正しく拾われることは確認したが、
**マージ後に基準(`origin/develop`)が自分自身になる**ことを考えていない。

これは PR #55 で 4 件記録した「母集団を人が列挙する検査」の延長線上にあるが、
**列挙ではなく「基準の選び方」が原因**という点で少し違う。台帳へ追記する。

## 直した形

```
backend/tests/ 配下で pitchlog.db / schema-manifest / migrations を参照するファイル
  + それらが import する補助モジュール(推移閉包)
```

**検討した案と却下理由**:

| 案 | 結果 |
| --- | --- |
| `pitchlog.db` の import のみ | **14 件**。`test_migration_hygiene.py` など 6 件を取りこぼす |
| 文字列参照のみ(`pitchlog.db` / `schema-manifest.json` / `backend/migrations`) | **17 件**。3 件取りこぼす |
| 参照 + **importer** の推移閉包 | **19 件**。補助モジュール `type_boundary_contract.py` を取りこぼす |
| 参照 + **双方向**の推移閉包 | **41 件**。`conftest.py` 経由で authz 一式まで巻き込む |
| **参照 + import 先の推移閉包**(採用) | **22 件**。20 件をすべて含み、余分は `conftest.py` と `environment_contract.py` の 2 件 |

余分の 2 件は **DB テストの共通基盤なのでコア領域に属すべきもの**で、既存の
`backend/tests/db/*` glob が覆うため検査は通る。

## 検証

**前回抜けていた確認を入れた** — `origin/develop` と同一の HEAD(このブランチの初期状態)で
母集団を数え、`backend/tests/` が **22 件**になることを確認した(旧規則では 0 件)。

- `tests/test_core_guard.py` 55 件 passed
- ルート `ruff check` green / `ty check` green

## 台帳への追記

**該当する。** `/pr` のクローズ処理で判断して追記する。
