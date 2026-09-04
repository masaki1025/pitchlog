---
feature: doc-check-multi-doc
type: design
date: 2026-09-04
---

# 詳細設計: 文書検査機構の多文書対応(プロファイル化 + 不変条件 DSL)

[plan.md](plan.md) 4 節から参照される詳細設計。事実の典拠は [research.md](research.md)(1〜5 節 = 2026-08-31、6 節 = 2026-09-04 再検証)にあり、
本書は**設計判断とその根拠**だけを書く(設計書 7.1-1)。略記は research.md と同じ(`PROP` / `COV` / `TSK250PLAN` 等)。
計画レビューの指摘 ID(`R1-*`〜`R8-*`)は worklog 2026-09-04 の一次記録表が正。

## 0. 前提となる裁定

| 日付 | 論点 | 裁定 | 本書 |
| --- | --- | --- | --- |
| 2026-08-31 | 不変条件の機械判定の範囲 | **既存の構造分岐を宣言へ移行**(型は動いているコードから抽出) | 2 節 |
| 2026-08-31 | CI 配線 | **プロファイル列挙**(引数を増やさない) | 9 節 |
| 2026-08-31 | 重さ分類 | **コア領域** | plan 4 節 |
| 2026-09-04 | MT-01(R1-P0-1・R2-P0-3・R3-P0-5・R4-P0-1) | **(a′) oracle の正当な改訂 + `absent-section` 型**。MT-01 の宣言は `required_declarations` で必須(有効化フラグは設けない) | 4 節 |
| 2026-09-04 | `has_filled_step_row` | **本タスクに含める** | 10 節 |
| 2026-09-04 | `check_authz_catalog.py` | **対象外・前例として資産書式を借りる** | 12 節 |
| 2026-09-04 | `guard_paths` 登録・台帳 H-78/H-79 追記 | **すべて TSK-250 に委ねる**(統制の空白は受容 — 14-2 節) | 11 節 |
| 2026-09-04 | 計画レビューの進め方 | R3 全件反映 → 4 周目以降も通常の敵対レビュー | — |
| **2026-09-04(R8 否決後・PO)** | **射程の縮小 (b)** | **本タスク = 契約 1〜4 + 既存 15 分岐の DSL 移行 + 検査の機構(枠)+ サンプル。契約 5 の実入力契約(データモデル正本の資産形状・必須抽出器・直接要件の分類・pins の実値)は TSK-250 の再レビューで確定**。TSK-250 契約 5 の文言変更を伴う | 6 節・11 節 24 |

**射程縮小の含意**(裁定 (b)): 6 節の 4 検査 + `collection-consistency` + `unique-owner` は**機構(評価器・抽出器・集合一致・資産ローダー・pins)として実装し、サンプルプロファイル(合成)で全 22 ID が動くことまで**を本タスクが保証する。
**実在するデータモデル正本に対してどの宣言・資産・pins が必須か**は本タスクでは決めない(二文書目が存在しないため決められない — 5〜8 周目の P0 が再生産された原因)。
6-1〜6-4 の「TSK-250 が作る」と書いた資産・宣言は**形式の例**であり、実契約は TSK-250 側で固定する。

**「新規機構を発明しない」(`docs/features/sync-protocol-canonical/plan.md:294`)との関係**: 本タスクが作る型体系・スキーマ・評価器・レジストリ・ランナー・抽出器は
**いずれも新規機構である**。「発明していない」とは主張しない(R1-P1-1)。2026-08-31 の裁定は**前決定に対する明示的な例外・上書き**として記録する。
例外を許す理由は、TSK-250 の受け渡し契約(`TSK250PLAN:65-68`)が機械保証を契約として要求し、かつ **TSK-250 は checker を変更しない**(`:217`)ため、
二文書目で必要な判定は**すべてプロファイルで宣言できる**形で本タスクが提供しなければならないこと。前決定の趣旨(台帳 H-78)は、機構を確定ゲートの外で作り oracle を触らずに作ることで守る(例外は 4 節の MT-01 のみ)。

## 1. プロファイル(文書固有の宣言の束)

### 1-1. 置き場・レジストリ・列挙・staging

| 資産 | パス | 役割 |
| --- | --- | --- |
| **レジストリ** | `scripts/design_relations/profiles/registry.json` | `schema_version` / `profiles: [{name, file, document, must_require, pins}]`。**`must_require`(必須 check ID)と `pins`(ゲート宣言の canonical digest)はレジストリ entry のフィールド**(プロファイル側には置かない)。一般規則: **必須検査を有効にする宣言はプロファイルの自己申告だけで成立させない — ゲート宣言の変更はレジストリの差分(レビュー対象)を伴う**(R7/R8 の P0 型を欄ごとではなく digest で閉じる。前例: `fixture-sha256.txt` — research 4-1 節) |
| プロファイル | `scripts/design_relations/profiles/<name>.json` | 文書 1 本につき 1 ファイル。**このディレクトリにはレジストリとプロファイル以外を置かない** |
| スキーマ | `scripts/design_relations/schemas/{profile,registry,invariant,assets}.schema.json` | `schema_version` を持つ |
| 宣言資産 | `scripts/design_relations/invariants/<name>.json` | 欠陥 ID → 構造宣言(2-2 節) |
| 共通ローダー | `scripts/doc_check_profile.py`(新設) | スキーマ検証(自前の最小検証器)・レジストリ照合・パス解決・`assets` ローダー・構造抽出器 |
| サンプル | `tests/fixtures/profile-sample/profiles/`(レジストリ + プロファイル 2 本)/ `doc/` / `assets/` | 実プロファイル非依存の契約テスト入力 |

**列挙の規則**(選択・上書き引数が一切無いとき): 使用するレジストリの `profiles[].file` の集合と、**同じディレクトリ**の `*.json`(レジストリ自身を除く)の実ファイル集合が
**完全一致**しなければ終了コード 2。`name` / `document` / 機械欠陥の名前空間は一意。0 件は終了コード 2。**`--registry <path>`**(両検査・ランナー共通・既定 = 本番)で
別のレジストリ(staging)を指定できる。**パス解決**: プロファイル内の相対パスとレジストリの `file` はリポジトリルート(`--root`)基準。

**staging の木(TSK-250 向け・固定 — R6-P1-1)**:
```
<staging>/profiles/registry.json        ← must_require = 全 22 の entry を持つ
<staging>/profiles/data-model.json      ← プロファイル(この 2 ファイル以外を profiles/ に置かない)
<staging>/doc/  (document.md〔骨格〕, manifest.json, defects.json, invariants.json, requirements 参照, universe 参照)
<staging>/assets/ (claims, auth-catalog, ddl-elements, auth-ddl-map, product-ddl-map, waiting, forbidden, direct-requirements, expected-ids, baseline-digest)
```
**作成順**: ① TSK-250 の文書骨格(現ステップ 1)が存在した**直後**に、上記の木を**全必須資産の構造的に妥当な骨格つきで原子的に**作る。この時点で
`check_doc_profiles.py --registry <staging>/profiles/registry.json --profile <staging>/profiles/data-model.json --json` は**終了 2 にならず**、終了 1(不適合・`partial: false`)の診断を返す
② 文書と資産を是正し、是正後に同コマンドが終了 0 ③ 本番パスへの移設と本番 `registry.json` への登録を**同一コミット**で行う。

### 1-2. フィールド

| 群 | フィールド | 値(同期プロファイル) | 由来 |
| --- | --- | --- | --- |
| 識別 | `schema_version` / `name` / `document` | `1` / `sync-protocol` / `docs/design/sync-protocol.md` | `PROP:36` |
| 資産 | `manifest` / `defects` / `invariants` / `requirements` / `universe` | 現行の既定値 | `PROP:37-38`・`COV:14-18` |
| 文法 | `section_id_grammar` / `preamble` / `link_base_dir` / `noncanonical_scan_start` | `\d+(-\d+(-[A-Z])?)?` / `first-h2` / `docs/design` / `^##\s+2` | `PROP:337`・`:334`・`:1089`・`:1066` |
| 宣言表 | `declaration_table`: `{section, row_prefix, column_count, columns}` | `2-5` / `| **R-` / `6` / 列名 | `PROP:643-682` |
| 語彙 | `exclusion_vocabulary` / `citation_inheritance` | `["対象外","対象にならない","含めない"]` / 現行値 | `PROP:421-424` |
| 帰属 | `attribution`: `{section_re, ledger_section, kinds, destination_grammar}` | `^11-3\.` / `11-5` / 3 区分 / 8 節 | `COV:429`・`:44`・`:30` |
| 名前空間 | `defect_id_namespaces`: `{all, machine}` | `all: ["SP","MT","CI","LG"]` / `machine: ["SP","MT"]` | R2-P0-9 |
| 種別 | `invariant_kinds` | 2-1 節の 13 種 + 契約 alias の部分集合 | 契約 2 |
| 検査 | **`required_checks`** / **`not_applicable`**: `{check_id: 理由}` | 同期: 既存 14 / 新 8(理由 = trim 後非空) | R3-P0-1 |
| 検査入力 | `assets` | 6-1 節。同期 = 空 | — |
| **構造抽出** | **`structure_extractors`**(6-3 節) | 同期 = 無し(`forbidden-structure` / `cross-consistency` は `not_applicable`) | R6-P0-2 |
| **集合一致** | **`collection_sets`**(6-4 節) | 同期 = 無し | R6-P0-5 |
| 帰属 | `direct_requirements` | 資産パス(`attribution-direct` 必須時は必須・非空)。同期 = 無し | R4-P0-6 |
| 参照 | `reference_policy` | 7 節 | — |

**完全分割**: `required_checks ∪ not_applicable` = 5-1 節の全 22 ID、積は空、`required_checks ⊇ registry.must_require`。未知 ID・空理由は終了 2。
`--checks` は部分診断(`partial: true`)。

**レジストリ entry による固定(`must_require` + `pins` — R7-P0-1/3/4・R8-P0-1〜3・R8-P2-1)**:
- `must_require`: 必須 check ID の集合。`required_checks ⊇ must_require` でなければ終了 2
- **`pins`**: ゲート宣言の **canonical digest**(6-2 節 `baseline-digest` と同じ canonical 形・SHA-256)。対象と算出は次で固定する:
  - `profile_gating_digest`: プロファイルの **ゲート節**(`required_checks` / `not_applicable` / `invariant_kinds` / `structure_extractors` / `collection_sets` / `assets`(各 asset の `identity`・`collections`・`structure`・`join`・`normalize`)/ `direct_requirements` / `reference_policy`)を canonical 化した digest
  - `invariants_digest`: `invariants/<name>.json` 全体の digest(宣言本体・`structural_required`・`required_declarations`・`global_invariants` を含む)
  - `asset_digests`: `{asset 名: digest}` — **入力側の oracle になる資産**(`forbidden` / `direct_requirements` / `expected_ids` / `auth_ddl_map` / `product_ddl_map` 等)のファイル digest
  いずれか不一致なら終了 2。**プロファイル・宣言資産・oracle 資産を変えるには必ずレジストリの pins を更新する = レビューで見える差分になる**。
  「何を pin するか(`asset_digests` のキー集合)」は entry ごとに宣言し、**必須検査に対応する資産の pin 欠落は終了 2**(`required_checks` に `attribution-direct` があるなら `asset_digests.direct_requirements` が必須、等の対応表は 6-2 節)
- 同期 entry: `must_require` = 既存 14、`pins` = 実値(同期プロファイル・`invariants/sync-protocol.json`・`defects.json`)。サンプル entry: 実値。
  **データモデル用 entry の実値と pin 対象は TSK-250 が確定**(裁定 (b) — 11 節 21・24)

**fail-closed**: 必須欠落・版不一致・未知フィールド・`invariant_kinds` 外の宣言・完全分割違反・`must_require` 違反・**pins 不一致・必須 pin の欠落**・必須検査の資産 / 抽出器 / 集合宣言の欠落・レジストリ不一致 — 終了コード 2。

## 2. 不変条件 DSL

### 2-1. 種別(13 種 + 契約 alias)— 旧分岐の述語に一対一

◎ `PROP:432-593` の全分岐と補助述語(`_table_row` / `_identified_row` / `_element_has_row` / `_element_occurs` / `_route_row_matches :389` / `_numbered_ids` / `_has_exclusion` / `check_emphasis :405`)を確認。

| # | kind | 引数 | 適合条件 | 由来 |
| --- | --- | --- | --- | --- |
| 1 | `forbidden-element` | `literals` / 任意 `sections` | literal が対象範囲に無い(`defects.json` の `forbidden` は自動でこの kind) | 全欠陥・**SP-19(forbidden-only)** |
| 2 | `row-selector` | `id`・`section`・`mode: needle|identifier`・`keys` | 該当行が**存在**。他宣言が `row: <id>` で参照 | SP-01・02・07・09・10・11・12・20 |
| 3 | `row-contains` | `row`・`literals` または `elements: {relation, field}` | 選択行に全 literal / 全要素 | SP-01・02・20 |
| 4 | `section-contains`(**alias `required-element`** = `as: text`) | `sections`・`literals` または `elements`・`as: text|identifier|identified-row|row`・任意 `key: id-part` | 各節に各 literal / 要素が as のモードで存在。**`identifier` は旧 `_element_occurs`(`PROP:895-924`)と同値の 3 分岐**(`=` を持つ要素は表行単位で ID・左辺・右辺を照合 / `ID:句1+句2` は同一行に ID と全意味句 / それ以外は節内の ID・語の出現) | SP-02・03・08・13・14 |
| 5 | `exact-set` | `sections` または `row`・**`relation`(必須 — 期待集合を取る manifest relation)**・任意 `field`・`routes`(`[P1..]` / `containing: T6`)・`prefix` | 各節(または行)の経路行の番号付き ID 集合が、指定 relation から導いた期待集合と完全一致 | SP-06・07・08・09(旧述語は `R-TXN-ROUTE` 固定 — `PROP:389`) |
| 6 | `cross-reference`(契約種別・合成 corpus) | `from: {row}`・`to: {row}`・`extract: regex` | 2 行から抽出した値が一致 | TSK-250 契約 |
| 7 | `element-lookup` | `relation`・`prefix`・`section`・`row_identifier` | 接頭辞で見つけた要素の意味部が識別行に含まれる | SP-08 |
| 8 | `row-scoped-forbidden` | `row`・`literals` | 選択行に literal が無い | SP-09 |
| 9 | `any-of` | `row`・`literals` | 選択行に literal のいずれか | SP-09 |
| 10 | `required-exclusion` | `row` または `sections`・**`terms: [1..2 個]`**(語彙はプロファイル) | `_has_exclusion(範囲, *terms)` が真 | SP-12・16 |
| 11 | `conditional-forbidden` | `row`・`literal`・`unless: [literals]` | literal 禁止、`unless` が全部あれば許容 | SP-20 |
| 12 | `well-formedness` | `scope`・`rule: balanced-emphasis-per-table-row` | **`\|` で始まる全 Markdown 表行(ヘッダ・区切り行を含む)**のそれぞれについて `**` が偶数個(表外は数えない — `check_emphasis :405-418` と同値。R7-P1-1) | SP-18 |
| 13 | `absent-section` | `section` | 節 ID の見出しが**存在しない** | MT-01 |
| alias | **`unique-owner`**(契約種別名) | `invariants/<name>.json` の **`global_invariants`** 領域に置く(欠陥 ID を持たない — 2-2 節)。引数は 6-2 節 | global check `unique-owner` へ写す。**`required_checks` に `unique-owner` があるなら `global_invariants` の宣言と `baseline_digest` 資産が同時に必須**(R7-P2-2) | TSK-250 契約(R6-P1-2) |

契約の 5 種別名との対応: `required-element` → alias(4)/ `forbidden-element` = 1 / `exact-set` = 5 / `cross-reference` = 6 / `unique-owner` → alias(global check)。
**5 種別名はすべて `invariant_kinds` に書け、スキーマが受理する**(契約違反にならない — 11 節 17)。

**評価順**: 1 欠陥内の宣言は配列順・first-failure。`defects.json` の `forbidden` は宣言より先(`PROP:619-622`)。`row-selector` の失敗は当該欠陥の違反。

**旧分岐 → 宣言の完全対応**(◎):

| 欠陥 | 宣言列 |
| --- | --- |
| SP-01 | `row-selector`(7-2 needle 未送信・退避済み)→ `row-contains`(A5・退避)→ `row-selector`(6-3 identifier B4)→ `row-contains`(A5・退避) |
| SP-02 | `row-selector`(7-1 identifier A5)→ `row-contains`(elements R-ACK-STATE.source)→ `section-contains`([6-3, 7-2]・同 elements・as row) |
| SP-03 | `section-contains`([6-3, 7-2, 9-5]・elements R-QUEUE-LIFE・as identifier) |
| SP-06 | `exact-set`(sections [8-1, 10-2, 11-2]・**relation R-TXN-ROUTE**・routes P1〜P3) |
| SP-07 | `exact-set`(sections [8-1]・relation R-TXN-ROUTE・P4)→ `row-selector`(9-2 needle 旧世代・退避・B4・原子)→ `row-selector`(10-2 needle 退避・B4・原子)→ `row-selector`(11-2 needle P4・退避・B4) |
| SP-08 | `element-lookup`(R-TXN-ROUTE・`T6:`・8-1・T6)→ `section-contains`(4-4・一時 ID・写像・text)→ `section-contains`(7-1・D5・確定結果・text)→ `exact-set`(sections [8-1]・relation R-TXN-ROUTE・containing T6) |
| SP-09 | `row-selector`(8-1 identifier P3)→ `exact-set`(row・relation R-TXN-ROUTE・T・P3)→ `row-scoped-forbidden`(T5)→ `any-of`(T7・V11) |
| SP-10 | `row-selector`(8-1 identifier P3)→ `row-selector`(7-1 needle P3・応答) |
| SP-11 | `row-selector`(6-2 needle 期待版不一致)→ 同(6-3)→ 同(8-3) |
| SP-12 | `row-selector`(6-3 identifier B3)→ `required-exclusion`(row・terms [D1 を持たない変更イベント, D5])→ `row-selector`(6-4 needle 同・D5)→ `required-exclusion`(row・**terms [D5]**) |
| SP-13 | `section-contains`(4-3・elements R-EVENT-FIELD・as identified-row・key id-part)→ `section-contains`([4-3-A, 11-2]・同・as identifier) |
| SP-14 | `section-contains`(4-3-A・W3-a・W3-b・変更版順・text)→ `section-contains`([5-5, 11-2]・変更版順・D1・D2・論理再生順・text) |
| SP-16 | `required-exclusion`(sections [6-1, 6-2]・terms [D1 を持たない変更イベント, prefix]) |
| SP-18 | `well-formedness`(4-3-A・balanced-emphasis-per-table-row) |
| SP-20 | `row-selector`(2-1 needle `\| D1 \|`)→ `row-contains`(順序と欠落・undo の逆順)→ `row-selector`(4-2 needle D1・順序・欠落)→ `row-selector`(4-2 needle D5・再送・二重適用)→ `conditional-forbidden`(row 2-1・再送の重複排除・unless D5 の用途・D1 の用途ではない) |
| **SP-19** | **宣言なし(forbidden-only)** — 構造分岐の判定文字列が `forbidden` と同一で到達不能(◎ `defects.json:258-276`・`PROP:570-572`)。撤去ステップで死コードを削除。oracle 無変更 |
| MT-01 | `absent-section`(`"1"`) |

**変異集合(唯一の正 — plan ステップ 2・DoD・6 節はここを参照する。R7-P2-4)**:

| 適用範囲 | 変異(exact-set) |
| --- | --- |
| (全 kind 共通の変異は**置かない** — 意味反転・主述交換は現行の needle 判定と同値でなく、旧述語では検出できない。R8-P1-1 で撤回) | — |
| 行スコープ kind(`row-contains` / `row-scoped-forbidden` / `any-of` / `conditional-forbidden` / `required-exclusion(row)` / `element-lookup` / `cross-reference`) | 別行移動 |
| 節スコープ kind(`section-contains` / `required-exclusion(sections)` / `exact-set`) | 別節移動 / 意味部欠落 / ID 交換 |
| `exact-set` | 別 relation を同一 manifest に置き、指定 relation だけが使われる |
| `well-formedness` | 奇数行が 2 行(合計偶数)で red / **ヘッダ行のみ奇数で red** / 表外に奇数個で green |

旧述語と同値でない変異は使わない。

### 2-2. 結合規則(汎用・常時強制)

`invariants/<name>.json` = `{schema_version, structural_required, legacy_structural, required_declarations, declarations, global_invariants}`。
`declarations` は欠陥単位(`defect_id` を持つ)、**`global_invariants` は欠陥 ID を持たない台帳全体の宣言**(`unique-owner` のみ — 規則 1〜6 の D には含めない)。
M = 機械欠陥 ID、D = `declarations` の欠陥 ID、F = `forbidden` を持つ ID:

1. `structural_required ⊆ M`、`required_declarations ⊆ M`、両者は互いに素
2. 宣言必須集合 = (structural_required − legacy_structural) ∪ required_declarations ⊆ D
3. `legacy_structural ⊆ structural_required`、`legacy_structural ∩ D = ∅`、legacy の各 ID に旧分岐が存在
4. `D ⊆ M` かつ `D ⊆ structural_required ∪ required_declarations`(余分な宣言を拒否)
5. `M − structural_required − required_declarations ⊆ F`(forbidden-only)
6. 移行完了時 `legacy_structural = ∅` かつ旧評価器の ID 別分岐 0 件(撤去と同時に検査)

**同期専用のコンフォーマンステスト**: `structural_required` = 15(`SP-01 02 03 06 07 08 09 10 11 12 13 14 16 18 20`)、`required_declarations` = `[MT-01]`、移行完了時 `D` = その和(exact)。
`required_declarations` は骨格作成時 `[]`、`absent-section` 導入ステップで `[MT-01]` へ宣言と同時に更新。

### 2-3. 移行の正しさの証明

1. 構造 corpus 15 件(旧分岐 15 ID): 異常例は forbidden literal を含まない / 各 ID の scope の全節見出しを実在させる / 異常例は終了 1・入力不正 0。SP-19・MT-01 の literal 対は forbidden corpus。MT-01 は `absent-section` 導入時に 16 件目
2. 期待構造化 reason fixture(`tests/fixtures/structural-reasons-expected.json`): キー `(case_id, defect_id)`・`input_kind`・`expected_exit`・`reason: {violated, kind, section, expected, actual, token}`(first-failure)
3. shadow 実行: 期待 fixture・旧分岐・新評価器の三者一致。kind 単位の移行ステップは「該当 ID の三者一致」+「新評価器単独で corpus 判定」
4. 撤去の順序: 全 kind の移行 → 前提検証 → 旧分岐と shadow 基盤の削除(規則 6 を同時に検査)

## 3. fail-closed

| 経路 | 現行 | 変更後 |
| --- | --- | --- |
| `extract_scope` の文法不一致トークン | 黙って捨てる(`PROP:337-339`) | 終了コード 2 |
| scope / 宣言の `section(s)` が文書に無い | `""`(`PROP:309-310`) | 終了コード 2。**`absent-section` の `section` は除外** |
| 未対応 kind / 必須引数欠落 / 未知の欠陥 ID / プロファイル欠落 / レジストリ不一致 / 完全分割違反 / 必須検査の資産・抽出器・集合宣言の欠落 / 正規化衝突 / 重複 JSON キー / 抽出器が 1 件も構造を得られない | — | 終了コード 2 |
| 帰属先 destination の未解析トークン / `reference_policy` に一致しない参照 | — | 終了コード 2 |

## 4. MT-01 の oracle 改訂 + `absent-section`(裁定 (a′))

事実は research 6-3 節(◎)。① oracle 改訂(plan ステップ 3)— MT-01 エントリ内で `scope` から `1節` を除き `location` / `positive` / `mapping` を「12 アンカー + 節 1 の不在」へ。差分は MT-01 エントリの範囲。
forbidden corpus の MT-01 対の禁止語を `### 2-2.` へ ② `absent-section` 型 + MT-01 宣言 + `required_declarations = [MT-01]`(plan ステップ 9・原子的)③ ステップ 3〜9 の間は同一 PR 内(14-2 節)。

## 5. CLI(契約 1)

| 引数 | 意味 |
| --- | --- |
| 選択・上書き引数が一切無い | レジストリ列挙(`--registry` 既定 = 本番) |
| `--registry <path>` / `--profile <path>` | 使用するレジストリ / 単一プロファイル |
| `--document` / `--manifest` / `--defects-file` / `--requirements` / `--universe` | `--profile` なしなら既定(同期)プロファイルに束縛して上書き |
| `--checks` / `--defects` | `--profile` なしなら既定プロファイルに束縛。部分診断 |

### 5-1. check ID の全体表 — **22 ID**(R6-P0-5)

| 検査機構 | 既存 14 | 新 8(同期では `not_applicable`) |
| --- | --- | --- |
| `PROP` | 12(`PROP:13-27`) | `forbidden-structure` / `cross-consistency` / **`collection-consistency`** / `baseline-digest` / `unique-owner` / `reference-class` |
| `COV` | 2(`attribution` `ledger`) | `attribution-destination` / `attribution-direct` |

## 6. TSK-250 が要求する 4 検査 — **機構(枠)+ サンプルまで**(裁定 (b))

本節の検査・資産・抽出器・集合宣言は、**汎用の機構として実装し、サンプルプロファイル(合成)で動くことを本タスクが保証する**。
「実在するデータモデル正本に対して、どの資産をどの形で置き、どの抽出器・集合宣言を必須にし、何を pin するか」は **TSK-250 の再レビューで確定する**(本節の「TSK-250 が作る」は形式の例)。
構造タプルの端点はすべて **`{namespace, id}`**(R8-P0-4 — 抽出器 map・DDL structure・FORB・`auth_ddl_map`・`product_ddl_map` の全経路で名前空間を保存し、名前空間別 alias 表を一意に適用できる)。

### 6-1. `assets`(現物の項目名が正)

| asset | 現物(◎) | 宣言例 |
| --- | --- | --- |
| `claims` | `requirement-claims.json`: `asset_kind` 無し、`claims[*].source_id`・`classification` | `{path, identity: {schema_version: 1, required_top_keys: ["input_manifest","claims"]}, collections: [{items: "$.claims[*]", id: "source_id", namespace: "claim", fields: {classification: "classification"}}]}` |
| `auth_catalog` | `auth-catalog.json`: `entries[*].catalog_entry_id` / `requirement_claim_id` | `{…, collections: [{items: "$.entries[*]", id: "catalog_entry_id", namespace: "auth"}], join: {from_key: "requirement_claim_id", to: "claims", to_key: "source_id"}}` |
| `ddl_elements` | `ddl-elements.json`: `tables[*].table_id`・`tables[*].policy_ids[*]`・`policies[*].policy_id`・**`policies[*].role_ids[*]`(配列 ◎ `:232-240`)**・`roles[*]`・`functions[*]`・`scope.product_schema` | `collections: [{items: "$.tables[*]", id: "table_id", namespace: "table"}, {items: "$.policies[*]", id: "policy_id", namespace: "policy", structure: {kind: "reference", source: "table_id", target: "role_ids[*]", direction: "source->target", participants: ["table_id", "role_ids[*]"]}}, {items: "$.tables[*]", id: "policy_ids[*]", namespace: "policy", role: "reference"}, …]`。**`structure` の `source` / `target` が配列パスなら要素ごとに 1 タプルを生成**(R7-P1-2)。構造を導出する collection の集合と `structure` の全欄は `pins.profile_gating_digest` に含まれる(R7-P0-1・R8-P0-2) |
| **`auth_ddl_map`** | TSK-250 が作る | `collections: [{items: "$.entries[*]", id: "catalog_entry_id", refs: "ddl_ids[*]", structures: "structures[*]"}]`。制約: ID 集合 = `auth_catalog` と exact-set / `ddl_ids` 非空 / **`structures` は entry ごとに非空・各 `participants ⊆ ddl_ids`・全 entry の `structures` の和 = `ddl_elements` から導出した(refs に対応する)構造の集合(exact-set・raw DDL ID で照合)** |
| **`product_ddl_map`**(probe-only DDL のとき必須 — R6-P0-3・R7-P0-2) | TSK-250 が作る | `ddl_elements.scope.product_schema == false` のとき必須: probe 要素 ID → 製品要素 ID(マニフェスト要素)の写像。**domain = `auth_ddl_map` が参照する全 ID(refs ∪ structures の source/target/participants)と exact-set**。未写像・余分・曖昧(1 対多)は終了 2。**射影は二段階**(6-2 節 `cross-consistency`) |
| `waiting` | `waiting-data-model.json` | `collections` + `fields: {status, physical, decision_section, source_id}`。WAIT 側の構造は **抽出器(6-3)が manifest / 本文から導出した構造のうち `physical` を participant に含むもの** |
| `forbidden` | `forbidden-data-model.json` | 構造宣言の列 `{id, kind: relation|column-role|transition|reference, source, target, direction: source->target|target->source|both, participants}`(**alias はここには置かない** — 単一 alias 表へ・R7-P2-3) |
| `baseline_digest` | 台帳 + digest | `{ledger, digest_file, expected_ids(必須・独立資産), owner_steps_allowed(必須)}`。`immutable_fields` はスキーマ版で固定 |
| `direct_requirements` | `direct-requirements.json` | 非空・全 ID が `universe` の要件 ID に含まれる。**さらに `claims` の `classification == direct_requirement` の集合と exact-set**(`collection_sets` の宣言 `direct-requirements-vs-claims`・資産自体は `pins.asset_digests.direct_requirements` で固定 — R7-P0-4・R8-P0-3。TSK-250 の claims 分類規則に `direct_requirement` を追加する — 11 節 22) |
| `normalize` | — | `{strip_prefixes, case, separator, aliases: {namespace: {alias: canonical}}}`。**alias の供給源はこの単一表のみ**。canonical を再 alias する・同一 alias が 2 つの canonical を持つ・循環 — いずれも終了 2。単射性は名前空間内(alias 同値類内の一致は許容) |

### 6-2. 各検査

| check ID | 判定 | 入力 |
| --- | --- | --- |
| `forbidden-structure` | `forbidden` の各構造を、**抽出器(6-3)が文書とマニフェストから導出した構造集合**(別名表で正規化済み)と `{kind, source, target, direction, participants}` で照合。一致すれば fail。方向の違う同一辺は別構造・`both` は両方向 | `forbidden` + 抽出器 |
| `attribution-direct` | 帰属表で `kind == 対象外` の要件 ID が `direct_requirements` に含まれれば fail(資産は必須・非空・**`claims` の `direct_requirement` 分類と exact** — `collection-consistency` の必須宣言で拘束) | `direct_requirements` + 帰属表 + `collection_sets` |
| `baseline-digest` | スキーマ版 1 の immutable exact-set `{id, baseline, source, location, detection, check, owner_step, invariant.scope, invariant.forbidden, invariant.positive, invariant.mapping}`(mutable = `{status, discovered_at, closure_evidence}`)を canonical 形(キーを UTF-8 バイト順・区切りなし・`ensure_ascii=False`・整数のみ・重複キーは終了 2)へ直列化して SHA-256。`id` 順に `<id> <hex>\n`、先頭行 `envelope schema_version=1 algo=sha256 fields=<列>`。逐語一致 | `baseline_digest` |
| `cross-consistency` | ① `waiting` の `status == resolved` なら `physical` が正規化後に**マニフェスト要素集合に存在し、かつ本文に出現**(契約どおり — R6-P0-3)② **段階 A(raw DDL ID)**: `auth_ddl_map` の各 ref が `ddl_elements` に存在、map の ID 集合 = `auth_catalog`、各 entry の refs・structures 非空、structures の和 = DDL 導出構造(exact)。**段階 B(製品 ID)**: `product_ddl_map` を refs と structures の `source` / `target` / `participants` の**全 ID に適用**して製品構造へ射影し(probe-only でなければ恒等写像)、射影後の各 ref が**マニフェスト要素集合に存在** ③ (射影後の AUTH structures ∪ WAIT の導出構造)と `forbidden` の各構造を **`{kind, source, target, direction, participants}` 全項目**で照合し、一致(`both` は方向不問)があれば fail(R7-P0-2) | `waiting` / `auth_catalog` / `auth_ddl_map` / `product_ddl_map` / `ddl_elements` / `forbidden` + 抽出器 |
| **`collection-consistency`** | プロファイルの `collection_sets`(6-4)に従い、資産 collection 間または資産とマニフェストの間で `exact` / `subset` を検査。差集合を reason に出す | `collection_sets` |
| `unique-owner`(global) | 台帳の ID 集合 = `expected_ids` と完全一致 / 全項目が `owner_step` を持ち `owner_steps_allowed` の要素 / 重複なし | `baseline_digest` |

**負例(必須)**: 空 map / map の脱落・過剰 / refs 空 / **`structures` 空・1 件脱落・participants 相違** / 禁止方向で red・逆方向で green / WAIT が本文に無い / AUTH がマニフェストに無い /
`direct_requirements` 空 / immutable 各フィールド(`baseline` 反転を含む)改変で red・mutable 改変で green / `collection_sets` の脱落・過剰・forbidden 混入。

### 6-3. 構造抽出器 `structure_extractors`(R6-P0-2)

プロファイルが**文書とマニフェストから構造タプルを導出する規則**を宣言する(checker に文書固有の表見出し・列位置をハードコードしない):

```json
"structure_extractors": [
  {"id": "relations", "source": "manifest", "kind": "relation",
   "map": {"source": "source_table", "target": "targets[*]", "direction": "source->target", "participants": ["source_table", "targets[*]"]}},
  {"id": "transitions", "source": "document", "section": "7-2", "table": {"header_match": ["遷移", "条件"]},
   "kind": "transition", "map": {"source": {"column": 0, "regex": "^(.+?) →"}, "target": {"column": 0, "regex": "→ (.+)$"}, "direction": "source->target", "participants": ["source", "target"]}},
  {"id": "column-roles", "source": "document", "section": "4-2", "table": {"header_match": ["要素", "役割"]}, "kind": "column-role",
   "map": {"source": {"column": 0}, "target": {"column": 1}, "direction": "both", "participants": ["source"]}},
  {"id": "implicit-refs", "source": "derived", "from": "relations", "rule": "transitive-closure", "kind": "reference"}
]
```
- `source: manifest | document | derived`。`document` は `section` + `table.header_match`(表の識別)+ 列 → タプル項目の写像(`column` / `regex`)。`derived` は既存抽出結果からの導出(`transitive-closure` / `inverse`)で**暗黙関係**を表す
- すべてのタプルは `normalize`(別名表を含む)を通す。**抽出器が 1 件も構造を得られない**(節・表が見つからない)場合は終了 2(黙って空にしない)
- `forbidden-structure` / `cross-consistency` を `required_checks` に含むプロファイルは `structure_extractors` が必須(欠落は終了 2)
- **完全性はレジストリ `pins.profile_gating_digest` で固定**(R7-P0-1・R8-P0-2): 抽出器の追加・削除・`map` / `direction` / `participants` / `from/rule` の変更はいずれも digest を変える。
  機構側の検査として **`forbidden` に現れる全 kind を覆う抽出器が無ければ終了 2**。抽出器 1 本の脱落・DDL 構造 collection 1 本の脱落・`map` 1 欄の変更で pins 不一致になる統合負例をサンプルに置く
- サンプルには relation / column-role / transition / reference の各 kind の抽出負例(表見出し不一致・列ずれ・別名未登録)を置く

### 6-4. 集合一致 `collection_sets`(R6-P0-5)

```json
"collection_sets": [
  {"id": "claims-relations-vs-manifest", "relation": "exact",
   "left":  {"asset": "claims", "collection": 0, "filter": {"field": "classification", "equals": "relation"}, "key": "source_id"},
   "right": {"manifest": "relations", "key": "id"}},
  {"id": "forbidden-not-in-manifest", "relation": "disjoint",
   "left": {"asset": "forbidden", "key": "id"}, "right": {"manifest": "relations", "key": "id"}}
]
```
`relation ∈ {exact, subset, disjoint}`。両辺は資産 collection(`filter` 可)またはマニフェストの集合。差集合を reason に含める。TSK-250 ステップ 5 の「claims の relation 行 = manifest」はこの宣言で満たす。
**必須の宣言はレジストリ `pins.profile_gating_digest` で固定**(R7-P0-3)— 宣言の追加・削除・左右の変更は digest を変える。サンプル entry は `claims-relations-vs-manifest`(exact)と
`direct-requirements-vs-claims`(exact)を持つ。**直接要件の期待集合**(R8-P0-3)は `pins.asset_digests.direct_requirements` で資産自体を固定する(claims 分類との exact は整合検査、
期待集合の正は pin された資産 — 資産を変えるにはレジストリ差分が要る)。データモデル型 entry の実値は TSK-250。

## 7. 参照の分類(`reference-class`)

`reference_policy.rules` は順序付き。条件: `source_section`(任意)/ `target_pattern`(正規化相対パスの glob・必須)/ `fragment`(任意)。first-match。未一致は終了 2。`normative` のリンク先は `status: approved`。既存 `noncanonical-reference` は変更しない。

## 8. 帰属検査の強化(`COV`)

destination 文法は `kind` ごとの判別共用体: `対象外` → 理由文(非空)/ 他 → `節式(。説明文)?`、`節式 := segment (・ segment)*`、`segment := section_atom | chapter 〜 chapter`、`section_atom := chapter | section`。
未解析は終了 2。現行 212 件の全件解析と `2-1・4〜9` / `2-1・6・9` / `10-1・11-1。配信は…` / 理由文を回帰例に固定。`attribution-destination`(節の実在 / **根拠 = 展開した節のいずれかに当該要件の安定 ID〔`FR-xxx` / `NFR-xxx`〕が明示出現する行が 1 行以上** — R8-P2-3。無関係な文章しかない節は負例)/ `attribution-direct`(6-2)。既存 `attribution` / `ledger` は変えない。

## 9. CI 配線

`ci.yml` の docs-lint 3 step(`:51-53`)は無変更。引数なし = 本番レジストリ列挙。`tests/test_ci_wiring.py` の既存アサーションは無変更。設計書 10.1 は触らない。

## 10. `codex_run.py` の `has_filled_step_row`

見出しレベルのスタック / fenced code 除外 / 見出し名の正規化一致(否定形は負例)。**報告は 3 状態**(R8-P2-2 — 関数は `bool` から `StepTableStatus` 列挙 + 従来互換の真偽ラッパへ):
`no-table`(表が無い — 現行文言を維持)/ `table-outside-scope`(記入済み行はあるが「実装ステップ」見出しのスコープ外 — 文言「ステップ表は見出し『…』の配下にあります。『実装ステップ』見出しの配下へ移すか、その見出し名を含めてください」)/
`table-in-fenced-code`(記入済み行が fenced code 内にしか無い — 文言「ステップ表がコードブロック内にあります」)。`cmd_implement` は状態別の文言で `die` する。`tests/test_codex_run.py` 新設。`tests/test_hooks.py` の wrapper ケース(`:814`・`:1022`・`:1116`)は green を保つ(期待文言の追随が必要かはステップ 1 で確定 — C 集合の条件付き要素)。

## 11. TSK-250 への申し送り(PR 本文に転記。**TSK-250 は着手前に再レビューが必要**。24 項目)

| # | 項目 | 本タスクの立場 |
| --- | --- | --- |
| 1 | ステップ 22「明示引数で CI に追加」 | CI は引数なし列挙。本番 `registry.json` 登録で検査対象になる |
| 2 | 設計書 10.1・`tests/test_ci_wiring.py` | 本タスクは触らない |
| 3 | `guard_paths` 登録(B 集合) | TSK-250 の最初の独立コミットで登録 |
| 4 | 台帳 H-78・H-79 | TSK-250 ステップ 25 |
| 5 | プロファイル・レジストリの実パス | `profiles/sync-protocol.json`・`profiles/registry.json` |
| 6 | fail-closed の条件 | 契約 3 + 解決できない節 / 脱落トークン / レジストリ不一致 / 完全分割違反 / 必須検査の資産・抽出器・集合宣言の欠落 / 正規化衝突 |
| 7 | `verify_handoff_digest.py` | ランナーには載せない |
| 8 | `assets` の宣言形式 | 6-1 節(現物の項目名・`identity`・複数 collection・`join`・名前空間・`structure`) |
| 9 | 「A へ戻す」経路 | Notion コメント + 新規タスク起票 |
| 10 | 欠陥台帳・宣言資産の項目 | 機械欠陥は `check` と `invariant` を持つ。`invariants/data-model.json` は 2-2 の汎用規則を満たす |
| 11 | 完全分割と `must_require` | データモデル型は `must_require` = 全 22(レジストリ entry) |
| 12 | ランナー契約と全検査 0 の時期 | 文書是正後に終了 0。それ以前は終了 1 の不適合診断 |
| 13 | `absent-section` | 「存在してはならない節」を表現できる |
| 14 | **作成順と staging の木**(1-1) | 文書骨格の直後に staging 一式を原子的に作る → 是正 → 終了 0 → 本番移設 + 登録を同一コミット |
| 15 | `auth_ddl_map`(`structures` 付き)/ **`product_ddl_map`**(probe-only DDL のとき)/ `direct_requirements` / `expected_ids` | TSK-250 が独立資産として作る |
| 16 | TSK-250 計画書の改訂点 | 資産パス(3 節)・ステップ 2/4/5/6/22/24/25・検証コマンド集合・欠陥台帳の項目・staging 骨格ステップの追加・`auth_target` の記述削除 |
| 17 | 契約の種別名 | 5 種別名(`required-element` / `forbidden-element` / `exact-set` / `cross-reference` / `unique-owner`)は**すべて `invariant_kinds` に書け、スキーマが受理する**。`required-element` は `section-contains(text)` へ、`unique-owner` は global check へ写る |
| 18 | 変異テストの方針 | 行スコープ = 別行移動、節スコープ = 別節移動・意味部欠落・ID 交換 |
| 19 | **`structure_extractors`**(6-3) | 二文書目の表構造(遷移表・列役割表・暗黙関係)を抽出する規則は TSK-250 がプロファイルで宣言する(checker は変更しない) |
| 20 | **`collection_sets`**(6-4) | claims の relation 行 = manifest の exact-set はこの宣言で満たす(`collection-consistency`) |
| 21 | **レジストリ entry の `must_require` + `pins`**(1-2) | データモデル型 entry は `must_require` = 22 と、`pins`(`profile_gating_digest` / `invariants_digest` / `asset_digests`)の実値を持つ。**何を pin するか(`asset_digests` のキー集合)と実値は TSK-250 が確定**。プロファイルの自己申告では必須検査を有効化・空洞化できない |
| 22 | **claims の分類 `direct_requirement`**(形式の例) | TSK-250 の claims 分類規則(ステップ 4)に `direct_requirement` を追加するかは TSK-250 の設計。採るなら `direct_requirements` 資産と exact-set で拘束し、資産を pin する |
| 23 | **`product_ddl_map` の二段階射影**(機構) | 段階 A = raw DDL ID で map と DDL 導出構造を exact 照合、段階 B = 全参照 ID を製品 ID へ射影して manifest / FORB と比較。写像 domain は全参照 ID と exact。**probe-only DDL を使うかどうか自体が TSK-250 の判断** |
| **24** | **契約 5 の文言変更(PO 裁定 (b)・2026-09-04)** | TSK-250 計画書 1 節の契約 5「次の 4 つを機械で保証する」は、**「A は 4 検査 + 集合一致 + `unique-owner` の機構(評価器・抽出器・集合一致・資産ローダー・pins)を提供し、合成サンプルで全 22 ID が動くことを保証する。データモデル正本に対する実入力契約(資産形状・必須抽出器・集合宣言・pin 対象と実値)は TSK-250 が自分の計画で固定し、機械保証の主張は TSK-250 側の受け入れ条件に置く」へ改める**。「人間確認へ回して契約を満たす」逃げ道の禁止は維持(機械保証の**実装場所**が A から B のプロファイル宣言 + A の機構へ移るだけ) |

## 12. 前例として借りるもの(`scripts/check_authz_catalog.py` — 対象外)

`schema_version` / `asset_kind` 不一致で停止(`:1151-1152`・`:1779-1780`)、`oracle_context.oracle_commit`(`contracts/authz/ddl-elements.json:4-7`)。

## 13. コンフォーマンスランナーの契約(`scripts/check_doc_profiles.py`)

- synopsis: `check_doc_profiles.py --profile <path> [--registry <path>] [--checks <ids>] [--json]`(`--profile` 必須・列挙しない)
- 終了コード: 0 適合 / 1 違反 / 2 入力不正。`--json` 時は終了コードにかかわらず 1 つの envelope:
  `{schema_version: 1, profile, registry, exit_code, partial, checks: [{check_id, status: pass|fail|not_applicable|not_run, reason?, findings: […]}], errors: [{code, message, path?}]}`
- `checks` は 5-1 節の順で **常に 22 件**。`--checks` 時は未選択の ID を **`not_run`**(`not_applicable` への偽装禁止 — R6-P2-3)、`partial: true`。終了 2 では `errors` 非空
- 実プロファイル非依存(同期側パスの open 無しをモックで固定)

## 14. 基準線の固定と残余リスク

### 14-1. 基準線

既存 node ID 875 件の固定集合包含(`baseline-node-ids-f92b5f8.txt`・SHA-256 `a07454fcc3e3bc9c365a28f1dc66cec2330bfb08ecede80d8c52725169369046`・無変更 oracle)/ passed ≥ 875 / `skipped` `xfailed` `xpassed` `deselected` = 0 / 最終統合表(plan ステップ 38)。

### 14-2. 残余リスク(受容済み)

| リスク | 受容の根拠 |
| --- | --- |
| マージ後〜TSK-250 の最初のコミットまで B 集合の新設分が `guard_paths` 外 | 人間の裁定 2026-09-04・11 節 3 |
| 1 周目 P1 3 件の一次記録欠落 | 2026-08-31 の転記漏れ(H-87) |
| ステップ 3〜9 の間、節 1 の不在が機械保証されない | 同一 PR 内 |
| `preamble` の意味と oracle 作成時の意図のずれ | プロファイルに明記して現状維持 |
| **契約 5 の実入力契約(データモデル正本に対する資産形状・必須宣言・pin 実値)は本タスクで検証しない** | **PO 裁定 (b)・2026-09-04**。二文書目が存在しないため本タスクで決められない。TSK-250 の再レビューで固定し、機構(6 節)と pins で空洞化を防ぐ |

## 未解決・検討メモ

- research 1-2 節・6 節の「16 分岐」は正しいが、SP-19 は到達不能な死コード(本書 2-1)。research は原文のまま残し、本書を正とする
- `GLOBAL_CHECK_IDS` の名前と実態のずれは触らない
