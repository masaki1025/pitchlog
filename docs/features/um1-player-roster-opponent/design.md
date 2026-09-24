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

**下表は入口 11 本。`route_id` は未定**(`route_kind` の値域決定が空席 — plan.md 4 節)。
**分割検討の閾値「経路 10 本超」**([`../product-impl-unit-split/design.md`](../product-impl-unit-split/design.md)`:136-145`)は
**route registry から経路を数える契約**なので、**`route_id` 付与後でなければ判定できない**。本書では判定を保留する。

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
- `Update`: `name: str` のみ(`allowed_update_columns={"name","hidden_at"}` — `models.py:135` 付近)
- **`TeamRecordCreated`**: `TeamRecordRead` + `similar_names: list[str]`。
  **チーム名に一意制約は無い**(`data-model.md:1363-1364`)。**類似名は警告**であってエラーにしない(FR-039)ため、
  **登録は成功させたうえで応答に警告を載せる**

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
- **`team_record_id` を `Update` に含めない**: immutability の `protected_columns` にも `allowed_update_columns` にも入らない
  **未分類列**で `unclassified_handoff="TSK-372"`。**所属チーム変更の可否がコードから読めない**(plan.md R3)

### `PlayerCreated`

`PlayerRead` + **`same_number_players: list[PlayerRead]`**。
FR-015「同番号で登録 → **警告が表示される(意図的なら登録可)**」(要件書 `:361`)を満たすため、
**登録は成功させたうえで同番号の現役選手を応答に載せる**。

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
9. **入口 11 本の分割判定を保留した**(`route_id` 未定のため)
