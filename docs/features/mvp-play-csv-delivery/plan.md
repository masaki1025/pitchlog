---
feature: mvp-play-csv-delivery
status: active
branch: feature/mvp-play-csv-real-source
承認: PO委任によるCodex/root判断（2026-11-07、既MVP内の欠陥修復・接続）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 毎球CSV候補の6指摘修復と実記録供給

起点d00f925aの既ud2-csv-export計画を再利用する。非作者の固定レビュー play-csv-independent-intake-20261106/REPORT.md（SHA e2047785b0fe7b0fa80b660364c1aa7dfad493e3623e11882bf9598bf1502aec）のP1=6を修復する。作者WTは変更せずrootが本WTを単独所有する。新しい野球意味は採用しない。既承認の記録時producer/同一RR/有限読取/C2/送出前認可/完成ZIP検査の要件を維持する。

| ステップ | 実装 | 検証 |
|---|---|---|
| 1 | frontend apiDownloadの既tenantBoundオプション伝達、gameExportsのC2必須化、必須長さ/SHAと画面破棄/試合変更後の保存拒否 | 実clientのchallenge/tenant/世代拒否、真正SHA照合、欠落・不正・破損・破棄のVitest、型/lint |
| 2 | backend C2 route登録、全イベントkeyset、保存snapshotのsource版照合、manifest全source版、送出直前の認可再確認、有限ディスク抽出へ修復 | pytest、500/501/2001境界、旧snapshot/版変更、撤回/越境/故障、非作者確認 |
| 3 | connected-rehearsal固定候補との通常接合、同TX88列producer/正式資産/実画面導線 | 事前fixture投入なし実新規記録からZIP、旧source無補完、正式資産/独立レビュー/CI。正式受理前は候補扱い |

rootへの既PO委任と2026-11-06の速度優先・品質維持指示に基づく範囲具体化。承認者はCodex/rootでありPO本人の逐行確認や署名ではない。ステップ1の実装を開始する。6指摘とproducerが未解消の間、CSV完成や正式提供とはしない。送出検査を緩めず、既一般apiDownloadの非CSV呼出しとの互換性を維持する。

## ステップ1実装結果（2026-11-07）

既apiDownloadへtenantBoundを後方互換で伝達し、毎球CSVに限ってtrueを必須とした。Content-Lengthの非安全整数はnullへ閉じ、componentは正の安全整数長さ・小文字64桁SHAの両方と実bytes一致を要求する。破棄/試合変更/認証世代変更後は保存を止める。実crypto SHAで長さだけ正しい破損も拒否し、実clientのchallenge応答欠落/不一致はBlob未消費を確認。対象3suite76passed、Vue型・対象ESLint成功。最初の2失敗はnative async digest終了前の試験観測をvi.waitForで是正したもので、検査/期待を緩和していない。backend C2登録はステップ2で行うため、現時点で製品CSV成功とはしない。非作者確認は未実施。

ステップ1固定d06e8356の非作者確認 `play-csv-fixed-independent-20261107/REPORT.md` SHA256 `0b434a4363e91626e2155c6db4e92f355c86443065ca4005794ae494ca3ec240` はP0/P1=0（read-only、独立試験再実行なし）。P2旧要求finallyのbusy上書きを同controller一致時だけへ限定し、A取得→Bへ切替/取得→A完了後もBがbusyを保つ対向を追加。対象3suite77passed。後発2path差分の確認は別記し、前レビューが後発HEAD全体を確認したとは扱わない。

## ステップ2の途中固定（未完）

全イベントをaccepted条件の500行keyset（d2 NULLはid独立系列）にし、2000件打切りを撤去。SQLite実SQLの500/501/2001件＋NULL3件/別tenant/退避混在で欠落・重複0を確認（PG ACL証拠ではない）。snapshotはtenant/game/source_event_id/play_version/generation/d2の全一致を要求し、候補DDLへ原本ID/版を追加した。旧fixtureの値を実原本へ追随しただけでproducer成功とはしない。manifestは全イベント/補助資源/保存projectionを束縛する。C2 route_class/閉operation追加と、完成ZIP後の提示token再照合・新RR可視性再確認/拒否cleanupを実装。関連94pytest、Ruff/Ty成功。送出拒否4caseは依存置換した単体試験であり真正認可の実DB証拠ではない。

**未完**: 全量RAM materializationは残り、repository/formatterを有限ページ→ディスクZIPへ接ぐ修復を継続する。製品app/正式資産登録と既registry完全一致検査の追随、実PG/C2/認可撤回実測、88列producerは後続。6指摘が全解消した、正式readが提供されたとはしない。

ステップ1後発22ade8c7の非作者反映確認 `play-csv-fixed-independent-20261107/reflection1/REPORT.md` SHA256 `f07ee585a6bf20de709c28fc6a36c03ccbf230df7e2b4b263c4c0421ad609ee1` はP0/P1/P2=0（実source読取、独立試験再実行なし）。

ステップ2継続: CSV各formatterをiteratorに変更し、完成行を全10ファイル分list化して二重保持する経路を撤去。manifest hashもJSONEncoder.iterencodeのchunk更新とし、巨大な単一JSON文字列を作らない。2001イベントのsourceを最初の要求行まで消費しない/500境界/全件exact対向を追加、関連95pytest・Ruff/Ty成功。**repository自体の全量tuple/list保持は残るため、全量RAM指摘の全解消とはしない**。次は同RR内で有限ページを直接archiveへ渡す読取の接合（archive完成までRRを保持）と88列producerを優先する。

## ステップ2・有限メモリ読取の接合（2026-11-07）

追加path `repositories/play_export_spool.py` は既ステップ2の有限ディスク抽出の具体化で、root単独編集。SQLAlchemy server-side cursor/yield_per500から同一RR原本を要求私有SQLiteへ逐次退避し、PlayRow/event/snapshot参照索引と参照ID集合もディスクへ置く。pickle/evalを使わず全ノード型タグでUUID/日付/日時/有限numeric/JSONを保持する。256MiB総量・4MiB行・集合100万行・SQLite有限cache/ディスク上限を各書込前に検査し、全出口で私有ファイルを閉じる。ZIP完成までstoreを保持し、保存原本を全量dict/list/tupleへ戻さず既formatterへ供給する。出力時のT1再計算/名簿補完はしない。

関連102pytest、Ruff/Ty成功。500/501/2001 SQL検査を退避あり/なし両方で実行し、disk bundleと同値memory bundleのsource拒否・manifest一致を確認。2001件・20MB超sourceの単体ではPython heap peakを4MB未満に抑える対向、容量拒否とcleanupを追加。これはtracemallocのPython heap検証でありnative SQLite/PG/RSS全量性能・実PG・製品88列供給の証拠ではない。後続非作者確認と実接合が必要。

## ステップ3接合と反映1（2026-11-07）

元CSV修復ad8b0cf3は非作者 `play-csv-ad8-independent-20261107/REPORT.md` でP0=0/P1=3（全監査index、巨大単一行の事前コピー、ASGI切断cleanup）として不採用中間を保持。rootは別WT feature/mvp-play-csv-real-sourceへconnected60fと通常mergeして4fb27253へ接合。transactionのstats/read/CSV readをそれぞれ保持し同時指定を拒否、C2両operation/既local route/成績routeを維持した。元レビュー固定WTは不変更。

反映: _encode前に深さ/ノード/最悪escaped bytesの有限予算を走査し、8MB行とcontrol escape膨張をコピー前に拒否。ASGI response自身のtry/finallyで出力fileを所有し、start/body送出例外がlive event loop内でも確実にclose。全監査用(tenant,game,d2,id) accepted部分indexを候補SQLへ追加したが、0047/実PG EXPLAIN前はindex指摘を解消扱いにしない。巨大行/切断の対象12pytest、Ruff/Ty成功、全関連は継続検査。Python追加heapとDB client/native RSSは分離する。

closed registryの旧6赤は60f同名6caseで同じ失敗を再現（cache csv-merge-closed-registry-base60f.log）。実現在43件の全operation literal順序と実token集合を追随し、旧42件/末尾offsetを修復、部分集合や期待値の無視はしない。対象2suite276passed。これは製品計算/認可変更ではない。正式資産・最終非作者・必須CIの追随は未了。

次の主作業は同TX88列producer、既D-1単一計算/生成器を用いる表示・座標・共通DBprimitive、記録時人名/背番号/roster metadata保存、正式0047+route/ACL、事前投入なし新規記録→ZIP/画面DL。sourceの欠測を0/NULL/現在名簿で補わない。P3有効source/取消/終了再開版へ連動し、未対応操作は成功にしない。

反映1固定前の結合検査: CSV/RowStore/ASGI拒否＋stats/function registryの全9suite **382passed18.69秒**、Ruff/Ty・Vue型・FE対象77成功。ASGI送出故障はClientDisconnectの型と発生phaseを明示し、loopを生かしたままcloseを確認する。候補監査indexの実PG EXPLAINは未実施のまま。sourceは次のproducer担当移管時に固定し、正式受理を既レビューへ拡張しない。

## ステップ3・申告敬遠との結合候補（2026-11-07）

PO委任によるCodex/root判断で、既ステップ3の現行v3実画面縦断を非投球の申告敬遠まで具体化する。別固定 source `a0c192a0` を通常 merge した隔離 WT `feature/mvp-nonpitch-csv-connection` だけで、二単打→申告敬遠→同D5再送→次球→再読取→画面ZIPを検査する。CSVの同TX88列、非投球の未観測NULL、球数0credit、4行/11CSVとmanifestの実bytesを同じゲームで照合する。共有T5・非投球核、正本、正式資産はここで変更しない。候補SQLの局所適用と正式0047/7.7受理は分け、旧単独画面成功を結合成功へ流用しない。

## ステップ3・取消と有効版の読取追補（2026-11-07）

PO委任によるCodex/root判断に基づき、CSV-CURRENT-01 を既MVP内の読取欠陥として修復する。固定非作者報告 `play-csv-nonpitch-independent-20261107/REPORT.md` の全取消・一部残存の反例を受け、同一 RR snapshot にある有効 PlayRow と、その exact source/世代/版に結合した保存 snapshot だけを CSV 本体へ供給する。監査用の旧 event と旧 snapshot は全 byte 保持し、別集合として manifest と照合する。単純な件数検査の削除、旧 snapshot の物理削除、現在名簿や欠測値による補完をしない。

所有は CSV 専用 repository/export、候補 SQL/serializer、専用 spec/E2E と本計画に限定する。共有 sync/P3/domain/contracts と正式 asset は編集しない。実 Undo の全取消・一部残存→再入力→reload/ZIP を owned PG/画面で検査する。P3 の有効版と終了・再開版は固定済み selector の証拠が供給された範囲だけ接合し、未供給を 409 のまま具体的依存として記録する。正式0047/7.7/registry は root の直列受理に残す。

### 取消後CSVの実測と継続境界

候補 reader は同一 RR で有効 PlayRow と全物理 PlayRow を別に取得し、全 snapshot を tenant/game、実 event、世代、D2、物理版へ照合する。監査物理行にも対応 snapshot を必須にし、旧原本は `projections.csv` と manifest の source digest に残す。候補 SQL に全物理 PlayRow と snapshot の試合限定索引を追補した。索引の正式0047採用と実EXPLAINは別の受理証拠とする。

owned r9（source前後SHA一致、所有container cleanup）で実新規開始→通常2球→取消1→同D5原文再送の重複→画面ZIP→全取消→画面ZIP→取消画面から再入力→画面ZIP→reload→画面ZIPを同一ゲームで完走し、backend実DB E2E 1件が129.13秒で成功。順に有効 `plays.csv` は1/0/1/1行、88列、監査 `projections.csv` は2/2/3/3行、`events.csv` は3/4/5/5行、各11 CSV・manifest・BOM・行数・SHA・ZIP整合性を照合した。DBでは元2物理行が hidden、再入力1物理行が現行、旧3 snapshot と event 原本を保持。後発のP3閉拒否対向を含む純85pytest、Ruff/Ty、Vue型/ESLintも成功。初球前のUndo GETは409であり、2球保存後に取消画面の既「再取得」操作を実行してから取消した。自動更新の共有UI修復は別cache候補としてrootへ渡し、本CSV WTでは共有画面を変更しない。

これは取消・再入力版の候補実証であり、P3は旧物理行を hidden/retired にしないため現 `_page_plays` の有効版選択では未成立。受理 `play_change` がある試合は当面409で閉じ、二重計上を許さない。現在のT5版/source pointerとP3 capsule/slotの原本対応を閉じた公開読取能力が不足している。終了→再開→再終了の最新版と、正式0047/7.7/registry、独立最終レビューも未成立のまま継続する。


### 取消後CSVと真正T5版/sourceの同時観測（2026-11-07）

専用WT `feature/mvp-play-csv-effective-versions` のr12で、既r9経路を実画面/owned PGで再実行し **1passed141.50秒**。4段階のZIP取得後・次操作前に試験専用barrierを置き、管理者の別read-only接続で真正current T5版と有限source identityを観測した。source_countは1/0/1/1、revision3/4/5/5、completionはcurrent_open、再入力とreloadのversion ID/source_set/source一覧は完全一致。保存済みZIPのplay_linksとT5 sourceのevent/play_row/generation/D2/play版を全件完全一致で照合し、slot versionは1であった。これは実producer/取消の候補実証で、P3 slot2や終了確定版の成立証拠ではない。

r11は旧/tmpのTLS資材パス消失で画面開始前に失敗した。新規秘密を発行せず、既cacheの所有loopback TLS資材へcache runnerだけを差替え、旧runner/logを保存してr12を実行した。r12はsource前後SHA一致/owned cleanup。独立レビュー・正式0047/7.7/統合は別条件として残す。r12保存観測/ZIPへの事後完全比較をE2E内の恒久assertにも追補する。

次のP3/終了再開接合には、唯一生成S/canonical_source_membersを再利用する閉じたsource identity読取を同RRへ供給する。既ReadPrimitivePageTokenはmetric/d2/eventだけで物理play/slotを返さないため代用しない。実装選択は既MVP内のDTO/保存読取具体化としてPO委任rootが許可済みだが、正式token/catalog/関数body/core境界はroot直列受理へ渡す。保存時88列snapshot不足を現在名簿/0/NULLで補完しない。

### ステップ3・唯一Sの閉identity read候補（2026-11-07、PO委任rootの実装指示を反映）

r13で435cb518の恒久assert入り画面縦断を再実行し、1passed136.17秒/source前後SHA一致/owned cleanupを確認してから新sourceへ進む。新設の `authz/play_export_source_read_product.py` は既 `_verified_inputs`/`play_export_score._canonical_parts` により検証済み唯一SのCTE/member JOINを再利用する。新しいeventの選択意味やT5再集計をCSV側へ追加せず、native現在版・health・digest/件数・全member数を照合した同RR/ROの500keyset identity read1関数を候補として描画する。0件も真正header sentinelで表し、未供給を0補完しない。

`repositories/play_export_source_codec.py` は閉token/15列値契約・版/snapshot・cursor・余剰/欠落・部分NULLを検査する。`play_export_source_operations.py` は固定登録metadataと真正CSV scope専用の有限readerを候補化する。自由なSession/executorやUUIDだけを認可能力へ変えず、未登録の現registryでは実行を閉じる。共有function_operations/operation_registry/transactionへの必要差分はcache patchとしてrootへ渡し、正式関数body/catalog/ACL/seal/7.7はrootが直列で受理する。これらの共有sourceは本WTで編集しない。

P3のeffective playに対する記録時88列producerは別供給として必要であり、identityのみを根拠に現在の名前/roster/0/NULLを埋めない。実PG・登録済token実経路・P3・終了/再開の接合が未成立の間、既P3 409を成功へ変更しない。計算・認可・保存保証は維持する。
