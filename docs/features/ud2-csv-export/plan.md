---
feature: ud2-csv-export
status: active
承認: 済（PO委任によるCodex主担当判断、2026-11-04）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-play-csv-connection
created: 2026-11-04
計画レビュー周回: 3
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 1試合の毎球CSV・サイドカーを実供給する

## 1. 目的と受理範囲

記録した1試合を実画面からダウンロードし、88列本体と新概念の別CSVを、同じDB版で取り出せるようにする。対象は今回MVPの新規PitchLog記録。過去データ移行と旧ピクセル/旧名簿の原字面復元は後続であり、本計画の前提にしない。FR-031・付録D-1/D-3・NFR-005/014/018/019/023を満たす。成績CSVとは別資源であり、T5/T6の計算・供給を待たず準備できる。成績の指標・暦年の裁定は変更しない。

今回の編集許可は本feature配下の候補文書だけ。**本計画は独立レビューと主担当の今回のPO委任判断による対象SHA承認後に実装する**。共通writer計画の承認は流用しない。rootがステップごとに指示し、そのステップで止まる。コミット実施者はAGENTS.mdに従う。

基線40ce2e312bc46435239f2a6d0ea0f1fb919a5de0。成果は`plays.csv`（88列固定）と[sidecars.candidate.json](sidecars.candidate.json)の全サイドカーを含む単一ZIP。JSON manifestで形式版・snapshot・ファイルSHA256/サイズ/行数を記録する。記録済み試合は進行中・中断中もFR-031対象であり、成績の「終了確定のみ」をCSVへ誤適用しない。確定保存された全プレイ（投球/非投球）、交代・補正等の全記録を省かない。未同期の端末キューはサーバー確定記録と混ぜず、画面で未送信があることを示す。

## 2. 再利用と供給境界

- `backend/src/pitchlog/exports/csv.py::stream_csv`と既54試験相当の契約を再利用。CSVの数式無害化・BOM/CRLF/NULLを作り直さない。
- 旧`/home/ymdms/projects/Baseball_Scoring/config.py::COLUMN_NAMES`をAST literalで読み、**88列をそのまま**[columns.candidate.json](columns.candidate.json)に固定した。モジュール実行なし。列の意味は版固定`docs/legacy/research/data-layer.md` §2、保存先は正式`docs/design/data-model.md` §12-1/12-2。55はエラー野手、60はコメント、7=後攻/8=先攻を守る。

- B-7表示座標の技術配置追補（2026-11-07、PO委任によるCodex主担当/root判断）: 既承認のD-1有限宣言/生成方式を維持し、T5 `canonicalEventFacts` から直交する表示宣言を `backend/domain/play-export-display.model.json` へ分離する。`play-export.model.json` のT5共通hash・旧v3保存profile・27数学goldenは変更しない。専用schema/manifestでgeometry契約と生成器/両targetを全byte束縛し、B-7既42例のうち正準保存→画面16例を独立期待として照合する。これはB-7の意味改訂ではなく、本計画の生成入力配置だけの追補である。新表示targetの正式受理・製品接続は候補検査と分ける。
- 新規記録の列50/51/72/75技術binding追補（2026-11-07、PO委任によるCodex主担当/root判断、独立確認前の候補）: 列50/51は受理済V7 `observations.battedBall.hitX/Y` の保存正規化文字列を同TXのPlayRow Doubleと照合して原字面で出し、manifestに`normalized-bottom-left`/`0..1`を明示する。旧pixelへの逆変換・値byte互換は主張しない。列72は真正V7のformat/calculation sourceとsource event idのみを版付き閉JSONへ保存し、旧入力flagを仮発明しない。列75は試合の自動`started_at`と同TXサーバー受理時刻からD-1生成targetで完了分`h:mm`を得る。開始欠測・負の差は拒否し、現場端末の観測時刻や廃止Tagと混同しない。日時はPostgreSQL `timestamptz`のマイクロ秒精度の瞬間をUTC正規化後に比較し、TS `Date`ミリ秒への丸めをしない。この列の生成targetはPythonサーバー専用であり、TSには未使用の類似関数を公開しない。88列見出し・順序と既履歴原本は不変。実writer/ZIPの成功と正式asset受理は別証拠とする。
- 列61/62の技術binding追補（2026-11-07、PO委任によるCodex主担当/root判断、独立確認前の候補）: 61は保存済みT1打席完了フラグと同TXの打撃結果語彙・捕球選手・打球種類をD-1専用表示宣言の生成targetへ渡す。継続打席は明示NULL、完了打席の結果欠測は拒否する。62は61の同じ完成表示source・同じ版のaliasであり、独立判定式を持たない。旧初期値`0`を新記録へ補完しない。
- G04-Aの既生成SQL不足に対する技術追補（2026-11-07、PO委任によるCodex主担当/root判断、独立確認前の候補）: 既T5 model/旧v3保存profile/27数学期待は変更せず、`backend/domain/play-export-score.model.json` の専用D-1有限宣言と `backend/src/pitchlog/domaingen/play_export_score.py` から `backend/src/pitchlog/exports/generated/play_export_score.sql` を生成する。源の確定集合Sは既T5 nativeの全byte検証済み `canonical_members` selectorを再利用する。球数は同Sの保存T5 `pitch_count` credit、回別scoreは同Sの保存T1 before/after scoreboard差とT2半回完了原本だけをDBのGROUP BYで読む。旧12回枠は第13回以降を12枠へ折りたたむ表示とし、同一snapshotの全回/未消化・進行中・完了状態を別sidecarへ保持する。新規得点判定・Python/TS合算・既9sidecar無言削除をしない。writer専用資格関数/実DB・ZIPはこの候補の後続接合として検証する。
- 全回保存値のZIP追補（2026-11-07、PO委任によるCodex主担当/root判断、独立確認前の候補）: `inning_scores.csv`を10番目のsidecarとして追加し、同一RRで読んだ最後の有効playに束縛する同TX `full_innings_json` から行単位に写す。既9sidecarは維持し、形式候補をv2とする。各回の`unplayed`/`in-progress`/`completed`とNULL/0を原状保持し、旧12回枠から再合算しない。P3等でcurrent play順が未供給なら409へ閉じる。正式資産の受理・全履歴対応は別証拠とする。
- TSK-271成果`docs/features/legacy-column-mapping/research.md`は意味・センチネル調査として利用し、調査の承認を88列正式写像の承認には読み替えない。旧U-G1/U-D2には利用可能な専用製品コード・正式schemaを今回の対象検索で確認できていない。
- 正式PlayRowに保存列はあるが、10–19/33–34/59/61–62/73–75/77/86–87等は正規計算側の完成値、20–25/36–38は走者結合、63–71は履歴の選手名/背番号、78–85は各プレイ時点の名簿を要する。CSV側はT1をリプレイ/再判定せず、T1/表示/既存座標正本の**受理済み投影**を受け取る。公開投影の無い箇所は[supply-matrix.md](supply-matrix.md) G03/G04の現行D-1宣言/生成target・共通DB primitiveを本計画で追加する。既存保存状態を読み出す抽出と、入力から状態を再計算することを区別する。
- 未供給をNULL・0・現在名簿・初期配列で埋めない。全88列のsource_receipt（提供者、型、保存場所、対象SHA、NULLの意味、照合fixture）を埋める。供給不足は構造化した非成功で返し、部分的88列を製品完成としない。供給の欠測はsupply-matrixへ列群単位で固定し、rootが所有する同計画の有限追加producer/adapterで閉じる。既ownerの未回答を無期限待機しない。既T1/T2の記録結果の意味は変更せず、その受理済み出力を利用する。

## 3. 製品の経路

`GET /games/{game_id}/exports/plays.zip`（候補operation_id=`game_play_csv_export`）。既`TenantMatchedRoute`/`require_tenant_access`と通常ユーザーの生記録読取認可を使い、保守権限・記録権保持を読取要件に足さない。存在しない/別tenant/共有グループ/hidden/trashedは404。認証失敗は既401契約。供給不足は409 `EXPORT_SOURCE_UNAVAILABLE`、同一版が取れない場合409 `EXPORT_SNAPSHOT_CHANGED`、既存RG1/DB利用不能は503、出力構造・ディスク障害は安全な5xx。内部キー・SQL・payloadはエラーやログへ出さない。

認可済み**同一tenant transactionのREPEATABLE READ**でgame・確定イベント・有効PlayRow・runner・出場区間・lineup・補助値を取得する。現在のtransaction helperにはこの保証がないため、専用scopeの追加または既scopeの限定拡張をステップ2で実装し、tenant binding/RG1を迂回しない。分離レベルは最初のDB操作より前に固定。snapshotはDB一貫読取に加え、gameの確定event/slot version集合のdigestと各source versionをmanifestへ記録する。D4や資格・トークン・proofは出力しない。新しいexport_idは成果物識別だけで同期版の代用にしない。

全クエリはtenant_id/game_id、hidden_at/trashed_at/retired_at/replaced_at等の資源別条件をDBで絞る。最新本体は有効なPlayRowと有効な生成元イベント、監査サイドカーは同snapshot内の置換・取消前を含む受理記録を明示区別して含める。拒否イベント・隔離raw・認証/端末資格は生プレイ資源へ便乗させない。退避/採用された記録の必要業務データは独立サイドカーへ出し、資格を除く。

本体は`(play_number,id)`、イベントは`(d2 NULLS LAST,id)`、他資源は安定した複合PKのキーセットで各最大500行。既索引`ix_play_rows_game_order`/`ix_operation_events_replay`を使い、追加索引が必要ならこの用途だけを移行する。NULL d2イベントは別の`id`キーセットで取得し、NULLを連番に捏造しない。走者はページ内のplay_id集合で一括結合しN+1を作らない。OFFSET/全試合読取/Python集計/全行list化は禁止。

DB読取中に一時ファイルへ各CSVを有限バッチで書き、ZIPを完成してCRC/manifest/ダイジェストを検証してから200を送る。ZIPはCSVを別ファイルで包むだけで、88列へ列追加しない。生成失敗/取消/容量不足では200を返さず一時成果を破棄する。一時ファイルは利用者データのDB削除ではなく出力作業領域であり、成功/例外/切断の全経路で閉じて除去。RAM全量収集を避け、出力全量の一時ディスク量は測定・監視する。送出直前に同じtenantで可視/認可を再確認し、撤回・削除済みなら送らない。HTTPは`Content-Length`と完成ZIPのSHA256ヘッダ、`Cache-Control: no-store`、安全な固定形式ファイル名。送出後のネットワーク故障はブラウザ側で長さ/全体ダイジェスト不一致を拒否して成功保存を止める。

画面は実`GameScreenEntryRecordHost.vue`に専用`GameCsvExport.vue`を接続し、`apiDownload`を再利用。認証/tenant切替の既staleガードを守る。取得・全体検証後だけobject URLを作って保存し、URLを解除する。成功/失敗/取消/二重押下、401/404/409/503を表示する。未供給の間も再試行可能な失敗として明示し、無内容ファイルを保存しない。

## 4. 編集範囲

列群と全9サイドカーの現在source/欠測/追加path/owner/単位/版/fixtureは[supply-matrix.md](supply-matrix.md)へ固定する。step1で保存値読取と計算の区分・D-1宣言/生成target・DB同TX metadata形成を実装し、step2で保存/DB primitive/抽出へ結ぶ。T5/T6またはTSK-250/214全体完了を一律前提にしない。

候補正式schema: `contracts/exports/{play_columns_v1,play_sidecars_v1}.json`と対応golden。実装前のstep1でこの候補から受理して配置する。契約追加に必要な個別ゲートを通し、TSK-250既所有を黙って上書きしない。

追加単一供給の範囲は現行**ADR-003 D-1/D-1-d**へ固定する。T5/DB primitiveの唯一の人手保守元は`backend/domain/play-export.model.json`、B-7表示座標だけは上記追補により`backend/domain/play-export-display.model.json`とする。B-7の必要な有限生成器/型schemaは`backend/src/pitchlog/domaingen/export_coordinate.py`・`backend/domain/play-export-display.schema.json`、DB primitiveの必要な既生成器/型schemaの限定拡張は`backend/domain/model.schema.json`・`backend/src/pitchlog/domaingen/{core.py,backends/python.py,backends/typescript.py,backends/sql.py}`。生成targetは`backend/src/pitchlog/exports/generated/{coordinate_transform.py,play_primitives.sql,play_formatter.py}`と対応TS参照target、manifest。`exports/record_projection.py`は保存T1のfield抽出/型検証/完成値直列化だけを行う。新規`frontend/src/domain/coordinateTransform.ts`/`recordExportProjection.ts`の手書きTS正本や同JS artifact追加は**この計画から撤去**した。

球数/各回scoreはrootがT5の既確定primitive供給担当として、`repositories/play_export_primitives.py::ReadPlayExportPrimitives`の単一入口を提供する。宣言reducerから生成するSQLだけが同RR snapshot内でWHERE/GROUP BY/window+索引により計算する。CSV/T5はこの同じ事実供給を消費する。Python/JSへ全イベントをページで渡し累積することは禁止。型/選択集合/取消・訂正・世代/論理順序と500境界はsupply-matrix G04-Aへ固定。T5全体・未決OPS/登板/打者数は対象外。

保存→画面のB-7規範は既決だが、その実現方式をD-14-mから拡張してはならない。出力計算は上記D-1で対象別契約・独立期待値/検査基盤を先に受理し、正本/生成物/製品呼出部/3層検査を同一変更で追加する。D-1の表現不能が具体的に判明してD-2へ置く場合は、当該対象に限定したADR/要件の正式改訂・7.6該当確定ゲートを**当該計算コード追加前**にrootが完了する。contract追加/3層検査/この計画承認だけでは方式改訂にならない。

記録時の不足metadata: `backend/src/pitchlog/sync/play_export_identity.py`、`sync/first_ball_projection.py`/`sync/ordinary_pitch_projection.py`の既同TXへの補助snapshot接続、`db/game_state/export_snapshots.py`と`*_play_export_snapshots.py`移行。自由なwire拡張/再計算はせず、履歴表示識別・入力経路・実記録時刻等の実保存が欠ける部分を新規記録時に保持する。新規metadataを保存する前の試合の欠測を推測補完しない。

製品: `backend/src/pitchlog/exports/{play_rows,archive}.py`、`repositories/play_export.py`、`api/routers/game_exports.py`、`api/schemas/game_exports.py`、既router登録、repository registry/operation/token境界、`repositories/transaction.py`の同一snapshot最小拡張。必要時の`backend/migrations/versions/*_play_export_indexes.py`とモデル索引のみ。Frontendは`api/client.ts`のapiDownload返却値へContent-Length/完成ZIP SHA256の読取metadataを後方互換で追加し（既認証検証はそのまま）、`api/gameExports.ts`、`components/game/GameCsvExport.vue`、既`GameScreenEntryRecordHost.vue`接合。対応pytest/Vitest/実HTTP/Playwright。認可・資産台帳/lockは既生成手順で必要差分のみ更新し、core pathは設計書6.3の先行宣言手順を守る。共通認可規則/署名判定/同期計算/他feature計画を改変しない。

## 5. 実装ステップ（全5ステップ）

| # | 実装範囲 | 合格条件 |
|---|---|---|
| 1 | 全88列/全サイドカー契約・独立準備とD-1供給targetを実装 | 候補JSONの88件/順序/型/意味/receipt、supply-matrixの全有限producer/adapterの型・版・fixtureを固定。C01はB-7の技術bindingで解消し、C02旧原字面復元は後続。未存在の公開投影/新規記録metadataは本計画の指定pathで追加し、外部ownerの回答待ちを完了条件にしない。供給無しをnullableにしない。正式契約追加の該当ゲート。新計算は現行D-1宣言→必要target生成。対象別契約/独立期待値/基盤の先行受理と正本/生成物/呼出部/3層の同一変更、純直列化/参照結合goldenで55/60/JSON長/座標/0とNULL/日本語/数式を確認。未受理のdomain計算は追加しない |
| 2 | tenant限定・版固定の全資源DB抽出 | 登録operationの実repositoryを隔離DBで検証。同一REPEATABLE READ、進行中/終了/再開/訂正/再終了/新世代/同番号/NULL d2/非投球を全取得。500境界で重複欠落0、RLS/tenant/可視/取消と監査履歴の区別、query planの索引/有限読込、同時更新でも版混在0。G04-Aは生成SQLのWHERE/GROUP BY/window/索引で球数/各回scoreを計算し、500境界の累計継続/訂正取消/再開再終了を検証。Python/JSの全件reduce経路0 |
| 3 | 完成ZIP生成・実HTTP登録 | 既stream_csv、全サイドカー、manifest+hashを実repositoryへ接続。401/404/409/503、越境/共有付与でも404、隠蔽、前処理/中盤/最終ZIP/ディスク不足/送出故障で成功偽装0。Content-Length/digest、cancel/切断 cleanup。fixture Portだけで合格にしない |
| 4 | 実画面ダウンロード | apiDownloadと実host接続。長さ/SHA256一致後のみ保存。Vitestでtenant変更/stale/不完全body/二重押下/取消/再試行/エラー/URL解除。実画面→HTTP→DBで記録した1試合ZIPが保存される |
| 5 | 往復・越境・故障の製品受入 | 正式統合対象SHAの実App/HTTP/隔離DBで1試合の全プレイ・非投球・交代・補正・責任投手・取消/訂正履歴を出力し、独立readerで構造値/結合キー/NULL/原JSONを比較。終了→再開→訂正→再終了、新記録世代、tenant越境/認可撤回、ページ境界、大量データ、故障/切断を確認。画面DLのbytesとbackend artifactが一致。iPhone/iPad/Mac実機未実施は未完として残す |

step1はsupply-matrixの欠測を同計画で実装する。step1内の独立準備として88列/sidecar型・保存T1抽出・参照結合・キーセット/tenant/snapshot型・ZIP生成とhash/故障試験・HTTP/DLの応答検証部品を先行できる（実route成功登録はstep3）。これらは計算式を持たず、必要方式ゲート未完でもrootが指示したこのstep1範囲を進める。step1の契約/計算が全て揃う前に完了コミットや製品成功を記録しない。そこで規範に無い新しい記録結果が判明した場合だけrootへ具体的な列/入力/原典不足を返し、未知値を仮採用しない。plan全体の承認待ちを一律の作業停止にはせず、独立レビュー・候補整備・機械列照合を進める。同計画のproducerを未実装/未受理のままstep2以降の正式供給完了にはしない。

### ステップ5の画面受入・限定技術配置（2026-11-07）

PO委任によるCodex主担当/root判断で、固定基線 `2706138c51f71bbe5136e05661bcca0255134b50` から専用 `feature/mvp-play-csv-screen-acceptance` を作り、`backend/tests/db/test_play_export_screen_e2e.py`、`frontend/src/screens/GameScreenPlayCsv.e2e.ts`・専用Playwright configと本計画/progressだけを編集する。既画面の「毎球CSVへ」導線から、実Vite/Chromium・HTTPS loopback・真正login/端末登録/開始/v3通常2球/認可付き実API/同TX候補producerを通し、ダウンロードしたZIP bytesの長さ・SHA256・88列・全11CSV・2playを同owned PGの保存原本へ照合する。候補DDL・専用関数は使い捨てowned0045に試験中だけ直接設置し、正式0047/registry受理とは分ける。資格・ACK・PlayRow/CSV完成値をfixture供給しない。ソース集合とSQL/driverを実行前後全byte照合し、Docker/PG/browser全寿命は共通flockで直列化する。実機と運用TLS、P3等の全試合受入はこの画面検査に含まない。

## 6. 完了と検証

全5ステップの製品経路が成立し、88列/全サイドカーの供給不足0、同一版・全記録の取り出し・数式無害化・有限DB抽出・認可が実測できたとき本feature完了。helper/DTO/スタブ/fixtureだけの成功、CSVのみで成績完成、未実機を実施済みとはしない。

実装時にbackend Ruff format/check・ty・対象pytest、frontend Prettier/ESLint/vue-tsc/Vitest、必要Playwright、変更箇所に対応する正式authz/core/契約検査を実行。全件反復は新差分/失敗/懸念がある時だけ。現候補作成ではpytest/DBを実行していない。

## 7. 正本への反映と残判断

FR-031・付録D・data-model §12-1/12-2の既定方針の実装であり、既規則の全面再計画はしない。契約定義の新設とAPI/DB登録の該当ゲートをstep1/3で処理する。既正本の意味変更が必要なら別の正式改訂をrootが選ぶ。[decisions.md](decisions.md) C01は既決B-7で解消し、C02は後続移行へ分離した。既決暦年や成績27項目を戻さない。

## 非作者レビュー反映

第1回: cache `ud2-plan-review-20261104/REPORT.md` SHA256 `37c5b370ebfc4e998f66c5010a7608f858aa3564d6d81a33f9a9fe300fc0733a`、P0=0/P1=1/P2=1。P1-01はB-7/A-1/geometryの既決を再確認しC01新裁定待ち・Y例を是正。P2-01は全88列/9サイドカーを有限供給matrixへ対応し、不足producer/記録metadata形成を同計画のexactpath/owner/stepへ追加。作者反映後の差分非作者レビュー・主担当承認は未実施。


反映1レビュー: `ud2-plan-reflection1-review-20261104/REPORT.md` SHA256 `af4fe980ff3b13a9becc1d0f01907b508ee890ca42b59e5b00e05983347579c6`、P0=0/P1=2。P1-01を採用しG04を保存T1の読取/整形と共通DB primitiveへ分離、全件JS累積を撤去。P1-02を採用し追加計算は現行D-1宣言→target生成へ固定。同JS artifact追加は撤去し、必要となる場合の最小正式化ゲートを当該計算追加前へ明記。反映2の非作者再レビュー/主担当承認は未実施。


## 2026-11-04 主担当採用とステップ1指示

判断者はCodex主担当/root、権限根拠は2026-10-23のMVP PO委任と、成立した操作/独立作業から実装を進める後続指示。対象は反映2の6file集合SHA256 `b17e4bf3f52f89527ba46014798819ef60d3cb81b061d1e381964ab9c89b42db`、計画本文SHA256 `16ba431d9167d35f0987da0d78786e942eb65704748d345ae71860ab66d2a87c`。非作者の第3回限定レビュー `ud2-plan-reflection2-review-20261104/REPORT.md` SHA256 `5577dfc511864d48ab9e0dea1c265f4b38b07c6372d6d724e18c940e2508ab64` でP0/P1未解消0、前2件の是正を確認し計画採用。これはPO本人の逐行確認・署名・正式CSV供給完了を意味しない。

ステップ1を開始する。まず上記範囲の保存値参照・88列/9sidecar型/契約候補の機械照合、既writer再利用、ZIP/hash/障害検査を含む独立準備を進める。正式契約の配置は該当ゲートと非作者確認後。D-1新演算や集計実装は対象別独立期待値/方式の成立後で、未知値を仮値へ置換しない。DB/記録path・共有registryの変更、HTTP route登録やstep2以降はrootが別途指示し、並行writerと重複させない。source・試験・証拠を保全しステップ1全体の未成立を明記する。
