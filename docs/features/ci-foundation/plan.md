---
feature: ci-foundation
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出)
承認: 済(2026-08-10・徳光 尋弥)  # codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3b793b75e68781babd88d6afa1de8ab1
branch: feature/ci-foundation
created: 2026-08-10
---

# 実装計画書: Phase 3 — CI 先行分(secrets・docs-lint・core-guard・harness)

改訂: レビュー 1 周目(P0×2/P1×5/P2×1)・2 周目(P0-1 未解消 + 新規 P1×3)を反映(2026-08-10)。
改訂 2(2026-08-10・PO 承認済みスコープ拡張): 設計書 v1.1 確定ゲート 1 周目(P0×3)を受け、(a) 設計書 2.3/6.2/12.1/12.2 と onboarding.md への「保護未適用の縮退状態」注記 + NFR-019 逸脱のリスク受容記録、(b) check_docs_status.py の固定文法厳格化(ステップ 3 差し戻し)、(c) 7.1-4 の「冒頭表 = 遷移履歴」改訂を追加。

## 1. 背景・目的

- ハーネス設計書 13 章 Phase 3 の実施。リモート側の強制層(CI)を、コードが無い docs 中心リポジトリの段階から常設する
- 要件上の根拠: 要件書 7.3「PRベース+CI全グリーン必須」・NFR-014(シークレット走査)・NFR-019(CI でのマージブロック)— 詳細は [research.md](research.md) §1
- Notion タスク: https://app.notion.com/p/3b793b75e68781babd88d6afa1de8ab1(優先度 高)
- 本タスクは Phase 2 完了条件「実運用での一巡検証」(/task-start → 計画書ゲート → /pr → /task-done)を兼ねる
- **ブランチ保護は後送り(PO 判断 2026-08-10)**: 所有者 Free プラン + private では branch protection / Rulesets 利用不可(rulesets API 403 を実機確認 — research.md §5-4)。**保護未適用の間、NFR-019 の「全グリーンでないとマージ不可」のリモート強制は未達**。暫定運用(マージ前に人間が CI 結果を確認)・再開トリガー・将来の必須チェック名を github-setup.md に記録する

## 2. スコープ

### やること

- `.github/workflows/ci.yml` 新設 — 設計書 10.1 の Phase 3 指定 **4 ジョブ**(不一致は 10.1 を正として採用 — research.md §4-4)。共通仕様は 4 節
- **正本 7 本**(索引 docs/README.md の正本欄全文書)への **YAML frontmatter(status)追加**(固定文法 — 4 節)
  - この状態表現の導入は**構造的な規約変更**であり、**設計書 7 章の改訂として /finalize-doc(敵対レビュー + 人間承認・版 1.0 → 1.1)を本 PR 内で通す**(レビュー 2 周目 P0-1 対応 — 計画承認による例外扱いはしない)
  - **要件書 v1.8 確定ゲート(別タスク進行中)との直列化**: 本 PR を先行マージとし、v1.8 タスクへ「rebase 時に frontmatter を維持する」旨を申し送り(worklog + Notion コメント)
- `scripts/check_docs_status.py` 新設(Python 標準ライブラリのみ・pytest 付き): 固定文法検査 + **索引整合検査**(正規化規則は 4 節)+ `docs/features/*/plan.md` の 2 値検査。worklog/legacy/templates 除外
- `scripts/core_guard.py` 新設(同上): 実行契約は 4 節。自己対象リストは `.claude/core-areas.json` に **`guard_paths` キーとして一元化**
- `.claude/skills/pr/SKILL.md` と `.github/pull_request_template.md` の整合更新: /pr は core 領域だけでなく **guard_paths 該当時もチェック欄を有効化**する(core_guard.py の期待文字列と完全一致の文言を共通化 — レビュー 2 周目 P1)
- 既存テスト 2 件の頑健化 + `.claude/settings.json` の JSON 妥当性・フック配線実在テスト追加
- `.python-version` 新設(**`3.12.3` に固定** — ローカル実測と一致・再現性)
- `docs/development/github-setup.md` 新設(正本・/finalize-doc ゲート)
- gitleaks の**初回全履歴監査**をローカル(docker・**digest 固定**)で実施(合格 = 真陽性・未失効シークレット 0 件)
- `docs/README.md` 索引現行化・設計書変更履歴追記

### やらないこと

- ブランチ保護の適用・`scripts/setup_branch_protection.py` の実装(**後送り** — プラン制約解消後の別タスク)
- backend / frontend / consistency / e2e / win-setup ジョブ(Phase 4 以降)/ deploy.yml(論点 D 待ち)/ PR 自動レビュー(Phase 5)
- markdownlint 等の書式 lint / CI からの Notion 連携(設計書 11.3)
- 要件書 v1.8 改訂の中身には触れない(frontmatter 追加のみ。ゲートは別タスク)
- core-guard の base 側実行への分離(保護有効化後の課題 — 4 節の残余リスク参照)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` | **7 章に frontmatter 併記の状態管理規約を追加(構造的規約変更・7.1-4 は「冒頭表 = 遷移履歴」に改訂)**+ 10.1 実装追随注記(採用ツール・SHA)+ 10.2/13 章に保護後送り注記 + **2.3/6.2/12.1/12.2 に保護未適用の縮退注記 + NFR-019 逸脱のリスク受容記録**(改訂 2)+ 変更履歴(**v1.0 → v1.1**) | **finalize-doc**(規約変更 + 版繰り上げ — 7.6 決定表) |
| `docs/development/onboarding.md` | ブランチ保護が未適用である縮退状態の注記(改訂 2 — 「直接コミットは保護で拒否」前提の記述を現実に合わせる) | PRレビュー |
| `docs/development/github-setup.md` | **新設**(保護の制約・再開条件・Rulesets 設定・必須チェック名・暫定運用・残余リスク・設定手順) | **finalize-doc**(新設 — AGENTS.md 絶対規則 4) |
| 正本 7 本(索引の正本欄全文書) | 冒頭に固定文法 frontmatter(status)追加 + 変更履歴追記(履歴表を持つ文書のみ。本文の内容変更なし) | PRレビュー(機械的追加。規約自体のゲートは設計書 v1.1 の finalize-doc が担う) |
| `.claude/rules/docs.md` | frontmatter status 規約(固定文法・索引整合)の追記 | PRレビュー |
| `docs/README.md` | github-setup.md 索引追加・設計書 v1.1・状態現行化 | PRレビュー |

(正本以外の変更: `.claude/core-areas.json` への guard_paths 追加・`.claude/skills/pr/SKILL.md`・`.github/pull_request_template.md`・`.python-version` — PR レビューで確認)

## 4. 実装方針

- **重さ分類 = 通常**: コア領域(5 領域)には触れない(CI・ハーネス層のみ)。軽微ではない
- **担当**: Codex 委任(/implement)= ステップ 1・3・4・6(コード)。Claude 直接 = ステップ 2・5・7〜11(正本・スキル文書・監査 — 設計書 3.1)。Claude 直接分も PR 前に `review normal` を通す(6.3)
- スクリプトは Python 標準ライブラリのみ・OS 非依存。bash/jq 依存のステップを CI に書かない(NFR-021 — research.md §1)

**frontmatter 固定文法**(check_docs_status.py はこの文法のみ受理・正規表現検査。設計書 v1.1 ゲート P0-2 で厳格化):
- 正本: **先頭からちょうど 3 行**(`---` / `status: <draft|in-review|approved|superseded>` / `---`)。追加キー・空行・行末コメント不可
- `features/*/plan.md`: 複数キーを持つため別規則 — `status: <active|in-review>` 行がちょうど 1 行(行末コメント可)
- **status の正は frontmatter**。索引 docs/README.md との整合検査の正規化規則: 索引の状態セルから太字マーカー `**` を除去し、最初の `(` より前を語彙として抽出、**前後空白を trim**(例: `**in-review**(v1.8 改訂を…)` → `in-review`、`approved(記録)` → `approved`)。不一致は fail
- **検査対象の正本一覧は索引の正本表から動的に取得**する(「7 本」を script にハードコードしない — github-setup.md 追加後も検査が自動追随する)

**core-guard 実行契約**(レビュー 1 周目 P1-1・2 周目 P1 対応):
- `pull_request` のみ本文チェック。checkout は **fetch-depth: 0**(base...head diff の取得契約)。差分 = `GITHUB_EVENT_PATH` の base/head SHA から `git diff --name-only base...head`。PR 本文はイベントペイロードから取得(`permissions: pull-requests: read`)
- 判定 = 差分パス ×(core-areas.json の `paths` ∪ `guard_paths`)。guard_paths = `.claude/core-areas.json`・`.github/workflows/ci.yml`・`scripts/core_guard.py`・`.github/pull_request_template.md`・`.claude/skills/pr/SKILL.md`
- 検知時: PR 本文の必須チェック文字列(PR テンプレ・/pr スキルと共通の完全一致文言)が `- [x]` であることを要求
- **fail-closed**: イベントファイル欠落・JSON 破損・本文取得不能は exit 非 0。paths 未定義は「Phase 4 で定義予定 — 検査対象なし」を明示して exit 0。push/workflow_dispatch は「PR イベントではない — スキップ」を明示して exit 0
- **残余リスク(明記・github-setup.md にも記載)**: pull_request は head 側の workflow/コードを実行するため、**PR 自身が ci.yml / core_guard.py を書き換えれば検査を無効化できる(循環参照)**。guard_paths は「未改変 PR への検知」であり防止ではない。保護未適用の間はマージ前の人間確認(CI 結果と guard_paths 変更の有無)を必須運用とし、base 側検査への分離は保護有効化後の課題とする

**ci.yml 共通仕様**:
- トリガー = `pull_request` + `push`(develop/main)+ `workflow_dispatch`。`concurrency` で同一 ref の旧実行キャンセル
- `permissions`: 既定 `contents: read`。core-guard のみ `pull-requests: read` 追加。**write 系権限は一切付与しない**
- 全 `uses:` は **40 桁 SHA + タグコメント**で固定(照合済み — research.md §5):
  - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`
  - `gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e # v3.0.0`
  - `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0`
  - `lycheeverse/lychee-action@e7477775783ea5526144ba13e8db5eec57747ce8 # v2.9.0`
- **secrets ジョブ**: checkout は通常イベントで既定 depth、**workflow_dispatch 時のみ fetch-depth: 0(全履歴スキャン — 2 周目 P1 の矛盾解消)**。gitleaks-action の出力は **`GITLEAKS_ENABLE_COMMENTS: "false"`・`GITLEAKS_ENABLE_UPLOAD_ARTIFACT: "false"`・`GITLEAKS_ENABLE_SUMMARY: "false"` をすべて明示**(上流既定はいずれも true — 3 周目 P2。write 権限不要・秘匿値の出力経路を遮断)
- **Python 実行契約(全ジョブ共通)**: Python を使うジョブ(harness・docs-lint・core-guard)はすべて setup-uv(**`version: "0.8.13"`** — 空欄は最新へフォールバックするため明示必須)+ `uv python install`(`.python-version` = **3.12.3** を解決)+ `uv run <script>` で実行する。ランナー同梱の `python` を直接呼ばない(固定 Python 契約を全ジョブに適用 — 3 周目 P1)
- **harness ジョブ**: 上記契約で `uv sync --locked --dev` → `uv run pytest tests/`。`enable-cache: true` + `prune-cache: true`
- **docs-lint ジョブ**: lychee(`--offline --root-dir`、対象 = `**/*.md`、`docs/legacy/**` 走査除外)+ `uv run python scripts/check_docs_status.py`。日本語**ファイル名**fixture(`tests/fixtures/docs_lint/日本語リンク元.md` → 日本語名ファイルへの相対リンク)を検査対象に含める

**gitleaks 監査(ステップ 11)**: ローカル docker で全履歴監査。イメージは **`ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f`** に固定(2026-08-10 照合済み)。誤検知は人間確認の上 `.gitleaksignore`(理由コメント付き)。**真のシークレット検出時は作業を停止して人間へ**(失効・ローテーション・履歴対処は人間判断 — NFR-014)。出力・記録に秘匿値を含めない

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | (Codex)既存テスト 2 件の頑健化(HEAD 依存 → 一時リポの feature ブランチ基準 / パス依存 → cwd を tmp_path 固定)+ settings.json の JSON 妥当性・フック配線実在テスト | worktree 内・develop チェックアウトのメインツリー両方で `uv run pytest tests/` 全グリーン |
| 2 | (Claude)正本 7 本へ固定文法 frontmatter 追加 + 変更履歴追記 + rules/docs.md 規約追記 + `.python-version` 新設(3.12.3) | 各 status が索引の正規化値と一致(要件書 = in-review)・固定文法適合・本文の内容変更なし・pytest 全グリーン |
| 3 | (Codex)`scripts/check_docs_status.py` + テスト(固定文法・索引整合の正規化・語彙違反・欠落・plan 2 値・除外域) | 新規テスト green・現リポでローカル実行 exit 0 |
| 4 | (Codex)`.claude/core-areas.json` に guard_paths 追加 + `scripts/core_guard.py` + テスト(空スキップ明示/検知×チェック有無/JSON 破損・イベント欠落 fail-closed/guard_paths 検知/非 PR スキップ) | 新規テスト green・paths 空で「検査対象なし」明示 exit 0 |
| 5 | (Claude)`.claude/skills/pr/SKILL.md`・`.github/pull_request_template.md` の整合更新(guard_paths 該当時のチェック欄有効化・core_guard.py と完全一致の文言) | 文言が core_guard.py の期待文字列と一致(テストで検証)・本 PR 自身が guard_paths 該当のためチェック欄を含む PR 本文の運用を確認 |
| 6 | (Codex)`.github/workflows/ci.yml` 新設(上記共通仕様どおり: 4 ジョブ・SHA 固定・permissions 最小・dispatch 全履歴分岐・コメント無効化・キャッシュ・lychee 除外 + fixture) | PR 上で 4 ジョブ全グリーン・lychee exit 0(fixture 含む)・uses の SHA が research.md 照合値と一致 |
| 7 | (Claude)`docs/development/github-setup.md` 起案(draft): 保護の制約(403 実測)・再開トリガー・Rulesets 設定(JSON)・必須チェック名 = 4 ジョブ・暫定運用・core-guard 循環参照の残余リスク・dispatch 全履歴スキャンは main 反映後有効 | draft コミット・索引に draft で追加 |
| 8 | (Claude+人間)github-setup.md の /finalize-doc(敵対レビュー → 反映 → 人間承認)→ approved 化 | 指摘反映完了・人間承認・status: approved・索引現行化 |
| 9 | (Claude)設計書改訂案の起案: 7 章 frontmatter 併記規約(構造的規約変更)+ 10.1 追随注記 + 10.2/13 章保護後送り注記 + 変更履歴 v1.0 → v1.1 | 改訂差分が 3 節の宣言と一致・変更履歴に規約変更の経緯を記録 |
| 10 | (Claude+人間)設計書 v1.1 の /finalize-doc(敵対レビュー → 反映 → 人間承認)→ approved 化 + 索引現行化 | 人間承認・status: approved v1.1・索引が v1.1 を反映 |
| 11 | (Claude)初回 gitleaks 全履歴監査(ローカル docker・digest 固定)+ worklog へ件数・種別・対応のみ記録 + 要件書 v1.8 タスクへの申し送り(frontmatter 維持) | **真陽性・未失効シークレット 0 件**・記録に秘匿値なし・申し送りを Notion コメントで確認可能 |

## 5. DoD(受け入れ基準)

<!-- Notion タスクの DoD と同期(計画承認時に Notion 側を更新) -->

- [ ] PR 上で CI 4 ジョブ(secrets / docs-lint / core-guard / harness)が自動実行され全グリーン
- [ ] docs-lint が正本 frontmatter(status)と索引の整合を機械検査している(固定文法・正規化・plan 2 値・除外域を含む)
- [ ] /pr・PR テンプレ・core_guard.py のチェック欄文言が一致し、guard_paths 該当 PR(本 PR 含む)でチェック欄が機能する
- [ ] 初回全履歴監査: 真陽性・未失効シークレット 0 件(記録に秘匿値なし)
- [ ] github-setup.md(approved)と設計書 v1.1(approved)に、保護の制約・再開条件・必須チェック名・暫定運用・core-guard の残余リスクを記録

## 6. テスト計画

- **単体(pytest・tests/)**: check_docs_status.py(固定文法・索引正規化の境界)・core_guard.py(fail-closed・guard_paths・非 PR スキップ)・チェック欄文言の一致検証・settings.json 配線検査。既存 103 ケース維持 + 環境依存 2 件の頑健化 — 本 PR から CI(harness)で毎 PR 実行
- **実機検証**: lychee は実データ + 日本語ファイル名 fixture(合格 = exit 0。件数固定値は条件にしない)。gitleaks は初回全履歴監査で実効性確認(ステップ 11)
- NFR-019 の一致性・越境・E2E・故障系は**対象外**(製品コード未着手 — Phase 4 以降。本 PR はその実行基盤の先行常設)
