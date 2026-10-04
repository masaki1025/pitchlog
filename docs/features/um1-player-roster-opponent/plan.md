---
feature: um1-player-roster-opponent
status: active
承認: 済(2026-10-05・山田正輝 / 改訂 2026-10-05 の承認 — 初版 2026-09-24)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..
notion: https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7
branch: feature/um1-player-roster-opponent
created: 2026-09-24
計画レビュー周回: 6        # 敵対レビュー 1 周目(判定 否決・P0 16 / P1 6 / P2 1)/ 改訂 2026-10-05 の 1 周目(否決・P1 3 / P2 2)・2 周目(否決・P1 3 / P2 3)・3 周目(否決・P1 2 / P2 4)・4 周目(否決・P1 3 — PO 裁定で N1〜N4 へ)・5 周目(否決・P1 1〔N3〕/ P2 1)の反映を含む
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
| **`.claude/core-areas.json`** | **paths を追加**(越境テスト `backend/tests/test_roster_boundary.py` の 1 件 — 新規リポジトリは既存 glob が覆う)。`:61` が「各核単位が自 PR で行う」と定める。**6.3-⑤ の敵対レビュー + 人間承認の対象** | PR レビュー(6.3-⑤) |
| `scripts/core_guard.py` / `tests/test_core_guard.py`(**改訂 2026-10-05 で追加**) | `AREA_PATH_ADDITIONS["tenant-isolation"]` の宣言と表明の更新(4 節 ステップ 4)。`BASELINE_DEFINITION_PATHS` のため `core-areas.json` と別コミット | PR レビュー |
| `contracts/authz/route-registry.json` / `http-route-matrix.json` (+ lock) | **追記**(`route_kind` の値域は PR #77 で決定済み — `record_and_aggregate`) | PR レビュー |
| `contracts/tenant_boundary/repository-contract.json` | **capability 登録**。**`FROZEN_BASELINE_ASSETS` の 1 つ**(`scripts/check_tenant_boundary_bypass.py:41`)なので**設計書 7.7-2 の記録が要る** | 7.7 の更新経路 |
| `contracts/tenant_boundary/base-allowlist.json`(権威履歴)/ 履歴 snapshot / `tests/fixtures/frozen-archive-cases/manifest.json`(**改訂 2026-10-05 で追加**) | 7.7-2 の記録 1 件・snapshot・比較 corpus の digest 再封印(4 節 ステップ 3 の内訳) | 7.7 の更新経路 |
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
> **新**: **ステップ 1〜4 は外部依存の着地を待たずに着手する。ステップ 5 以降が 4・6・7 の着地を待つ。**
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
> | **5 選手の入口を開く** | `ROUTERS` へ登録 | **ここから要る**(**4・6・7**) |
>
> **dep 4 は 12-4 の通過条件①であり、`data-model.md` 12-4 は「マージ条件」であって「着手条件」ではない**
> (`../product-impl-unit-split/plan.md:40`「**最重要の発見**」)。
>
> **ステップ 3 が `test_owner.status = planned` で登録する設計**であることも、
> **入口を「登録するが開かない」段階が最初から想定されていた**ことを示している。

> ### 【2026-10-04 追補】**dep 6 の落としを是正**
>
> **初版の改訂は「ステップ 5 以降が 4・7 を待つ」と書き、`dep 6`(`TenantContext` の生成 = U-A1)を落としていた。**
> **ステップ 5 で入口を開くには、リクエストの認証からテナント文脈を作る γ(`TSK-469`)が要る**
> (本書の依存表 6 番 と R1 は U-A1 を挙げたまま)。**`TSK-469`(γ)は `TSK-468`(β)の後で、β は PR #87 の後。**
> **入口までの最長の系統はこれ**(U-A1 担当の指摘・2026-10-04)。
>
> **したがってステップ 5 以降が待つのは `dep 4`・`dep 6`・`dep 7` の 3 本。**

> ## 【改訂 2026-10-05・改訂承認: 山田正輝】paths 登録を入口の直前へ移し、追加層の宣言ステップを足す
>
> **ステップ番号はこの改訂で付け替えた。上の 2026-10-04 の改訂ブロックの番号は旧番号**
> (旧 1 → 新 5 / 旧 2〜4 → 新 1〜3 / 旧 5〜8 → 新 6〜9 / **新 4 は追加**)。
>
> ### 何が起きたか(2026-10-05 実測)
>
> **旧ステップ 1(`core-areas.json` へ paths を足すだけ)は core-guard を通らない。**
>
> - `scripts/core_guard.py:31` の `AREA_PATH_ADDITIONS`(領域別の追加層)のキーは **`game-state` と `data-migration` だけ**。
>   `validate_area_path_layers()`(`:302-314`)は、宣言の無い領域に `{merge-base の paths}` しか許さないので、
>   **`tenant-isolation` へ 1 件足すだけで `GuardError`**
> - 宣言は `core-areas.json` より**前の別コミット**で入れる必要がある(`verify_area_path_baseline()` `:362-371` が
>   `core-areas.json` と `BASELINE_DEFINITION_PATHS` = `scripts/core_guard.py`・`tests/test_core_guard.py` の**同一コミット変更を拒否**)
> - `tests/test_core_guard.py:1617-1623` が「追加層を持つのは domain-calc の 2 領域だけ・他 3 領域は merge-base と同一」を表明しており、
>   宣言を足すとこれも破れる
>
> 旧 R6 は「同一コミットにしない」までは書いていたが、**宣言のコミットをステップ表に置いていなかった**(#74 の二層方式は本書の承認〔2026-09-24〕より後に着地)。
>
> ### 何を変えたか
>
> 1. **追加層の宣言をステップ 4 として足す**(`core_guard.py` / `test_core_guard.py` — 本書の変更範囲を広げる。**本表直後の「第 2 群を後から足すときの再承認」により敵対レビュー + 人間承認の対象**)
> 2. **paths 登録(旧 1)を新 5 へ移し、入口を開く直前に置く**。登録対象 `backend/tests/test_roster_boundary.py` を作るのは新 6 なので、前倒しする利点が無い
> 3. **新 4・5 は TSK-344 のマージと develop の取り込みの後に行う(本書の拘束)**。TSK-344 も `tenant-isolation` へ paths を足す予定で、
>    **同じ `AREA_PATH_ADDITIONS["tenant-isolation"]` の行を書く**。`validate_area_path_layers()`(`:303-314`)は**宣言の一部だけが merge-base に取り込まれた状態を拒否する**ので、
>    **先着の宣言に U-M1 の 1 件を累積すると新 4 の時点で落ちる**(敵対レビュー 2 周目 P1-2 — 仮の基線・候補で実測済み)。
>    **通る手順は「develop を取り込む → 宣言を U-M1 の未取り込み分だけに置き換える → 新 5 で JSON を merge-base ＋ その分にする」**。
>    TSK-344 以外にも同じ領域の宣言・paths を変えるブランチ(`feature/ua1-auth-db-layer` — 同計画書 `:89-90` が条件付きで変更)があるので、
>    **新 4 の着手時に、`AREA_PATH_ADDITIONS` または `tenant-isolation.paths` を変える未マージのブランチを確認し(対象 ref の範囲は内訳 4)、先着分を取り込んでから行う**
>
> ### 新 1・2 と新 6〜9 は旧 2・3 と旧 5〜8 から番号だけ変えた。新 3(旧 4)は「ステップ 3〜5 の内訳」の 3 を追加した(承認後に着地した登録機構・凍結履歴・比較 corpus への追随)

**着手の拘束**: **ステップ 1〜3 は外部依存の着地を待たない(ステップ 3 の前に draft PR を作る — 内訳 3)。ステップ 4・5 は TSK-344 のマージと develop の取り込みの後(上記の改訂 3 — 本書の拘束)。ステップ 6 以降は dep 4・6・7 の着地後**
(`/implement` は承認済み計画書を要求する)。
**総数を確定できないため、ステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **DTO を追加する** — `backend/src/pitchlog/api/schemas/roster.py`。[design.md](design.md) 4 節の全 DTO(`PlayerStatusPreview` を含む)を定義する | `backend/tests/test_roster_schemas.py` が green。値域・省略と明示 null の区別・空配列と重複 ID の扱いをテストで確認。`ruff check` / `ruff format --check` / `ty check` green |
| 2 | **入口の契約資産を追記する** — `route-registry.json` と `http-route-matrix.json`(+ lock 再封印)へ本単位の入口を登録する。**既存行の `test_owner` は書き換えない**。新規行の `test_owner.status` は **`planned`** とする。**あわせて検査器の期待集合を更新する**(`scripts/check_authz_catalog.py:2175-2186` は `record_and_aggregate` の経路を空集合で固定している — 「経路 0 件なので空集合」は登録する単位が更新する設計 — `../route-kind-vocabulary/plan.md:88`・`:150`)。`route_id` は導出規則(`:2412-2421` — `ROUTE:RECORD:<資源>:<操作>`)と操作の閉じた値域(`:2407-2411` — read / insert / update)に従う。**細部は内訳 N1・N2** | `uv run pytest -c pyproject.toml tests/test_check_authz_catalog.py` が green。registry と matrix が exact-set で一致。期待集合が本単位の `route_id` と exact-set で一致 |
| 3 | **リポジトリと operation token を追加する** — TSK-424 の capability カタログから token 型を導き、registry へ登録する。**7.7-2 の記録と比較 corpus の再封印**を同時に行う。**内訳は表の下「ステップ 3〜5 の内訳」の 3** | 内訳 3 の合格条件をすべて満たす |
| 4 | **`tenant-isolation` の追加層を宣言する** — `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` と `tests/test_core_guard.py`。**`.claude/core-areas.json` を同一コミットに入れない**。**内訳 4** | 内訳 4 の合格条件をすべて満たす |
| 5 | **`.claude/core-areas.json` へ本単位の paths を登録する** — 越境テスト `backend/tests/test_roster_boundary.py` を `tenant-isolation` の末尾へ追加する(新規リポジトリは既存の `backend/src/pitchlog/repositories/*` が覆う — `fnmatch` の `*` は `/` を跨ぐ)。**ステップ 4 の宣言と完全一致させる**。単独コミット。**内訳 5** | 内訳 5 の合格条件をすべて満たす |
| 6 | **選手の入口を開く** — 作成・一覧・取得・更新。`ROUTERS` へ登録し、`test_api_conventions.py` の述語 4(経路数)の期待値を更新する | `test_roster_boundary.py` の当該入口ぶんが green(認可行列どおりに通り行列外は 404)。`/health` `/version` を含む既存テストが green |
| 7 | **在籍区分の入口を開く** — プレビューと適用。**キャッシュ無効化の発火点**を `CacheInvalidationTrigger.ROSTER_STATUS_CHANGE` で置く | 在籍区分変更後に共有集計のキャッシュが失効することを受入テストで確認(要件書 `:996`) |
| 8 | **選手の削除ガードを実装する**(FR-018) — 紐づけゼロ判定・進行中試合の存在判定・同一トランザクション化 | 競合挿入を含む同時実行テストで、判定後に紐づいた場合に失敗すること・進行中試合があると拒否されることを確認 |
| 9 | **対戦相手チームレコードの入口を開く**(FR-039) — 作成・一覧・更新・削除。類似名の警告と削除拒否の誘導 | 試合または選手が紐づくチームの削除が拒否されること・類似名が警告で登録続行できることを確認 |


#### ステップ 3〜5 の内訳(改訂 2026-10-05 — 敵対レビュー 4 周の反映)

**3. リポジトリと operation token**

- **着手条件: ステップ 3 の前に branch を push し draft PR を作って `acceptance_id` を確定する**。`acceptance_id` は実際の PR 番号から導出され、PR 受理検査でイベント値との一致を要求される(`scripts/frozen_history.py:672`・`:685`)ので、番号を知らないままでは記録を完成できない(仮の番号はローカルで green でも受理時に落ちる)。前例は TSK-443(`../runtime-contract-switch/plan.md:80`「draft PR を作って `acceptance_id` を確定する」)。**作り方と `/pr` との両立は N3**

- **契約と生成物**: `contracts/tenant_boundary/repository-contract.json` の `product_capability_ids` / `product_operation_token_types`(`:127-128`)へ本単位の分を登録し、生成モジュール `backend/src/pitchlog/repositories/repository_contract.py`(`PRODUCT_CAPABILITY_IDS` / `PRODUCT_OPERATION_TOKEN_TYPES`)を同期する。**`cross_tenant_functions` は空のまま**
- **実行 registry**: `repositories/base.py` の `_OPERATION_REGISTRY` を契約と exact-set で一致させる
- **登録文の検証**: `backend/src/pitchlog/authz/capability_registration.py`(`:1195-1269` — カタログの ID・表・操作との照合)に通す
- **空を表明する既存テストの更新**: `backend/tests/test_authz_capability_registration.py:1022-1027`(`test_product_registries_remain_empty`)・`backend/tests/test_authz_repository_contract.py:407-417`
- **凍結基準の記録(7.7-2)**: `repository-contract.json` 側は `baseline_control` の `contract_revision` と `current_identifiers` を同期し、**既存 history は保持する**(非権威資産への履歴の追記は拒否される — `scripts/frozen_history.py:492-519`)。
  **追加の記録は権威履歴(`contracts/tenant_boundary/base-allowlist.json` の `baseline_control.history`)へ 1 件だけ**置き、影響を受ける凍結資産の全件・変更前後の snapshot・生成モジュールの digest を同期する(様式は設計書 `:584-608`)。
  **記録はステップ 3 のコミット時点で、draft PR の番号とその時点の比較元に対して完全に書く**(識別値を未記入にする・revision だけ動かす形は検査が通らない)
- **比較 corpus の再封印**: `contracts/tenant_boundary` は比較 corpus の入力 tree(`tests/fixtures/frozen-archive-cases/manifest.json:16-18`)なので、`history-snapshots/` と manifest の digest を再導出する
- **再導出の時点**: PR の受理検査は event の `base.sha` と二親 merge で評価する(`scripts/check_tenant_boundary_bypass.py:6163`・`scripts/frozen_history.py:1185`)。**PR 直前の develop 取り込み時に再導出・再検証し、PR 作成後に base が進んだら再度行う(コミット先は N4)**
- **前版の結果照合**: `tests/test_frozen_archive_case_runner.py` は現版だけを実行する(`:414`)ので、再封印時に runner(`tests/fixtures/frozen-archive-cases/runner.py`)を `--checker previous=<前版> --checker current=<現版>` で両方当て、**全ケースで manifest の期待値と一致する**ことを確かめる。前版の作業木は固定 SHA・detached・清潔であること(`runner.py:1034`)
- **合格条件**: 前版・現版の全ケース一致(上)。`backend/tests/test_authz_repository_contract.py`(資産と生成モジュールの一致 `:303-309` を含む)・`backend/tests/test_authz_capability_registration.py`・`tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py`・`tests/test_frozen_archive.py`・`tests/test_frozen_archive_case_runner.py` が green。カタログ外の ID・表・操作が拒否される負例が green

**4. 追加層の宣言**

- **着手条件**: TSK-344 のマージ後、develop を取り込んでから行う(上の改訂 3)。着手時に `git fetch origin` し、**`origin/feature/*`・`origin/fix/*` とローカルの `refs/heads/*`(`git worktree list` の全 worktree を含む — 未 push の競合を落とさないため)のうち、`scripts/core_guard.py` の `AREA_PATH_ADDITIONS` または `.claude/core-areas.json` の `tenant-isolation.paths` を変える未マージの ref とその SHA を worklog に記録する**。未マージの競合は順序調整の対象(該当タブへ連絡)であり、宣言の基線へ取り込むのは **develop に着地した変更だけ**。ステップ 5 と PR の前に同じ確認を繰り返す
- **逐行確認**: `scripts/core_guard.py`・`tests/test_core_guard.py`・`.claude/core-areas.json` はいずれも最上位 `guard_paths` に該当する(`:466`)。本単位の PR は元から逐行確認が必須なので、ステップ 4・5 で手続きは増えない
- **宣言**: `AREA_PATH_ADDITIONS["tenant-isolation"]` を **U-M1 の未取り込み分だけ**(`("backend/tests/test_roster_boundary.py",)`)にする。先着ブランチの宣言は**累積せず置き換える**(部分取り込みは `scripts/core_guard.py:303-314` が拒否)
- **テスト**: `tests/test_core_guard.py` の「宣言領域・未宣言領域」を固定する表明(`:1497`・`:1544`・`:1617-1623`)を更新する。**意図した宣言の exact-set をテスト側に独立して残す**(`set(AREA_PATH_ADDITIONS)` を実装から読んで許す形にしない)。**部分追加・並べ替え・削除・未宣言の追加の 4 種を直接試す負例**を足す(部分追加・並べ替えは複数パスを宣言した合成例で試す)
- **検査器の性質の正確な記述**: 宣言後も、JSON が merge-base のままの状態は検査器が許す(`:310`)。**登録の欠落は検査器では検出しない** — ステップ 5 の独立確認で検出する
- **合格条件**: `uv run pytest tests/test_core_guard.py` が green。**ステップ 4 のコミット SHA に対して `uv run python -c "import sys; from pathlib import Path; sys.path.insert(0, 'scripts'); import core_guard; print(core_guard.verify_area_path_baseline(Path('.'), '<origin/develop の SHA>', '<ステップの SHA>'))"`(リポジトリルートで。base SHA・ステップ SHA・戻り値〔merge-base の OID〕を worklog に記録) を実行し、例外なく戻ることを確かめる**(PR の CI は最終 head しか検査せず、ローカルの `core_guard.py` は PR event が無いと skip するため — `.github/workflows/ci.yml:55`・`scripts/core_guard.py:499`)

**5. paths の登録**

- **合格条件**: 内訳 4 と同じコマンドをステップ 5 の SHA に対して実行し、例外なく戻る(worklog に記録)。**独立確認として、実際の `tenant-isolation.paths` が「merge-base の列 ＋ `backend/tests/test_roster_boundary.py` の 1 件」に一致することを確かめる**。`uv run pytest tests/test_core_guard.py` が green。PR 本文に 6.3-⑤ の審査対象として明示する



#### 実装時に原典で決める事項(N1〜N4 — 改訂 2026-10-05・PO 裁定「ステップ 2・3 の詳細は実装時に詰める」)

**計画書では方針だけを固定し、手順の細部は当該ステップの委任時に原典で決めて design.md と worklog に記録する。**
**計画時に固定しない理由**: 対象の検査器・凍結履歴の機構は他タスク(TSK-431・TSK-344 ほか)が並行して動かしており、
2026-09-24 の計画書が承認後 11 日で 3 箇所陳腐化した(capability の登録機構・`core_guard.py` の二層方式・`record_and_aggregate` の期待集合)。
**手順を今固定すると実装時にはずれている見込みが高く、固定した手順の正しさは計画レビューでは閉じない**(敵対レビュー 4 周で毎周新種が出た)。

| # | 事項 | 方針(本書で固定) | 決める時点 | 受入証跡 |
| --- | --- | --- | --- | --- |
| **N1** | **入口ごとの `route_id` と操作の対応** | 導出規則 `ROUTE:RECORD:<資源>:<操作>` と操作の値域 read / insert / update に従う。**削除系の入口(FR-018 の非表示化・FR-039 の削除)は論理削除なので update に写す**(AGENTS.md「削除はすべて論理削除」)。**同じ資源・同じ操作の入口が複数ある場合(一覧と取得はどちらも read)、導出規則上 `route_id` が衝突しうるので、1 経路への集約か規則の扱いかを原典(`route_id` の一意性の検査・HTTP 行列との対応)で確かめて決める**。design.md の入口表(`:54` で未定)を埋める | ステップ 2 の委任前 | design.md の入口表に全入口の `route_id` と操作が載り、ステップ 2 の合格条件が green |
| **N2** | **検査器の期待集合の更新範囲** | `scripts/check_authz_catalog.py` の `_validate_record_and_aggregate_route_ids` の期待集合と、対応する `tests/test_check_authz_catalog.py` の表明・負例を、ステップ 2 のコミットで本単位の `route_id` へ更新する。**期待集合を registry から読む形にしない**(独立した exact-set を残す)。両ファイルは `.claude/core-areas.json` の**最上位 `guard_paths`** に該当し(`scripts/core_guard.py:466` の完全一致)、PR 本文の逐行確認チェックを要求する(本単位はコア領域なので要求は元から掛かる — 追加の手続きは生じない) | ステップ 2 の委任前 | ステップ 2 の差分に検査器とテストが含まれ、期待集合外の `route_id` が拒否される負例が green |
| **N3** | **`acceptance_id` を得るための早期 PR の作り方と、`/pr` との両立** | **ステップ 3 の前に PR 番号を確定する**(内訳 3)。**前例は #87(TSK-443)**: 2026-09-29 に PR を先に作り(ステップ 5/8 の時点)、2026-10-04 に `/pr` のクローズ処理を行ってから ready 化した(`docs/worklog/2026-09-26-runtime-contract-switch.md:60-76`)。ただし **`/pr` の文面は「PR 作成の唯一の入口」で、既存 OPEN PR の扱いを差し戻し後の再レビューに限っている**(`.claude/skills/pr/SKILL.md:2`・`:53`)ので、前例の流れは文面上の規定外である(敵対レビュー 5 周目 P1)。**ステップ 3 の前に人間へ確認し、(a) 前例どおり進めてよいか (b) `/pr` 側の改訂が要るか(要るならハーネスのタスクとして別に起票し、本単位では `/pr` を改訂しない)を決める**。draft 中は core-guard が逐行確認欄の未記入で red になる(想定内 — 確認は最新 HEAD に対して最後に行う。`docs/development/github-setup.md:60-61`) | ステップ 3 の前(**人間の判断を経てから PR を作る** — PR の作成は外部へ出る操作) | 人間の判断(a / b)と、PR 番号・作成時の base SHA が worklog にある。ステップ 3 の記録の `acceptance_id` が実番号と一致。**最終のクローズ処理が同じ PR で完了している** |
| **N4** | **base が凍結資産ごと進んだときの再封印のコミット先** | **ステップ 3 の是正コミット**として行う(件名は `(ステップ 3 再導出)` — 付記つきの完全トークン。前例 `134bd39b`「(ステップ 4/8 是正)」)。記録・snapshot・corpus の digest を新しい base に対して再導出し、内訳 3 の合格条件を再度満たす。**TSK-431 など同じ資産群を触るタスクの着地を検知したら必ず行う** | PR 作成後に base が進むたび | 再導出コミットと、そのときの base SHA・合格条件の結果が worklog にある |


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
- [ ] **凍結基準の記録(7.7-2)が権威履歴に 1 件あり、PR の base に対して再導出・再検証済み**。比較 corpus の digest が再封印済み(4 節 内訳 3 — 改訂 2026-10-05)
- [ ] **追加層の宣言(ステップ 4)と paths 登録(ステップ 5)が別コミット**で、各 SHA に対する `verify_area_path_baseline()` の green が worklog にある。`tenant-isolation.paths` が「merge-base ＋ 1 件」に一致(内訳 4・5)
- [ ] **同領域の宣言・paths を変える未マージ ref の確認記録**(確認した ref と SHA)がステップ 4・5・PR 前の 3 時点で worklog にある

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

**ハーネス側(リポジトリルートで — 改訂 2026-10-05 で追加)**: ステップ 3〜5 で `uv run pytest tests/test_core_guard.py tests/test_check_tenant_boundary_bypass.py tests/test_frozen_history.py tests/test_frozen_archive.py tests/test_frozen_archive_case_runner.py`。ステップ 4・5 は各コミット SHA に対する `verify_area_path_baseline()` の結果を worklog に記録する(4 節 内訳 4・5)

**迂回検査は実装スケルトンの段階で当てる**:
`uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`

## 7. リスク

| # | リスク | 対応 |
| --- | --- | --- |
| **R1** | 入口を開くのに**外部所有者が 5 者**(TSK-424 PR A / PR C・TSK-344・`route_kind` 値域〔**解消済み** — PR #77〕・**U-A1**(ブロック中)・在籍区分キーの別タスク)。1 つでも動かないとマージできない | 着地状況を /pr の前に再確認する。空席の所有者は 8 節で人間へ上げる |
| **R2** | `test_owner.status: "implemented"` は**ハーネス側 `tests/` の node ID** としか照合されない(`scripts/check_authz_catalog.py:2674-2685`) | 新規行は **`planned` 止まり**(ステップ 2 の合格条件) |
| **R3** | `players.team_record_id` は immutability の**未分類列**(handoff `TSK-372`)。所属チーム変更の可否がコードから読めない | `PlayerUpdate` の更新対象に含めない。必要になれば TSK-372 へ上げる |
| **R4** | **capability 登録は凍結基準を動かす**(`repository-contract.json` が `FROZEN_BASELINE_ASSETS`)。**TSK-431 が同じファイル群を触る** | ステップ 3 で **7.7-2 の記録**(権威履歴へ 1 件)と比較 corpus の再封印を同時に行い、**PR 直前の取り込みと base の前進のたびに再導出する**(4 節 内訳 3)。TSK-431 と順序を調整する |
| **R5** | API 層は `api/**` の**全ソース連結**に対する部分一致検査を受け、**`Session`・`generation` を docstring・コメント含め書けない**(`backend/tests/test_api_conventions.py:22-37`)。**TB004 は AST 上の識別子検査**で範囲が異なる(`scripts/check_tenant_boundary_bypass.py:2672`) | [design.md](design.md) D5 で 2 つの検査を**分けて**記述し、命名を実装前に固定する |
| **R6** | **`core-areas.json` を編集する**ため **#74 の `verify_area_path_baseline()`** が掛かる。`core_guard.py` / `test_core_guard.py` と同一コミットにすると、**後から revert しても打ち消せず force-push も `git_guard.py` が拒否する** | **追加層の宣言(ステップ 4)と paths 登録(ステップ 5)を別コミットにする**。旧版は宣言のステップを置いていなかった(改訂 2026-10-05) |

## 8. 人間の判断を仰ぐ事項

| # | 事項 | 本書の扱い |
| --- | --- | --- |
| **1** | **フロントエンド実装の帰属** — 単位分割の正本に「フロントエンド」「Vitest」「Vue」の語が **1 件も無い**(実測)。`:60` が各単位へ送るのは **UI の「設計正本」**であって実装ではない。**FR-015/017/018/039 の UI 面の受け皿が正本上空席** | **U-M1 は射程外**として線を引いた。受け皿の決定を仰ぐ |
| **2** | **FR-015 の同期面の帰属** — 分担表に FR-015 の行が無く、「面が切れなかったときの手順」の対象外。正本上は **U-M1 の単独主所有**のまま | 帰属表を更新せずに U-S1 へ移さない。判断を仰ぐ |
| **3** | **`route_kind` の値域決定の所有者** — `TSK-380` の射程は既存 37 経路の `test_owner` 再割り当てであり、**値域拡張は空席**(**2026-09-24 時点の記述**) | **解消済み(2026-10-04 訂正 — 4 節の外部依存 5)**。TSK-446 / PR #77 が 2026-09-25 にマージ済み |
| **4** | **在籍区分キーの値と seed の別タスク起票** — `active` のみ `data-model.md:524` に典拠。`other`/`ob` はリポジトリ内に文字列が存在しない。seed は **5 領域すべてのコア paths** で契約 3 の例外に U-M1 は含まれない | 別タスクへ切り出す前提で本書から外した。起票の可否を仰ぐ |
| **5** | **Notion カードのコア判定が正本より古い** — **葉 6 本すべてが同型**と見られる(TSK-394 で確認) | TSK-393 のカードには訂正コメントを入れる。**他タスクのカードには触れない** |
| **6** | **改訂 2026-10-05 の承認**(ステップ 4 の追加と番号の付け替え — 4 節の改訂ブロック)。あわせて **7.7-2 の記録の承認値**(承認者・承認日)はステップ 3 の実装時に人間へ確認する | 計画レビュー後に人間の承認を仰ぐ。承認までステップ 1 以降を実装しない。**N1〜N4 は各時点で決めて記録する(PO 裁定 2026-10-05)** |
