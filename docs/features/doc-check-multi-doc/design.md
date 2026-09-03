---
feature: doc-check-multi-doc
type: design
date: 2026-09-04
---

# 詳細設計: 文書検査機構の多文書対応(プロファイル化 + 不変条件 DSL)

[plan.md](plan.md) 4 節から参照される詳細設計。事実の典拠は [research.md](research.md)(1〜5 節 = 2026-08-31、6 節 = 2026-09-04 再検証)にあり、
本書は**設計判断とその根拠**だけを書く(設計書 7.1-1)。略記は research.md と同じ(`PROP` / `COV` / `TSK250PLAN` 等)。
計画レビューの指摘 ID(`R1-*`〜`R5-*`)は worklog 2026-09-04 の一次記録表が正。

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

**「新規機構を発明しない」(`docs/features/sync-protocol-canonical/plan.md:294`)との関係**: 本タスクが作る型体系・スキーマ・評価器・レジストリ・ランナーは
**いずれも新規機構である**。「発明していない」とは主張しない(R1-P1-1)。2026-08-31 の裁定は**前決定に対する明示的な例外・上書き**として記録する。
例外を許す理由は、TSK-250 の受け渡し契約(`TSK250PLAN:65-68`)が機械保証を契約として要求しているため。前決定の趣旨(台帳 H-78)は、
**機構を確定ゲートの外(本タスク)で作り、oracle を触らずに作る**ことで守る(例外は 4 節の MT-01 のみ)。

## 1. プロファイル(文書固有の宣言の束)

### 1-1. 置き場・レジストリ・列挙

| 資産 | パス | 役割 |
| --- | --- | --- |
| **レジストリ** | `scripts/design_relations/profiles/registry.json` | `schema_version` / `profiles: [{name, file, document, must_require: [check_id…]}]`。**期待されるプロファイルの完全集合**。**`must_require` はレジストリ entry のフィールド**(プロファイル側には置かない) |
| プロファイル | `scripts/design_relations/profiles/<name>.json` | 文書 1 本につき 1 ファイル。**このディレクトリにはレジストリとプロファイル以外を置かない** |
| スキーマ | `scripts/design_relations/schemas/{profile,registry,invariant,assets}.schema.json` | `schema_version` を持つ |
| 宣言資産 | `scripts/design_relations/invariants/<name>.json` | 欠陥 ID → 構造宣言(2-2 節) |
| 共通ローダー | `scripts/doc_check_profile.py`(新設) | スキーマ検証(自前の最小検証器)・レジストリ照合・パス解決・`assets` ローダー |
| サンプル | `tests/fixtures/profile-sample/profiles/`(レジストリ + プロファイル 2 本)/ `doc/`(合成文書・manifest・defects・invariants・requirements・universe)/ `assets/`(合成資産) | 実プロファイル非依存の契約テスト入力(R5-P1-1 — レジストリ専用ディレクトリを分ける) |

**列挙の規則**(選択・上書き引数が一切無いとき): 使用するレジストリの `profiles[].file` の集合と、**そのレジストリと同じディレクトリ**の `*.json`(レジストリ自身を除く)の
実ファイル集合が**完全一致**しなければ終了コード 2。`name` / `document` / 機械欠陥の名前空間は一意。0 件は終了コード 2。
**`--registry <path>`**(両検査・ランナー共通・既定 = 本番レジストリ)で別のレジストリ(staging)を指定できる。**パス解決**: プロファイル内の相対パスとレジストリの `file` は
リポジトリルート(`--root`)基準。

**TSK-250 の作成順**(R3-P0-8・R4-P0-8・R5-P1-2): ① **最初の独立ステップで staging 一式の骨格を原子的に作る** — staging ディレクトリ(例 `docs/features/data-model-canonical/staging/`)に
`registry.json`(`must_require` = 全 21)・プロファイル・**全必須資産の構造的に妥当な骨格**(manifest / defects〔`check` と `invariant` を持つ〕/ invariants〔`structural_required` / `required_declarations`〕/
claims / auth_catalog / ddl_elements / auth_ddl_map / waiting / forbidden / direct_requirements / expected_ids / baseline_digest)。この時点で
`check_doc_profiles.py --registry <staging> --profile <staging のプロファイル> --json` は**終了 2 にならず**、終了 1(不適合)の診断を返す(`partial: false`)
② 文書と資産を是正し、是正が終わった後に同コマンドが終了 0 ③ 本番パスへの移設と本番 `registry.json` への登録を**同一コミット**で行う。

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
| 種別 | `invariant_kinds` | 2-1 節の 13 種の部分集合 | 契約 2 |
| 検査 | **`required_checks`** / **`not_applicable`**: `{check_id: 理由}` | 同期: 既存 14 / 新 7(理由 = trim 後非空) | R3-P0-1・R4-P1-1 |
| 検査入力 | `assets` | 6-1 節。同期 = 空 | — |
| 帰属 | `direct_requirements` | 資産パス(`attribution-direct` 必須時は必須・非空)。同期 = 無し | R4-P0-6 |
| 参照 | `reference_policy` | 7 節 | — |

**完全分割**: `required_checks ∪ not_applicable` = 5-1 節の全 21 ID、積は空、`required_checks ⊇ registry.must_require`。未知 ID・空理由は終了 2。
`--checks` の部分実行は「部分診断」(`partial: true`)で適合判定ではない。

**fail-closed**: 必須欠落・版不一致・未知フィールド・`invariant_kinds` 外の宣言・完全分割違反・`must_require` 違反・必須検査の資産欠落・レジストリ不一致 — 終了コード 2。

## 2. 不変条件 DSL

### 2-1. 種別(13 種)— 旧分岐の述語に一対一 + 契約の種別名(R3-P0-10・R4-P0-2・R5-P0-2・R5-P2-7)

◎ `PROP:432-593` の全分岐と補助述語(`_table_row` / `_identified_row` / `_element_has_row` / `_element_occurs` / `_route_row_matches` / `_numbered_ids` / `_has_exclusion` / `check_emphasis`)を確認。

| # | kind | 引数 | 適合条件 | 由来 |
| --- | --- | --- | --- | --- |
| 1 | `forbidden-element` | `literals` / 任意 `sections` | literal が対象範囲に無い(`defects.json` の `forbidden` は自動でこの kind。宣言版は TSK-250 向け) | 全欠陥・**SP-19(forbidden-only)** |
| 2 | `row-selector` | `id`・`section`・`mode: needle|identifier`・`keys` | 該当行が**存在**。他宣言が `row: <id>` で参照 | SP-01・02・07・09・10・11・12・20 |
| 3 | `row-contains` | `row`・`literals` または `elements: {relation, field}` | 選択行に全 literal / 全要素 | SP-01・02・20 |
| 4 | `section-contains`(**契約名 `required-element` を alias として受理** — `as: text` に写る) | `sections`・`literals` または `elements`・`as: text|identifier|identified-row|row`・任意 `key: id-part` | 各節に各 literal / 要素が as のモードで存在 | SP-02・03・08・13・14 |
| 5 | `exact-set` | **`sections`(複数)または `row`**・`routes`(`[P1..]` / `containing: T6`)・`prefix`・`expected: manifest-route` | 各節(または行)の経路行の番号付き ID 集合が期待集合と完全一致 | SP-06・07・08・09 |
| 6 | `cross-reference`(**契約種別 — 旧分岐に由来なし・合成 corpus で受け入れ**) | `from: {row}`・`to: {row}`・`extract: regex` | 2 行から抽出した値が一致 | TSK-250 契約 |
| 7 | `element-lookup` | `relation`・`prefix`・`section`・`row_identifier` | 接頭辞で見つけた要素の意味部が識別行に含まれる | SP-08 |
| 8 | `row-scoped-forbidden` | `row`・`literals` | 選択行に literal が無い | SP-09 |
| 9 | `any-of` | `row`・`literals` | 選択行に literal のいずれか | SP-09 |
| 10 | `required-exclusion` | `row` または `sections`・`subject`・`term` | 除外宣言がある(`_has_exclusion`・語彙はプロファイル) | SP-12・16 |
| 11 | `conditional-forbidden` | `row`・`literal`・`unless: [literals]` | literal 禁止、`unless` が全部あれば許容 | SP-20 |
| 12 | `well-formedness` | `scope`・`rule: balanced-emphasis` | `**` が偶数個 | SP-18 |
| 13 | `absent-section` | `section` | 節 ID の見出しが**存在しない** | MT-01 |

**`unique-owner` は kind ではなく check ID**(global invariant — 6-2 節)。契約の 5 種別名との対応: `required-element` = alias(4)/ `forbidden-element` = 1 /
`exact-set` = 5 / `cross-reference` = 6 / `unique-owner` = check ID(11 節 17 で申し送る)。

**評価順**: 1 欠陥内の宣言は配列順・first-failure。`defects.json` の `forbidden` は宣言より先(`PROP:619-622`)。`row-selector` の失敗は当該欠陥の違反。

**旧分岐 → 宣言の完全対応**(◎):

| 欠陥 | 宣言列 |
| --- | --- |
| SP-01 | `row-selector`(7-2 needle 未送信・退避済み)→ `row-contains`(A5・退避)→ `row-selector`(6-3 identifier B4)→ `row-contains`(A5・退避) |
| SP-02 | `row-selector`(7-1 identifier A5)→ `row-contains`(elements R-ACK-STATE.source)→ `section-contains`([6-3, 7-2]・同 elements・as row) |
| SP-03 | `section-contains`([6-3, 7-2, 9-5]・elements R-QUEUE-LIFE・as identifier) |
| SP-06 | `exact-set`(**sections [8-1, 10-2, 11-2]**・routes P1〜P3・manifest-route) |
| SP-07 | `exact-set`(sections [8-1]・P4)→ `row-selector`(9-2 needle 旧世代・退避・B4・原子)→ `row-selector`(10-2 needle 退避・B4・原子)→ `row-selector`(11-2 needle P4・退避・B4) |
| SP-08 | `element-lookup`(R-TXN-ROUTE・`T6:`・8-1・T6)→ `section-contains`(4-4・一時 ID・写像・text)→ `section-contains`(7-1・D5・確定結果・text)→ `exact-set`(sections [8-1]・containing T6) |
| SP-09 | `row-selector`(8-1 identifier P3)→ `exact-set`(row・T・P3)→ `row-scoped-forbidden`(T5)→ `any-of`(T7・V11) |
| SP-10 | `row-selector`(8-1 identifier P3)→ `row-selector`(7-1 needle P3・応答) |
| SP-11 | `row-selector`(6-2 needle 期待版不一致)→ 同(6-3)→ 同(8-3) |
| SP-12 | `row-selector`(6-3 identifier B3)→ `required-exclusion`(row・D1 を持たない変更イベント・D5)→ `row-selector`(6-4 needle 同・D5)→ `required-exclusion`(row・D5) |
| SP-13 | `section-contains`(4-3・elements R-EVENT-FIELD・as identified-row・key id-part)→ `section-contains`([4-3-A, 11-2]・同・as identifier) |
| SP-14 | `section-contains`(4-3-A・W3-a・W3-b・変更版順・text)→ `section-contains`([5-5, 11-2]・変更版順・D1・D2・論理再生順・text) |
| SP-16 | `required-exclusion`(sections [6-1, 6-2]・D1 を持たない変更イベント・prefix) |
| SP-18 | `well-formedness`(4-3-A・balanced-emphasis) |
| SP-20 | `row-selector`(2-1 needle `\| D1 \|`)→ `row-contains`(順序と欠落・undo の逆順)→ `row-selector`(4-2 needle D1・順序・欠落)→ `row-selector`(4-2 needle D5・再送・二重適用)→ `conditional-forbidden`(row 2-1・再送の重複排除・unless D5 の用途・D1 の用途ではない) |
| **SP-19** | **宣言なし(forbidden-only)** — 構造分岐の判定文字列が `forbidden` と同一で到達不能(◎ `defects.json:258-276`・`PROP:570-572`)。撤去ステップで死コードを削除。oracle 無変更 |
| MT-01 | `absent-section`(`"1"`) |

**変異テスト**(R4-P0-2・R5-P0-3): 「literal を別行へ移す」は**行スコープの kind**(`row-contains` / `row-scoped-forbidden` / `any-of` / `conditional-forbidden` /
`required-exclusion` の `row` 形 / `element-lookup` / `cross-reference`)に適用。**節スコープの kind**(`section-contains` / `required-exclusion` の `sections` 形 / `exact-set` / `well-formedness`)
には「別節へ移す」「要素の意味部を欠落させる」「ID 集合を 1 要素だけ交換する」を適用する。旧述語と同値でない変異は使わない(既存の振る舞いを変えないため)。

### 2-2. 結合規則(R2-P0-1・R3-P0-7・R4-P0-1・R5-P0-1・R5-P1-3)

`invariants/<name>.json` = `{schema_version, structural_required, legacy_structural, required_declarations, declarations}`。M = 機械欠陥 ID、D = 宣言を持つ ID、F = `forbidden` を持つ ID。
**汎用規則(全プロファイルに常時強制・違反は終了 2)**:

1. `structural_required ⊆ M`、`required_declarations ⊆ M`、`structural_required ∩ required_declarations = ∅`
2. **宣言必須集合 = (structural_required − legacy_structural) ∪ required_declarations ⊆ D**
3. `legacy_structural ⊆ structural_required`、`legacy_structural ∩ D = ∅`、legacy の各 ID に旧分岐が存在
4. **`D ⊆ M` かつ `D ⊆ structural_required ∪ required_declarations`**(余分な宣言 — SP-19 や人間欠陥への宣言 — を拒否)
5. `M − structural_required − required_declarations ⊆ F`(forbidden-only)
6. 移行完了時 `legacy_structural = ∅` かつ旧評価器の ID 別分岐 0 件(撤去と同時に検査)

**同期プロファイル専用のコンフォーマンステスト**(汎用規則ではない — R5-P0-1): `structural_required` = 固定集合 15(`SP-01 02 03 06 07 08 09 10 11 12 13 14 16 18 20`)、
`required_declarations` = `[MT-01]`、移行完了時 `D = structural_required ∪ required_declarations`(exact-set)。

`required_declarations` は骨格作成時 `[]`、`absent-section` 導入ステップで `[MT-01]` へ宣言と同時に更新。

### 2-3. 移行の正しさの証明

1. **構造 corpus 15 件**(旧分岐 15 ID): 異常例は forbidden literal を含まない / 各 ID の scope の全節見出しを実在させる / 異常例は終了 1・入力不正 0。SP-19・MT-01 の literal 対は forbidden corpus。MT-01 は `absent-section` 導入時に構造 corpus の 16 件目
2. **期待構造化 reason fixture**(`tests/fixtures/structural-reasons-expected.json`): **キー `(case_id, defect_id)`**、`input_kind: corpus-valid|corpus-invalid|fixture|approved`、`expected_exit`、
   `reason: {violated, kind, section, expected, actual, token}`(1 欠陥 1 reason・first-failure)。旧分岐の結果を手で写像(R5-P2-1)
3. **shadow 実行**: 移行期間中、期待 fixture・旧分岐・新評価器の三者一致。kind 単位の移行ステップは「該当 ID の三者一致」+「新評価器単独で corpus 判定」
4. **撤去の順序**: 全 kind の移行 → 前提検証(legacy 空・宣言の exact-set・期待 fixture への一致が shadow 無しで成立)→ 旧分岐と shadow 基盤の削除(規則 6 を同時に検査)

## 3. fail-closed

| 経路 | 現行 | 変更後 |
| --- | --- | --- |
| `extract_scope` の文法不一致トークン | 黙って捨てる(`PROP:337-339`) | 終了コード 2 |
| scope / 宣言の `section(s)` が文書に無い | `""`(`PROP:309-310`) | 終了コード 2。**`absent-section` の `section` は事前検査から除外** |
| 未対応 kind / 必須引数欠落 / 未知の欠陥 ID / プロファイル欠落 / レジストリ不一致 / 完全分割違反 / 必須検査の資産欠落 / 正規化衝突 / 重複 JSON キー | — | 終了コード 2 |
| 帰属先 destination の未解析トークン / `reference_policy` に一致しない参照 | — | 終了コード 2 |

## 4. MT-01 の oracle 改訂 + `absent-section`(裁定 (a′))

事実は research 6-3 節(◎)。① **oracle 改訂(plan ステップ 3)** — MT-01 エントリ内で `scope` から `1節` を除き `location` / `positive` / `mapping` を「12 アンカー + 節 1 の不在」へ。
差分は MT-01 エントリの範囲。forbidden corpus の MT-01 対の禁止語を `### 2-2.` へ ② **`absent-section` 型 + MT-01 宣言 + `required_declarations = [MT-01]`(plan ステップ 9・原子的)**。
③ ステップ 3〜9 の間は同一 PR 内(14-2 節)。`defects.json` は `guard_paths` 該当。

## 5. CLI(契約 1)

| 引数 | 意味 |
| --- | --- |
| 選択・上書き引数が一切無い | レジストリ列挙(`--registry` 既定 = 本番) |
| `--registry <path>` | 使用するレジストリ |
| `--profile <path>` | 単一プロファイル |
| `--document` / `--manifest` / `--defects-file` / `--requirements` / `--universe` | `--profile` なしなら既定(同期)プロファイルに束縛して上書き |
| `--checks` / `--defects` | `--profile` なしなら既定プロファイルに束縛(selector 単独テストを壊さない)。部分診断 |

### 5-1. check ID の全体表 — 21 ID

| 検査機構 | 既存 14 | 新 7(同期では `not_applicable`) |
| --- | --- | --- |
| `PROP` | 12(`PROP:13-27`) | `forbidden-structure` / `cross-consistency` / `baseline-digest` / `unique-owner` / `reference-class` |
| `COV` | 2(`attribution` `ledger`) | `attribution-destination` / `attribution-direct` |

## 6. TSK-250 が要求する 4 検査

### 6-1. `assets`(R3-P0-2/3・R4-P0-5・R4-P1-2・R5-P0-4・R5-P2-6)

現物(`contracts/authz/*.json` ◎)に対する宣言例を契約の正とする:

| asset | 現物 | 宣言例 |
| --- | --- | --- |
| `claims` | `requirement-claims.json`: `asset_kind` 無し、`claims[*].source_id` | `{path, identity: {schema_version: 1, required_top_keys: ["input_manifest","claims"]}, collections: [{items: "$.claims[*]", id: "source_id", namespace: "claim"}]}` |
| `auth_catalog` | `auth-catalog.json`: `entries[*].catalog_entry_id` / `requirement_claim_id`。DDL 要素 ID は持たない | `{…, collections: [{items: "$.entries[*]", id: "catalog_entry_id", namespace: "auth"}], join: {from_key: "requirement_claim_id", to: "claims", to_key: "source_id"}}` |
| `ddl_elements` | `ddl-elements.json`: `tables[*].table_id`・`tables[*].policy_ids[*]`・`policies[*].policy_id`・`roles[*]`・`functions[*]`・`scope.product_schema` | `collections: [{items: "$.tables[*]", id: "table_id", namespace: "table"}, {items: "$.policies[*]", id: "policy_id", namespace: "policy"}, {items: "$.tables[*]", id: "policy_ids[*]", namespace: "policy", role: "reference"}, …]` |
| **`auth_ddl_map`**(新規契約) | TSK-250 が作る | `{…, collections: [{items: "$.entries[*]", id: "catalog_entry_id", refs: "ddl_ids[*]", structures: "structures[*]"}]}`。**`structures[*]` = 正規化済み構造タプル `{kind, source, target, direction, participants}`**(AUTH 主張が主張する構造 — R5-P0-4)。制約: ID 集合 = `auth_catalog` と exact-set / `ddl_ids` 非空 / 各 ref が `ddl_elements` に存在 |
| `waiting` | `waiting-data-model.json` | `collections` + `fields: {status, physical, decision_section, source_id}` |
| `forbidden` | `forbidden-data-model.json` | 構造宣言の列 `{id, kind: relation|column-role|transition|reference, source, target, direction: source->target|target->source|both, participants, aliases}` |
| `baseline_digest` | 台帳 + digest ファイル | `{ledger, digest_file, expected_ids(必須・独立資産), owner_steps_allowed(必須)}`。`immutable_fields` は `assets.schema.json` の版で固定 |
| `direct_requirements` | `direct-requirements.json` | `{path, collections: [{items: "$.ids[*]"}]}`。非空・全 ID が `universe` の要件 ID に含まれる |
| `normalize` | — | `{strip_prefixes, case, separator, aliases: {namespace: {alias: canonical}}}` |

- **正規化名前空間**(R5-P2-6): 各 collection は `namespace`(`table` / `policy` / `role` / `function` / `claim` / `auth` …)を持つ。**単射性は名前空間内**で検証し、
  異なる元 ID が同じ正規形へ潰れたら終了 2。`aliases` は名前空間ごとの同値類で、同値類内の一致は意図的として許容。名前空間をまたぐ照合は行わない
- `items` / `id` / `refs` / `structures` は JSON パスの最小部分集合(`$.a.b[*]`・`c`・`c[*]`)。配列値 id と複数 collection を扱える
- `identity` は `asset_kind` または `required_top_keys`。不一致は終了 2
- `cross_consistency.auth_target: manifest | ddl_elements` をプロファイルで宣言
- サンプル(`tests/fixtures/profile-sample/assets/`)は `contracts/authz/` の現行 JSON と同形。データモデル型最小プロファイル(`must_require` = 21)は同期側パスを一度も開かずに全 21 ID を実行できる

### 6-2. 各検査

| check ID | 判定 | 入力 |
| --- | --- | --- |
| `forbidden-structure` | `forbidden` の各構造(kind・source・target・direction・participants)を別名表を通した正規化後に、文書の宣言表・遷移表・マニフェストから抽出した構造と照合。一致すれば fail。方向の違う同一辺は別構造・`both` は両方向 | `forbidden` + マニフェスト + 文書 |
| `attribution-direct` | 帰属表で `kind == 対象外` の要件 ID が `direct_requirements` に含まれれば fail。資産は必須・非空 | `direct_requirements` + 帰属表 |
| `baseline-digest` | 台帳の各項目から **スキーマ版 1 の immutable exact-set** `{id, baseline, source, location, detection, check, owner_step, invariant.scope, invariant.forbidden, invariant.positive, invariant.mapping}`(R5-P0-5 — `baseline` を含む)を取り出し(mutable exact-set = `{status, discovered_at, closure_evidence}`)、canonical 形(キーを UTF-8 バイト順・区切りなし・`ensure_ascii=False`・整数のみ・重複キーは終了 2)へ直列化して SHA-256(小文字 hex)。`id` の UTF-8 バイト順に `<id> <hex>\n` で連結、先頭行 `envelope schema_version=1 algo=sha256 fields=<列>`。逐語一致。RFC 8785 準拠は名乗らない | `baseline_digest` |
| `cross-consistency` | ① `waiting` の `status == resolved` なら `physical` が正規化後に `auth_target` の要素集合に存在 ② `auth_ddl_map` の各 ref が `ddl_elements` に存在し、`auth_target == manifest` ならマニフェスト要素にも存在。map の ID 集合 = `auth_catalog` の ID 集合、各 entry の refs 非空 ③ **構造タプル照合**: `auth_ddl_map` の `structures` と `waiting` 由来の構造(物理要素を participant とする)を、`forbidden` の各構造と `(kind, source, target, direction)` で照合し、一致(`both` は方向不問)があれば fail。**逆方向のみ一致は fail にしない** | `waiting` / `auth_catalog` / `auth_ddl_map` / `ddl_elements` / `forbidden` + マニフェスト |
| `unique-owner` | 台帳の ID 集合 = `expected_ids` と完全一致 / 全項目が `owner_step` を持ち `owner_steps_allowed` の要素 / 重複なし | `baseline_digest` |

**負例(必須)**: 空 map / map の脱落・過剰 / refs 空 / **禁止方向で red・逆方向で green の対** / `direct_requirements` 空 / immutable 各フィールド(`baseline` の反転を含む)1 件ずつの改変で red / mutable 各フィールドの改変で green。

## 7. 参照の分類(`reference-class`)

`reference_policy.rules` は順序付き。条件: `source_section`(任意)/ `target_pattern`(正規化相対パスの glob・必須)/ `fragment`(任意)。first-match。未一致は終了 2。
`normative` のリンク先は `status: approved`。既存 `noncanonical-reference` は変更しない。

## 8. 帰属検査の強化(`COV` — R5-P0-6)

- destination 文法は `kind` ごとの判別共用体: `対象外` → 理由文(非空)/ `同期側で決める`・`境界として参照` → `節式(。説明文)?`。
  **`節式 := segment (・ segment)*`、`segment := section_atom | chapter 〜 chapter`、`section_atom := chapter | section`**(混合式 `2-1・4〜9` と章単独 `2-1・6・9` を含む)。
  未解析は終了 2。現行 212 件(38/84/90)の全件解析と、`2-1・4〜9` / `2-1・6・9` / `10-1・11-1。配信は…` を回帰例に固定
- `attribution-destination`: 展開した各節が実在 / 根拠文が空でない。`attribution-direct`: 6-2 節。既存 `attribution` / `ledger` は変えない

## 9. CI 配線

`ci.yml` の docs-lint 3 step(`:51-53`)は無変更。引数なし = 本番レジストリ列挙。`tests/test_ci_wiring.py` の既存アサーションは無変更。設計書 10.1 は触らない。

## 10. `codex_run.py` の `has_filled_step_row`

見出しレベルのスタック / fenced code 除外 / 見出し名の正規化一致(否定形は負例)/ 3 種の報告。`tests/test_codex_run.py` 新設。`tests/test_hooks.py` の wrapper ケース(`:814`・`:1022`・`:1116`)は green を保つ。
`codex_run.py` は `core-areas.json` のどちらの集合にも無い(**C 集合**)。

## 11. TSK-250 への申し送り(PR 本文に転記。**TSK-250 は着手前に再レビューが必要**)

| # | 項目 | 本タスクの立場 |
| --- | --- | --- |
| 1 | ステップ 22「明示引数で CI に追加」 | CI は引数なし列挙。本番 `registry.json` 登録で検査対象になる |
| 2 | 設計書 10.1・`tests/test_ci_wiring.py` | 本タスクは触らない。二文書目登録時に TSK-250 が現行化 |
| 3 | `guard_paths` 登録(B 集合 = plan 3 節・最終確定はステップ 37) | TSK-250 の最初の独立コミットで登録 |
| 4 | 台帳 H-78・H-79 | TSK-250 ステップ 25 |
| 5 | プロファイル・レジストリの実パス | `profiles/sync-protocol.json`・`profiles/registry.json` |
| 6 | fail-closed の条件 | 契約 3 + 解決できない節 / 脱落トークン / レジストリ不一致 / 完全分割違反 / 必須検査の資産欠落 / 正規化衝突 |
| 7 | `verify_handoff_digest.py` | ランナーには載せない |
| 8 | `assets` の宣言形式 | 6-1 節(現物の項目名が正・`identity`・複数 collection・`join` 異名キー・名前空間) |
| 9 | 「A へ戻す」経路 | Notion コメント + 新規タスク起票 |
| 10 | 欠陥台帳・宣言資産の項目 | 機械欠陥は `check` と `invariant` を持つ。`invariants/data-model.json` は 2-2 の汎用規則を満たす(`structural_required` は DM 側で定義) |
| 11 | 完全分割と `must_require` | データモデル型は `must_require` = 全 21(レジストリ entry で宣言) |
| 12 | ランナー契約と全検査 0 の時期 | 文書是正後に終了 0。それ以前は終了 1 の不適合診断(`partial: false`) |
| 13 | `absent-section` | 「存在してはならない節」を表現できる |
| 14 | **作成順** | 最初の独立ステップで staging 一式(レジストリ・プロファイル・**全必須資産の骨格**)を原子的に作る → 是正 → 終了 0 → 本番移設 + 登録を同一コミット |
| 15 | `auth_ddl_map`(`structures` を含む)/ `direct_requirements` / `expected_ids` | TSK-250 が独立資産として作る |
| 16 | TSK-250 計画書の改訂点 | 資産パス(3 節)・ステップ 2/4/5/6/22/24/25・検証コマンド集合・欠陥台帳の項目・`auth_target`・staging 骨格ステップの追加 |
| 17 | **契約の種別名との対応** | `required-element` = `section-contains` の alias(`as: text`)/ `forbidden-element`・`exact-set`・`cross-reference` = 同名 kind / **`unique-owner` = check ID(global invariant・欠陥宣言の kind ではない)** |
| 18 | 変異テストの方針 | 行スコープ = 別行移動、節スコープ = 別節移動・意味部欠落・ID 交換(旧述語と同値な変異のみ) |

## 12. 前例として借りるもの(`scripts/check_authz_catalog.py` — 対象外)

`schema_version` / `asset_kind` 不一致で停止(`:1151-1152`・`:1779-1780`)、`oracle_context.oracle_commit`(`contracts/authz/ddl-elements.json:4-7`)。

## 13. コンフォーマンスランナーの契約(`scripts/check_doc_profiles.py`)

- synopsis: `check_doc_profiles.py --profile <path> [--registry <path>] [--checks <ids>] [--json]`(`--profile` 必須・列挙しない)
- 終了コード: 0 適合 / 1 違反 / 2 入力不正。`--json` 時は終了コードにかかわらず 1 つの envelope:
  `{schema_version: 1, profile, registry, exit_code, partial, checks: [{check_id, status: pass|fail|not_applicable, reason?, findings: [構造化 reason…]}], errors: [{code, message, path?}]}`
  (終了 2 では `checks` は部分結果・`errors` 非空。`checks` は 5-1 節の順)
- 実行する検査 = `required_checks`。**`partial: true` は `--checks` 使用時のみ**(全 21 の反復は `partial: false` の不適合診断 — R5-P2-2)。実プロファイル非依存(同期側パスの open 無しをモックで固定)

## 14. 基準線の固定と残余リスク

### 14-1. 基準線

- 既存 node ID 875 件の固定集合包含(`baseline-node-ids-f92b5f8.txt`・SHA-256 `a07454fcc3e3bc9c365a28f1dc66cec2330bfb08ecede80d8c52725169369046`・無変更 oracle)
- passed 総数は下限 875。`skipped` / `xfailed` / `xpassed` / `deselected` = 0
- 最終統合表(plan ステップ 37): 各負例 fixture → 期待 check ID で fail

### 14-2. 残余リスク(受容済み)

| リスク | 受容の根拠 |
| --- | --- |
| マージ後〜TSK-250 の最初のコミットまで B 集合の新設分が `guard_paths` 外 | 人間の裁定 2026-09-04・11 節 3 |
| 1 周目 P1 3 件の一次記録欠落 | 2026-08-31 の転記漏れ(H-87) |
| ステップ 3〜9 の間、節 1 の不在が機械保証されない | 同一 PR 内 |
| `preamble` の意味と oracle 作成時の意図のずれ | プロファイルに明記して現状維持 |

## 未解決・検討メモ

- research 1-2 節・6 節の「16 分岐」は正しいが、そのうち SP-19 は到達不能な死コード(本書 2-1)。research は原文のまま残し、本書を正とする
- `GLOBAL_CHECK_IDS` の名前と実態のずれは触らない
