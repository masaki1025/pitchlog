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


非作者のNFR-018指摘反映（2026-11-06、PO委任Codex/root判断）: ef992の敵対レビューでbackend projection検証内のフォース連鎖再計算とTS内の占有真理値表重複を検出、双方採用。backendは唯一hostの真正出力/再実行完全一致とmodalityの型付き投影検証を保持し、野球意味のforce再導出を削除。TSは既hasRunnerをrunnerOccupancy.tsへ移しstate/battedHitから共有、adapterは閉塁番号のBigInt変換だけとする。数学真理値表を変更しない。artifact/pin/manifestは合成source固定後に公式builderで一括追随し、更新未了の固定版は提供済みとしない。最終非作者反映確認が必要。


非作者P1物理statusの反映（2026-11-06、PO委任Codex/root判断）: packet43cdde37e70a4e91fecc7842fa33ae10012821d1035bf2bace769051d8e4e97dの16pathを接合。起点baseと当該playの到達status/auto-manualを区別し、唯一T1の進塁計画から固定語彙へ写す。V7の明示overrideはmanual、規範による自動はauto。SQL・保存全値read・BE DTO・FE validatorを同時追随。作者owned実画面3試合ではhelperとの自己比較に加え、DBの(1,三進,manual)/(1,本進,manual)/一二塁HRの2行を独立literalで照合し1passed155.18秒。root実木75/FE34成功、全publisher body一致。SO05はアウト原因未供給のため物理保存は閉拒否、T1の純数学ケース成功を製品保存へ拡大しない。最終非作者反映確認/同版全ハーネス/正式受理は未了。

2026-11-08 root接合追補（PO委任Codex主担当判断）: 1bf起点の凡打死作者候補を既step1/2の範囲で、root専用feature/mvp-batted-out-integration-20261108へ接ぐ。rootはlineup v3 schema2件/d.ts2件、terminal_pitch_write_stamp唯一factoryと公式body/manifest、唯一artifactの既公式pin/有限互換宣言を直列所有。旧4安打のnone制限を保持したresult/第三アウトの閉union、無走者凡打0/1アウトnone・2アウトの記録者明示batter-before-first/公式打者ID照合だけを追加する。既数学期待/owner/ACL/nonce/同TX条件を変えない。固定差分の非作者レビュー・実保存が未了の版は候補に留め、正式値の受理/全件CIは最終候補固定後にまとめる。

残る打球操作群の作者追補（2026-11-08、PO委任root指示、起点 `7bdbf6082f62935738530766c57cc0e3d5204b48`）: 既step1/2の未接続打球を一群として扱う。対象は走者あり凡打、併殺・野選・犠打/犠飛・失策・妨害のうち正本付録E/OUT3/RBI/INTと既閉契約から計算・原本が確定する有限形。唯一frontend T1核へ明示観測を渡し、domainrtは同artifactの実出力とV7元観測を照合する。必要な走者別第3アウト時機、公式失策帰属、妨害裁定、打点因果を推測・既定補完せず、欠落/未知形は閉拒否する。所有はfrontend domain打球、打球観測API/provider/画面、backend domainrt閉型・terminal pitch payload/物理投影、専用試験と本計画のみ。契約/正本/共有SQL/認可/catalog/正式pin/台帳はroot唯一writerへbefore SHA付きpacketで渡す。旧4安打・無走者凡打・RunnerEvent・通常投球の意味と拒否順、同TX/テナント/重複原本を保持し、公式artifact buildは操作群をまとめて一回だけ行う。有限ケースの成功を全MVP完了とせず、意味未定の具体例だけを別票へ記録する。

配置拡張の技術追補（2026-11-08、同step1、PO委任root指示）: 既`ADV-01`〜`04`の明示overrideを唯一T1核へ渡す範囲で、犠打は在塁者の実進塁を必須、犠飛は三塁走者の実生還を必須とし、0/1アウトの複数配置を閉検証する。野選・打球出塁は実到達とフォース連鎖・塁衝突を検証し、`RBI-08`の野選得点は唯一核の条件へ接ぐ。失策を伴う犠打は現行の記録者入力が`RBI-05`の反実仮想を表せないため、無得点かつ公式失策1件だけを通し、得点配置は閉じる。旧53原本/旧artifactは書き換えず、現行新規writeでは唯一核が返す有効生還効果と走者別因果の全キーを照合する。進塁が一件もない在塁走者の全停止や、野選の走者アウト、失策下の得点、妨害裁定はこの段階の成功範囲へ含めず、入力契約と実装の残件に保持する。

全停止・失策出塁の追補（2026-11-08、同step1、PO委任root指示）: 在塁者の通常飛球アウトで全員停止したことを記録者が確定できるよう、既`applied.overrides`の各走者に「起点塁への明示到達」を追加する。全停止時は全在塁走者の記載を必須にし、未入力/部分入力を拒否する。同塁は唯一核へ`hold`として渡し、物理行には起点塁とmanual観測を保存する。打者出塁と同塁の衝突は従来どおり拒否する。正本matrixの`batting-result.error`は公式失策1件と守備側実野手を必須とし、得点時の`RBI-05`因果が未表現の現入力では無得点だけを受理する。共有schema/SQLの閉enum・条件はbefore SHA付きpacketでrootへ渡し、旧原本/旧期待は不変更。前段の「全停止は残件」は本追補で解消するが、野選で走者をアウトにする場合、失策下得点、妨害裁定は依然閉拒否とする。

走者別打点因果の是正（2026-11-08、PO委任root指示）: FR-003と付録A-3のRBI-03/04に従い、打球結果名・失策なし・本塁到達だけから打点を推定しない。実生還した非本塁打走者には起点塁別の「通常プレイ／ミスプレイ中も走り続けた／停止後再発進」をV7/T1両方で明示し、唯一核で得点と打点を別々に確定する。旧保存原本・53件の旧要求と数学値を変更せず、現行writerのV7読取だけ必要な全キー欠落を閉拒否する。このwriter限定呼出差分が `ordinary_pitch_execution.py` の2箇所へ必要なため、本人担当の同path追加と後発root接合packetへ含める。過去訂正の新入力は同じ現行観測を要求する接合残件であり、旧artifactの読取資格を訂正時の欠測補完に流用しない。
