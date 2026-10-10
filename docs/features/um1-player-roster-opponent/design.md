---
feature: um1-player-roster-opponent
type: design
date: 2026-09-24
---

# 詳細設計: U-M1 選手・在籍・対戦相手チーム

計画書: [plan.md](plan.md) / 調査メモ(典拠集): [research.md](research.md)

## 根拠の層(U-00 / U-01 の書き分けを継承)

- **(A) 要件・設計正本の直接帰結** — 破ってはならない
- **(B) U-M1 の設計判断** — **`TSK-346`(API 契約の正本・未着手)が別の形を定めたらそちらが正**

U-01 は**型だけ**を確定し中身を葉に残した([`../u01-dto-base/design.md`](../u01-dto-base/design.md)`:150`
「**上限は置かない。既定値も置かない。**」/ `:152`「**`cursor` / `next_cursor` の中身は不透明で、書式は `U-01` で決めない(葉と `TSK-346` の判断)**」)。
**(B) は U-00 の前例**([`../../worklog/2026-09-16-u00-api-shell.md`](../../worklog/2026-09-16-u00-api-shell.md)`:124`)**と同じ形で `TSK-346` へ申し送る**(6 節)。

## 1. 暫定規約

| # | 決定 | 値 | 層 | 根拠 |
| --- | --- | --- | --- | --- |
| **D1a** | **一覧のページサイズ上限** | **200** | **(B)** | **根拠は弱い。**要件書・付録 C に数値が無く(実測)、旧の規模「1 チーム数十名 × 年次入れ替わり・**無期限保持**」([`../../legacy/requirements-tsukuba-pss-v0.2.md`](../../legacy/requirements-tsukuba-pss-v0.2.md)`:457-458`)**は 200 件以内を保証しない**。**表示の 1 ページとして妥当な上限**として置き、**実測で見直す**前提とする |
| **D1b** | **一括変更の 1 要求あたりの上限** | **50** | **(B)** | **D1a と別の値にする。**一括変更は 1 トランザクションで複数行を更新するため、**表示の上限とは競合特性が違う**(P1-1)。**実測で見直す**前提とする |
| **D2** | **`limit` の既定値** | **置かない**(U-01 のまま必須) | **(B)** | U-01 が**意図的に**置いていない。葉ごとに足すと単位間で割れる |
| **D3** | **カーソルの書式** | **決めない** — 実装詳細を露出しない不透明トークン | **(B)** | `u01-dto-base/design.md:152`。**「決めていない」ことを明示する**(書かないと `TSK-346` 着手時に既成事実になる) |
| **D4** | **在籍区分キーの値** | **本単位では決めない** — 別タスクが決める | **(A) への委譲** | `system_vocabularies` は **`key` 単独が主キーで全フィールド不変**(`backend/src/pitchlog/db/tenant_isolation/models.py:1119`・`:1139`)。**category と複合ではない**ため、非名前空間化された値がグローバルキーを占有する。要件書 `:171` は**試合区分と在籍区分の双方に「その他」**を置いており衝突しうる。**キーは共有語彙**(U-M2・U-C 系も使う)なので U-M1 が単独で決めない |
| **D5** | **識別子の命名** | 下表の禁止語を使わない | **(A)** | 機械検査の帰結(2 節) |
| **D6** | **`operation_id`** | `roster_<資源>_<動作>` の snake_case | **(B)** | [`../u00-api-shell/design.md`](../u00-api-shell/design.md)`:124-139`。`contracts/authz/route-registry.json` の `enums.operation_ids` 8 件(`create_group` / `issue_invitation` / `revoke_invitation` / `accept_invitation` / `leave_group` / `update_grants` / `change_role` / `close_group`)と重ねない。**`capability_id`(リポジトリ操作の識別子)は別物**で、**TSK-424 の capability カタログが定める** |

## 2. 命名の禁止語 — **2 つの検査は範囲が違う**

| 検査 | 範囲 | 禁止語 | 典拠 |
| --- | --- | --- | --- |
| **TB004**(迂回検査 条件 4) | **`backend/src` の追加行のうち、AST 上のクラス名・関数名・名前参照・属性**を `_check_identifier` に渡したもの。**docstring・コメントは対象外** | `roster_status_change` / `change_roster_status` / `player_merge` / `merge_player` / `player_split` / `split_player` / `player_identity` / `undo`(いずれも `_` 境界) | `contracts/tenant_boundary/base-allowlist.json:185`・`:189`・`:196` / 検査 `scripts/check_tenant_boundary_bypass.py:2672` |
| **API 規約検査** | **`backend/src/pitchlog/api/**` の全ソースを連結した文字列**。**docstring・コメントも対象** | `sqlalchemy` / **`Session`** / `engine` / `session.execute` / `select(` / `text(` / `raw_connection` / `idempotenc` / `seq_no` / `tombstone` / `revision_no` / **`generation`** | `backend/tests/test_api_conventions.py:22-37` |

**TB004 は大文字でも一致する** — `_normalize_identifier`(`scripts/check_tenant_boundary_bypass.py:1440-1445`)が最後に `.lower()` する。
したがって **`ROSTER_STATUS_CHANGE` という定数名も一致する**。

**キャッシュ無効化の扱い**: **`from pitchlog.repositories.cache_invalidation import CacheInvalidationTrigger` して
`CacheInvalidationTrigger.ROSTER_STATUS_CHANGE` を参照する。文字列リテラルも同名の自前定数も書かない。**
救済経路は `allow_condition4`(同 `:3118` import / `:3250`・`:3260` 参照解決)。

既存 ORM 列名 `roster_status_key` は TB004 のパターンに**一致しない**(トークン境界が違う)。

## 3. 入口表(FR-015 / 017 / 018 / 039)

**用語**: [`../../design/data-model.md`](../../design/data-model.md)`:2438-2441` —
**入口** = 製品の外からの要求を受け取り DB のデータへ到達する 1 本の口(HTTP なら **method と path の組**)。
**経路** = **同じ `route_id` を持つ入口の集合**。**判定・測定・記録の単位は入口**であり、**両者は 1 対 1 ではない**。

**下表は入口 11 本。`route_id` は【2026-10-05 決定 — plan.md 第 2 改訂の N1】の表のとおり**(旧記述: 「`route_id` は未定 — `route_kind` の値域決定が空席」。値域は PR #77 で決定済み)。
**分割検討の閾値「経路 10 本超」**([`../product-impl-unit-split/design.md`](../product-impl-unit-split/design.md)`:136-145`)は
**route registry から経路を数える契約**なので、**`route_id` 付与後でなければ判定できない**。~~本書では判定を保留する。~~ **【2026-10-05】経路 6 本に決めたので閾値に掛からない**(下の「経路 6 本と入口の対応」)。

既定拒否は**全入口 404**(要件書 `:641`「第三者として記録した対戦相手データ → 付与によらず不可 → 404」)。
403 は器が 404 へ写す(`backend/src/pitchlog/api/errors.py`)。

| # | method | path | `operation_id` | request DTO | response DTO | 既定拒否 | 越境テスト | FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | POST | `/players` | `roster_player_create` | `PlayerCreate` | `PlayerRead` | 404 | `test_roster_boundary.py` | FR-015 |
| 2 | GET | `/players` | `roster_player_list` | `PlayerListRequest` | `Page[PlayerRead]` | 404 | 同上 | FR-015 / 017 |
| 3 | GET | `/players/{player_id}` | `roster_player_read` | — | `PlayerRead` | 404 | 同上 | FR-015 |
| 4 | PATCH | `/players/{player_id}` | `roster_player_update` | `PlayerUpdate` | `PlayerRead` | 404 | 同上 | FR-015 / 017 |
| 5 | POST | `/players/status-preview` | `roster_player_status_preview` | `PlayerStatusBulkRequest` | `PlayerStatusPreview` | 404 | 同上 | FR-017 |
| 6 | POST | `/players/status-apply` | `roster_player_status_apply` | `PlayerStatusBulkRequest` | `PlayerStatusApplied` | 404 | 同上 | FR-017 |
| 7 | DELETE | `/players/{player_id}` | `roster_player_delete` | — | `PlayerRead` | 404 | 同上 | FR-018 |
| 8 | POST | `/team-records` | `roster_team_create` | `TeamRecordCreate` | `TeamRecordCreated` | 404 | 同上 | FR-039 |
| 9 | GET | `/team-records` | `roster_team_list` | `TeamRecordListRequest` | `Page[TeamRecordRead]` | 404 | 同上 | FR-039 |
| 10 | PATCH | `/team-records/{team_record_id}` | `roster_team_update` | `TeamRecordUpdate` | `TeamRecordRead` | 404 | 同上 | FR-039 |
| 11 | DELETE | `/team-records/{team_record_id}` | `roster_team_delete` | — | `TeamRecordRead` | 404 | 同上 | FR-039 |

### 【2026-10-05 決定】経路 6 本と入口の対応(plan.md N1)

経路は**資源 × 操作**で切る(`route_id` の導出規則 `ROUTE:RECORD:<資源>:<操作>` — `scripts/check_authz_catalog.py:2407-2421`、操作の値域は read / insert / update)。
資源名は capability カタログの表名に揃える。**削除は論理削除なので update**(`../route-kind-vocabulary/plan.md:130`)。
**経路 6 本**なので、分割検討の閾値「経路 10 本超」に掛からない。

| `route_id` | 入口(上表の #) |
| --- | --- |
| `ROUTE:RECORD:players:insert` | 1 |
| `ROUTE:RECORD:players:read` | 2・3・5(プレビューは POST だが副作用を持たない — 4 節) |
| `ROUTE:RECORD:players:update` | 4・6・7 |
| `ROUTE:RECORD:team_records:insert` | 8 |
| `ROUTE:RECORD:team_records:read` | 9 |
| `ROUTE:RECORD:team_records:update` | 10・11 |

**5 と 6 を分ける理由**: FR-017 が「**プレビュー→確認→実行**」を受入基準に持つため(要件書 `:382` — (A))。
**パスはハイフン表記**(`status-preview` / `status-apply`)。TB004 は `_` 境界のパターンなのでパス文字列は一致せず、
`operation_id` も `roster_player_status_*` の形で `roster_status_change` / `change_roster_status` のいずれにも一致しない。

## 4. DTO 定義

ORM は実装済み(`backend/src/pitchlog/db/tenant_isolation/models.py`)。**列は再定義せず写す。**

### 共通の方針(P1-4 の是正)

- **`tenant_id` を応答に出さない**。根拠は **FR-034 の認可行列**(要件書 `:641`)と、自他の判別を `kind` で行い
  **`tenant_id` では判別しない**という設計([`../../design/data-model.md`](../../design/data-model.md)`:1335-1347` 敵対レビュー P0-1 の是正)。
  `EntityId` の docstring は**型が文脈を内包しない**ことを言うだけで、応答フィールドの選択根拠ではない
- **PATCH の省略と明示 `null`**: **省略 = 変更しない / 明示 `null` = その列を NULL にする**。
  nullable でない列に `null` を与えたら 422。実装は `model_dump(exclude_unset=True)` で区別する
- **一括要求の空配列は 422**、**重複 ID は 422**(黙って畳まない — NFR-015「黙殺しない」)

### `TeamRecordRead(ReadSchema)`

| フィールド | 型 | 必須 | 由来 |
| --- | --- | --- | --- |
| `id` | `EntityId` | 必須 | `TeamRecord.id` |
| `kind` | `Literal["self","opponent"]` | 必須 | `CheckConstraint("kind IN ('self','opponent')")`(`models.py:89`) |
| `name` | `str` | 必須 | `TeamRecord.name` |
| `hidden_at` | `Timestamp \| None` | 省略可 | `DeletionLifecycle.HIDDEN` |

### `TeamRecordCreate` / `TeamRecordUpdate` / `TeamRecordCreated`

- `Create`: `name: str`(`min_length=1`)のみ。**`kind` を受け取らない**
- **`kind='opponent'` の注入箇所**: **リポジトリ操作のサーバー側リテラル**として与える。
  `kind` は `protected_columns`(`models.py:135`)で不変、DB 側に既定値は無く(`models.py:123`)、
  **`UNIQUE (tenant_id) WHERE kind='self'`**(`models.py:113-118` — 述語は `:117`)があるため
  **API から作れるのは `opponent` だけ**である
- `Update`: `name: str` のみ。名前変更 token の登録は `allowed_update_columns={"name"}`、論理削除は別 token・別登録で `allowed_update_columns={"hidden_at"}`。どちらも認可行列の `CAP:team_records:update` を使う
- **`TeamRecordCreated`**: `TeamRecordRead` + `similar_names: list[str]`。
  **チーム名に一意制約は無い**(`data-model.md:1363-1364`)。**類似名は警告**であってエラーにしない(FR-039)ため、
  **登録は成功させたうえで応答に警告を載せる**

**ステップ 11 の類似名**: 同一テナントの非表示でない対戦相手レコードのうち、
新しい名前と大文字小文字を無視して一致する名前を類似名とする。新規行自身は除く。
DB で双方の名前を NFKC 正規化し、Unicode White_Space の前後を除き、
小文字化した等価条件で絞る。ID 順で最大 200 件を返す。
`public.authn_normalize_team_name` はアプリ用ロールの EXECUTE が契約上取り消されているため、
`pg_catalog.normalize`・`btrim`・`lower` を用いる。
元の表記を `similar_names` に載せ、該当があっても登録は成功する。
要件書 FR-039 は類似度の計算法を定めていないため、誤警告を抑えるこの判定を採る。

**削除不可の応答**: `DELETE` で対象が無い・他テナントの対象・自チームなら共通の 404。
試合への紐づきがあれば 409 と共通エラー封筒の固定文言
「試合が紐づいているため削除できません。名前を変更してください」、
選手への紐づきがあれば同じ 409 で
「選手が紐づいているため削除できません。名前を変更してください」を返す。
両方ある場合は試合を先に示す。非表示の選手も紐づきとして数える。
論理削除済みの試合と非表示の選手も紐づきとして数える。
判定と論理削除は同じテナントの 1 トランザクションで行う。
削除ガードは同一トランザクションでの判定までとする。並行する紐づけ挿入は
TSK-459 の射程に、試合の相手チームと選手の所属チームを含めて申し送る。

### `PlayerRead(ReadSchema)`

| フィールド | 型 | 必須 | 由来 |
| --- | --- | --- | --- |
| `id` | `EntityId` | 必須 | 不変(`protected_columns={"id"}`) |
| `team_record_id` | `EntityId` | 必須 | 複合 FK `(tenant_id, team_record_id)`(`models.py:144-150`) |
| `name` | `str` | 必須 | 表示用属性 |
| `throws` | `Literal["right","left"] \| None` | 省略可 | **DB は無制約 `Text`**。**値域は API の判断 (B)** — FR-015「投(右/左)」を英語キーへ写す |
| `bats` | `Literal["right","left","both"] \| None` | 省略可 | 同上。FR-015「打(右/左/両)」 |
| `uniform_number` | `str \| None` | 省略可 | **任意**・**一意制約なし**(`data-model.md:1424` P-15)。**空文字は拒否**(`min_length=1`)、`None`(番号なし)は許す |
| `roster_status_key` | `str` | 必須 | **`Literal` に閉じない**(D4)。`system_vocabularies.key` への FK で実行時に検証する |
| `roster_label_key` | `str \| None` | 省略可 | `tenant_vocabularies` 参照(複合 PK `(tenant_id, key)`) |
| `hidden_at` | `Timestamp \| None` | 省略可 | 論理削除 |

### `PlayerCreate` / `PlayerUpdate`

- `Create`: `team_record_id` / `name` / `throws?` / `bats?` / `uniform_number?` / `roster_status_key` / `roster_label_key?`
- `Update`: **`name` / `throws` / `bats` / `uniform_number` / `roster_status_key` / `roster_label_key` のみ**
  (`allowed_update_columns` の完全な集合は `models.py:206-215`。`hidden_at` は削除経路が扱う)
- **ステップ 9 の PATCH では `roster_status_key` / `roster_label_key` を受けない**(指定された要求は 422)。在籍区分の変更はプレビュー・確認・適用を伴う在籍区分の入口で開く(計画書の第 10 改訂で #95 から外し、#95 のマージ後に TSK-447 と同じ後続 PR で開く — 旧ステップ 11)。これらを PATCH でも受けるかはその PR で決める
- **`team_record_id` を `Update` に含めない**: immutability の `protected_columns` にも `allowed_update_columns` にも入らない
  **未分類列**で `unclassified_handoff="TSK-372"`。**所属チーム変更の可否がコードから読めない**(plan.md R3)

### `PlayerCreated`

`PlayerRead` + **`same_number_players: list[PlayerRead]`**。
FR-015「同番号で登録 → **警告が表示される(意図的なら登録可)**」(要件書 `:361`)を満たすため、
**登録は成功させたうえで同番号の現役選手を応答に載せる**。
現役は seed の `roster_status_key = "active"` とし、同じテナント・同じ背番号・`hidden_at IS NULL` の選手から新規行自身を除く。DB 側で絞り込み、応答は DTO のページ上限と同じ最大 200 件とする。背番号が `None` なら空配列を返す。

### `PlayerListRequest(PageRequest)` / `TeamRecordListRequest(PageRequest)`

- `limit` に**上限 200**(D1a)。`PageRequest` の `ge=1` を継承し `le=200` を足す
- 絞り込み: `team_record_id?` / `roster_status_key?` / `include_hidden: bool = False`

### `PlayerStatusBulkRequest` / `PlayerStatusPreview` / `PlayerStatusApplied`

- `PlayerStatusBulkRequest`: `player_ids: list[EntityId]`(**1 件以上・上限 50**(D1b)・重複不可)/
  `roster_status_key: str` / `roster_label_key: str | None`
- **`PlayerStatusPreview`**: `changes: list[PlayerStatusChange]`(各要素 = `player_id` / `name` / `before_status_key` / `after_status_key`)/
  `unchanged_player_ids: list[EntityId]` / `not_found_player_ids: list[EntityId]`。**副作用を持たない**
- **`PlayerStatusApplied`**: `applied: list[PlayerRead]` / `not_found_player_ids: list[EntityId]`
- **全区分可逆**(FR-017)なので遷移の方向を制限しない

## 5. 一覧クエリと索引の計画(NFR-005)

既存索引は **`ix_players_team` = `(tenant_id, team_record_id, id)` の `hidden_at IS NULL` 部分索引**
(`models.py:177-184` — 述語は `:182`)。

| 一覧の形 | WHERE | ORDER BY | カーソル条件 | 索引 |
| --- | --- | --- | --- | --- |
| `team_record_id` **指定あり** | `tenant_id = :t AND team_record_id = :r AND hidden_at IS NULL` | `id ASC` | `id > :cursor_id` | **`ix_players_team` が効く** |
| `team_record_id` **指定なし** | `tenant_id = :t AND hidden_at IS NULL` | `team_record_id ASC, id ASC` | `(team_record_id, id) > (:c1, :c2)` | **`ix_players_team` の先頭列から使える** |
| `roster_status_key` **での絞り込み** | 上記 + `roster_status_key = :s` | 同上 | 同上 | **索引に `roster_status_key` が無い** → **後続フィルタになる** |

**未解決**: `roster_status_key` 絞り込みを索引で効かせるには **索引の追加が要る**が、
**索引の追加は migration = 5 領域すべてのコア paths** で、契約 3 の例外に U-M1 は含まれない(plan.md 2 節)。
→ **在籍区分キーの seed を行う別タスクと同じ PR で索引も足す**のが筋。**8 節で人間へ上げる**(plan.md 8 節 #4 に含める)。

**カーソルは D3 のとおり不透明**。上表のタプルを実装詳細として露出しない形で符号化する。
**LIMIT は `limit + 1` 件取得して次ページの有無を判定**し、`next_cursor` を返す。

## 6. `TSK-346` への申し送り

**(B) の決定はすべて `TSK-346` が別の形を定めたらそちらが正。**

1. **一覧のページ上限を 200・一括変更の上限を 50 とした**(D1a / D1b)— **根拠は弱く、実測で見直す前提**
2. **`limit` の既定値を置かなかった**(D2)
3. **カーソルの書式を決めていない**(D3)
4. **`throws` / `bats` の値域を英語キーの `Literal` に閉じた**(DB は無制約 `Text`)
5. **PATCH の省略と明示 `null` を区別する**ことにした
6. **一括要求の空配列・重複 ID を 422 にした**
7. **警告を応答に載せる形**にした(`PlayerCreated.same_number_players` / `TeamRecordCreated.similar_names`)
8. **`operation_id` を `roster_<資源>_<動作>` とした**(D6)
9. ~~**入口 11 本の分割判定を保留した**(`route_id` 未定のため)~~ **【2026-10-05】経路 6 本に決め、閾値「経路 10 本超」に掛からないと判定した**(3 節)

## 7. リクエストの認証の細部(plan.md N6 — ステップ 8・2026-10-08)

**H-2 の決定(人間の決定 — 変えない)**: Cookie の属性 = `HttpOnly`・`Secure`・`SameSite=Strict` / CSRF 対策 = カスタムヘッダの必須化 + `Origin` の検査(`../ua1-team-auth/design.md:18`・`:195-197`)。以下は**決定に含まれない細部**で、U-M1 が先に決め、δ(TSK-470 — Cookie を発行する側)が後から合わせる(plan.md R7)。

| 事項 | 値 | 理由 |
| --- | --- | --- |
| Cookie の名前 | **`__Host-pitchlog_token`** | `__Host-` 接頭辞はブラウザが `Secure`・`Path=/`・`Domain` なしを強制し、サブドメインからの上書きを防ぐ(H-2 の属性を補強する側にしか倒れない)。名前に `session` を含めない(API 層の禁止語 R5 は大文字始まりの `Session` だが、紛れを避ける) |
| Cookie のパス | **`/`** | `__Host-` の要件 |
| 有効期限の表現 | **`Max-Age` で表す(`Expires` は併記しない)**。値は δ がトークンの失効と揃えて決める | 失効の正はサーバー側のトークン(γ の検証)であり、Cookie の期限は補助。U-M1 は Cookie を読むだけで期限を発行しない |
| CSRF の対象とする HTTP メソッド | **`GET`・`HEAD`・`OPTIONS` 以外のすべて**(`POST`・`PUT`・`PATCH`・`DELETE` ほか) | 安全なメソッドを除く全部を対象にする閉じた否定形。未知のメソッドも対象側に倒れる |
| カスタムヘッダの名前と値 | **`X-Pitchlog-Request: 1`**(値は文字列 `1` と完全一致) | 単純要求(simple request)では付けられないヘッダで、クロスオリジンの送信には事前確認が要る。値を固定して空・別値を拒否する |
| `Origin` の許可値の出所 | **環境変数 `PITCHLOG_ALLOWED_ORIGINS`**(カンマ区切りの完全一致のオリジン列。ワイルドカードなし)。**未設定・空なら、状態を変える要求をすべて拒否する**(fail closed)。各要素は**閉じた文法**で検証し、当たらない要素は捨てる — スキーム `http`/`https`、ホストは ASCII の LDH ラベルの DNS 名(末尾ドット不可・国際化ドメインは punycode)か、角括弧で囲んだ IPv6 アドレス(ゾーン ID・IPvFuture 不可)、ポートは省略か 1〜65535(先頭ゼロ不可)。パス・クエリ・フラグメント・ユーザー情報・末尾 `/`・`null`・ワイルドカードは不可(汎用の URL 解析の結果を正規化する形は、括弧付きホストの扱いで別のオリジンへ化けるため採らない — ステップ 8 の敵対レビュー 3 周目)。通った要素は RFC 6454 のシリアライズ形(スキームとホストは小文字・既定ポートは省く)へ正規化する。**要求側の `Origin` は正規化せず完全一致**で比べ、`null` は常に拒否する | 配備ごとに違う値なので設定で持つ。`.env.example` には名前と説明だけを足す(実値なし — NFR-014) |

**拒否の応答**: 既存のエラー規約(`backend/src/pitchlog/api/errors.py`)の封筒で返す。Cookie の欠落・空 → 401、CSRF の欠落・不一致 → 403。**応答の文言は拒否の種類ごとに固定**し、提示値・`Origin` の値・テナントや認証主体の存在を含めない。

**403 を 404 へ写す既存規約との関係(層 (B) — `TSK-346` が別の形を定めたらそちらが正)**: `errors.py` の HTTP 例外の 403 → 404 の写しは、**認可の拒否で資源の存在を漏らさない**ための規約(要件書の制御資源の「拒否の応答」— 403 は「そのグループが存在し、自分が権限を持たない操作がある」ことを漏らす)。要求面の拒否は**資源の参照より前に、資源に依存せず**決まるので、401 / 403 を返しても資源の存在は漏れない。**要求面の拒否は専用の例外で区別し、その例外だけを 401 / 403 で返す**(認可の拒否の 403 → 404 は変えない)。クライアントが「Cookie が無い」「CSRF のヘッダが無い」を区別して直せることを優先した。**`TSK-346` へ申し送る**(6 節と同じ扱い)

## 8. テナント文脈の発行入口(plan.md N7 — ステップ 9・2026-10-09)

製品全体で 1 つの発行専用モジュールを `backend/src/pitchlog/repositories/tenant_context_issuance.py` に置く。公開関数は `issue_tenant_context_from_presented_token(value: str, presentation: TokenPresentation) -> TenantContext | None` の 1 つとし、後続単位もこの関数を共用する。API 層の `api/tenant_access.py` の依存関数 `require_tenant_access` だけがこれを呼ぶ。`require_tenant_context` という名前は API 全ソースの禁止部分文字列 `text(` に当たるため採らない。

依存関数は `request.app.state.token_presentation` の署名器を渡す。発行関数は `create_database_engine()` で接続資源を得て、内部で γ の公開入口 `verify_tenant_id(value, presentation, engine)` を呼ぶ。γ が UUID を返した場合に限り発行能力を使って `TenantContext` を作る。拒否時は `None` を返し、依存関数が提示値や ID を含まない固定の 401 応答へ写す。検証済みの ID は発行関数の外へ渡さない。

接続資源を発行のたびに生成・破棄するのは、現時点の `repositories/transaction.py` が操作時に `create_database_engine()` から資源を得る形に揃えたため。供給方式の共通化は Session 供給を扱う TSK-424 PR C の範囲で決める。署名器はアプリ起動時に設定された唯一のものを使い、γ の私有状態を参照しない。

選手作成時の PostgreSQL 外部キー違反のうち、ORM の `fk_players_team`・`fk_players_roster_status`・`fk_players_roster_label` は参照先を対象テナントで利用できない拒否として 404 に写す。ほかの FK、`roster_status_category = 'roster_status'` の CHECK 違反、`pk_players` の一意違反などは 404 に写さず、既存の共通エラー規約の固定 500 応答へ渡す。後者は対象資源の不在を意味せず、カテゴリ既定値やランダム生成 ID の不整合など実装・データ側の障害を含むため、404 に畳まない。応答に制約名や入力値は載せない。

名前の衝突は `git grep --untracked -n -w issue_tenant_context_from_presented_token` で全行走査する。定義、依存関数からの import・呼び出し、契約資産・配布モジュール、テストの正当な参照以外の衝突は 0 件。

TSK-457 の発行入口の保証範囲を本単位でも引き継ぐ。`getattr` による発行入口の取り出しや別名での再公開は TB007 の保証外とし、このステップで検査器の射程を広げない。
