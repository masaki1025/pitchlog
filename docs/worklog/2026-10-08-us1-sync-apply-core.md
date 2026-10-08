---
date: 2026-10-08
topic: U-S1 同期適用核 — べき等キー・連番と採番の不可分性・墓標/改訂(TSK-391)
branch: feature/us1-sync-apply-core
---

# 作業ログ: 2026-10-08 U-S1 同期適用核 — べき等キー・連番と採番の不可分性・墓標/改訂(TSK-391)

## やったこと

### /task-start(2026-10-08・455 タブから切り替え)

- Notion TSK-391 を 進行中 へ。ブランチ `feature/us1-sync-apply-core`(起点 develop `1fdf1eec`)
- カードの出所は TSK-363(`docs/features/product-impl-unit-split/plan.md`。2026-09-13 承認)。帯 1(核)。主所有 FR-012
- コア判定: sync-protocol × recording-rights の重複帰属(`docs/features/product-impl-unit-split/design.md:101`)。レビューは敵対レビュー + 人間の逐行確認
- 依存先 U-T1(TSK-390)は Notion で「完了」と再確認した。U-T1 から分離した TSK-424(製品認可面)は「確認待ち」
- 前のタスク TSK-455 は `feature/vitest-vector-runner` の `b181b261` まで(調査済み・/plan 前)で中断した。Notion のステータスは 進行中 のまま

### 469 master からの衝突面の実測(2026-10-08)

- core-areas.json の追加窓口(`AREA_PATH_ADDITIONS`。`scripts/core_guard.py` の 310 行付近で回転式)には、236 と UM01 の 2 本がすでに乗っている。U-S1 が 3 本目を足すと、どの順でマージしても途中で赤になる
- UM01 が `backend/tests/test_*_boundary.py` と `backend/tests/test_*_repository.py` の glob を追加中(人間承認済み)。U-S1 の越境テストをこの命名に合わせれば、core-areas.json に触れずに済む可能性がある。ただし DoD の「重複帰属の明示」に JSON の変更が要るかは、別に切り分ける
- 同期適用核を触っている他タブはない(backend 側に同期適用核は存在しない)。`frontend/src/lib/sync/` の契約の写しと検査器を先に読む
- TSK-455 の Notion ステータスは 469 master が「保留中」に変えた
- 見積り: 13pt はコードの量で、計画レビューと承認の日数は別にかかる(他単位の実績は 1〜9 周)

### /investigate(2026-10-08)

- spec-checker・decision-tracer・Explore の 3 本を並列で実行し、`research.md` に統合した。決定的な主張 5 件は原典で確認した(transaction.py:109-113 が Select 限定、base-allowlist.json:8102-8113 の TB002、sync-server-apply/plan.md:60-66 の TSK-330 受け取り、DM:803-812 の C10、TSK-330/331/332/392 の Notion ステータス)
- 要旨: サーバー側の適用実装は TSK-330 が受け取り先(未着手)で、U-S1 との線引きがない。機構の詰まりは TB002・Select 限定・core-areas の窓口の 3 つ。依存は記録権の判定(U-R1)と状態遷移(U-X1・凍結中)が逆向き。裁定事項は R-1〜R-8

## 決定

## 未決・次の一歩

- /investigate で下調べ → /plan
