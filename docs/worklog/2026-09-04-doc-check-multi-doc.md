---
date: 2026-09-04
topic: TSK-269 文書検査機構の多文書対応 — 保留解除・再開
branch: feature/doc-check-multi-doc
---

# 作業ログ: 2026-09-04 TSK-269 文書検査機構の多文書対応 — 保留解除・再開

## やったこと

### /task-start(再開)— 二重着手せず既存 worktree を再利用

- TSK-269 は 2026-08-31 に着手済み(worktree `../pitchlog-worktrees/feature-doc-check-multi-doc`・
  計画書雛形 `docs/features/doc-check-multi-doc/plan.md`〔承認: 未〕・調査メモ `research.md`)で、
  人間の判断により **TSK-270 先行のため保留**(Notion `ブロック中`)されていた
  → 前回 worklog: [2026-08-31-doc-check-multi-doc.md](2026-08-31-doc-check-multi-doc.md)
- **保留理由の解消を確認**: TSK-270(PostgreSQL 認可構成の実機検証)は 2026-08-31 完了(PR #33)。
  追補の TSK-312(TSK-270 マージ後レビュー P0 7 件の是正)も 2026-09-03 完了(PR #39)
- ブランチを `origin/develop`(f92b5f8 — PR #41 マージ後)へ **rebase**(184 コミット遅れを解消)。
  ブランチ固有の変更は新規 3 ファイル(plan.md / research.md / 前回 worklog)のみで競合なし
- Notion TSK-269 を `ブロック中` → `進行中` へ遷移し、再開の経緯をコメント

### /investigate — 前回調査メモの再検証(develop 24adeb2 → f92b5f8)

- 調査サブエージェント **3 本**を並列(コード差分監査〔general-purpose・Opus〕/ decision-tracer / spec-checker〔受け渡し契約の突合〕)。
  重い主張は Claude が原典で直接確認し、`research.md` に **6 節「再検証(2026-09-04)」** を追記(1〜5 節は原文のまま残す)
- **確認した事実の要点**
  - 検査機構本体(`check_design_propagation.py` / `check_doc_coverage.py` / `design_relations/` 4 資産 / `codex_run.py`)は
    **md5 一致 = 無変更**。1〜2 節の行番号は全部有効。変わったのは `core-areas.json`(guard_paths 18→24・area paths 8→34)・
    `test_core_guard.py`(辞書完全一致)・`test_ci_wiring.py`(81→1,148 行・pytest コマンド exact オラクル)・`ci.yml`(`-c pyproject.toml`)
  - **P0 MT-01 は事実**: `defects.json:471` の scope `1節` に対応する `## 1.` が同期正本に無く、`冒頭` も 61 文字しか切り出していない。
    1-4 節の故障モードが**一文書目で既に部分発生**している
  - **第 3 の検査機構** `scripts/check_authz_catalog.py`(5,019 行)が develop に入った。CI docs-lint には未配線
  - TSK-250 計画書は develop 未マージ・未改訂(`承認: 済 2026-08-31`・26 ステップ)。**ステップ 22「明示引数」との衝突は継続**。
    **4 検査の入力契約は TSK-250 側も未定義**。`AUTH-*` という ID はリポに 0 件で、TSK-270 実資産(`CATALOG:`/`POLICY:` 前置き・probe スキーマ限定)と体系が違う
  - `has_step_table` は誤記で実名 **`has_filled_step_row`**(`codex_run.py:62-78`・問題行 `:71`)。core-areas.json のどちらの集合にも無く、起票も未履行
  - 新たに効く手続: 7.3-1〜7.3-8・6.1 反映周コミット・6.3 実施記録行・H-85/H-87/H-88
- **基準線を再測定**: pytest **875 passed** / 3 検査 green / ruff・ty クリーン。**node ID 875 件を `baseline-node-ids-f92b5f8.txt` に固定**
  (P1「784 件以上は既存テスト削除でも達成できる」への対応資産)

### /plan — 計画書の全面改訂(1 周目 P0 6 / P1 7 + 再検証の論点 4 件を反映)

- **MT-01 裁定 (a) の実現可能性を実測**(scratchpad に scripts/docs/tests を複製し `defects.json` の scope から `1節` を除いて現行 `PROP` を実行):
  fixture の MT-01 は**引き続き検出**(rc=1)、approved 正本は**引き続き green**(rc=0)→ 検出集合を変えずに改訂できる。
  ただし `DEFECT_CHECK_CASES` の `draft-metadata` 対(`tests/test_check_design_propagation.py:261-267`)は `## 1.` 配下に禁止語を置くため、
  同じステップで scope 内へ移す必要がある(design 4 節)
- `design.md` を新設(plan = 契約 / design = 詳細設計の分離 — 設計書 6.1)。0 節に裁定一覧と「新規機構を発明しない」への**明示的な例外**の記録、
  1 節プロファイル、2 節 DSL と移行の証明(corpus 17 件 + shadow 比較)、4 節 MT-01、5 節 CLI、6 節 4 検査の入力契約(`assets` 宣言・ID 前置き非依存)、
  9 節 CI、10 節 `has_filled_step_row`、11 節 TSK-250 への申し送り 9 項目、12 節 authz 検査器から借りる前例
- `plan.md` を全面改訂: 3 節は**正本・`core-areas.json`・台帳・README すべて「反映なし」**、`defects.json` のみ MT-01 の 1 行。
  ステップ表は 24 → **25 ステップ**(群: 基盤 4 / oracle 1 / DSL 9 / COV 2 / 新検査 6 / 配線 1 / 記録 1。旧ステップ 13 の
  `GLOBAL_CHECK_IDS` 整理は削除、`codex_run.py` 是正をステップ 1 に、corpus 拡充をステップ 2 に、旧分岐の撤去を独立のステップ 15 に)。
  共通合格条件に**基準 node ID 875 件の全件収集**と **checker 出力の worklog 転記(H-88)** を追加。`計画レビュー周回: 0 → 1`(1 周目の指摘を反映)
- 機構チェック: `has_filled_step_row` が表を認識 / frontmatter 正 / 25 ステップ連番 / docs-lint green / `test_check_plan_docs_sync`・`test_feature_status` 99 passed
- **計画レビュー 2 周目(敵対・ラッパー経由 `review adversarial`)を起動**(プロンプト: 検証観点 10 + 計画書全文、design/research はパス参照)

### 計画レビュー 2 周目(敵対・sol xhigh)= **否決** / P0 9・P1 11・P2 4(一次記録 — H-87)

1 周目の指摘に安定 ID を付ける: **R1-P0-1〜6**(worklog 2026-08-31 の P0 6 件・記載順)/ **R1-P1-1〜4**(同 P1 4 件・記載順)。
**1 周目の要約は「P1 7 件」だが一次記録は 4 件しかない**(R2-P1-1 が指摘)— 3 件は 2026-08-31 時点で転記漏れ(復元不能・H-87 の事象)。
2 周目は **R2-P0-1〜9 / R2-P1-1〜11 / R2-P2-1〜4**。採否は反映と同時に記入(「採用」= 計画・設計へ反映 / 「部分」= 一部反映・残余を明記 / 「裁定待ち」)。

| ID | 指摘(要旨) | 根拠 | 採否 |
| --- | --- | --- | --- |
| R2-P0-1 | ステップ 7 の移行状態が成立しない — 宣言 0 件のまま「宣言 or forbidden-only 以外は fail」を有効化すると SP-02 等(`forbidden: []`・Python 分岐あり)が終了コード 2 | `defects.json:39`・`PROP:427` | 採用: `legacy_structural` 一時 allowlist(16 ID)。移行ステップごとに除去、撤去ステップで空集合を検査 |
| R2-P0-2 | 「forbidden-only」判定で構造分岐の脱落を隠せる — forbidden が先に評価され(`PROP:596-622`)命中すれば構造判定に到達しない。SP-18 の異常 corpus は forbidden にも一致 | `PROP:596`・`test_check_design_propagation.py:252` | 採用: 構造宣言必須 ID を **固定集合 16** として検査(forbidden の有無から推論しない)。corpus の異常例は forbidden literal を含まない構造専用に |
| R2-P0-3 | MT-01 の scope 1 行改訂は oracle の他記述(`location`・`positive`・`mapping` の「13 アンカー」)と矛盾し、「節 1 が再出現しない」検査を失う。欠陥 ID 集合一致では消失を検出できない | `defects.json:445-471`・fixture `:18` | 採用: **人間の再裁定 (a′)**(2026-09-04)— MT-01 エントリ内を一貫改訂(ステップ 3)+ `absent-section` 型を追加し MT-01 の宣言で節 1 の不在を機械保証(ステップ 16)。種別は 13 |
| R2-P0-4 | `assets: {}` +「対象なし」で 4 検査が恒久的に無効化できる(データモデル用プロファイルも空 assets で登録可)= 受け渡し契約 5 を満たさない fail-open | design 6-2・`TSK250PLAN:212` | 採用: プロファイルに **`required_checks`** を必須化。必要検査の資産欠落は終了コード 2。`not_applicable` は理由付き明示宣言に限る |
| R2-P0-5 | `assets` の例が TSK-270 実資産の形(`auth-catalog.json` と `ddl-elements.json` に分離・複数トップレベル配列)を読めない。`claims` がステップ 18 から脱落 | `contracts/authz/auth-catalog.json:40`・`ddl-elements.json:1` | 採用: `auth_catalog` / `ddl_elements` / `claims` / `waiting` / `forbidden` / `baseline_digest` を別 asset に。各 `schema_version`・`asset_kind`・複数 collection・join key を契約化。fixture は現行 JSON のトップレベル構造と同形 |
| R2-P0-6 | 欠陥台帳の結合スキーマ(id / check / detection / invariant 宣言)が TSK-250 の作成形式と接続されていない。TSK-250 は検査スクリプトを変更しない契約 | `PROP:238`・`TSK250PLAN:130`・`:214`・`:141` | 採用: 結合スキーマを design で固定し 申し送りへ。合成の「データモデル型最小プロファイル」を fixture に置く |
| R2-P0-7 | ステップ 24「列挙時に `--document` を fail」は、`--profile` なしで `--document` を使う安全網 2 本(`:711`・`:731`)を壊す | `PROP:1274`・`test_check_design_propagation.py:711,731` | 採用: `--document` 単独は既定(同期)プロファイルに束縛(互換維持)。列挙は「引数なし」のときだけ |
| R2-P0-8 | glob 列挙はプロファイルの脱落(削除・改名)を検出しない。重複文書・重複 name・namespace 衝突も未規定 | design 9 | 採用: **`profiles/registry.json`**(期待集合)と実ファイル集合の完全一致、document / name / namespace の一意性を検査 |
| R2-P0-9 | 名前空間 `["SP","MT"]` は現行台帳(CI-01〜11・LG-01〜08 も存在)を表さない。未知 ID fail-closed と衝突 | `defects.json` 全 ID | 採用: 名前空間を全欠陥用(`SP/MT/CI/LG`)と機械欠陥用に分離。既存全 ID をロードする受け入れテストをステップ 4 に |
| R2-P1-1 | 1 周目 P1 7 件の閉塞を一次記録から追跡できない(記録は 4 件) | worklog 08-31 `:25-61` | 採用(部分): 上記の安定 ID と対応表。3 件は復元不能と明記 |
| R2-P1-2 | 1 ステップ = 1 確定単位の違反(15: 最終型移行 + 全撤去 / 18: スキーマ + 解釈器 + ローダー + fixture / 23: ランナー + fixture + テスト) | `HARNESS:271` | 採用: 15 → 3 分割(最終型 / 完全性検証 / 撤去)、18 → 2 分割(契約スキーマ・ローダー / 合成資産)、23 → 2 分割 |
| R2-P1-3 | 共通合格条件「worklog 転記」がステップ 1・2 の差分制限(「X のみ」)と矛盾 | plan 共通条件 | 採用: 全ステップの許可差分に worklog を明示 |
| R2-P1-4 | node ID 基準は自己書換え可能。skip / xfail / 空テストを検出しない | plan 4 節 | 採用: 基準ファイルを無変更 oracle に追加(SHA-256 を計画に固定)。`skipped/xfailed/deselected = 0` を共通条件に |
| R2-P1-5 | `guard_paths` 委任の統制空白に受容条件が無い。`tests/fixtures/profile-sample/` がディレクトリ名のみでファイル未確定 | `core-areas.json:3`・`TSK250PLAN:235` | 部分: 新設ファイルを個別列挙(最終一覧はステップ 25 で確定)+ 申し送りに「TSK-250 の最初の独立コミットで登録」の順序制約。**空白そのものは 2026-09-04 の人間の裁定で受容済み** → 残余リスクとして記録 |
| R2-P1-6 | digest の canonicalization(順序・結合・envelope・文字コード)未定義。`unique-owner` が owner の実在と期待 ID 全集合を見ない | design 6-2・`TSK250PLAN:214` | 採用: RFC 8785 相当(キー順・UTF-8・空白なし)+ id 順の項目 digest を改行結合 + envelope。`unique-owner` に期待 ID 集合と許可 step 集合を入力 |
| R2-P1-7 | 帰属先「節の実在」の文法が未定義(`2-1・4〜9` の列挙・範囲表記が現行にある) | `sync-protocol.md:1848` | 採用: destination 文法(単一 / `・` 列挙 / `〜` 範囲)をスキーマ化。未解析トークンは終了コード 2。現行 212 件の解析完全性を固定 |
| R2-P1-8 | shadow 比較が reason の内容と複数違反の順序を固定しない | design 2-2 | 採用: reason を構造化(kind / section / expected / actual / token)、違反は順序付きリストで比較 |
| R2-P1-9 | 参照分類がパス分類のみで、参照ごとの役割(同じ feature 文書を証拠 / 規範根拠として使う場合)を区別できない。優先順位・未一致・複数一致が未定義 | design 7 | 採用: 順序付き規則の first-match + 参照元の節による role 上書き。未一致は終了コード 2 |
| R2-P1-10 | 新 4 検査と既存「12 検査」(10.1)の関係が未定義。独立 ID を足すと「12」が事実でなくなる | `HARNESS:675`・`PROP:13` | 採用: 全 check ID 対応表を design に。**新検査は新 ID・`required_checks` で有効化・同期プロファイルでは有効化しない**ため同期正本は 12 検査のまま(10.1 は事実のまま) |
| R2-P1-11 | コンフォーマンスランナーの機械契約(引数・出力形式・終了コード・最小コマンド)が無い | plan ステップ 23 | 採用: CLI synopsis・exit 0/1/2・JSON 結果スキーマ・最小実行コマンドを design に固定し申し送りへ |
| R2-P2-1 | 不変条件種別の件数表記が不一致(「10 種」と表の 11 種 + `unique-owner`) | plan 4 節 | 採用: **12 種**(11 + `unique-owner`)で全箇所統一 |
| R2-P2-2 | `tests/test_hooks.py` に既存の wrapper 検査(表なし・空表)がある(design 10 節の事実認識誤り) | `test_hooks.py:814,1022,1116` | 採用: ステップ 1 の許可差分・合格条件に含める |
| R2-P2-3 | 見出し検出がコードフェンス内の疑似見出しと否定形の見出しを扱わない | `codex_run.py:62` | 採用: fenced code 除外 + 否定形見出しの負例をステップ 1 に |
| R2-P2-4 | 基準が「875 passed」と「875 件以上」で揺れる | plan 1 節・ステップ 25・DoD | 採用: 総数は下限 / 既存 875 node ID は固定集合包含 / 新規テストは別集合、の三者を明記 |

**2 周目の反映**(全 24 件を採用・R2-P1-5 は部分): design.md を全面改訂(0 節裁定表 / 1-1 レジストリ / 1-2 `required_checks`・`not_applicable`・名前空間分離 /
2-1 種別 13 / 2-2 構造専用 corpus + 構造化 reason / 2-3 結合スキーマ / 4 (a′) / 5 `--document` 互換 + 5-1 check ID 全体表 / 6-1 別 asset・同形 fixture・
データモデル型最小プロファイル / 6-2 canonical JSON・`unique-owner` 強化 / 7 順序付き規則 + 節別上書き / 8 destination 文法 / 10 fenced code・否定形 /
11 申し送り 13 項目 / 13 ランナー契約 / 14 基準線の固定と残余リスク)。plan.md はステップ表を 25 → **30**(15 の 3 分割・18 の 2 分割・23 の 2 分割・
`absent-section` ステップ追加)、共通合格条件に skipped/xfailed/deselected = 0・基準ファイル digest・worklog を許可差分に。`計画レビュー周回: 1 → 2`。
機構チェック: 30 ステップ連番・`has_filled_step_row` True・docs-lint green・99 tests green。**3 周目(敵対)を起動**。

### 計画レビュー 3 周目(敵対・sol xhigh)= **否決** / P0 10・P1 7・P2 2(一次記録 — H-87)

R2 閉塞判定(レビュアー): 閉じた 7(R2-P0-2/7/9・P1-3・P2-2/3/4)/ 形だけ 5(R2-P1-2/4/8/9・P2-1)/ 未対応 7(R2-P0-1/4/5/6・P1-1/6/7)/
新たな矛盾 5(R2-P0-3/8・P1-5/10/11)。**Claude が原典で確認した事実**: `requirement-claims.json` の claim ID は `source_id`・`asset_kind` 無し /
`ddl-elements.json` は `policies[*].policy_id` と `tables[*].policy_ids[*]` が別 / `auth-catalog.json` の entry に DDL 要素 ID 無し /
SP-01 の scope は `6-3、7-1、7-2` だが corpus の異常例は `7-2` のみ / `--checks` 単独で既定文書を検査するテストが両検査にある / 帰属先セルに理由文・説明文付きがある。

| ID | 指摘(要旨) | 根拠 | 採否(案) |
| --- | --- | --- | --- |
| R3-P0-1 | check ID の完全性が自己申告(`required_checks ∪ not_applicable` が全 ID を覆う規則が無い)。新 ID が 6 と 7 で不一致。DoD「含めなければ終了 2」と同期の設計が矛盾 | design 1-2・5-1、plan ステップ 4/20/22/28 | 採用: 全 21 ID(既存 14 + 新 7)の**完全分割**を終了 2 で強制。データモデル型は新 7 を `not_applicable` にできない。6→7 を全箇所統一 |
| R3-P0-2 | `assets` 契約が実ファイルを読めない(`claims` の ID は `source_id`・`asset_kind` 無し・DDL の配列値パスの位置) | `requirement-claims.json:1-3,413`・`ddl-elements.json:219,230` | 採用: 現物に対する宣言例を固定(`claims=$.claims[*]/source_id`・join の異名キー・DDL 2 collection・`asset_kind` 不在を許す資産型の明示) |
| R3-P0-3 | `auth_catalog → ddl_elements` の結合キーが存在しない(entry に DDL 要素 ID が無い) | `auth-catalog.json:40-48` | 採用: AUTH 主張 → DDL 要素の**写像資産**(`auth_ddl_map`)を契約に追加(申し送り)。probe DDL を製品マニフェストへ要求しない射程規則 |
| R3-P0-4 | サンプル資産が全 21 検査を自己完結実行できない(manifest / invariants / requirements / universe / 帰属表・台帳文書が一覧に無い) | plan 3 節・design 13 | 採用: サンプル全ファイルをリテラル列挙。全 21 ID 実行時に同期側パスを一度も開かない統合試験 |
| R3-P0-5 | MT-01 の二段移行: MT-01 は現行 forbidden のみで構造 corpus にできない(ステップ 2 の 17 件は不成立)/ 第 2 の対で 18 対 / `structural_required` 外なので absent 宣言を落とせる | `PROP:427-593,596-623` | 採用: ステップ 2 = 旧分岐 16 件の構造 corpus + MT-01 literal 対は別 corpus。`absent-section` 導入時に MT-01 を 17 件目として追加。`required_declarations: [MT-01]` で必須化。ステップを DSL 骨格直後へ前倒し |
| R3-P0-6 | 「節不在 = 終了 2」が既存 corpus を入力エラーへ変える(SP-01 の異常例は scope 3 節のうち 7-2 のみ) | `defects.json:23-36`・test `:164-167` | 採用: ステップ 2 で全 corpus の全 scope 見出しを実在させ「終了 1・入力不正 0」を固定。`absent-section` は節解決の事前検査から除外 |
| R3-P0-7 | `legacy_structural` と結合規則 (i) が矛盾(宣言 0 件・allowlist 16 のステップ 7 が規則を満たさない) | design 2-1・2-3 | 採用: 正式な結合式 — 宣言必須 = `structural_required − legacy_structural`、legacy 内は旧評価器必須、重複禁止、最終時 legacy 空 |
| R3-P0-8 | TSK-250 の受け渡し順が循環(実プロファイルを置くと未登録で終了 2、登録すると資産欠落で終了 2)。欠陥台帳の `check` / `invariant` が TSK-250 側に無い | design 11・13・`TSK250PLAN:130,213-217` | 採用: staging 場所で作成 → 資産完成後にプロファイル移設 + registry 登録を同一コミット、の順序を申し送り。TSK-250 は**着手前に再レビュー**(既定路線)。結合スキーマを成果物へ明記 |
| R3-P0-9 | digest / `unique-owner` の自己正当化(`expected_ids` 省略で恒真・`immutable_fields` がプロファイル選択・RFC 8785 の順序は UTF-16) | design 6-2(c) | 採用(部分): `expected_ids` 必須・`immutable_fields` はスキーマ版で固定・RFC 8785 を名乗らず自前 canonical(UTF-8 バイト順・空白なし・重複キー拒否)を明記 |
| R3-P0-10 | 13 種 DSL が名前だけ(kind 別必須引数・値域・評価順が無い)。SP-09 の `exact-set` 分がステップ 12 に無い、SP-19 の kind 不明 | design 2-1、plan ステップ 10/12/14 | 採用(部分): kind 別 JSON 形・必須項目・評価意味の表と、16 + MT-01 → 宣言の完全対応表を design に。SP-09 は 3 宣言をステップ 12 で、SP-19 の kind を明記 |
| R3-P1-1 | destination 文法が現行 212 行を表現しない(「対象外」行は理由文・節参照に説明文が続くセル) | `sync-protocol.md:1852,1884` | 採用: `kind` ごとの判別共用体(対象外 = 理由文法 / 他 = 節式 + 任意の説明文) |
| R3-P1-2 | shadow 比較の oracle が未定義のまま削除される(旧は first-failure の文字列 1 件、新は順序付きリスト) | design 2-2、plan 17/18 | 採用: 旧 16 ID の期待構造化 reason を独立 fixture に固定。新評価器も first-failure。撤去前に fixture oracle へ移す |
| R3-P1-3 | 1 委任 1 論理変更になっていない(ステップ 4 の fail 条件はローダー未存在・21 は 5 機構同時・25 は 2 ID 同時) | plan 4/21/25 | 採用: 4 の fail 条件を 5 へ、21 を 2 分割、25 を 2 分割 |
| R3-P1-4 | 「引数なし」判定が `--checks` / `--defects` 単独の既定文書互換を壊す | test `:773-785`・COV test `:238-252` | 採用: 列挙は「選択・上書き引数が一切無い」経路のみ。selector 単独は既定同期プロファイルへ束縛 |
| R3-P1-5 | `reference-class` の節別上書きは同一節内の複数リンクを区別できない。pattern 文法未定義 | design 7 | 採用(部分): 規則の条件を `source_section + target_pattern(glob・正規化相対パス)+ fragment` に拡張。複数一致は先勝ち・未一致は終了 2 |
| R3-P1-6 | 新設ファイル一覧と guard 登録対象が混同(`assets/{…}` は列挙でない。`git diff` 全追加は docs も含む) | plan 3 節・ステップ 30 | 採用: 「PR の全追加ファイル」と「core-guard 登録対象の実行資産」を別の exact-set に。サンプルを実パス 1 行ずつ |
| R3-P1-7 | 回帰基準が XPASS・テスト空実装化を許す | design 14-1 | 採用: `xpassed = 0` を追加。最終ステップに「各負例が期待 check ID で fail する統合表」 |
| R3-P2-1 | worklog の採否欄「12 種」・「ステップ 25」・決定欄の (a) が現行値と違う | worklog | 採用: 履歴は改変せず「現行値」注記を追記(本節末尾) |
| R3-P2-2 | ランナーの `--json` 時の終了 2 の出力契約が無い | design 13 | 採用: 0/1/2 全部の JSON envelope を固定 |

**人間の裁定(2026-09-04・R3 否決後)**: **R3 全件反映 → 4 周目も通常の敵対レビュー**(打ち切り案 3 つを提示したうえでの選択)。上表の「採否(案)」は全件そのまま採用。

**3 周目の反映**: design.md — 1-1 レジストリに `must_require`・作成順(staging → 移設 + 登録を同一コミット)/ 1-2 完全分割規則・パス解決基準 /
2-1 kind 別必須引数表 + 16 + MT-01 → 宣言の完全対応表(SP-09 = 4 宣言・SP-19 = 節指定 `forbidden-element`)・first-failure / 2-2 結合規則を式 1〜5 に・
`required_declarations` / 2-3 構造 corpus 16 + MT-01 17 件目・scope 全節実在・期待構造化 reason fixture・三者一致・撤去順 / 3 `absent-section` を事前検査から除外 /
5 選択・上書き引数単独は既定に束縛 / 5-1 全 21 ID / 6-1 現物の項目名に合わせた宣言例(`source_id`・`identity`・DDL 2 collection・`auth_ddl_map` 新規契約・`auth_target`)/
6-2 自前 canonical(RFC 8785 を名乗らない)・`expected_ids` 必須・`immutable_fields` は版固定 / 7 規則条件 `source_section + target_pattern + fragment` /
8 `kind` 別 destination 文法 / 11 申し送り 15 項目 / 13 全終了コードで JSON envelope / 14-1 xpassed = 0・統合表。
plan.md — ステップ 30 → **34**(共通ローダーを独立ステップ 5・`absent-section` を DSL 骨格直後の 9・COV 新 2 ID を 21/22 に分割・資産を 23/24/25 に分割・
新検査 5 ID を各 1 ステップ)、3 節を **A 表(PR 全ファイル)/ B 表(guard 登録対象)** に分離しサンプルを実パスで列挙。`計画レビュー周回: 2 → 3`。**4 周目(敵対)を起動**。

**現行値の注記(R3-P2-1・R4-P2-4 で更新)**: 履歴上の数値(R2 採否欄「12 種」「ステップ 25」、R3 反映「ステップ 34」、決定欄「(a)」)は各時点の値で改変しない。
**現在の値は本節末尾の「現行値(最新)」が正**。

### 計画レビュー 4 周目(敵対・sol xhigh)= **否決** / P0 8・P1 3・P2 4(一次記録 — H-87)

R3 閉塞判定(レビュアー): 閉じた 12(R3-P0-1/2/4/6・P1-1〜5/7・P2-2)/ 形だけ 3(R3-P0-8/9/10)/ 未対応 1(R3-P2-1)/ 新たな矛盾 3(R3-P0-3/5/7)+ R3-P1-6。
**Claude が原典で確認した事実**(`PROP:432-593` 全文): SP-19 の forbidden literal「`D1=5` の位置には」は構造分岐の判定文字列と**同一**で、forbidden が先に評価されるため
**構造分岐は到達不能(死コード)** / SP-01・SP-02・SP-12・SP-20 は**行スコープ**の述語(識別行・needle 行の中の包含・除外)/ SP-07・SP-10・SP-11 は**行の存在**だけ /
`cross-reference` に対応する分岐は**存在しない**(SP-07・SP-10 は exact-set + 行存在)。→ 旧分岐の述語は「行の存在 / 行内包含 / 節内包含(text・identifier・identified-row・row の 4 モード)/ 経路 exact-set / 行スコープ禁止 / 選言 / 除外 / 含意 / 強調対」に**一対一**で写せる。

| ID | 指摘(要旨) | 根拠 | 採否 |
| --- | --- | --- | --- |
| R4-P0-1 | ステップ 8 が `required_declarations=[MT-01]`・宣言 0 件を「有効化フラグ」で黙認(式 2 が常時強制されない) | plan 8/9 | 採用: フラグを設けない。ステップ 8 は `required_declarations: []`、ステップ 9 で MT-01 の宣言と必須化を**原子的に**追加 |
| R4-P0-2 | kind 表では旧分岐を再現できない(SP-02 の行所属・SP-12 の識別行 + 表行・SP-10 は行存在のみ) | `PROP:445-452,520-525,530-541` | 採用: kind を実述語に合わせて再定義 — `row-contains` 新設・`required-element` → `section-contains`(4 モード)・`cross-reference` は該当分岐なしで**廃止**。16 → 宣言の対応表を全面改訂。「literal を別行へ移す」変異を全 ID に |
| R4-P0-3 | SP-19 の構造 corpus は作成不能(forbidden と同一文字列・構造分岐に到達しない) | `defects.json:258-276`・`PROP:570-572,619-623` | 採用: SP-19 を **forbidden-only** に(`structural_required` = **15**)。oracle 無変更(死コードは撤去ステップで削除) |
| R4-P0-4 | SP-01 を依存 kind の実装前に allowlist から除外(依存逆転) | plan 11/12 | 採用: 移行を **kind 単位**に並べ替え、各 ID は必要 kind が揃った最初のステップで移行。残数を再計算 |
| R4-P0-5 | `auth_ddl_map` が空でも交差検査が通り、参照方向を検査できない | design 6-1/6-2 | 採用: catalog ID 集合と map ID 集合の exact-set・各 entry の DDL 参照非空・FORB は `participants` + `direction` の構造タプルで照合・空/脱落/過剰/方向衝突の負例 |
| R4-P0-6 | `attribution-direct` が必須でも `direct_requirements` 空で恒真 | design 8・plan 22 | 採用: 必須時は独立資産 `direct-requirements.json`(非空・母集合 ⊆)を必須。空は `not_applicable` のときだけ |
| R4-P0-7 | digest の `immutable_fields` の実集合が未列挙(実装者が選べる) | design 6-2 | 採用: スキーマ版 1 の immutable / mutable exact-set を design に列挙。フィールド 1 件ずつの変異テスト |
| R4-P0-8 | staging 手順が現行契約で実行不能(未登録 = 終了 2 / ランナーに registry 引数なし / 全検査 0 の時期 / 欠陥台帳の項目) | design 1-1・11・13 | 採用: `--registry` を契約化(staging 用レジストリ・`must_require` = 21)。全検査 0 は**文書是正後**、それ以前は `partial` 診断。TSK-250 の計画変更点(資産パス・ステップ・検証コマンド・欠陥台帳の `check`/`invariant`)を申し送りに列挙 |
| R4-P1-1 | `not_applicable` の理由を空文字で通せる | design 1-2 | 採用: trim 後 minLength 1・未知 ID は終了 2 |
| R4-P1-2 | 正規化後の ID 衝突を拒否しない | design 6-1 | 採用: 正規化を単射として検証、衝突は終了 2(明示 alias のみ例外) |
| R4-P1-3 | B 表「guard 登録対象」に `codex_run.py`(対象外)が混在 | plan 3 節 | 採用: **A(全差分)/ B(guard 登録)/ C(実行資産だが guard 対象外)** の 3 集合に分離 |
| R4-P2-1 | destination 文法に列挙中の単独章番号(`2-1・6・9`)が無い | `sync-protocol.md:1849` | 採用: `section_atom := chapter \| section` |
| R4-P2-2 | ステップ 18「式 5 の事前検証」は式 5 ではない | plan 18 | 採用: 「式 5 の前提検証(legacy 空)」と改称。式 5 は撤去と同時に検査 |
| R4-P2-3 | 複数 kind を 1 コミットに束ねた移行ステップが残る | plan 12/14/16 | 採用: kind 単位に分割(評価器のみのステップを許す) |
| R4-P2-4 | worklog の現行値注記が陳腐化 | worklog | 採用: 「現行値(最新)」を末尾 1 箇所に集約 |

**4 周目の反映**: design 2-1 を実述語ベースの 13 種(`forbidden-element` / `row-selector` / `row-contains` / `section-contains` / `exact-set` / `element-lookup` /
`row-scoped-forbidden` / `any-of` / `required-exclusion` / `conditional-forbidden` / `well-formedness` / `unique-owner` / `absent-section`)へ、対応表を 15 + MT-01 で全面改訂。
plan ステップは 34 → **36**(DSL 群 = 骨格 / absent-section / kind 10 ステップ / 前提検証 / 撤去 の 14)。`計画レビュー周回: 3 → 4`。**5 周目(敵対)を起動**。

### 計画レビュー 5 周目(敵対・sol xhigh)= **否決** / P0 6・P1 3・P2 7(一次記録 — H-87)

R4 閉塞判定(レビュアー): 閉じた 9(R4-P0-1/4/6・P1-1/2/3・P2-2/3/4)/ 形だけ 5(R4-P0-3/5/7/8・P2-1)/ 新たな矛盾 1(R4-P0-2)/ 未対応 0。**P0 は 10 → 8 → 6 と収束傾向**。

| ID | 指摘(要旨) | 根拠 | 採否 |
| --- | --- | --- | --- |
| R5-P0-1 | 汎用結合規則が同期固有の 15 ID を固定(式 1)しており、TSK-250 の `invariants/data-model.json` をロードできない | design 2-2・`TSK250PLAN:127-133` | 採用: 式 1 を `structural_required ⊆ M` の集合制約に。SP 15 ID の exact-set は**同期プロファイル専用のコンフォーマンステスト**へ |
| R5-P0-2 | `exact-set` の引数(`section` 単数)で SP-06(3 節 × P1〜P3)を表現できない | design 2-1・`PROP:459-467` | 採用: `sections`(複数)を正式引数に |
| R5-P0-3 | 「別行移動を全 ID で red」は節スコープの旧述語(SP-03/13/14/16)と両立しない | `PROP:554-566` | 採用: 別行移動は**行スコープ kind のみ**。節スコープは「別節へ移動」「要素の意味部欠落」に |
| R5-P0-4 | AUTH–FORB の参照方向を比較するデータが `auth_ddl_map` に無い | design 6-1/6-2・`TSK250PLAN:173-181` | 採用: `auth_ddl_map.entries[*].structures`(正規化済み構造タプル `kind/source/target/direction/participants`)を契約に。③ はタプル照合(禁止方向 red・逆方向 green の対) |
| R5-P0-5 | digest の immutable に `baseline` が無い(TSK-250 契約は `baseline: true` で固定) | `TSK250PLAN:130` | 採用: `baseline` を immutable に追加・反転変異を負例に |
| R5-P0-6 | destination 文法が混合式 `2-1・4〜9` を解析できない | `sync-protocol.md:1848` | 採用: `節式 := segment (・ segment)*`、`segment := section_atom \| chapter〜chapter`。回帰例に `2-1・4〜9` |
| R5-P1-1 | サンプル配置がレジストリの実ファイル完全一致規則と矛盾(同ディレクトリの補助 JSON が未登録扱い) | design 1-1・plan 3 節 | 採用: `profile-sample/profiles/` をレジストリ専用に、文書付随 JSON は `profile-sample/doc/`、資産は `assets/`。`must_require` はレジストリ entry のフィールド(プロファイル側には置かない)と統一 |
| R5-P1-2 | TSK-250 の現行ステップ順では staging を検証できない(資産が後から作られる・新必須資産 3 つが無い) | `TSK250PLAN:212-217` | 採用: 申し送りに「最初に staging registry・profile・全必須資産の構造的に妥当な骨格を**原子的に**作るステップ」を固定。その後だけ終了 1 の診断を許す |
| R5-P1-3 | 結合規則が宣言集合 D の余分な要素(SP-19・人間欠陥への宣言)を拒否しない | design 2-2 | 採用: `D ⊆ M` と `D ⊆ structural_required ∪ required_declarations` を追加。同期の移行完了時は `D = structural_required ∪ required_declarations`(exact)をコンフォーマンステストで固定 |
| R5-P2-1 | reason fixture が複数入力(corpus / fixture / approved)を識別できない | design 2-3 | 採用: キーを `(case_id, defect_id)`、入力種別と期待終了コードを持つ |
| R5-P2-2 | staging の `partial` 記述がランナー契約と不一致 | design 1-1・13 | 採用: 全 21 検査の反復は `partial: false` の不適合診断と記述 |
| R5-P2-3 | スキーマ作成ステップの重複(4 / 8 / 25)と資産ローダー(25)より先の `attribution-direct`(24) | plan | 採用: 4 = profile/registry スキーマのみ、invariant は 8、assets は資産群。`attribution-direct` を資産群の後へ |
| R5-P2-4 | 共通条件「worklog を許可」と個別条件「〜のみ」の不整合 | plan | 採用: 個別条件を「worklog を除く実装差分が〜のみ」に統一 |
| R5-P2-5 | `defects.json` が B 集合から漏れている | plan 3 節・`core-areas.json:11` | 採用: B に「登録済み」として含め、A = B ∪ C ∪ 文書 |
| R5-P2-6 | 正規化の単射性の集合境界が未定義 | design 6-1 | 採用: 正規化名前空間(要素種別ごと)を定義し、単射性は名前空間内。alias 同値類の意図的一致は許容 |
| R5-P2-7 | `unique-owner` が kind と check ID の双方にあるが宣言形式が無い | design 2-1 | 採用: DSL kind から外し **check ID(global invariant)のみ**。あわせて**契約の種別名との対応**(`required-element` = `section-contains` の alias / `cross-reference` は契約どおり提供〔合成 corpus〕/ `unique-owner` = check ID)を design と申し送りに明示 |

**5 周目の反映**: design 2-1 を 13 種(`forbidden-element` / `row-selector` / `row-contains` / `section-contains`〔alias `required-element`〕/ `exact-set`〔`sections`〕/
`cross-reference`〔契約種別・合成〕/ `element-lookup` / `row-scoped-forbidden` / `any-of` / `required-exclusion` / `conditional-forbidden` / `well-formedness` / `absent-section`)、
2-2 を集合制約 + 同期コンフォーマンステスト、6-1/6-2 に構造タプル・`baseline`、8 に混合式文法、11 に申し送り 17・18。plan は 36 → **37**(`cross-reference` の評価器ステップを追加・
`attribution-direct` を資産群の後へ・スキーマ責務を整理)。`計画レビュー周回: 4 → 5`。**6 周目(敵対)を起動**。

### 計画レビュー 6 周目(敵対・sol xhigh)= **否決** / P0 5・P1 3・P2 4(一次記録 — H-87)

R5 閉塞判定(レビュアー): 閉じた 12 / 形だけ 3(R5-P0-4・P1-2・P2-7)/ 新たな矛盾 1(R5-P1-1)/ 未対応 0。**P0 は 10 → 8 → 6 → 5**。
新規 P0 は「TSK-250 が checker を変更せずに 4 検査を使えるか」(構造抽出の宣言・`exact-set` の relation・claims と manifest の集合一致)に集中。

| ID | 指摘(要旨) | 根拠 | 採否 |
| --- | --- | --- | --- |
| R6-P0-1 | `exact-set` が期待集合を取る manifest relation を宣言できない(旧述語は `R-TXN-ROUTE` 固定) | `PROP:389` | 採用: `relation`(必須)・`field` を引数に。別 relation を同一 manifest に置く負例 |
| R6-P0-2 | `forbidden-structure` に文書から構造タプルを抽出する**宣言**が無い(TSK-250 は checker 変更不可) | design 1-2/6-2・`TSK250PLAN:217` | 採用: プロファイルに **`structure_extractors`**(対象節・表識別・列 → タプル項目の写像・暗黙辺の導出・方向・participants の正規化)をスキーマ化。kind 別の抽出負例 |
| R6-P0-3 | `cross-consistency` が契約より弱い(WAIT は manifest **と本文**、AUTH は manifest 必須。`auth_target` で弱めていた) | `TSK250PLAN:175` | 採用: `auth_target` を**廃止**。WAIT = manifest ∩ 本文、AUTH = `ddl_elements` ∩ manifest を常に要求。probe-only DDL は **`product_ddl_map`**(TSK-250 が作る写像)で製品要素へ写してから照合 |
| R6-P0-4 | WAIT/AUTH–FORB の構造照合に省略可能経路(`structures` 空・脱落・WAIT 側に方向なし・participants を比較キーから落とした) | design 6-1/6-2 | 採用: `structures` は entry ごとに非空・`participants ⊆ refs`・**DDL 資産から導出した構造との exact-set**。WAIT 側は抽出器で manifest/本文から導出。比較キーは両側 `{kind, source, target, direction, participants}`。空・1 件脱落・participants 相違の負例 |
| R6-P0-5 | claims の relation 行と manifest の exact-set を検査する機構が無い(TSK-250 ステップ 5 の要求) | `TSK250PLAN:215` | 採用: 新 check ID **`collection-consistency`**(プロファイルの `collection_sets` で資産 collection 間 / 資産と manifest の exact / subset を宣言)。check ID は **22**(新 8) |
| R6-P1-1 | staging 骨格と `must_require` の配置が自己矛盾(文書が無い時点の終了 2・プロファイル側の `must_require`・staging の木構造未定) | design 1-1・plan 27 | 採用: staging の完全な木(`profiles/` = レジストリ + プロファイルのみ / `doc/` / `assets/`)を固定。原子ステップは**文書の骨格が存在した直後**。`must_require` は常にレジストリ entry(plan 27 の文言修正) |
| R6-P1-2 | `unique-owner` を check ID にしたのは契約(DSL 種別として列挙)の一方的変更 | `TSK250PLAN:42,70` | 採用: **kind 名 `unique-owner` を受理**し、宣言は global check `unique-owner` へ写す(alias 方式)。契約の 5 種別名を全部受理 |
| R6-P1-3 | `well-formedness` が旧 SP-18 の**表の各行**単位の判定を再現していない | `PROP:405,567` | 採用: rule を「Markdown 表の各データ行について `**` が偶数」と明文化。奇数行 2 行・表外奇数の同値テスト |
| R6-P2-1 | C 集合に任意要素(`test_hooks.py` 変更の可能性) | plan 3 節 | 採用: C を必須 / 条件付き(ステップ 1 で確定)に分離 |
| R6-P2-2 | worklog 決定欄の MT-01 が (a) のまま | worklog | 採用: 決定欄に (a′) への上書き注記 |
| R6-P2-3 | partial 実行時の未選択 check の envelope 表現が未定義 | design 13 | 採用: status に `not_run` を追加(`not_applicable` への偽装禁止) |
| R6-P2-4 | SP-12 の第 2 `required-exclusion` が必須引数を満たさない | design 2-1・`PROP:536` | 採用: 引数を `terms: [1..2]`(subject 任意)に変更し、第 2 宣言を `terms: ["D5"]` と明記 |

**6 周目の反映**: design 1-1 staging の木・1-2 `structure_extractors` / `collection_sets`・2-1 `exact-set(relation)`・`required-exclusion(terms)`・`well-formedness`(行単位)・
`unique-owner` alias・5-1 **22 ID**(新 8: + `collection-consistency`)・6-1 `product_ddl_map`・WAIT/AUTH 構造の導出と exact-set・6-2 契約どおりの存在検査・13 `not_run`。
plan は 37 → **38**(`collection-consistency` のステップを追加)、C を必須 / 条件付きに分離。`計画レビュー周回: 5 → 6`。**7 周目(敵対)を起動**。

**現行値(最新・2026-09-04 R6 反映後)**: 種別 **13**(+ 受理する契約 alias: `required-element` → `section-contains(text)`・`unique-owner` → global check)/ 構造宣言必須 **15**(同期・SP-19 は forbidden-only)/
check ID **22**(既存 14 + 新 8)/ 申し送り **20** / ステップ **38**(最終一覧の確定はステップ 38)/ MT-01 = **(a′)** / 計画レビュー周回 **6**。

## 決定

- 新規ブランチ・worktree は切らない(前回保留時の裁定「worktree とブランチは残す」に従う)
- **人間の裁定 2026-09-04(/plan 冒頭)**:
  1. MT-01 → **(a) oracle の正当な改訂**(独立ステップで `1節` を scope から外す)
     → **R2-P0-3 を受けて同日 (a′) へ上書き**(oracle 改訂 + `absent-section` 型・R6-P2-2 で注記。現行値は末尾の「現行値(最新)」)
  2. `codex_run.py` の `has_filled_step_row` → **本タスクに含める**
  3. `scripts/check_authz_catalog.py` → **対象外・前例として資産書式を借りる**
  4. `guard_paths` への新資産登録・台帳 H-78/H-79 追記 → **すべて TSK-250 に委ねる**(本タスクは `core-areas.json` と台帳を触らない)
- 上記 4 に伴い、設計書 10.1 `docs-lint` 行の現行化も TSK-250 ステップ 22 へ(マージ時点で文言は事実のまま。H-19 ⑥ の前例に照らし規範条件に触れる改訂を本タスクから外す)
- 調査 3 本の観点は「要件 / 旧システム / 決定」の既定から**「コード差分 / 決定 / 受け渡し契約」へ振り替え**た
  (本タスクは既存コードの一般化で、旧システムは射程外。受け渡し契約が事実上の要件)

## 未決・次の一歩

- **/plan へ**。計画レビュー 1 周目の **P0 6 件・P1 7 件**+ 再検証で増えた論点 4 件の反映(対応表は `research.md` 6-7 節)。
  **人間の裁定が要るもの**: ① MT-01(oracle 改訂 / 意味型の分離 / warning 化)② `has_filled_step_row` を射程に含めるか起票か
  ③ `check_authz_catalog.py` を多文書対応の対象に含めるか ④ guard_paths 登録・H-78/H-79 追記の A/B 分担
- 前提のずれは `research.md` 6-2 節で現行化済み(/plan 冒頭の再確認は不要)
