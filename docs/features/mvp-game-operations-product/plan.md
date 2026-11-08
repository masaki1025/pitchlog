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


2026-11-08 18:50 JST root共有接合追補（PO委任によるCodex/root判断）: 既step1/2の走者あり凡打・野手選択・犠打/犠飛・併殺等を作者専用枝の唯一核へまとめ、rootは既lineup v3 JSON schema2件/d.ts2件、固定親bodyからの保存SQL overlay/公式body、stats/facts.pyの原観測射影、公式artifact pin/有限互換/D11と関連正負試験を直列で接合する。走者別RBI-03/04の観測と実runner IDをT1/V7で一致させ、現行writerで欠落・余剰を拒否する。旧保存原本の再生と新規記録/訂正の入力条件を分け、旧53host全値・規範期待を変更しない。非作者の固定差分確認/実保存/正式値受理/必須CI前は候補として保持する。新しい意味判断は含めず、未裁定の失策・妨害因果だけ留保しMVP残件へ維持する。部品ごとの新ゲートを追加せず、作者batchの固定版とroot接合差分をまとめて検証する。
