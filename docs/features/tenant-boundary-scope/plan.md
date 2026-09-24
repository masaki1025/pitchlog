---
feature: tenant-boundary-scope
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-24・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e493b75e68781cb819ce706fa3252b1
branch: fix/tenant-boundary-scope
created: 2026-09-24
計画レビュー周回: 7        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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

**差分方式が相殺しているので見えていない**が、**「ファイルを触ると全部出る」わけでもない**
(`scan_source_change` `:3452-3485` を読んで確認した):

- 相殺の条件は、head 側の違反行が **SequenceMatcher の一致ブロックを通じて基準版の連続した行へ写る**こと、
  かつ識別値 **`(scope, line, end_line, condition, code, symbol, message)`** が一致すること
- → **既存の違反は、その行と所属シンボル名が変わらない限り相殺される**
- → **当該行を編集する・囲む関数名を変える・コードを移動すると、既存分も「増えた」として出る**

**したがって「`authz` を触ると 172 件が一度に出る」は誤りで、「その行を動かした分だけ出る」が正しい。**

**関係する要件**: NFR-010(`docs/requirements/requirements-pitchlog-2026-07-22.md:846-850`)。
ただし `:850` の測定方法は**ランタイムの越境アクセステスト**であり、
**「静的な迂回検査を置け」「解決不能なら拒否せよ」は要件正本に存在しない**(research.md §4)。

## 2. スコープ

### やること

- **TB007 を TB005 と同じ「名前駆動」へ揃える**(4-1)
- **両建ての厳しくする側**: 検査 visitor の訪問漏れを閉じる(**現行のバグ是正**)/ 相対 import の絶対化 /
  末尾名一致を provenance 非依存で拒否 / 再輸出写像(4-4)
- **保証範囲の正式な縮小**: `design.md` 6-0 と 1-1 を改訂し、**コア paths を `api/**`・`services/**` へ広げて
  人間の逐行確認を実際に発火させる**(2 周目 P0-3)
- **条件 2 は候補を 1 文字も狭めず、裁定済みシンボルの exact-set で裁定する**(4-2)
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
| (v) | **再輸出写像の可能な起源集合に `constructor_symbol` が含まれる、または内部再輸出の解決が `unresolved`**(深さ上限 / star / 条件分岐 / 循環 / 自己参照 / 欠落した `pitchlog.*` / 未対応の静的代入) | **新設**(1 周目 P0・7 周目 P1-1 で `unresolved` を明記) |

**解決不能な属性呼び出しで、末尾名が `TenantContext` でも再輸出でもないものは拒否しない。**

#### 再輸出写像((v))と、その保証の限界(2 周目 P0-1 / P0-2 の反映)

**検査器は既に `_git_snapshot` で baseline と head の全ファイルを別々に読んでいる**(`:3976-3977`)。
**それぞれのスナップショットから別々に**「**モジュール → 輸出名 → 可能な起源の集合**」を作る。

**★ baseline 解析には baseline の写像、head 解析には head の写像を渡す**(3 周目 P0-4)。
**両方に head の写像を渡すと、baseline 側も赤になり `scan_source_change` が相殺して見逃す。**
実害の形: **façade を安全型から `TenantContext` へ変え、consumer は無関係な別行だけ変更する**
(consumer は走査対象なので、保証外にした「consumer 無変更」とは別のケース。通常の複合リファクタリング)。
→ **実コミット列でこの遷移が TB007 になることを固定する。**
→ あわせて **「façade だけ変更・consumer 無変更は保証外で green」も固定**して境界を明瞭にする。

**起源は単一値ではなく「可能な起源集合 + unresolved 状態」で持つ**(2 周目 P0-2):

- **可能な起源に `constructor_symbol` が 1 つでもあれば赤**
- **`unresolved == true` なら原因を問わず、裸の名前でも属性呼び出しでも赤**(3 周目 P1-1)。
  unresolved になる原因: **深さ上限超過 / star import / 条件分岐 / 循環再輸出(循環訪問は unresolved)/
  自己参照 / 欠落モジュール / 未対応の静的代入**。
  (「(iii) 扱い」にすると属性呼び出しが fail-closed にならないため、原因別の扱いにしない)
- **完全修飾された絶対モジュールをキーにする**ので、**別モジュールの無関係な同名 `Context` は閉じられる**
  (**単体テストで固定する** — 正例 fixture は `allowed_symbols` と exact-set で縛られていて追加できない)
- **★ 「欠落モジュール」の境界を定める**(5 周目 P1-3):
  - **外部モジュール(stdlib / third-party)= 写像に無いのが正常**。**終端起源として扱い、unresolved にしない**
    (しないと通常の import が大量に red になる)
  - **`pitchlog.*` のモジュールが写像に無い = 欠落**。**unresolved = red**
  - **両側にテストを置く**(外部 import が緑 / 欠落した `pitchlog.*` が赤)
- `import module` + `Context = module.TenantContext` のような **`ImportFrom` 以外の静的再輸出**も写像へ入れる
- `importlib.import_module` は**既に TB005 が拒否する**(`:3022`)ので (v) の射程外

**負例は (iv) で捕まらない名前で作る**(2 周目 P0-1)。
`TenantContext(t)` は末尾名一致だけで赤になるので **(v) の実効性を証明しない**。
`from facade import Context` → `Context(t)` の形にする。

#### ★ (v) が塞がない範囲(保証外として正式に宣言する — 2 周目 P0-1)

**CI の検査母集団は「変更ファイル」だけ**である(`:3898` `:3976`)。したがって:

```python
# HEAD で facade.py だけを変更
from pitchlog.repositories.context import TenantContext as Context
# consumer.py は無変更 → 走査されない
from facade import Context
context = Context(tenant_id)
```

**再輸出元だけを変更し、利用側を変更しない漂流は、利用側が走査されないので検出できない。**

- **これは本タスクが作る穴ではなく、差分方式が元から持つ穴**である
- **逆依存を母集団へ足す**ことは原理的には可能だが、**「変更ファイルだけを見る」という
  検査器の基本設計を変える**ことになり、本タスクの射程を大きく超える
- → **保証外として `design.md` 6-0 へ明記し、人間の逐行確認へ委ねる**(下記 4-6)

#### (iii) の既定値を変えない理由(1 周目 P0 で正当化を差し替えた)

**当初は「裸の名前呼び出し = 呼び出し側が選んだ意図的な間接化」と論じていたが、これは誤りだった。**
レビューの反証: `Regenerator`(`domaincheck/divergence.py:180`)と
`Clock = Callable[[], float]`(`domainmut/scope.py:242`)は**普通の型付き `Callable`** であり、
意図的な間接化ではない。逆に `registry[k].make_context(t)` は**明示的な間接化なのに属性呼び出しなので通る**。

**差し替えた根拠**: (iii) を fail-closed に保つのは**原理ではなく、負例が現に守っている範囲を落とさないため**である
(`C5_CONTEXT_UNKNOWN_FACTORY` が `factory(t)` を赤に保つ)。
**この非対称は恣意的であることを認め、保証外の宣言(下記)へそのまま書く。**

#### 宣言する保証単位(**共通の逐語文を 1 つ固定し、4 箇所へそのまま置く**)

**★ 5 周目 P1-1 / 6 周目 P1-2 の是正**: 従来は 6-0 用・1-1 用に別々の完成文を書いていたが、
**それでは「同文」にならない**。**共通逐語の対象は下の引用ブロック全体**((i)〜(v) と「守らないもの」を含む)。
**これを逐語で 4 箇所(検査器 docstring / `design.md` 6-0 /
同 1-1(`:58`)/ PR 本文)へ置く**。各所の文脈説明は**この 1 文の前後に足す**(1 文自体は変えない)。
**4 箇所の突合はステップ 10(文書を書くステップ)で行う** — ステップ 6 は docstring しか触らないので、
そこで「4 箇所で同文」を合格条件にすると実行順として成立しない。

> **条件 5(`TenantContext` 生成経路)の保証単位は「構築に使われる名前が、
> 変更ファイル内で読み取れること」である。型の解決可否は保証の条件にしない。**
> 赤にするもの: (i) 完全修飾名が構築シンボルに解決される / (ii) 資産が列挙する禁止構築シンボル /
> (iii) 名前が読み取れない callable(属性式でない呼び出し)/ (iv) **末尾名が構築シンボル末尾名に一致**
> (属性でも裸の名前でも)/ (v) **再輸出写像の可能な起源集合に構築シンボルが含まれる、
> または内部再輸出の解決が `unresolved`**(深さ上限 / star / 条件分岐 / 循環 / 自己参照 /
> 欠落した `pitchlog.*` モジュール / 未対応の静的代入)。
>
> **守らないもの(正式に縮小する — 人間承認の対象)**:
> 1. **再輸出元だけを変更し、利用側を変更しない漂流**。CI の母集団が変更ファイルに限られるため
> 2. **`registry[k].make_context(t)` のように、構築シンボル以外の属性名で、
>    再輸出写像でも解決できない callable を経由した構築**
> 3. **(iii) と (iv)(v) の非対称は原理ではなく、既存負例が守る範囲を落とさないための線である**

### 4-6. 保証縮小の代償を実在させる(2 周目 P0-3)

**「人間の逐行確認へ委ねる」は、逐行確認が実際に発火しなければ空手形である。**

- 逐行確認はコア paths に該当した PR で要求される(`dev-harness-design-2026-08-07.md:383`)
- **現在の tenant-isolation paths は `authz/*`・`db`・`repositories/*`・検査器・資産で、
  `backend/src/pitchlog/api/**` や services を含まない**(`.claude/core-areas.json:303`)
- → **API 層で普通の factory / DI リファクタリングとして `issuer.make_context(t)` を足すと、
  静的検査は green・逐行確認も発火しない**

**したがって本タスクで `.claude/core-areas.json` の tenant-isolation へ
`backend/src/pitchlog/api/**` と `backend/src/pitchlog/services/**` の両方を追加する。**

**`services/**` を落としてはいけない**(3 周目 P0-1)— 今後の製品実装先に `services/` が明記されている
(`docs/features/product-impl-unit-split/plan.md:467`)。`services/context_issuer.py` で
`issuer.make_context(t)` を足す形は**まさに保証外にした経路**であり、ここが発火しないと代償が空手形になる。

**ただし `api/**` + `services/**` でも一般化はできない**(`domain/**`・`sync/**` でも同型は書ける)。
**より形骸化しにくい形はレビュアの提案**である:
**`TenantContext` の発行と registry 登録を専用モジュールへ封じ、その境界だけをコアにする。**
本タスクでは**製品コードの構造を変える射程が無い**ので **paths 追加に留め、専用モジュール化は申し送る**。

**core guard が機械的に保証するのは「該当パスがあれば PR 本文のチェック済み文字列を要求する」まで**
(`scripts/core_guard.py:200` `:274`)。**実際の逐行確認は運用統制**である。これも明記する。

- **これは 6.3-⑤「paths の追加・削除・縮小は敵対レビュー + 人間承認の対象」に当たる**
- **`design.md` 6-0 の既存 bullet を「置換」する**(3 周目 P0-2)。
  **置換後の本体は上記の共通逐語ブロック((i)〜(v) と「守らないもの」を含む引用全体)そのもの**とし、
  下の 1 文は**その前に置く文脈説明**である(6 周目 P1-2):

  > **守るもの(置換後)**: **変更ファイル内で構築に使われる名前を読み取れる範囲**において、
  > **宣言済みの条件 (i)〜(v) が対象とする構築経路**について、不注意・知識の欠落・
  > リファクタリングによる漂流を止めること。**名前を読み取れない範囲は「守らないもの」に従う。**

- **`design.md:58`(1-1)も同じ共通逐語ブロックで置換する**。下の 1 文は**その後に置く文脈説明**である:

  > **allowlist 外からの構築は、条件 (i)〜(v) が名前を読み取れる範囲において検査で red になる。**
  > **読み取れない範囲のうち `backend/src/pitchlog/{api,services}/**` は人間の逐行確認が担う。**
  > **それ以外の層(`domain/**`・`sync/**` ほか)は、機械検査でも逐行確認でも覆われない残余リスクである。**

#### ★ 残余リスク(人間承認の対象として明示する — 4 周目 P0-1)

**`api/**` と `services/**` をコア paths へ足しても、一般化はできない。**
将来の実装先には `sync/` と `domain/` も含まれる(`product-impl-unit-split/plan.md:467`)。

> **`backend/src/pitchlog/{domain,sync}/**` で、構築シンボル以外の属性名で、
> 再輸出写像でも解決できない callable を経由して `TenantContext` を構築する経路は、
> 機械検査でも人間の逐行確認でも覆われない。**

**この PR は「防御が閉じた」ではなく「この残余リスクを明示的に受容する」案件として人間承認へ出す。**
**受容されない場合は、`TenantContext` の発行と registry 登録を専用モジュールへ封じ込める設計へ戻す**
(下記の申し送り)。
- **代償**: **人間の逐行確認が必要な PR が増える。** これは保証を縮めた分の対価であり、
  **縮めるだけで代償を払わない形にはしない**(`harness-evaluation.md:3343` の両建て)
- **注意**: `core-areas.json` と `scripts/core_guard.py` / `tests/test_core_guard.py` を
  **同一コミットで変更しない**(PR #74 が持ち込む `verify_area_path_baseline` の制約。
  develop に入る順序が未定なので**どちらでも通る形**にする)

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

#### 裁定の単位と、裸の名前の扱い(実測で決着)

110 件を裁定できる単位で分類した(実測):

| 形 | 件数 | 扱い |
| --- | --- | --- |
| **完全修飾シンボル**(`pitchlog.domaingen.core.GenerationError` ほか) | **94** | **exact-set で裁定**(理由必須) |
| **裸のクラス名**(`MutationGeneration` / `TracedGeneration` ほか) | **9** | 同モジュール内の定義へ解決できるので**同じく exact-set で裁定** |
| **裸の局所変数**(`generation` / `missing_generation` / `generation.unsupported`) | **7** | **裁定しない** — 下記 |

**裸の局所変数 7 件は TSK-235 側で変数名を変える**(`domainmut/engine.py:262` ほか。
`MutationGeneration` を受ける局所変数が `generation` という名前になっている)。

- **理由**: 完全修飾シンボルが無いので exact-set で裁定できない。
  「裸の名前を候補から外す」形にすると**候補を狭めることになり、1 周目 P1 と同じ失敗型**に戻る
- **残る TB007 約 7 件と同じ扱い**(人間の判断 2026-09-24 = TSK-235 側で書き換える)
- **コストは小さい**(7 箇所の変数名)。**候補集合には一切触らない**

#### (iv) を裸の名前へ広げることの副作用(実測で確認)

`backend/src` に `TenantContext` という名前のクラスは **`repositories/context.py:19` の 1 つだけ**
(ほかは正例 fixture の 1 件)。**同名の無関係な型は存在しないので、巻き添えは無い。**

#### 再輸出の現況(実測)

- `backend/src/pitchlog/repositories/__init__.py` は**docstring 1 行のみで再輸出なし**
  → **P0 のシナリオは「これから漂流で足される」仮定**である(現時点の実害ではない)
- `backend/src` に **star import(`from X import *`)は 0 件**
- `__all__` を持つのは `repositories/{base,tokens,cache_invalidation}.py` の 3 件
  → 再輸出写像は `__all__` を**名前の生成源として扱わない**(`__all__` は `import *` の対象を絞るだけで、
  名前を作らない)。**ただし star import が将来入ったら写像が取り逃がすので、
  star import の存在自体を fail-closed にする**(検出したらそのモジュールを解決不能扱い)

### 4-3. 通り抜けるもの(PR 本文へ全件そのまま載せる)

| # | 経路 | 状態 |
| --- | --- | --- |
| P1 | **別名で再輸出された生成関数の属性呼び出し**(`factories.make_context(t)` / `ctx_mod.build(t)`) | **本提案で新たに常時通る。** ただし**今日も receiver の型が解けていれば通っていた**(`:2946-2952` の無条件免除) |
| P2 | 他モジュールの関数が `TenantContext` を返す(`helper.build(t)`) | **今日も検出できていない**(unknown 経由で偶然赤になることがあるだけ)。単一ファイル解析の原理的外側 |
| P3 | `DictComp` の `iter` 内・添字代入先の内側での直接構築 | **今日は「未訪問 → `None` → 赤」で偶然拾えている。緩和すると本当に抜ける** → **ステップ 3** で塞ぐ |
| P4 | 相対 import 経由の `TenantContext` | `_kind_for_type` / `dataclasses.replace` 判定に穴 → **ステップ 4** で塞ぐ |
| P5 | `x.TenantContext(t)`(receiver が既知の非 DB 型) | **今日通っている**(`:2946-2952`)→ **ステップ 5** で塞ぐ(**強化**) |
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
- **ステップ 5 は既存テストの主張を書き換える。** 射程を絞る PR でテストを書き換えるのは最も疑われる形。
  **書き換え後も両側 red を主張していることを示す以上の防御手段がない**
- **ステップ 3 は flow の意味論そのものを変える。** `unknown` → `non_db` へ倒れる値が増え、
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
| D5 | **全 `ast.Call` が flow に登録され、かつ実際に検査判定を通ったこと**。`_visit_function`(`:3222`)が **デフォルト引数・注釈・戻り注釈を訪問していない**ため、`def run(context=TenantContext(...))` が**現行で 0 件 → 是正後 TB007**(実測)。**develop への波及は 0 件**(実測)。class keyword・match guard・`TryStar` も含めて全構文を対象にする(2 周目 P0-4) |
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
| **新(機械)** センサス回帰 | **`path` / `line` / `end_line` / `scope` / `code` / `symbol` / `message` の exact-set**。**永続 golden を置かず、旧 checker と新 checker を同一ソースへ当てて差分を取る**ので、**行番号は旧・新で同じ**であり「無関係な行移動でずれる」問題は起きない(3 周目 P1-2 — 2 周目に `line` を外した理由は同一ソース比較と矛盾していた)。**未管理の凍結基準にもならない** | D7 |
| **新(機械)** **CI の実経路**での回帰 | `scan_directory` ではなく **`scan_source_change` + 実コミット列 + `check_repository`**(`:3376` `:3964-3989`)。**全文走査と CI 経路を取り違えて「閉じた」と誤判定した前例がある**(`docs/worklog/2026-09-17-tenant-boundary-enforcement.md:144-148`) | D7 |
| **新(機械)** **検査器の不変条件**(3 集合一致・`ContractError` → exit 2) | 各構文位置について **flow 登録**と **scanner 判定**の両方を記録し、**判定済み `ast.Call` の ID を突き合わせる**(3 周目 P1-3)。現行の実測値: | D5 |

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
| `negative-fixtures.json` | **新規負例 22 件**で `fixtures` が変わる(内訳: 再輸出系 9 = façade / サブクラス / 深さ上限 / star / 循環 / 自己参照 / 条件分岐 / 欠落モジュール / 未対応の静的代入、PEP 695 型境界 2、訪問位置 9 = デフォルト引数 / `DictComp` / 添字代入先 / 相対 import / lambda default / annotated assignment / class base / except handler type / 終端文の後、ほか 2 = 属性名一致 / 許可シンボルのデフォルト捕捉) | `fixture_set_revision` 5→6、同上 |
| 他 5 資産 | 変更しない | **履歴も識別値も触ってはならない**(`:678-680`) |

#### ★ マージ順による凍結対象の変化(TSK-431 との調整・2026-09-24)

**TSK-431 の 7B は、`scripts/check_tenant_boundary_bypass.py` を 7 資産すべての
`external_files` へ入れる**(現在は `base-allowlist.json` の 1 件だけ)。
さらに **新規 `scripts/frozen_history.py` と `.github/workflows/ci.yml` も 7 資産の `external_files`** へ入る。

| マージ順 | 本タスクの凍結手続 |
| --- | --- |
| **TSK-440 が先**(推奨) | **2 資産のまま**(`base-allowlist.json` / `negative-fixtures.json`)。431 側が 440 後の検査器を凍結するだけ |
| TSK-431 が先 | **7 資産すべての識別値更新と履歴記録**が要る |

**別セッション(TSK-431 担当)から「440 を先に出して構わない」と回答を得ている**
(同タスクは人間承認待ちで、承認後も draft PR から始まる)。
**順序は固定しない**が、**先に出せるなら本タスクを先に出す**。
`added` は merge-base 相対であり `strict_required_status_checks_policy: true` なので、
**どちらの順でも後発がリベースを強制されるだけ**で、機構上の問題は起きない。

**条件 2 の裁定 exact-set は新資産を作らず `base-allowlist.json` へ内包する**(2 周目 P1-2)。
新ファイルにすると **8 資産目として `FROZEN_BASELINE_ASSETS` の exact-set 更新と初回履歴**が要り
(`tests/test_check_tenant_boundary_bypass.py:323`)、受理対象がもう 1 つ増えるため。

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

**厳しくする側(1〜5)を緩和(6)より先に入れる。凍結更新(ステップ 12)は必ず最後。**

| # | ステップ(何を作るか) | 合格条件 |
| --- | --- | --- |
| 1 | **センサスの土台**: **`path`/`line`/`end_line`/`scope`/`code`/`symbol`/`message` の exact-set** で比較する回帰と、**CI の実経路(`scan_source_change` + 実コミット列 + `check_repository`)**の回帰を置く。**永続 golden は置かず、旧 checker と新 checker を同一ソースへ当てて差分を取る**。**検査器のロジックは 1 行も変えない** | `[機械]` 現行 develop で差分 0・CI 経路のテスト green |
| 2 | **検査 visitor の訪問漏れを閉じる(現行バグの是正)**: `_visit_function`(`:3205-3231`)が **`node.args` のデフォルト値・kw デフォルト・引数注釈と `node.returns`** を訪問する(現行は `decorator_list` と `body` のみ)。**★ decorator・defaults・annotations・returns は `function_stack` の push 前に訪問し、body だけを push 後に訪問する**(3 周目 P0-3。デフォルト値は関数本体ではなく**定義が置かれた外側のスコープ**。push 後に訪問すると許可シンボル免除(`:3003`)が漏れ、`def _tenant_context_proof(x=_TENANT_CONTEXT_SECRET)` が **0 件**になる)。class keyword・**関数とクラスの `type_params`**(PEP 695)も scanner 側の訪問対象へ | `[機械]` 負例 `C5_CONTEXT_IN_DEFAULT_ARG` が red(**実測: 現行 0 件 → 是正後 TB007**)・**負例 `C5_SECRET_IN_DEFAULT_CAPTURE`(許可シンボルのデフォルト捕捉)で訪問順序の差を検出**(**不変条件の green 判定はステップ 3 末尾で行う** — 現 HEAD で既に差があり、`DictComp` 等の flow 修正を入れるまで green にならないため)

**実測(レビュアと自分で独立に一致)**: `backend/src` 全体で **実 Call 2,261 / flow 登録 2,249 = 差 12 件**。
内訳は **`pitchlog/authz/catalog.py` 10 / `pitchlog/authz/ddl.py` 1 /
`pitchlog/db/sync_protocol/event_kinds.py` 1**(自分の計測で特定)。
→ **ステップ 3 の合格条件は「差 12 → 0」**であり、**この 3 ファイルが実際の検証対象**になる。・**実測で develop への波及は増分 0 件・減分 0 件**(363 件のまま)なので、**センサスが完全不変であることを合格条件にする** |
| 3 | **flow の網羅性を閉じ、不変条件を green にする**: `_expression` へ `ast.DictComp`、`_assign_target`(`:2138-2156`)が `Subscript`/`Attribute`/`Starred` 代入先の内側を評価、**lambda default・annotated assignment・class base・`except`/`except*` の handler type・終端文の後**(`:2484`)、**match guard**(`:2444`)、**`TryStar`**(`:2411`)、**関数・クラスの `type_params`**(PEP 695)。**5 周目の探針 5 件に対応する flow 修正はここで入れる** | `[機械]` **不変条件が green**(3 集合一致)・負例 `C5_CONTEXT_IN_DICT_COMPREHENSION` / `..._IN_SUBSCRIPT_TARGET` / `..._IN_LAMBDA_DEFAULT` / `..._IN_ANNOTATED_ASSIGNMENT` / `..._IN_CLASS_BASE` / `..._IN_EXCEPTION_HANDLER_TYPE` / `..._AFTER_TERMINATOR` red・**センサスが TB001〜TB006 について不変** |
| 4 | **相対 import の絶対化**: `level` と自モジュール名から絶対名を作るヘルパーを `:2277` / `:2508` / `:1685` で使う | `[機械]` 負例 `C5_CONTEXT_RELATIVE_IMPORT` red・**センサス完全不変**(相対 import が 0 件なので差分が出たら実装が誤り) |
| 5 | **(iv)(v) を入れる(強化)**: 末尾名一致を属性でも裸の名前でも provenance 非依存で拒否 + **再輸出写像を「可能な起源集合 + unresolved」で持つ**(集合に構築シンボルがあれば赤 / 深さ上限・star・曖昧分岐は裸名でも属性でも赤)。既存テスト `:1395` を**両側 red**へ書き換え | `[機械]` 負例 `C5_CONTEXT_REEXPORT_FACADE`(**`Context(t)` — (iv) で捕まらない名前**)/ `..._REEXPORT_SUBCLASS` / `..._REEXPORT_DEPTH_LIMIT` / `..._REEXPORT_STAR` / `..._ATTRIBUTE_NAME_ON_KNOWN_RECEIVER` が red・**センサスで TB007 が増える方向のみ** `[手動]` **逐行確認必須** |
| 6 | **既定値の反転(本丸)**: `:2960-2971` を 4-1 の (iii)(iv)(v) へ置換。検査器 docstring へ保証単位の宣言文 | `[機械]` 負例 exact-set が全 red・正例全 green・**統合 worktree で TB007 が約 7 件へ** `[手動]` docstring の文が**共通逐語文と一致**していること(**4 箇所の突合はステップ 10**) |
| 7 | **条件 2 の裁定機構**: 候補パターンは**変えず**、**裁定済みシンボルの exact-set を `base-allowlist.json` へ内包**(理由必須)。未登録は red。**裸の局所変数 7 件は裁定せず TSK-235 側で改名**(候補集合には触らない) | `[機械]` **`RecordingGeneration` 14 件が赤のまま**・裁定済み(完全修飾 94 + 裸のクラス名 9)が緑・**裁定に無い新しい `*Generation` が赤**。**統合 worktree の TB002 = 0 は TSK-235 の改名後に成立する**ので、本タスクでは **7 件が残ることを合格条件にする** |
| 8 | **コア paths の拡大(第 1 段)**: `tests/test_core_guard.py` の area paths exact-set(`:1566`)へ `backend/src/pitchlog/api/**` と `backend/src/pitchlog/services/**` を**先に**足す。**`core-areas.json` はまだ触らない** | `[機械]` テストが**まだ red**(実体が無いため)。**この 1 コミットは意図的に red で、次のステップで green になる**ことを PR 本文へ明記 |
| 9 | **コア paths の拡大(第 2 段)**: `.claude/core-areas.json` の tenant-isolation へ **`api/**` と `services/**` の両方**を追加。**`core_guard.py` / `test_core_guard.py` と同一コミットにしない**(PR #74 が持ち込む共変更禁止) | `[機械]` `matched_paths()` が**両パスを検出する正例**と、**どちらかを外すと red になる負例**・`test_core_guard.py` が green `[手動]` **6.3-⑤ の敵対レビュー + 人間承認** |
| 10 | **保証縮小の正式化(文書)**: `design.md` 6-0 の**該当 bullet を共通逐語文で置換**・**1-1(`:58`)を同じ共通逐語文で置換**。**PR 本文にも同じ引用ブロックを置く** | `[手動]` **4 箇所(docstring / 6-0 / 1-1 / PR 本文)の引用ブロックが逐語で一致**すること・6-0 と 1-1 が矛盾しないこと |
| 11 | **申し送り**: 残る TB007 約 7 件と条件 2 の局所変数 7 件を位置・形・性質つきで列挙し TSK-235 へ。**Notion の DoD を正式更新** | `[手動]` 全件列挙・**真の脆弱性でない根拠**つき・DoD が Notion に反映 |
| 12 | **凍結基準の受理(最後)**: `base-allowlist.json`(`contract_revision` 13→14)と `negative-fixtures.json`(`fixture_set_revision` 5→6)に履歴 1 件ずつ | `[機械]` `check_tenant_boundary_bypass.py` exit 0・凍結系テスト green `[手動]` **コア領域の逐行確認**(設計書 `:377`) |

**効果測定の環境**: **統合用の一時 worktree**(現行 contract + 現行 checker + TSK-235 の `backend/src`)を作って測る。手順を worklog へ残す。

## 5. DoD(受け入れ基準)

**Notion の DoD「検出 0 件」は本計画で正式に更新する**(人間の判断 2026-09-24):
**TSK-440 で TB007 約 7 件 + TB002 7 件まで下げ、TSK-235 側の書き換え・改名で 0 件にする。**

- [ ] 条件 5 の保証単位が**宣言文として 4 箇所へ同文**で置かれている(docstring / 6-0 / 1-1 / PR 本文)
- [ ] **保証縮小が正式化されている** — `design.md` 6-0 の**既存 bullet を完成文で置換** + **1-1 を完成文で置換** +
      **`core-areas.json` へ `api/**` と `services/**` を追加**(6.3-⑤ の敵対レビュー + 人間承認を経ている)
- [ ] **訪問順序が固定されている** — decorator / defaults / annotations / returns は `function_stack` **push 前**、
      body だけ push 後。**訪問順序の差を検出する負例**がある
- [ ] **baseline/head の写像が分離されている** — 遷移負例(実コミット列)で TB007 になることと、
      「façade だけ変更・consumer 無変更は保証外で green」の両方が固定されている
- [ ] **`unresolved` は原因を問わず赤**。循環・自己参照・条件分岐・star・欠落モジュール・未対応代入の負例と、
      **別モジュールの同名 `Context` が緑であることの単体テスト**がある
- [ ] **構文マトリクス**(デフォルト引数・注釈・class keyword・match guard・`TryStar`)が
      **flow 登録と scanner 判定の両方**で埋まっている
- [ ] **現行バグの是正**: デフォルト引数内の構築が red になる(**現行は 0 件**)
- [ ] 再輸出 façade(**`Context(t)` — (iv) で捕まらない名前**)・サブクラス・深さ上限・star が負例で red
- [ ] 統合 worktree で **TB007 約 7 件 / TB002 7 件**。**残りは TSK-235 側の申し送りが出ている**
- [ ] **通り抜けるもの**が PR 本文に全件明記されている(**再輸出元だけの変更・registry 経由・非対称が原理でないこと**を含む)
- [ ] **落ちてはいけないもの D1〜D7** が負例で守られている
- [ ] **センサス**(`path`/`line`/`end_line`/`scope`/`code`/`symbol`/`message` の exact-set・永続 golden 無し)で
      **TB001・TB003〜TB006 が不変**。**TB002 は裁定した 103 件だけが緑になる**(期待差分を明示)。
      **CI の実経路でも確認している**
- [ ] **条件 2 は候補を狭めていない** — **候補の raw 集合が不変**であることを別に検査し、
      **裁定後の red 集合は期待差分 103 件を明示**している。`RecordingGeneration` が赤のまま
- [ ] **`tenant-context-allowlist.json` の 7B 不一致**が PR 本文に明記され TSK-431 へ申し送られている
- [ ] `contract_revision` / `fixture_set_revision` と sha256 inventory が整合している
- [ ] pytest / ruff / ty green
- [ ] **コア領域(テナント分離)** → sol xhigh・敵対レビュー + **人間の逐行確認**

## 6. テスト計画

NFR-019 の種別では**単体**(検査器自身のテスト)。ランタイムの越境テストは本タスクの射程外。

### 6-1. 全 `ast.Call` の被覆は「列挙」ではなく「検査器自身の不変条件」で示す(5 周目 P0-1)

**★ 構文位置を列挙しても被覆は証明できない。**
**列挙した fixture の木に対する `ast.walk` 三者一致は、その fixture に含まれない位置を証明しない。**
これは台帳の既知失敗型「**母集団を人が列挙する検査は、射程が動くたびに黙って古くなる**」
(`docs/development/harness-evaluation.md:2442`)そのものである。

→ **検査器の中へ不変条件を置く**:

> **`scan_source` が正常に parse した同一の `tree` について、`scanner.visit(tree)` 完了直後に
> ① `ast.walk(tree)` の `ast.Call` ID ② `flow.callable_symbols` のキー
> ③ `_check_tenant_context_call` へ実際に到達した Call ID の 3 集合が一致すること。**
> **一致しなければ `ContractError` として伝播させ、exit 2(判定不能)にする。**

**★ 通常の `Violation`(`TB000`)にしてはいけない**(6 周目 P0-1)。
`scan_source_change` は baseline と head を**同じ `scan_source`** で検査し(`:3401` `:3410`)、
**同一行・scope・code・symbol・message の違反を相殺する**(`:3446` `:3475`)。
→ **同じ未登録 Call が baseline / head の双方にあると相殺されて消える。**
→ **baseline 側だけの不一致は head 違反の走査対象にならず、やはり消える。**
**visitor の通常のリファクタリング・注釈変更・別行の編集で再現する漂流経路**であり、
「不一致なら検査器自体を red」という保証を満たさない。

**exit 契約**: 通常の違反は exit 1、`ContractError` は **exit 2**(`:4031`)。
**不変条件の不一致は exit 2 側に載せ、相殺の外へ出す。**
**負例(期待値を型どおり固定する — 7 周目 P1-2)**:
baseline と head が**同じ不一致を持つ**ケースで、

| 対象 | 期待 |
| --- | --- |
| `scan_source_change` | **`ContractError` を送出**(終了コードは返さない) |
| `check_repository` | **`ContractError` を送出** |
| `main` / subprocess | **exit が ちょうど 2** |

**これなら、将来 Python に新しい構文位置が増えても自動的に検出される。**
下の表は**例示であって母集団ではない**(実測値は残すが、**被覆の根拠にはしない**)。

#### 実測(2026-09-24・自分で計測)

| 構文位置 | scanner 判定 | **flow 登録** |
| --- | --- | --- |
| 関数本体(対照) | TB007 | **○** |
| デフォルト引数 | **0 件** | ○ |
| 引数注釈 / 戻り注釈 | **0 件** | — |
| class keyword(`metaclass=`) | **0 件** | — |
| 関数・クラスの type param bound(PEP 695) | **0 件** | — |
| **lambda default** | TB007 | **× 未登録** |
| **annotated assignment の annotation** | TB007 | **× 未登録** |
| **class base** | TB007 | **× 未登録** |
| **`except` / `except*` の handler type** | TB007 | **× 未登録** |
| **終端文(`return` 等)の後の Call** | TB007 | **× 未登録** |
| match guard / `TryStar` 本体 | TB007 | **×**(`:2444` / `:2411`) |
| `DictComp` の `iter` / 添字代入先 | TB007(**未訪問 → `None` の偶然**) | × |

**scanner が判定していても flow が登録していない位置は、provenance が常に `unknown`** になる。
**既定値を緩和すると、そこが素通りする。**

**計測上の注意(自分が踏んだ)**: `callable_symbols` は `id(node)` で引くので、
**別々に `ast.parse` した木と比べると全件「未登録」に見える**。
**scanner が実際に使った木**で比べること。

### 6-2. 追加するもの

| 追加するもの | 種別 | 置き場 |
| --- | --- | --- |
| 構文マトリクス(6-1)と**判定済み ID の突合** | 単体 | `tests/test_check_tenant_boundary_bypass.py` |
| センサス回帰(**`line`・`end_line` を含む exact-set**・永続 golden 無し) | 単体 | 同上 |
| **CI の実経路**(`scan_source_change` + 実コミット列 + `check_repository`) | 単体 | 同上 |
| **baseline/head 写像の分離**の遷移負例(実コミット列) | 単体 | 同上 |
| 相対 import 絶対化(`__init__.py` を含む) | 単体 | 同上 |
| `C5_CONTEXT_IN_DEFAULT_ARG` / `C5_SECRET_IN_DEFAULT_CAPTURE`(**訪問順序の差を検出**) | 負例 fixture | `tests/fixtures/tenant_boundary/negative/` |
| `C5_CONTEXT_REEXPORT_FACADE`(**`Context(t)`** — (iv) で捕まらない名前)/ `..._REEXPORT_SUBCLASS` / `..._REEXPORT_DEPTH_LIMIT` / `..._REEXPORT_STAR` / `..._REEXPORT_CYCLE` / `..._REEXPORT_SELF_REFERENCE` / `..._REEXPORT_CONDITIONAL` / `..._REEXPORT_MISSING_MODULE` / `..._REEXPORT_UNSUPPORTED_ASSIGN` | 負例 fixture | 同上。**宣言した unresolved の原因を全件覆う**(4 周目 P1-1) |
| `C5_CONTEXT_IN_FUNCTION_TYPE_BOUND` / `C5_CONTEXT_IN_CLASS_TYPE_BOUND`(**PEP 695**) | 負例 fixture | 同上 |
| `C5_CONTEXT_IN_LAMBDA_DEFAULT` / `..._IN_ANNOTATED_ASSIGNMENT` / `..._IN_CLASS_BASE` / `..._IN_EXCEPTION_HANDLER_TYPE` / `..._AFTER_TERMINATOR` | 負例 fixture | 同上(5 周目 P0-1 の探針) |
| `C5_CONTEXT_ATTRIBUTE_NAME_ON_KNOWN_RECEIVER` / `..._IN_DICT_COMPREHENSION` / `..._IN_SUBSCRIPT_TARGET` / `..._RELATIVE_IMPORT` | 負例 fixture | 同上 |
| **別モジュールの無関係な同名 `Context` が緑であること** | **単体テスト**(`scan_source` を直接呼ぶ) | `tests/test_check_tenant_boundary_bypass.py` |
| **`C2_GENERATION_IMPORT` は変更しない**(候補を狭めないため赤のまま) | 負例 fixture | — |

### 6-3. 条件 2 のセンサスはマージ順で自己矛盾する(3 周目 P1-4)

**マージ順を固定しないので、TSK-235 が先に入ると D7「TB001〜TB006 不変」を満たせない**
(旧 checker は 110 件、新 checker は裁定済み 103 件を緑にするため)。

→ **2 段に分ける**:
1. **条件 2 候補の raw 集合が不変**であることを別に検査する(**候補を狭めていないことの証明**)
2. **裁定後の red 集合は、期待差分 103 件を明示**する(裁定した分だけが緑になる)

**★ 正例 fixture は追加できない。** `load_contract`(`:1401-1411`)が
**正例 fixture 集合と `allowed_symbols[].fixture` の exact-set 一致**を強制するので、
**正例を 1 件足すには `allowed_symbols` を 1 件足す**ことになる
(= 許可する DB 到達シンボルを増やす意味の変更)。**本タスクの射程ではない。**
→ **「緑であること」の確認は単体テストで行う。**

**既存 68 負例・正例 5 件は exact-set で守られている**ので、増減はすべて資産と同時更新する。
`EXPECTED_NEGATIVE_IDS`(`:32`)も同時に更新する。

## 7. 申し送り(本タスクの射程外)

### TB005 137 件(`develop` の潜在)— 別セッションの実測

| 群 | 件数 | 場所 | 性質 |
| --- | ---: | --- | --- |
| **A 実行時 DB アクセス** | **72** | `authz/catalog.py` 40 / `authz/provisioning.py` 32 | **真陽性**。実際の psycopg 呼び出し |
| **B 宣言的スキーマ定義** | **65** | `db/*/models.py` | **別種の誤検知**。`server_default=text("true")` などの **DDL 宣言**であり実行時アクセスではない |

- **A は `allowed_symbols`(現在 5 件)へ入るべきインフラ**の可能性が高い
- **B は「`sqlalchemy.text` を宣言文脈で使うのは DB アクセスではない」という別の射程判断**で、
  TB007 と同型だが**条件が違う**
- **どちらも本タスクの射程外。** 敵対レビュー 2 周目で射程を広げると収束が遠のく
- **「他タスクが触ると 72 件が表面化する」は成立しない。** 相殺は行と所属シンボルの対応で決まるので、
  **新たに DB 呼び出しを足した増分だけ**が TB005 に当たる
  (別セッションが当初「触ると表面化する」と説明し、後から訂正した)
- **`db-api-inventory.json` に `sessionmaker` と `sqlalchemy.orm.Session` が登録済み**なので、
  **TSK-424 の PR C が Session 供給を新設すると、供給シンボルを `allowed_symbols` へ足さない限り
  TB005 に当たる**(誤検知ではなく設計どおりの検出)

### そのほか

- **同期単位へ**: D4「記録権世代」の欄名と条件 2 の語彙を突き合わせること。
  **同期プロトコル正本 v0.4(2026-09-24 approved)は D4 の「物理形式は本書で決めず、
  10-1 の論点 17 から実装計画へ送る」と明記している**(`docs/design/sync-protocol.md:32`)。
  → **欄名は未確定**であり、**条件 2 の候補を狭めない判断は正本と整合している**。
  なお現行の実装は `backend/src/pitchlog/db/recording_rights/models.py` が
  `RecordingGeneration` と列名 `generation` を使っている(**正本が未確定なので暫定**)
- **TSK-431 へ**: `tenant-context-allowlist.json` の 7B 不一致(通知済み)
- **TSK-235 へ**: 残る TB007 約 7 件 + 条件 2 の裸の局所変数 7 件の書き換え
- **新規タスクの起票が要る**: **`TenantContext` の発行と registry 登録を専用モジュールへ封じ込め、
  その境界だけをコアにする**。`api/**` + `services/**` の paths 拡大では
  `domain/**`・`sync/**` を覆えないため(4 周目 P0-1)。**人間が残余リスクを受容しない場合はこれが必須になる**
- **マージ順序は固定しない**(履歴の「ちょうど 1 件」は merge-base 相対のため。
  `scripts/check_tenant_boundary_bypass.py:702`)
