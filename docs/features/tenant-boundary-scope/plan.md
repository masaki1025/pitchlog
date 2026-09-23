---
feature: tenant-boundary-scope
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e493b75e68781cb819ce706fa3252b1
branch: fix/tenant-boundary-scope
created: 2026-09-24
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 迂回検査 条件 5・条件 2 の射程を判定する(TSK-440)

## 1. 背景・目的

- Notion タスク: [TSK-440](https://app.notion.com/p/3e493b75e68781cb819ce706fa3252b1)
- 調査: [research.md](research.md)

`scripts/check_tenant_boundary_bypass.py`(U-T1 / TSK-390 が新設したテナント境界の迂回検査)が、
テナント境界と無関係な 3 パッケージ(`backend/src/pitchlog/{domaincheck,domaingen,domainmut}`)で
**719 件**を検出する(TB007 609 / TB002 110・38 ファイル)。
**2026-09-24 に `tenant-boundary-bypass` が必須チェックへ入った**(TSK-434)ため、
**誤検知が実害に変わった** — PR #74 は `harness` / `tenant-boundary-bypass` が red でマージできない。

**3 パッケージは develop に存在しない**(PR #74 が新設する)。本 worktree では再現しない。

### これは新設パッケージだけの問題ではない(実測)

`develop` の `backend/src` を**全行スキャン**すると、既に次が潜んでいる:

```
TB007 185(authz 172 / api 9 / db 4)/ TB005 137 / TB002 26 / TB004 15
```

差分方式が基準版の違反を相殺しているので**見えていないだけ**で、
**`authz` を触る PR が出た時点で表に出る。**

**関係する要件**: NFR-010(`docs/requirements/requirements-pitchlog-2026-07-22.md:846-850`)。
ただし `:850` の測定方法は**ランタイムの越境アクセステスト**であり、
**「静的な迂回検査を置け」「解決不能なら拒否せよ」は要件正本に存在しない**(research.md §4)。

## 2. スコープ

### やること

- **TB007 を TB005 と同じ「名前駆動」へ揃える**(4-1)
- **両建ての厳しくする側**: flow の訪問漏れを閉じる / 相対 import の絶対化 /
  `attr == TenantContext` を provenance 非依存で拒否(4-4)
- **条件 2 のパターン `generation` を契約名 `generation_no` へ絞る**(4-2)
- **通り抜けるものを全件明記**し、**落ちてはいけないものを負例で守る**
- `tenant-boundary-enforcement/design.md` 6-0 へ保証単位を明文化
- 凍結基準の受理(**最後のコミットで 1 回**)

### やらないこと

- **パス・パッケージ・モジュール単位の除外**(`design.md:457` `:463` `:470-471` が P0 で否決済み)
- **import グラフ / 到達可能性レジームの新設** — 当初案だったが 4-1 の理由で採らない
- **一般的な型推論器**(`design.md:454` が明示的に否定)。**他ファイルの戻り型は解決しない**
- **脅威モデルを正本へ上げること**(人間の判断 2026-09-24 = 上げない)
- **既存の未承認履歴 7 件の是正**(人間の判断 2026-09-24 = 触らない)
- **`conservative_member_names` を広げること** — inventory の member 名の非空部分集合しか
  許されず(`scripts/check_tenant_boundary_bypass.py:843-857`)、`strip` / `get` は**機構的に足せない**
- **残る約 7 件を消すために検査器をさらに緩めること**(人間の判断 = TSK-235 側で書き換える)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/design/sync-protocol.md` | **反映なし**(条件 2 の語彙確定は同期単位へ申し送る) | — |
| `docs/design/data-model.md` / `docs/adr/**` | **反映なし** | — |
| `docs/development/dev-harness-design-2026-08-07.md` | **反映なし**(6.3 の境界定義表は動かさない) | — |
| `docs/development/harness-evaluation.md` | 既存候補へ実測を追記(クローズ処理で判断) | PR レビュー |
| `docs/README.md` | 上記を反映した場合の最終更新日 | PR レビュー |

**`docs/features/tenant-boundary-enforcement/design.md` は正本ではない**(feature 設計書)。

## 4. 実装方針

**重さ分類 = コア領域**(ハーネス設計書 6.3 のテナント分離)。
`.claude/core-areas.json` が `contracts/tenant_boundary/*` と検査器を登録済み。
**敵対レビュー + 人間の逐行確認が必須**。

### 4-1. 条件 5(TB007)— 名前駆動へ揃える

#### 現行の欠陥(実測)

| 実測 | 値 |
| --- | --- |
| TB007 609 件の発火分岐 | 未解決 callable 分岐 `:2960-2971` が **607**、`dataclasses.replace` `:2913-2926` が **2** |
| `node.func` の構文形 | `ast.Attribute` **599** / `ast.Name` 9 / `ast.Subscript` 1 |
| **属性名が `TenantContext` のもの** | **0 件** |
| receiver の provenance | **609 件すべて `unknown`** |
| リポジトリ全体の未解決属性呼び出し | **813 件。免除されたのは 14 件(1.7%)** |
| 未解決の第一損失点 | **stdlib / 3rd-party の戻り型 320**・既知コンテナの要素型 124・添字結果 48・組み込みメソッド戻り値 27・`object`/`Any` 注釈 18・自パッケージ他モジュール 17・ほか。**他ファイル / 外部ライブラリ由来が 61%** |
| **相対 import** | **`backend/src` に 0 件**(誤検知の原因ではない) |

**現行規則は、検査対象の呼び出し自身の性質を一切見ていない。**
見ているのは「無関係な別の式(receiver の由来)に対して、不完全な解決器がたまたま成功したか」である。
**同一構文の 2 つの呼び出しが、別の場所の注釈の有無で赤/緑に分かれる。**
拒否 799 / 免除 14 という比が、これが保証ではなく雑音であることを示している。

#### 検査器自身が既に持っている正しい形

**TB005(DB API 側・`_check_db_call:2772-2820`)は名前駆動**である。
属性名が inventory の member 名集合に入らない限り**一切発火しない**。
`provenance` は「名前が一致した中でさらに `non_db` なら免除する」という**二次的な絞り**にしか使われない。

**TB007 だけが名前ゲートを持たず `provenance` 単独で拒否している。**
→ **TB007 を TB005 と同じ形へ揃える。**

#### 提案する規則(計画レビュー 1 周目 P0 の反映後)

条件 5 の `TenantContext` 生成経路の拒否を、次の 5 つに限定する。

| # | 条件 | 現行との差 |
| --- | --- | --- |
| (i) | 完全修飾名が `constructor_symbol` に解決され、モジュール allowlist 外 | **変更なし**(`:2972-2980`) |
| (ii) | 資産の `forbidden_construction_symbols` に一致 | **変更なし**(`:2865-2926`) |
| (iii) | **callable が属性式でない**(`f(...)` / `tbl[k](...)` / `expr()(...)` / `getattr(...)(...)`)かつ解決不能 | 現行の**部分集合** |
| (iv) | **末尾名が `constructor_symbol` の末尾名に一致**する呼び出し — **属性呼び出しでも裸の名前でも**、provenance に関係なく | **強化**(1 周目 P0) |
| (v) | **再輸出写像で `constructor_symbol` へ解決される呼び出し** | **新設**(1 周目 P0) |

**解決不能な属性呼び出しで、末尾名が `TenantContext` でも再輸出でもないものは拒否しない。**

#### 再輸出写像(1 周目 P0 の是正の中心)

**検査器は既に `_git_snapshot` で `backend/src` の全ファイルを読んでいる**(`:3976-3977`)。
同じスナップショットから「**モジュール → 輸出名 → 起源シンボル**」の写像を作り、
façade 再輸出を解決する。

```python
# pitchlog/repositories/__init__.py
from pitchlog.repositories.context import TenantContext
# 利用側 — 現在も提案 (iii)(iv) 単独でも素通りする
from pitchlog.repositories import TenantContext
def make(tenant_id): return TenantContext(tenant_id)
```

- **これは現行でも検出されていない既存の穴**であり、本ステップは**厳しくする側**である
- **他ファイルを読むが型推論ではない** — `ast.ImportFrom` の名前を追うだけで、
  不動点反復も値の型の推定も要らない。**再輸出の連鎖は深さ上限を置いて打ち切り、
  打ち切った先は fail-closed(解決不能として (iii) の扱い)**にする
- 別名クラス(`Alias = TenantContext`)と再輸出経由のサブクラス化も同じ写像で解決する

#### (iii) の既定値を変えない理由(1 周目 P0 で正当化を差し替えた)

**当初は「裸の名前呼び出し = 呼び出し側が選んだ意図的な間接化」と論じていたが、これは誤りだった。**
レビューの反証: `Regenerator`(`domaincheck/divergence.py:180`)と
`Clock = Callable[[], float]`(`domainmut/scope.py:242`)は**普通の型付き `Callable`** であり、
意図的な間接化ではない。逆に `registry[k].make_context(t)` は**明示的な間接化なのに属性呼び出しなので通る**。

**差し替えた根拠**: (iii) を fail-closed に保つのは**原理ではなく、負例が現に守っている範囲を落とさないため**である
(`C5_CONTEXT_UNKNOWN_FACTORY` が `factory(t)` を赤に保つ)。
**この非対称は恣意的であることを認め、保証外の宣言(下記)へそのまま書く。**

#### 宣言する保証単位(検査器 docstring・`design.md` 6-0・PR 本文の三箇所へ同文)

> **条件 5(`TenantContext` 生成経路)の保証単位は「構築に使われる名前が読み取れること」である。
> 型の解決可否は保証の条件にしない。**
> 赤にするもの: (i) 完全修飾名が構築シンボルに解決される / (ii) 資産が列挙する禁止構築シンボル /
> (iii) 名前が読み取れない callable(属性式でない呼び出し)/ (iv) **末尾名が構築シンボル末尾名に一致**(属性でも裸の名前でも)/
> (v) **再輸出写像で構築シンボルへ解決される**。
> **守らないもの(6-0 の「守らないもの」へ追加。人間承認の対象)**:
> **`registry[k].make_context(t)` のように、構築シンボル以外の属性名で、
> 再輸出写像でも解決できない callable を経由した構築。**
> **(iii) と (iv)(v) の非対称は原理ではなく、既存負例が守る範囲を落とさないための線である。**

### 4-2. 条件 2(TB002・110 件)— 広く保ち、別の軸で裁定する

#### 当初案は撤回した(計画レビュー 1 周目 P1)

当初は `(?:^|_)generation(?:_|$)` → `(?:^|_)generation_no(?:_|$)` へ絞る案だった。**実測で否定された。**

`develop` の TB002 **26 件中 14 件が `RecordingGeneration`**
(`backend/src/pitchlog/db/recording_rights/models.py:153` ほか)= **D4「記録権世代」の実モデルそのもの**で、
**絞り込むとこれが黙って消える**。実際の列名も **`generation`** であって `generation_no` ではない。
**FR-013「世代番号」から `_no` 形を推論したのは誤り**だった。

**これは台帳の既知失敗型**(`harness-evaluation.md:2520-2524`「母集団を狭めて本物と偽装の併存が通った」)。
**feature ブランチの 110 件が 0 になることだけを測り、現行の検査が何を捕まえているかを測っていなかった。**

#### 採る形 — 候補は広く、裁定は exact-set で fail-closed

台帳の対応案(`:2522`)「**候補は意図的に広く取り(部分一致でよい)、
そのうえで同一性を別の assertion で主張する**」の 2 段にする。

1. **候補**: `generation` を含む 7 パターンは**そのまま**。1 文字も狭めない
2. **裁定**: 候補に入った**完全修飾シンボル**のうち、**同期セマンティクスの契約ではないと裁定したもの**を
   資産へ **exact-set** で列挙する。**列挙に無いものは red**(fail-closed)

- **新しいシンボルが候補に入ったら、裁定されるまで red** — **狭める方向の部分一致ではない**
- 裁定の単位は**完全修飾シンボル**(`pitchlog.domaingen.core.GenerationError` など)。
  **パスやパッケージの接頭辞では裁定しない**(`design.md:470` のシンボル粒度に揃える)
- 裁定には**理由**を必須にする(「コード生成の `Generation` であり同期の世代ではない」)
- **負例で両側を固定する**: `RecordingGeneration` が**赤のまま**であること /
  裁定済みシンボルが緑であること / **裁定に無い新しい `*Generation` が赤**であること

#### 裸の名前の扱い(未解決)

実測の 110 件には**裸の局所変数 `generation` / `missing_generation` が 9 件**ある
(`domainmut/engine.py:262` ほか。`MutationGeneration` を受ける局所変数)。
**完全修飾シンボルが無いので exact-set で裁定できない。**
→ **実装時に決める**: 局所束縛の由来が裁定済みシンボルなら裁定を継承する / 裸の名前は候補から外す /
  当該変数名を product 側で変える。**どれも通り抜けを生むので、選んだ案を保証外の一覧へ書く。**

### 4-3. 通り抜けるもの(PR 本文へ全件そのまま載せる)

| # | 経路 | 状態 |
| --- | --- | --- |
| P1 | **別名で再輸出された生成関数の属性呼び出し**(`factories.make_context(t)` / `ctx_mod.build(t)`) | **本提案で新たに常時通る。** ただし**今日も receiver の型が解けていれば通っていた**(`:2946-2952` の無条件免除) |
| P2 | 他モジュールの関数が `TenantContext` を返す(`helper.build(t)`) | **今日も検出できていない**(unknown 経由で偶然赤になることがあるだけ)。単一ファイル解析の原理的外側 |
| P3 | `DictComp` の `iter` 内・添字代入先の内側での直接構築 | **今日は「未訪問 → `None` → 赤」で偶然拾えている。緩和すると本当に抜ける** → ステップ 1 で塞ぐ |
| P4 | 相対 import 経由の `TenantContext` | `_kind_for_type` / `dataclasses.replace` 判定に穴 → ステップ 2 で塞ぐ |
| P5 | `x.TenantContext(t)`(receiver が既知の非 DB 型) | **今日通っている**(`:2946-2952`)→ ステップ 3 で塞ぐ(**強化**) |
| P6 | `getattr(mod, "Tenant"+"Context")(t)` | func が `ast.Call` → 非属性 → (iii) で**赤のまま** |
| P7 | `TABLE["ctx"](t)` ディスパッチ辞書 | `ast.Subscript` → (iii) で**赤のまま** |
| P8 | 実行時 import / `importlib` / 実行時の型 | 6-0(`design.md:442-450`)が既に「守らない」と宣言済み |
| P9 | 人間レビューを通る悪意ある committer | 同上 |
| P10 | **既存 `authz` 172 件等の潜在 TB007 が静かに消える** | **誤検知の解消であり保証の縮小ではない**が、**件数を PR 本文へ書く** |
| P11 | 同期単位が D4 の欄を `generation` と命名した場合、条件 2 は検出しない | 条件 2 は単位分割の規律なので**セキュリティ上の後退ではない**。同期単位へ申し送る |

#### 自己申告の弱点

- **DoD の「検出 0 件」に届かない。** 本設計単独では **719 → 約 7 件**(TB007)。
  **人間の判断(2026-09-24)= 残りは TSK-235 側で 4〜7 箇所書き換える。** 582 箇所の改変とは桁が違う
- **P1 は本当に抜ける。** 今日は receiver の型が解けたときだけ抜けていたものが常時抜ける。
  **保証範囲の実質的な縮小**であり、両建て(4-4)が釣り合っているかは**定量化できない**
- **ステップ 3 は既存テストの主張を書き換える。** 射程を絞る PR でテストを書き換えるのは最も疑われる形。
  **書き換え後も両側 red を主張していることを示す以上の防御手段がない**
- **ステップ 1 は flow の意味論そのものを変える。** `unknown` → `non_db` へ倒れる値が増え、
  **TB005 を緩める向きに波及しうる**。全行センサスが唯一の検証手段で、**これは既存テストに無い新設ゲート**である
- **相対 import の解決は効果 0 件**(今日 0 件)。「使われていない機能を足した」と評価される余地がある

### 4-4. 落ちてはいけないもの(両建て)

`harness-evaluation.md:3343`「**射程を狭めただけでは通らないよう、宣言した保証範囲に対しては厳しくする両建てが要る**」/
`docs/worklog/2026-09-17-tenant-boundary-enforcement.md:240-247`
「**絞った結果として落ちてはいけないものを同時に名指しする**」。

#### (i) 名指し

| | 落ちてはいけないもの |
| --- | --- |
| D1 | **名前が読み取れない callable を呼ぶ形**からの構築(`factory(t)` / `tbl[k](t)` / `getattr(...)(t)`) |
| D2 | **属性名が `TenantContext` である呼び出し — receiver の型が既知であっても** |
| D3 | 資産が列挙する禁止構築シンボル 4 種 |
| D4 | 発行証跡 `_tenant_context_proof` / `_TENANT_CONTEXT_SECRET` の許可シンボル外参照 |
| D5 | **検査器の flow が一度も評価しない構文位置が存在しないこと**(訪問漏れによる偶然の検出に依存しない) |
| D6 | 相対 import で書かれた `TenantContext` が構築シンボルとして解決されること |
| D7 | **条件 1〜4 および TB005 / TB006 の検出件数が 1 件も減らないこと** |

#### (ii) 負例

| ID | 内容 | 守る |
| --- | --- | --- |
| `C5_CONTEXT_UNKNOWN_FACTORY` ほか既存 TB007 8 件 | **無改変** | D1 D3 D4 |
| **新** `C5_CONTEXT_ATTRIBUTE_NAME_ON_KNOWN_RECEIVER` | `def make(mod: ContextFactory, t): return mod.TenantContext(t)` — **注釈があっても赤** | D2 |
| **新** `C5_CONTEXT_IN_DICT_COMPREHENSION` | `{k: v for k, v in TenantContext(t).items()}` | D5 |
| **新** `C5_CONTEXT_IN_SUBSCRIPT_TARGET` | `store[TenantContext(t)] = 1` | D5 |
| **新** `C5_CONTEXT_RELATIVE_IMPORT` | `from .context import TenantContext` → `TenantContext(t)` | D6 |
| **新(機械)** センサス回帰(**exact-set**) | `path` / `line` / `scope` / `code` / `symbol` / `message` の**期待差分を exact-set で固定**する。件数一致では「真陽性が 1 件消え偽陽性が 1 件増えた」交換を検出できない(1 周目 P1) | D7 |
| **新(機械)** **CI の実経路**での回帰 | `scan_directory` ではなく **`scan_source_change` + 実コミット列 + `check_repository`**(`:3376` `:3964-3989`)。**全文走査と CI 経路を取り違えて「閉じた」と誤判定した前例がある**(`docs/worklog/2026-09-17-tenant-boundary-enforcement.md:144-148`) | D7 |
| **新(機械)** 訪問漏れ 0 の不変条件 | 任意ソースの全 `ast.Call` が `flow.callable_symbols` に登録済み | D5 |

**負例は資産に載せる**(単体テストで済ませると「exact-set の負例」という宣言力を失い、両建ての証拠として弱い)。
→ `negative-fixtures.json` の `fixture_set_revision` が動き、**2 つ目の資産の履歴 1 件が機械的に要求される**。
`tests/test_check_tenant_boundary_bypass.py:32` の `EXPECTED_NEGATIVE_IDS` も同時更新する。

### 4-5. 凍結基準の手続(★ 最後のコミットで 1 回)

**`base-allowlist.json:25-28` が `"acceptance_unit": "single_review_acceptance"` /
`"intermediate_commits_are_records": false` を宣言している**(実測で確認)。
→ **途中コミットで凍結射影検査が赤になるのは資産自身の宣言上許容**であり、
**履歴は受理時点で 1 件にまとめる。この根拠を PR 本文に書く。**

**逆に、凍結更新を途中のステップに置いてはならない** — 後続ステップで検査器を 1 行でも触ると
射影 SHA が合わなくなる(`external_files` に検査器本体が入っているため)。

| 資産 | 動く理由 | 要求 |
| --- | --- | --- |
| `base-allowlist.json` | `external_files` に検査器本体(`:19-21`)。1 行で動く | `contract_revision` 13→14、`current_identifiers` 更新、履歴**ちょうど 1 件** |
| `negative-fixtures.json` | 新規負例 4 件で `fixtures` が変わる | `fixture_set_revision` 5→6、同上 |
| 他 5 資産 | 変更しない | **履歴も識別値も触ってはならない**(`:678-680`) |

#### ★ `tenant-context-allowlist.json` の扱い(計画レビュー 1 周目 P1)

**同資産も `pass_fail_mapping` を movement trigger として宣言している**
(`contracts/tenant_boundary/tenant-context-allowlist.json:22-37`)。
本タスクは**条件 5 の合否写像を直接変える**ので、宣言上は基準が動く。

**しかし同資産の `external_files` は空**(各資産 `:19`)なので、**機械的には射影が動かない** —
これは **TSK-431 の既知欠陥 7B**(`docs/features/tenant-boundary-enforcement/plan.md:99-107`)である。

**人間の判断(2026-09-24)= 本タスクで裁定する**:
- **`tenant-context-allowlist.json` の履歴は足さない**(射影が動かないので足すと red — `:678-680`)
- **宣言と実装の不一致が本タスクの写像変更で初めて実害として表に出る**ことを **PR 本文へ明記**する
- **TSK-431 へ申し送る**(7B の優先度材料。別セッションへ通知済み)

`movement_policy.movement_triggers` に **`pass_fail_mapping`** が含まれる
→ **射程変更は「基準を動かす」に当たる**ので `movement_fact` に明記する。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**厳しくする側(1〜4)を緩和(5)より先に入れる。凍結更新(9)は必ず最後。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **センサスの土台**: `path`/`line`/`scope`/`code`/`symbol`/`message` の **exact-set** を取る回帰テストと、**CI の実経路(`scan_source_change` + 実コミット列 + `check_repository`)**を通す回帰テストを置く。**検査器のロジックは 1 行も変えない** | `[機械]` 現行 develop に対して exact-set が固定できる・CI 経路のテストが green `[手動]` 全文走査と CI 経路の両方を通していること |
| 2 | **flow の網羅性を閉じる**: `_expression` へ `ast.DictComp`、`_assign_target`(`:2138-2156`)が `Subscript`/`Attribute`/`Starred` 代入先の内側を評価 | `[機械]` 「全 `ast.Call` が `callable_symbols` に登録済み」green・新負例 `C5_CONTEXT_IN_DICT_COMPREHENSION` / `..._IN_SUBSCRIPT_TARGET` red・**ステップ 1 の exact-set が TB001〜TB006 について不変** |
| 3 | **相対 import の絶対化**: `level` と自モジュール名から絶対名を作るヘルパーを `:2277` / `:2508` / `:1685` で使う | `[機械]` 新負例 `C5_CONTEXT_RELATIVE_IMPORT` red・**exact-set が完全不変**(相対 import が 0 件なので差分が出たら実装が誤っている) |
| 4 | **(iv)(v) を入れる(強化)**: 末尾名一致を**属性でも裸の名前でも** provenance 非依存で拒否 + **再輸出写像**で構築シンボルへ解決される呼び出しを拒否。既存テスト `test_unresolved_attribute_constructor_mutation_is_red`(`:1395`)を**両側 red**へ書き換え(`scan_source` で個別に red を確認する形) | `[機械]` 新負例 `C5_CONTEXT_ATTRIBUTE_NAME_ON_KNOWN_RECEIVER` / `C5_CONTEXT_REEXPORT_FACADE` / `C5_CONTEXT_REEXPORT_SUBCLASS` red・**exact-set で TB007 が増える方向のみ** `[手動]` **逐行確認必須**。書き換え前後の主張の差を PR 本文へ |
| 5 | **既定値の反転(本丸)**: `:2960-2971` を 4-1 の (iii)(iv)(v) へ置換。検査器 docstring へ保証単位の宣言文 | `[機械]` 負例 exact-set が全 red・正例全 green・**統合 worktree で TB007 が約 7 件へ**・exact-set で TB001〜TB006 不変 `[手動]` 宣言文が 3 箇所で同文 |
| 6 | **条件 2 の裁定機構**: 候補パターンは変えず、**裁定済みシンボルの exact-set 資産**(理由必須)を新設し、未登録は red。裸の名前の扱いを決めて保証外へ明記 | `[機械]` **`RecordingGeneration` 14 件が赤のまま**・裁定済みシンボルが緑・**裁定に無い新しい `*Generation` が赤**・統合 worktree で TB002 が 0 件 |
| 7 | **残る約 7 件の裁定を申し送りへ**: 位置・形・性質つきで全件列挙し、TSK-235 側での書き換え案を worklog と PR 本文へ | `[手動]` 7 件全件が列挙され、**真の脆弱性でないことの根拠**が付いている |
| 8 | **文書**: `tenant-boundary-enforcement/design.md` 6-0 へ保証単位と「守らないもの」を追補。**`tenant-context-allowlist.json` の 7B 不一致**を PR 本文へ明記し TSK-431 へ申し送る。**Notion の DoD を正式更新** | `[手動]` 6-0 の既存の線引きと矛盾しない・DoD の変更が Notion に反映されている |
| 9 | **凍結基準の受理(最後)**: `base-allowlist.json` と `negative-fixtures.json` の識別値と履歴 1 件ずつ。射影 SHA は算出値を貼る | `[機械]` `check_tenant_boundary_bypass.py` exit 0・`test_every_frozen_baseline_asset_has_a_valid_chained_history` / `test_checker_pass_fail_mapping_change_requires_revision_and_history` green `[手動]` **コア領域の逐行確認**(設計書 `:377`) |

**効果測定の環境**: TSK-235 の worktree で**旧スクリプトをそのまま実行しても新写像は検証できない**。
**統合用の一時 worktree**(現行 contract + 現行 checker + TSK-235 の `backend/src`)を作って測る。手順を worklog へ残す。

## 5. DoD(受け入れ基準)

**Notion の DoD「検出 0 件」は本計画で正式に更新する**(人間の判断 2026-09-24):
**TSK-440 で約 7 件まで下げ、TSK-235 側の書き換えで 0 件にする**。依存関係を Notion へ明記する。

- [ ] 条件 5 の保証単位が**宣言文として 3 箇所へ同文**で置かれている
- [ ] **再輸出・別名・再輸出経由のサブクラス**が負例で赤になる(1 周目 P0 の是正)
- [ ] 統合 worktree で **TB007 約 7 件 / TB002 0 件**。**残りは TSK-235 側の書き換え申し送りが出ている**
- [ ] **通り抜けるもの**が PR 本文に全件明記されている(**(iii) と (iv)(v) の非対称が原理でないことを含む**)
- [ ] **落ちてはいけないもの D1〜D7** が負例で守られている
- [ ] **exact-set のセンサス**(`path`/`line`/`scope`/`code`/`symbol`/`message`)で TB001〜TB006 が不変。
      **CI の実経路(`scan_source_change` + `check_repository`)でも確認している**
- [ ] **条件 2 は候補を狭めていない**。`RecordingGeneration` が赤のまま
- [ ] **`tenant-context-allowlist.json` の 7B 不一致**が PR 本文に明記され TSK-431 へ申し送られている
- [ ] `contract_revision` / `fixture_set_revision` と sha256 inventory が整合している
- [ ] pytest / ruff / ty green
- [ ] **コア領域(テナント分離)** → sol xhigh・敵対レビュー + **人間の逐行確認**

## 6. テスト計画

NFR-019 の種別では**単体**(検査器自身のテスト)。ランタイムの越境テストは本タスクの射程外。

| 追加するもの | 種別 | 置き場 |
| --- | --- | --- |
| **訪問漏れ 0 の不変条件**(全 `ast.Call` が `callable_symbols` に登録済み) | 単体 | `tests/test_check_tenant_boundary_bypass.py` |
| **全行センサス回帰**(TB005 137 / TB002 26 / TB004 15) | 単体 | 同上 |
| 相対 import 絶対化の単体テスト(`__init__.py` を含む) | 単体 | 同上 |
| `C5_CONTEXT_ATTRIBUTE_NAME_ON_KNOWN_RECEIVER` / `..._IN_DICT_COMPREHENSION` / `..._IN_SUBSCRIPT_TARGET` / `..._RELATIVE_IMPORT` | 負例 fixture | `tests/fixtures/tenant_boundary/negative/` + `negative-fixtures.json` |
| `C2_GENERATION_IMPORT` の `generation_no` 化 | 負例 fixture | 同上 |
| `test_unresolved_attribute_constructor_mutation_is_red` の**両側 red 化** | 単体(書き換え) | `tests/test_check_tenant_boundary_bypass.py:1395` |

**既存 68 負例・正例 5 件は exact-set で守られている**ので、増減はすべて資産と同時更新する。
`EXPECTED_NEGATIVE_IDS`(`:32`)も同時に更新する。
