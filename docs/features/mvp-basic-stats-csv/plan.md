---
feature: mvp-basic-stats-csv
status: in-review
承認: 候補（既mvp-stats-primitives計画の再利用・PO委任範囲。新規意味判断なし）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-basic-stats-csv
created: 2026-11-06
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 基本成績・CSV MVP接続（最小追補）

状態: **in-review（候補・未統合）**。承認は既 `mvp-stats-primitives` 計画とPO委任の範囲で行い、
本追補は新規の意味判断を追加しない。

- 起点: `a018b896bfc1ee49efc5b0912f1b6a04fd24e363`（`feature/mvp-stats-native-foundation` の固定HEAD）
- 作業枝: `feature/mvp-basic-stats-csv`
- 実Git照合: 作業開始時点の foundation worktree は `49bf535ce73c51ab843217e2dab706a0d257b2f6` で、
  `a018b896` の子3コミット（D11比較資産・runner・test）を含んでいた。本枝は固定HEAD `a018b896` から作成し、
  D11未統合候補は取り込んでいない（差は `docs/features/mvp-basic-stats-csv/progress.md` に記録）。
- 既存計画の再利用:
  - `docs/features/mvp-stats-primitives/plan.md` のステップ3〜5（T6実表集計・27項目・実API/画面・CSV）
  - `docs/features/mvp-csv-serialization/plan.md` の共通 `stream_csv`（BOM/CRLF/無害化）
  - `docs/features/ud2-csv-export/` のstep1候補（88列/ZIP部品）は**未接続の依存**として保持
  - `feature/mvp-stats-bf-calculation` のBF数学は調査のみ。26→27のnative CHECK/codec/migrationが
    未接続のため本枝へ取り込んでいない（下記「未接続」）。

## 1. 到達点（この枝で実際に動くもの）

1. 試合別の基本成績（暫定/公式）を実API→実DBで返す。
2. JST暦年のシーズン基本成績を公式/練習/合算で切り替える。
3. 打撃16項目・投手11項目のうち、既存の26十分統計から計算できる25項目を表示する。
   - 打撃: 打席/打数/安打/二塁打/三塁打/本塁打/得点/打点/四球/死球/三振/盗塁/打率/出塁率/長打率/OPS
   - 投手: 投球回/被安打/被本塁打/与四球/与死球/奪三振/失点/WHIP/球数
   - 未接続: 登板（D03の正式出場source）、打者数（D04の責任帰属source）。0補完せず
     `source_unavailable` + 理由を返す。
4. 試合別/シーズン成績CSV（BOM付きUTF-8、共通 `stream_csv`、27項目+未取得一覧）。
5. 終了確定した最新版だけをシーズン集計に使う。再開中（current_open）は公式対象外。
6. 終了確定は**製品関数として提供しない**。任意receiptを受け取るapp実行可能なfinalizeは
   receipt真正性を検証できないため、P0として候補から除外した。終了確定providerが自身のTX内で
   真正receiptとともにcompletion列を更新する。`candidates/finalize_game_stats.test-only.sql` は
   owned隔離DBのread検証専用で、正式catalog/HTTPへ接続しない。

## 2. 実装の境界

- **T5の数式を表示層へ複製しない**。打率・WHIPは `backend/domain/stats-display.model.json` に一度だけ宣言し、
  `generate_display_rates_bundle` で `stats/generated/rates.py` だけを生成する。出塁率・長打率は
  **T5のOPSが計算した同じcomponent pair**を表示し、式をT6へ複製しない（NFR-018）。
  `generated/facts.py` は共通OPS component accessorを追加し、wrapperは旧native入口と実行前pinを維持する。TSはbyte不変だが、物理Python生成byteと `t5ArtifactSetSha256` は更新する。旧保存版を新currentへ暗黙再刻印しない。
- 26十分統計の集計は既存の `backend/src/pitchlog/stats/generated/stats.sql` を唯一の式とし、
  新関数はscope条件（試合/暦年・公式/暫定）だけを差し替える。
- 画面はAPIの表示値をそのまま描画し、率の再計算・丸め・年度導出を持たない。
- 正式authz/tenant資産（`contracts/authz`・`contracts/tenant_boundary`・repository contract・
  route registry・seal）は**直接編集していない**。候補差分を
  `docs/features/mvp-basic-stats-csv/candidates/` に固定した。

## 3. 変更パス

- 新規: `backend/src/pitchlog/stats/basic_stats.py`（27項目の写像）
- 新規: `backend/src/pitchlog/stats/basic_sql.py`（候補SQLビルダー）
- 候補（tests隔離、正式受理時に製品pathへ移す）:
  `backend/tests/stats_basic_candidate.py`（固定read operation）、
  `backend/tests/stats_schemas_candidate.py`、`backend/tests/stats_api_candidate.py`
- 新規: `backend/src/pitchlog/stats/generated/rates.py`（T6表示率の派生物）
- 新規: `backend/domain/stats-display.model.json`
- 変更: `backend/src/pitchlog/domaingen/core.py`、`backends/python.py`、`formatter.py`
  （T6表示率と共通component accessor。旧8対象中Python生成1を更新、他7は不変）
- 変更: `backend/src/pitchlog/stats/facts.py`（OPSの生成核を表示層から参照）
- 変更: `backend/src/pitchlog/repositories/operation_registry.py`、`transaction.py`（追加許可のみ）
- 変更: `backend/src/pitchlog/api/app.py`、`frontend/src/router.ts`
- 新規: `frontend/src/api/stats.ts`、`components/stats/BasicStatsTable.vue`、
  `screens/SeasonStats.vue`、`screens/GameStatsScreen.vue`
- 候補: `docs/features/mvp-basic-stats-csv/candidates/basic_stats_functions.sql`、
  `candidates/authz-diff.md`

## 4. 検証（同一固定版・owned隔離PG）

- `backend/tests/db/test_stats_basic_vertical_http.py` 1成功（約76秒）:
  - 既存の実HTTP新規作成→開始→通常3球→再送/reloadを再利用
  - 候補finalize（試験用receipt）→ `GET /games/{id}/stats?mode=official` 200・20名
  - `mode=current` はfinalize後0名（古い値を最新と偽らない）
  - `GET /stats/seasons/2026?category=all/practice` は10名、`official` は0名
    （試合区分 `game_other` のため。D02写像の実測）
  - 同じfinalizeの再実行は同一結果（冪等）
  - 試合別/シーズンCSV 200・BOM `EFBBBF`・行数20/10・ヘッダ27項目・未取得一覧
  - 保存factのplayer/metric合計とAPIのcount値を全件照合
- `backend/tests/db/test_stats_basic_db.py`: 候補SQLの構文・owner・ACL、finalizeの冪等/別receipt拒否
- `backend/tests/stats/test_basic_stats.py`・生成runtime・function boundary: 成功
- `frontend`: `BasicStatsTable.spec.ts` 2成功、`vue-tsc`/ESLint成功
- 候補SQLの実DB適用: `stats_basic_api` schema/2関数/ACL。正式catalogには未登録。

## 5. 未接続・未解消（MVP完成へ読み替えない）

1. **打者数（BF）**: `feature/mvp-stats-bf-calculation` の数学（source16/generated8）は採用済み候補だが、
   native DBの26固定CHECK/`computed_metric_keys<=26`/保存関数/`stats_function_codec`のv1/v2 profileを
   27へ広げるmigrationと3-profile decodeが未接続。本枝の26保存と衝突するため取り込んでいない。
   必要差分: 27番目 `batters_faced` のCHECK/配列/上限、current v3 profile、Save/read/creditsの27対応、
   D11/manifest/ART再束縛。BFは「no-change完了PAのみ1、未完0、継承責任はunavailable」の既採用範囲。
2. **登板（D03）**: 正式な投手出場/交代source（participation interval等）が未供給。lineup/payloadからの
   推測集計はしない。0球交代・再登板の境界fixtureとsource契約が必要。
3. **終了確定provider**: 製品の終了/再開トランザクションから `finalize_game_stats` を呼ぶ接続が未実施。
   `games.status='finished'` とreceiptの真正性は呼出側の責任。本枝のfinalizeは候補関数であり、
   終了確定の成功を製品で主張しない。再開時は既存confirmed版の `is_current=false` 化と新current_open版の
   Saveが必要（main担当の取消/終了再開経路）。
4. **毎球/プレイCSV（88列）**: `ud2-csv-export` step1の直列化/ZIP部品は再利用可能だが、DB抽出・
   HTTP・画面DLは未接続。全88列のうちG07入力項目/G08プレイ時刻/history snapshot等のproducerが未供給で、
   NULL/0で埋めない方針のため部分成功を出さない。必要差分は同計画のstep2〜5。
5. **正式認可/tenant資産**: 候補SQLの関数本体/schema/ACL/RLS policy、repository contractのtoken追加、
   route registry、capability catalog、seal/7.7は未受理。`candidates/authz-diff.md` の差分を主担当が
   正式導出する必要がある。本枝のAPIは候補関数をowned DBへ置いた検証だけ。
6. **画面の実ブラウザ/E2E**: Vueの型/単体は成功したが、実Vite/Chromium/実機での画面操作は未実施。
7. **性能/負荷**: シーズンは選手ごとに生成SQLを実行する（最大200名/page）。15万play・同時負荷の
   実測は未実施。DB側集計ではあるが、pageあたりのcanonical CTE反復の最適化が必要。
8. **CSVの正式ZIP/manifest**: 本枝は単一CSV。計画の打撃/投手別ZIP+manifestは未実装。

## 6. 次の最小接続（主担当向け）

1. `candidates/basic_stats_functions.sql` のread関数を正式catalogへ登録し、`candidates/authz-diff.md` の
   grants/policies/route/tokenを一括受理する。finalize関数は登録しない。
2. 終了確定providerの同一TXでcompletion列を真正receiptとともに更新する。receiptは既存の終了確定版から渡す。
3. BF/登板のsourceを27 CHECK/migrationとparticipation intervalへ接続する。本枝の
   `README`/APIは `appearances`/`batters_faced` がmetric JSONに現れれば自動で表示する。
4. 毎球CSVは `ud2-csv-export` step2以降を同じ `stream_csv`/ZIP部品で接続する。

## 7. 実装ステップ（候補）

| # | 実装範囲 | 合格条件 |
| --- | --- | --- |
| 1 | 基本成績のT6表示率・API・画面・成績CSV・終了確定候補を、既存T5 artifactを変更せず接続する | 打撃16/投手11のうち既存26事実から算出できる25項目、公式/暫定/暦年、試合別/シーズンCSV、owned PGの3球縦断1成功。D03/D04は0補正せずsource_unavailable。正式認可/終了provider/毎球CSVは未接続として残す |


## 現在基盤への接合追補（2026-11-06、root）

原外部HEAD41507aa0と反映候補19pathは保持し、新しい作業範囲は ../mvp-basic-stats-product/plan.md に従う。共通model/旧OPS数学は不変、生成8と表示1は公式builderで全byte再現。generated facts=a7ca0116…、current T5 set=cfc7bbb8…へ実物から再束縛。旧v1は全値保持、旧v2 set28af30fd…は履歴identityとして保存し、自動current互換とはしない。旧v2保存seriesの提供互換/3関数SQLbodyの追随と正式受理は未成立。
