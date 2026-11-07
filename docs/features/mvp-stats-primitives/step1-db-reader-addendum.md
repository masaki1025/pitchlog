# ステップ1(c)(d) 実DB・唯一reader接合の追補候補

基点 `b204e8765e0166515edb88ac5340a4e3dcaa1c76`。1(b)207pytest/7生成bytes再現の採用を継承する。ここでは次のexact編集候補を示し、root採否前に製品code・DB・正式登録を変更しない。到達点は隔離PGで実生成SQLを実行し、唯一の `ReadPlayExportPrimitives` から同じ受理T5 fact版を読み、COUNT/SUM/window・typed受け口・formatterを照合すること。fixture表の直接SELECTだけでは製品接合成功としない。

## 1. 次の有限編集範囲と所有

| 所有 | exact path候補 | 役割 |
| --- | --- | --- |
| 本担当 | `backend/src/pitchlog/stats/facts.py` | 真正providerの閉入力/receipt検証と共通生成T5呼出。式・権限判定の別実装なし |
| 本担当 | `backend/src/pitchlog/repositories/play_export_primitives.py` | 唯一readerのtyped scope/cursor/page DTOと閉operation token。自由Session/SQL文字列を受理しない |
| 本担当 | `backend/src/pitchlog/repositories/stats.py` | 同じsnapshot/metric sourceを利用するCOUNT/SUM受け口。season/率/public API完成へ進まない |
| 本担当 | `backend/tests/db/test_stats_storage.py` | root migrationの実適用、版/制約/同TX失敗rollback/権限の対向 |
| 本担当 | `backend/tests/db/test_stats_queries.py` | 生成SQLの実PG COUNT/SUM/window、独立整数期待、500跨ぎ/版・欠測/境界 |
| 本担当 | `backend/tests/db/test_play_export_primitives.py` | 実root登録operation→唯一reader→typed receiver/formatterの正負 |
| 本担当 | 既 `backend/tests/stats/test_primitive_facts.py`、`test_basic_stats.py` | 有限projectionと既55期待・拒否/再現の回帰 |
| 本担当 | 既 `backend/domain/model.schema.json`、`play-export.model.json`、`stats.model.json`、`stats-manifest.json`、`stats-property-catalog.json`、`stats-property-catalog.schema.json` | source relation/版の有限binding、必要な依存projection宣言/検査pin。人手式は共通modelのみ |
| 本担当 | 既 `backend/src/pitchlog/domaingen/{core.py,pregen_checks.py,backends/python.py,backends/typescript.py,backends/sql.py}` | 同一式の依存field限定入口、SQL共通S/COUNTとsnapshot bindingを実生成 |
| 本担当 | 既7生成target（plan4.1のfacts/receiver/formatter/2SQL/2TS） | 正規再生成だけ。新しい手書きtargetなし |
| 本担当 | 本追補と `step1-db-reader-evidence.md` | 実測・未成立・exact/hash固定 |
| root | `backend/src/pitchlog/db/game_state/stats.py`、`backend/src/pitchlog/db/all_models.py`、`backend/migrations/versions/stats_fact_versions.py`（実revision名はroot固定） | relation/DDL/FK/索引/RLS/論理失効、版の唯一正式供給 |
| root | 既 `repositories/transaction.py`、`operation_registry.py`、`tokens.py`、`function_operations.py`、生成`repository_contract.py`とtenant/authz正式契約・有限SQL資産 | 正式capability/関数署名/同snapshot transaction、閉tokenの正式登録 |
| root | 既 `sync/first_ball_projection.py`、`ordinary_pitch_projection.py`、必要な`ordinary_pitch_execution.py` | 本担当のT5 wrapperを実frame/ledger/checkpointと同TXで接合。関数/同期writer所有はrootに一本化 |
| root | 共有 `backend/domain/manifest.json`、display-binding、正式contracts/source registry・collector | actual PY/TS/SQL direct targetの正式登録/証跡。作者は編集しない |

exact集合を包括拡大しない。新正式SQLファイル名・capability署名・migration revisionはrootが固定して担当へ返す。上表のroot所有を本担当が迂回実装しない。新PO意味判断は要求しない。

## 2. 現存sourceと欠測の具体差分

現コードは `db/game_state/models.py` のgames/play_rows、`db/sync_protocol/models.py` のoperation_events/event_slots、`db/writer_binding/ordinary_models.py` の実checkpoint/admissionを持つ。ordinary projectionは実frame→受理ledger/D1/D2/世代/source fingerprint→実PlayRow/次checkpointを同TXで束縛する。PlayRow物理列にはPA identity/得点責任/RBI/盗塁観測がすべては保存されず、単独PlayRow読取をT5入力としない。既候補SQLのstats relation2個は未実在であり、完了receipt/public pointerも自由なUUID・nonnull判定だけでは真正性が成立しない。

| 26提供可能計算群 | 正式native供給条件 / 未成立 |
| --- | --- |
| pitch_count | 実accepted sourceの全23flags/実投手・event種別/実before、slot/play版/checkpointを閉照合して供給可能な最初の群。現コードの保存flagsから別の投球判定をしない。唯一の合格群には限定せず、下記照合で閉じる他群も同じ実PGへ接合する |
| PA/AB/H/2B/3B/HR/TB/BB/HBP/K/SH/SF/妨害出塁2種（14） | PA identity/開始完了・打者責任/安打種別/表示snapshotを実sourceで閉じる。未完PA観測と欠測PAを別にする。native欠測をfalse/noneで埋めない |
| pitching_outs/pitcher_k/pitcher_bb/pitcher_hbp/hits_allowed/home_runs_allowed（6） | 正式実効outs数量・各責任投手を閉じる。継承BBや振逃げは既期待どおり。現投手から責任を推測しない |
| runs/rbi/runs_allowed（3） | 有効走者・RBI既9分岐・数量・実責任投手の真正供給後。有効性をSQLで再判定しない |
| stolen_bases/fielding_errors（2） | 実企図/成否/走者、実失策野手の観測供給後。flagsだけから人物/成功数を作らない |

PA群のIDはpa/ab/h/doubles/triples/hr/total_bases/bb/hbp/k/sh/sf/catcher_interference_reached/runner_interference_reachedの14個。上表の1+14+6+3+2で合計26。実装receiptではID列挙を正として全26のavailable/source_unavailableを返し、未供給を0/false/空観測へ変換しない。

具体的な表現不足: 1(b)核は全field先行型検査のため、PA未供給時に `pa.ended_here=false` / `hit_kind=none` を捏造しなければ球数へ到達できない。修復候補は同じ式から依存field集合を静的導出し、requested primitiveだけを検査/評価する有限projection入口。未知requested IDは拒否し、真正providerで欠測と確定した群はsource_unavailable/nullを保全する。実nativeに存在するfalse/0/未完PAはコピー可能な真正値であり、欠測とは別に扱う。入力型にない履歴責任情報を存在しないと断定しない。全26入力が閉じた既呼出と55期待は不変。新しいPA算入式/NULL意味を追加せず、必要な型差分だけroot採否対象として明示する。

### 2.1 依存fieldから実保存pathへの照合（全26）

現在WTのV7正本は `OrdinaryPitchPlayPayload`（`sync/ordinary_pitch_payload.py:65`）、T1は `domainrt/ordinary_pitch_continuation.py:201`。以下のPは実 `OperationEvent.payload`、Tは `P.calculation.response.value.t1`、Qは `P.calculation.request.t1.before`。実payloadの保存/実frameとの一致は `ordinary_pitch_projection.py` / `read_ordinary_pitch_payload` が担当する。JSON pathの存在だけで真正性を付与しない。

| metric ID（全26） | 共通モデルが読む本質的依存 → 現native実path / 状態 |
| --- | --- |
| pitch_count | `stat_flags.投球数`, actual_pitcher → `T.statFlags.投球数`, `P.participants.pitcherId`。現ordinaryではtrue、実source付きで使用可 |
| pa, ab, h, hr, bb, hbp, k, sh, sf, catcher_interference_reached, runner_interference_reached（11） | 対応全23flag、`pa.ended_here`, credited_batter → `T.statFlags`, `T.plateAppearanceEnded`, `P.participants.batterId`。現ordinaryは明示false/未完という真正情報を持つ。PA未完をunknownへ落とさず、完了PA責任の追加sourceは後述 |
| doubles, triples, total_bases（3） | H/TB flag、PA完了、`pa.hit_kind`, credited_batter → `T.statFlags`, `T.plateAppearanceEnded`, `P.calculation.request.t1.resultId`/結果語彙snapshot照合。現在の通常ball/strikeに安打種別をnoneと仮生成しない。guardの実falseが閉じる場合は同じmodelの短絡依存だけで処理し、hit_kindが真に必要な結果は正式安打source待ち |
| pitching_outs | innings_outs flag、実out_effect数量、outs責任 → `T.statFlags.投球回算入アウト`, `T.outEffect.count`（ordinaryは明示0）、`P.participants.pitcherId`。責任が必要な正のoutは履歴/継承sourceも照合 |
| pitcher_k, pitcher_bb, pitcher_hbp, hits_allowed, home_runs_allowed（5） | 対応投手flagと専用責任ID → `T.statFlags.奪三振/与四球/与死球/被安打/被本塁打`, `P.participants.pitcherId`、実PA履歴責任。現ordinaryの明示falseは利用可能、正値は現投手への暗黙帰属を禁止 |
| runs, rbi, runs_allowed（3） | runner_scores valid/数量/RBI branch/batter/responsible_pitcher → before/after runner/scoreboard、`T.statFlags.得点/打点/失点`、履歴/実責任source。flagsは存在するが走者別数量/責任はflagsだけで復元しない。明示empty観測を正式providerが解決した場合だけ空を使用 |
| stolen_bases | steal_attempts runner/succeeded → runner/history/sourceの実企図観測。現V7 observationsは投球観測であり、盗塁観測の不存在を成功falseと置かない |
| fielding_errors | `stat_flags.失策`, error_fielder → `T.statFlags.失策`は存在（現ordinary false）、fielderは実守備者/該当エラーsource。true時の野手をpitcher/catcherから推測しない |

全23flags、実before/after、実未完PA、実outs0、実participantsを使えるため、球数以外25全てが未供給という扱いにはしない。どのfalse guardがどの依存を不要にするかは共通modelから静的導出し、missing fieldを補う条件式をadapterへ書かない。availability条件も同modelの式を保ち、不足した条件を勝手にcompleteへ変更しない。既契約で閉じない部分だけsource_unavailableとし、必要なら最小契約差分をrootへ提示する。

`source.responsibility.paStartSource`等の正式native責任sourceが主担当側#191/#192で存在する可能性は本WTの不在と区別する。本WTのordinary V7/schemaにはそのmemberがないため、新assetの正確なpath/hash/保存履歴をrootから受領して同じ照合表へ加える。現V7を改変したり、その情報をないものとして25群を除外したりしない。PA identity/ordinal/start/end/participant change/runner責任の各fieldへ実pathを束縛し、receiptのtenant/game/event/D4/D1D2/ledger/checkpoint/rule/artifact/model/signature authorityを省略しない。

## 3. rootへ申請するrelation・供給者binding

候補の3relationはrootが正式化する。schema名も認可設計へ合わせてroot固定とする（既public候補を無条件採用しない）。

- `stats_fact_versions`: tenant/game/版ID、共通model・T1artifact・rule版、真正source-set S digest/count、checkpoint/ledger位置、completion/public pointer receipt、失効/置換状態。版は追記し、現在版選択と取消を論理失効で更新する。
- `stats_primitive_sources`: version/tenant/game/event、generation/D1/D2、slot/play版、真正receipt/checkpoint/rule/artifact参照、計算済みmetric keysと欠測理由。寄与0のsourceも保持し、Sの不足・重複をCOUNT/一意制約で検出する。
- `stats_primitive_facts`: source参照/metric/player/credit ordinal、available amountまたはsource_unavailable NULL。任意精度integer相当numeric（float禁止）、amountは共通T5生成だけ。sourceの同TX保存が完了する前に版をcomputed扱いしない。

rootの正式providerが実frameと実保存値を解決し、`stats/facts.py` の唯一核でT5を実行してsources/factsへ同TX保存する。T6 SQLは保存済みamountのみを集約する。source表/版/credits全体のreceiptを検証し、呼出側の `computed_metric_keys` 宣言だけでは空0を認めない。欠測群はdependent metricだけNULL。source relationの追加が不要な正式既assetで同等のS/zero-source証明を供給できる場合はrootの同等bindingへ置換し、その差分を固定する。

唯一readerはroot登録の有限関数/operationだけを呼ぶ。候補責務は `ReadPlayExportPrimitives(scope, snapshot_receipt, cursor, page_size<=500)`。tenantは既TenantContextから束縛し、scopeのgame/player/model/fact版/S/metric射影とcursor全tupleをreceiptに結合する。初回receiptは実DBが発行し、UUID/hash文字列を権限にしない。reader自体でquery文字列/Session/権限boolを受けない。

## 4. 同snapshotと実PG受入

rootの狭い読取transactionが最初のquery前にREPEATABLE READ READ ONLY snapshotを固定し、その同handle内でCOUNTと全page/windowを実行する案を採る。公開readerへSessionを露出しない。複数HTTP/TXへ跨ぐ将来のCSVは本段で成功claimせず、rootのimmutable fact版+可視性/取消epoch receipt再検証の正式契約へ接合する。現段は実同TXのsnapshotで比較する。古いcursor/別tenant/game/model/S/版は拒否し、異snapshotのpageを継ぎ足さない。

実SQLのSはaccepted/適用済み・D4確定/ledger/checkpoint・現在slot版・playrow版・世代・生存状態から唯一形成し、COUNT/SUM/windowが同じCTE/receiptを参照する。取消/訂正/再開に対して旧版を最新扱いしない。全件eventのPython/JS読込集計を作らない。windowの後で(D2,event,metric,必要ならcredit ordinal)の全tie keysetを掛ける。複数creditの事前GROUP BYとページ対象を明示し、500/501で重複/欠落/累積resetを検出する。

rootとPG時間を調整し、既 `backend/tests/db/sync_writer_binding_support.py::owned_binding_database` の所有隔離PG/実migration headを使う。起動前に共有DSNをunsetし、fixture所有証明を満たす一時endpointだけをテスト内設定する。共有DB・共有DSNへ接続せず、191/192のPG実行と重ねない。

合格面は次の有限集合: (1)実native最低1source→実生成T5→同TX保存→登録operation→reader→generated receiver/formatter、(2)独立55期待のうちDB対象を実格納facts/creditsへ導出入力として投入して実SQL結果比較、(3)同一版500/501・複数credit・巨大整数・0/NULL/空・非投球・未完PA、(4)二世代/同D1異世代/訂正取消/tombstone/遅着/重複/旧model/checkpoint/receipt・別tenant/hidden/trashed、(5)途中故障rollback・読取並行更新・同snapshot COUNTとpage一致、(6)索引/EXPLAINと限定roleの迂回拒否。合成DB入力は数学/SQL検証として分類し、実native成功と分ける。native未供給metricは明示的未成立を残す。

root採否後、コード/試験準備はDB枠待ちと並行し、実正式資産の合流後に登録operation経由の実PG比較まで進める。新table/認可資産を作者の一時fixtureで代替して製品完成としない。D02〜05は依存だけpending、暦年既決は戻さない。ステップ1全体の完了は本有限実測・正式登録・独立再確認まで保留する。

## 主担当採用と編集所有の最小追補（2026-11-05）

主担当rootが対象SHA61fcba18…を既plan/D-1/共通S/真正native責任と照合しPO委任で採用する。本担当の表中code/生成/test exact集合の実装を開始可。共有資産採否を待つだけの停止を避けるため、本担当へ専用WT内の新db/game_state/stats.py・既db/all_models.py・新migration 0040_stats_fact_versions.pyの3relation candidate作成も移管する。rootは正式認可/共有registry/同期hook/共有manifestの最終採否と正式追記を直列管理する。作者は新3tableの列/FK/索引/RLS/lifecycle・読取書込operationのexact候補を先に固定してrootへ渡し、許可globalassetの追加writerを自己判断で増やさない。

receiptは実frame/ledger/保存原本に依存し、任意UUID/文字列/呼出者boolを資格としない。新秘密/本人署名の発行を要せず、現に提供される真正型/同TX資格を使う。終了確定が未提供なら公式版をconfirmed_endedへ上げず、現在版の実SQL確認と分離する。利用可能な全26群の依存を同じモデルから処理し、nativeで欠測の群だけ保留する。rootの191/192新source責任は版SHA付きで後続受渡しし、既ordinary sourceを偽造して代用しない。PG枠はrootがowned192終了後に通知する。

本追補の実装/新DB/正式認可候補は別非作者へ渡す。rootが計画を採用したことを製品供給/DB耐久/全27完成としない。

モデル走査接合のexact1追加（2026-11-05、PO委任による主担当root判断）: 既test_alembic_environmentのmodels走査とBase.metadataを同一に保つため、backend/src/pitchlog/db/game_state/models.py末尾の新stats3 Table alias再exportだけを本担当へ追加許可する。既table/class/意味/FK/権限の変更・走査test緩和は不可。既writer_binding方式へ揃え、循環import/全models再現性を検証する。

進行中S更新の性能binding（2026-11-05、PO委任による主担当判断）: 毎球ごとの全既source/fact複製は採用しない。current_openの同model/rule/T5artifact-set生成系列に限り、revision・S digest/count・計算済keys/欠測状態・更新位置を実frame同TXの期待前値比較で更新し、source/creditは追記保持する。既amount/原source・tenant/game/model/rule/artifact・識別子の書換えは許さない。S digestは版/同snapshot receiptに属し、各旧factへ最新global digestを複写する条件を置かない。取消/訂正は生存slot/sourceの正規集合からDB側選択し、旧source/factを物理削除しない。confirmed_endedの確定内容は凍結、再開/再終了には新しい公開版を用い、旧確定内容のin-place上書きを行わない。旧receipt/遅着/異snapshotは拒否し、versionの可変列はこの有限集合だけへ閉じる。公式終了provider未提供中はcurrent_openの実供給のみであり、nonnull UUIDで公式確定にしない。

同snapshot helper名はrepositories.transaction.stats_primitive_read_scope(context)を採用する。root所有で、最初のSQL前RR/READ ONLY、同実_TenantTransaction handle、Open/Page/Totalsのみの閉phase、tx/tenant/game/model/S/revisionの一致を検証する。新コード/候補SQL/DB原子性を非作者へ渡し、採用済み版/保存保証を一般緩和しない。
