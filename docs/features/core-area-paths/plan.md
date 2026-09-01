---
feature: core-area-paths
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-02・徳光尋弥) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3ce93b75e68781d8a73aff23b8c1ead7
branch: feature/core-area-paths
created: 2026-09-01
計画レビュー周回: 5        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: コア領域 paths のコード側充填(core-areas.json — H-12)

## 1. 背景・目的

`.claude/core-areas.json` の `areas[].paths` は文書 2 本のみ(data-migration は空)で、コア領域統制(敵対レビュー + 人間逐行確認)がコード変更に対して空回りしている(台帳 [H-12](../../development/harness-evaluation.md))。2026-08-31 の PR #33(pg-authz-verification)で認可構成の初コード群が core-guard 非発火・逐行確認なしでマージされ顕在化した([research.md](research.md) 3 節)。本タスクは、現存する実装資産を設計書 6.3 の境界定義表([dev-harness-design](../../development/dev-harness-design-2026-08-07.md) `:354-365`)へ当てはめて paths を充填し、あわせて計画レビューで発見された **rename による core-guard 迂回**と **pytest 設定・conftest 経由の検査迂回**を塞いで、統制を実効化する。

- Notion タスク: [TSK-281 コア領域 paths のコード側充填](https://app.notion.com/p/3ce93b75e68781d8a73aff23b8c1ead7)(優先度 高・C1 緊急裁定 — `docs/features/gate-convergence-rules/plan.md:47`)
- 保護対象の要件: 境界定義表が参照する FR-013(記録権)/ FR-033〜035・037・041・042(テナント分離)/ 4.0-4・付録E・FR-040・FR-007(状況計算)/ FR-038・FR-031・付録D(データ移行)。統制自体の根拠 = NFR-019(検証必須)・NFR-018(c) 例外表(座標変換 spec の一致固定 — 要件書 `:906`)
- 下調べの正: [research.md](research.md)(3 エージェント調査 + 原典確認。裁定事項 10 件は本計画 4 節で確定)

## 2. スコープ

### やること

- **core-guard の rename-safe 化**(計画レビュー 1 周目 P0-2): `scripts/core_guard.py` の変更パス取得を rename 非追跡(`--no-renames`)へ改める + 故障系テスト 3 種(保護内→外は**旧パス**で発火 / 保護外→内は**新パス**で発火 / 保護外→保護外は非発火)+ `/pr`「3. 作成」手順 2 のコア判定(`.claude/skills/pr/SKILL.md`)へ「`--no-renames` で旧・新両パスを base 側 core-areas.json(`git show origin/develop:.claude/core-areas.json`)へ突合する」を追随 + `NO_CORE_PATHS_MESSAGE` の「Phase 4 で定義予定」文言の現在形化(P2-1)
- **pytest 実行経路の固定**(計画レビュー 2 周目 P0-1・3 周目 P1-2/P1-3): CI の pytest 2 呼び出し(harness `ci.yml:85`・backend `ci.yml:220`)へ `-c pyproject.toml` を付与し、別設定ファイルによる検査対象の差し替えを遮断 + `tests/test_ci_wiring.py` へ **harness ジョブの pytest コマンドの完全一致オラクルを新設**(`uv run pytest -c pyproject.toml tests/` と `uv run pytest -c pyproject.toml --cov` の 2 本を exact 固定・harness = リポジトリルート / backend = `working-directory: backend` の構造検査つき)+ `backend/tests/db/environment-expectations.json` の**期待コマンド値と CI 参照の `provenance.extracted_text`** を追随(**本計画 4 節の確定コマンドを先行オラクルとする** — 出典注記を provenance に記し、`source_revision` は本計画の承認〔起票〕コミットへ更新する)
- `areas[].paths` へのコード側パスの**追加**(4 節の確定表 — **5 領域の定義を維持し、うち 3 領域へ計 26 パスを追加**。既存登録の削除・縮小はしない〔ADR-003 `:354`〕)。conftest 経由の収集迂回(`backend/*conftest.py`)と実行環境ピン(`backend/.python-version`・`mise.toml` — 3 周目 P1-1)を含む
- **guard_paths へ 5 パスを追加**(ルート `pyproject.toml`・`uv.lock`・`.python-version`・`conftest.py`・`tests/conftest.py` — ハーネス検査の実行制御点。conftest 2 件は現存しないが、**将来の新設がそのまま検知対象になる**〔照合は diff のパス文字列に対して行われるため〕)
- `core-areas.json` の `description`(冒頭)の現行化(「Phase 4 のコード骨格確定時に埋める」→ 実装追随で 6.3 規則により更新する旨へ)
- `tests/test_core_guard.py` の期待値追随(**領域別期待集合の辞書完全一致 + 領域 ID 重複拒否**)+ 新規 paths の変更検知ケース + glob 境界テスト
- 台帳 H-12 の**部分対応**化(残余 =「13 章 Phase 4 完了条件への組み込み」**1 件**)+ **設計書 10.1 の実装追随**(pytest コマンド行 — 節更新・版は上げない)+ 索引現行化(日付 + 状態要約)+ worklog 更新
- pg-authz 計画「第 2 群(計画改訂 2)」が留保していた tenant-isolation 登録責務の本タスクへの移管を記録(4 節)
- **申し送りの起票**(worklog 記録): 恒久規則「paths 変更 PR の逐行確認は PR 作成者以外」の**6.3 条文化**は H-12 残余ではなく**別 follow-up**として次回設計書改訂に合流させる(3 周目 P2-1 — H-12 の元来の残余「具体的承認者の指定」は山田指定で解消するため)

### やらないこと

- **設計書 6.3・13 章の改訂**(規範変更 = 確定ゲート〔7.6-3 後段〕)。設計書への反映は 10.1 の実装追随(ci.yml のコマンド変更の追随 — `:667`)**のみ**。core_guard の rename-safe 化はアルゴリズム詳細で、**設計書に該当記述が存在しないことを確認済み**(`name-only|rename|no-renames` の grep 実測)
- `contracts/README.md` への authz 系追記(索引未追随 — 申し送り。worklog に記録)
- NFR-018(c) 例外表の現行化(**TSK-270 へ合流済み** — `docs/features/course-coordinate-contract/plan.md:156-183`)
- マージ済み文書(pg-authz 計画書等)の遡及編集(歴史記録は書き換えない)
- TSK-228 / TSK-254 の Notion 整理(統合・取り下げは PO 裁定 — TSK-281 コメントで依頼済み)
- **製品コード(`backend/src/**`・`frontend/src/**`・`contracts/**`)の変更**(1 行も変えない — paths に**登録**するだけ。変更するのはハーネス側: `scripts/`・`tests/`・`.claude/`・`.github/workflows/ci.yml`・`backend/tests/db/environment-expectations.json` と正本 3 点)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| [ハーネス運用評価台帳](../../development/harness-evaluation.md) | **H-12 を部分対応へ**(①コード側 paths の充填と rename-safe 化の実施 ②承認手続の決着〔PO 判断 2026-09-01: 逐行確認 = PR 作成者以外。有効確認者 = 既定 山田・不在時は PO 指名の代替者(それまでマージ保留)〕③PR #33 遡及裁定の結果 ④残余 =「13 章 Phase 4 完了条件への組み込み」**1 件**へ絞り込み)+ 変更履歴 1 行。**版は上げない・`H-*` 新規採番なし**(7.6-3 前段) | PRレビュー |
| [開発ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) | **10.1 の実装追随のみ**: CI ジョブ表の harness・backend 行の pytest 呼び出しへ `-c pyproject.toml` を追随(`:667` ほか該当行)+ 変更履歴 1 行。**節更新・版は上げない**(実装追随 — 7.6-3 前段) | PRレビュー |
| [docs/README.md](../../README.md)(索引) | 台帳行と設計書行の**最終更新日**、台帳行の**状態要約**(H-12 補記 → 部分対応)を現行化 | PRレビュー |
| 要件書・ADR・`docs/design/**`・CLAUDE.md・AGENTS.md | **反映なし**(理由は 2 節「やらないこと」— 確認済み) | — |

**正本体系外だが同一 PR で更新するもの**(/pr 突合の別枠宣言 — `.claude/skills/pr/SKILL.md` 手順 2-2):

| ファイル | 変更内容 |
| --- | --- |
| `.claude/core-areas.json` | paths 充填(4 節の確定表: area +26 / guard_paths +5)+ description 現行化。**guard_paths 該当** |
| `scripts/core_guard.py` | rename-safe 化(`--no-renames`)+ `NO_CORE_PATHS_MESSAGE` 現在形化。**guard_paths 該当** |
| `tests/test_core_guard.py` | 期待値追随・故障系/境界テスト追加。**guard_paths 該当** |
| `.claude/skills/pr/SKILL.md` | コア判定手順の rename 突合追随。**guard_paths 該当** |
| `.github/workflows/ci.yml` | pytest 2 呼び出しへ `-c pyproject.toml`(各 1 行)。**guard_paths 該当** |
| `tests/test_ci_wiring.py` | 期待コマンド追随 + **harness ジョブの exact オラクル新設**。**guard_paths 該当** |
| `backend/tests/db/environment-expectations.json` | 期待コマンド値(`single_command.expected`)と CI 参照の `provenance.extracted_text` の追随 + `source_revision` を本計画の承認(起票)コミットへ更新(出典 = 本計画 4 節の注記つき) |
| `docs/worklog/2026-09-01-core-area-paths.md` | 経緯・裁定の記録(遡及処置の完遂記録を含む) |
| `docs/features/core-area-paths/plan.md`・`research.md` | 本計画・調査メモ(起票コミットで追加) |

## 4. 実装方針

### 重さ分類の根拠 — コア領域

コア領域 5 領域の**製品実装コードには 1 行も触れない**。しかし変更対象はコア領域ガードの定義と検知機構そのもの(`core-areas.json` + `core_guard.py` + 完全一致オラクル + CI 実行経路)であり、誤った充填・誤った検知は**全領域の統制喪失に直結**する。6.3-⑤ が敵対レビュー + 人間承認を明示要求していることとあわせ、保守側に倒して**コア領域**(sol xhigh・敵対レビュー・人間逐行確認)を適用する。

### 6.3-⑤ の充足経路と承認手続(宣言)

- **敵対レビュー**: 計画 = `codex_run.py review adversarial`(実施中 — 周回は frontmatter)/ 実装 = /implement(ADR-001 コア領域行)+ PR の敵対レビュー
- **有効確認者(4 役の一元担当)**: **逐行確認・実施記録行の記入・GitHub approve・マージの 4 役を同一の人間**が担う(github-setup 2 章 v1.2 手続 3「マージ担当者自身が逐行確認しチェック・実施記録行を記入」— `docs/development/github-setup.md:40`)。**既定 = 山田**。**PR 作成者(徳光)は GitHub 仕様上自分の PR を approve できない**ため作成者は担えない(PO 判断 2026-09-01 の「逐行確認は PR 作成者以外」と整合 — [worklog 決定節](../../worklog/2026-09-01-core-area-paths.md))
- **approve の head 拘束と検証方法**: approve は**記録済み head SHA と同一 commit に対して**行う。検証は GitHub Reviews API で**レビューを全ページ取得**し(既定 30 件のページングに注意)、**有効確認者の GitHub login に限定**した上で、**その最新レビューが `APPROVED` かつ `commit_id` == PR の `headRefOid`** であり、**同確認者による後続の `CHANGES_REQUESTED` / `DISMISSED` がない**ことを照合する(`gh api repos/{owner}/{repo}/pulls/{n}/reviews`)。**push 後とマージ直前に同じ照合を再実施**する
- **マージコマンドの固定**: `gh pr merge --merge --match-head-commit <記録済み head SHA>`(マージ方式 = merge commit・head 拘束つき)
- **PO 承認(徳光)の記録媒体**: ①本計画の承認(frontmatter `承認: 済` + 起票コミット)②PR 上の「PO 承認」コメント(approve レビューは作成者不可のためコメントで残す)
- **山田さん不在時は原則マージ保留(ブロック)**: 自己確認による代替は**不成立**(GitHub 仕様上 approve できず DoD を満たせない)。例外は **PO が代替の有効確認者を指名する個別裁定**のみ — 指名時は**氏名と GitHub login を worklog と PR コメントへ記録**し、**代替者が 4 役すべてを引き継ぐ**(2026-09-01 の「次善 = 自己確認」記載は計画レビュー 3 周目で**失効**させ、worklog に追記済み)
- **マージ手続**(github-setup 2 章 v1.2 手続 2・3): 確認時 base/head SHA の **PR コメント記録** → base SHA 3 点一致(CI 検査 test merge の第一親 = 確認時 base = マージ直前 base〔取得元固定〕)→ 上記マージコマンド。**実施記録行の記入後の push・本文編集後は最新 HEAD で全必須ジョブ green を再確認**
- 恒久規則「**paths 変更 PR の逐行確認は PR 作成者以外の人間が行う**」は台帳 H-12 対応案へ**記録**する(**6.3 への条文化は H-12 残余とは別の follow-up** — 次回設計書改訂に合流。3 周目 P2-1)

### 検査迂回の閉塞(計画レビュー 1 周目 P0-2・2 周目 P0-1・3 周目 P1-1〜P1-3)

1. **rename 迂回**: `scripts/core_guard.py` の変更パス取得(`git diff --name-only base...head`)は rename 検出時に新パスしか返さない。`--no-renames` を付与して rename を**削除(旧パス)+ 追加(新パス)の対**として列挙させる(guard_paths の完全一致照合も同じ取得結果を使うため、この 1 箇所で両方が rename-safe になる)
2. **pytest 設定迂回**: pytest は `pytest.ini`・`pytest.toml` 等を `pyproject.toml` より優先するため、保護外の別設定ファイル新設で `testpaths` を差し替えられる。CI の pytest 呼び出しを **`-c pyproject.toml` で固定**して代替設定を無効化し(pyproject.toml は本計画で保護)、**固定自体を `test_ci_wiring.py` の exact オラクルで恒久化**する(3 周目 P1-2 — 現行は backend コマンドのみ厳密比較で harness 側は未検証)
3. **conftest 迂回**: 親 conftest の `pytest_ignore_collect` 等で保護テストの収集を外せる。**`backend/*conftest.py` を tenant-isolation へ、ルートの `conftest.py`・`tests/conftest.py` を guard_paths へ登録**し、既存・将来の conftest 変更を検知対象にする
4. **実行環境の差し替え**(3 周目 P1-1): 検査を実行するランタイムのピン(`backend/.python-version`・ルート `.python-version`・`mise.toml`)は CI の `uv python install`・mise 導入が読む(`ci.yml:69,143,202`・設計書 `:204,:216`)。lockfile と同じ理由で保護する

### 登録集合(確定表 — 帰属根拠は [research.md](research.md) 2 節 + 計画レビュー 1〜3 周目の反映)

**tenant-isolation へ追加(+10)**(既存の文書 2 本は維持):

| パス(glob) | 判定 |
| --- | --- |
| `contracts/authz/*` | 確実(認可主張母集合・行列・封印の 15 本 — 6.3 `:361` + 規則①) |
| `scripts/check_authz_catalog.py` | 確実(強制点) |
| `tests/test_check_authz_catalog.py` | 確実(強制点のテスト) |
| `tests/fixtures/authz_claims/*` | 確実(凍結フィクスチャ) |
| `backend/tests/db/*` | fail-closed 採用(越境テストの受け皿 — pg-authz 計画 3 節が本領域資産と宣言) |
| `backend/pyproject.toml` | fail-closed 採用(pytest 収集範囲・`requires_db` マーカーの制御点) |
| `backend/uv.lock` | fail-closed 採用(`uv --locked` は整合検査のみ — 制約内の lock 単独再解決は通る) |
| `backend/*conftest.py` | fail-closed 採用(収集迂回の閉塞 — 既存 `backend/tests/conftest.py` と将来の新設を包含) |
| `backend/.python-version` | fail-closed 採用(backend 検査のランタイムピン — `uv python install` が読む) |
| `docker-compose.yml` | fail-closed 採用(DB 環境期待値の provenance) |

**game-state へ追加(+15)**(既存の文書 2 本は維持):

| パス | 判定 |
| --- | --- |
| `frontend/src/lib/courseInputView.ts` | 確実(座標変換 — NFR-018(c) 例外表が名指し) |
| `frontend/src/lib/displayGeometry.ts` | 確実(座標系定数・幾何計算) |
| `frontend/src/lib/spatialInput.ts` | 確実(座標域クランプ — 規則②で全体) |
| `frontend/src/components/zone/StrikeZone.vue` | 確実(画面→保存座標の変換 — 規則②) |
| `frontend/src/lib/courseCoordinateContract.spec.ts` | 確実(契約テスト — course-coordinate からの引き渡し) |
| `frontend/src/lib/displayGeometry.spec.ts` | 確実(契約値固定テスト) |
| `frontend/src/components/zone/StrikeZone.spec.ts` | fail-closed 採用(変換コンポーネントのテスト) |
| `contracts/display_geometry_263_v1.json` | 確実(②参照データ契約 — ADR-003 `:250`) |
| `frontend/vite.config.ts` | fail-closed 採用(`@contracts` エイリアスの解決点) |
| `frontend/vitest.config.ts` | fail-closed 採用(同・テスト側) |
| `frontend/package.json` | fail-closed 採用(`"test"` スクリプトの実行制御 — 規則②で全体) |
| `frontend/tsconfig.app.json` | fail-closed 採用(`@contracts` の型解決側) |
| `frontend/tsconfig.json` | fail-closed 採用(vue-tsc の入口 — 継承・include の差し替えで型検査を空洞化できる) |
| `frontend/pnpm-lock.yaml` | fail-closed 採用(`--frozen-lockfile` は整合検査のみ) |
| `mise.toml` | fail-closed 採用(frontend 検査の Node ランタイムピン — `ci.yml:143` が読む。設計書 `:216` が Node 版固定の正と定義) |

**data-migration へ追加(+1)**: `frontend/src/lib/format.ts` — fail-closed 採用(88 列契約の試合日時形式を実装する唯一の現存コード。未使用・逐語移植だが「変え得るファイル」として含む側。文書は追加しない — 負のオラクル `tests/test_core_guard.py:329-335` と `docs/design/sync-protocol.md:210` の移行対象外宣言のとおり)

**sync-protocol / recording-rights**: 追加なし(登録できる実装コードが現存しない — research.md 2 節の実測。文書 2 本の既存登録を維持)

**guard_paths へ追加(+5)**: ルート `pyproject.toml`(ハーネス pytest・ruff・ty の設定)/ ルート `uv.lock`(整合検査のみのため lockfile 自体を保護)/ ルート `.python-version`(ハーネス検査のランタイムピン)/ `conftest.py`・`tests/conftest.py`(現存しないが将来の新設を検知 — ハーネス検査の収集制御点)。単一領域に属さないため area paths ではなく guard_paths〔検査経路〕へ

### 除外の確定(通常レビューに留めるもの — 除外理由と代替統制)

| パス | 除外理由 / 代替統制 |
| --- | --- |
| `frontend/.prettierignore` | 逐語性が壊れる変更(再整形)は保護対象ファイル自身の diff として現れ、そのファイルは paths 登録済 |
| `docs/features/pg-authz-verification/probe/*.sql` | 正本ではない一時作業域の履歴(設計書 7.2)。強制点は `contracts/authz/ddl-elements.json`(登録済)側 |
| `frontend/{eslint,prettier}.config.js`・`index.html`・`public/**` | 契約・検査の実行制御に関与しない(lint 整形は品質ゲートであり領域の不変条件ではない) |
| `backend/.coverage` 等の生成物 | 検査の入力ではない |

(1〜3 周目の指摘により、lockfile 3 本・`tsconfig.json`・実行環境ピン 3 本は**登録側へ移動済み**)

### 機構・オラクルの方針(計画レビュー 1 周目 P1-1・2 周目 P1-4・3 周目 P1-2/P1-3 反映)

- **オラクルは完全一致を維持**: `EXPECTED_AREA_PATHS`(領域 ID → 期待 paths の辞書)との**辞書完全一致** + `len(actual_by_id) == len(areas)` による**領域 ID 重複拒否**へ再構成
- **変更検知ケース**を代表 4 系で追加: `contracts/authz/auth-catalog.json`・`frontend/src/lib/courseInputView.ts`・`frontend/src/lib/format.ts`・`backend/conftest.py`(新設パスでの発火)
- **glob 境界テスト**: `contracts/authz/nested/example.json` は**発火**(`fnmatchcase` の `/` 跨ぎを固定)・`contracts/authz-other/example.json` は**非発火**
- **rename 故障系**: 外向き(保護内→保護外)は**旧パスが検知されたこと**を、内向き(保護外→保護内)は**新パスが検知されたこと**を assert。保護外→保護外の rename が**非発火**である回帰も追加
- **CI 配線オラクル**(3 周目 P1-2): `tests/test_ci_wiring.py` へ harness ジョブの exact 検査を新設し、`uv run pytest -c pyproject.toml tests/`(harness・リポジトリルート)と `uv run pytest -c pyproject.toml --cov`(backend・`working-directory: backend`)の 2 本を完全一致で固定
- **期待資産の先行オラクル**(3 周目 P1-3): `environment-expectations.json` の期待コマンド値と CI 参照 provenance は**本計画 4 節の確定コマンドから転記**し(承認済み計画 = 先行オラクル)、CI 実装と同一コミットで原子的に更新する(出典注記を provenance に記す)。`source_revision` も本計画の承認(起票)コミットへ更新する(4 周目 P2-1)
- data-migration の文書非登録オラクル(`:329-335`)は**期待値を変えず**維持。guard_paths 完全一致オラクル(`:337-341`)は**+5 件**を反映
- **glob 設計**: ディレクトリ単位は `dir/*` 1 本(入れ子まで覆う)、個別ファイルは明示列挙(逐行確認のしやすさ優先)。TSK-275(courseInputView の生成物移設)時は⑤の手続で paths を更新する(申し送り)
- **本 PR 自身は新 paths では捕捉されない**(該当判定は base 側 — github-setup `:40`)が、`core-areas.json`・`core_guard.py`・`test_core_guard.py`・`pr/SKILL.md`・`ci.yml`・`test_ci_wiring.py` が guard_paths 該当のため逐行確認 + 実施記録行が機械要求される

### authz 検査器を guard_paths に入れない判断

authz 検査器 3 資産(検査器・テスト・フィクスチャ)は **tenant-isolation の area paths に登録**する。area paths の統制(敵対レビュー + 逐行確認)は guard_paths(逐行確認のみ)より**強い**ため、research.md 5 節の非対称は実質解消される。guard_paths へ追加するのはハーネス横断の実行制御点 5 件のみ。

### 遡及逐行確認(PR #33 マージ済み分)— PO 裁定枠(3 周目 P1-5 で時系列を確定)

義務を定めた決定は存在しない(research.md 5 節)。**推奨 = 全量遡及はしない**。代替: `contracts/authz/` は `oracle-seal.lock.json` が digest 封印済みのため、**検査器(`check_authz_catalog.py`)と封印の要点確認**を山田(作者)+ 徳光で行う。時系列: **計画承認時に PO が処置を裁定 → ステップ 4 の開始前に処置を完遂**(マージ済みコードの確認であり PR と独立に実施可能)→ **ステップ 4 で最終結果を一度だけ記録**(対象・確認者・実施日・結果。「しない」裁定の場合はその理由)。PR 作成後の外部手続には含めない

### 責務の移管(記録)

pg-authz 計画 3 節は tenant-isolation.paths と guard_paths への登録を「第 2 群(計画改訂 2)の射程」として意図的に留保していた。**本タスク(TSK-281 = C1 緊急裁定)がこの登録責務を引き取る**。pg-authz 計画書は編集しない(履歴)— 本節と台帳 H-12・TSK-281 コメントを記録先とし、**有効確認者の逐行確認をもって移管合意とする**(既定 = 山田〔pg-authz 作者〕本人の確認。**代替時は PO の指名裁定に移管承認を含める** — worklog へ明記)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **core-guard の rename-safe 化**: `scripts/core_guard.py` の変更パス取得へ `--no-renames` を付与 + `NO_CORE_PATHS_MESSAGE` の現在形化 + rename 故障系テスト 3 種(外向き = 旧パス検知 / 内向き = 新パス検知 / 保護外→保護外 = 非発火)+ `.claude/skills/pr/SKILL.md`「3. 作成」手順 2 のコア判定へ「`git diff --no-renames --name-only origin/develop...HEAD` の旧・新両パスを base 側(`git show origin/develop:.claude/core-areas.json`)へ突合」を追随 | `uv run pytest tests/` green(新規故障系 3 ケース含む)/ `uv run ruff check .`・`uv run ty check` green / 変更ファイルが `scripts/core_guard.py`・`tests/test_core_guard.py`・`.claude/skills/pr/SKILL.md` のみ(`git diff --name-only`)/ 旧文言「Phase 4 で定義予定」が両ファイルに 0 件(`rg -F`)/ `pr/SKILL.md` に `--no-renames` と `旧・新両パス` が**ともにヒット**(`rg -F`) |
| 2 | **pytest 実行経路の固定**: `.github/workflows/ci.yml` の pytest 2 呼び出し(`:85`・`:220`)へ `-c pyproject.toml` を付与 + `tests/test_ci_wiring.py` へ **harness ジョブ exact オラクル新設**(2 コマンド完全一致 + working-directory 構造検査)と backend 期待の追随 + `backend/tests/db/environment-expectations.json` の期待コマンド値・CI 参照 provenance を本計画の確定コマンドから転記(出典注記つき) | `uv run pytest tests/` green(test_ci_wiring の新設オラクル含む)/ `ci.yml` の差分が **pytest 2 行の変更のみ**(ジョブ構成・`on`・`permissions` 不変を base と構造比較)/ `environment-expectations.json` の差分が期待コマンド値・CI 参照 provenance(+出典注記)・`source_revision`(本計画の承認コミットへ更新)のみ / `test_ci_wiring.py` が `-c pyproject.toml` の**欠落を検知して red になる**ことを変異確認(ci.yml から一時的に外して red → 戻して green) |
| 3 | **paths 充填とオラクル追随**: `.claude/core-areas.json` へ本節の確定表どおり登録(tenant +10 / game-state +15 / data-migration +1 / guard_paths +5)+ description 現行化 + `tests/test_core_guard.py` を `EXPECTED_AREA_PATHS` 辞書完全一致 + ID 重複拒否へ再構成 + 変更検知 4 系 + glob 境界 2 種 | `uv run pytest tests/` green / ruff・ty green / `git diff` で登録集合が本計画 4 節の確定表と**完全一致**・既存登録(文書 2 本 × 4 領域)の削除なし・guard_paths の増分が 5 件のみ / data-migration に文書パスなし(負のオラクル green) |
| 4 | **文書反映**: 台帳 H-12 を部分対応へ(①コード側 paths の充填と rename-safe 化 ②承認手続の決着〔有効確認者 = 既定 山田・不在時は PO 指名の代替者が 4 役を引き継ぐ・それまでマージ保留〕③遡及裁定の結果〔ステップ 4 開始前に完遂済みの内容〕④残余 =「13 章 Phase 4 完了条件への組み込み」1 件)+ 台帳変更履歴 1 行 + 設計書 10.1 の pytest コマンド追随 + 設計書変更履歴 1 行(版は上げない)+ `docs/README.md`(台帳行・設計書行の日付 + 台帳状態要約)+ worklog へ実施記録(遡及処置の完遂記録・6.3 条文化 follow-up の申し送りを含む) | `uv run python scripts/check_docs_status.py` green / H-12 節の切り出し(`sed -n '/^### H-12/,/^### H-13/p'`)に対し **7 つの固定文字列を個別確認**(`rg -F`): `部分対応`・`コード側 paths の充填`・`rename-safe`・`逐行確認は PR 作成者以外`・`有効確認者`・`遡及`・`Phase 4 完了条件への組み込み` / 台帳・設計書の**変更履歴表の範囲を sed で切り出し**、追記が各 1 行であることを確認 / 両正本の**版が不変**・`H-*` 新規採番なし / README 台帳行に `部分対応` がヒット |

**PR 作成後の外部手続(ステップ外 — DoD で担保)**: Notion TSK-281 の DoD 文言同期・PR URL 記録 / PR 本文の逐行確認チェック + 実施記録行(**有効確認者**が記入 — 既定 山田)/ SHA 記録と approve(head 拘束・`commit_id` 検証・再 approve 規則)とマージ(`gh pr merge --merge --match-head-commit <SHA>`)。

## 5. DoD(受け入れ基準)

- [ ] core-guard が rename-safe(故障系テスト 3 種 green: 外向き = 旧パス・内向き = 新パス・保護外間 = 非発火)で、`/pr` のコア判定手順が差分コマンドと base 取得方法まで明記して追随している
- [ ] CI の pytest 2 呼び出しが `-c pyproject.toml` で固定され、**harness ジョブの exact オラクル**(2 コマンド完全一致 + working-directory 構造検査)が test_ci_wiring に新設され、`-c` の欠落で red になることを変異確認した
- [ ] `environment-expectations.json` の期待コマンド値と CI 参照 provenance が本計画の確定コマンドから転記され(出典注記つき)、`source_revision` が本計画の承認(起票)コミットへ更新され、CI 実装と同一コミットで原子的に更新された
- [ ] 5 領域の定義を維持したまま、3 領域へ計 **26 パス** + guard_paths へ **5 パス**が 4 節の確定表どおり登録され、既存登録の削除・縮小がない(ADR-003 `:354`)
- [ ] `tests/test_core_guard.py` が新集合で green(辞書完全一致 + ID 重複拒否・変更検知 4 系・glob 境界 2 種・rename 故障系 3 種を含む)・/check(harness)green
- [ ] 台帳 H-12 が部分対応(7 固定文字列・残余 1 件)+ 設計書 10.1 追随 + 索引(日付・状態要約)現行化・**両正本とも版不変**
- [ ] **遡及逐行確認の PO 裁定処置がステップ 4 開始前に完遂され**、対象・確認者・実施日・結果(「しない」裁定ならその理由)がステップ 4 で worklog・台帳 H-12 に記録された
- [ ] PR に逐行確認チェック + 実施記録行(**記入 = 有効確認者〔既定 山田。代替時は PO 指名の氏名・GitHub login を worklog と PR コメントに記録し 4 役を引き継ぐ〕**)が付き、確認時 base/head SHA が PR コメントに記録され、**全ページ取得したレビューを有効確認者の login に限定した最新レビューが `APPROVED` かつ `commit_id` == `headRefOid`**(同確認者の後続 `CHANGES_REQUESTED`/`DISMISSED` なし)を API で確認済み(**push 後・マージ直前に再実施**)、`gh pr merge --merge --match-head-commit <SHA>` でマージされた
- [ ] PO 承認が①計画承認(frontmatter)②PR 上の「PO 承認」コメント(徳光)として記録された
- [ ] 「逐行確認 = PR 作成者以外」の 6.3 条文化が**別 follow-up として worklog に申し送られた**(H-12 残余には含めない)
- [ ] Notion TSK-281 の DoD 文言を本計画と同期(「H-12 を対応済みへ」→「部分対応へ」等)し、PR URL を記録した

## 6. テスト計画

- **ハーネス単体(故障系)**: `tests/test_core_guard.py` に追加 — ① rename 故障系 3 種(外向き = 旧パス検知で exit 1 / 内向き = 新パス検知で exit 1 / 保護外→保護外 = 非発火)② 新規 paths の変更検知パラメトライズ 4 系(`contracts/authz/auth-catalog.json` / `frontend/src/lib/courseInputView.ts` / `frontend/src/lib/format.ts` / `backend/conftest.py`〔新設〕)③ glob 境界 2 種(`contracts/authz/nested/example.json` 発火 / `contracts/authz-other/example.json` 非発火)。再構成: 領域別期待集合の辞書完全一致 + 領域 ID 重複拒否。維持: data-migration 文書非登録の負のオラクル・guard_paths 完全一致(+5 件反映)
- **CI 配線(故障系)**: `tests/test_ci_wiring.py` へ harness ジョブの pytest exact オラクルを新設(`-c pyproject.toml` の欠落・改変で red)+ backend 期待の追随。導入時に変異確認(`-c` を外して red)を行う
- **製品テスト(NFR-019 の単体・一致性・越境・E2E)**: **追加なし** — 本タスクは製品コードを 1 行も変更しないため対象外。越境テストの実体整備は pg-authz 第 2 群以降の実装タスクの責務(`backend/tests/db/*` を paths に先行登録して受け皿を保護する)
