---
date: 2026-08-07
topic: WSL2 移行の引継ぎとハーネス実地整備
branch: feature/dev-harness
---

# 作業ログ: 2026-08-07 WSL2 移行の引継ぎとハーネス実地整備

## やったこと

- **環境実査(WSL2・Ubuntu)**: リポジトリは WSL 側 FS(`~/projects/pitchlog`)に配置済みを確認。gh は認証済み(HellsingWalter)・Codex は ChatGPT ログイン済み
- **python 修復(重大)**: `python` が Windows 側 pyenv-win の壊れたシム(`/mnt/c/.../pyenv-win/shims/python`)に解決され、**hooks 全体が fail-open していた**。PATH 先頭の `~/.local/bin` に `python → /usr/bin/python3` のシムリンクを作成して解消(sudo 不要の代替。onboarding v0.3 に罠として記録)
- **git ユーザー設定**: WSL 側が未設定だったため、リポジトリローカルに過去コミットと同一の作者(`walter97 <168tokumitsu@gmail.com>`)を設定
- **テスト**: `uv sync` → `uv run pytest tests/` **44 件全グリーン**(0.77s)
- **hooks 実地確認(onboarding §5 相当・10 項目 OK)**: main 上 commit ブロック / feature 上 commit 許可 / refspec 経由 develop push ブロック / 生 `codex exec` ブロック / ラッパー経由許可 / 危険フラグ無条件ブロック / `.env` 参照ブロック / `.env.example` 許可 / `docs/legacy` 書込ブロック / 通常 docs 書込許可。SessionStart(session_context)の文脈注入も正常
- **Codex 整備**: CLI を 0.144.0 → **0.146.1**(設計書・ADR-001 の検証済みベースライン)へ更新。`~/.codex/config.toml` に本リポジトリの trust を追記(既存が `projects = { ... }` インライン表形式だったため表内に追記 — セクション併記は TOML 重複でエラー)
- **ラッパー疎通**: `codex_run.py review normal` で一気通貫確認 — read-only sandbox 適用・`model_reasoning_effort=max` 受理・日本語 stdin 正常・セッション ID 捕捉。bubblewrap はシステム未導入でも codex 同梱版で動作(警告のみ)
- **文書更新**: onboarding v0.3(python シムの罠・インライン表・bubblewrap)/ docs/README.md 索引の設計書版数を 0.9 → 0.11 に現行化
- **敵対レビュー2周目を実行**(設計書 v0.11 の宣言事項「WSL 移行後に実施」): `codex_run.py review adversarial`(sol xhigh)— 結果は本ログ末尾・チャット報告参照
- **PO 追加指示2件を反映(設計書 v0.13)**: (1) **Notion 連動の機構化** — タスク DB の実ステータス語彙 11 選択肢を MCP で取得し `.claude/notion-map.json` に一元化。全遷移(着手=進行中/PR=確認待ち/差し戻し/完了+完了日)のタイミングと実施スキルを固定、/setup-dev に語彙突合を追加。(2) **段階実装・こまめコミット** — 計画書に「実装ステップ(コミット単位)」表を必須化(ラッパーが機構検査)、/implement を「1 委任 = 1 ステップ → 検証 → 1 コミット」ループへ改稿、AGENTS.md に「指示されたステップで止まる」を明記
- **PO 追加指示を反映(設計書 v0.12)**: feature 作業域は **1 feature = 1 ディレクトリ**(`docs/features/<slug>/` 配下に plan.md・research.md・補助資料を集約。直下に単発ファイルを置かない)。スキル・テンプレート・session_context は既にディレクトリ前提で実装済みだったため文書側の明確化のみ。確認の過程で v0.10 P1-4(plan 状態2値化)への追随漏れ「active → merged」を4箇所(設計書 7.2/7.6・rules/docs.md・docs/README.md)に発見し掃除

## 決定

- python の PATH 修復は `~/.local/bin/python` シムリンク方式(sudo 不要・`python-is-python3` と同効果)。onboarding に両方式を記載
- Codex CLI は検証済みベースライン 0.146.1 に固定して更新(latest 追従はしない)
- git 作者設定はリポジトリローカル(グローバルは未設定のまま — 他プロジェクトに影響させない)

## 未決・次の一歩

- **セッション再起動が必要**: 本セッションは main(settings 無し)で起動したため hooks/permissions が未ロード。次回起動時に SessionStart 注入と /permissions を確認(onboarding §5-1/5-2)
- **Notion 紐づけ未設定**: `/setup-dev` の対話が必要(PITCHLOG_NOTION_USER_ID)
- **Docker WSL 統合が無効**: Docker Desktop → Settings → Resources → WSL integration で有効化(Phase 4 の開発 DB まで不要)
- **openai-codex プラグインは不使用**(WSL 側 Claude Code に未導入): Codex 経路は `codex_run.py` ラッパーに一本化済み(v0.16)。stop-review-gate も使わない(Claude 直接実装時は `codex_run.py review normal` を通す)
- **確定ゲート通過(2026-08-07)**: 敵対レビュー5周(2→3→4→5。各否決を反映、v0.17 で 3 ガードを shlex 字句解析ベースへ設計転換して収束。残余は宣言済み脅威モデル外)→ **PO 承認**。設計書 v1.0 approved・ADR-001/002 も一括 approved・索引現行化。7.3 確定ゲートの初回適用案件
- 任意: `sudo apt install python-is-python3 bubblewrap`(現状はシムリンク+同梱版で充足)

## 残タスク(承認後)

- **要件書 v1.8**: フロントエンド Vue 化ほか3点の改訂は in-review のまま。実装着手(Phase 4)前に別途 7.3 ゲート(敵対レビュー → 人間承認)を通す — 2.4/論点A
- **Phase 3 以降**: CI 先行分(secrets/docs-lint/harness)+ ブランチ保護適用 → プロジェクト骨格(backend/frontend/contracts)。設計書13章のとおり
- 運用時の環境依存: Notion 紐づけ(/setup-dev)・Docker WSL 統合・セッション再起動での hooks ロードは初回に実施

## 敵対レビュー2周目の triage(判定=否決・P0×7/P1×11/P2×2)

レビュー全文: セッションの scratchpad(要点は本表)。**即応済み** = v0.13 コミットに含む。

### 即応済み(6件)

| 指摘 | 対応 |
| --- | --- |
| [P1] `--resume` が引数順で必ず失敗 | `implement_argv()` で exec オプションを resume の前へ(実機検証+回帰テスト) |
| [P1] /task-start 一巡破綻(worktree 置き場なし・Notion 先行遷移・テンプレ相対パス誤り) | `mkdir -p` 事前確保/遷移を worktree 成功後へ/テンプレ `../../..` に修正 |
| [P1] `fix/*` が /pr・/task-done を通れない | ブランチは計画書 frontmatter の `branch` を正に(feature/fix 両対応) |
| [P1] 副作用スキルがモデルから自動起動可能 | 9本に `disable-model-invocation: true`(worklog/check/investigate/research は対象外のまま) |
| [P0] `python` PATH 汚染で hooks fail-open | hooks 起動を `/usr/bin/python3` **絶対パス化**(部分対応 — SessionStart 正負プローブは次版検討) |
| [P1] 表記の不整合(8.4 merged 残存・テスト数 38/44 混在)+ `review --base` の偽装受理 | 8.4 修正/47 件に統一/`--base` は明示拒否+テスト |

### 追記(v0.14 で対応完了)

PO へ推奨方針(脅威モデル=誤操作+外部入力暴走まで。敵対 AI フル想定はしない)を提示、応答タイムアウトのため推奨案で自走(可逆・ブランチ内)。下記「採用予定」5件+「要PO判断」のうち軽量対応(research 秘密レス検査・安全キー明示上書き・worktree 照合・的絞り deny)を **v0.14 として実装済み**(テスト 59 件)。**確定不採用**: Bash allow 絞り込み(日常導線の破壊)・承認/fast トークン化(Claude 自身が読み書きできる場所にあり防御にならない)・CODEX_HOME 隔離(実シークレット投入前に過剰 — Phase 4 で再検討、設計書 12.1 の宣言どおり)。sandbox キーの config 層仕様の真偽は**未検証のまま論点を無効化**(ラッパーが毎回 CLI 明示上書き — CLI は config に優先)。PowerShell matcher は防御の残置として維持。

## 敵対レビュー3周目(判定=否決・P0×4/P1×5/P2×2 — 20→11件に収束)

**v0.15 で全11件を反映**(不採用なし)。要点:

- **同根の2件を1機構で解決**: 「非ラッパー heredoc(`bash <<EOF`)の本文が検査から漏れる」(P0)と「正規ラッパーの heredoc プロンプトを git/secret ガードが誤ブロックする」(P1)は、`guard_common.py` の「**データ扱いは正規ラッパーへの stdin のみ**」判定で両方解決
- 残りの P0: `writable_roots=[]` の明示固定(公式リファレンスで config から追加書込ルートを設定できることが確認された — 2周目で保留した仕様問題の決着)/ `/research` 秘密検査の再帰化 / secret_guard の `.env.example.*` 穴
- P1: 実装ステップ表の構造検証(`\S` が `|` にマッチする regex バグを発見・修正)/ branch 必須化+worktree 親ディレクトリ判定 / SessionStart の branch 突合 / ブランチ強制削除の同義形遮断(settings の deny は語順・別名で迂回可能 — 意味ベースは hooks 側の責務と整理)/ task-done の `pull --ff-only`
- P2: fast path の計画書雛形保持を明文化 / 8.2 の permissions 例示を撤去(実ファイルが正 — 複製は必ず腐る)

## 敵対レビュー4周目(判定=否決・P0×4/P1×5/P2×2)→ v0.16 で全件反映

- **guard_common を設計反転**: 3周目の「先頭行がラッパーなら全 heredoc 除去」は、ラッパー heredoc の後ろに `bash <<RUN` を連ねる迂回を許した(P0)。**正規形の受理**(ラッパー単独+末尾 stdin heredoc 1つに完全一致する時だけ本文除外)へ変更し、追加コマンド・2つ目の heredoc・終端後残余・解析不能マーカーは全文検査に戻す
- P0 残り: 引用符付き実行(`"codex" exec`)捕捉 / `.env.example` をトークン終端判定(`-prod`・`~`・`/secret` 派生を遮断)/ `/research` の走査除外ディレクトリ撤廃+fail-closed
- P1: worktree の **git-common-dir 照合**(同名別リポジトリを排除)/ fast のブランチ種別検証 / ステップ表の見出し配下3セル全記入 / force refspec・分離短縮形の意味遮断 / **Codex 経路をラッパーに完全一本化**(`/codex:*`・stop-review-gate・runtime フラグ・review_model の記述を全廃)/ fast×PR テンプレ整合
- P2: SessionStart の branch 欠落 plan 除外 / worklog 締め帰属を /pr に統一 / config.toml コメントを 9.3 と整合
- テスト 71→82 件。**収束傾向**: 20(3周目)→11→…だが4周目も11件。ただし内容は「実装の詰め(regex 境界・照合の厳密化)」に移行し、設計論点の蒸し返しは無し

### (旧)採用予定 — 次版のガード強化パスで対応(5件)→ v0.14 で対応済み

| 指摘 | 方針 |
| --- | --- |
| [P0] codex_guard の substring 迂回(絶対パス codex・`echo codex_run.py; codex exec`・npx) | allow を完全一致文法へ・複合コマンド不許可・別ランチャー既定拒否 |
| [P0] git_guard の `cd &&`・複合コマンド見落とし | シェル節ごとの評価+`git -C` 全走査。リポジトリ側 pre-commit の併設検討 |
| [P1] SessionStart が兄弟 worktree を列挙しない | `git worktree list --porcelain` を正に全 worktree 走査 |
| [P1] fast path と /pr の契約不整合 | 短縮計画の形式定義+/pr の fast 分岐 |
| [P1] テストが既知迂回を検出できない | 一時 Git リポジトリ+偽 codex 実行体で迂回ケース・argv・一巡を統合テスト(ガード強化とセット) |

### 要PO判断 — 方針決定後に対応(4件)

| 指摘 | 論点 |
| --- | --- |
| [P0] read-only sandbox が秘密の読み取り境界でない(/research の live search 併用) | /research を秘密レス worktree に固定するか・専用ランナー(CODEX_HOME 隔離)まで踏み込むか。**脅威モデルの確定が先**(hooks は「Claude の誤操作を止める」層 — 8.3。敵対的 AI を想定するかで工事規模が大きく変わる) |
| [P0] sandbox 設定がユーザー/プロジェクト config で拡張されうる・ALLOW_NET に承認記録なし | 公式仕様の再検証(/research)→ 全セキュリティキーの明示上書き or CODEX_HOME 隔離。ネット例外の承認トークン化 |
| [P0] Bash allow が広い(`uv run:*` 等は任意コード) | 絞ると日常開発の承認プロンプトが激増する。利便性と防御のバランスは PO 判断 |
| [P0] 計画承認・worktree・fast 判定が自己申告 | 承認のハッシュ/記録紐づけ・`git worktree list` 照合・fast の事前承認トークン。同じく脅威モデル次第(worktree 照合のみ先行採用が候補) |

### 不採用提案・保留(3件)

| 指摘 | 理由 |
| --- | --- |
| [P1] 要件書 v1.7 参照が残存 | 仕様どおり: v1.8 は確定ゲート通過前(in-review)であり、approved 正本参照としての v1.7 は正確。ゲート通過時に一括更新する |
| [P2] WSL2 での無条件 casefold が過剰拒否 | 安全側の過剰ブロックで実害小。次版で /mnt 配下限定 casefold を検討(保留) |
| [P2] `.env.example` が Read deny に巻き込まれる | permissions の glob に負の例外が書けない。Bash 経由(`cat .env.example`)は secret_guard が許可済みで実務は回る。deny 緩和+hook 代替は防御レイヤの後退 — 現状維持を提案(PO 確認事項) |
