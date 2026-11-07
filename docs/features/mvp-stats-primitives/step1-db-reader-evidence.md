# ステップ1(c)(d) 接合準備候補（実DB未実）

基点 `b204e8765e0166515edb88ac5340a4e3dcaa1c76`。採用追補とrootの技術具体化に従い、source49列からcurrent系列revision/更新位置5列を加えた3表54列のモデル・静的migration0040を準備した。共有manifest/正式認可/operation registry/transaction/同期hook/正式contracts/refsは編集していない。これはsource供給・実DB・ステップ1完了の受理ではない。

## 実装と唯一性

共通modelの `sql.canonicalSelection={version:1,kind:accepted-play-slot-v1}` と固定relation bindingから、実event_slots/recording_generations/operation_events/idempotency_ledger/PlayRowを起点とする独立Sを生成する。保存stats_sourcesを起点にしない。既W3/W3-aのtarget generation/D1/expected versionと対象D2へ従い、P3 current sourceを未解決のまま消さない。control/tombstone/deleteの除外とsource_unavailableを行として保持し、未知native variantはincludedのままT5取り込み不足として残す。

`play_primitives.sql` の固定sectionは `window/count/current_totals/canonical_members/canonical_health` の5件。後者2件は同じS宣言の有限pageとCOUNT/未解決数/digest。保存側はcanonical全識別tuple・版・source fingerprint・T1 artifactをJOINし、同一集合・coverageを確認する。source_countだけの比較ではない。版のSdigestはsource/wire指紋と別の型で、各factに最新global Sdigestを要求するJOINはない。root4関数はこの生成sectionを利用し、別のS式を作らない。

T5は同じ生成核のoptional requested ID射影で、実際に読むrefだけを型検査する。欠測fieldだけsource_unavailable、型/enum/過大collection不正は拒否、全23flagsは閉集合を維持する。full入力入口の55期待・既拒否を緩めない。mapperはnativeの値コピーと有限enum変換だけで、A-2/得点/盗塁等を再計算しない。実未完PAは欠測と区別し、PA行に必要なordinal/表示を仮生成しない。

Root提供のimmutable191/192資産5件はGit全SHAと内容SHAを照合してcacheへ保全した。v2 request.source.responsibility.paStartSource、v3 beforeParticipants/responsibility/nextResponsibility、全23flags/実outs/実beforeを参照する。native no-changeのみ責任IDをaliasし、one-changeを推測しない。走者別得点/RBI/失点/盗塁4群の未供給はNULL。22群を球数だけへ縮めず、PA/AB/BB/HBP/K/投手K/outsも同じ方式にする。数学wrapperのJSON/UUID/ok=trueは認可・保存receiptではない。

## 保存とrootの接合

3表はsync_fence、複合tenant FK・rule版一致FK・既知metric/整数状態・source(generation,D1,slot_version)の一意性・必要索引・FORCE RLS・既app/actor全REVOKEで配置する。migrationで権限/policyを開かない。metadata走査はgame_state/models.py末尾の3 Table aliasだけを追加し、既走査テストを維持した。all_models.pyの公開契約は変更していない。

versionはmodel/rule/**t5_artifact_set_sha256**の生成系列。sourceは別にT1 artifact_sha256/rule_sha256、実frame/checkpoint/指紋、T5 evaluation hash/stateを保持する。current_openのrevision/Sdigest/count/keys/更新位置だけを同frame TXで期待前値CASし、既source/credit/amountは追記する。毎playで過去Sを複製しない。confirmed_ended内容は凍結、再開は新公開版。真正終了provider未供給なのでcurrent_openをconfirmed_endedへ偽装しない。

Root owned `stats_primitive_read_scope(context)` が最初のSQL前に真のRR ROを設定し、実handle markerを発行する。reader init/_liveはroot `_require_stats_primitive_read_scope(handle)` を毎回要求する。未供給時や通常writable scopeでは拒否し、自由Session/SQL/権限boolを受けない。8項目のOpen receiptとcursorは同handle/receiptへ束縛し、Page/Totalsもgame/player/model/版/S/revisionを渡す。COUNTと逐次page件数を照合し、全件list化やPython/JSの全event集計を実装しない。

Saveのexpected_revision/expected_source_set_sha256はroot同frame phaseが実系列から得る値。root SQLもrow lockして独立比較し、初回0/nullはNOT EXISTS系列かつ真正admission/ledger/保存原本が閉じる場合だけ許す。canonicalは公共watermarkを読むため、T5評価の束縛後、保存/S健康/CASはprefix・watermark更新後かつ同business TX確定前でflushする。rootの実frame評価binding/4正式operation/限定関数・認可・同snapshot scopeの接合前に成功を宣言しない。

## 検証と未成立

rootのread-scope/helper供給は40eebf0eで保存され、外部所有PG17.11で2passed10.92s（scopeだけ）を参照する。統計4関数/S/save/HTTPの成功ではない。

共有DSN3種をunsetしたpure pytest **229passed**（旧81・alembic走査6を含む）。55独立期待→生成Python/実Node、26数量変異、有限射影同値/欠測・CAS型・cursor・canonical構造の比較を実施。7targetのbyte再現を確認する。Ruff/ty、生成TSのPrettier/ESLint/vue-tsc、Vitest6件を確認。pglast8.7ではSQL計6statementの構文parseだけを実施し、DB上の型/関数/権限/実行/EXPLAINとは区別する。

DB用8件をcollectしたが未実行。実HTTP cookie→正式TenantContext→同TX保存→登録readerのordinary3球、191v2 walk/HBPのPA/BB/HBP、同S COUNT/SUM/windowを実PGで検証する準備で、未登録をskip/0成功にしない。191/192実providerの本WT合流、root4関数/phase、DB型・RLS/実権限、500跨ぎ/世代/非投球/取消/競合/故障、EXPLAIN/大規模は未成立。D02〜05はpendingのまま。DB枠はrootと調整し、共有DSN/DBを使用しない。

最新exact paths/SHA、3表・4署名、native原典・変遷・root最小接合interfaceは `~/.cache/pitchlog/stats-primitives-step1cd-binding-20261105/` へ固定する。準備候補を実接続完成へ読み替えず、root正式接合・owned PGで実SQL/実readerを通す作業を継続する。

## 非作者P1-1反映1（seasonのgame別S健康）

初回30path/不採用REPORTと反例はcacheへ保全。canonical_healthをtenant/game GROUP BYし、同gameのversion/source_membersとbinding_healthで対応比較する。全体の不足は各gameの不一致と未供給versionから集約する。単一gameの公開health4列/count12列・Sdigest内容・数学55期待・モデル宣言・D02〜05は不変。新しい意味裁定ではない。

正常1/2試合、外tenant追加、片側source/version欠損、旧model、片側S改変、同件数membership交換の8対向を追加した。手指定2球入力と独立反例のS_iを用い、生成済みsource JOIN/health/CASE/SUMを有限SQLite面で実行した。型/array/BOOL_ANDの汎用適合だけをテスト側に置き、期待2球をartifactから転写していない。生成canonical_healthのper-game GROUP BYも確認する。旧保持SQLは同じ面で投球数source_unavailable/NULLとなる反例を再現した。これはPostgreSQL/認可/実providerの実証ではない。

pure pytest237件（新8件込み）、Ruff/ty成功。生成7targetを正規再生成し、変更はSQL2件だけ。PG構文parse5+1件は成功、PGは起動していない。正式4fn・同frame保存・実PG・500跨ぎ等の未成立は維持する。反映1packet/全30SHAと6変更pathを固定後、writerを停止する。
