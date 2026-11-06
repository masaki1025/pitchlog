# 毎球CSV 供給不足の引き渡し（ステップ2〜4実装時点）

対象HEAD: `6646c7f7` 系。基線 `14b96546`。本書は「実装済みだが列を完成できない」ものだけを列挙する。0・NULL・現在名簿で補った列はない。HTTPは欠測を `409` の `missing_column.<index>.<header>.<group>` として返す。

## 1. 実装側で追加が必要な列

| 列 | group | 現状 | 必要差分 |
|---|---|---|---|
| 34 球数 | G04-A | 未接続。保存T1の `statFlags.投球数` は1球ごとの可否だけで累計ではない | `backend/src/pitchlog/repositories/play_export_primitives.py::ReadPlayExportPrimitives` と、`backend/domain/play-export.model.json` の有限reducerから `backend/src/pitchlog/exports/generated/play_primitives.sql` を生成する。同RRの `tenant/game/pitcher_id`、source D2順、`play_rows.event_kind='pitch'` のCOUNT window。Python/JSの全event累積は不可 |
| 42 コースX / 43 コースY | G03 | `observations.course` の正準k（unit=1/263）は読めるが、旧画面座標への変換targetが無い | `backend/domain/play-export.model.json` のcoordinate-transform宣言→`backend/src/pitchlog/exports/generated/coordinate_transform.py`。B-7の保存→画面（x=kx, y=263-ky）を単一実装にする。既存 `courseQuantization` は入力形成で逆変換ではない |
| 50 打球位置X / 51 打球位置Y | G10 | `play_rows.hit_x/hit_y` は0〜1正規化。旧画面座標へのB-6 field geometry targetが無い | G03と同じD-1宣言へfield geometryの型付き別計算を追加し、`contracts/field-regions/field_region_seed_v1.json` の `fieldImage.normalization` から生成targetを作る。コースk263の推測転用はしない |
| 61 打席結果 / 62 Result_col | G04-R | 保存T1・打撃結果key・捕球選手・打球typeは揃うが、旧表示合成のformatterが無い | D-1の表示規則から生成するformatter target。`見三振`/`空三振`/`6G`/`4L併` 等の合成をPythonへ手書きしない |
| 73 先攻打順 / 74 後攻打順 | G04-R | `state.battingOrder` は攻撃側のみ。守備側の現在打順ポインタは保存T1に無い | 両チームの打順ポインタを保存する記録metadata、または同RRで読める保存投影。攻撃側から守備側を推測しない |
| 86 top_score / 87 bottom_score | G04-A | 保存T1の `scoreboard.inningScores` は累計 `{home,away}` で、旧16要素配列（回別得点+末尾4）ではない | 34と同じDB primitiveで、確定済みT1のbefore/after得点差分を `tenant/game/攻撃側/回` でGROUP BY/window集計する。旧配列末尾4の定義はDL precedenceの契約に従う |
| 40 プレイの種類（non_pitch行） | G02 | `play_rows.event_kind` は `pitch`/`non_pitch` のみ。旧区分（牽制/ボーク/ピッチクロック違反等）の保存値が無い | non_pitchの旧区分を保存する記録metadata、または受理済みpayloadからの表示binding。pitch行は「投球」を供給済み |

## 2. 記録時snapshotが必要な列（現在参照で暫定供給）

| 列 | group | 現状 | 必要差分 |
|---|---|---|---|
| 27 打者氏名 / 32 投手氏名 / 35 捕手 | G06 | 現在の `players.name` を参照。記録後に改名すると出力名が変わる | `backend/src/pitchlog/sync/play_export_identity.py` と `sync/{first_ball,ordinary_pitch}_projection.py` の既同TXへ、記録時点の表示名snapshotを追加する。共有同期核の変更になるため本ブランチでは直接編集していない |
| 63 打者登録名 / 65 一走登録名 / 67 二走登録名 / 69 三走登録名 | G06 | 同上。旧列の「登録名」としては現在参照を供給するが、履歴名ではない | 同上。source_kindを `current_reference` と `recorded_snapshot` に分ける |
| 64/66/68/70 走者番号 / 71 投手番号 | G06 | `GameLineup.entries_with_uniform_number_snapshot` と `ParticipationInterval.uniform_number_snapshot` を優先。両方に無い場合だけ現在値を出さず欠測にする | 交代・移行記録の全区間snapshotを記録時に保存する。現状は保存済み区間が無い場合に欠測 |

## 3. 意図的にNULL（新規nativeの元不在）

- 72 入力項目: 新規nativeに旧移行原字面が無い。
- 75 経過時間 / 77 現在時刻: 旧TagはWon't。記録時刻列が無いため、現在時刻や経過時間を生成しない。
- これらは「未供給をNULLで埋めた」のではなく、新規nativeの元NULLとして `projections.csv` に記録する。

## 4. 制限付き資産の差分

`handoff/restricted-assets.patch` は、次の3ファイルの基線 `14b96546` からの差分である。共有同期核・`contracts/authz/*`・oracle seal・主担当台帳は変更していない。

- `backend/src/pitchlog/repositories/operation_registry.py`: 5 read operationの登録。
- `backend/src/pitchlog/repositories/repository_contract.py`: 生成済みtoken/capability一覧。
- `contracts/tenant_boundary/repository-contract.json`: 上記の生成元資産（`scripts/rederive_tenant_generated_modules.py` で再導出済み）。

`CAP:play_runners:read` と `CAP:participation_intervals:read` は既存の product capability catalog に存在するread capabilityを使う。新しい表・関数・sealは追加していない。
