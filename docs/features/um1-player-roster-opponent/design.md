---
feature: um1-player-roster-opponent
type: design
date: 2026-09-24
---

# 詳細設計: U-M1 選手・在籍・対戦相手チーム

計画書: [plan.md](plan.md) / 調査メモ: [research.md](research.md)

## 根拠の層(U-00 / U-01 の書き分けを継承)

- **(A) 要件・設計正本の直接帰結** — 破ってはならない
- **(B) U-M1 の設計判断** — **`TSK-346`(API 契約の正本・未着手)が別の形を定めたら `TSK-346` が正**

U-01 は**型だけ**を確定し中身を葉に残した([`../u01-dto-base/design.md`](../u01-dto-base/design.md)`:150`
「**上限は置かない。既定値も置かない。**」/ `:152`「**`cursor` / `next_cursor` の中身は不透明で、書式は `U-01` で決めない(葉と `TSK-346` の判断)**」)。
**本書の (B) は U-00 の前例**([`../../worklog/2026-09-16-u00-api-shell.md`](../../worklog/2026-09-16-u00-api-shell.md)`:124`
— 403→404 の写像 / 封筒に `code` を置かない)**と同じ形で `TSK-346` へ申し送る**。

## 1. 暫定規約(D1〜D6)

| # | 決定 | 値 | 層 | 根拠 |
| --- | --- | --- | --- | --- |
| **D1** | **ページサイズの上限** | **200** | **(B)** | 要件書・付録 C に数値が無い(実測)。旧の規模は「1 チーム数十名 × 年次入れ替わり・**無期限保持**(卒業選手は OB 化)」([`../../legacy/requirements-tsukuba-pss-v0.2.md`](../../legacy/requirements-tsukuba-pss-v0.2.md)`:457-458`)。歴代を含めても 1 ページに収まりやすく、かつ全件読み込みにはならない値 |
| **D2** | **`limit` の既定値** | **置かない**(U-01 のまま必須) | **(B)** | U-01 が**意図的に**既定値を置いていない。葉ごとに既定を足すと単位間で割れる |
| **D3** | **カーソルの書式** | **決めない** — 実装詳細を露出しない不透明トークンとして扱う | **(B)** | `u01-dto-base/design.md:152`。**「決めていない」ことを本書に明示する**(書かないと `TSK-346` 着手時に既成事実として扱われる) |
| **D4** | **在籍区分キーの実値** | **`active` / `other` / `ob`** | **(B) — 新規決定** | 3 区分固定は [`../../design/data-model.md`](../../design/data-model.md)`:1425`・FR-017(A)。**キー文字列は `active` のみ同書 `:524` に典拠があり、`other`/`ob` はリポジトリ内に存在しない**(実測)。`system_vocabularies.category = 'roster_status'`(`backend/src/pitchlog/db/tenant_isolation/models.py:1114-1143`)の `key` として使う |
| **D5** | **識別子の命名** | 下記の禁止語を使わない | **(A)** | 機械検査の帰結 |
| **D6** | **`operation_id`** | `roster_<資源>_<動作>` の snake_case | **(B)** | [`../u00-api-shell/design.md`](../u00-api-shell/design.md)`:124-139`。`contracts/authz/route-registry.json` の `enums.operation_ids` 8 件(`create_group` / `issue_invitation` / `revoke_invitation` / `accept_invitation` / `leave_group` / `update_grants` / `change_role` / `close_group`)と重ねない |

### D5 の禁止語(実測 — 破ると機械検査が red になる)

| 範囲 | 禁止語 | 検査 |
| --- | --- | --- |
| `backend/src` の**追加行** | `roster_status_change` / `change_roster_status` / `player_merge` / `merge_player` / `player_split` / `split_player` / `player_identity` / `undo`(いずれも `_` 境界) | **TB004** — `contracts/tenant_boundary/base-allowlist.json:185`・`:189`・`:196` |
| **`api/**` の全ソース連結** | `sqlalchemy` / **`Session`** / `engine` / `session.execute` / `select(` / `text(` / `raw_connection` | `backend/tests/test_api_conventions.py:22-30` |
| 同上 | `idempotenc` / `seq_no` / `tombstone` / `revision_no` / **`generation`** | 同 `:31-37` |

**docstring・コメントも対象**(全文連結の部分一致)。既存 ORM 列名 `roster_status_key` は
トークン境界が違うため TB004 に**一致しない**(パターンの形から確認)。

## 2. 経路表(FR-015 / 017 / 018 / 039)

**第 2 群で実装する。**`route_id` の登録は `route_kinds` の値域拡張待ち(plan.md 4 節)。
既定拒否は**全経路 404**(FR-034 認可行列 — 要件書 `:641`「第三者として記録した対戦相手データ → 付与によらず不可 → 404」)。
403 は器が 404 へ写す(`backend/src/pitchlog/api/errors.py`)。

| # | method | path | `operation_id` | request DTO | response DTO | 既定拒否 | 越境テスト | FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | POST | `/players` | `roster_player_create` | `PlayerCreate` | `PlayerRead` | 404 | `test_roster_boundary.py` | FR-015 |
| 2 | GET | `/players` | `roster_player_list` | `PlayerListRequest` | `Page[PlayerRead]` | 404 | 同上 | FR-015 / 017 |
| 3 | GET | `/players/{player_id}` | `roster_player_read` | — | `PlayerRead` | 404 | 同上 | FR-015 |
| 4 | PATCH | `/players/{player_id}` | `roster_player_update` | `PlayerUpdate` | `PlayerRead` | 404 | 同上 | FR-015 / 017 |
| 5 | POST | `/players/status-preview` | `roster_player_status_preview` | `PlayerStatusBulkRequest` | `PlayerStatusPreview` | 404 | 同上 | FR-017(プレビュー→確認→実行) |
| 6 | POST | `/players/status-apply` | `roster_player_status_apply` | `PlayerStatusBulkRequest` | `Page[PlayerRead]` | 404 | 同上 | FR-017(一括変更) |
| 7 | DELETE | `/players/{player_id}` | `roster_player_delete` | — | `PlayerRead` | 404 | 同上 | FR-018 |
| 8 | POST | `/team-records` | `roster_team_create` | `TeamRecordCreate` | `TeamRecordRead` | 404 | 同上 | FR-039 |
| 9 | GET | `/team-records` | `roster_team_list` | `TeamRecordListRequest` | `Page[TeamRecordRead]` | 404 | 同上 | FR-039 |
| 10 | PATCH | `/team-records/{team_record_id}` | `roster_team_update` | `TeamRecordUpdate` | `TeamRecordRead` | 404 | 同上 | FR-039(リネーム誘導) |
| 11 | DELETE | `/team-records/{team_record_id}` | `roster_team_delete` | — | `TeamRecordRead` | 404 | 同上 | FR-039 |

**経路数 11 本**は分割検討の起動条件「経路 10 本超」([`../product-impl-unit-split/design.md`](../product-impl-unit-split/design.md)`:136-145`)に**触れる**。
**分割しない判断**: 主所有 FR は 4 件(閾値 5 件未満)で、11 本は同じ 2 資源(`players` / `team_records`)の CRUD + 在籍区分の 2 経路に収まる。
**5・6 を 1 経路に畳めば 10 本**だが、FR-017 が「**プレビュー→確認→実行**」を受入基準に持つため畳まない(要件の直接帰結)。
**第 2 群の着手時に経路数を再確認する**。

**パスに `roster-status` のようなハイフン表記を使う**理由: TB004 は `_` 境界のパターンなので、
ハイフンのパス文字列は一致しない。`operation_id` は snake_case だが `roster_player_status_*` の形で
`roster_status_change` / `change_roster_status` のいずれにも一致しない。

## 3. DTO 定義(第 1 群 — `backend/src/pitchlog/api/schemas/roster.py`)

ORM は実装済み(`backend/src/pitchlog/db/tenant_isolation/models.py`)。**列は再定義せず写す。**

### `TeamRecordRead(ReadSchema)`

| フィールド | 型 | 必須 | 由来 |
| --- | --- | --- | --- |
| `id` | `EntityId` | 必須 | `TeamRecord.id` |
| `kind` | `Literal["self", "opponent"]` | 必須 | `CheckConstraint("kind IN ('self','opponent')")`(`models.py:89`)。**`tenant_id` では自他を判別しない**(`data-model.md:1335-1347` 敵対レビュー P0-1 の是正) |
| `name` | `str` | 必須 | `TeamRecord.name` |
| `hidden_at` | `Timestamp \| None` | 省略可 | 論理削除(`DeletionLifecycle.HIDDEN`) |

**`tenant_id` を応答に出さない**(`EntityId` の docstring「テナント文脈を含まない・認可判定に使わない」— `schemas/base.py:21-26`)。

### `TeamRecordCreate(BaseSchema)` / `TeamRecordUpdate(BaseSchema)`

- `Create`: `name: str`(1 文字以上)のみ。**`kind` を受け取らない** — `kind` は `protected_columns`(`models.py:135`)で不変、かつ
  `UNIQUE (tenant_id) WHERE kind='self'`(`models.py:110-116`)があるため **API から作れるのは `opponent` だけ**
- `Update`: `name: str` のみ(`allowed_update_columns = {"name", "hidden_at"}`)
- **チーム名に一意制約は無い**(`data-model.md:1363-1364`)。**類似名は警告**であってエラーにしない(FR-039)

### `PlayerRead(ReadSchema)`

| フィールド | 型 | 必須 | 由来 |
| --- | --- | --- | --- |
| `id` | `EntityId` | 必須 | `Player.id`(**不変** — `protected_columns={"id"}`) |
| `team_record_id` | `EntityId` | 必須 | 複合 FK `(tenant_id, team_record_id)`(`models.py:144-150`) |
| `name` | `str` | 必須 | 表示用属性 |
| `throws` | `Literal["right","left"] \| None` | 省略可 | `Text` nullable。**列レベルの CheckConstraint は無い**(実測)ので DTO 側で値域を課す |
| `bats` | `Literal["right","left","both"] \| None` | 省略可 | FR-015「打(右/左/両)」 |
| `uniform_number` | `str \| None` | 省略可 | **任意**。**DB の一意制約を張らない**(`data-model.md:1424` P-15) |
| `roster_status_key` | `Literal["active","other","ob"]` | 必須 | **D4** |
| `roster_label_key` | `str \| None` | 省略可 | `tenant_vocabularies` 参照(チーム拡張ラベル — Should) |
| `hidden_at` | `Timestamp \| None` | 省略可 | 論理削除 |

### `PlayerCreate(BaseSchema)` / `PlayerUpdate(BaseSchema)`

- `Create`: `team_record_id` / `name` / `throws?` / `bats?` / `uniform_number?` / `roster_status_key`(既定 `active`)/ `roster_label_key?`
- `Update`: **`name` / `throws` / `bats` / `uniform_number` / `roster_status_key` / `roster_label_key` のみ**
  (`allowed_update_columns` — `models.py:211-213`)
- **`team_record_id` を `Update` に含めない**: `protected_columns` にも `allowed_update_columns` にも入らない
  **未分類列**で `unclassified_handoff="TSK-372"`(`models.py:214-218`)。**所属チーム変更の可否がコードから読めない**(plan.md R3)
- **`uniform_number` は空文字を拒否**(`min_length=1`)。`None`(番号なし)は許す — FR-015「B 戦の番号なし選手も登録可」

### `PlayerListRequest(PageRequest)` / `TeamRecordListRequest(PageRequest)`

- `limit` に**上限 200**(D1)。`PageRequest` の `ge=1` を継承し `le=200` を足す
- 絞り込み: `team_record_id?` / `roster_status_key?`(**WHERE で絞る** — NFR-005)
- **並び順とカーソルは索引に合わせる**: `ix_players_team` は `(tenant_id, team_record_id, id)` の
  `hidden_at IS NULL` 部分索引(`models.py:173-179`)。**キーセット方式**(`data-model.md:1572`)

### `PlayerStatusBulkRequest(BaseSchema)`(第 2 群)

- `player_ids: list[EntityId]`(上限 200 — D1 に揃える)/ `roster_status_key: Literal[...]` / `roster_label_key: str | None`
- **全区分可逆**(FR-017)なので遷移の方向を制限しない

## 4. 越境テストのファイル名(第 2 群)

**`backend/tests/test_roster_boundary.py`**。`test_authz*` を使えない
(`.claude/core-areas.json:319` の `backend/tests/test_authz*.py` に一致し、**機械判定でコア paths に引きずり込まれる**ため)。
fixture は **`backend/tests/api_fixtures.py`** へ置き明示 import する
(`backend/tests/conftest.py` は `backend/*conftest.py`(同 `:326`)に一致するため**差分 0 行**を守る)。

## 5. `TSK-346` への申し送り

**(B) の決定はすべて `TSK-346` が別の形を定めたらそちらが正。**

1. **ページサイズの上限を 200 とした**(D1)— 要件書に数値が無く、根拠は旧システムの規模のみ
2. **`limit` の既定値を置かなかった**(D2)— U-01 に揃えた
3. **カーソルの書式を決めていない**(D3)— 不透明トークンのまま
4. **在籍区分キーを `active` / `other` / `ob` とした**(D4)— **`active` 以外は典拠が無い新規決定**
5. **`operation_id` を `roster_<資源>_<動作>` とした**(D6)
6. **経路が 11 本で分割検討の起動条件(10 本超)に触れるが分割しない**と判断した(2 節)
