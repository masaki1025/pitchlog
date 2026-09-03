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

- 2026-09-04: **develop の取り込みと push**: ステップ 1〜3 実装中に develop が 4 PR 進行(#36 設計書 v1.13〔13 章に製品実装節〕/ #37 legacy-frontend-coverage〔台帳 H-12 再発補記〕/ #38 decision-sheet-ruling〔改善台帳 v1.2・H-12 3 件目補記〕/ #39 authz-claims-corpus = TSK-312〔contracts/authz 15 本の改訂・reseal・check_authz_catalog.py 改修・要件書 NFR-018 例外表 2 セル有効化 d485abc〕)。**変更ファイルの重なりゼロ**を確認し、SHA 参照(source_revision・worklog 記録)保全のため rebase でなく **merge で取り込み**(f130f14 — gate-convergence 時の前例方式)。取り込み後 ruff・ty・pytest **875 passed**。山田さん側の準備(②要点確認の事前読解)のためブランチを origin へ push 済み
- 2026-09-04: ステップ 4 への影響メモ: ①台帳 H-12 は補記 2 件が増えた**現行文言を起点に**部分対応化を書く ②遡及要点確認の対象は「現行 develop(#39 反映後)の `check_authz_catalog.py`・`oracle-seal.lock.json`」— #39 の作者も山田さんのため確認は速い見込み ③#36〜#39 も core-guard 非発火のままマージされており(paths 未登録のため構造的に当然)、本 PR の緊急性の裏付けが増えた

- 2026-09-04: **PR #40 の取り込み(2 回目の develop 同期)**: 山田さん側の提案どおり #40(TSK-278 — ADR-003 v0.2・要件書 v2.6・authz 資産 reseal・台帳 H-88 新設/H-85 補記)を先行マージしてもらい、merge 87d8ccd で取り込み(変更ファイルの重なりゼロ・競合なし)。取り込み後 ruff・ty・pytest **875 passed**・push 済み。②遡及要点確認はこの状態(= #40 後の develop 相当)で実施できる

- 2026-09-04: ステップ 1〜4 実装完了(コミット 676f503 / 1e2a7f0 / d4373ec / 1bf690c — 各ステップの合格条件は委任先報告を再現検証)。総合検証: 差分スコープ = 計画 3 節と完全一致(13 ファイル)・check_plan_docs_sync exit 0・harness ゲート(ruff/ty/pytest 875)green。**検出 1 件**: backend 側 `test_environment_expectations.py` の凍結カウント(provenance 総数 24)が出典注記 +1 で red — H-85 型の件数オラクル連鎖。24→25 へ追随し計画 3 節別枠へ宣言追加(ステップ 2 追補)。backend 静的テスト 9 passed・ruff/ty green

## 決定

- **本タスクは移譲せず自分(徳光)で実施する**(2026-09-01・PO 判断)— 理由: 緊急性が高い(H-12 顕在化 — PR #33 が core-guard 非発火でマージ)+ 責任者が自分であるため。もう一人の開発者への役割は、PR #33 コードの帰属判定ヒアリングと PR 段階の逐行確認・承認候補として検討を残す

- **承認手続の指定(2026-09-01・PO 判断)**: 起草・PR 作成 = 徳光 / **逐行確認(実施記録行の記入)= 山田** / 最終承認(PO)= 徳光。恒久規則「**paths 変更 PR の逐行確認は PR 作成者以外の人間が行う**」を計画書の承認手続に明記する(台帳 H-12 残余「具体的な承認者の指定」をこれで畳む)。山田さんの都合がつかない場合の次善 = 実施記録行に「自己確認」と明記+敵対レビュー(sol xhigh)+マージ後の事後確認を DoD 化
- **上記「次善(自己確認)」は失効(2026-09-02・計画レビュー 3 周目 P1-4 の反映)**: GitHub 仕様上 PR 作成者は自分の PR を approve できず、自己確認では approve DoD が成立しないため。**既定 = 山田さん不在時はマージ保留(ブロック)**。例外は **PO が代替の逐行確認者を指名する個別裁定**のみ(plan 4 節・台帳 H-12 の記録と同文言)
- **役割の一般化「有効確認者」(2026-09-02・計画レビュー 4〜5 周目の反映)**: 逐行確認・実施記録行の記入・GitHub approve・マージの **4 役を同一の人間が担う**。**既定 = 山田**。不在時はマージ保留とし、例外は **PO が氏名+GitHub login を worklog と PR コメントへ指名記録**して**代替者が 4 役すべてを引き継ぐ**。pg-authz 第 2 群責務の**移管合意は既定 = 山田本人の確認**、**代替時は PO の指名裁定が移管承認を兼ねる**

- **計画承認(2026-09-02・PO 徳光尋弥)**: 計画レビュー収束(指摘反映 5 周 + 収束確認 1 周・28 件全採用・最終 P0/P1/P2 ゼロ)を受け、実装計画書 v6 を承認。frontmatter を `済(2026-09-02・徳光尋弥)` へ
- **遡及逐行確認の裁定(2026-09-02・PO 徳光尋弥)**: PR #33 マージ済み分への全量遡及は**しない**。**要点確認で代替** — 検査器(`scripts/check_authz_catalog.py`)と `oracle-seal.lock.json` の封印を山田 + 徳光で確認する(authz 15 本は digest 封印済みのため)。**ステップ 4 開始前に完遂**し、対象・確認者・実施日・結果を本 worklog と台帳 H-12 へ記録する

- **遡及要点確認の完遂(2026-09-04)**: 対象 = `scripts/check_authz_catalog.py`・`contracts/authz/oracle-seal.lock.json`(develop `6b9e087` = PR #40 反映後)/ 確認者 = 山田正輝・徳光尋弥 / 実施日 = 2026-09-04 / **所見 = 問題なし**。内訳: ①既定資産 = 要件書 1 + authz 15 で実ファイルと過不足なし ②exact-set は両方向(母集合不足・未登録入力)+ 構造順一致まで検査(`check_authz_catalog.py:1200-1208`)③要件書 blob digest は v2.6(固定元 = dc9d114)と一致・検査器単体 green(ok total=1073)④oracle_commit = dfd523a(#40 reseal)・入力資産 8 本の digest 全一致・封印対象 6 本 ⑤変異実証 = auth-catalog.json への 1 行追記で「oracle input blob 不一致」red → 復元 green(作業ツリー不変)
- **PO 判断(2026-09-04・徳光尋弥)**: 検査器の CI 強制経路は ci.yml の単独ステップではなく **harness ジョブの `uv run pytest tests/` 経由で足りる**と承認(実リポ資産を検査する 2 テストを含み経路は閉じている。本 PR で検査器・テストとも tenant-isolation paths に登録され変更は逐行確認対象になる補完つき)

## 結果サマリ

- **何を実装したか**: ① core-guard の rename-safe 化(`--no-renames` + 故障系 3 種 + /pr 手順追随)② CI pytest の `-c pyproject.toml` 固定(harness exact オラクル新設 + 変異確認)③ **コア領域 paths のコード側充填** — tenant-isolation +10 / game-state +15 / data-migration +1(area 計 +26)+ guard_paths +5。オラクルは領域別辞書完全一致 + ID 重複拒否 + 変更検知 4 系 + glob 境界 2 種 ④ backend 件数オラクル追随(H-85 型連鎖の実測)
- **正本への反映**: 台帳 H-12 を**部分対応**へ(承認手続の決着・遡及完遂・残余 1 件 + 継続論点)+ **H-85 実測補記** / 設計書 10.1 実装追随(版不変)/ 索引現行化
- **統制の実施記録**: 計画 = 敵対レビュー 6 周(指摘 28 件全採用・最終 P0/P1/P2 ゼロ)→ PO 承認 2026-09-02 / 遡及要点確認 = 2026-09-04 完遂・所見 問題なし / PR = 有効確認者(山田)による逐行確認・実施記録行・approve・`--match-head-commit` マージ待ち
- **台帳への追記判断(クローズ処理)**: **該当** — H-12 部分対応(ステップ 4)+ **H-85 へ実測補記**(出典注記 1 件で backend 凍結カウント red — 対応案③の裏付け)。**新規 `H-*` は起票しない**(今回の知見はいずれも既存項目への追記で足りる — 同種の欠陥は既存項目へ集約)

## 未決・次の一歩

- **follow-up 申し送り**: 恒久規則「paths 変更 PR の逐行確認は PR 作成者以外(有効確認者)」の **6.3 への条文化** — 規範の新設 = 確定ゲート事項のため本タスクでは行わず、**次回設計書改訂に合流**する(H-12 残余には含めない — 計画レビュー 3 周目 P2-1 の裁定)
- 総合検証(/check)→ /pr(PR 本文: 逐行確認チェック + 実施記録行〔有効確認者 = 山田さんが記入〕・base/head SHA の PR コメント記録・approve の head 拘束・`gh pr merge --merge --match-head-commit`)→ ③山田さんへ依頼
- TSK-228 / TSK-254 との統合・取り下げ裁定(TSK-281 コメントに記録済み・PO 裁定待ち)
- 文書のみタスクで paths が原理的に非発火の件の運用規則化の要否 — 台帳 H-12 の継続論点(本タスク外)
- `contracts/README.md` の authz 系未記載(索引未追随)— 申し送り(research.md 5 節)
