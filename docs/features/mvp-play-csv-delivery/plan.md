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
