---
feature: feature-status
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出)
承認: 済(2026-08-10・徳光 尋弥) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3b793b75e68781319d04d3b07d484b09
branch: feature/feature-status
created: 2026-08-10
計画レビュー周回: 10       # /plan レビュー(指摘反映まで)1 周ごとに +1 — 本タスクで導入する拡張キー
確定ゲート周回: 0          # /finalize-doc 敵対レビュー 1 周ごとに +1 — 同上
実行方式: 通常             # 通常 | fast(fast path 適用時 — 人間の事前 OK 必須)— 同上
---

# 実装計画書: feature 現在地の導出機構(plan frontmatter 拡張 + feature_status.py + SessionStart 注入)+ 計画書 3 ファイル役割分担(A 案)

## 1. 背景・目的

- Notion タスク: [TSK-203 feature 現在地の導出機構](https://app.notion.com/p/3b793b75e68781319d04d3b07d484b09) — PO 提案(2026-08-10)「人も AI も作業段階に迷わない機構をハーネスに埋め込む」。保存型 state.yaml は二重正本のため不採用が合意済みで、**導出方式**(plan frontmatter 拡張 + 導出スクリプト + SessionStart 注入)を実装する。※タスク本文の先例引用「v0.15 P1-4」は **v0.10 P1-4** の取り違え([research.md](research.md) §5)
- PO 追加要望(2026-08-10・**A 案採用**): plan.md 単一ファイルの密度低減のため、plan(契約)/ research(調査)/ design(詳細設計)の 3 ファイル役割分担を標準化する。実測根拠: ci-foundation の plan は 4 節だけで全体の約 55%(research.md §2)
- 設計書上の根拠: 7.6-4「進行中 feature の一覧は静的に持たず、worktree の現存を正とする(SessionStart 文脈が表示)」・6.1「完了の正は『PR merged + Notion 完了 + worktree 除去』の組で導出する」— 本タスクはこの導出の機械化
- 要件との接点(research.md §1): 製品 FR・コア領域には非接触。遵守する NFR — **NFR-019**(テストを伴う実装 — 6 節)・**NFR-014**(シークレット — 認証は gh CLI と対話セッションの MCP へ委譲し自前トークンを持たない)・**NFR-021**(WSL2/Windows 完結 — 標準ライブラリのみ)

## 2. スコープ

### やること

1. `scripts/feature_status.py` 新規 — plan frontmatter・実装ステップ表 × git log・PR 状態(gh)から現在地を**導出して表示**(無保存・読み取り専用)。Notion は期待値表示 + 対話セッションでの実値照合(設計: [design.md](design.md) §3)
2. `.claude/hooks/session_context.py` 改修 — 進行中 feature の現在地要約を注入。**先頭 800 文字切り詰めの廃止**(frontmatter ブロック全読)と進行中 feature 判定の feature_status.py への一本化(design.md §4)
3. plan frontmatter 拡張キー 3 個 — `計画レビュー周回`・`確定ゲート周回`・`実行方式`(frontmatter 末尾配置。design.md §2)
4. A 案の標準化 + ライフサイクル整備 — `docs/development/templates/design-template.md` 新設・plan-template.md への拡張キー + design.md 導線 + コミット記法追記・スキル 5 本への手順追記(`/plan`〔design 分離・周回キー・起票コミットは記法なし〕・`/finalize-doc`〔確定ゲート周回 + 更新先 plan の明示〕・`/implement`〔ステップコミット件名の固定記法・fast 節に実行方式記入〕・`/task-start`〔design.md は任意 — 作成判断は /plan〕・`/pr`〔**差し戻しの往復手順**: 再開 = in-review → active + Notion 進行中 / 修正完了 = active → in-review + Notion 確認待ち(OPEN の既存 PR では gh pr create せず再レビュー依頼)— 7/8 周目 P1〕)(design.md §2/§3.2/§3.3/§5)
5. テスト — `tests/test_feature_status.py` 新規・`tests/test_hooks.py` 更新(6 節)
6. 正本反映 — 設計書の節更新(3 節)・docs/README.md・.claude/rules/docs.md の追随

### やらないこと

- 保存型状態ファイル(state.yaml 等)の新設・Notion / GitHub / Git への**書き込み**(feature_status.py は表示のみ)
- plan.md **必須 6 節構成の変更(B 案)** — codex_run.py・check_docs_status.py は**無改修**で成立することが A 案の成立条件(research.md §3 不変条件)
- feature_status のスキル化(8.4 表への行追加)— 対話導線は今回はコマンド直叩きで足りる。必要が実証されたら別タスク
- 設計書 v0.10 変更履歴行の表記揺れ(「3 値化」)の遡及修正 — 履歴行は改変しない(worklog に記録済み)
- ブランチ保護・github-setup 関連(別タスク — プラン制約解消後)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md`(v1.2) | **実装追随の節更新**: 6.1「1 feature = 1 ディレクトリ」標準構成へ design.md 追記 / 6.1 段階実装へ導出機構(feature_status.py)の言及と**ステップコミット件名の固定記法**(既存慣行の明文化)を追記 / 6.1・7.6-4 へ**差し戻しの往復ライフサイクル**(再開 = in-review → active / 修正完了 = active → in-review — 7/8 周目 P1)と導出の機械化を追記 / 8.3 表 session_context 行の注入内容更新 / frontmatter 拡張キーの記載(6.1) / 変更履歴追記。**版繰り上げなし** — 必須 6 節構成(:238-245)と frontmatter 文法規約(7.1-5)には触れない | **PR レビュー**(7.6-3 前段)。※PO が「構造的変更」と判定した場合は /finalize-doc + v1.3 へ切替(6.4 の判定撤回前例あり — research.md §4) |
| `docs/README.md` | :20 SessionStart 説明・:24 テンプレート一覧へ design-template 追記・:30 features 行(design.md)・索引の最終更新現行化 | PR レビュー(7.1-5 派生表示) |
| `.claude/rules/docs.md` | :13 の feature ディレクトリ説明へ design.md 追随(設計書と**同一 PR** — 7.6-2) | PR レビュー(7 章の要約) |
| `docs/development/templates/`(plan-template.md 改・design-template.md 新設) | 拡張キー 3 個(計画レビュー周回・確定ゲート周回・実行方式)+ design.md 導線 + コミット記法 / 新テンプレ | PR レビュー(正本表・docs-lint の対象外 — research.md §4) |
| 要件書・ADR・`docs/design/`・`docs/ops/` | **反映なし**(製品機能・技術選定・運用に非接触) | — |

コード・スキル・フック・テスト(`scripts/`・`.claude/hooks/`・`.claude/skills/plan|finalize-doc`・`tests/`)は正本ではない — 変更は 4 節ステップ表に列挙。

## 4. 実装方針

- **重さ分類 = 通常** の根拠: コア領域 5 分野(同期プロトコル・状況計算・記録権・テナント分離・データ移行 — `.claude/core-areas.json`)にコード・データとも非接触(開発ハーネスの基盤のみ)。軽微(50 行超・複数ファイル)でもない → 通常(計画レビュー = review normal + 人間承認 — 6.3)
- **guard_paths への接触宣言**(7 周目 P1 で追加): スキル変更 5 本(plan・finalize-doc・implement・task-start・**pr**)のうち `.claude/skills/pr/SKILL.md` は guard_paths 該当(差し戻し再開手順の追記 1 箇所)→ **CI core-guard の人間逐行確認チェックが本 PR で発火する**(PR 本文のチェックボックス + 逐行確認が必要 — 設計書 10.1)。コア領域 5 分野への接触ではないため重さ分類は通常のまま
- 設計原則(詳細は [design.md](design.md)): **導出のみ・無保存・書き換えない** / 出力は派生表示(正本ではない)/ 縮退は fail-open + 「未取得」明示(無言縮退禁止 — NFR-015 類推)/ Notion はスクリプトから呼ばず期待値表示 + セッション照合(11.3)・不一致は顕在化のみ / 拡張キーは frontmatter 末尾配置(status・branch を前方維持)
- **承認・起票コミットはステップ表の外**(5 周目 P1): 計画承認後の plan.md・research.md・design.md・worklog の起票コミットは /plan の承認後処理(合格条件: `uv run python scripts/check_docs_status.py` green・diff が上記 4 ファイルのみ)。**ステップ記法を付けない** — 計画系コミットとして進捗導出から除外され、直後の現在地は「実装前(全 6 ステップ)」になる(design.md §3.3 — 本 feature 自身が検証ケース)
- 委任区分(設計書 3 章): ステップ 1〜4 = **Codex 委任**(通常 → ADR-001)。ステップ 5・6 = ドキュメント・スキル記述につき **Claude 直**(PR の反対側レビューで担保)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | `scripts/feature_status.py` コア(worktree 列挙・frontmatter 解析〔8KiB 上限・status 厳密一致〕・ステップ表 × git log 突合〔表検証・完全トークン・計画系コミット除外〕・stage 判定・text/hook 出力 — design.md §3.1〜3.3, 3.6)+ `tests/test_feature_status.py`(単体: 選別行列・進捗整合の全分岐) | `uv run pytest tests/` green・本リポで手動 smoke(feature-status 自身が正しい段階で表示される) |
| 2 | gh 連携(PR 状態・timeout・縮退ラベル — design.md §3.4)+ 故障系テスト(gh 不在/タイムアウト/非 0) | pytest green・gh 無効環境で「PR 状態: 未取得(縮退)」表示を確認 |
| 3 | Notion 期待値(notion-map.json 参照・stage×PR→期待ステータス対応表・CLOSED の人間判断表示・map 破損/拡張キー不正値の縮退 — design.md §2/§3.5)+ テスト | pytest green・notion-map 破損 fixture で期待値「未取得」・hook モードで gh/Notion 系を起動しないことをテストで固定 |
| 4 | `session_context.py` 一本化(進行中 feature ブロックを feature_status.py 起動へ置換・失敗時「未取得(導出失敗)」注入 — design.md §4)+ `tests/test_hooks.py` 更新(正常注入・800 字超回帰・8KiB 超・非ルート cwd・timeout) | pytest green・SessionStart 手動確認(現在地行が注入される) |
| 5 | テンプレ・スキル整備: plan-template.md(拡張キー・design 導線・コミット記法)・design-template.md 新設・plan/SKILL.md(design.md 分離 + 周回キー更新 + 起票コミットの記法なし明記)・finalize-doc/SKILL.md(確定ゲート周回 + 更新先 plan 明示)・implement/SKILL.md(件名固定記法・fast 節に実行方式記入)・task-start/SKILL.md(design.md は任意)・**pr/SKILL.md(差し戻しの往復: 再開 = in-review → active + Notion 進行中 / 修正完了 = active → in-review + Notion 確認待ち・OPEN は gh pr create せず再レビュー依頼・CLOSED は reopen or 新 PR — guard_paths 該当・逐行確認対象)** | check_docs_status.py green(**既存 plan 2 本が無改修で通る = 後方互換**)・**plan-template.md に拡張キー 3 個すべてがあることを確認**・`lychee --offline --root-dir "$(pwd)" --no-progress --exclude-path docs/legacy './**/*.md'`(CI links ジョブと同引数 — ci.yml)をローカル実行して green(未導入なら PR の CI で確認) |
| 6 | 正本反映: 設計書 6.1(標準構成・コミット記法・拡張キー)/7.6-4/8.3 の節更新 + 変更履歴追記・docs/README.md(:20/:24/:30)・rules/docs.md 追随 | check_docs_status.py green・索引整合・**3 節宣言と diff の一致**(/pr 突合の事前確認) |

## 5. DoD(受け入れ基準)

Notion タスクの DoD 3 点と同期 + A 案(PO 追加要望)を追加:

- [ ] **保存ではなく導出**: `scripts/feature_status.py` が plan frontmatter・実装ステップ表 × git log・PR 状態(gh)から現在地を計算して表示し、状態を一切保存しない。Notion 照合は**対話時のみ**(スクリプトは期待値表示・実値照合はセッション手順・書き換えない)
- [ ] **session_context(SessionStart)が進行中 feature の現在地要約を注入する**(先頭 800 文字制限の解消と回帰テストを含む)
- [ ] **保存が必要な事実は plan.md frontmatter の拡張キーで持つ**(`計画レビュー周回`・`確定ゲート周回`・`実行方式`。新規状態ファイルなし・正本 status の複製なし)
- [ ] **A 案 3 ファイル役割分担**(plan = 契約 / research = 調査 / design = 詳細設計)がテンプレ・スキル・設計書 6.1 に反映され、`codex_run.py`・`check_docs_status.py` は**無改修**で green
- [ ] 全ステップのテストが CI harness ジョブ(`pytest tests/`)で green

## 6. テスト計画

NFR-019 の種別のうち一致性・越境・E2E は製品コード未着手につき対象外(ci-foundation の前例 — 同 plan 6 節)。**単体 + 故障系**を `tests/` に追加する(CI harness ジョブは `pytest tests/` 一括実行のため、本節の明示が唯一の担保 — research.md §1):

- **単体**(`tests/test_feature_status.py` 新規):
  - frontmatter 解析: 拡張キー・行末コメント・**キー欠落 → 既定値 0**(後方互換)・拡張キーの**非整数/負値 → 「不正値」表示**
  - **選別行列**(1 周目 P1): 複数 worktree の列挙 / main・develop worktree の除外 / branch 不一致・欠落の無言除外 / **status 厳密一致の境界**(2 周目 P1 — `activeX`・余剰トークン・候補行重複 → 解析失敗 / 行末コメント → 適合 / 本文中の偶然一致を拾わない)/ **候補抽出は `^status\s*:`**(3 周目 P1 — `status : active` 単独 → 解析失敗・正規行との併存 → 解析失敗)/ **評価順の複合**(3 周目 P2 — `activeX` + branch 不一致 → 解析失敗を表示)
  - **承認判定**(2 周目 P1): `済(YYYY-MM-DD・承認者)`・`済` 単独 → 承認済み / `未`・欠落 → 計画段階(codex_run.py と同一の `startswith` 判定)
  - ステップ進捗: 表パース(「実装ステップ」見出し配下限定 — codex_run.py と同一判定)/ **表検証が最優先**(3 周目 P1 — 表番号の欠番 `1,3`・重複 `1,1`・N=0 → コミット数にかかわらず不整合)/ コミット記法は**完全トークンのみ算入**(3/4 周目 P1 — 括弧なし `ステップ 2 の補足`・数値なし括弧書き → 不算入 / 全角・半角括弧 → 算入 / **未閉止 `(ステップ 7`・括弧種不一致 `（ステップ 7)`・非境界 `(ステップ 2abc)`・k=0・`(ステップ 4/3)`〔トークン N ≠ 表 N〕→ 不整合**)/ 3 値判定(**連続 → k 採用・欠番 → 不整合・k>N → 不整合・異なるコミット間の同一 k 重複 → 正常・1 件名に有効トークン 2 個 → 不整合**〔6 周目 P1〕)/ **計画系コミット除外**(4/5 周目 P1 — 承認・起票コミット〔パス 1 件以上・全件が feature ディレクトリ + worklog 配下・記法なし〕のみ → **実装前 k=0**・最初の実装コミット `(ステップ 1/6)` → **k=1**・実装系の無記法コミット → **不明**・**無記法の 2 親マージ / 空コミット → 不明**〔空パス集合は保守的に実装系〕)
  - stage 判定表(design.md §3.2)の全 10 分岐(**`実行方式: fast` → 「fast path 実装中」・省略/`通常` → 従来判定・列挙外値 `fastt`/空値 → 「未取得(実行方式不正)」を text/hook 両方で・コメント付き正値 → 適合**〔7/8 周目 P1〕を含む)/ **差し戻しの往復ライフサイクル**(9 周目 P1 — **全 N ステップ完了済みの実在ケース**で、OPEN/CLOSED を問わず in-review → active で「実装中(差し戻し修正)」〔k=N でも「実装完了・/pr 前」と誤表示しない — Git 履歴から in-review 痕跡を導出〕・修正完了 active → in-review で PR 段階へ復帰・**base 側(origin/develop 以前)だけに in-review 履歴がある場合は「差し戻し修正」に入らない**〔10 周目 P1 — 走査は base..HEAD 限定〕・履歴走査の git 失敗 → 「未取得(git 失敗)」 — を text/hook で固定)/ notion-map.json からの期待ステータス導出(**stage×PR 対応表・CLOSED → 人間判断表示・MERGED+worktree 現存 → `transitions.pr_created.status` を状態維持として参照 + 「/task-done 待ち」併記**〔2/3 周目 P1〕・**map の pr_created.status を差し替えた fixture で表示が追随**することの固定)
- **故障系**(同上): gh 不在・タイムアウト・非 0 終了 → 「PR 状態: 未取得(縮退)」/ **git 失敗の出力契約**(3 周目 P2 — `git worktree list` 失敗 → 「進行中 feature: 未取得(worktree 列挙失敗)」で 0 件正常と区別・merge-base/log 失敗 → 当該 feature「未取得(git 失敗)」・**いずれも exit 0 のまま必ず「未取得」を出す**)/ **解析不能 plan(frontmatter 非閉止・8KiB 超・status 候補行数 ≠ 1)→ 「未取得(frontmatter 解析失敗)」を表示し、併存する健全 feature の表示に影響しない**(2 周目 P1 — 無言除外にしない)/ **notion-map.json 破損 → 期待値「未取得」** / **hook モードで gh・Notion 系サブプロセスを起動しない**ことの固定
- **hooks**(`tests/test_hooks.py` 更新): **正常注入**(進行中 feature の 1 行要約が additionalContext に含まれる)/ **800 字超 frontmatter でも feature を検出する回帰** / 8KiB 超 frontmatter / 非ルート cwd / 子プロセス失敗・timeout → **「進行中 feature: 未取得(導出失敗)」を注入**(無言省略しない)/ 配線テスト(:56-69)は settings.json 無変更につき既存のまま green
