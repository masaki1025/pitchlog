---
date: 2026-09-01
topic: コア領域 paths のコード側充填(core-areas.json — H-12 顕在化の是正)
branch: feature/core-area-paths
---

# 作業ログ: 2026-09-01 コア領域 paths のコード側充填

## やったこと

- 2026-09-02: /investigate 実施(調査サブエージェント 3 並列: spec-checker = 帰属判定 / legacy-analyst = 移行領域の現存資産 / decision-tracer = 拘束決定 17 件)。統合者側で PR #33 の実マージ内容(git diff 1ab778f)・`tests/test_core_guard.py` の 3 オラクル・pg-authz 計画 3 節「第 2 群の射程」宣言を原典確認し、`docs/features/core-area-paths/research.md` へ統合(裁定事項 10 件を申し送りに整理)

- 2026-09-02: /plan — 計画書 v1 起草 → 敵対レビュー 1 周目(sol・adversarial): **P0×2 / P1×4 / P2×2・全 8 件採用**(①P0-1 除外の代替統制不成立 → backend/pyproject・docker-compose・vite/vitest config・package.json・tsconfig.app を登録へ、lockfile は `--locked`/`--frozen-lockfile` を典拠に除外維持、ルート pyproject を guard_paths へ ②P0-2 rename 迂回 → core_guard の `--no-renames` 化+故障系テスト+/pr 追随をスコープへ ③P1-1 オラクル構造規定 ④P1-2 逐行確認者 兼 マージ担当 = 山田・SHA 手続詳細化・自己確認フォールバックは既定不採用へ ⑤P1-3 3 節に正本体系外の別枠 ⑥P1-4 ステップ 3 本化+合格条件の個別化 ⑦P2-1 NO_CORE_PATHS_MESSAGE 現行化 ⑧P2-2 表現是正)。`計画レビュー周回: 1`。レビュー全文: セッション scratchpad(plan-review-round1.md)

- 2026-09-02: 敵対レビュー 2 周目: **P0×1 / P1×5 / P2×3・全 9 件採用**(①P0-1 pytest 別設定/conftest 迂回 → CI の pytest へ `-c pyproject.toml` 固定+`backend/*conftest.py`(tenant)・`conftest.py`/`tests/conftest.py`(guard)登録 ②P1-1 lockfile 除外根拠不成立(`--locked` は整合検査のみ)→ 3 lockfile を登録へ ③P1-2 `frontend/tsconfig.json` 登録 ④P1-3 作成者は自己 approve 不能 → approve 担当 = 山田・PO 承認は計画+PR コメント・approve の head 拘束/再 approve 規則 ⑤P1-4 /pr 追随の内容検証(--no-renames・旧新両パスの固定文字列)+rename テストの assert 詳細化+保護外間非発火回帰 ⑥P1-5 遡及処置の完遂を DoD 条件化 ⑦P2-1 別枠へ plan/research 追加・文言是正 ⑧P2-2 ステップ 4 の固定文字列 6 種化+変更履歴アンカー限定 ⑨P2-3 research の authz 件数 17→15 訂正)。ステップは 4 本構成へ(rename-safe / pytest 固定 / paths+オラクル / 文書)。`計画レビュー周回: 2`。レビュー全文: scratchpad(plan-review-round2.md)

- 2026-09-02: 敵対レビュー 3 周目: **P0×0 / P1×5 / P2×2・全 7 件採用**(①P1-1 実行環境ピン 3 件を登録へ〔backend/.python-version→tenant・mise.toml→game-state・ルート .python-version→guard〕→ area +26 / guard +5 ②P1-2 harness pytest の exact オラクルを test_ci_wiring へ新設 ③P1-3 environment-expectations は期待値+CI 参照 provenance を更新(承認済み plan を先行オラクルと宣言・同一コミットで原子更新)④P1-4 worklog の自己確認フォールバックを失効追記(既定 = マージ保留・例外 = PO の代替確認者指名)⑤P1-5 遡及処置はステップ 4 開始前に完遂・PR 後手続から除外 ⑥P2-1 H-12 残余 = 1 件に統一・6.3 条文化は別 follow-up ⑦P2-2 approve 検証 = REST の commit_id == headRefOid・マージ = `gh pr merge --merge --match-head-commit`)。`計画レビュー周回: 3`。レビュー全文: scratchpad(plan-review-round3.md)

- 2026-09-02: 敵対レビュー 4 周目(収束確認): **P0×0 / P1×2 / P2×1・全 3 件採用**(登録集合・件数・実装ステップは収束判定。①P1-1「有効確認者」を定義 — 4 役〔逐行確認・実施記録・approve・マージ〕の一元担当・既定 山田・代替時は PO が氏名+GitHub login を指名記録し 4 役を引き継ぐ。DoD・H-12 文言・固定文字列(7 個目 `有効確認者`)へ接続 ②P1-2 approve 照合を「全ページ取得+有効確認者 login 限定+最新 APPROVED+commit_id==headRefOid+後続 CHANGES_REQUESTED/DISMISSED なし+push 後/マージ直前に再実施」へ強化 ③P2-1 environment-expectations の `source_revision` を承認コミットへ更新する許可差分に追加)。`計画レビュー周回: 4`。レビュー全文: scratchpad(plan-review-round4.md)

- 2026-09-02: 敵対レビュー 5 周目(収束確認): **P0×0 / P1×1 / P2×0・採用**(4 周目反映 3 件は充足判定。残 1 件 = 「山田固定」の残存 3 箇所〔責務移管合意・PR 外部手続の実施記録行・worklog 決定節の 4 役未同期〕を「有効確認者」へ統一 — 移管合意は既定 = 山田本人・代替時は PO 指名裁定が移管承認を兼ねる)。`計画レビュー周回: 5`。レビュー全文: scratchpad(plan-review-round5.md)

- 2026-09-02: 敵対レビュー 6 周目(最終収束確認): **P0×0 / P1×0 / P2×0 — 収束(承認可)**(5 周目 P1-1 の反映は充足判定・反映起因の新規欠陥なし)。周回は増やさない(収束確認周)。計画レビュー合計 = 指摘反映 5 周 + 収束確認 1 周・指摘 28 件全採用。PO 承認待ちへ。レビュー全文: scratchpad(plan-review-round6.md)

## 決定

- **本タスクは移譲せず自分(徳光)で実施する**(2026-09-01・PO 判断)— 理由: 緊急性が高い(H-12 顕在化 — PR #33 が core-guard 非発火でマージ)+ 責任者が自分であるため。もう一人の開発者への役割は、PR #33 コードの帰属判定ヒアリングと PR 段階の逐行確認・承認候補として検討を残す

- **承認手続の指定(2026-09-01・PO 判断)**: 起草・PR 作成 = 徳光 / **逐行確認(実施記録行の記入)= 山田** / 最終承認(PO)= 徳光。恒久規則「**paths 変更 PR の逐行確認は PR 作成者以外の人間が行う**」を計画書の承認手続に明記する(台帳 H-12 残余「具体的な承認者の指定」をこれで畳む)。山田さんの都合がつかない場合の次善 = 実施記録行に「自己確認」と明記+敵対レビュー(sol xhigh)+マージ後の事後確認を DoD 化
- **上記「次善(自己確認)」は失効(2026-09-02・計画レビュー 3 周目 P1-4 の反映)**: GitHub 仕様上 PR 作成者は自分の PR を approve できず、自己確認では approve DoD が成立しないため。**既定 = 山田さん不在時はマージ保留(ブロック)**。例外は **PO が代替の逐行確認者を指名する個別裁定**のみ(plan 4 節・台帳 H-12 の記録と同文言)
- **役割の一般化「有効確認者」(2026-09-02・計画レビュー 4〜5 周目の反映)**: 逐行確認・実施記録行の記入・GitHub approve・マージの **4 役を同一の人間が担う**。**既定 = 山田**。不在時はマージ保留とし、例外は **PO が氏名+GitHub login を worklog と PR コメントへ指名記録**して**代替者が 4 役すべてを引き継ぐ**。pg-authz 第 2 群責務の**移管合意は既定 = 山田本人の確認**、**代替時は PO の指名裁定が移管承認を兼ねる**

- **計画承認(2026-09-02・PO 徳光尋弥)**: 計画レビュー収束(指摘反映 5 周 + 収束確認 1 周・28 件全採用・最終 P0/P1/P2 ゼロ)を受け、実装計画書 v6 を承認。frontmatter を `済(2026-09-02・徳光尋弥)` へ
- **遡及逐行確認の裁定(2026-09-02・PO 徳光尋弥)**: PR #33 マージ済み分への全量遡及は**しない**。**要点確認で代替** — 検査器(`scripts/check_authz_catalog.py`)と `oracle-seal.lock.json` の封印を山田 + 徳光で確認する(authz 15 本は digest 封印済みのため)。**ステップ 4 開始前に完遂**し、対象・確認者・実施日・結果を本 worklog と台帳 H-12 へ記録する

## 未決・次の一歩

- /investigate で下調べ(6.3 境界定義表への当てはめ対象 = PR #33 認可構成・contracts/ 等の棚卸し)→ /plan で計画書
- 上記 PO 判断(承認手続)を /plan で計画書(承認手続・DoD)へ転記し、PR 時に山田さんへ逐行確認を依頼する
- TSK-228 / TSK-254 との統合・取り下げ裁定(TSK-281 コメントに記録済み)
