---
feature: mvp-game-operations-product
status: active
承認: 済（PO委任Codex主担当/root、2026-11-06。2時間の実接続優先試行）
重さ分類: コア領域
branch: feature/mvp-game-operations-product
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-game-operations-product
created: 2026-11-06
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 残る試合操作を既計算核と製品経路へ接続する

POの「統合候補までまとめて実装し、その固定版をまとめてレビュー・検査」「今から2時間その方法」を根拠に、既採用MVP内の実装を進める。独立レビューは候補固定後に実施、正式統合前の全件/認可/耐久性/正式値ゲートは維持する。本人逐行確認や新意味の採用は代記しない。

固定基線67218adb（候補、正式developではない）。最優先は走者あり打球・走者アウト/併殺/失策等の未対応操作を既単一T1核へ実装し、同じhost/同期/保存/再取得へ接続する。既feature/mvp-runners-batted-spike@fdab2a64等の素材を再利用し、全差分一括採用はしない。契約・正本から確定しない得点/RBI/第3アウトの因果を推測しない。

## 編集所有

この専用WTのfrontend/src/domain/**、関連frontend/src/apiの打球・走塁境界、GameScreenBattedHitObservation/OrdinaryPitch/Provider/Controllerと専用spec/実画面試験、backend/src/pitchlog/domainrt/lineup_prefix_source.py・lineup_play_prefix_continuation.pyの閉wire型・同期terminal_pitch_payload/projectionと関連専用試験、専用docsを担当する。唯一artifactは公式builderで生成し、正式pin/manifest/認可契約への必要差分は別patchでrootへ渡す。共有台帳・他WT・正式contracts/正本/DDL/認可資産を直接編集しない。rootは取消/終了再開/正式資産のwriterを保持する。

## 実装ステップ

| # | 単位 | 到達条件 |
|---|---|---|
| 1 | 既正本/閉型の操作を唯一T1核へ実装 | 未対応操作を列挙し、観測入力を明示。既23flag/OUT3/RBI/状態の正負対向、旧回帰、型の検査。新意味が必要な箇所だけ具体例で留保し他を継続 |
| 2 | 既製品HTTP/画面/保存へ接続 | 正式既認可/記録権/同TX/再送/結果不明を維持して同じ候補の再取得まで進む。仮Port/固定結果/生イベント独自集計を作らない |
| 3 | 固定候補の独立レビュー・実結合検査 | 全差分/原典/検査/未達をrootへ引渡し。正式資産/必須CI/通常PRはrootが直列管理し、不成立を完成としない |

2時間の開始は2026-11-06 18:37:31 JST、評価時刻20:37:31 JST。作業上限/停止命令ではなく製品成果を評価する区切りであり、MVP全目標を縮小しない。


root接合候補反映（2026-11-06 19:46 JST、PO委任Codex/root判断）: actual LC a7ae1d40へsource2bdfを通常mergeした後、最終overlay patch SHA57556d3cf1ecba5aa51775c7c5dfa99ccb07766289839167971e55ed75941b08の25path全before/after SHAを照合して適用。正式schemaと唯一artifact fbcf253bの結合、有限v2旧host互換witness、公式SQL body/manifestの候補を揃える。過去数学期待217件を保持した作者証拠、独立clone再適用25/25、旧profile54・正式FE schema6成功を根拠とするが、root最終独立確認/全ハーネス/正式受理は未了。source単体merge後はroot backend107件/FE型成功。終了再開cache/交代は未合成であり、MVP全体/正式提供と記録しない。

凡打死の後続実装（2026-11-08、PO委任root指示、起点 `1bfad343fa365f3902d1a02b38a5f1b1a5cf8139`）: 既承認step1/2の未対応打球を現統合候補へ追加する。最初に `batting-result.batted-out` の無走者・明示失策なし/妨害なし、通常アウト及び打者走者の一塁到達前による第3アウトを、既T1唯一核・v3画面・同期/保存/GETへ接続する。走者あり/併殺/失策/妨害の因果観測が不足する分岐は閉拒否して後続残件に保持し、この有限実装を全試合完成と扱わない。担当所有は本計画の既列挙された frontend domain/API/打球画面/Provider、backend domainrt/sync payload/物理投影と専用試験に限る。共有SQL/registry/認可/catalog/contracts/正式pinは root 唯一writerへ before SHA 付き候補packetで渡す。旧4安打/走者操作/保存資格・同TX・再送の拒否順を維持し、唯一artifactだけ公式builderで再生成する。原典は付録Eの `batting-result.batted-out` 行、OUT3-01、FR-003/005とし、必要な記録者観測を既定値で補わない。

凡打死後継artifactの有限追随（2026-11-08、PO委任root指示、統合起点 `5bc8bb681073051a0499a3098a4157d649a02a9a`）: 公式builder結果 `0db3c87d…b72fff` へ現行D11/manifest/FE fixtureを追随する。旧v1/v2/v3 witnessと全規範期待は不変更。実Git旧`ab8e9de1…a2ff8c` hostと新実hostの53件全値一致を旧期待から導き、実行pinと既許可自己echoだけを再封印したv4 witness/有限4pair registry・検証器を追加する。旧`4e8b`/`4e7d`は既v3鎖の固定hashも検査し、未知pairは拒否する。共有D03開始SQL/正式authz資産はroot唯一writerへ生成本文候補を渡し、本候補の純検査を実PG/正式受理へ読み替えない。

凡打死隔離実画面確認（2026-11-08、PO委任root指示、起点 `c20d245d46deb1d7231e731e67a750a353314c17`）: step2/3の製品縦断として既`RealGameRecording.e2e-support.ts`の打球観測有限分岐と専用Playwright/config/owned backend testだけを新WTで実装する。真正画面create/start、3凡打で第3アウト、同D5原要求重複、reload、実DBの3原本/current成績版を同じ正常49 profileで確認する。事前に型/lint/collectを通し、共通PG/browser lockを全寿命保持する。共有SQL/正式資産/台帳は編集せず、実試験未通過を成功に数えない。


非作者のNFR-018指摘反映（2026-11-06、PO委任Codex/root判断）: ef992の敵対レビューでbackend projection検証内のフォース連鎖再計算とTS内の占有真理値表重複を検出、双方採用。backendは唯一hostの真正出力/再実行完全一致とmodalityの型付き投影検証を保持し、野球意味のforce再導出を削除。TSは既hasRunnerをrunnerOccupancy.tsへ移しstate/battedHitから共有、adapterは閉塁番号のBigInt変換だけとする。数学真理値表を変更しない。artifact/pin/manifestは合成source固定後に公式builderで一括追随し、更新未了の固定版は提供済みとしない。最終非作者反映確認が必要。


非作者P1物理statusの反映（2026-11-06、PO委任Codex/root判断）: packet43cdde37e70a4e91fecc7842fa33ae10012821d1035bf2bace769051d8e4e97dの16pathを接合。起点baseと当該playの到達status/auto-manualを区別し、唯一T1の進塁計画から固定語彙へ写す。V7の明示overrideはmanual、規範による自動はauto。SQL・保存全値read・BE DTO・FE validatorを同時追随。作者owned実画面3試合ではhelperとの自己比較に加え、DBの(1,三進,manual)/(1,本進,manual)/一二塁HRの2行を独立literalで照合し1passed155.18秒。root実木75/FE34成功、全publisher body一致。SO05はアウト原因未供給のため物理保存は閉拒否、T1の純数学ケース成功を製品保存へ拡大しない。最終非作者反映確認/同版全ハーネス/正式受理は未了。

2026-11-08 root接合追補（PO委任Codex主担当判断）: 1bf起点の凡打死作者候補を既step1/2の範囲で、root専用feature/mvp-batted-out-integration-20261108へ接ぐ。rootはlineup v3 schema2件/d.ts2件、terminal_pitch_write_stamp唯一factoryと公式body/manifest、唯一artifactの既公式pin/有限互換宣言を直列所有。旧4安打のnone制限を保持したresult/第三アウトの閉union、無走者凡打0/1アウトnone・2アウトの記録者明示batter-before-first/公式打者ID照合だけを追加する。既数学期待/owner/ACL/nonce/同TX条件を変えない。固定差分の非作者レビュー・実保存が未了の版は候補に留め、正式値の受理/全件CIは最終候補固定後にまとめる。

## 2026-11-08 9回凡打55プレイの実環境検証追補

PO委任rootの指示で、c20dを含む3a3b25b6から専用WT `feature/mvp-full-game-batted-out-20261108` を起こす。旧9回163球の試験は保持。新規画面作成→先頭HR1点→無走者凡打54out（計55play/18半回）→正式終了→reload→同終了版の試合/JST暦年season成績と毎球/成績CSVを実API・保存原本へ照合する。全MVP操作網羅・実機・性能完成とは別。

編集所有は新 `GameScreenFullGameBattedOut.e2e.ts`/config、新 `backend/tests/db/test_full_game_batted_out_screen_e2e.py`、本追補。root追加移管で既共有 `RealGameRecording.e2e-support.ts` のfielder選択だけをtop→home/bottom→awayの実守備側へ閉対応し、未知/不足はthrow。既作成/記録helperを再利用し、原headを偽造して合わせない。製品domain/正式asset/他WTは非編集。helper前後SHAと純正負を固定する。既3a3のbackend wire型期待修復はgame担当専有で非編集。

まず型/限定純検査を行い固定HEAD/patchをrootへ渡す。root接合・非作者確認後に共通ownedPG/network lockの順序下で1回実測。UI/実認証/記録権/唯一artifact/同TXを省略せず、候補SQL/権限注入を使わない。未供給は失敗として記録し、0/現在名簿/固定成功へ補完しない。


2026-11-08 18:48 JST root共有接合追補（PO委任によるCodex/root判断）: 既step1/2の走者あり凡打・野手選択・犠打/犠飛・併殺等を作者専用枝の唯一核へまとめ、rootは既lineup v3 JSON schema2件/d.ts2件、固定親bodyからの保存SQL overlay/公式body、stats/facts.pyの原観測射影、公式artifact pin/有限互換/D11と関連正負試験を直列で接合する。走者別RBI-03/04の観測と実runner IDをT1/V7で一致させ、現行writerで欠落・余剰を拒否する。旧保存原本の再生と新規記録/訂正の入力条件を分け、旧53host全値・規範期待を変更しない。非作者の固定差分確認/実保存/正式値受理/必須CI前は候補として保持する。新しい意味判断は含めず、未裁定の失策・妨害因果だけ留保しMVP残件へ維持する。部品ごとの新ゲートを追加せず、作者batchの固定版とroot接合差分をまとめて検証する。

共有接合下書きpreflight（2026-11-08 18:52 JST）: 旧canonical schema SHA0523f14a/2fac3fe6を入力に、走者別RBI閉map/実走者force-out/新resultのJSON2件をcacheだけへ描画し、meta2件・shape20正負を確認。製品schema/正式受理/実保存は未変更。RBI-03/04の新観測不足を作者が採用し、新writeは有効得点走者全キー必須・旧53数学/保存読取は固定互換へ分離して同batchへ反映中。作者固定後にrootが実schema/d.ts/SQL/T5/唯一artifactを接合する。
残る打球操作群の作者追補（2026-11-08、PO委任root指示、起点 `7bdbf6082f62935738530766c57cc0e3d5204b48`）: 既step1/2の未接続打球を一群として扱う。対象は走者あり凡打、併殺・野選・犠打/犠飛・失策・妨害のうち正本付録E/OUT3/RBI/INTと既閉契約から計算・原本が確定する有限形。唯一frontend T1核へ明示観測を渡し、domainrtは同artifactの実出力とV7元観測を照合する。必要な走者別第3アウト時機、公式失策帰属、妨害裁定、打点因果を推測・既定補完せず、欠落/未知形は閉拒否する。所有はfrontend domain打球、打球観測API/provider/画面、backend domainrt閉型・terminal pitch payload/物理投影、専用試験と本計画のみ。契約/正本/共有SQL/認可/catalog/正式pin/台帳はroot唯一writerへbefore SHA付きpacketで渡す。旧4安打・無走者凡打・RunnerEvent・通常投球の意味と拒否順、同TX/テナント/重複原本を保持し、公式artifact buildは操作群をまとめて一回だけ行う。有限ケースの成功を全MVP完了とせず、意味未定の具体例だけを別票へ記録する。

配置拡張の技術追補（2026-11-08、同step1、PO委任root指示）: 既`ADV-01`〜`04`の明示overrideを唯一T1核へ渡す範囲で、犠打は在塁者の実進塁を必須、犠飛は三塁走者の実生還を必須とし、0/1アウトの複数配置を閉検証する。野選・打球出塁は実到達とフォース連鎖・塁衝突を検証し、`RBI-08`の野選得点は唯一核の条件へ接ぐ。失策を伴う犠打は現行の記録者入力が`RBI-05`の反実仮想を表せないため、無得点かつ公式失策1件だけを通し、得点配置は閉じる。旧53原本/旧artifactは書き換えず、現行新規writeでは唯一核が返す有効生還効果と走者別因果の全キーを照合する。進塁が一件もない在塁走者の全停止や、野選の走者アウト、失策下の得点、妨害裁定はこの段階の成功範囲へ含めず、入力契約と実装の残件に保持する。

全停止・失策出塁の追補（2026-11-08、同step1、PO委任root指示）: 在塁者の通常飛球アウトで全員停止したことを記録者が確定できるよう、既`applied.overrides`の各走者に「起点塁への明示到達」を追加する。全停止時は全在塁走者の記載を必須にし、未入力/部分入力を拒否する。同塁は唯一核へ`hold`として渡し、物理行には起点塁とmanual観測を保存する。打者出塁と同塁の衝突は従来どおり拒否する。正本matrixの`batting-result.error`は公式失策1件と守備側実野手を必須とし、得点時の`RBI-05`因果が未表現の現入力では無得点だけを受理する。共有schema/SQLの閉enum・条件はbefore SHA付きpacketでrootへ渡し、旧原本/旧期待は不変更。前段の「全停止は残件」は本追補で解消するが、野選で走者をアウトにする場合、失策下得点、妨害裁定は依然閉拒否とする。

走者別打点因果の是正（2026-11-08、PO委任root指示）: FR-003と付録A-3のRBI-03/04に従い、打球結果名・失策なし・本塁到達だけから打点を推定しない。実生還した非本塁打走者には起点塁別の「通常プレイ／ミスプレイ中も走り続けた／停止後再発進」をV7/T1両方で明示し、唯一核で得点と打点を別々に確定する。旧保存原本・53件の旧要求と数学値を変更せず、現行writerのV7読取だけ必要な全キー欠落を閉拒否する。このwriter限定呼出差分が `ordinary_pitch_execution.py` の2箇所へ必要なため、本人担当の同path追加と後発root接合packetへ含める。過去訂正の新入力は同じ現行観測を要求する接合残件であり、旧artifactの読取資格を訂正時の欠測補完に流用しない。

打球群の利用者実証（2026-11-08、PO委任rootの明示指示、起点 `2b762ede4c868c09156d898bd2d9ecb0c08f9c54`）: 本step2/3内の試験接合として、専用feature/mvp-batted-operations-screen-20261108で新 `GameScreenBattedOperationsBatch.e2e.ts`/config、`BattedOperations.e2e-support.ts`、`backend/tests/db/test_batted_operations_batch_screen_e2e.py`のみと本追補を所有する。旧RealGameRecording helper/Full55/163球を変更せず呼出・後段を再利用。1つの新規UI試合で走者あり凡打の全停止、犠打/犠飛/野選/公式失策1件（実守備野手ID）、併殺、生還したが停止後再発進のRBI0を明示し、合法配置から9回59プレイ/54outsへ至る。実認証/記録権/唯一artifact/同TX/同D5再掲/reloadと同終了版game/season27項目/毎球・成績CSVを既原本へ全照合する。固定SQLはUI前EXPLAINし、wire型/hidden_at/metric availabilityを事前検査する。事前投入game/play/仮Port/認可迂回を使わず、所有fixture語彙だけ準備可。共有schema/SQL/正式pinはroot単独接合のため現段階は候補で実走未成立。未支持配置や欠測を成功/0補完にしない。追加PGはroot/Recoveryの順序指示後、共通lock全寿命とDSNunset/source一致/cleanupを維持して1回実測する。

59打球群実証候補の固定（2026-11-08、実走前）: 新driverは前半14操作で全停止/SH/SF/FC/実野手失策/DP/停止後再発進の因果を明示し、残45凡打で9回54outsに至る。同じ59操作を公式artifact `ef7f0b0ef4c741d323ff3a061c54ec361e6f6e09c91e56c4b041712005aaee6b` へ純入力し、全14固定状態と59後のnormal-end、away2/home0・安打4・失策1が一致（cache pure-sequence-result.json）。これは資格を発行する検査でも期待値の再採取でもなく、固定UIシナリオの合法性確認。満塁の正準状態名がfirst-second-thirdである点を実走前に是正した。

実画面では新規作成/開始→全UI入力→実ACK/GET、2件目の同要求再送は重複/同head、14件目reloadを要求し、終了v1/同receiptとgame・JST2026 season27項目/両CSV/88列ZIPを保存版へ全値照合する。DBでは全41列とrunner10列を保存V7から既単一mapperへ通して完全比較し、全停止manual/DP封殺/失策1の原野手/RBI0を独立literalでも比較する。全固定SELECTは実UIの前にEXPLAINする。対象backend型/Ruff/pytest collect、frontend型/ESLint/Playwright list成功。実PG/実HTTP/実ブラウザは未実施、共通lock未取得。

残る供給はroot直列の新schema/SQLguard（同塁holdを旧guardが拒否する点の是正を含む）/rowgate有限結果と失策物理列/T5の新打球群/公式pin・manifest。起点2bのrepository結果は旧5種、native no-stealも旧凡打だけなので、この候補だけでは実保存を開かず、根拠付き接合後に1回実走する。旧55/163球/共有helper・数学/正式assets/台帳に差分なし。


### 初回単打送信前診断（2026-11-08、PO委任root指示）

正常49/71fの59操作run2は実create/start後にPOST未観測で停止。全59操作を反復せず、専用E2E/config/backend wrapperの新3ファイルだけで最初のsingleへ絞る。既製品/共通helper/認可/要求/slot/期限は不変更。CDPは開始後のcaught例外を一時停止してclassと固定src site/行のみ保存し即resume（message/locals/原文/UUID/資格なし）。この観測がタイミングに影響し得る限定を保持する。UI固定status分類、正規化endpoint/method/status、既finally read-only RRを残す。実head/観測JSON保存は不要。失敗は成功へ置換せず、root固定差分確認前のPG再投入なし。

診断採用: 2026-11-08 21:21 JST、PO委任Codex rootの非作者全文確認（e936bf7e / diff e0ffd13c9703fe7ece884306f4e641e932bd965af16c33a9bc19738017c669ee）。docstring是正とresume observerの未処理rejection抑止だけを追加条件として採用。製品不変、CDP観測の時機影響は実失敗と分離する。


### 59操作試験の正規C2読取接合（2026-11-08、PO委任root採用）

run6は実2play/同要求重複ACK後、test direct GETのC2提示不足で404。製品/認可/共通helperを変えず、59driverの再送後started・最終lifecycle started・毎球ZIPだけを実UIと同じ既client（readLineupPrefixGame/readGameLifecycle/apiDownload、内部tenantBound:true）へ委譲する。非C2のstatsJSON/成績CSVは既経路を保持。closed found/全prefix/after/items/終了版/ZIP全byte長とSHAの期待を維持し、401/404を成功へ置換しない。元59全実測の後続停止は別の初回原因として保存する。
