---
feature: tenant-boundary-scope
type: research
date: 2026-09-24
---

# 調査メモ: 迂回検査 条件 5・条件 2 の射程(TSK-440)

## 問い

`scripts/check_tenant_boundary_bypass.py` がテナント境界と無関係な新設パッケージで 700 件超を検出する。
**どこまでを射程とすべきか**を、要件・脅威モデル・過去の決定・実測から決める。

## 結論(要約)

1. **条件 5 と条件 2 は別の問題である。** 条件 2 はこの検査器の脅威モデルのどの項目にも対応しておらず、
   由来は上流分割計画の「**面を混ぜない**」規律である。まとめて扱うと根拠が混ざる。
2. **TB007 の「由来を解決できないなら拒否する」という既定値は、文書のどこにも書かれていない。**
   本タスクは「**文書化されていない既定値を、文書化したうえで選び直す**」作業になる。
3. **案 C(`TenantContext` へ到達できないモジュールを対象外にする)の素朴な形には穴がある。**
   実測で、`TenantContext` へ到達できず DB 面へ到達できるモジュールが **11 件**あり、
   これは迂回検査が最も見たいコードである。**U-T1 が同型を既に否決している**(design.md:463)。
4. **除外の単位をモジュールにしてはならない。** 到達可能性は**母集団の導出根拠**には使えるが、
   「モジュールを除外する」形にすると U-T1 が P0 で否決した「パスで丸ごと除外」と同じになる。
5. **実装より手続が重い。** 検査器を 1 行変えると `base-allowlist.json` の凍結射影が動き、
   履歴ちょうど 1 件 + `contract_revision` 更新が機械的に要求される。

## 詳細と典拠

### 0. 本タスクの特殊事情(先に確認したこと)

- **誤検知の対象パッケージは develop に存在しない。** `backend/src/pitchlog/{domaincheck,domaingen,domainmut}` は
  **PR #74(TSK-235)が新設する**。本 worktree(develop 起点)では 0 件で、再現しない。
  → **負例・正例は合成 fixture で作る。** DoD の「feature/domain-calc-dsl で検出 0 件」は
  **他ブランチを当てて確かめる手順**になる。

### 1. 再現と分布(自分の実測・2026-09-24)

`feature-domain-calc-dsl` の worktree で `uv run python scripts/check_tenant_boundary_bypass.py` → **exit 1・719 件**。

| | TB007(条件 5) | TB002(条件 2) | 計 |
| --- | --- | --- | --- |
| `domaincheck` | 430 | 2 | **432** |
| `domaingen` | 70 | 78 | **148** |
| `domainmut` | 109 | 30 | **139** |
| 計 | **609** | **110** | **719** |

- **38 ファイル。3 パッケージの外は 0 件。**
- カード記載は 692 件(TB007 582 / TB002 110)。差は TSK-235 が敵対レビュー 4 周目の是正で足したコード。
  **この領域にコードが増えるたびに増える。**
- `domainmut.operators_lang` 単独で **60 件**。

### 2. 検査器の構造

- **検査コードと condition の対応**: TB001〜TB004 は資産 `base-allowlist.json` の `conditions[].error` から動的
  (`scripts/check_tenant_boundary_bypass.py:2688-2699`)。TB005 以降はコード内リテラル。
  **条件 5 には資産側の規則が無く、すべてコード側にある。**
- **TB007 の発火点**(`_check_tenant_context_call` `:2839-2980`):
  `flow.callable_symbol(node)` が `None`(= 由来を完全修飾名へ解決できない)のとき、
  属性呼び出しに限った免除を通したうえで TB007(`:2945-2971`)。
- **免除される provenance**(`:2946-2959`): `db` / `non_db` / `tenant_context` の属性呼び出し、
  および `db_result` / `non_db_attribute` で属性名が `TenantContext` の末尾名でないもの。
  → **誤検知は provenance が `unknown` に落ちた呼び出し**である。
- **相対 import を解決していない**(自分で確認 — `node.level` を参照する行が **0 件**)。
  `from .x import Y` は `x.Y` ではなく誤名になる。**由来が解決できない一因**。
- **`conservative_member_names` は主に保守的「拡大」の機構**で、緩和は同じ分岐の
  `provenance == "non_db"` 側にある(`:2793-2800`)。
  **inventory の member 名の非空部分集合しか許されない**(`:843-857`)ので、
  **案 B(この集合を広げる)は inventory の外へは出られない**。
- **`allowed_product_modules` は 0 件が強制**されている(`:1209-1211`
  「U-A1 / TSK-217 が未導入のため製品モジュールの生成経路は 0 件が必要」。実値も `[]`)。
- **走査母集団**: `git diff -U0 {base_ref}...HEAD -- backend/src`(`base-allowlist.json` の `diff.command`)。
  `base_ref` は資産から削除済みで CI が与える。既定は検査器ソースに凍結。
  **差分ファイルは全行解析**し、基準版の違反集合との差を取る方式(`scan_source_change`)。
- **汎用のパス除外・ファイル除外機構は存在しない。** あるのは条件 4 の provider モジュール免除、
  関数スコープ固定の免除 1 件、TB007 のモジュール allowlist(製品側 0 件強制)、
  TB005 の許可シンボル(関数単位)のみ。
- **条件 2 のパターン**(`base-allowlist.json` の条件 2 に 7 本): `(?:^|_)generation(?:_|$)` を含む。
  `_normalize_identifier`(`:1440-1445`)が `TracedGeneration` → `traced_generation` へ正規化するため末尾一致する。
  **条件 1〜3 には免除機構が一切無い。**

### 3. 脅威モデルと決定経緯

- **脅威モデルの実体は `docs/features/tenant-boundary-enforcement/design.md:426-454`(6-0 節)。**
  「脅威モデル」を節見出しに持つ文書は全 docs 中これ 1 件のみ。
  **feature 設計書であり、AGENTS.md 絶対規則 4 が列挙する正本ではない。**
  U-T1 のクローズ記録も「/sync-docs: 正本への反映なし」(`docs/worklog/2026-09-17-tenant-boundary-enforcement.md:57`)。
- **守るもの**(`design.md:435-440`): 強制点を経由せず DB へ到達する変更が red になること /
  不注意・知識の欠落・リファクタリングによる**漂流**を止めること / 強制点そのものが静かに書き換えられたら red。
- **守らないもの**(`:442-450`): 人間の逐行レビューを通過する**悪意ある committer** / **実行時の型** /
  同一プロセス内の攻撃者。「**一般的な型解決器は作らない**」(`:454`)。
- **6-0 が書かれた理由**(`:428-433`): 3 周目 P1「由来を追跡して既知の非 DB 型は通せ(過剰拒否)」と
  4 周目 P0「型注釈を信用するな(見逃し)」が**正面から矛盾**し、
  「両方を同時に満たすには一般的な型推論器が要る」。**線を引く。**
- **収束のさせ方**(`docs/development/harness-evaluation.md:3337-3343`):
  脅威モデルを明文化したうえで、レビューのプロンプトへ
  「経路を出すなら漂流か意図的な偽装かを明示せよ。後者だけなら P0 にするな」と課し、
  **逆向きに「6-0 が守ると書いたことを守れていなければ P0」も課した**。7 周目で P0 が 0。
  > **射程を狭めただけでは通らないよう、宣言した保証範囲に対しては厳しくする両建てが要る。**
- **射程を絞るときの規律**(`docs/worklog/2026-09-17-tenant-boundary-enforcement.md:240-247`):
  > **射程を絞るときは、絞った結果として落ちてはいけないものを同時に名指しする必要がある。**
- **TB007 を fail-closed にした決定文は存在しない。** docs 配下に「TB007」の語は **0 件**。
  `conservative_member_names` の決定記録も docs 配下に **0 件**。
- **条件 2 の由来**(`docs/features/product-impl-unit-split/plan.md:270`):
  5 条件表の条件 2 =「**同期セマンティクス**を扱わない」。同 `:258`
  「5 条件そのものは葉の計画書でも『**面を混ぜない**』規律として有効なので下表は残す」。
  同 `:275-277`「**検索式は『候補』であり、確定は各単位の計画書が行う**」。
  → **条件 2 はテナント境界の防御ではなく、単位分割の規律**である。
  対応するコア領域はハーネス設計書 6.3 の**同期プロトコル**行(`:391`)。
  sync-protocol の D4(記録権世代)との対応づけは**推論**で、明示リンクは無い。

### 4. 要件との関係

- **テナント分離の要求は存在する**: NFR-010(`docs/requirements/requirements-pitchlog-2026-07-22.md:846-850`)。
  ただし **`:850` の測定方法は「越境アクセスの自動テスト(API 直叩き含む。CI に常設)」= ランタイムのテスト**であり、
  静的解析による迂回検査ではない。
- **「静的な迂回検査を置け」「解決不能なら拒否せよ」は要件正本に存在しない。**
  要件書の fail-closed の用例 3 件(`:895` `:909` `:918`)は**すべて NFR-018**でテナント分離ではない。
- FR-034 の既定拒否は `:608` が「**射程は FR-041 が新設する権限・経路に限る**」と明文で限定。
  U-T1 自身も「**FR-034 の既定拒否を fail-closed の根拠に使わない**」
  (`docs/features/tenant-boundary-enforcement/plan.md:51`)。
- → **射程を狭めることは要件条文に抵触しない。** 掛かるのは手続(§6)と過去の決定(§5)。

### 5. 過去の決定との整合 — パス・モジュール単位の除外は否決済み

`docs/features/tenant-boundary-enforcement/design.md`:

- `:457`「旧案は…『**基底ファイルをパスで丸ごと除外する**』だった。**いずれも誤りだった**」(計画レビュー 1 周目 P0)
- `:463`「**基底ファイルを丸ごと除外すると、後からそのファイルへ直接 SQL や認可迂回を足しても
  永久に検査対象外**になる」
- `:470`「許可の粒度 | **ファイルではなく、基底の特定シンボル・特定関数の内側**に限る」
- `:471`「基底自身 | **除外しない**」

さらに「**検査対象パスを存在しない場所へ狭める**」は迂回の変種として**実測で拒否**されている
(`docs/worklog/2026-09-17-tenant-boundary-enforcement.md:197-199`)。
一般則として `plan.md:109`「**検査対象が検査の条件を決められる**」(7A・7D・2 周目 P0-3 が同型)。

### 6. 到達可能性の実測(定義別・自分の実測)

`backend/src/pitchlog` の静的 import グラフ(`feature/domain-calc-dsl` 側で 85 モジュール)。
`TenantContext` の定義は `backend/src/pitchlog/repositories/context.py:19`。

| 定義 | `TenantContext` へ到達可能 | 3 パッケージ内 |
| --- | --- | --- |
| A すべての静的 import(`TYPE_CHECKING` 内を含む) | **3** | 0 |
| B `TYPE_CHECKING` を除く | **3** | 0 |
| C B + 動的 import / `getattr` を fail-closed で到達扱い | **7** | **1**(`domainmut.operators_lang`・60 件) |

- **A と B は一致した** — `TYPE_CHECKING` の扱いは本リポジトリでは結論を変えない。
- 到達可能な 3 モジュールは `repositories.base` / `repositories.binding` / `repositories.context`。

#### ★ 素朴な案 C の穴(実測で発見)

**「`TenantContext` へ到達できないモジュールを除外」とすると、
`TenantContext` へ到達できず、かつ DB 面へ到達できるモジュール 11 件が除外対象に入る。**

```
pitchlog.authz.catalog / pitchlog.authz.provisioning
pitchlog.db.base / pitchlog.db.engine / pitchlog.db.mixins
pitchlog.db.data_migration.models / pitchlog.db.game_state.models
pitchlog.db.recording_rights.models / pitchlog.db.sync_protocol.event_kinds
pitchlog.db.sync_protocol.models / pitchlog.db.tenant_isolation.models
```

**迂回検査が本来いちばん見たいコードである。**
テナント境界を迂回するコードは **`TenantContext` を import しないからこそ迂回になる**ので、
「`TenantContext` へ到達できない」を除外条件にすると**検査が自分の目的を潰す**。
これは `design.md:463` が P0 で否決した構造と同じである(独立に実測で再発見した)。

**DB 面への到達可能は 13 / 85。3 パッケージは DB 到達も 0 件**なので、
除外条件を「**`TenantContext` にも DB 面にも到達できない**」の連言にすれば **719 件はすべて消える**。

### 7. 掛かる手続(実装より重い)

- **`base-allowlist.json` の `frozen_projection.external_files` に検査器本体が入っている**
  (`contracts/tenant_boundary/base-allowlist.json:19-21`)。
  → **`scripts/check_tenant_boundary_bypass.py` を 1 行変えるだけで凍結射影が動く。**
- 射影が動いたら機械的に要求されるもの(`scripts/check_tenant_boundary_bypass.py:694-719`):
  履歴を**ちょうど 1 件**追加 / **`contract_revision` の更新が必須**(現在 13)/
  履歴の before/after の `frozen_projection_sha256` が実スナップショットと一致 /
  **動いていないのに履歴を足すと red** / **merge-base の既存履歴の変更・削除は red**(追記のみ)。
- `movement_policy.movement_triggers` に **`pass_fail_mapping`** が含まれる
  → **合否写像の変更も「基準を動かす」**と資産自身が宣言している。**射程変更はこれに当たる**(推論)。
- 負例 fixture は exact-set(68 件)。条件 2 を触るなら
  `negative-fixtures.json` の `expected_error: "TB002"` 系 7 件の扱いを同時に決める。
- **コア領域の変更 → 人間の逐行確認必須**(ハーネス設計書 `:377`)。
  `.claude/core-areas.json` が `contracts/tenant_boundary/*` と検査器を tenant-isolation に登録済み。

### 8. 調査報告どうしの食い違いの裁定(原典で確認した)

| 論点 | 報告 | 原典での事実 |
| --- | --- | --- |
| `external_files` に検査器本体が入る資産 | 一方は「**全 7 資産**」 | **`base-allowlist.json` だけ**。他 6 資産は `"external_files": []`(各 `:19`)。**「全 7 資産」は誤り** |
| 未承認履歴を持つ資産 | 一方は「`base-allowlist.json` に 1 件」 | **7 資産すべて**が `"approved_by": "未承認(PR #72 のレビュー待ち)"` を持つ(各 `:61-64`)。**報告は過小** |
| 相対 import の解決 | 「`node.level` を一切見ない」 | **確認**。`node.level` を参照する行は検査器に **0 件** |

## 未解決・申し送り

1. **既存の未承認履歴 7 件の扱いは人間の判断が要る。**
   7.7-2-4(`docs/development/dev-harness-design-2026-08-07.md:596`)は承認者・承認日を要求するが、
   **履歴は追記のみで書き換え不可**。本 PR で基準を動かすなら、この既存記録をどうするかを決める必要がある。
   (「これが違反か」の判定は本調査の役割外 — 事実の指摘まで。)
2. **TB007 を fail-closed にした判断そのものを記録した文書は見つかっていない。**
   6-0 は二律背反の存在と「一般的な型解決器は作らない」までで、**未解決の由来をどちらへ倒すかは書いていない**。
3. **カードの「7 周目に収束」と「脅威モデルの明文化」を因果で結ぶ明文は無い**
   (周回表では 6-0 の反映は計画レビュー 4 周目、収束は実装後の敵対レビュー 7 周目で**系列が違う**)。
4. **カードの「DB 参照は domainmut の 3 ファイルのみ」は `backend/src` の話としては成り立たない。**
   3 パッケージに `psycopg` / `sqlalchemy` / `pitchlog.db` の参照は **0 件**。
   PostgreSQL を使うのは `tests/domain/mut/test_lang_operators.py` で、**検査器は `backend/src` しか走査しない**。
5. **`design.md` 6-0 は正本ではない。** 射程を動かすなら、
   **その線引きを正本へ上げるべきか**が論点になる(U-T1 の worklog `:162-163` が
   「脅威モデルの線引きは人間の判断事項として残す」としている)。

## 追補(2026-09-24・設計検討で追加した実測)

### 13. 相対 import は `backend/src` に 0 件

`ast.ImportFrom` で `level > 0` を全 85 ファイル走査 → **0 件**。3 パッケージにも 0 件。
→ **719 件のうち相対 import 由来は 0 件。**
調査 §2 の「検査器は相対 import を解決していない」は事実だが、
**これを誤検知の原因と見るのは誤り**だった(当初の計画はこの誤りの上に立っていた)。

なお相対 import は解決されなくても `None` にはならない。`:2277` が `f"{module}.{alias.name}"` を作るので
`from .x import Y` は `"x.Y"` という**誤った非 None シンボル**になり、`non_db` に落ちて**免除される側**へ倒れる。
→ **相対 import 未対応は誤検知の原因ではなく、見逃しの原因**である。

### 14. TB007 609 件の分岐別・構文形別

| 発火分岐 | 件数 |
| --- | --- |
| 未解決 callable 分岐(`:2960-2971`) | **607** |
| `dataclasses.replace` 専用分岐(`:2913-2926`) | **2**(`operators_display.py:469,479`) |

| `node.func` の構文形 | 件数 |
| --- | --- |
| `ast.Attribute` | **599** |
| `ast.Name` | 9 |
| `ast.Subscript` | 1 |

- **属性名が `TenantContext` のものは 0 件**
- **receiver の provenance は 609 件すべて `unknown`**
- 上位属性名: `get` 148 / `resolve` 52 / `group` 41 / `strip` 29 / `start` 24 / `as_posix` 23 …

### 15. 未解決の第一損失点(なぜ `unknown` に落ちたか)

| 原因 | 件数 |
| --- | --- |
| **stdlib / 3rd-party の戻り型が不明**(`re.compile` 92 / `pathlib.Path` 43 …) | **320** |
| 既知コンテナの要素型が不明(反復変数) | 124 |
| 添字結果(`x[i]`) | 48 |
| 組み込み型のメソッド戻り値 | 27 |
| 引数注釈が `object` / `Any` / ローカル別名 | 18 |
| 自パッケージの他モジュール関数の戻り型 | 17 |
| `/` 演算子結果・組み込み関数戻り値・合流不能ほか | 45 |
| **相対 import 由来** | **0** |

→ **他ファイル・外部ライブラリの戻り型が 61%**。**単一ファイル解析の原理的な外側**にある。

### 16. 免除機構は事実上機能していない

リポジトリ全体の未解決属性呼び出しは **813 件**。免除されたのは **14 件(1.7%)**
(`non_db` 10 / `db_result` 3 / `non_db_attribute` 1)。**799 件(98.3%)が拒否**。

### 17. ★ develop に既に 185 件の TB007 が潜んでいる

`develop` の `backend/src` を**全行スキャン**した結果(自分で実測):

```
TB007 185(authz 172 / api 9 / db 4)/ TB005 137 / TB002 26 / TB004 15
```

**差分方式(`scan_source_change`)が基準版の違反を相殺しているので見えていないだけ**であり、
**`authz` を触る PR が出た時点で表に出る。**
→ **新設パッケージだけの問題ではない。**

### 18. TB005 は名前駆動、TB007 だけが違う

`_check_db_call`(`:2772-2820`)は**属性名が inventory の member 名集合に入らない限り一切発火しない**。
`provenance` は「名前が一致した中でさらに `non_db` なら免除」という**二次的な絞り**。
**TB007 だけが名前ゲートを持たず `provenance` 単独で拒否している**(設計の一貫性の欠落)。

### 19. 凍結基準の受理単位(手続の順序に効く)

`contracts/tenant_boundary/base-allowlist.json:25-28`:

```json
"acceptance_unit": "single_review_acceptance",
"intermediate_commits_are_records": false,
```

→ **途中コミットで凍結射影検査が赤になるのは資産自身の宣言上許容**。**履歴は受理時点で 1 件にまとめる。**
→ **凍結更新を途中のステップに置いてはならない**(後続で検査器を 1 行でも触ると射影 SHA が合わなくなる)。

### 20. 既存テストの 1 本は書き換えが要る

`tests/test_check_tenant_boundary_bypass.py:1395` の
`test_unresolved_attribute_constructor_mutation_is_red` は `mod.TenantContext(tenant_id)` を使い、
**注釈を外す変異で赤になること**を主張している。
`attr == TenantContext` を provenance 非依存で拒否すると**注釈ありの基準版も赤**になり、
差分方式の相殺で `scan_source_change` が空になる。
→ **「両側 red」を主張する形へ書き換えが必要。**

### 21. 当初案(到達可能性レジーム)を捨てた理由

実測で 2 点。

1. **辺の張り方で結論が反転する。** 「`pkg` と `pkg.name` の両方へ張る」(広い側)にすると、
   `from pitchlog.domainmut import operators_lang` が**ルートパッケージ `pitchlog` への辺**を生む。
   `pitchlog/__init__.py` は **docstring 1 行**なのに **48 モジュールが触る hub** になり、
   **無向到達が 3 パッケージ 44 件中 43 件を引き戻す**(dotted 優先なら 0/44)。
2. **潜在 185 件が残る。** `authz` / `api` / `db` は anchor 側(レジーム A)なので消えない。
