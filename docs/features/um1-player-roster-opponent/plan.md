---
feature: um1-player-roster-opponent
status: active
承認: 済(2026-09-24・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..
notion: https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7
branch: feature/um1-player-roster-opponent
created: 2026-09-24
計画レビュー周回: 1        # 敵対レビュー 1 周目(判定 否決・P0 16 / P1 6 / P2 1)の反映を含む
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: U-M1 選手・在籍・対戦相手チーム

## 1. 背景・目的

**Notion**: [TSK-393](https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7)
**出所**: TSK-363 / [`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:212`(承認済 2026-09-13)
**調査メモ**: [research.md](research.md) — **典拠集**(正本ではない。`docs/features/` は作業ディレクトリ)。
本書が事実を述べるときは**正本を直接引く**。research.md は調査の経緯をたどるための索引として参照する。

U-M1 は pitchlog **最初の製品コード**。主所有 FR は 4 件、**分担先なしの単独主所有**
([`../product-impl-unit-split/design.md`](../product-impl-unit-split/design.md)`:75` 帰属表 / `:86-92` 分担表に U-M1 の行なし)。

| FR | 必須度 | 要求の骨子 |
| --- | --- | --- |
| [FR-015](../../requirements/requirements-pitchlog-2026-07-22.md#FR-015)(`:356-364`) | Must | 不変の内部 ID / 名前・投・打 / 背番号は任意・**一意制約を張らない**(同番号は**警告のみで登録続行可**)/ **記録時点の背番号で過去試合を表示** / **試合画面を離れずその場登録**(断中は一時 UUID → 同期時に正式 ID へ置換)/ 入部年度・学年を持たない |
| [FR-017](../../requirements/requirements-pitchlog-2026-07-22.md#FR-017)(`:374-383`) | Must(区分 3 つ)/ ラベルは Should | 3 区分固定 / **OB は候補から完全除外** / **「その他」は初期表示に出ないが明示操作で選択可** / **全区分可逆** / 一括変更は**プレビュー→確認→実行** / **相手チームレコードの選手にも適用** / **カルテ・試合準備画面からも変更できる** / **初期ラベル同梱** / 変更はキャッシュ無効化トリガー |
| [FR-018](../../requirements/requirements-pitchlog-2026-07-22.md#FR-018)(`:385-392`) | **Should** | プレイ紐づけゼロ → **確認の上で非表示化**(ゴミ箱 UI を経ない)/ 紐づく選手は **OB 化へ誘導** / **競合挿入を含めて紐づけ判定と削除が同一トランザクション** / **進行中(未終了)試合があると削除不可で OB 化へ誘導** |
| [FR-039](../../requirements/requirements-pitchlog-2026-07-22.md#FR-039)(`:405-414`) | Must | テナント内レコード・テナント間で共有されない / **試合作成を中断せず登録・選択** / **類似名は重複警告(意図的なら登録可)** / **試合または選手が紐づくチームは削除不可でリネームへ誘導** / **付与によらず 404** |

### 着手時点の与件が覆った点

> **U-M1 はコア領域(機械判定で確定)であり、降格条件は存在しない。**
> Notion カードの「コア判定(機械): 非コア」「降格条件: 6.3 の確定ゲートで (i) が確定すること」は
> [`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:292-315`【承認後の是正】より前のスナップショット。
> **TSK-394 でも同一記述を確認済み**(葉 6 本が同型と見られる)。カード一括訂正の要否は PO 判断。

> **U-T1 の公開面は空で、現時点では DB に到達できない。** 実効依存に **TSK-424** を含む(4 節)。

## 2. スコープ

### やること

- **バックエンド実装** — 選手・在籍区分・対戦相手チームレコードの HTTP 入口とリポジトリ操作、越境テスト
- **自 FR の UI 設計正本を書く**([`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:60`「API / UI / データモデルの設計正本を書く = 各単位のタスク」)
- **`.claude/core-areas.json` への paths 登録**(同 `:61`「**各核単位が自 PR で行う**」)

### やらないこと

| 項目 | 理由・送り先 |
| --- | --- |
| **フロントエンド実装(Vue)と Vitest** | **正本が帰属を定めていない。**`../product-impl-unit-split/` の plan.md・design.md に「フロントエンド」「Vitest」「Vue」の語が **1 件も無い**(実測)。`:60` が各単位へ送るのは **UI の「設計正本」**であって実装ではない。**受け皿が正本上空席**である事実を 8 節で申し送る |
| **`system_vocabularies` の seed と在籍区分キーの値の決定** | **別タスクへ切り出す**(8 節)。migration は **5 領域すべてのコア paths** で、契約 3(`:181`)の「2 領域以上は例外として明示列挙」に **U-M1 は含まれない**。コミットを分けても PR の変更 path は変わらない。値は U-M2・U-C 系も使う**共有語彙** |
| スタメンの記憶・復元(FR-016) | **U-M2** |
| 試合作成時の相手チーム選択(FR-001) | **U-G1** |
| 試合の削除とゴミ箱(FR-019) | **U-D1** |
| キャッシュ無効化**契約** | **U-T1**(**発火点のみ U-M1** — 同書が「発火は各トリガー所有単位が負う」と申し送り) |
| 選手統合・分割(FR-035/037) | **U-A2** |
| 移行のファンアウト・在籍棚卸し・名寄せ(FR-038) | **U-X5** |

### 契約 4 — 主所有 FR × 5 コア領域の突合(`:182` が各単位へ要求)

| FR | 同期プロトコル | 状況計算 | 記録権 | テナント分離 | データ移行 |
| --- | --- | --- | --- | --- | --- |
| **FR-015** | **触れる** — 断中の一時 ID → 正式 ID の置換。**機構は U-S1 が持つ**(下記) | 触れない | 触れない | **触れる** — 選手はテナントデータ。全出力経路の越境 | **触れる** — 88 列 63-71 が「移行時に使用」。**機構は U-X5** |
| **FR-017** | 触れない | 触れない | 触れない | **触れる** — 在籍区分の変更が**キャッシュ無効化トリガー 14**(共有集計のみ) | **触れる** — 移行後の在籍棚卸し。**機構は U-X5** |
| **FR-018** | 触れない(下記の判定) | 触れない | 触れない | **触れる** — 削除もテナント境界内 | 触れない |
| **FR-039** | 触れない | 触れない | 触れない | **触れる** — 第三者データは**付与によらず 404**(要件書 `:641`) | **触れる** — チームのファンアウト複製。**機構は U-X5** |

**FR-018 が同期プロトコルに触れないことの判定**(条文の逐語読解):
受入基準(要件書 `:392`)の条件は「**当該チームに進行中(未終了)の試合が存在する**」という**状態の問い合わせ**であり、
括弧内の「断中端末の未同期キューが当該選手を参照している可能性があり、サーバー側のトランザクションでは検知できないため」は
**この保守的な規則を採った理由の説明**である。**未同期キューを読む機構は要求されていない。**
必要なのは ① プレイ紐づけゼロの判定 ② 進行中試合の存在判定 ③ ①②と削除の同一トランザクション化 の 3 つで、いずれも読み取りで閉じる。

**FR-015 の同期面の帰属** — `../product-impl-unit-split/design.md:86-92` の分担表に FR-015 の行が無く、
`../product-impl-unit-split/plan.md:240-252` の「面が切れなかったときの手順」も**対象を FR-007/010/011/019 に限定している**ため、
**FR-015 はその手順の適用対象外**である。したがって本書は手順を代用せず、**8 節で人間の判断を仰ぐ**。
正本上 FR-015 は依然 **U-M1 の単独主所有**であり、帰属表を更新しない限り U-S1 へ移らない。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/design/data-model.md` / 要件書 / `docs/adr/` | **反映なし**(既決事項に従うのみ。再決定しない) | — |
| **`.claude/core-areas.json`** | **paths を追加**(越境テスト・新規リポジトリ)。`:61` が「各核単位が自 PR で行う」と定める。**6.3-⑤ の敵対レビュー + 人間承認の対象** | PR レビュー(6.3-⑤) |
| `contracts/authz/route-registry.json` / `http-route-matrix.json` (+ lock) | **追記**(`route_kind` 値域の決定が要る — 4 節) | PR レビュー |
| `contracts/tenant_boundary/repository-contract.json` | **capability 登録**。**`FROZEN_BASELINE_ASSETS` の 1 つ**(`scripts/check_tenant_boundary_bypass.py:41`)なので**設計書 7.7-2 の記録が要る** | 7.7 の更新経路 |
| `docs/features/um1-player-roster-opponent/design.md` | **新設**(暫定規約・入口表・DTO 定義) | PR レビュー |

## 4. 実装方針

**重さ分類 = コア領域**(機械判定の確定。降格の道は無い)。詳細設計は [design.md](design.md) を正とし本節で複製しない。

### 外部依存(**すべて着地しないと入口を開けない**)

| # | 要るもの | 所有 | 状態 |
| --- | --- | --- | --- |
| 1 | **capability カタログ**(`contracts/authz/product/capability-catalog.json`) | **TSK-424 PR A** ステップ 21 | 計画レビュー中 |
| 2 | **capability の登録** | **U-M1 自身** | **凍結基準を動かす**(上記 3 節)→ 7.7-2 の記録 + **TSK-431 との順序調整** |
| 3 | **Session 供給**(`TenantRepositoryBase._session`) | **TSK-424 PR C** | 未着手(PO 裁定 2026-09-24)。**供給形式は U-M1 で決めない** |
| 4 | **RLS DDL の実スキーマ適用**(12-4 通過条件①) | **TSK-344** | 未着手。**`backend/migrations` に `CREATE POLICY`/`CREATE ROLE`/`ROW LEVEL SECURITY` が 0 件**(実測) |
| 5 | ~~**`route_kind` の値域決定**~~ | **✅ 解消済み(2026-10-04 訂正)** — TSK-446 / **PR #77**(2026-09-25 マージ)。`record_and_aggregate` が `ROUTE_KINDS` に入っている。**本表の「空席」は誤記で、本書作成の翌日に解決していた** | `route-registry.json` と `http-route-matrix.json` は exact-set(`scripts/check_authz_catalog.py:2437-2442`)。`route_kinds` は検査器の定数 `ROUTE_KINDS`(同 `:92`)に固定で、**選手 CRUD を表す種別が無い**。**TSK-380 の射程は既存 37 経路の `test_owner` 再割り当てであって値域拡張ではない** |
| 6 | **`TenantContext` の生成** | **U-A1**(ブロック中) | `repositories/context.py:26`「テナント ID が認証済み主体のものであることは API 層(TSK-217 / U-A1)の責務」 |
| 7 | **在籍区分キーの値と seed** | **別タスク**(8 節) | 未起票 |
| 8 | **複数表の不変条件の実行単位** — 入口 **#7**(FR-018 の削除ガード)・**#11**(FR-039 の削除ガード)・**#6**(FR-017 の一括変更)は**複数表にまたがる判定を 1 トランザクションで**行う必要がある | **TSK-444(PR C)** | 未着手。**2026-09-24 に当方の指摘を受けて射程へ取り込まれた** |
| 9 | **無効化意図の ID 導出規則と原子性の錨** — `contracts/tenant_boundary/cache-invalidation-contract.json` の `durable_intent` は `intent_id_derivation: ["target_event_v10","target_confirmed_version"]` と `same_transaction_with: "T7"` を**トリガー別の分岐なしで 14 件すべてに掛けており**、**イベント由来でない 7 トリガー**(在籍区分の変更を含む)に適用できない | **TSK-447** | 未着手。**U-M1 側で暫定規約を決めない**(他のトリガー所有単位と割れるため) |

> **【承認後の追記 — 2026-09-24】** 上表の **8・9 は承認(2026-09-24)後に判明した外部依存**である。
> **射程・DoD・実装ステップは変えていない**(依存の記録のみ)。
>
> **経緯**: `TenantRepositoryBase._execute_operation` は `_tenant_transaction` の中で 1 文だけ実行し、
> `repositories/binding.py` が「**同一 Session へテナント文脈を再束縛できない**」を課すため、
> **同一 Session では `execute()` を 2 回呼べない**(実測)。
> 一方 TSK-424 の capability カタログ(74 件・`CAP:<table>:<operation>`)は **1 operation = 1 表**を強制する。
> この 2 つが重なると **FR-018 と FR-039 の削除ガードが構造的に実装できない**。
> **TSK-444 が実行単位を、TSK-447 が意図 ID と原子性の錨を引き取った**(2026-09-24・セッション間の調整)。

**製品 operation token 型は TSK-424 の着地前に定義しない。**
[`../tenant-boundary-enforcement/plan.md`](../tenant-boundary-enforcement/plan.md)`:174`(ステップ 9)が
「**製品 capability 集合と越境関数 registry は初期値ともに空集合**とし…**製品表操作は TSK-424 の表分類から生成する capability を受けて初めて有効化する**」と定め、
同 [`design.md`](../tenant-boundary-enforcement/design.md)`:321` が「**ステップ 9 の製品 capability も TSK-424 の出力契約に含める**」と定めているため、
先行定義すると型名・capability ID が生成物と分岐する。

### 非コアで通せる 5 条件 — 本単位には適用されないが「面を混ぜない」規律として守る

`../product-impl-unit-split/plan.md:254-258` が「**葉 6 本は機械判定でコアが確定したので本節の条件では通せない。
ただし 5 条件そのものは葉の計画書でも『面を混ぜない』規律として有効なので下表は残す。**」と定める。
**検査対象 = `git diff -U0 origin/develop...HEAD -- backend/src` の追加行。各式の一致 0 が合格。**

| # | 条件 | 確定した検索式 | 許可側 |
| --- | --- | --- | --- |
| 1 | 新たな認可判定を追加しない | `\b(can_\|may_\|is_allowed\|has_permission\|check_.*_access\|require_role\|assert_.*_owner)` | U-T1 の公開関数の呼び出しのみ |
| 2 | 同期セマンティクスを扱わない | `\b(idempotenc\|idempotent_key\|seq_no\|sequence_no\|tombstone\|revision_no\|generation)\b` | — |
| 3 | NFR-018 の対象計算を含まない | `responsible_pitcher\|earned_run\|at_bat_result\|inning_state\|rbi\|era\|avg\|obp\|slg` | — |
| 4 | キャッシュ無効化契約に触れない | `\b(invalidate\|cache_clear\|evict\|purge_cache)` | `pitchlog.repositories.cache_invalidation` の公開シンボルの import / 参照 / 呼び出しのみ |
| 5 | テナントデータは U-T1 の越境関数経由だけ | `\b(session\.(execute\|query\|scalars)\|select\(\|text\(\|engine\.\|raw_connection)` | U-T1 のリポジトリ基底の継承・呼び出しのみ |

**条件 3 の注意**: `era` は `operation` の部分文字列に一致する(`../u01-dto-base/plan.md:150` の先例)。**差分行限定**で当てる。
**条件 4 の注意**: `_normalize_identifier`(`scripts/check_tenant_boundary_bypass.py:1440-1445`)が**最後に `.lower()` する**ため、
**`ROSTER_STATUS_CHANGE` という大文字の識別子も TB004 に一致する**。
→ **`from pitchlog.repositories.cache_invalidation import CacheInvalidationTrigger` して `.ROSTER_STATUS_CHANGE` を参照する。
文字列リテラルも同名の自前定数も書かない。**(救済経路 = `allow_condition4`・同 `:3118`・`:3250`・`:3260`)

### 実装ステップ(コミット単位 — 設計書 6.1)

> ## 【改訂 2026-10-04・改訂承認: 山田正輝】着手の拘束をステップ 5 以降へ縮める
>
> **旧**: 「着手は外部依存 1・3・4・5・7 の着地後(**着地前に着手しない**ことを本書の拘束とする)」
>
> **新**: **ステップ 1〜4 は外部依存の着地を待たずに着手する。ステップ 5 以降が 4・7 の着地を待つ。**
>
> ### 改訂の理由
>
> **旧の拘束は本書が自分に課したもので、正本から導かれたものではない**(「**本書の拘束とする**」)。
> **2026-09-24 に、当時 5 本すべてが未充足だった前提で書かれている。**
>
> **2026-10-04 の実測で 3 本が着地済み**:
>
> | dep | 状態 |
> | --- | --- |
> | 1 capability カタログ | **✅ develop**(`contracts/authz/product/capability-catalog.json`) |
> | 3 Session 供給 | **✅ develop**(`TenantRepositoryBase._session` — PR #82) |
> | 5 `route_kind` の値域 | **✅ 解消済み**(TSK-446 / **PR #77**・2026-09-25。`record_and_aggregate`)。**本書の「空席」は誤記** |
> | 4 RLS DDL の実適用 | ❌ TSK-344 |
> | 7 在籍区分キーと seed | ❌ TSK-475(2026-10-03 起票・進行中) |
>
> **残る 4・7 は、ステップ 1〜4 の合格条件に現れない**(2026-10-04 実測):
>
> | ステップ | 合格条件 | 4・7 を要するか |
> | --- | --- | --- |
> | 1 `core-areas.json` へ paths 登録 | core-guard が green | **要らない** |
> | 2 DTO を追加 | `test_roster_schemas.py` green + lint/type | **要らない**(純粋なスキーマ定義) |
> | 3 契約資産へ入口を登録(**`test_owner.status` は `planned`**) | `test_check_authz_catalog.py` green・registry と matrix が exact-set | **要らない**(dep 5 のみで、着地済み) |
> | 4 リポジトリと operation token | 契約テスト green + 7.7-2 の記録 | **要らない**(dep 1 のみで、着地済み) |
> | **5 選手の入口を開く** | `ROUTERS` へ登録 | **ここから要る** |
>
> **dep 4 は 12-4 の通過条件①であり、`data-model.md` 12-4 は「マージ条件」であって「着手条件」ではない**
> (`../product-impl-unit-split/plan.md:40`「**最重要の発見**」)。
>
> **ステップ 3 が `test_owner.status = planned` で登録する設計**であることも、
> **入口を「登録するが開かない」段階が最初から想定されていた**ことを示している。

**着手の拘束**: **ステップ 1〜4 は外部依存の着地を待たない。ステップ 5 以降は dep 4・7 の着地後**
(`/implement` は承認済み計画書を要求する)。
**総数を確定できないため、ステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`.claude/core-areas.json` へ本単位の paths を登録する** — 越境テストと新規リポジトリのパスを `tenant-isolation` へ追加する。**`scripts/core_guard.py` / `tests/test_core_guard.py` を同一コミットに入れない**(#74 の `verify_area_path_baseline()` がチェック欄の検査より前に例外を投げるため) | `core-guard` が green。6.3-⑤ の審査対象として PR に明示されている |
| 2 | **DTO を追加する** — `backend/src/pitchlog/api/schemas/roster.py`。[design.md](design.md) 3 節の全 DTO(`PlayerStatusPreview` を含む)を定義する | `backend/tests/test_roster_schemas.py` が green。値域・省略と明示 null の区別・空配列と重複 ID の扱いをテストで確認。`ruff check` / `ruff format --check` / `ty check` green |
| 3 | **入口の契約資産を追記する** — `route-registry.json` と `http-route-matrix.json`(+ lock 再封印)へ本単位の入口を登録する。**既存行の `test_owner` は書き換えない**。新規行の `test_owner.status` は **`planned`** とする | `uv run pytest -c pyproject.toml tests/test_check_authz_catalog.py` が green。registry と matrix が exact-set で一致 |
| 4 | **リポジトリと operation token を追加する** — TSK-424 の capability カタログから token 型を導き、registry へ登録する。**7.7-2 の記録**を同時に行う | `test_authz_repository_contract.py` が更新後の契約で green。凍結基準の記録が 7.7-2 の様式を満たす |
| 5 | **選手の入口を開く** — 作成・一覧・取得・更新。`ROUTERS` へ登録し、`test_api_conventions.py` の述語 4(経路数)の期待値を更新する | `test_roster_boundary.py` の当該入口ぶんが green(認可行列どおりに通り行列外は 404)。`/health` `/version` を含む既存テストが green |
| 6 | **在籍区分の入口を開く** — プレビューと適用。**キャッシュ無効化の発火点**を `CacheInvalidationTrigger.ROSTER_STATUS_CHANGE` で置く | 在籍区分変更後に共有集計のキャッシュが失効することを受入テストで確認(要件書 `:996`) |
| 7 | **選手の削除ガードを実装する**(FR-018) — 紐づけゼロ判定・進行中試合の存在判定・同一トランザクション化 | 競合挿入を含む同時実行テストで、判定後に紐づいた場合に失敗すること・進行中試合があると拒否されることを確認 |
| 8 | **対戦相手チームレコードの入口を開く**(FR-039) — 作成・一覧・更新・削除。類似名の警告と削除拒否の誘導 | 試合または選手が紐づくチームの削除が拒否されること・類似名が警告で登録続行できることを確認 |

**第 2 群を後から足すときの再承認**: 本表へステップを追加する場合は、**追加分について敵対レビューと人間承認を再度受ける**。
承認済みステップの続きとして無審査で追加しない。

## 5. DoD(受け入れ基準)

### 主所有 FR の受入基準(要件書の条文と 1 対 1)

- [ ] **FR-015**: 同番号の警告が出て**警告後も登録を続行できる** / **記録時点の背番号**で過去試合が表示される(**正本はイベント側** — `data-model.md:1430-1462`。本単位は選手側に当時値を持たせないことの確認に留まる) / **試合画面を離れずに登録できる**(UI 設計正本を書く) / 内部 ID が不変 / 入部年度・学年を持たない
- [ ] **FR-017**: **OB が候補から完全除外** / **「その他」は初期表示に出ないが明示操作で選択可** / **全区分可逆** / **プレビュー→確認→実行** / **相手チームレコードの選手にも適用** / **カルテ・試合準備画面からも変更できる**(UI 設計正本)/ **初期ラベル同梱**(別タスクの seed と整合)/ **キャッシュ無効化が発火する**
- [ ] **FR-018**: **確認 UI** / **OB 化へ誘導** / **競合挿入を含む同一トランザクション** / **進行中試合があると拒否して誘導**
- [ ] **FR-039**: **試合作成を中断しない登録・選択** / **類似名の警告** / **試合または選手が紐づくチームの削除拒否とリネーム誘導** / **付与によらず 404**

### 横断要求(`../product-impl-unit-split/design.md:109-121` が「破っていない」として入れることを要求)

- [ ] **物理削除しない** / **テナント分離を全機能に適用** / **自動エスケープ**(NFR-023)
- [ ] **趣旨の宣言** / **テナントの用語定義**に反していない
- [ ] **一覧はページングする**(NFR-005 — 全件読み込み型の集計を書かない)
- [ ] **NFR-019**: pytest を伴う。**越境テストは FR-034 の認可行列で合否判定**(要件書 `:933`)

### 機構

- [ ] **`backend/tests/conftest.py` の差分が 0 行**(`.claude/core-areas.json:326` の `backend/*conftest.py` に一致するため。fixture は `backend/tests/api_fixtures.py` へ置き明示 import — U-00 の先例 `test_api_errors.py:7`)
- [ ] **`test_authz*` の命名を使わない**(同 `:319` に一致するため。**越境テストは名前ではなく paths 登録でコア化する** — 3 節)
- [ ] **5 条件すべてに一致 0**(4 節の式で実測)
- [ ] pytest / ruff / **ruff format** / ty green
- [ ] **契約 4 の 5 領域突合**(2 節)を書いた

## 6. テスト計画

| 対象 | 種別 | ファイル | 確認すること |
| --- | --- | --- | --- |
| DTO のバリデーション | 単体 | `backend/tests/test_roster_schemas.py` | 値域 / `extra="forbid"` / PATCH の省略と明示 null / bulk の空配列・重複 ID / ページ上限の境界 |
| 越境 | 越境 | `backend/tests/test_roster_boundary.py` | **認可行列どおりに通り、行列外はすべて 404**。**API 直叩きを含む**(`data-model.md:2532` — 入口を開く PR は同一 PR に外から直接叩くテストを含む) |
| 在籍区分変更後のキャッシュ失効 | 受入 | 同上 | **OB 化した選手が共有結果に現れない**(要件書 `:933` の (b) 列挙) |
| 削除の競合 | 故障系 | 同上 | 判定後に紐づいた場合に失敗する / 進行中試合があると拒否 |
| 同番号の警告後の登録続行 | 受入 | 同上 | 警告が出たうえで登録できる |

**実行手順**(`backend/` で。CI と同じ順 — `.github/workflows/ci.yml:255-262`):

```
docker compose up -d                    # backend/tests/db/conftest.py が DB 必須テスト 0 件を失敗扱いにする
uv run ruff check .
uv run ruff format --check .            # backend では CI が強制する(AGENTS.md の注記はハーネス側のもの)
uv run ty check
uv run pytest -c pyproject.toml
```

**迂回検査は実装スケルトンの段階で当てる**:
`uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`

## 7. リスク

| # | リスク | 対応 |
| --- | --- | --- |
| **R1** | 入口を開くのに**外部所有者が 5 者**(TSK-424 PR A / PR C・TSK-344・`route_kind` 値域の**空席**・**U-A1**(ブロック中)・在籍区分キーの別タスク)。1 つでも動かないとマージできない | 着地状況を /pr の前に再確認する。空席の所有者は 8 節で人間へ上げる |
| **R2** | `test_owner.status: "implemented"` は**ハーネス側 `tests/` の node ID** としか照合されない(`scripts/check_authz_catalog.py:2674-2685`) | 新規行は **`planned` 止まり**(ステップ 3 の合格条件) |
| **R3** | `players.team_record_id` は immutability の**未分類列**(handoff `TSK-372`)。所属チーム変更の可否がコードから読めない | `PlayerUpdate` の更新対象に含めない。必要になれば TSK-372 へ上げる |
| **R4** | **capability 登録は凍結基準を動かす**(`repository-contract.json` が `FROZEN_BASELINE_ASSETS`)。**TSK-431 が同じファイル群を触る** | ステップ 4 で **7.7-2 の記録**を同時に行い、TSK-431 と順序を調整する |
| **R5** | API 層は `api/**` の**全ソース連結**に対する部分一致検査を受け、**`Session`・`generation` を docstring・コメント含め書けない**(`backend/tests/test_api_conventions.py:22-37`)。**TB004 は AST 上の識別子検査**で範囲が異なる(`scripts/check_tenant_boundary_bypass.py:2672`) | [design.md](design.md) D5 で 2 つの検査を**分けて**記述し、命名を実装前に固定する |
| **R6** | **`core-areas.json` を編集する**ため **#74 の `verify_area_path_baseline()`** が掛かる。`core_guard.py` / `test_core_guard.py` と同一コミットにすると、**後から revert しても打ち消せず force-push も `git_guard.py` が拒否する** | ステップ 1 を**単独コミット**にする(合格条件に明記) |

## 8. 人間の判断を仰ぐ事項

| # | 事項 | 本書の扱い |
| --- | --- | --- |
| **1** | **フロントエンド実装の帰属** — 単位分割の正本に「フロントエンド」「Vitest」「Vue」の語が **1 件も無い**(実測)。`:60` が各単位へ送るのは **UI の「設計正本」**であって実装ではない。**FR-015/017/018/039 の UI 面の受け皿が正本上空席** | **U-M1 は射程外**として線を引いた。受け皿の決定を仰ぐ |
| **2** | **FR-015 の同期面の帰属** — 分担表に FR-015 の行が無く、「面が切れなかったときの手順」の対象外。正本上は **U-M1 の単独主所有**のまま | 帰属表を更新せずに U-S1 へ移さない。判断を仰ぐ |
| **3** | **`route_kind` の値域決定の所有者** — `TSK-380` の射程は既存 37 経路の `test_owner` 再割り当てであり、**値域拡張は空席** | 空席として明示。所有者の指名を仰ぐ |
| **4** | **在籍区分キーの値と seed の別タスク起票** — `active` のみ `data-model.md:524` に典拠。`other`/`ob` はリポジトリ内に文字列が存在しない。seed は **5 領域すべてのコア paths** で契約 3 の例外に U-M1 は含まれない | 別タスクへ切り出す前提で本書から外した。起票の可否を仰ぐ |
| **5** | **Notion カードのコア判定が正本より古い** — **葉 6 本すべてが同型**と見られる(TSK-394 で確認) | TSK-393 のカードには訂正コメントを入れる。**他タスクのカードには触れない** |
