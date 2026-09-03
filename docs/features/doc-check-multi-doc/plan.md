---
feature: doc-check-multi-doc
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3cc93b75e6878194b72bcc12219d6cdb
branch: feature/doc-check-multi-doc
created: 2026-08-31
計画レビュー周回: 7        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 文書検査機構の多文書対応(プロファイル化 + 不変条件 DSL)

## 1. 背景・目的

**下調べ**: [research.md](research.md)(1〜5 節 = 2026-08-31 / **6 節 = 2026-09-04 の再検証**)。**詳細設計**: [design.md](design.md)(2026-09-04)。
前提事実・基準線は research.md が、設計判断の根拠は design.md が正で、**本書へ内容を複製しない**(設計書 7.1-1)。本書は契約(機構が読む状態と実装ステップ表)のみを持つ。
計画レビューの指摘(`R1-*`〜`R7-*`)の一次記録と採否は worklog 2026-09-04 が正。

- Notion タスク: [TSK-269](https://app.notion.com/p/3cc93b75e6878194b72bcc12219d6cdb)
- **受け渡し先**: [TSK-250](https://app.notion.com/p/3c593b75e6878152b3edd6cf4f26b30b)(計画承認済み 2026-08-31・develop 未マージ)。
  **本タスクのマージが TSK-250 の開始条件**であり、TSK-250 の計画書 1 節に**受け渡し契約 5 項目**がある(research 6-4 節)。
  **TSK-250 は本タスクのマージ後・着手前に再レビューが必要**(design 11 節の申し送り 23 項目)

現在の検査機構は `docs/design/sync-protocol.md` 専用に書かれている。二文書目(データモデル正本)を同じ強度で検査するには一般化が要る。
**TSK-250 の計画レビューで、この一般化が同一 PR に収まらないと判定されたため独立タスクとして切り出された**(人間の裁定 2026-08-31)。
2026-08-31 に計画レビュー 1 周目(否決)まで進んだのち TSK-270 先行のため保留し、2026-09-04 に再開した(TSK-270 完了・PR #33)。

**本タスクの性格は「既存コードの一般化」であり、機能追加ではない。** research.md 6-6 節の基準線(3 検査 green / ruff・ty クリーン /
**既存 node ID 875 件の固定集合を包含** — design 14-1 節)を**最後まで維持すること**が成功条件の中心にある。
ただし TSK-250 が **checker を変更しない**契約のため、二文書目で必要な判定(構造抽出・集合一致・交差)は**すべてプロファイルで宣言できる形**で本タスクが提供する。

**主な要件**: NFR-019(テストを伴う実装)。本タスクは要件の実装ではなくハーネスの機構であるため、FR への直接の対応はない(**該当なし** — research 6-4 節)。
規範の正は設計書 7 章(正本の規律)と 10.1(CI ジョブ表)。

### 人間の裁定

| 日付 | 論点 | 裁定 |
| --- | --- | --- |
| 2026-08-31 | 不変条件の機械判定をどこまで作るか | **既存の構造分岐を宣言へ移行する**(型は動いているコードから抽出)。**前決定「新規機構を発明しない」(`docs/features/sync-protocol-canonical/plan.md:294`)に対する明示的な例外・上書き**(design 0 節) |
| 2026-08-31 | CI 配線 | **プロファイル列挙**(CI の引数を増やさない) |
| 2026-08-31 | 重さ分類 | **コア領域**(sol xhigh・敵対レビュー必須・人間の逐行確認必須) |
| 2026-09-04 | MT-01(R1-P0-1・R2-P0-3・R3-P0-5・R4-P0-1) | **(a′) oracle の正当な改訂 + `absent-section` 型**。MT-01 の宣言は `required_declarations` で必須(有効化フラグを設けない — design 4 節) |
| 2026-09-04 | `codex_run.py` の `has_filled_step_row` | **本タスクに含める**(design 10 節) |
| 2026-09-04 | 第 3 の検査機構 `scripts/check_authz_catalog.py` | **対象外**。資産書式の前例として借りる(design 12 節) |
| 2026-09-04 | `guard_paths` への新資産登録・台帳 H-78/H-79 の実績追記 | **すべて TSK-250 に委ねる**。統制の空白は**受容**(design 14-2 節) |
| 2026-09-04 | 計画レビューの進め方(3 周目否決後) | **全件反映 → 以降も通常の敵対レビュー** |

## 2. スコープ

### やること

1. **プロファイル・レジストリ(`--registry` で staging も指定可)・共通ローダー** — 全 22 check ID の**完全分割**と、レジストリ entry の **`must_*`**(`must_require` / `must_extract` / `must_derive_structures` / `must_collection_sets`)による**必須宣言の固定**を強制(プロファイルの自己申告だけでは必須検査を有効化できない)。スキーマ版を持つ(design 1 節)
2. **不変条件 DSL(13 種 — 旧分岐の述語に一対一 + 契約 5 種別名の受理)** — 構造分岐 15 ID を宣言へ移行し `_structural_reason` の直書き分岐を無くす(SP-19 は死コード → forbidden-only)。
   結合規則は汎用の集合制約(常時強制)+ 同期専用のコンフォーマンステスト。移行の正しさは構造 corpus 15 + MT-01・期待構造化 reason fixture・shadow 三者一致(design 2 節)
3. **fail-closed の徹底**(design 3 節)/ 4. **MT-01 の oracle 改訂 + `absent-section`**(design 4 節)
5. **CLI 名の固定** — `--document` / `--profile` / `--manifest` / `--defects-file` / `--checks` / `--defects`(+ `--registry`)。上書き・選択引数単独は既定プロファイルに束縛(design 5 節)
6. **TSK-250 が要求する 4 検査** + `collection-consistency` + `unique-owner`。入力は `assets`(現物の項目名・`auth_ddl_map` の `structures`・`product_ddl_map`・独立資産)、
   **`structure_extractors`**(文書・マニフェストから構造タプルを導出する宣言)、**`collection_sets`**(集合一致の宣言)で、checker に文書固有の構造をハードコードしない(design 6 節)
7. **コンフォーマンスランナー**(design 13 節)と**サンプル一式**(`profiles/` `doc/` `assets/`・全 22 ID を自己完結で実行できるデータモデル型最小プロファイル)
8. **参照の分類** `reference-class`(design 7 節)/ 9. **帰属検査の強化**(design 8 節)/ 10. **CI 配線の一般化**(design 9 節)/
11. **`codex_run.py` の `has_filled_step_row`**(design 10 節)/ 12. **TSK-250 への申し送り 23 項目**(design 11 節)

### やらないこと

| 対象外 | 受け取り先 | 理由 |
| --- | --- | --- |
| **データモデル用の実プロファイル・実資産(`auth_ddl_map` / `product_ddl_map` / `direct_requirements` / `expected_ids`)・実抽出器・実集合宣言の作成** | **TSK-250** | 二文書目がまだ存在しない。本タスクはランナー・サンプル・データモデル型最小プロファイル(合成)まで |
| **`.claude/core-areas.json` の `guard_paths` への新資産登録** | **TSK-250**(最初の独立コミット) | 人間の裁定 2026-09-04。登録対象は 3 節 B 集合(最終確定はステップ 38) |
| **台帳 H-78・H-79 の実績追記** | **TSK-250**(ステップ 25) | 人間の裁定 2026-09-04。`H-*` 新規採番も禁止のまま |
| **設計書 10.1 `docs-lint` 行・`docs/README.md` の現行化** | **TSK-250**(ステップ 22) | 同期に走る検査は既存 14 のまま(新 8 ID は `not_applicable`)なので現行文言は事実のまま(design 5-1 節)。H-19 ⑥ の前例 |
| **同期側 oracle の内容変更**(`req-universe.json` / `tests/fixtures/sync-protocol-source.txt` / `fixture-sha256.txt`) | — | 触らない。`defects.json` は **MT-01 エントリの範囲だけ**を独立ステップで改訂。SP-19 の oracle も無変更 |
| **同期プロファイルでの新 8 ID の有効化** / **同期正本の本文変更** | (TSK-250 以後)/ — | 既存の振る舞いを変えない / 反映なし |
| **`scripts/check_authz_catalog.py` のプロファイル化** / **`verify_handoff_digest.py` をランナーに載せる** | (TSK-270 系)/ **TSK-250**(ステップ 4) | 人間の裁定 / ランナーは単一プロファイルの検証器 |
| `GLOBAL_CHECK_IDS` の整理 / 意味の判断の機械化 / TSK-270 計画書の暫定回避の注記 | — | R1-P1-2 / 前タスクが断念した領域 / 他タスクの文書 |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| **`docs/development/dev-harness-design-2026-08-07.md`** | **反映なし**(10.1 の「12 検査(引数なし)」は同期に走る検査が既存のままなので事実のまま) | — |
| **`docs/development/harness-evaluation.md`** / **`docs/README.md`** / **`.claude/core-areas.json`** / **`docs/design/sync-protocol.md`** / `docs/requirements/**` / `docs/adr/**` / `contracts/` / `backend/` / `frontend/` | **反映なし** | — |
| `scripts/design_relations/req-universe.json` / `sync-protocol.json` / `tests/fixtures/sync-protocol-source.txt` / `fixture-sha256.txt` | **反映なし**(同期側 oracle) | — |
| **`scripts/design_relations/defects.json`**(oracle・`guard_paths` 該当) | **MT-01 エントリの範囲のみ**(ステップ 3・design 4 節) | PR レビュー + 人間の逐行確認 |
| `docs/features/doc-check-multi-doc/baseline-node-ids-f92b5f8.txt` | **無変更 oracle**(SHA-256 `a07454fcc3e3bc9c365a28f1dc66cec2330bfb08ecede80d8c52725169369046`) | — |

### PR のファイル集合(ステップ 38 で実 diff と突合する exact-set)

**A = PR の全追加・変更ファイル = B ∪ C ∪ 文書**。文書 = `docs/features/doc-check-multi-doc/{plan,design,research}.md`・`baseline-node-ids-f92b5f8.txt`・
`docs/worklog/2026-08-31-doc-check-multi-doc.md`・`docs/worklog/2026-09-04-doc-check-multi-doc.md`。

**B = core-guard 対象の実行資産**(未登録分を TSK-250 が完全列挙で `guard_paths` へ登録):

| 資産 | 内容 | 既存 |
| --- | --- | --- |
| `scripts/design_relations/defects.json`(変更 — MT-01 のみ) | oracle | **登録済み** |
| `scripts/design_relations/profiles/registry.json` / `sync-protocol.json`(新設) | 本番レジストリ・同期プロファイル | 未登録 |
| `scripts/design_relations/schemas/profile.schema.json` / `registry.schema.json` / `invariant.schema.json` / `assets.schema.json`(新設) | スキーマ(版付き) | 未登録 |
| `scripts/design_relations/invariants/sync-protocol.json`(新設) | `structural_required` 15 / `legacy_structural` / `required_declarations` / `declarations` | 未登録 |
| `scripts/doc_check_profile.py`(新設) | 共通ローダー(スキーマ検証・レジストリ・資産・抽出器・集合) | 未登録 |
| `scripts/check_design_propagation.py`(変更) | プロファイル駆動 + 宣言評価器 + 新 6 ID。ID 別分岐を撤去 | **登録済み** |
| `scripts/check_doc_coverage.py`(変更) | プロファイル駆動 + destination 文法 + 新 2 ID | **登録済み** |
| `scripts/check_doc_profiles.py`(新設) | コンフォーマンスランナー | 未登録 |
| `tests/fixtures/profile-sample/profiles/registry.json` / `profile.json` / `data-model-like.json` | サンプル用レジストリ + プロファイル 2 本(**これ以外を置かない**) | 未登録 |
| `tests/fixtures/profile-sample/doc/document.md` / `manifest.json` / `defects.json` / `invariants.json` / `requirements.md` / `req-universe.json` | 合成文書(宣言表・帰属表・台帳・遷移表・列役割表)と付随資産 | 未登録 |
| `tests/fixtures/profile-sample/assets/requirement-claims.json` / `auth-catalog.json` / `ddl-elements.json` / `auth-ddl-map.json` / `product-ddl-map.json` / `waiting.json` / `forbidden.json` / `direct-requirements.json` / `expected-ids.json` / `baseline-digest.txt` | 合成資産(`contracts/authz/` と同形) | 未登録 |
| `tests/fixtures/structural-reasons-expected.json`(新設) | 旧 15 ID の期待構造化 reason | 未登録 |
| `tests/test_check_design_propagation.py` / `tests/test_check_doc_coverage.py` / `tests/test_ci_wiring.py`(変更) | corpus・shadow・プロファイル・fail-closed・新検査(`test_ci_wiring.py` は CI 契約ブロックに触れない) | **登録済み** |
| `tests/test_doc_check_profile.py` / `tests/test_check_doc_profiles.py`(新設) | ローダー / ランナー | 未登録 |

**C = 実行資産だが core-guard 対象外**(登録しない)。**必須**: `.claude/scripts/codex_run.py`(変更)/ `tests/test_codex_run.py`(新設)。
**条件付き**(ステップ 1 で変更要否を確定し、承認後は確定した集合が exact): `tests/test_hooks.py`(wrapper ケースの期待文言追随のみ)。

## 4. 実装方針

### 重さ分類の根拠 — **コア領域**(人間の裁定 2026-08-31)

前例上は「通常」で通せる余地があった(`docs/features/backend-skeleton/plan.md:69`)。それでも**コア領域に倒す**理由は、本タスクの成果物がコア領域文書を検証する機構そのもので、
設計書 6.3「判定に迷うコードは含む側に倒す」に従うため。TSK-281 の前例(`docs/features/core-area-paths/plan.md:75-77`)と整合。→ sol xhigh・敵対レビュー必須・人間の逐行確認必須。
**コア領域(CLAUDE.md の列挙)に触れるか**: 5 領域の本文・実装には触れない。触れるのは `guard_paths` 該当の検査機構で、core-guard が発火する。

### 中核の制約 — **既存の振る舞いを変えない**(design 14-1 節)

すべてのステップの合格条件: `test_fixture_reports_exact_machine_defect_set`(機械 17 件の検出集合の完全一致)/ `test_fixture_default_adds_global_findings` /
**既存 node ID 875 件の固定集合を包含**(基準ファイルは無変更 oracle)/ **passed ≥ 875** / **skipped・xfailed・xpassed・deselected = 0**。
fixture・`fixture-sha256.txt`・`req-universe.json` は不変。`defects.json` はステップ 3 の MT-01 エントリ以外で不変。

### 不変条件 DSL — 既存の構造分岐を宣言へ移行する(前決定の明示的な例外)

種別 13 + 契約 alias・15 + MT-01 → 宣言の完全対応表・結合規則(汎用 1〜6・常時強制)・同期専用コンフォーマンステストは design 2 節が正。
**受け入れ条件**: `_structural_reason` の ID 別分岐 0 件 / `legacy_structural` 空 / 同期の `D = structural_required(15) ∪ {MT-01}`(exact)/ 機械 17 件の検出集合が移行前と完全一致 /
構造 corpus 16 件が新評価器単独で判定 / 期待構造化 reason fixture への一致 / 旧述語と同値な変異が全 ID で red。

### fail-closed / CLI / 4 検査 / 抽出器 / 集合一致 / 参照分類 / 帰属 / CI / `codex_run.py` / ランナー契約

design.md 3・5・6・7・8・9・10・13 節が正。本書には複製しない。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**全ステップ共通の合格条件**(表では省略): `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/ -rA` **green かつ skipped/xfailed/xpassed/deselected = 0** /
**3 検査が引数なしで green** / **安全網 2 本 green** / **既存 node ID 875 件の包含・基準ファイルの digest 一致** /
**fixture・`fixture-sha256.txt`・`req-universe.json` 無変更**(`defects.json` はステップ 3 以外で無変更)/
**checker 実行結果(コマンド・終了コード・要約行)を worklog へ転記**(H-88)。表の「実装差分が〜のみ」は **worklog を除く**範囲。
`legacy_structural` の残数は各移行ステップの合格条件に明記(15 → 0)。【】は群。**見出しで群を分けない**。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | 【基盤】**`codex_run.py` の `has_filled_step_row` を是正** — 見出しレベルのスタック / fenced code 除外 / 見出し名の正規化一致(否定形は負例)/ 3 種の報告。`tests/test_codex_run.py` 新設。**`tests/test_hooks.py` の変更要否を確定**(design 10 節) | **`####` 配下の表を認識** / **同レベル以上の見出しで抜ける** / **別見出し配下の数値表を拾わない** / **fenced code 内の疑似見出し・疑似表を無視** / **否定形見出しは負例** / **3 メッセージが区別される** / **`tests/test_hooks.py` の wrapper ケースが green** / 実装差分が C 集合のみ(条件付き要素の要否を worklog に確定) |
| 2 | 【基盤】**構造 corpus 15 件 + forbidden corpus** — `DEFECT_CHECK_CASES` を旧分岐 15 ID の正常・異常対へ拡充(**異常例に forbidden literal を含めない・各 ID の scope の全節見出しを実在させる**)。SP-19・MT-01 の literal 対は forbidden corpus へ。**design 2-1 節の変異集合(唯一の正)**を ID ごとに用意。検査本体は変更しない | **15 ID すべてに構造専用の正常・異常対と design 2-1 の変異集合** / **各異常例が forbidden literal を含まない**(機械検査)/ **各 corpus 文書に当該 ID の scope 全節の見出しがある**(機械検査)/ **異常例・変異が終了 1、正常例が終了 0(入力不正 0 件)** / 全対が現行コードで green / 実装差分がテストのみ |
| 3 | 【oracle】**MT-01 エントリの一貫改訂**(裁定 (a′) 前半 — design 4 節)— `scope` から `1節` を除き、`location` / `positive` / `mapping` を「12 アンカー + 節 1 の不在」へ。forbidden corpus の MT-01 対の禁止語を `### 2-2.` へ | **`defects.json` の差分が MT-01 エントリの範囲に閉じる**(他エントリ無変更を機械検査)/ **fixture の検出集合が完全一致(MT-01 を含む)** / **approved 正本 green** / `fixture-sha256.txt` 無変更 |
| 4 | 【基盤】**`profile.schema.json`・`registry.schema.json`・本番レジストリ・同期プロファイル**(データのみ)— `profiles/registry.json`(同期 1 件・**entry の `must_require` = 既存 14**)、`profiles/sync-protocol.json`(現行定数の移送・`required_checks` = 既存 14・`not_applicable` = 新 8 の理由付き・`assets` 空・`reference_policy` 現行同値・`invariant_kinds`) | **全フィールドが現行の定数値と一致**(値ごとの突合テスト)/ **全 22 check ID が `required_checks ∪ not_applicable` に現れ、理由が非空**(データ検査)/ **本ステップでスクリプトを変更していない** |
| 5 | 【基盤】**共通ローダー `scripts/doc_check_profile.py`(プロファイル・レジストリ部)** — 最小スキーマ検証器・レジストリ照合(完全一致・一意性・`--registry`)・完全分割と `must_require`・理由非空と未知 ID 拒否・パス解決。`tests/test_doc_check_profile.py` 新設。検査スクリプトはまだ呼ばない | **必須欠落・版不一致・未知フィールド・完全分割違反・`must_require` 違反・空理由・未知 ID・レジストリ不一致(脱落/未登録/重複)・0 件が例外(終了 2 相当)** / **別ディレクトリの staging レジストリ(`profiles/` にレジストリとプロファイル以外が無い木)で同じ検証が動く** / **現行 `defects.json` の全 40 ID が名前空間検査を通る** / 実装差分がローダーとテストのみ |
| 6 | 【基盤】**`PROP` のパスと CLI のプロファイル駆動化** — `DEFAULT_*` とリンク基準をローダー経由に。`--profile` / `--registry` / `--manifest` / `--defects-file` 追加。上書き・選択引数単独は既定プロファイルに束縛(design 5 節) | **引数なし・`--document` 単独・`--checks`/`--defects` 単独・`--profile` 指定の 4 経路で検出集合が変更前と同一** / **安全網 2 本と selector 単独テスト(`:773-785`)が本文無変更で green** / **プロファイル欠落・スキーマ不一致・未知 ID が終了コード 2** |
| 7 | 【基盤】**文法と語彙のプロファイル化 + fail-closed** — 節 ID 文法・`preamble`・除外語彙・引用継承先・非正本走査の開始見出し・宣言表をプロファイルへ。**解決できない節と脱落トークンを終了コード 2** | **未解決の節・脱落トークンで fail する負例** / **corpus 30 文書が終了 1/0 のまま(終了 2 が 0 件)** / **同期プロファイルでの検出集合が完全一致** / `preamble` の意味がプロファイルに明記 |
| 8 | 【DSL】**`invariant.schema.json`(13 種 + 契約 alias・kind 別必須引数)・宣言資産の骨格・汎用結合規則 1〜5・同期コンフォーマンステスト・期待構造化 reason fixture・shadow 基盤** — `invariants/sync-protocol.json`(`structural_required` 15・`legacy_structural` 15・**`required_declarations` = []**・`declarations` 空)、`tests/fixtures/structural-reasons-expected.json`(`(case_id, defect_id)`・旧 15 ID)、三者一致テスト、`forbidden-element`(宣言版)の評価器。判定ロジックは移行しない | **汎用規則 1〜5 の各違反で終了 2 相当**(宣言必須 ID の宣言欠落 / legacy と宣言の重複 / legacy の ID に旧分岐が無い / 余分な宣言 / forbidden-only でない機械欠陥)/ **同期コンフォーマンステスト(15 ID exact)が green** / **kind 別の必須引数欠落・未知 kind で終了 2・alias `required-element` が `section-contains(text)` に、`unique-owner` が global check に写る** / **旧分岐の結果が期待 fixture と全件一致** / **有効化フラグ・xfail が無い** / 検出集合の完全一致 |
| 9 | 【DSL】**`absent-section` 型 + MT-01 の宣言 + `required_declarations = ["MT-01"]`**(裁定 (a′) 後半・原子的)— 事前検査からの除外を含む。構造 corpus の 16 件目 | **fixture(節 1 あり)で MT-01 が宣言でも違反・approved で適合** / **16 件目の対が新評価器で判定** / **`absent-section` の `section` が節不在の事前検査を通る** / **規則 2 が MT-01 を含めて成立** / 検出集合の完全一致 |
| 10 | 【DSL】**`row-selector`(needle / identifier)の評価器 + SP-10・SP-11 の移行**。allowlist から除去。旧分岐は残す | **該当 2 ID の三者一致(期待 fixture・旧分岐・新評価器)** / **新評価器単独で正常・異常対・同値変異を判定** / **`legacy_structural` = 13** |
| 11 | 【DSL】**`row-contains` の評価器 + SP-01 の移行** | 同上 / **別行移動の変異で red** / **`legacy_structural` = 12** |
| 12 | 【DSL】**`section-contains`(4 モード)の評価器 + SP-02・SP-03・SP-13・SP-14 の移行** | 同上 / **4 モードそれぞれの単独負例** / **別節移動・意味部欠落の変異で red** / **`legacy_structural` = 8** |
| 13 | 【DSL】**`exact-set`(`sections` / `row`・`relation` 必須)の評価器 + SP-06・SP-07 の移行** | 同上 / **ID 交換の変異で red** / **3 節すべてで判定(1 節だけ壊す負例)** / **別 relation を同一 manifest に置き、指定 relation だけが使われる負例** / **`legacy_structural` = 6** |
| 14 | 【DSL】**`element-lookup` の評価器 + SP-08 の移行** | 同上 / **接頭辞検索が宣言で表現されている** / **`legacy_structural` = 5** |
| 15 | 【DSL】**`row-scoped-forbidden` の評価器**(移行 ID なし) | **評価器の正常系・別行移動変異** / 三者一致(変化なし)/ **`legacy_structural` = 5** |
| 16 | 【DSL】**`any-of` の評価器 + SP-09 の移行**(4 宣言) | 同上 / **4 宣言それぞれの単独負例** / **`legacy_structural` = 4** |
| 17 | 【DSL】**`required-exclusion`(row / sections・`terms`)の評価器 + SP-12・SP-16 の移行** | 同上 / **除外語彙をプロファイルから変えると判定が変わる** / **`terms` 1 個・2 個の両形** / **`legacy_structural` = 2** |
| 18 | 【DSL】**`conditional-forbidden` の評価器 + SP-20 の移行** | 同上 / **含意の両側にテスト** / **`legacy_structural` = 1** |
| 19 | 【DSL】**`well-formedness`(`\|` で始まる全表行 — ヘッダ・区切りを含む)の評価器 + SP-18 の移行** | 同上 / **奇数行 2 行(合計偶数)で red・ヘッダ行のみ奇数で red・表外の奇数個で green** / **`legacy_structural` = 0** |
| 20 | 【DSL】**`cross-reference` の評価器**(契約種別・合成 corpus) | **正常系・異常系・別行移動変異が合成データで green/red** / **同期 `D` に変化なし(規則 4 exact を維持)** |
| 21 | 【DSL】**規則 6 の前提検証**(テストのみ)— `legacy_structural` 空・同期 `D` exact・構造 corpus 16 件が新評価器単独で green・期待 fixture への一致が **shadow を経由せず**成立 | **4 条件がテストとして固定** / 実装差分がテストのみ |
| 22 | 【DSL】**旧分岐(SP-19 の死コードを含む)と shadow 基盤の撤去** — 規則 6 を同時に検査 | **`_structural_reason` の ID 別分岐が 0 件**(機械検査)/ **規則 6 が成立** / **機械 17 件の検出集合が移行前と完全一致(SP-19 は forbidden で検出)** / ステップ 21 のテストが green |
| 23 | 【COV】**`COV` のプロファイル駆動化 + `kind` 別 destination 文法**(`節式 := segment (・ segment)*`、`segment := section_atom \| chapter〜chapter`、`section_atom := chapter \| section`)— ローダー経由・`--profile` / `--registry`・上書き・選択引数単独は既定に束縛。未解析は終了 2 | **同期プロファイルでの判定が変更前と同一**(212 件・38/84/90)/ **現行 212 件の destination が全件解析できる**(`2-1・4〜9`・`2-1・6・9`・`10-1・11-1。配信は…`・理由文を回帰例に)/ **未解析トークンの負例で fail** / selector 単独テスト(`:238-252`)が本文無変更で green |
| 24 | 【COV】**`attribution-destination`** — 展開した各節の実在・根拠文の存在(同期では `not_applicable`) | **実在しない節を指す帰属で red** / **根拠文の欠落で red** / **既存 `attribution` の結果が無変更** |
| 25 | 【資産】**`assets.schema.json` + 資産ローダー + JSON パス最小部分集合 + 正規化名前空間** — immutable / mutable exact-set(`baseline` を含む)を版で固定、`identity`、複数 collection、配列値 id、`refs` / `structures` / `fields`、`namespace`、collection の `structure`(配列パスは要素ごとに 1 タプル)(design 6-1 節) | **`contracts/authz/` の現行 3 ファイルに対して宣言例で ID が取り出せる**(`source_id` / `catalog_entry_id` / `table_id` / `policy_id` / `policy_ids[*]` / `role_ids[*]`)/ **現物 `ddl-elements.json` から `table → role_ids[*]` の代表構造タプルを導出し期待 exact-set と一致** / **`identity` 不一致・資産欠落・パス不正・未知キー・重複 JSON キーで終了 2** / 同期プロファイルの検出集合が完全一致 |
| 26 | 【資産】**`join`・`normalize`(単一 alias 表・名前空間内の単射性)・必須検査との連動** — 異名キーの `join`、`normalize`(名前空間別 `aliases` — 供給源はこれのみ)、**同一名前空間内の衝突・canonical の再 alias・循環は終了 2**、**`required_checks` に含む検査の資産・抽出器・集合宣言が無ければ終了 2** | **異名キーの join が成立** / **前置きの違う同一要素が一致** / **同一名前空間の衝突で終了 2・別名前空間の同名は衝突扱いしない・明示 alias なら通る・alias の競合/循環で終了 2** / **`required_checks` に新 ID を含むのに `assets` / `structure_extractors` / `collection_sets` が空で終了 2** |
| 27 | 【資産】**`structure_extractors` と `collection_sets` のスキーマとローダー + レジストリ `must_extract` / `must_derive_structures` / `must_collection_sets`**(design 1-2・6-3・6-4 節)— `source: manifest \| document \| derived`、表の識別と列 → タプル写像、`derived` の規則、`normalize` 適用、**抽出 0 件は終了 2**。`collection_sets` の `exact \| subset \| disjoint`。**`must_*` とプロファイル宣言の exact-set 照合(`forbidden` の全 kind を覆う抽出器が無ければ終了 2)** | **合成文書の遷移表・列役割表・マニフェストから 4 kind のタプルが導出される** / **表見出し不一致・列ずれ・別名未登録・抽出 0 件の負例で終了 2** / **`derived`(transitive-closure・inverse)の正常系** / **`collection_sets` の 3 関係それぞれの正常系** / **抽出器 1 本脱落・DDL 構造 collection 1 本脱落・必須集合宣言の脱落/差し替えで終了 2** / 同期の検出集合が完全一致 |
| 28 | 【資産】**サンプル一式** — `profiles/`(レジストリ〔**データモデル型 entry: `must_require` = 全 22・`must_extract` = `forbidden` の全 kind を覆う抽出器・`must_derive_structures`・`must_collection_sets` = `claims-relations-vs-manifest` + `direct-requirements-vs-claims`**〕・`profile.json`・`data-model-like.json`)、`doc/`(合成文書〔宣言表・帰属表・台帳・遷移表・列役割表〕・manifest・defects・invariants・requirements・req-universe)、`assets/`(合成資産 10 ファイル・`contracts/authz/` と同形・`requirement-claims.json` に `direct_requirement` 分類・`auth-ddl-map.json` は `structures` を持つ・`product-ddl-map.json` の domain = 全参照 ID) | **合成資産のトップレベル構造と ID 位置が現行 JSON と同形**(キー集合の比較テスト)/ **`data-model-like.json` がサンプル用レジストリでローダーを通る(`profiles/` の実ファイル完全一致・`must_*` の exact を含む)** / **B 集合のサンプルファイルが全部存在し過不足がない** / 実装差分が fixture とテストのみ |
| 29 | 【COV】**`attribution-direct`** — `direct_requirements`(独立資産・必須時は非空・母集合 ⊆・**`claims` の `direct_requirement` 分類と exact**)の ID が「対象外」なら red(同期では `not_applicable`) | **全件「対象外」の負例で red** / **`required_checks` に含むのに資産が無い・空・母集合外の ID で終了 2** / **直接要件 1 件脱落(資産と claims 分類の不一致)で red・資産と母集合を同時に縮めても claims 分類との exact で red** / **`not_applicable` のときだけ資産不要** / 既存結果無変更 |
| 30 | 【新検査】**`forbidden-structure`**(抽出器が導出した構造集合との照合・別名・方向 — design 6-2 節) | **別名で同じ構造を作った負例で red**(語句一致では通ることを対比で示す)/ **方向の違う同一辺を区別** / **抽出器 0 件で終了 2** / 合成データで正常系 / 同期では `not_applicable` を理由付きで出力 |
| 31 | 【新検査】**`cross-consistency`**(WAIT = manifest ∩ 本文 / AUTH = **二段階**: 段階 A raw DDL ID で map・refs・`structures` を DDL 導出構造と exact 照合 → 段階 B `product_ddl_map` を全参照 ID に適用して製品構造へ射影し manifest / FORB と比較 / 構造タプル全項目照合) | **3 条件それぞれに正常系と衝突負例** / **空 map・脱落・過剰・refs 空・`structures` 空・1 件脱落・participants 相違の負例** / **WAIT が本文に無い / AUTH がマニフェストに無い負例** / **禁止方向で red・逆方向で green(射影後の製品 ID で)** / **probe-only DDL で `product_ddl_map` 欠落・未写像・余分・曖昧写像なら終了 2** / 同期では `not_applicable` |
| 32 | 【新検査】**`collection-consistency`**(`collection_sets` の `exact` / `subset` / `disjoint`・差集合を reason に) | **claims の relation 行と manifest の脱落・過剰で red** / **`forbidden` 混入(`disjoint`)で red** / **`subset` の正常系と違反** / 同期では `not_applicable` |
| 33 | 【新検査】**`baseline-digest`**(自前 canonical・envelope・版固定の immutable exact-set) | **immutable 各フィールド(`baseline` 反転を含む)1 件ずつの改変で red・mutable 各フィールドの改変で green** / **キー順・空白を変えても digest 一致** / **重複キーで終了 2** / **`immutable_fields` をプロファイルから変えられない** |
| 34 | 【新検査】**`unique-owner`**(global check・`invariants/<name>.json` の `global_invariants` 宣言からの写像・`expected_ids` 独立資産必須・`owner_steps_allowed` 必須) | **重複・欠落・過剰・許可外 step の負例** / **`expected_ids` 省略・空で終了 2** / **`global_invariants` の `unique-owner` 宣言・`required_checks`・`baseline_digest` の 3 者が揃わないと終了 2** / 同期では `not_applicable` |
| 35 | 【新検査】**`reference-class`**(順序付き規則・first-match・未一致 2・`normative` は approved 限定) | **feature・worklog・legacy を `normative` として参照する負例で red** / **同一節内の 2 リンクを `fragment` で別 role にできる** / **未一致の参照で終了 2** / **既存 `noncanonical-reference` の結果が無変更** |
| 36 | 【ランナー】**`scripts/check_doc_profiles.py` + サンプル 2 本で全検査を実行** — design 13 節の契約(`--profile` 必須・`--registry`・終了 0/1/2・全終了コードで JSON envelope・`checks` は常に 22 件・`not_run`・`partial` は `--checks` 時のみ) | **終了 0/1/2 の各経路で JSON がスキーマに適合** / **`errors` が終了 2 でのみ非空** / **`--checks` で未選択 ID が `not_run`・`partial: true`、無しで `false`** / **`data-model-like.json` で新 8 ID すべてが `pass` または `fail`(`not_applicable` 0)** / **同期側パスを一度も開かない**(open をモックで固定)/ **staging レジストリを `--registry` で使える** / 実装差分がスクリプトと `tests/test_check_doc_profiles.py` のみ |
| 37 | 【配線】**レジストリ列挙** — 両スクリプトが選択・上書き引数なしのとき `--registry`(既定 = 本番)を読み、登録集合 = 実ファイル集合を検証して全文書を検査。**`ci.yml` は無変更**。`test_ci_wiring.py` にはスクリプト側テストのみ追加 | **`ci.yml` 無変更** / **`test_ci_wiring.py` の既存アサーション(step 1 件・禁止セレクタ・harness exact)が無変更で通る** / **レジストリに 1 件足すと検査対象が増える** / **未登録ファイル・脱落・重複 name/document・0 件で終了 2** |
| 38 | 【記録】**検証記録・A/B/C の exact-set・統合表・申し送り** — 全ステップの検証結果を worklog へ整理。A/B/C(C の条件付き要素はステップ 1 の確定値)を実 diff から確定。**各負例 fixture → 期待 check ID で fail する統合表**。新規 node ID 一覧。design 11 節の申し送り 23 項目 | **基準線 green(passed ≥ 875・既存 875 node ID 包含・digest 一致・skipped/xfailed/xpassed/deselected = 0 / 3 検査 / ruff / ty)** / **機械 17 件の検出集合が着手前と完全一致** / **A = `git diff --name-status origin/develop` の全件、A = B ∪ C ∪ 文書、B ∩ C = ∅** / **統合表の全行が実行で確認済み** / **申し送り 23 項目が worklog にある** |

## 5. DoD(受け入れ基準)

Notion タスク TSK-269 の DoD(受け渡し契約を含む)と同期させている(承認時に Notion 側へ本節を転記する)。

- [ ] **プロファイル・レジストリ(`--registry` で staging 指定可)・共通ローダー**。スキーマ版を持つ。全 22 check ID の完全分割と `must_require`(レジストリ entry)・理由非空を強制
- [ ] **不変条件 DSL(13 種・旧分岐の述語に一対一 + 契約 5 種別名の受理)**。構造分岐 15 ID を宣言へ移行し `_structural_reason` の ID 別分岐 0 件・`legacy_structural` 空・同期 `D = 15 ∪ {MT-01}`(exact)・
      機械 17 件の検出集合が移行前と完全一致・構造 corpus 16 件と期待構造化 reason fixture で移行の各段が一致・design 2-1 節の変異集合が全 ID で red
- [ ] **MT-01 の oracle 改訂**(差分は MT-01 エントリの範囲・検出集合不変)と **`absent-section` の必須宣言**(有効化フラグなし)
- [ ] **CLI 名を固定** — `--document` / `--profile` / `--manifest` / `--defects-file` / `--checks` / `--defects`(+ `--registry`)。上書き・選択引数単独は既定プロファイルに束縛
- [ ] **fail-closed**: 未対応 kind・必須引数欠落・未知 ID・余分な宣言・プロファイル欠落・解決できない節・脱落トークン・レジストリ不一致・完全分割違反・必須検査の資産/抽出器/集合宣言の欠落・抽出 0 件・正規化衝突・重複 JSON キー・未解析の帰属先・未分類の参照は終了コード 2
- [ ] **4 検査を機械で保証**(`forbidden-structure` / `attribution-direct` / `baseline-digest` / `cross-consistency`)+ `collection-consistency` + `unique-owner`。
      入力は `assets`(現物の項目名・`auth_ddl_map` の `structures`・`product_ddl_map` の二段階射影・独立資産)・`structure_extractors`・`collection_sets` の宣言で、**checker に文書固有の構造をハードコードしない**。
      **必須の宣言集合はレジストリ entry の `must_*` で固定**(自己申告で落とせない)。WAIT は manifest ∩ 本文、AUTH は manifest、AUTH/WAIT–FORB は方向込みで照合。`direct_requirements` は claims の `direct_requirement` 分類と exact
- [ ] **コンフォーマンスランナー**(契約: synopsis・`--registry`・終了コード・全終了コードで JSON envelope・`not_run`)と**サンプル一式**(データモデル型最小プロファイルで全 22 ID が同期側パスを開かずに動く)
- [ ] **参照の分類** `reference-class` / **帰属検査の強化**(混合式を含む destination 文法で現行 212 件が全件解析)。既存結果は無変更
- [ ] **`codex_run.py` の `has_filled_step_row`** が入れ子見出し・fenced code・否定形を扱い、3 種の報告を区別する
- [ ] **既存の振る舞いが変わらない** — 3 検査 green / ruff・ty クリーン / 既存 node ID 875 件の包含(digest 一致)/ passed ≥ 875 / skipped・xfailed・xpassed・deselected = 0 /
      fixture・`fixture-sha256.txt`・`req-universe.json` 無変更 / 同期で走る検査は既存 14 のまま
- [ ] **CI は引数なしのまま**(`ci.yml` 無変更)で、本番レジストリに登録された全プロファイルを検査する
- [ ] **A/B/C の exact-set・負例 → check ID の統合表・申し送り 23 項目**が worklog と PR 本文にある
- [ ] **正本・`core-areas.json`・台帳は変更していない**(3 節の「反映なし」宣言と PR 差分が一致)

## 6. テスト計画

| 種別 | 足すもの | 置き場 |
| --- | --- | --- |
| **単体**(a) | `has_filled_step_row`: 入れ子見出し / 同レベル脱出 / 別見出し配下の表 / fenced code / 否定形 / 3 メッセージ | `tests/test_codex_run.py`(新設)+ `tests/test_hooks.py`(既存維持) |
| **単体**(a) | **構造 corpus 15 + MT-01**(禁止語なし・scope 全節実在・終了 1/0・同値変異)/ **forbidden corpus** / **期待構造化 reason fixture への一致** / **三者一致** / **汎用規則 1〜6 と同期コンフォーマンス** | `tests/test_check_design_propagation.py`・`tests/fixtures/structural-reasons-expected.json` |
| **単体**(a) | **宣言評価器 13 種 + alias** の正常系・異常系・同値変異(`exact-set` は別 relation 負例、`well-formedness` は奇数行 2 行 / 表外奇数)。`cross-reference`・`absent-section` は合成データで | 同上 |
| **単体**(a) | **ローダー**: 必須欠落 / 版不一致 / 未知フィールド / 完全分割違反 / `must_require` 違反 / 空理由 / 未知 ID / レジストリ不一致 / 0 件 / `--registry` 切替 / staging の木 / 名前空間 40 ID / パス解決 | `tests/test_doc_check_profile.py`(新設) |
| **単体**(a) | **fail-closed の負例**: 未解決の節 / 脱落トークン / 未対応 kind・必須引数欠落 / 未知 ID / 余分な宣言 / 必須検査の資産・抽出器・集合宣言の欠落 / 抽出 0 件 / `identity` 不一致 / 名前空間内の正規化衝突 / 重複 JSON キー / 未解析 destination / 未分類参照 | 同上・`tests/test_check_doc_coverage.py`・`tests/test_ci_wiring.py`(スクリプト側) |
| **単体**(a) | **`assets` 契約**(現物 3 ファイルからの ID 抽出・配列値 id・`join` 異名キー・`normalize`・名前空間・`structure`)/ **抽出器 4 kind と `derived`** / **`collection_sets` 3 関係** / **合成資産の同形性** | 同上 |
| **単体**(a) | **帰属**: destination の 3 kind(理由文・節式 + 説明文・列挙・範囲・章単独・混合式)/ 212 件全件解析 / 節の実在 / 根拠文 / 直接要件の「対象外」 | `tests/test_check_doc_coverage.py` |
| **単体**(a) | **`forbidden-structure`**(別名・方向・抽出 0 件)・**`cross-consistency`**(3 条件・map/`structures` の空/脱落/過剰・本文/manifest 不在・禁止方向 red / 逆方向 green・`product_ddl_map`)・**`collection-consistency`**・**`baseline-digest`**・**`unique-owner`** | `tests/test_check_design_propagation.py` |
| **単体**(a) | **`reference-class`**: 負例 3 種 / `fragment` / 未一致 2 / 既存 `noncanonical-reference` 無変更 | 同上 |
| **単体**(a) | **ランナー契約**: `--profile` 必須 / `--registry` / 終了 0・1・2 の envelope / `not_run`・`partial` / サンプル 2 本で全 22 ID / 同期側パスを開かない | `tests/test_check_doc_profiles.py`(新設) |
| **退行**(a) | 安全網 2 本・selector 単独テスト(本文無変更)/ 既存 node ID 875 件の包含と digest / skipped・xfailed・xpassed・deselected = 0 / `test_ci_wiring.py` 既存アサーション・`ci.yml` 無変更 | `tests/`(既存)+ ステップ合格条件 |
| **統合**(a) | **負例 fixture → 期待 check ID で fail する統合表**(ステップ 38) | worklog(記録)+ 実行 |
| **一致性**(c)・**越境**(b)・**E2E**・**故障系**(d) | **本タスクでは足さない**(ハーネスの機構) | — |

**変異テストの方針**(research 4-1 節・台帳 H-79): 変異集合の**唯一の正は design 2-1 節の表**(共通・行スコープ・節スコープ・`exact-set`・`well-formedness`)。ステップ 2・DoD・本節はそれを参照し、個別に思いついた変異に頼らない。
