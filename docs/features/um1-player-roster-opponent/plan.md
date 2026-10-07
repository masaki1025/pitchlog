---
feature: um1-player-roster-opponent
status: active
承認: 済(2026-10-07・山田正輝 / 第 3 改訂 — 第 2 改訂・第 1 改訂 2026-10-05・初版 2026-09-24)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..
notion: https://app.notion.com/p/3da93b75e687812eb946c4a8cf5fc1a7
branch: feature/um1-player-roster-opponent
created: 2026-09-24
計画レビュー周回: 10       # 敵対レビュー 1 周目(判定 否決・P0 16 / P1 6 / P2 1)/ 改訂 2026-10-05 の 1 周目(否決・P1 3 / P2 2)・2 周目(否決・P1 3 / P2 3)・3 周目(否決・P1 2 / P2 4)・4 周目(否決・P1 3 — PO 裁定で N1〜N4 へ)・5 周目(否決・P1 1〔N3〕/ P2 1)/ 第 2 改訂の 1 周目(否決・P1 4 / P2 1)・2 周目(否決・P1 1 / P2 1)/ 第 3 改訂の 1 周目(否決・P0 2 / P1 2)・2 周目(否決・P1 2)の反映を含む
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
| `scripts/core_guard.py` / `tests/test_core_guard.py`(**改訂 2026-10-05 で追加**) | `AREA_PATH_ADDITIONS["tenant-isolation"]` の宣言と表明の更新(4 節 ステップ 6)。`BASELINE_DEFINITION_PATHS` のため `core-areas.json` と別コミット | PR レビュー |
| `contracts/authz/route-registry.json` / `http-route-matrix.json` (+ lock) | **追記**(`route_kind` の値域は PR #77 で決定済み — `record_and_aggregate`) | PR レビュー |
| `contracts/authz/oracle-seal.lock.json` / oracle 資産(`oracle_commit` 7 箇所)/ `contracts/authz/frozen-baselines.json` / `scripts/check_authz_catalog.py` / `tests/test_check_authz_catalog.py`(**第 2 改訂で追加**) | route-registry と HTTP 行列が oracle 封印の入力資産のため、oracle の追随・凍結基準の記録(series `oracle_input`)・`--reseal-oracle` による再封印。検査器の期待集合の更新(4 節 ステップ 2〜4) | 7.7 の更新経路・**人間の確認**(`reseal_policy`) |
| `contracts/tenant_boundary/repository-contract.json` | **capability 登録**。**`FROZEN_BASELINE_ASSETS` の 1 つ**(`scripts/check_tenant_boundary_bypass.py:41`)なので**設計書 7.7-2 の記録が要る** | 7.7 の更新経路 |
| `contracts/tenant_boundary/base-allowlist.json`(権威履歴)/ 履歴 snapshot / `tests/fixtures/frozen-archive-cases/manifest.json`(**改訂 2026-10-05 で追加**) | 7.7-2 の記録 1 件・snapshot・比較 corpus の digest 再封印(4 節 ステップ 5 の内訳) | 7.7 の更新経路 |
| `contracts/tenant_boundary/tenant-context-allowlist.json` / 配布モジュール `backend/src/pitchlog/repositories/tenant_context_contract.py` / `scripts/check_tenant_boundary_bypass.py` / `tests/test_check_tenant_boundary_bypass.py`(**第 3 改訂で追加**) | 発行専用モジュールの登録と発行入口の 2 欄・0 件必須の分岐の置き換え・テストの改訂(4 節 ステップ 9)。受理記録はステップ 10。allowlist は凍結資産で、検査器は `frozen_projection.external_files` に入る | 7.7 の更新経路(受理記録はステップ 5 の分と合わせて 1 件)・**人間の逐行確認** |
| `.env.example`(**第 3 改訂で追加・該当するときだけ**) | リクエストの認証の設定値を持つ場合に、名前と説明だけを足す(実値なし — NFR-014。N6) | PR レビュー |
| `docs/design/data-model.md` / `docs/features/ua1-team-auth/design.md`(**第 3 改訂で確認 — 反映なし**) | **反映なし**。12-8 節の残件の行は δ を「認証の HTTP の入口」の受け取り先としており、データへ届く入口のリクエストの認証を名指していない。`../ua1-team-auth/design.md` 3 節の δ の行(Cookie と CSRF)は作業ディレクトリの記録で、正本ではない。**帰属の変更(依存表 12)は本書と Notion(TSK-470 へのコメント)に記録する** | — |
| `docs/features/um1-player-roster-opponent/design.md` | **新設**(暫定規約・入口表・DTO 定義)。**第 3 改訂で追記**: リクエストの認証の細部(N6)・発行専用モジュールの名前と置き場(N7) | PR レビュー |

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
| 6 | **検証済みのテナント ID を返す公開入口**(署名照合 → `authn.verify_token()` → 非 NULL の `tenant_id`) | **U-A1 γ(TSK-469)** | **ステップ 9 の着手条件 — develop に着地済みであること**。**第 3 改訂で書き換え**: 旧記述「`TenantContext` の生成 = U-A1」は裁定 b'(2026-10-05)で分かれた — γ は**検証済みのテナント ID を返すところまで**、`TenantContext` の生成箇所は U-M1 ステップ 9(発行専用モジュールが γ の公開入口を内部で呼ぶ — 内訳 9)(`../ua1-auth-app-layer/plan.md` 4-7 節 — 未マージのブランチ上)。**ログアウトの保護された入口は γ が持つ**(裁定 ⑫・利用者の裁定 (ア) 2026-10-07 — U-M1 はログアウトの入口を持たない) |
| 7 | **在籍区分キーの値と seed** | **別タスク**(8 節) | 未起票 |
| 8 | **複数表の不変条件の実行単位** — 入口 **#7**(FR-018 の削除ガード)・**#11**(FR-039 の削除ガード)・**#6**(FR-017 の一括変更)は**複数表にまたがる判定を 1 トランザクションで**行う必要がある | **TSK-444(PR C)** | 未着手。**2026-09-24 に当方の指摘を受けて射程へ取り込まれた** |
| 9 | **無効化意図の ID 導出規則と原子性の錨** — `contracts/tenant_boundary/cache-invalidation-contract.json` の `durable_intent` は `intent_id_derivation: ["target_event_v10","target_confirmed_version"]` と `same_transaction_with: "T7"` を**トリガー別の分岐なしで 14 件すべてに掛けており**、**イベント由来でない 7 トリガー**(在籍区分の変更を含む)に適用できない | **TSK-447** | 未着手。**U-M1 側で暫定規約を決めない**(他のトリガー所有単位と割れるため) |
| 10 | **`system_vocabularies` を参照する FK への category の拘束**(`fk_players_roster_status` ほか 3 本) — 着地前に選手の入口を開くと、在籍区分の列に試合区分のキーが入りうる状態になり、入口を開いた後からは回復できない | **TSK-480**(ブランチ `feature/vocab-category-fk`・正本は実装追随の PR レビューで版据え置き — 【裁定 2026-10-06・山田正輝】`../vocab-category-fk/plan.md` 3 節。**第 3 改訂で訂正**: 旧記述「確定ゲートの対象」は同裁定の前の記述) | **ステップ 9 の着手条件 — develop に着地済みであること**(480 タブの依頼 2026-10-06。第 3 改訂の番号)。U-M1 側のコード変更は要らない見込み(新しい列は既定値付き・FK は同名で張り替え・migration `0029_system_vocab_category_fk`) |
| 11 | **TenantContext の発行の機構と検査器**(公開 constructor の封じ・capability 型・検査器の新しい規則・負例) | **TSK-457**(235 タブ) | **ステップ 9 の着手条件 — develop に着地済みであること**(第 3 改訂の番号)。人間の裁定(2026-10-05)で、発行専用モジュールの実体・生成許可への登録・生成箇所・7.7 の受理記録は U-M1 に残る。**第 3 改訂でステップ 9(発行・登録・生成箇所)と 10(受理記録)に取り込んだ**(受け取る項目の一覧は TSK-457 の計画書 4-3 節「U-M1 ステップ 8 に渡るもの」— 未マージのブランチ上・同書の「ステップ 8」は第 2 改訂の番号) |
| 12 | **リクエストの認証**(Cookie から提示値を取り出す・CSRF の検査 — 方式は H-2 で決定済み: Cookie は `HttpOnly`・`Secure`・`SameSite=Strict`、CSRF はカスタムヘッダの必須化 + `Origin` の検査。`../ua1-team-auth/design.md` C-4 末尾・3 節) | **U-M1 自身(ステップ 8)** — **【裁定 2026-10-07・山田正輝】δ(TSK-470)から U-M1 へ移す** | **第 3 改訂で追加**。旧来の受け取り先は δ だったが、δ は γ と TSK-344 の後で、しかもレート制限の具体設計(要件書 10 章の相談)を待つ。最初にデータへ届く入口はステップ 9 なので、U-M1 が先に持つ。**Cookie の名前など、H-2 の決定に含まれない細部も U-M1 が先に決め、δ が後から合わせる**(R7) |

> **【承認後の追記 — 2026-09-24】** 上表の **8・9 は承認(2026-09-24)後に判明した外部依存**である。
> **射程・DoD・実装ステップは変えていない**(依存の記録のみ)。
>
> **経緯**: `TenantRepositoryBase._execute_operation` は `_tenant_transaction` の中で 1 文だけ実行し、
> `repositories/binding.py` が「**同一 Session へテナント文脈を再束縛できない**」を課すため、
> **同一 Session では `execute()` を 2 回呼べない**(実測)。
> 一方 TSK-424 の capability カタログ(74 件・`CAP:<table>:<operation>`)は **1 operation = 1 表**を強制する。
> この 2 つが重なると **FR-018 と FR-039 の削除ガードが構造的に実装できない**。
> **TSK-444 が実行単位を、TSK-447 が意図 ID と原子性の錨を引き取った**(2026-09-24・セッション間の調整)。

> **【承認後の追記 — 2026-10-06】** 上表の **10・11 は第 2 改訂の承認(2026-10-05)後に判明した外部依存**である。
> **射程・DoD・実装ステップは変えていない**(依存の記録のみ)。ステップ 8 の射程の変化(裁定 b' と TSK-457 の射程の裁定)は**第 3 改訂**で扱う(作業ログ 2026-10-05 夜の節)。

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

> ## 【第 2 改訂 2026-10-05・改訂承認: 山田正輝】ステップ 2 を 3 本に分け、oracle の追随と再封印を足す
>
> **番号は第 1 改訂(上のブロック)からさらに付け替えた**: 第 1 改訂の 3 → 5 / 4 → 6 / 5 → 7 / 6〜9 → 8〜11。**新 3・4 は追加**。
> 上の 2 つの改訂ブロックの番号はそれぞれの時点の番号である。
>
> ### 何が起きたか(2026-10-05 実測 — 検査を実際に当てて確認)
>
> `contracts/authz/route-registry.json` と `http-route-matrix.json` は **oracle 封印(`contracts/authz/oracle-seal.lock.json`)の入力資産**で、
> blob digest で固定されている(`input_assets` 8 件)。**経路を 1 本足し、検査器の期待集合と HTTP 行列を合わせ、`--reseal-derived --skip-oracle` で派生 lock を作り直しても、
> 通常の検査は `contracts/authz/route-registry.json: oracle input blob が不一致` で落ちる**(作業ツリーで一時的に変更して実測し、元に戻した)。
> 封印の作り直しは `--reseal-oracle` 専用で人間の確認が要る(`reseal_policy`: `normal_validation_reseals: false` / `human_review_required: true`)。
> **前例は #77(TSK-446)**: 派生 lock の再封印 → oracle の内容追随と 7 箇所の `oracle_commit` 差し替え → 敵対レビューと人間確認 → `contracts/authz/frozen-baselines.json` への記録(series `oracle_input`・`acceptance_id` = PR 番号)と再封印、を別ステップで行った(`../route-kind-vocabulary/plan.md:170-173`・コミット `fb71c300`)。
>
> ### 何を変えたか
>
> 1. **ステップ 2 を「契約資産・検査器・派生 lock」にまとめ、oracle の追随(新 3)と記録・再封印(新 4)を足す**。新 3 は前段(新 2)のコミット SHA を `oracle_commit` に書くので、新 2 と同じコミットにできない
> 2. **PR 番号が要る時点が新 4 へ早まった**(oracle_input の記録の `acceptance_id`)。N3 の判断はステップ 4 の前に行う。新 5(リポジトリ)の tenant_boundary の記録も同じ PR 番号を使う
> 3. **N1・N2 を決めた**(下の N 表と [design.md](design.md) 3 節)
> 4. 登録したパスに実ファイルが当たる確認を、**ファイルを作るステップ(新 8)の合格条件**に置く(TSK-344 の計画レビューで見つかった型 — 登録だけ先に入ると空振りの glob のまま進む窓が空く)

> ## 【第 3 改訂 2026-10-07・改訂承認: 山田正輝】第 2 改訂のステップ 8 を 3 本に分け、リクエストの要求面・`TenantContext` の発行と入口の開放・受理記録の 1 件化を置く
>
> **番号は第 2 改訂からさらに付け替えた**: 第 2 改訂の 8 → 9(発行の追加とあわせて) / 9〜11 → 11〜13。**新 8・10 は追加**。ステップ 1〜7 は番号も内容も変えない。
> 上の 3 つの改訂ブロック・承認後の追記・作業ログの「ステップ 8」は、それぞれの時点の番号である(第 2 改訂の 8 = 本改訂の 9)。
>
> ### 何が起きたか
>
> 第 2 改訂の承認(2026-10-05)の後に、ステップ 8(選手の入口を開く)の射程を変える裁定が 3 つ出た。
>
> | | 裁定 | ステップ 8 への効き方 |
> | --- | --- | --- |
> | 1 | **裁定 b'(2026-10-05・山田正輝)** — `TenantContext` の生成箇所・`allowed_product_modules` への登録・7.7 の受理記録・検査器の 0 件必須の解除を、γ(TSK-469)から**最初の入口を開く U-M1** へ移す(`../ua1-auth-app-layer/plan.md` 冒頭の裁定ブロック・4-7 節) | 生成箇所・登録・記録・0 件必須の解除が増える |
> | 2 | **TSK-457 の射程の裁定(2026-10-05・山田正輝)** — 発行の機構と検査器の新しい規則は TSK-457、発行専用モジュールの実体・登録・生成箇所・7.7 の受理記録は U-M1(TSK-457 計画書 3 節「やらないこと」・4-3 節) | 発行専用モジュールを U-M1 が作る。0 件必須の分岐の置き換えとそのテストの改訂も U-M1(同 4-3 節の 1〜5) |
> | 3 | **リクエストの認証の帰属(2026-10-07・山田正輝)** — Cookie から提示値を取り出し CSRF を検査する部分を、δ(TSK-470)から **U-M1** へ移す(依存表 12) | 要求面(Cookie・CSRF)を U-M1 が作る |
>
> あわせて、**ログアウトの入口は γ が持つ**(利用者の裁定 (ア) 2026-10-07)ので U-M1 の射程に入らない(依存表 6)。
>
> **受理記録は 1 PR につき 1 件**(`contracts/tenant_boundary/base-allowlist.json` の `intermediate_commits_are_records: false`)。#95 はステップ 5 で 1 件持っている。
> ステップ 9 で `tenant-context-allowlist.json` と検査器が動くので、**ステップ 5 の記録を、ステップ 5 と 9 の両方の変更を覆う 1 件へ導出し直す**(2 件目を足すと red)。
>
> **data-model.md v0.6(TSK-382・2026-10-06 承認・PR #98 で develop へ着地)が 12-4 の「実スキーマ」を定義した**。入口を開く本 PR の 12-4 の判定記録(通過条件 ①②)を、v0.6 の 4 要件と「判定の記録」行の必須項目に照らして書けるようになったので、DoD に足す。
>
> ### 何を変えたか
>
> 1. **新 8 = リクエストの要求面**。Cookie(H-2 の属性)から提示値を**不透明な値のまま**取り出し、状態を変える要求で CSRF(カスタムヘッダの必須化 + `Origin` の検査)を検査する。**提示値を分解せず、γ も呼ばず、`TenantContext` も作らない**。外部依存を待たない
> 2. **新 9 = `TenantContext` の発行と選手の入口の開放(1 コミット)**。発行専用モジュールの発行関数が**提示値を受け取り、モジュールの中で γ の公開入口を呼び**、照合を通ったテナント ID からだけ `TenantContext` を作る。`tenant-context-allowlist.json` への登録・検査器の 0 件必須の分岐の置き換え・配布モジュールの追随と、選手の入口(作成・一覧・取得・更新)の配線・`ROUTERS` への登録を**同じコミット**に置く。DTO の `name` の空文字の扱いを token と揃える(ステップ 5 の持ち越し P2)
> 3. **新 10 = 受理記録の 1 件化と比較 corpus の再封印**。ステップ 9 の SHA を受けて、#95 の記録を導出し直す
> 4. **外部依存の表**: 6 を γ の公開入口へ書き換え、10(TSK-480)の正本ゲートの記述を訂正し、12(リクエストの認証)を足す。**着手条件の番号を付け替えた**
> 5. **N6・N7 を足した**(Cookie の名前など δ が決めるはずだった細部 / 発行専用モジュールと発行関数の名前)
>
> ### 区切り方の理由(計画レビュー 1 周目の反映)
>
> - **発行関数が提示値を受け、γ を内部で呼ぶ**: γ の公開入口 `verify_tenant_id` は通常の `UUID | None` を返す(`../ua1-auth-app-layer/` の実装 — 未マージのブランチ)。発行関数がその戻り値を受ける形では、**生の UUID と区別できず、署名を照合していない ID を発行関数へ渡せてしまう**(1 周目 P0)。**提示値 → γ → `TenantContext` を発行専用モジュールの中で閉じれば、発行関数の外に検証済みのテナント ID が現れない**。γ の戻り値の型を変える必要もない
> - **登録と入口の開放を同じコミットにする**: U-T1 は「製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる」(`../tenant-boundary-enforcement/design.md` 2 節の機構表「未検証の明示」行)。**この規律は受理記録の数え方とは別で、途中コミットにも掛かる**(1 周目 P0)。したがって**登録した製品モジュールが入口より先に存在するコミットを作らない**
> - **受理記録を別ステップに分ける**: 前例はステップ 2〜4(資産の変更 → oracle の追随 → 記録と再封印)。記録は確定した SHA を参照するので、変更と同じコミットに置くと作り直しが要る。ステップ 9 の SHA では凍結履歴の検査が期待どおり落ち、ステップ 10 で解消する
> - **新 8 を分ける**: 新 8 は外部依存を待たない。新 9 と同じコミットにすると、γ・TSK-457・TSK-480 を待つ間、新 8 も止まる


**着手の拘束**: **ステップ 1〜3 は外部依存の着地を待たない。ステップ 4 の前に PR 番号を確定する(N3 — 人間の判断を経てから PR を作る)。ステップ 5 はステップ 4 と同じ PR 番号を使う。ステップ 6・7 は TSK-344 のマージと develop の取り込みの後(第 1 改訂の 3 — 本書の拘束)。**
**第 3 改訂の番号で: ステップ 8 は外部依存を待たない(ステップ 7 の後)。ステップ 9 以降は dep 4・6(γ)・7・10(TSK-480)・11(TSK-457)の develop 着地後**
(`/implement` は承認済み計画書を要求する)。
**総数を確定できないため、ステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **DTO を追加する** — `backend/src/pitchlog/api/schemas/roster.py`。[design.md](design.md) 4 節の全 DTO(`PlayerStatusPreview` を含む)を定義する | `backend/tests/test_roster_schemas.py` が green。値域・省略と明示 null の区別・空配列と重複 ID の扱いをテストで確認。`ruff check` / `ruff format --check` / `ty check` green |
| 2 | **入口の契約資産を追記する** — `route-registry.json` と `http-route-matrix.json` へ本単位の経路 6 本を登録し、**派生 lock を `--reseal-derived --skip-oracle` で作り直す**(oracle 封印には触れない)。**既存行の `test_owner` は書き換えない**。新規行の `test_owner.status` は **`planned`** とする。**あわせて検査器の期待集合を更新する**(`scripts/check_authz_catalog.py:2175-2186` は `record_and_aggregate` の経路を空集合で固定している — 「経路 0 件なので空集合」は登録する単位が更新する設計 — `../route-kind-vocabulary/plan.md:88`・`:150`)。`route_id` は導出規則(`:2412-2421` — `ROUTE:RECORD:<資源>:<操作>`)と操作の閉じた値域(`:2407-2411` — read / insert / update)に従う。**`route_id` と期待集合は N1・N2(決定済み)** | `uv run pytest -c pyproject.toml tests/test_check_authz_catalog.py` のうち oracle 封印に依存しない検査が green。**封印入力の許容差分を固定列挙しているテスト(`tests/test_check_authz_catalog.py:4997-5025`)へ `http-route-matrix.json` とその lock を加える**。**期待失敗の集合は全件実行で確定して worklog に列挙し、ステップ 3・4 で解消されることを各ステップで確かめる**(封印の不一致が中心 — 事前に列挙しきらない)。派生 lock の `entries` が追加 6 行だけ増え、既存行の判定が不変。registry と matrix が exact-set で一致。期待集合が本単位の `route_id` と exact-set で一致 |
| 3 | **oracle の内容を追随させ、人間の確認を受ける** — ステップ 2 のコミット SHA を `oracle_commit`(封印 1 + oracle 資産 6 — 前例 `../route-kind-vocabulary/plan.md:171`)へ差し替え、経路の追加に伴う oracle 資産の内容の追随を行う(範囲は**内訳 3**)。**`oracle_commit` の変更で blob が変わる `ddl-elements.json`・`claim-mutant-map.json` を参照する `failure-injection-points.json`・`mcdc-map.json` の digest も追随させる**(`--reseal-oracle` は両資産を更新しない — 前例 `../route-kind-vocabulary/plan.md:172` の 5b)。**このステップで敵対レビューと人間の確認を受ける**(`review_policy` `ORACLE_STEP5_REREVIEW`) | 差分が人間の確認を受けた記録が worklog にある。`scripts/check_failure_injection_points.py`・`scripts/check_mcdc_map.py` が green。**期待失敗は封印の不一致と、`boundary-proposal` 検査による凍結台帳の最新 `oracle_input` との不一致(`scripts/check_authz_catalog.py:6520-6531`)** — いずれもステップ 4 で解消 |
| 4 | **凍結基準の記録と oracle の再封印** — `contracts/authz/frozen-baselines.json` へ series `oracle_input` の記録を 1 件(`acceptance_id` = 本 PR — **ステップ 4 の前に N3**)追記し、`--reseal-oracle` で再封印する。前例 `fb71c300` | `uv run python scripts/check_authz_catalog.py` が ok。`tests/test_check_authz_catalog.py`・`tests/test_check_authz_catalog_spec.py`・`tests/test_frozen_baseline_*.py`・`tests/frozen_negatives/` が green |
| 5 | **リポジトリと operation token を追加する** — TSK-424 の capability カタログから token 型を導き、registry へ登録する。**7.7-2 の記録と比較 corpus の再封印**を同時に行う。**内訳は表の下「ステップ 5〜7 の内訳」の 3** | 内訳 5 の合格条件をすべて満たす |
| 6 | **`tenant-isolation` の追加層を宣言する** — `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` と `tests/test_core_guard.py`。**`.claude/core-areas.json` を同一コミットに入れない**。**内訳 6** | 内訳 6 の合格条件をすべて満たす |
| 7 | **`.claude/core-areas.json` へ本単位の paths を登録する** — 越境テスト `backend/tests/test_roster_boundary.py` を `tenant-isolation` の末尾へ追加する(新規リポジトリは既存の `backend/src/pitchlog/repositories/*` が覆う — `fnmatch` の `*` は `/` を跨ぐ)。**ステップ 6 の宣言と完全一致させる**。単独コミット。**内訳 7** | 内訳 7 の合格条件をすべて満たす |
| 8 | **リクエストの要求面を足す**(第 3 改訂で追加) — Cookie(H-2 の属性)から提示値を不透明な値のまま取り出し、**状態を変える要求**ではカスタムヘッダの必須化と `Origin` の検査で CSRF を拒否する依存関数を API 層に置く。**提示値を分解せず、γ を呼ばず、`TenantContext` を作らない**。どの入口にもまだ結線しない。**内訳 8** | 内訳 8 の合格条件をすべて満たす |
| 9 | **`TenantContext` の発行と選手の入口を、同じコミットで開く**(第 3 改訂 — 第 2 改訂の 8 に発行を足した) — 発行専用モジュールの発行関数が提示値を受けて γ の公開入口を呼び、照合を通ったテナント ID からだけ `TenantContext` を作る(**生成箇所** — 8-3 節「検証の手順」⑤)。`tenant-context-allowlist.json` へ登録し、検査器の 0 件必須の分岐を置き換え、配布モジュールを追随させる。選手の入口(作成・一覧・取得・更新)をステップ 8 の依存関数 → 発行関数 → リポジトリの順に結線し、`ROUTERS` へ登録し、`test_api_conventions.py` の述語 4(経路数)の期待値を更新する。**DTO の `name` の空文字の扱いを token と揃える**(ステップ 5 の持ち越し P2)。**内訳 9** | `test_roster_boundary.py` の当該入口ぶんが green(認可行列どおりに通り行列外は 404)。`/health` `/version` を含む既存テストが green。**`backend/tests/test_roster_boundary.py` を作るこのステップで、ステップ 7 で登録した `tenant-isolation` のパスが実ファイルに当たることを確かめる**(登録が先行するため — 第 2 改訂の 4)。内訳 9 の合格条件をすべて満たす |
| 10 | **受理記録を 1 件にまとめ、比較 corpus を再封印する**(第 3 改訂で追加) — ステップ 9 の SHA を受けて、#95 の 7.7 の受理記録を、ステップ 5 と 9 の両方の変更を覆う 1 件へ導出し直す。**内訳 10** | 内訳 10 の合格条件をすべて満たす |
| 11 | **在籍区分の入口を開く** — プレビューと適用。**キャッシュ無効化の発火点**を `CacheInvalidationTrigger.ROSTER_STATUS_CHANGE` で置く | 在籍区分変更後に共有集計のキャッシュが失効することを受入テストで確認(要件書 `:996`) |
| 12 | **選手の削除の入口を開き、削除ガードを実装する**(FR-018) — `DELETE /players/{player_id}`(design.md 3 節の入口 7 — 第 3 改訂で入口を開くことを明記)。紐づけゼロ判定・進行中試合の存在判定・同一トランザクション化 | **入口を外から直接叩くテスト**(12-4 節「測定経路」行)が green。競合挿入を含む同時実行テストで、判定後に紐づいた場合に失敗すること・進行中試合があると拒否されることを確認 |
| 13 | **対戦相手チームレコードの入口を開く**(FR-039) — 作成・一覧・更新・削除。類似名の警告と削除拒否の誘導 | 試合または選手が紐づくチームの削除が拒否されること・類似名が警告で登録続行できることを確認 |


#### ステップ 2〜4 の内訳(第 2 改訂 2026-10-05)

**2. 契約資産・検査器・派生 lock**

- 封印入力の許容差分の固定列挙(`tests/test_check_authz_catalog.py:4997-5025`)を更新する
- 経路 6 本(N1)を `route-registry.json` に足す: `route_kind: record_and_aggregate` / `origin: design` / `source_claim_ids: []` / `provenance_ids` に `PLAN-TSK446-RECORD-AND-AGGREGATE` を含む / `operation`(検査器 `scripts/check_authz_catalog.py:2346-2429`)
- `http-route-matrix.json` に 6 行(`disposition: conditional` — 同 `:2729`。`test_owner.status: planned`)
- 検査器の期待集合を 6 本の独立リテラルへ(N2)。`tests/test_check_authz_catalog.py` の表明と負例(期待集合外の `route_id`・導出規則違反・専用 provenance 欠落)を更新・追加
- 派生 lock を `--reseal-derived --skip-oracle` で作り直す。**fixture 側の lock(`tests/fixtures/authz_claims/route-registry.lock.json` など)は CLI が触らない**ので、前例どおり手で揃えるかを原典で確かめる(`../route-kind-vocabulary/plan.md:170`)

**3. oracle の追随と人間の確認**

- **`failure-injection-points.json`・`mcdc-map.json` の digest 追随**(上の表のステップ 3)を含める
- `oracle_commit` をステップ 2 のコミット SHA へ差し替える箇所と、経路の追加に伴って内容の追随が要る oracle 資産(`attack-tree.json`・`boundary-proposal.json`・`claim-mutant-map.json` など)は、**前例 `a1e2a8be`・`e01926ec`(#77 のステップ 5)を当てて原典で確定する**(N5)
- **敵対レビューと人間の確認をこのステップで受ける**。確認の記録を worklog に残す

**4. 凍結基準の記録と再封印**

- `frozen-baselines.json` の `history` へ 1 件(前例 `fb71c300` — 10 キー: `acceptance_id` / `series` / `new_identity` / `prior_identity` / `changes` / `placement_change` / `moved` / `reason` / `approved_by` / `approved_at`)。`approved_by` / `approved_at` は人間に確認した値
- `--reseal-oracle` で再封印する(`human_review_required: true` — ステップ 3 の確認を経た後)
- **PR の base が進んだら再導出する**(N4)

#### ステップ 5〜7 の内訳(改訂 2026-10-05 — 敵対レビュー 4 周の反映)

**5. リポジトリと operation token**

- **着手条件: ステップ 4 で確定した PR 番号を `acceptance_id` に使う**(PR を作るのはステップ 4 の前 — N3)。`acceptance_id` は実際の PR 番号から導出され、PR 受理検査でイベント値との一致を要求される(`scripts/frozen_history.py:672`・`:685`)ので、番号を知らないままでは記録を完成できない(仮の番号はローカルで green でも受理時に落ちる)。前例は TSK-443(`../runtime-contract-switch/plan.md:80`「draft PR を作って `acceptance_id` を確定する」)。**作り方と `/pr` との両立は N3**

- **契約と生成物**: `contracts/tenant_boundary/repository-contract.json` の `product_capability_ids` / `product_operation_token_types`(`:127-128`)へ本単位の分を登録し、生成モジュール `backend/src/pitchlog/repositories/repository_contract.py`(`PRODUCT_CAPABILITY_IDS` / `PRODUCT_OPERATION_TOKEN_TYPES`)を同期する。**`cross_tenant_functions` は空のまま**
- **実行 registry**: `repositories/base.py` の `_OPERATION_REGISTRY` を契約と exact-set で一致させる
- **登録文の検証**: `backend/src/pitchlog/authz/capability_registration.py`(`:1195-1269` — カタログの ID・表・操作との照合)に通す
- **空を表明する既存テストの更新**: `backend/tests/test_authz_capability_registration.py:1022-1027`(`test_product_registries_remain_empty`)・`backend/tests/test_authz_repository_contract.py:407-417`
- **凍結基準の記録(7.7-2)**: `repository-contract.json` 側は `baseline_control` の `contract_revision` と `current_identifiers` を同期し、**既存 history は保持する**(非権威資産への履歴の追記は拒否される — `scripts/frozen_history.py:492-519`)。
  **追加の記録は権威履歴(`contracts/tenant_boundary/base-allowlist.json` の `baseline_control.history`)へ 1 件だけ**置き、影響を受ける凍結資産の全件・変更前後の snapshot・生成モジュールの digest を同期する(様式は設計書 `:584-608`)。
  **記録はステップ 5 のコミット時点で、draft PR の番号とその時点の比較元に対して完全に書く**(識別値を未記入にする・revision だけ動かす形は検査が通らない)
- **比較 corpus の再封印**: `contracts/tenant_boundary` は比較 corpus の入力 tree(`tests/fixtures/frozen-archive-cases/manifest.json:16-18`)なので、`history-snapshots/` と manifest の digest を再導出する
- **再導出の時点**: PR の受理検査は event の `base.sha` と二親 merge で評価する(`scripts/check_tenant_boundary_bypass.py:6163`・`scripts/frozen_history.py:1185`)。**PR 直前の develop 取り込み時に再導出・再検証し、PR 作成後に base が進んだら再度行う(コミット先は N4)**
- **前版の結果照合**: `tests/test_frozen_archive_case_runner.py` は現版だけを実行する(`:414`)ので、再封印時に runner(`tests/fixtures/frozen-archive-cases/runner.py`)を `--checker previous=<前版> --checker current=<現版>` で両方当て、**全ケースで manifest の期待値と一致する**ことを確かめる。前版の作業木は固定 SHA・detached・清潔であること(`runner.py:1034`)
- **合格条件**: 前版・現版の全ケース一致(上)。`backend/tests/test_authz_repository_contract.py`(資産と生成モジュールの一致 `:303-309` を含む)・`backend/tests/test_authz_capability_registration.py`・`tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py`・`tests/test_frozen_archive.py`・`tests/test_frozen_archive_case_runner.py` が green。カタログ外の ID・表・操作が拒否される負例が green

**6. 追加層の宣言**

- **着手条件**: TSK-344 のマージ後、develop を取り込んでから行う(上の改訂 3)。着手時に `git fetch origin` し、**`origin/feature/*`・`origin/fix/*` とローカルの `refs/heads/*`(`git worktree list` の全 worktree を含む — 未 push の競合を落とさないため)のうち、`scripts/core_guard.py` の `AREA_PATH_ADDITIONS` または `.claude/core-areas.json` の `tenant-isolation.paths` を変える未マージの ref とその SHA を worklog に記録する**。未マージの競合は順序調整の対象(該当タブへ連絡)であり、宣言の基線へ取り込むのは **develop に着地した変更だけ**。ステップ 7 と PR の前に同じ確認を繰り返す
- **逐行確認**: `scripts/core_guard.py`・`tests/test_core_guard.py`・`.claude/core-areas.json` はいずれも最上位 `guard_paths` に該当する(`:466`)。本単位の PR は元から逐行確認が必須なので、ステップ 6・7 で手続きは増えない
- **宣言**: `AREA_PATH_ADDITIONS["tenant-isolation"]` を **U-M1 の未取り込み分だけ**(`("backend/tests/test_roster_boundary.py",)`)にする。先着ブランチの宣言は**累積せず置き換える**(部分取り込みは `scripts/core_guard.py:303-314` が拒否)
- **テスト**: `tests/test_core_guard.py` の「宣言領域・未宣言領域」を固定する表明(`:1497`・`:1544`・`:1617-1623`)を更新する。**意図した宣言の exact-set をテスト側に独立して残す**(`set(AREA_PATH_ADDITIONS)` を実装から読んで許す形にしない)。**部分追加・並べ替え・削除・未宣言の追加の 4 種を直接試す負例**を足す(部分追加・並べ替えは複数パスを宣言した合成例で試す)
- **検査器の性質の正確な記述**: 宣言後も、JSON が merge-base のままの状態は検査器が許す(`:310`)。**登録の欠落は検査器では検出しない** — ステップ 7 の独立確認で検出する
- **合格条件**: `uv run pytest tests/test_core_guard.py` が green。**ステップ 6 のコミット SHA に対して `uv run python -c "import sys; from pathlib import Path; sys.path.insert(0, 'scripts'); import core_guard; print(core_guard.verify_area_path_baseline(Path('.'), '<origin/develop の SHA>', '<ステップの SHA>'))"`(リポジトリルートで。base SHA・ステップ SHA・戻り値〔merge-base の OID〕を worklog に記録) を実行し、例外なく戻ることを確かめる**(PR の CI は最終 head しか検査せず、ローカルの `core_guard.py` は PR event が無いと skip するため — `.github/workflows/ci.yml:55`・`scripts/core_guard.py:499`)

**7. paths の登録**

- **合格条件**: 内訳 6 と同じコマンドをステップ 7 の SHA に対して実行し、例外なく戻る(worklog に記録)。**独立確認として、実際の `tenant-isolation.paths` が「merge-base の列 ＋ `backend/tests/test_roster_boundary.py` の 1 件」に一致することを確かめる**。`uv run pytest tests/test_core_guard.py` が green。PR 本文に 6.3-⑤ の審査対象として明示する

#### ステップ 8〜10 の内訳(第 3 改訂 2026-10-07)

**8. リクエストの要求面**

- **着手条件**: ステップ 7 の後。外部依存を待たない
- **置き場**: `backend/src/pitchlog/api/` 配下。**API 層の全ソース連結に対する部分一致検査**(R5 — `Session`・`generation` を docstring・コメントを含めて書けない)を受ける
- **Cookie**: H-2 の属性(`HttpOnly`・`Secure`・`SameSite=Strict`)を前提に、提示値を取り出す。名前などの細部は **N6**
- **CSRF**: 状態を変える要求では、**カスタムヘッダの必須化と `Origin` の検査**を両方行う(H-2)。対象とする HTTP メソッドの範囲・`Origin` の許可値の出所は **N6**
- **信頼境界**(8-3 節「検証の手順」②): **提示値を不透明な値として扱い、分解しない**。ID を取り出すのも署名を照合するのも γ の公開入口であり、その呼び出しはステップ 9 の発行専用モジュールの中だけに置く。**このステップの依存関数は γ も認証関数も呼ばない**
- **秘密性**(NFR-014): 提示値をログ・例外のメッセージ・応答に出さない
- **拒否の応答**: 既存のエラー規約(`backend/src/pitchlog/api/errors.py`)に従う。**応答の内容が、拒否の理由以外の事実(テナントや認証主体の存在など)で変わらない**
- **合格条件**: 単体テストで、Cookie の欠落と空の値が拒否される / 状態を変える要求で、カスタムヘッダの欠落・`Origin` の欠落・`Origin` の不一致がいずれも拒否される / 正しい要求で提示値がそのまま返る / 提示値がログ・例外のメッセージ・応答に出ない / **依存関数が γ・認証関数・`TenantContext` のいずれも import しない**(構造テスト)/ `ruff check`・`ruff format --check`・`ty check`・`backend/tests/test_api_conventions.py` が green

**9. `TenantContext` の発行と選手の入口の開放**

- **着手条件**: dep 4・6(γ)・7・10(TSK-480)・11(TSK-457)が develop に着地していること。着手時に、γ の公開入口(`verify_tenant_id` — 名前・引数・戻り値)と、TSK-457 計画書 4-3 節「U-M1 ステップ 8 に渡るもの」の 1〜5・「U-M1 への制約」を、**着地した版の原典**で再確認し、worklog に記録する
- **発行専用モジュール**: 発行関数を **1 つだけ**公開する。**入力は提示値**とし、**γ の公開入口の呼び出しはこのモジュールの中だけ**に置く。照合を通ったテナント ID からだけ `TenantContext` を作り、照合を通らなければ作らない。**検証済みのテナント ID を発行関数の外へ返さない**。置き場・モジュール名・発行関数の名前は **N7**。**発行関数の名前はリポジトリ内で一意にし、全行走査で衝突 0 件を確かめる**(TSK-457 の照合は末尾名でも一致する)
- **資産**: `contracts/tenant_boundary/tenant-context-allowlist.json` の `allowed_product_modules` に発行専用モジュールを 1 件入れ、発行入口の 2 欄(シンボルと許可シンボル)を設定する。`source_digest` の再計算・`contract_revision` の繰り上げ・配布モジュール `backend/src/pitchlog/repositories/tenant_context_contract.py` の追随
- **検査器**: `scripts/check_tenant_boundary_bypass.py` の `_load_tenant_context_contract` にある 0 件必須の分岐を、**「`allowed_product_modules` が、資産の発行入口のシンボルが属するモジュール 1 件と exact-set で一致する」へ置き換える**。**期待値は資産から導出し、検査器にモジュールの完全修飾名を直書きしない**(凍結基準の値を検査器へ直書きしない — 設計書 7.7-1)。**解除して無制限にしない** — 以後に製品モジュールを足すには発行入口の設定と規則の両方を変える必要があり、それは 7.7 を通る(`movement_triggers` の `pass_fail_mapping`)
- **テスト**: `tests/test_check_tenant_boundary_bypass.py` の `test_product_module_cannot_be_added_before_authenticated_entry_exists` を新しい規則へ改訂する。**負例**: 別のモジュールを 1 件足す・2 件にする・空にする・発行入口の 2 欄を空のまま登録する、のいずれも `ContractError`。**検査器のソースに発行専用モジュールの完全修飾名が現れないこと**を確かめる。`PRODUCT_APPLICATION_PATHS` に発行専用モジュールを足し、`test_tenant_repository_product_definition_passes_bypass_scan` で violation 0
- **生成箇所の一意性と ② の後半**: 発行関数の呼び出し元を**入口の依存関数の 1 箇所**に限り、構造テストで exact-set を固定する。**γ の公開入口の呼び出し元が発行専用モジュールだけ**であることも構造テストで固定する。**γ のテスト `backend/tests/test_authz_app_layer_surface.py` は製品コードからの呼び出し元を期待集合(`_PUBLIC_CALLERS` ほか — 着地した版で確認)で固定しているので、発行関数を呼び出し元として 1 件足す**。**γ の公開操作の集合(`_PUBLIC_OPERATIONS`)は増やさない**。ログアウトの入口は γ の所有で、U-M1 はその呼び出しを足さない。これで 8-3 節「検証の手順」② の後半(署名を照合していない ID をテナント文脈の生成へ渡す経路を作らない)が閉じる — γ の計画書 4-7 節の残余リスクの後半
- **入口**: ステップ 8 の依存関数 → 発行関数 → リポジトリの順に結線する。入口ごとに、**他テナントの提示値・Cookie の欠落・CSRF の欠落で拒否される**ことを、**外から直接叩く形**で確かめる(`data-model.md` 12-4 節「測定経路」行 — 入口を開く PR は同一 PR に直接叩くテストを含む)
- **DTO の `name`**: 空文字を DTO で拒否し、token の値域に揃える
- **期待失敗**: このステップの SHA では、テナント境界の凍結履歴の検査が、資産と記録の不一致で落ちる(ステップ 10 で解消)。**期待失敗の集合は全件実行で確定して worklog に列挙する**
- **合格条件**: 上の表のステップ 9 の合格条件 / 発行関数が提示値以外(生の UUID・文字列化した ID)からは `TenantContext` を作れないことの負例 / 許可外のモジュールから発行能力・発行入口を名指すと TB007 になる(TSK-457 の機構が本単位の登録値で効いていることの確認)/ 発行関数と γ の公開入口の呼び出し元の exact-set が green(γ の `test_authz_app_layer_surface.py` を含む — 公開操作の集合は不変)/ `name` の空文字が 422 で拒否される / 衝突 0 件の走査コマンドと結果が worklog にある / 期待失敗の集合が worklog にあり、それ以外が green

**10. 受理記録の 1 件化**

- **手順**: 権威履歴(`contracts/tenant_boundary/base-allowlist.json` の `baseline_control.history`)の #95 の記録を、**ステップ 5 とステップ 9 の両方の変更を覆う 1 件へ導出し直す**。影響する凍結資産・前後の snapshot・生成モジュールの digest・比較 corpus の再封印は内訳 5 の手順を準用する。`frozen_projection.external_files` に検査器自身が入っていることを踏まえる。`approved_by` / `approved_at` は人間に確認した値
- **合格条件**: 内訳 5 の合格条件をこのステップの状態で再度満たす(前版・現版の全ケース一致を含む)/ **権威履歴にある #95 の記録が 1 件だけ** / ステップ 9 の期待失敗がすべて解消 / `uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop` が ok / `tests/test_check_tenant_boundary_bypass.py`・`tests/test_frozen_history.py`・`tests/test_frozen_archive.py`・`tests/test_frozen_archive_case_runner.py`・`backend/tests/test_authz_tenant_context.py` が green



#### 実装時に原典で決める事項(N1〜N7 — 改訂 2026-10-05・PO 裁定「ステップ 2・3 の詳細は実装時に詰める」。N6・N7 は第 3 改訂で追加)

**計画書では方針だけを固定し、手順の細部は当該ステップの委任時に原典で決めて design.md と worklog に記録する。**
**計画時に固定しない理由**: 対象の検査器・凍結履歴の機構は他タスク(TSK-431・TSK-344 ほか)が並行して動かしており、
2026-09-24 の計画書が承認後 11 日で 3 箇所陳腐化した(capability の登録機構・`core_guard.py` の二層方式・`record_and_aggregate` の期待集合)。
**手順を今固定すると実装時にはずれている見込みが高く、固定した手順の正しさは計画レビューでは閉じない**(敵対レビュー 4 周で毎周新種が出た)。

| # | 事項 | 方針(本書で固定) | 決める時点 | 受入証跡 |
| --- | --- | --- | --- | --- |
| **N1** | **経路ごとの `route_id` と、入口から経路への対応** | **決定済み(第 2 改訂)**: 経路は**資源 × 操作**で切る 6 本 — `ROUTE:RECORD:players:read` / `:insert` / `:update`・`ROUTE:RECORD:team_records:read` / `:insert` / `:update`。**経路 = 同じ `route_id` を持つ入口の集合**(design.md `:51-52` — 入口と経路は 1 対 1 でない)なので、一覧と取得が同じ `read` 経路に入るのは定義どおりで衝突ではない。資源名は capability カタログの表名(`CAP:players:*`・`CAP:team_records:*`)に揃える。入口 11 本の対応は design.md 3 節(作成 → insert / 一覧・取得・在籍区分のプレビュー → read / 更新・在籍区分の適用・削除 → update — **削除は論理削除なので update**、`../route-kind-vocabulary/plan.md:130`)。経路 6 本は分割検討の閾値「経路 10 本超」に掛からない | ステップ 2 | design.md 3 節に経路 6 本と入口の対応が載り、ステップ 2 の検査が(封印の不一致を除き)green |
| **N2** | **検査器の期待集合の更新範囲**(**決定済み**) | `scripts/check_authz_catalog.py` の `_validate_record_and_aggregate_route_ids` の期待集合と、対応する `tests/test_check_authz_catalog.py` の表明・負例を、ステップ 2 のコミットで本単位の `route_id` へ更新する。**期待集合を registry から読む形にしない**(独立した exact-set を残す)。両ファイルは `.claude/core-areas.json` の**最上位 `guard_paths`** に該当し(`scripts/core_guard.py:466` の完全一致)、PR 本文の逐行確認チェックを要求する(本単位はコア領域なので要求は元から掛かる — 追加の手続きは生じない) | ステップ 2 | ステップ 2 の差分に検査器とテストが含まれ、期待集合外の `route_id` が拒否される負例が green |
| **N3** | **`acceptance_id` を得るための早期 PR の作り方と、`/pr` との両立** | **【決定 2026-10-05・山田正輝】(a) #87 の前例どおり draft PR を先に作る — 確定した番号 = `masaki1025/pitchlog#95`**(ステップ 3 の後に作成。ステップ 4・5 の `acceptance_id` はこの番号から導出する。完了時に `/pr` のクローズ処理を行ってから ready)。以下は決定前の記述: **ステップ 4 の前に PR 番号を確定する**(内訳 4 — 第 2 改訂で早まった。ステップ 5 も同じ番号を使う)。**前例は #87(TSK-443)**: 2026-09-29 に PR を先に作り(ステップ 5/8 の時点)、2026-10-04 に `/pr` のクローズ処理を行ってから ready 化した(`docs/worklog/2026-09-26-runtime-contract-switch.md:60-76`)。ただし **`/pr` の文面は「PR 作成の唯一の入口」で、既存 OPEN PR の扱いを差し戻し後の再レビューに限っている**(`.claude/skills/pr/SKILL.md:2`・`:53`)ので、前例の流れは文面上の規定外である(敵対レビュー 5 周目 P1)。**ステップ 4 の前に人間へ確認し、(a) 前例どおり進めてよいか (b) `/pr` 側の改訂が要るか(要るならハーネスのタスクとして別に起票し、本単位では `/pr` を改訂しない)を決める**。draft 中は core-guard が逐行確認欄の未記入で red になる(想定内 — 確認は最新 HEAD に対して最後に行う。`docs/development/github-setup.md:60-61`) | ステップ 4 の前(**人間の判断を経てから PR を作る** — PR の作成は外部へ出る操作) | 人間の判断(a / b)と、PR 番号・作成時の base SHA が worklog にある。ステップ 4・5 の記録の `acceptance_id` が実番号と一致。**最終のクローズ処理が同じ PR で完了している** |
| **N4** | **base が凍結資産ごと進んだときの再封印のコミット先** | **系列ごとに元のステップの是正コミット**として行う — tenant_boundary は `(ステップ 5 再導出)`。**authz は場合を分ける**: (i) base が凍結台帳だけを進めた → `(ステップ 4 再導出)` で履歴と seal を再導出 (ii) **base が封印入力(route-registry・HTTP 行列・lock ほか `input_assets`)を変えた** → 封印は作業ツリーの blob と `oracle_commit` 上の blob の両方を照合する(`scripts/check_authz_catalog.py:6791-6814`)ので、`(ステップ 2 再導出)` で入力と lock を確定 → `(ステップ 3 再導出)` で SHA 差し替えと人間の再確認 → `(ステップ 4 再導出)` で履歴と seal (iii) **base が封印対象の oracle 資産(`sealed_assets` — `claim-mutant-map.json` ほか。入力 8 資産とは別 — `scripts/check_authz_catalog.py:6827`)だけを変えた** → `(ステップ 3 再導出)` で差分を再レビューし**人間の再確認を受けてから** `(ステップ 4 再導出)` で再封印する(`human_review_required` は宣言値の照合で確認の実施を検証しない — `:6855`)(付記つきの完全トークン — 付記つきの完全トークン。前例 `134bd39b`「(ステップ 4/8 是正)」)。記録・snapshot・corpus の digest を新しい base に対して再導出し、内訳 5 の合格条件を再度満たす。**TSK-431 など同じ資産群を触るタスクの着地を検知したら必ず行う** | PR 作成後に base が進むたび | 再導出コミットと、そのときの base SHA・合格条件の結果が worklog にある |
| **N5** | **oracle 資産の内容追随の範囲** | `oracle_commit` の差し替え 7 箇所に加え、経路の追加で内容が変わる oracle 資産があるかを、#77 のステップ 5(`a1e2a8be`・`e01926ec`)と各資産の検査器を当てて確定する。**範囲を推測で決めない** | ステップ 3 | 差し替え・追随した資産の一覧と根拠が worklog にあり、人間の確認を受けている |
| **N6** | **リクエストの認証の細部**(第 3 改訂で追加): Cookie の名前・パス・有効期限の表現、CSRF の対象とする HTTP メソッドの範囲、カスタムヘッダの名前、`Origin` の許可値の出所 | **H-2 の決定(属性と方式)は変えない**。決定に含まれない細部だけを U-M1 が先に決め、[design.md](design.md) に書く。**δ は後からこの値に合わせる**(R7)。設定値で持つものは `.env.example` へ実値なしで足す(NFR-014) | ステップ 8 | design.md に値と理由があり、δ の担当(Notion TSK-470)へ値を連絡した記録が worklog にある |
| **N7** | **発行専用モジュールと発行関数の名前・置き場**(第 3 改訂で追加) | 発行関数の名前はリポジトリ内で一意(TSK-457 計画書 4-3 節「U-M1 への制約」)。**API 層には置かない**(R5 の部分一致検査と、発行能力を名指せる場所を最小にするため)。置き場は TSK-457 が着地させた機構の位置を見て決める | ステップ 9 | design.md にモジュール名・関数名・置き場と、衝突 0 件の走査結果がある |


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
- [ ] **凍結基準の記録(7.7-2)が権威履歴に 1 件あり、PR の base に対して再導出・再検証済み**。比較 corpus の digest が再封印済み(4 節 内訳 5 — 改訂 2026-10-05)
- [ ] **oracle 封印の再封印と凍結基準(series `oracle_input`)の記録が 1 件あり、人間の確認(ステップ 3)を経ている**。PR の base に対して再導出・再検証済み(第 2 改訂)
- [ ] **追加層の宣言(ステップ 6)と paths 登録(ステップ 7)が別コミット**で、各 SHA に対する `verify_area_path_baseline()` の green が worklog にある。`tenant-isolation.paths` が「merge-base ＋ 1 件」に一致(内訳 6・7)
- [ ] **同領域の宣言・paths を変える未マージ ref の確認記録**(確認した ref と SHA)がステップ 6・7・PR 前の 3 時点で worklog にある
- [ ] **リクエストの認証**(第 3 改訂): Cookie は H-2 の属性・状態を変える要求はカスタムヘッダと `Origin` の両方を検査・提示値を分解しない・提示値がログ・例外・応答に出ない(内訳 8)。N6 の値を δ の担当へ連絡済み
- [ ] **`TenantContext` の発行**(第 3 改訂): 発行専用モジュールが `allowed_product_modules` と exact-set で一致し、検査器は 0 件必須を解除せず「資産の発行入口が属するモジュール 1 件」へ置き換えた(期待値は資産から導出し、検査器に直書きしない)。発行関数の名前の衝突が 0 件。**発行関数の入力は提示値で、γ の公開入口は発行専用モジュールの中だけで呼ぶ**(内訳 9)
- [ ] **8-3 節「検証の手順」② の後半が閉じている**: 発行関数の呼び出し元が 1 箇所・γ の公開入口の呼び出し元が発行専用モジュールだけで、生の UUID や文字列化した ID からは `TenantContext` を作れない(内訳 9 — γ の計画書 4-7 節の残余リスクの後半)
- [ ] **テナント境界の受理記録が #95 について 1 件だけ**で、ステップ 5 と 9 の変更を覆い、PR の base に対して再導出・再検証済み(`intermediate_commits_are_records: false` — 内訳 10)
- [ ] **製品モジュールの登録と入口の開放が同じコミット(ステップ 9)にある**。登録した製品モジュールが入口より先に存在するコミットが無い(U-T1 の「製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる」— 途中コミットにも掛かる)
- [ ] **12-4 の判定記録**(PR に記録する — `data-model.md` v0.6 12-4 節のゲート表「判定の記録」行と「実スキーマ」小見出し): 入口を開く本 PR について、v0.6 の「実スキーマ」(4 要件)に当たる対象で RLS の DDL が適用され(通過条件 ①)、越境テストが green(同 ②)であることを、次の項目を**省かず**に書いた
  - **誰が・いつ**確認したか
  - **どの実スキーマに対して**: **接続先の識別**(クラスタとデータベースから導いた要約値でよい — 接続情報の実値は書かない)と**作り直した世代の識別**(実行の採番)。書式は運用の正本 `docs/ops/product-rls-real-schema.md` に従い、その版を記す
  - **どの入口について**: 開いた入口ごとに **`route_id` と method / path の組**(**本 PR が開く全入口** — [design.md](design.md) 3 節の入口表の全行。ステップ 9・11・12〔選手の削除〕・13 で開く。一覧と取得のように同じ経路に入る入口があるので、`route_id` だけでは区別できない — N1)
  - **1 回の実行の妥当性**: 運用の正本の手順が未整備の項目は、v0.6「1 回の実行の妥当性」の暫定の記録(出所・各実行の連番と開始・終了時刻・比較の結果)で書く
- [ ] **ログアウトの入口を持たない**(γ の所有 — 裁定 (ア))

## 6. テスト計画

| 対象 | 種別 | ファイル | 確認すること |
| --- | --- | --- | --- |
| DTO のバリデーション | 単体 | `backend/tests/test_roster_schemas.py` | 値域 / `extra="forbid"` / PATCH の省略と明示 null / bulk の空配列・重複 ID / ページ上限の境界 |
| 越境 | 越境 | `backend/tests/test_roster_boundary.py` | **認可行列どおりに通り、行列外はすべて 404**。**API 直叩きを含む**(`data-model.md:2532` — 入口を開く PR は同一 PR に外から直接叩くテストを含む) |
| 在籍区分変更後のキャッシュ失効 | 受入 | 同上 | **OB 化した選手が共有結果に現れない**(要件書 `:933` の (b) 列挙) |
| 削除の競合 | 故障系 | 同上 | 判定後に紐づいた場合に失敗する / 進行中試合があると拒否 |
| 同番号の警告後の登録続行 | 受入 | 同上 | 警告が出たうえで登録できる |
| リクエストの認証(第 3 改訂) | 単体・故障系 | `backend/tests/` 直下(名前は `test_authz*` を避ける — DoD「機構」) | Cookie の欠落・空の値 / CSRF のヘッダ欠落・`Origin` の欠落と不一致 / 提示値がログ・例外・応答に出ない / 依存関数が γ・認証関数・`TenantContext` を import しない(内訳 8) |
| `TenantContext` の発行(第 3 改訂) | 単体・負例 | `tests/test_check_tenant_boundary_bypass.py` / `backend/tests/` | `allowed_product_modules` の exact-set(別モジュール・2 件・空・発行入口が空のままの登録が `ContractError`)/ 検査器のソースに発行専用モジュールの名前が無い / 許可外からの発行能力・発行入口の名指しが TB007 / 生の UUID・文字列化した ID から `TenantContext` を作れない(内訳 9) |
| 生成箇所の一意性(第 3 改訂) | 構造 | `backend/tests/` | 発行関数の呼び出し元が 1 箇所・γ の公開入口の呼び出し元が発行専用モジュールだけ(内訳 9) |
| 12-4 の判定(第 3 改訂) | 越境 | `backend/tests/test_roster_boundary.py` | 実スキーマ(v0.6 の 4 要件)の上で越境テストが green であることを記録する(DoD) |

**実行手順**(`backend/` で。CI と同じ順 — `.github/workflows/ci.yml:255-262`):

```
docker compose up -d                    # backend/tests/db/conftest.py が DB 必須テスト 0 件を失敗扱いにする
uv run ruff check .
uv run ruff format --check .            # backend では CI が強制する(AGENTS.md の注記はハーネス側のもの)
uv run ty check
uv run pytest -c pyproject.toml
```

**ハーネス側(リポジトリルートで — 改訂 2026-10-05 で追加)**: ステップ 2〜4 で `uv run python scripts/check_authz_catalog.py` と `uv run pytest tests/test_check_authz_catalog.py tests/test_check_authz_catalog_spec.py tests/test_frozen_baseline_acceptance_rules.py tests/test_frozen_baseline_declarations.py tests/frozen_negatives/`(第 2 改訂で追加)。ステップ 5〜7 で `uv run pytest tests/test_core_guard.py tests/test_check_tenant_boundary_bypass.py tests/test_frozen_history.py tests/test_frozen_archive.py tests/test_frozen_archive_case_runner.py`。ステップ 6・7 は各コミット SHA に対する `verify_area_path_baseline()` の結果を worklog に記録する(4 節 内訳 6・7)

**迂回検査は実装スケルトンの段階で当てる**:
`uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`

## 7. リスク

| # | リスク | 対応 |
| --- | --- | --- |
| **R1** | 入口を開くのに**外部所有者が 5 者**(TSK-424 PR A / PR C・TSK-344・`route_kind` 値域〔**解消済み** — PR #77〕・**U-A1**(ブロック中)・在籍区分キーの別タスク)。1 つでも動かないとマージできない | 着地状況を /pr の前に再確認する。空席の所有者は 8 節で人間へ上げる |
| **R2** | `test_owner.status: "implemented"` は**ハーネス側 `tests/` の node ID** としか照合されない(`scripts/check_authz_catalog.py:2674-2685`) | 新規行は **`planned` 止まり**(ステップ 2 の合格条件) |
| **R3** | `players.team_record_id` は immutability の**未分類列**(handoff `TSK-372`)。所属チーム変更の可否がコードから読めない | `PlayerUpdate` の更新対象に含めない。必要になれば TSK-372 へ上げる |
| **R4** | **capability 登録は凍結基準を動かす**(`repository-contract.json` が `FROZEN_BASELINE_ASSETS`)。**TSK-431 が同じファイル群を触る** | ステップ 5 で **7.7-2 の記録**(権威履歴へ 1 件)と比較 corpus の再封印を同時に行い、**PR 直前の取り込みと base の前進のたびに再導出する**(4 節 内訳 5)。TSK-431 と順序を調整する |
| **R5** | API 層は `api/**` の**全ソース連結**に対する部分一致検査を受け、**`Session`・`generation` を docstring・コメント含め書けない**(`backend/tests/test_api_conventions.py:22-37`)。**TB004 は AST 上の識別子検査**で範囲が異なる(`scripts/check_tenant_boundary_bypass.py:2672`) | [design.md](design.md) D5 で 2 つの検査を**分けて**記述し、命名を実装前に固定する |
| **R6** | **`core-areas.json` を編集する**ため **#74 の `verify_area_path_baseline()`** が掛かる。`core_guard.py` / `test_core_guard.py` と同一コミットにすると、**後から revert しても打ち消せず force-push も `git_guard.py` が拒否する** | **追加層の宣言(ステップ 6)と paths 登録(ステップ 7)を別コミットにする**。旧版は宣言のステップを置いていなかった(改訂 2026-10-05) |
| **R7** | **リクエストの認証の細部(Cookie の名前など)を、本来の受け取り先の δ より先に U-M1 が決める**(第 3 改訂 — 依存表 12)。δ が後から別の値を選ぶと、Cookie を発行する側と読む側が食い違う | N6 の値を design.md に書き、**δ の担当へ連絡し、Notion の TSK-470 へコメントで残す**。H-2 の決定(属性と方式)は変えない。δ が値を変える必要が出たら、δ の PR で U-M1 の読み取り側も同時に変える |
| **R8** | **ステップ 9 の依存が 3 本(γ・TSK-457・TSK-480)増え、受理記録の再導出の機会も増える**(TSK-457 は `contracts/tenant_boundary/` と検査器を変える) | 凍結資産の取り込みは回数で費用がかかるので、**ステップ 9 の直前に 1 回取り込み、ステップ 10 でまとめて再導出する**(内訳 10)。それより前の取り込みで base が凍結資産ごと進んだら、N4 の手順で行う |

## 8. 人間の判断を仰ぐ事項

| # | 事項 | 本書の扱い |
| --- | --- | --- |
| **1** | **フロントエンド実装の帰属** — 単位分割の正本に「フロントエンド」「Vitest」「Vue」の語が **1 件も無い**(実測)。`:60` が各単位へ送るのは **UI の「設計正本」**であって実装ではない。**FR-015/017/018/039 の UI 面の受け皿が正本上空席** | **U-M1 は射程外**として線を引いた。受け皿の決定を仰ぐ |
| **2** | **FR-015 の同期面の帰属** — 分担表に FR-015 の行が無く、「面が切れなかったときの手順」の対象外。正本上は **U-M1 の単独主所有**のまま | 帰属表を更新せずに U-S1 へ移さない。判断を仰ぐ |
| **3** | **`route_kind` の値域決定の所有者** — `TSK-380` の射程は既存 37 経路の `test_owner` 再割り当てであり、**値域拡張は空席**(**2026-09-24 時点の記述**) | **解消済み(2026-10-04 訂正 — 4 節の外部依存 5)**。TSK-446 / PR #77 が 2026-09-25 にマージ済み |
| **4** | **在籍区分キーの値と seed の別タスク起票** — `active` のみ `data-model.md:524` に典拠。`other`/`ob` はリポジトリ内に文字列が存在しない。seed は **5 領域すべてのコア paths** で契約 3 の例外に U-M1 は含まれない | 別タスクへ切り出す前提で本書から外した。起票の可否を仰ぐ |
| **5** | **Notion カードのコア判定が正本より古い** — **葉 6 本すべてが同型**と見られる(TSK-394 で確認) | TSK-393 のカードには訂正コメントを入れる。**他タスクのカードには触れない** |
| **6** | **改訂 2026-10-05 の承認**(ステップ 4 の追加と番号の付け替え — 4 節の改訂ブロック)。あわせて **7.7-2 の記録の承認値**(承認者・承認日)はステップ 5 の実装時に人間へ確認する | **第 1 改訂は 2026-10-05 に承認済み。ステップ 1 は実装済み(3a3aaa53)**。以後の停止位置は 7 による。**N1〜N4 は各時点で決めて記録する(PO 裁定 2026-10-05)** |
| **7** | **第 2 改訂 2026-10-05 の承認**(ステップ 2 の分割と新 3・4 の追加・番号の付け替え・N1/N2 の決定・N5 の追加)。あわせてステップ 3 の **oracle の追随の人間確認**と、ステップ 4 の記録の承認値 | **2026-10-05 に承認済み(山田正輝)**。ステップ 3 の oracle 追随の人間確認とステップ 4 の記録の承認値は各ステップの実装時に仰ぐ |
| **8** | **リクエストの認証の帰属**(Cookie から提示値を取り出す・CSRF の検査) | **【裁定 2026-10-07・山田正輝】U-M1 ステップ 8 が持つ**(δ から移す — 依存表 12・R7) |
| **9** | **第 3 改訂 2026-10-07 の承認**(ステップ 8 を 3 本に分割・新 8・10 の追加・番号の付け替え・依存表 6・10・12・N6・N7・DoD と R7・R8 の追加)。あわせてステップ 10 の受理記録の承認値 | **2026-10-07 に承認済み(山田正輝)**。ステップ 10 の承認値は実装時に仰ぐ |
