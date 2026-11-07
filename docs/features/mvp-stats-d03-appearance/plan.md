---
feature: mvp-stats-d03-appearance
status: active
branch: feature/mvp-stats-d03-appearance
承認: PO委任によるCodex/root判断（2026-11-07、対象8033f1d7全文）
重さ分類: コア領域（成績source未正式除外）
計画レビュー周回: 1
確定ゲート周回: 0
---

# D03・真正投手出場から試合別とシーズンの登板を供給する

起点6a424a301a7acbc15fe55f9e25506f874e1ca1e1。PO採用済みD03は、実際に投手として出場した試合を1登板、再登板は同試合1、0球交代も1とする。球数/打者数から出場を推測しない。D02の公式=公式戦/準公式戦、練習=オープン戦/紅白戦/その他、allとJST暦年は既宣言を再利用する。本人署名・P6 blindや正式受理を代記しない。

## 現物と開始条件

既basic_sql._normal_appearance_sqlは開始原本だけを確認し、試合別・交代/取消/再開なしに限定している。シーズンは常時source_unavailable。basic_statsは登板のoptional値と未供給理由を既実装しており、新しい表示式は不要。

public.participation_intervalsはmutableでstats fact versionへの束縛が無く、その行だけのCOUNTは採用しない。新しいevent状態畳込も行わない。開始時game_lineupsとcommitted start原本、現在checkpointのsubstitutionFramesが持つbefore/afterContext、0044 substitution_write_receipts/nonplay admission/event/ledger/slotの同TX原本を再利用する。真正性の既境界はauthz/nonplay_prefix_read_sql.pyとsync/substitution_projection.pyに存在する。出場候補は検証済み文脈のfielding position1のplayer identity集合に、実際に守備へ出たことを証明する半回開始/投手出場原本を結合したものに限定する。開始スタメン掲載/交代登録だけでは出場成立にしない。1回表早期終了の先攻投手、守備開始前に交代した選手を除外し、実守備出場済みなら0球交代も保持する。投球creditの存在は出場の十分条件になる場合も必要条件にはしない。

半回開始/投手出場原本の実供給可否は未確認であり、本plan全体の集計実装着手条件とは別にstep1で閉じる。既mvp-basic-stats-csv/plan.mdはlineup/payloadからの推測集計を禁止しており、既正常限定SQLもこの境界に対して再検査が必要。providerが無いと分かれば、必要な最小typed観測/生成タイミング/版付き保存先/原子的更新案をrootへ提示し、共有核を勝手に実装しない。

D03 readは既T6のcurrent版/唯一S/healthと同RR、既basic_sqlの真正終了LC receipt/head照合と同じgame集合へ束縛する。再開中は公式対象外、再終了は同gameの現版だけを参照する。出場identity集合のCOUNT DISTINCT(game_id,player_id)を単一SQL宣言で一度だけ計算し、basic_sqlはscope/bind/形式へ接合する。別のPython/FE計算は作らない。

着手はrootの本計画採用後。実checkpoint/frameを既guardと同等に照合できるread資格/版identityが不足する場合は、缺測を0にせずunavailableへ閉じ、必要な有限providerの引数/返却型/版条件をrootへ固定する。正式source providerを独自認証したことにしない。交代原本を含む現在版と開始原本を単にunionするだけで成功させず、source集合の完全性と取消/訂正による投手出場の除去/保持が既契約から確定する範囲を検査する。新しい意味判断はrootへ返す。

| # | 実装単位 | 検査/成立条件 |
|---|---|---|
| 1 | 登板の閉source/SQL宣言と生成器を候補化し、既readへのsource境界を具体化する | 始投手/0球交代/再登板/守備変更で投手へ/無関係交代、欠落frame・別tenant・不正receipt・旧checkpoint・未供給の正負対向。野球状態の再計算はしない |
| 2 | 唯一の生成SQLをbasic_sqlに接合し試合/season/category/表示/CSVへ同値供給する | 1試合1・2試合2・再開中除外・再終了1・JST境界・official/practice/all・ページ境界・供給不足はunavailable。表示/CSVは既DTOを使う |
| 3 | owned実PGで真正開始/交代/終了/再開/再終了とreadを照合する | 同一source固定/同RR、実認証/記録権/同TXを維持しfixture投手出場だけの成功を製品接続と扱わない。正式DDL/catalog/7.7と全CIはrootへpacket |

編集候補: backend/src/pitchlog/stats/basic_sql.py、必要時basic_stats.py、backend/domain/stats-appearance.model.json/schema.json/manifest.json（全て新規候補）、backend/src/pitchlog/domaingen/stats_appearance.py、backend/src/pitchlog/stats/generated/appearances.sql、D03専用tests/test_stats_appearance_source.pyとtests/db/test_stats_appearance_http.py、既test_stats_basic_sql.pyの登板部分、本計画のみ。root採用後に実装する。新生成manifestは公式生成器の候補出力に限定し正式D11/共有manifestを編集しない。既計算modelやT5/T6の他指標を改変しない。

source唯一writerは本新WT担当。共有sync/domain/認可source、contracts/正式assets/catalog/seal/history/7.7、共有台帳/他WT/main/developは非編集。実PGは共通owned-pg-browser-network.lockを全寿命保持しDSNをunset。未完のCSV依存130/0047と起動0046を正式成立へ読み替えない。既8/27項目等の見かけの件数を完了尺度にせず、登板を正しく取得できた操作/証拠/不足sourceを報告する。


root非作者全文レビュー/委任採用の固定点: HEAD8033f1d7d06a1a5d7723cde93d29adf0897b3907、plan SHA2560107e26a9f284896ad0def521b15c12dfd009db2833f6d063606bad2fb606d51。新P0/P1なし、source不足時の具体producer境界提示と独立生成/対向準備を含め着手可。root留保は既D03の実出場境界を保持するもので、新しいPO意味裁定ではない。本人確認・P6blind・正式値受理は記録しない。


## step1・実source確認と必要なproducer（2026-11-07）

現実装には実守備出場の完全供給がない。game_start_attemptsのcommitted/game_lineupsは開始承認/出場予定の原本、participation_intervalsはmutable投影でstats版FKなし、substitutionFrames/0044 receiptは割当変更と真正保存の原本で、未守備側が実際にposition1で出場したことを単独では証明しない。通常T1の攻守交代も計算結果であり、人が守備へ出た観測を補完しない。nativeの唯一Sはプレイ原本集合で、0球出場を完全列挙する別sourceはない。従って既_normal_appearance_sqlの両開始投手COUNTは早期終了時に誤計上し得る。閉じた実出場sourceが接続されるまでこの推測枝だけを除きsource_unavailableへ戻す（安全なavailable0へ置換しない）。

rootへの最小producer要求: (a) 実守備出場の確認原本を、元event/観測ID、tenant/game/player、所属side、投手position1、対象半回/時点、元記録権世代/D1とともに同一TX保存する。(b) 0球出場を含む各試合の完全集合について、native fact_version_id/revision/source_set_sha256と出場集合source receipt/hash/countを束縛し、終了LC head/receipt/public pointerと同じ版へ公開する。(c) 取消/過去訂正は原本sourceから有効集合を正規providerで更新し、再登板の複数proofは保持しつつgame/player一意に計数する。再開中は公式集合から除外し、再終了は新current版だけを公開する。共有核の変更はrootのみで実装し、本担当は原本を独自に畳み込まない。

候補入力CTEはappearance_scope（tenant/game/fact_version_id/revision/source_set_sha256/supply_complete/member_count）とappearance_members（同版5key＋player_id/proof_kind/proof_source_id）。proof_kindのdefensive-half-entry/pitcher-defensive-entryは供給境界の仮ラベルで、新しい記録操作/野球意味を正式採用したものではない。完全性boolだけを外から受けて成功資格にはせず、正式providerが元原本と集合hash/count/版を検証してこれらCTEを作る必要がある。生成targetはその後段の唯一COUNT DISTINCT(game_id)だけを担い、製品のSQL入口や任意Session APIを追加しない。未知種類/版不一致/件数不足/NULL/同game複数版は未供給で閉じる。

現段階の成立: 新候補SQL宣言/schema/生成器/manifestと合成SQLite正負ケースを用意した。これは真正provider/実PG/画面/シーズンの提供成功ではない。step2の実接続とstep3のowned検査を閉じるには上記producerの供給が必要。既API/CSVのunavailable表示経路は維持する。旧candidate body固定fileの機械的追随1pathはrootへ編集所有を照会済み、正式assetsは編集しない。


root PO委任判断で候補SQL1path（docs/features/mvp-basic-stats-csv/candidates/basic_stats_functions.sql）の機械的追随を追加承認。生成元はpitchlog.stats.basic_sql.candidate_sql、コマンドは `PYTHONPATH=backend/src <backend-venv>/python -c 'from pitchlog.stats.basic_sql import candidate_sql; ...write_text(candidate_sql())'`。旧SHAaeb11dcb1aca6e144e52f0606d2b33dd33456e91a4de2c7264fa2417672e1146→新SHA679e58e828c98eb2397db57f1dea8ec7b89703750d3887d799f3e6297c06f357。byte完全比較は維持し、正式contracts/catalog/sealは非編集。

供給の全欠落対向も保持する。生成SQLのexpected_game_count bindは既真正可視/対象current版集合の実件数からproviderが供給し、利用者自由入力や入力scopeの件数だけから作らない。1対象試合に対するscope0件を空season0へ変えず未供給にする。真正対象0件のseasonだけはavailable0となる。


step1途中固定: 最終凍結sourceでD03専用/基本SQL/既T6の3suiteが126passed22.67秒、Ruff/Ty成功、diff --check成功。宣言/生成SQL/manifestの再現比較と、0球実出場/再登板/2試合/未守備先発/他選手/別tenant/完全空集合/全scope欠落/版・件数・種類・NULL不一致の対向を含む。合成SQLiteの供給fixture成功は実PG/真正出場providerの証拠ではない。初回は本WTのprettier未配置で既生成suiteが失敗し、offline frozen install後に解消。candidate body byte不一致1件はroot許可後の公式再生成で解消し、比較を削除していない。2回のrootcwdからbackend testsを探した実行はno-testsであり成功件数に含めない。

実装されたのはD03計数の候補と既誤計上枝の閉鎖であり、step1の完全source成立・step2/3・登板の製品提供は未完。rootが上記真正producerと版付き供給を接合できた時点で、本生成SQLを同RRへ接続し、実終了/再開/再終了/区分/暦年/CSVを再実証する。


## 次単位の最小追補・既状態遷移からの真正entry（2026-11-07）

前step1 packetは「計算上の半回遷移と別に、人の実守備確認を新設しなければならない」としたが、これは既原典照合が不足した過剰前提なので撤回する。FR-023/XMARK本文は攻撃回の開始を「当該チームの攻撃状態へ遷移した時点」、初球前も開始済みと既定義し、XMARK-02は表完了時終了により裏が未開始の場合を区別する。FR-003は第3outの攻守交代、FR-011は交代記録時点の効力を既定義する。D03はその時点の守備側position1出場を採用する。PO委任rootはこの既規定の技術接合を採用済みで、新たなPO意味裁定や観測操作を前提にしない。75112239の旧スタメン両投手推測枝の閉鎖は維持し、真正片側entryへ置き換える。

推奨は既保存TX内の単一SQL entry projector＋版付き集合。開始保存receipt/committed start原本→初期T1の1回表が開始済みであること→後攻position1だけを保存する。既play/runner/non-pitch確定では既artifactのT1 before/afterとT2 facts/decisionを写し、次半回が開始済みと確定した場合だけ新守備側position1を保存する。表完了でもT2が終了を検知し裏未開始（XMARK-02）なら保存しない。終了理由の再計算やスコア/回/アウトからの別推測はしない。交代は唯一artifactのbeforeContext/afterContext/attackingSideと確定receiptを使い、現在守備側のposition1へ実際に就いたincomingだけを即時保存する。攻撃中の投手割当変更は予定変更でありentryを作らず、そのチームの守備半回が開始する時点に有効な選手だけを採る。0球交代もこのentryの存在で計数する。T2による未開始半回が再開操作で初めて開始済みとなる場合は、既LCのrelease済みcontextから同じprojectorへ供給する。単なる再開/再終了で既半回のentryを水増ししない。

保存案: 原entry表はtenant/game/player、defending_side、inning/half、proof_kind、元start_attempt_idまたはsource_event_idの閉union、元generation/D1/slot版（開始は架空D1=0を作らない）、元fingerprint、唯一artifact hash、T1/T2/交代receiptの根拠IDを持つ追記専用。原本event/start receiptへの複合FKを持ち、同要求再送は同proofを再掲する。member/headerはtenant/game/native fact_version_id/revision/S＋entry集合hash/countを束縛する。全原entryは監査保存し、有効memberだけを現在集合へ供給する。自由なtrue/Session/JSONから真正資格を発行しない。候補migrationスロット/slugはrootが選び、0046/0047/0048を流用しない。

TX境界: repositories/game_start._initialize_startの正式保存receiptと同TX、sync/stats_native_flush._flush_native_statsの既native Save/CSV producerと同TX、既substitution_execution/正式consume_substitutionのreceipt/checkpoint更新と同TX、既Undo/P3の唯一再計算結果/Saveと同TX、既lifecycleの終了/再開版更新と同TX。startはnative play sourceがまだ無いので原entryを保存し、最初のnative Saveで開始原本も含め完全memberへ束縛する。0プレイの終了も既LCが真正empty Sのnative版を確定できる必要があり、未供給ならその経路を別依存として具体化する（架空playやfinalize fixtureで補わない）。P3/取消のmemberは既canonical/capsuleと復元contextの有効原本から作り、別event列畳込を実装しない。

編集提案: 本担当は既stats-appearance.model/schema/生成器/専用testsと、stats/pitcher_appearance_source.py（新規・sourceの閉型/同一SQL呼出adapter）、db/game_state/pitcher_appearance_models.py（新規候補）、repositories/stats_appearance.py（新規・有限同RR読取候補）、D03専用DB testsを実装する。共有保存hook/正式migration/provisioning/catalog/D11/7.7はroot専有のままcache patchに分ける。単一SQL projectorで既kernel出力を照合/写像し、T1/T2/scoreboard/終了理由/D04責任計算のコピーを作らない。最終パス追加はrootの本追補採用後に着手する。

独立case: 開始直後0球は後攻投手1/未守備先攻0、1回表の早期終了も同じ、表第3out→裏開始は先攻投手entry、表第3outでも終了条件成立で裏未開始はentry無し、守備中A→B→Cが0球でもB/Cを含む、攻撃中A→B→CはBを数えず次守備開始のCだけ、同試合再登板はgame/player1・別試合は2、同D5再送/ACK喪失でproof/member増加無し、取消/P3で元根拠だけ失効・再開/再終了で旧終了版を二重加算しない。故障点は原entry保存後/member挿入後/native公開pointer直前で全TX rollback。RR読取はfact版/S/entry集合hash/count/LC版と完全照合し、越境/旧版/未知kind/全体不足は拒否する。D04/BFは既27native metricの責任帰属を一切変更せず、登板はPA/BF/pitch_countを入力にしない別原事実集合とする。
