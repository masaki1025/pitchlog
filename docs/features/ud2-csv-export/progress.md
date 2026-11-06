# 毎球CSV ステップ2〜5 実装候補・引継ぎ

## 2026-11-07 交代後snapshot修復候補（作者owned実測）

専用枝 `fix/mvp-play-csv-substitution-snapshots` は画面受入 `324a7963` を基線とし、開始時名簿参照を現役選手へ無条件に流用していた失敗を是正中。受理済み交代eventと0044同TX receipt、記録時の保存native sourceとplayer氏名/背番号を同writer内で照合する候補を追加した。交代後次球は非play sourceの `checkpoint.content.restored` を使う。固定試験HEAD `41caa778f457008d01a9dcf7b41f19ae3a4d8d22` のowned PG `substitution-r3` は1 pass/110.74秒。真正交代→次球→旧2 CSV行不変・新3行目の交代投手氏名/番号11→別App再読込まで通過し、前後source選定SHA同一・所有PG回収済み。現 `participation_intervals` は交代writerから更新されないため、そこへ実在しない証拠を仮定しない。非投球PlayRowの実製品writer入口と唯一T5 credit 0に整合するD-1 score SQLは未供給、正式0047/registry/7.7受理も未成立。独立270レビューのD4漏出P1へ対する監査JSON redaction、snapshot行なし409の別対向を後発候補として実装・実測中。

## 2026-11-07 画面受入候補（基線2706138c、作者実測）

旧節は当時の候補・fixture経路の履歴として保持する。新基線 `2706138c51f71bbe5136e05661bcca0255134b50` は現行v3 2球の同TX88列保存と全11 CSVの実HTTP ZIPまで所有PGで通過済み。専用枝 `feature/mvp-play-csv-screen-acceptance` の固定試験HEAD `d6ff4727c10eff25032762271fef7b66a8e89e93` で、実画面の「毎球CSVへ」からChromiumダウンロードした59,346 bytesをHTTP Content-Length/SHA256と突合し、同じowned PGの2球原本・88列・11 CSV・sidecar・各ファイルhash/行数へ照合した。BE試験1 pass/95.01秒、Playwright 1 pass/40.0秒。code/SQL/driver等920追跡pathの前後SHAは一致し、所有PGは回収済み。直前のr2は初球POST/GET待ち30秒で失敗し、同じ製品sourceのr3で通過したため、待ち超過履歴を消さない。試験用固定ACK/完成88列投入は行わない。候補DDL直接設置と正式0047/7.7、実機/運用TLS、P3等の全試合受入は別証拠。

最終更新: 2026-11-06（候補・未統合）

## 1. 固定点

| 項目 | 値 |
| --- | --- |
| 主repo | `/home/ymdms/projects/pitchlog` |
| 起点worktree | `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-play-csv-connection` / HEAD `14b96546` |
| 作業worktree | `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-play-csv-product` |
| branch | `feature/mvp-play-csv-product`（push済み・PR未作成） |
| 既存step1 | `14b96546`（88列/9sidecarの型・`stream_csv`・ZIP/hash・故障試験、全70成功） |
| 計画 | `docs/features/ud2-csv-export/plan.md`（承認済み・5ステップ） |
| 隔離PG共通ロック | `/home/ymdms/.cache/pitchlog/test-coordination/owned-pg-browser-network.lock` |

## 2. 実装した範囲

### ステップ2: tenant限定・同一snapshot DB抽出

- `backend/src/pitchlog/repositories/transaction.py` に `play_export_read_scope` を追加。
  - `REPEATABLE READ` + `READ ONLY` を最初のDB操作前に固定。
  - 実scopeのhandleだけを許可し、通常scope/別handleを拒否。
- `backend/src/pitchlog/repositories/play_export.py`
  - 可視game、有効PlayRow（受理event結合）、全受理event（置換/退役前含む）、
    runner一括結合、lineup、participation、参照player/team/vocabを同一RRで読む。
  - PlayRowは `(play_number,id)` のkeyset、runnerはページ内 `play_id` 一括結合。
  - 未供給の88列projectionは `public.play_export_snapshots` の有無で判定し、
    無い場合に0/NULL/現在名簿へ補完しない。
- 候補table: `docs/features/ud2-csv-export/candidates/play_export_snapshots.sql`
  （`plays_csv_json` に88列の完成値、app SELECTのみ、RLS tenant）。

### ステップ3: ZIP API

- `backend/src/pitchlog/exports/play_export_csv.py`
  - 88列本体は記録時projection `plays_csv_json` を写すだけ。T1再計算なし。
  - 9サイドカー（play_links/events/runners/lineups/participations/game/references/
    projections/preserved_sources）を同一bundleから構築。
  - `prepare_play_archive`（step1）と `stream_csv` を再利用。
- `backend/src/pitchlog/api/routers/game_exports.py`
  - `GET /games/{game_id}/exports/plays.zip`
  - 401/404/409/503、tenant越境404、未供給409 `EXPORT_SOURCE_UNAVAILABLE`。
  - 完成ZIPを応答用一時ファイルへ写してから `Content-Length`/
    `X-Pitchlog-Archive-SHA256`/`Cache-Control: no-store` を返す。
  - 部分ZIPを200で送らない。接続終了時にtempをclose。
- **製品appには未登録**。owned検証のapp scriptだけが `app.include_router` で接続する。
  正式route registry/capability/repository contractは主担当の差分。

### ステップ4: 画面

- `frontend/src/api/client.ts` の `apiDownload` に
  `contentLength`/`sha256` を後方互換で追加。
- `frontend/src/api/gameExports.ts`、`GameCsvExport.vue`、
  `GameExportScreen.vue`、router `/games/:gameId/export`。
- 長さ/SHA-256一致後のみobject URLを作成して保存。不一致/401/404/409/503は
  再試行可能な失敗として表示。二重押下を1回に閉じる。
- 実Vite/Chromium/実機の画面操作は未実施。Vue単体（4件）とAPI client（57件）のみ成功。

### ステップ5: 実DB/HTTP/ZIP検証

`backend/tests/db/test_play_export_http.py` **1 passed / 87.85秒**:
- 既存の実HTTP新規作成→開始→通常3球→再送/reloadを再利用。
- 88列projection未投入: **409** `EXPORT_SOURCE_UNAVAILABLE`。
- 試験fixtureで88列projectionを投入後: **200**
  - 10CSV（88列+9サイドカー）+ manifest
  - `Content-Length`/`X-Pitchlog-Archive-SHA256`/ZIP bytes一致
  - 3 play、events、lineups、references等のsidecar行
  - `plays.csv` の数式セルが `'=1+1` に無害化（既 `stream_csv` 再利用）
- 不存在game **404**、未ログイン **401**、別tenant **404**。
- 隔離PGのfixture作成から後始末までを共通ロック
  `owned-pg-browser-network.lock` で囲む（`backend/tests/db/owned_pg_network_lock.py` の
  autouse fixture）。画面試験中のDockerネットワーク変更との干渉を防ぐ。

## 3. 未接続（製品完成へ読み替えない）

**最重要: 88列projectionの記録時producerが未実装。**
候補table `public.play_export_snapshots.plays_csv_json` を、新規記録の同一TXで
書く producer/trigger がまだ無い。このため実gameは409で、200は試験fixtureでのみ成立する。
以下はproducerへ必要な列群と提供元（supply-matrix準拠）:

| 列群 | 提供元 | 不足 |
| --- | --- | --- |
| 0-9,26,28-31,39-41,44-58,60 | Game/PlayRow/語彙 | 抽出可。表示辞書の旧互換写像は未接続 |
| 10-19,33-34,59,61-62,73-74,86-87 | 保存T1 before/after、roster、打者位置 | projection producerで完成値化が必要。T1再計算は禁止 |
| 20-25,36-38 | PlayRunner + 履歴名簿 | 抽出可。旧status文字列/打順の写像が未確定 |
| 42-43 | payload observations.course | canonical k→`x=kx,y=263-ky`。D-1宣言target未接続 |
| 63-71 | 履歴player名/背番号 | 記録時snapshotが必要（現在名簿で補完しない） |
| 72,75,77 | 入力経路/記録時刻 | 記録時metadataが必要（OperationEventに時刻列なし） |
| 78-85 | 各play時点のlineup/participation | 記録時roster snapshotが必要。旧非対称配列のfixture未固定 |
| 50-51 | 打球座標 | 保存hit_x/hit_yは正規化。旧field geometry変換が未接続 |

- 正式認可/tenant: `public.play_export_snapshots` の正式migration/ACL/RLS、
  新route registry/capability catalog/repository contract、
  `play_export_read_scope` のcore登録・seal/7.7。
- `GameScreenEntryRecordHost.vue` への実リンクは未接続。現状は
  `/games/{id}/export` の候補routeで動作する。
- 画面の実ブラウザ/Playwright、500行境界、訂正/取消/再開/再終了/新世代、
  大量データ、切断/容量故障、実機は未実施。
- 既存step1の契約JSON/候補statusは本枝で `accepted` へ更新していない。

## 4. 主担当への差分

1. `play_export_snapshots` の正式migration（tenant FK/RLS/app SELECT）と、
   新規記録の同一TXで `plays_csv_json` を書くproducerを共有同期核へ接続する
   （共有核は直接編集せず、別パッチで渡す）。
2. `game_exports.router` を製品appへ登録し、route registry/認可/capability/
   repository contractへ追加する。
3. `play_export_read_scope` のcore境界登録とseal/7.7。
4. `GameScreenEntryRecordHost.vue` へ `GameCsvExport` を導線接続する。
5. 88列producerのfixture（G03/G04/G06/G07/G08/G09/G10）を確定し、
   実game→200を再実測する。

## 5. 検査

- `backend/tests/test_play_csv_rows.py` + `test_play_export_archive.py`: **70 passed**
- `backend/tests/db/test_play_export_http.py`: **1 passed / 87.85秒**
- backend Ruff/Ty: 成功
- frontend `GameCsvExport.spec.ts`: **4 passed**
- frontend `client.spec.ts`: **57 passed**
- `vue-tsc`/ESLint: 成功

## 2026-11-07 交代後snapshot・監査redaction・球数creditの限定修復候補

専用枝 `fix/mvp-play-csv-substitution-snapshots` は旧 `2706138c` と画面枝 `324a7963` を変更せず、実記録時の出場者を受理済み交代event・0044 receipt・今回の保存sourceへ照合する。owned PostgreSQL の固定 `substitution-r5` では、交代 ACK、次球保存、交代前2球のZIP不変、交代後の新投手氏名・背番号、別リクエストでのZIP再読込、非投球交代の監査行を確認した。実行前後のsource全byteは同一で、owned containerは削除済み。`substitution-r4` では破損snapshot行と対象試合のsnapshot行欠測を別々の実HTTP 409として確認した。

監査eventの業務JSONは有限event kindと版付きredactionへ写し、D4・既知資格鍵は表示可能な置換形へ、未知秘密様鍵は閉拒否する。別JSON欄も同じ鍵検査を通す。真正lifecycle D4を含むZIPの実DB対向と正式contract受理は未了。

score専用D-1候補は、保存T5の `pitch_count` state・0/1 credit配列と同版fact行を照合する。`pitch`/`non_pitch`の保存PlayRow区分とT1原本区分が一致する行だけを読ませ、非投球の0球を強制1球へ変えない。既T5 model・生成facts・旧pitch vectorの値は変更しない。真正 `non_pitch` PlayRowの製品保存経路と、それを経由した88列ZIPは別枝で実装中であり、この候補の純試験成功を実接続成功へ読み替えない。正式score資産・writer関数・0047の受理はrootが直列で扱う。

固定 `554f502b` の owned `score-r1` では既3球のscore/球数全値と交代後ZIPの2件が成功し、source前後全byte一致・owned container削除済み。後続の非投球専用観測は `observations={"kind":"intentional-walk"}` で投球座標/速度を持たないため、保存PlayRowの `event_kind=non_pitch`、T1 `non-pitch-event`、course_x/y・速度等のNULLへ閉照合する候補を別コミットで追加した。通常投球の座標欠測、未知variant、片側だけのNULLは拒否する。これは非投球の実DB通過証拠ではない。
