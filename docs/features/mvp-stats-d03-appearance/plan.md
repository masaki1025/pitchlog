---
feature: mvp-stats-d03-appearance
status: draft
branch: feature/mvp-stats-d03-appearance
承認: 未（root限定レビュー/PO委任判断を依頼）
重さ分類: コア領域（成績source未正式除外）
計画レビュー周回: 0
確定ゲート周回: 0
---

# D03・真正投手出場から試合別とシーズンの登板を供給する

起点6a424a301a7acbc15fe55f9e25506f874e1ca1e1。PO採用済みD03は、実際に投手として出場した試合を1登板、再登板は同試合1、0球交代も1とする。球数/打者数から出場を推測しない。D02の公式=公式戦/準公式戦、練習=オープン戦/紅白戦/その他、allとJST暦年は既宣言を再利用する。本人署名・P6 blindや正式受理を代記しない。

## 現物と開始条件

既basic_sql._normal_appearance_sqlは開始原本だけを確認し、試合別・交代/取消/再開なしに限定している。シーズンは常時source_unavailable。basic_statsは登板のoptional値と未供給理由を既実装しており、新しい表示式は不要。

public.participation_intervalsはmutableでstats fact versionへの束縛が無く、その行だけのCOUNTは採用しない。新しいevent状態畳込も行わない。開始時game_lineupsとcommitted start原本、現在checkpointのsubstitutionFramesが持つbefore/afterContext、0044 substitution_write_receipts/nonplay admission/event/ledger/slotの同TX原本を再利用する。真正性の既境界はauthz/nonplay_prefix_read_sql.pyとsync/substitution_projection.pyに存在する。出場候補は検証済み文脈のfielding position1のplayer identity集合であり、投球creditや現rosterで補わない。

D03 readは既T6のcurrent版/唯一S/healthと同RR、既basic_sqlの真正終了LC receipt/head照合と同じgame集合へ束縛する。再開中は公式対象外、再終了は同gameの現版だけを参照する。出場identity集合のCOUNT DISTINCT(game_id,player_id)を単一SQL宣言で一度だけ計算し、basic_sqlはscope/bind/形式へ接合する。別のPython/FE計算は作らない。

着手はrootの本計画採用後。実checkpoint/frameを既guardと同等に照合できるread資格/版identityが不足する場合は、缺測を0にせずunavailableへ閉じ、必要な有限providerの引数/返却型/版条件をrootへ固定する。正式source providerを独自認証したことにしない。交代原本を含む現在版と開始原本を単にunionするだけで成功させず、source集合の完全性と取消/訂正による投手出場の除去/保持が既契約から確定する範囲を検査する。新しい意味判断はrootへ返す。

| # | 実装単位 | 検査/成立条件 |
|---|---|---|
| 1 | 登板の閉source/SQL宣言と生成器を候補化し、既readへのsource境界を具体化する | 始投手/0球交代/再登板/守備変更で投手へ/無関係交代、欠落frame・別tenant・不正receipt・旧checkpoint・未供給の正負対向。野球状態の再計算はしない |
| 2 | 唯一の生成SQLをbasic_sqlに接合し試合/season/category/表示/CSVへ同値供給する | 1試合1・2試合2・再開中除外・再終了1・JST境界・official/practice/all・ページ境界・供給不足はunavailable。表示/CSVは既DTOを使う |
| 3 | owned実PGで真正開始/交代/終了/再開/再終了とreadを照合する | 同一source固定/同RR、実認証/記録権/同TXを維持しfixture投手出場だけの成功を製品接続と扱わない。正式DDL/catalog/7.7と全CIはrootへpacket |

編集候補: backend/src/pitchlog/stats/basic_sql.py、必要時basic_stats.py、backend/domain/stats-appearance.model.json/schema.json/manifest.json（全て新規候補）、backend/src/pitchlog/domaingen/stats_appearance.py、backend/src/pitchlog/stats/generated/appearances.sql、D03専用tests/test_stats_appearance_source.pyとtests/db/test_stats_appearance_http.py、既test_stats_basic_sql.pyの登板部分、本計画のみ。root採用後に実装する。新生成manifestは公式生成器の候補出力に限定し正式D11/共有manifestを編集しない。既計算modelやT5/T6の他指標を改変しない。

source唯一writerは本新WT担当。共有sync/domain/認可source、contracts/正式assets/catalog/seal/history/7.7、共有台帳/他WT/main/developは非編集。実PGは共通owned-pg-browser-network.lockを全寿命保持しDSNをunset。未完のCSV依存130/0047と起動0046を正式成立へ読み替えない。既8/27項目等の見かけの件数を完了尺度にせず、登板を正しく取得できた操作/証拠/不足sourceを報告する。
