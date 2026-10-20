# U-F8全試合記録向け後続計画の採否

## 起案と第1回全文レビュー

2026-10-20のユーザー指示による未承認の別計画。第1期#160は`57069b72`へ最新developを通常取込み・push済みで、旧レビュー履歴は保持する。この記録は後続計画だけの6.1レビューであり、第1期の追加レビュー枠ではない。

既定ラッパー `python .claude/scripts/codex_run.py review adversarial -`、gpt-6-sol/xhigh、read-onlyで第1回全文レビューを実施。ログ`/tmp/uf8-followup-review1.log`、依頼全文`/tmp/uf8-followup-review1-prompt.txt`。判定は**否決 P0=3 / P1=6 / P2=0**。計画レビュー周回を0→1へ更新した。旧全文は`/tmp/uf8-followup-r1-before/`、報告抽出は`/tmp/uf8-followup-review1-report.md`。以下すべて採用、受理範囲外による不採用なし。起因は全件起案の欠落/不整合で、正本改訂ではない（7.3確定ゲートの(A)/(B)分類は適用外）。

| # | 重大度・指摘 | 採否と反映 / 典拠 |
| --- | --- | --- |
| 1 | P0 T1/T2接続を1コミットに束ねている | 採用。ステップ8/T1と9/T2を分離し、544/545所有PR・T1マージ待ち・実コミット対応を明記。U-X1計画4節/ハーネス6.1 |
| 2 | P0 新規route除外で実画面へ到達不能 | 採用。ステップ6に登録済みGameScreenEntry*/router*のページ付き一覧/開始/再開と2routeを追加。U-G1/U-G2公開APIの前提を明記。現routerに記録routeなしを確認 |
| 3 | P0 Playwright成果物/依存/CI経路なし | 採用。ステップ7と変更範囲にGameScreen系設定/シナリオ、package/lock、既存CIの専用隔離DB付きjobを追加。実Portの仮登録/実通しのskip成功は不可。現packageにPlaywrightなし、NFR-019のCI検査 |
| 4 | P1 FR-020〜023表示の対応欠落 | 採用。ステップ5/DoD/試験にH/E/K/B・当日/シーズン成績・7列打席履歴・球種割合/球数を列挙。T3〜T6等の正式提供待ちを不足表へ追加。要件書FR-020〜023 |
| 5 | P1 過去交代訂正なし | 採用。ステップ4/不足表/通し試験に交代の人/回/時点訂正・下流帰属を追加。主所有U-G2/再計算U-X1を維持。要件書FR-011 |
| 6 | P1 閲覧側の最終反映時刻/オフライン実測欠落 | 採用。ステップ5/11、DoD/試験に正式契約と入力/閲覧2端末の実測を明記。未提供時は未取得。要件書NFR-006 |
| 7 | P1 NFR-020の開始前提検査が不足 | 採用。ステップ6/11に前提1/5/6の単独/複合不足列挙、開始拒否、キュー保持、閲覧可を追加。persistだけの拒否と区別。要件書NFR-020 |
| 8 | P1 投球/非投球と必須値の区別なし | 採用。ステップ2と試験に非投球の盗塁/牽制/ボークと種別別必須値を追加。非投球でコース/球種/結果を要求しない。要件書4.0-2/FR-004 |
| 9 | P1 採否worklogが変更範囲外 | 採用。本ファイルを計画3節へ宣言。ハーネス6.3 |

変更は計画/設計/採否のみ。製品実装・正式資産変更・人間承認・逐行確認は行っていない。第2回は反映差分と影響節に限定する。計画の承認前コミット/実装開始はせず、ローカル成果を保全して人間へ提示する。


## 第2回反映差分レビューと採否

既定ラッパーのadversarial/read-only（gpt-6-sol/xhigh）で基本枠2回目を実施。ログ`/tmp/uf8-followup-review2.log`、依頼`/tmp/uf8-followup-review2-prompt.txt`、前版`/tmp/uf8-followup-r2-before/`。**否決 P0=2 / P1=2 / P2=0**。全4件採用、計画レビュー周回1→2。以下は第1回反映の不足に起因する。

| # | 重大度・指摘 | 採否・反映 / 典拠 |
| --- | --- | --- |
| 1 | P0 外部PRのステップ8/9がU-F8履歴の欠番になる | 採用。544/T1と545/T2を番号付き表から外して外部前提M-T1/M-T2へ移動。U-F8自身の9ステップだけを連番で実施し、統合SHA/公開型/結合証跡を受け取る。ハーネス6.1・feature_status |
| 2 | P0 CI差分で凍結基準/corpusが赤になる | 採用。限定された基準/履歴/スナップショット/corpusの候補更新と7.7の人間受理を3節/ステップ7/設計5節へ追加。CIだけ変えず、受理前は候補準備・ローカル検査まで。資産受理は代行せず、1〜6は独立提出可能。base-allowlist/census-baselineのexternal_filesとcorpus manifestを確認 |
| 3 | P1 断中更新が古い値の暫定表示でも合格になる | 採用。断中新規プレイごとの共有クライアント計算核による最新スコア/当日成績/球種割合/球数の更新をステップ9/DoDへ明記。FR-020〜023 |
| 4 | P1 全イニング欄・次打者/代打切替が不足 | 採用。各チーム開始済み全イニング/合計/H/E/K/Bと現在/次打者、代打記録時点の切替を表示・DoD・通し試験へ対応。FR-020/022 |

P0を2件採用したため、6.3の自動例外1回で第3回を**P0限定**の反映差分レビューとして依頼する。P1/P2の新規査読は依頼しない。第2回P1の最終反映は人間が差分を確認する残余として残す。正式資産の実差分・受理は将来のステップ7であり、今回変更したのは未承認計画文書だけである。


## 第3回P0限定レビュー・人間承認への提示

第2回P0を採用した自動例外1回として、既定ラッパーadversarial/read-only（gpt-6-sol/xhigh）でP0限定の反映差分レビューを実施。ログ`/tmp/uf8-followup-review3.log`、依頼`/tmp/uf8-followup-review3-prompt.txt`。**可決 P0=0**。前回P0二件の解消と新規P0なしを確認した。P1/P2は今回の査読範囲外で、全重大度ゼロの再査読とは記録しない。

第3回は指摘反映なしの確認周なので計画レビュー周回は2のまま。レビュー実行は基本2回＋P0例外1回を消費済み。追加枠は求めず、人間には13件全採用の一覧、最終計画、最終反映のP1範囲（断中更新・全イニング/次打者/代打切替）を提示する。製品実装/正式資産受理/人間逐行確認の記録は行わない。

提示時にdevelop `8e4698f6dc254439b7d5e0c273cc2aef70cda657`（#163受入シート判定修正）まで通常fast-forwardした。未コミットの計画文書は保持され、計画内容と製品コードに変更はない。P-7の523項目別責任受領と未提供型の区別は`docs/features/uf8-full-game-followup/p7-receipt.md`へ保存し、544主担当へ送付した。P-7全体成立や具体製品型の正式受理を代記しない。

## 2026-10-20 人間計画承認と実装再開

山田正輝が2026-10-20、計画SHA-256 `935bac90426571acf1c9a66b8d41ff0097e14232421fc5f80ff966e9f5551cf4` を明示して後続9ステップを承認した。実ファイルのSHA一致を確認して承認メタデータを更新した。査読実行3回・全13件採用・最終P0限定可決、採用反映2周と最終P1反映の未再レビュー範囲は保持する。承認は正式資産受理・P-7全体成立・本人逐行確認・公開・Draft解除・マージの許可を兼ねない。

ステップ1〜6は正式接続を待たず表示/フォーム/入口を実装し、未接続操作の実送信/成功表示は封鎖する。ステップ7は完全な前後値の候補準備まで進め、7.7正式受理を別途人間へ提示する。当日/シーズン成績の未提供は担当と必要な計算を明示し、分析40項目全完成を暗黙の前提にしない。

第1期GameScreenが未統合なので#160の固定HEADを通常取り込みし、後続PRは比較元をfeature/uf8-game-recordingにしたstacked Draftとして差分を分離する。#160の人間統合後に比較元をdevelopへ変更する。#160自身の差分/レビュー/本人確認資料を後続の実施記録へ混在させない。

## ステップ1 停止UI

既定implementラッパーでステップ1のみを実装し、同ステップの再開で表示専用のexport型を切り出し、利用者文言を是正した。`GameScreenStopDisplay.ts`は正式runtime DTO/停止判定/耐久索引ではない。0/未取得/読取失敗/停止/照会中、訂正注意3種、同内容再開/内容訂正の封鎖、直接dispatchでemit/送信/保存がないことをDOMで固定。関連Vitest12ファイル171件、Prettier/ESLint/vue-tsc/diff-check成功。

主担当は実Vue/CSS・既存Meiryoの隔離Chromium fixtureで375/320px各scrollWidth一致、POST0、pageerror0を実測し、画像を開いて確認した。0/未取得/読取失敗、fixture再供給の再読込、独立2タブの表示分離、断中封鎖を確認。再読込はfixture再供給であり、耐久provider・実Port/HTTP/DB受入ではない。結果`/tmp/uf8-followup-stop-browser-result.json`、画像`/tmp/uf8-followup-stop-{375,320}.png`。コードログは`/tmp/uf8-followup-step1{,-correction}.log`。全frontend検査は別途実行中で、完了前に成功とは記録しない。

## ステップ1の一次/敵対レビュー第1回と採否

固定比較97e6eeec...13d04a91にClaude一次（実モデルclaude-opus-5-5、read-only、`/tmp/uf8-stop-claude-review.json`）を実施し、P0=0/P1=0/P2=4。別に既定ラッパー敵対基本第1回（gpt-6-sol/xhigh、`/tmp/uf8-stop-adversarial1.log`）を実施し、否決P0=0/P1=1/P2=1。対象は停止UIコードPRであり計画レビュー/第1期#160の回数をリセットしない。レビュー者は自らテスト実行せず、主担当の実測と区別した。

| 指摘 | 採否・反映 |
| --- | --- |
| Claude P2/敵対P1: phaseにconstructor/__proto__等を渡すと継承値を拾う | 採用。文字列かつObject.hasOwnで自前キーを確認してからラベルを読み、未知/継承/非文字列の6件を追加。関連177件成功 |
| Claude P2: 現在地が第1期のステップ総数を読む | 採用。stacked比較元#160の旧8/10段をdevelopとの差として継承する警告とPR本文へ記し、#160統合後に再導出。新9ステップの件名は正規、機構を改変しない |
| Claude P2: 平常非停止状態が未定義 | 採用（接続時の受渡し）。506/U-S1の正式型提供時に非停止時の表示/非表示を合わせる。今回の表示専用型に新しい停止判定を発明しない |
| Claude P2/敵対P2: 全件結果・幅実測の記録不足 | 採用。13d04a91の全frontend83ファイル1567件/93.18秒、Prettier/ESLint/vue-tsc/build、closure9ファイル/外部0/違反0成功を記録。ブラウザ375/320=scroll375/320、POST0/error0、日本語フォント読込を実測済み。結果要旨をPRにも固定記載 |

是正は同ステップのimplement --resumeで実施し、関連177件・型/lint/整形/diff-checkが成功。全frontendは是正後にも別途実行する。ここでコード敵対の採用反映は1周、計画レビュー周回2/確定ゲート周回0は不変。追加の独立一次再レビューや人間逐行確認を代記しない。

## 停止UI提出状態（ステップ1のみ）

敵対基本第2回は13d04a91...df2f8935の反映差分と影響箇所を読み取り専用で確認し、**可決 P0=0/P1=0/P2=0**。ログ`/tmp/uf8-stop-adversarial2.log`。コード敵対は基本2回を消費、採用反映1周で終了。計画レビューは実行3回/採用反映2周、確定ゲート0のまま保持。第1期の敵対/normal回数へ流用しない。人間逐行確認は未実施。

最終コードdf2f8935のfrontend全件は **83ファイル/1,573 passed/124.44秒**。Prettier/ESLint/vue-tsc/build成功、closure9ファイル/外部0/違反0。root Ruff/ty・docs-status/計画同期/diff-check成功、影響するguard/計画同期のpytest **280 passed/25.72秒**。backend/lib/sync/contractsの変更は0で、第1期の隔離backend実測を再利用し今回再実行とは記録しない。実Port/HTTP/DB通しは未提供のまま。

提出比較元は第1期の固定97e6eeec（feature/uf8-game-recording）。このPRは停止UIのステップ1と承認/依存/採否文書だけで、残り8ステップや1試合完遂の完了ではない。台帳への追記なし: 新たな運用規則・確定傾向ではなく、既知のstacked枝の派生警告と未提供依存の個別記録である。計画statusをこの提出枝でin-reviewとし、次ステップは別の承認済み計画紐付け枝で進める。

### ステップ2の独立提出枝

計画のPR分割に従い、ステップ1の固定コミット13d04a91を比較元にした`feature/uf8-play-observations` worktreeでステップ2のみを実施する。計画本文・9ステップ・承認対象SHA・レビュー回数は維持し、実行枝のfrontmatter branchだけを更新した。ステップ1のレビュー/是正は親枝側で行い、必要な是正だけを明示的に取り込む。

## ステップ2 打球・走者観測の下書き（独立枝）

`GameScreenPlayObservation.vue`と表示専用型・質問部品・DOM試験を`GameScreen*`内に追加し、`GameScreen.vue`へ表示統合した。公開する表示契約は`PlayObservationRequest`（文脈キー、投球/非投球、非投球種別別の対象走者、質問、候補）と`RawPlayObservation`（payloadのraw観測のコピー）であり、正式wire DTOではない。非投球で旧投球欄を隠し、種別別の結果/到達・企図塁を受ける。打球座標は付録Bの値の手入力だけを保持し、タップ変換は封鎖。供給された捕球候補を表示して手動選択できるが、推定候補を既定選択しない。走者キーごとの進塁上書き・第三アウト時機・打点因果、妨害裁定、付随失策の質問は未選択を保持する。候補/文脈変更で下書きを破棄し、重複走者キーの要求は閉じる。実確定/保存/送信ボタンは封鎖を維持した。

実測: `pnpm test`は84ファイル1576件成功（後述の追加1試験より前）。最終の関連Vitestは`GameScreenPlayObservation.spec.ts`、`GameScreen.spec.ts`、`GameScreenStopDisplay.spec.ts`、`GameScreenNarrowWidth.spec.ts`の4ファイル46件成功。`pnpm exec eslint .`、`pnpm exec vue-tsc --noEmit`、対象5ファイルの`pnpm exec prettier --check`、`pnpm build`（build closure conforming）、`git diff --check`が成功。DOMでは投球/非投球、3種別、複数走者、未選択、提供質問の反映、候補/文脈切替、直接dispatchでfetch 0、停止/確定封鎖、375/320pxの縦積み・折返し構造を確認した。

実ブラウザのピクセル幅は未実測。隔離fixtureのVite起動が`listen EPERM`、ローカルChromium起動がsandboxの`Operation not permitted`で拒否された。付録B座標へのタップ変換、捕球推定、FR-003の対象走者/質問判定、妨害/公式記録の正式入力要求、単一計算の製品型/署名と正式wire変換・保存経路は未提供であり、仮実装で埋めていない。実試合・実送信・再読込復元の受入は未実施。ステップ3以降、コミット、push、PR、連絡は実施していない。

主担当による補完検証: 内側のimplement sandboxではローカルbind/Chromium起動が拒否されたため、主担当の許可済みホスト環境で同じ観測フォームの実Vue/CSS fixtureを起動し直した。HTTP localhost:15325・日本語Meiryoで375/320pxのdocument/body scrollWidthが各375/320、POST0・pageerror0・日本語フォント読込trueを実測。フォームの確定とタップ変換はdisabledのまま。結果`/tmp/uf8-observation-browser-result.json`、画像`/tmp/uf8-play-observation-{375,320}.png`。これは表示入力fixtureの検証で実Port/HTTP/DB受入ではない。

## ステップ2の一次/敵対レビュー第1回と採否

固定比較a1e5643d...584a0322にClaude一次（claude-opus-5-5）を実施しP0=0/P1=0/P2=7、既定コード敵対基本第1回（gpt-6-sol/xhigh）は否決P0=2/P1=2/P2=1。各レビューは読み取り専用で検査を再実行せず、主担当の実測を区別した。計画査読13件/第1期/停止UIの回数をこの観測コードPRへ流用しない。一次7件・敵対5件はすべて採用し、主担当補足も反映した。

| 指摘 | 採用反映 |
| --- | --- |
| 敵対P0: 配列回答と投球時企図塁をrawが捨てる | scalar質問をsingle-onlyの型/表示前検証へ限定し、投球時の企図塁もrawに保持。正式wire DTOとは分離 |
| 敵対P0/一次P2: 複数選択解除が空配列 | 最後を解除すると未選択null。明示noneは提供候補の選択だけから受ける |
| 敵対P1: 非投球の複数走者試験なし | 二走者の結果/到達/企図塁が独立してrawへ残る回帰試験 |
| 敵対P1/P2/一次P2: 全件・比較元・実ブラウザの時点不足 | 親是正追随後584a0322は84ファイル1583件/96.48秒、静的検査/build成功。当時の46件→追随後52件、起案基線13d04a91→提出比較元a1e5643dを区別。内側起動拒否は失敗のまま、主担当ホストでの実Vue/CSS/Meiryo375/320幅一致・POST0/error0を別途補完。是正後コードの全件は再実行する |
| 一次P2: 同内容props再供給でも消去 | 画面要求/文脈の内容比較用snapshotを共有し、新参照でも同内容なら保持。実変更時だけ破棄して理由を表示。通信codec/要求指紋ではない |
| 一次P2: unknown mode/非投球に打球・打撃結果混入 | 明示した2modeだけ受け付け、非投球への禁止質問は型/表示前検証で拒否。未知modeで旧投球欄を併出しない |
| 一次P2: 推定候補の採用が未観測と不明瞭 | 既承認の手動選択と同じ「候補を選ぶ」操作を追加し、明示選択IDと未観測nullを区別。候補の自動採用/新しい意味規則は追加しない |
| 一次P2: 質問のアクセシブル名/試験不足 | selectのlabel、複数選択のlegend、clear/identity変更/innerWidth復元を追加 |
| 主担当補足: identity変更でも子の観測が残る | 内容比較に基づき投球/観測の両下書きを破棄する回帰試験。同じ内容のidentity再供給では消さない |

同ステップのimplement --resumeで是正し、最終関連4ファイル67件・型/ESLint/Prettier/diff-check成功。全件・実ブラウザは主担当が最終コードを別途検証する。次の敵対レビューは基本2回目の反映差分と影響節だけ。人間逐行確認・P-7正式型受理・GAP-05/原子性/1試合完遂は未実施/未達を維持。

### ステップ3の実行枝

計画のPR分割に従い、観測入力の584a0322を基線にしたfeature/uf8-play-correctionsでステップ3を独立実装する。承認済み計画の本文/9ステップ/査読回数は維持し、実行枝のfrontmatter branchのみ変更。親の観測入力のレビュー是正は必要な差分だけ後で追随する。

## ステップ3 取消・過去修正の表示下書き（独立枝）

作業枝`feature/uf8-play-corrections`の236da432を開始点とし、584a0322の観測入力を継承した。`GameScreenUndo.vue`と`GameScreenPastCorrection.vue`を分け、`GameScreen.vue`には表示専用propと部品配置だけを追加した。正式履歴側がundo自身を除外して供給する直前の取消可能操作を表示し、対象なし/未取得を区別する。未送信/同期済み件数によるundo分岐はない。正式undo入口は未提供で、ボタンは全条件でdisabled。

過去修正は、記録権/空キュー/オンラインの提供状態をそれぞれ表示し、未知・非保持・未同期あり・断中を説明する。既存`deriveQueueStatus`は件数表示用で、空キュー全体や記録権・接続可否の正式判定を供給しないため、その件数から修正可否を再判定せず、別の表示専用`CorrectionPrerequisites`を受ける。前提がすべて揃うfixtureでも確定はdisabled。対象は提供された1ページ分だけを描画し、ページ送りも接続待ちで封鎖する。修正/挿入/論理削除ごとの提供質問をローカル下書きへ保持し、確認画面へ進める。サーバー供給の準備中/失敗/楽観ロック競合/差分行だけを描画し、文脈・対象・操作・下書き世代が一致しない旧応答は表示しない。下流の走者/得点/アウトや交代時点・終了状態は画面で計算・変更せず、終了後追記再開を起こさない。表示値はVueの自動エスケープを使用し、内部原因を表示しない。下書きは未保存で離脱時に消える旨を明示した。

実測: 関連Vitest 6ファイル87件成功（`GameScreenCorrection.spec.ts`、既存のGameScreen/観測/停止/狭幅/確定ゲート）。対象5ファイルのESLint・Prettier check、`vue-tsc --noEmit`成功。DOM試験ではundoの対象なし/未取得と件数非分岐、過去修正の前提5組、3操作の入力/確認、プレビュー4状態と識別子4項目の不一致、旧文脈遮断、直接dispatch時のfetch/保存/操作イベント0、375/320px向け縦積み構造と長い名前の折返し指定を確認した。既存の停止・観測・確定封鎖の関連試験も通過した。

frontend全件試験、実ブラウザのピクセル幅、実HTTP/DB、正式undo/記録権/空キュー/過去修正/プレビューAPIとの接続は未実施。内側sandboxのローカルbind制限があるため、実ブラウザ補完は主担当のホスト検証へ残す。実画面HTTP/DBの証跡を先方の着手前条件へ追加しない。次ステップ、コミット、push、PR、外部連絡は実施していない。

主担当の確定前検査で、再mount時に旧プレビューが再一致する点、同内容の新参照で下書きが消える点、利用者向け実装用語を検出し、同ステップで是正した。画面インスタンス識別子を提供プレビューの照合に追加し、生成不能時はプレビューだけを封鎖する。同内容は保持、条件変更時は消去理由を表示。関連Vitest94件、型検査・ESLint・Prettier・diff検査が成功（/tmp/uf8-corrections-selfcheck.log）。正式取消/訂正API・保存・送信は未接続、成功扱いなし。

### ステップ4の実行枝

48d22f78の取消/訂正入力を継承し、feature/uf8-game-substitutionsで承認済みステップ4のみ実行する。実行枝のbranchだけ更新、承認・査読履歴・9ステップ本文は保持。親のレビュー是正は追随する。

## ステップ4 交代・タイブレークの表示下書き（独立枝）

`feature/uf8-game-substitutions`で`GameScreenSubstitutions.vue`とUI専用のraw下書き・供給要求型・Vitestを`GameScreen*`内に追加し、既存`GameScreen.vue`へ統合した。正式wire DTO、実Port、計算核は追加していない。投手/代打/代走/守備変更について、供給された交代前後の選手・守備位置/DH・打順等の候補と質問だけを表示し、その場登録を別の入力方法として保持する。タイブレークの走者配置・先頭打者・回、過去の交代履歴1ページと人/回/時点の訂正質問を表示する。未選択は`null`、候補の自動選択なし。必須性は供給質問の明示値だけを読み、欠落・未知値・未検証を検証済みと扱わない。9ポジション、打順、人・投手・打者帰属、記録権、終了条件の判定は画面で作っていない。

過去交代の下流帰属プレビューは提供されたpending/failed/conflict/readyと差分行だけを表示する。文脈・操作・対象・下書き世代・画面インスタンスの照合に失敗した旧応答、必須入力が空のready応答、表示形式が不正な応答は表示しない。同内容の新参照では下書きを保持し、実文脈・供給要求の変更時には対象フォームの下書きを破棄して理由を表示する。終了条件ロックと既存undo対象の提供状態を合わせて説明し、供給状態が食い違う場合は可否未確認とする。通常交代、回配置、過去訂正、ページ送りを含む実操作は常にdisabledで、直接click dispatchでも通信・保存・送信・queue追加・成功表示はしない。

実測: 関連Vitest 7ファイル123件成功（新規`GameScreenSubstitutions.spec.ts`、既存GameScreen/過去修正/観測/停止/確定ゲート/狭幅）。4対象ファイルのESLint・Prettier check、`pnpm exec vue-tsc --noEmit`、`git diff --check`成功。DOMでは4交代種別、候補・DH・その場登録・未選択、タイブレーク3組、過去訂正4状態と旧応答拒否、同内容保持/実変更消去、未知/未提供値、終了ロック/undo整合、Vue自動escape、質問label/legend、375/320px向け縦積み・長い日本語の折返し指定、全実操作直接dispatchでfetch 0を確認した。

frontend全件試験、実ブラウザの375/320pxピクセル幅、実HTTP/DB結合はこの枝では未実施。主担当が統合後に補完する。正式な交代/登録/配置/検証/タイブレーク/過去交代訂正/下流再計算/終了条件の公開契約と提供SHAは未提供として実接続を封鎖したまま。これらの未提供を544/545の着手前結合試験条件にはしない。ステップ5以降、コミット、push、PR、外部連絡は実施していない。

### ステップ4確定前の主担当検査是正

主担当が、子部品の`getDrafts`だけでは画面外の提供側へ`uiInstanceId`/`draftId`を渡せず、同じ下書きに対応する検証結果・プレビューを返せない公開境界欠落を検出した。同ステップで子のUI専用`draft-change`を`GameScreen`の公開`substitution-draft-change`へ中継した。通常交代・タイブレーク・過去訂正の各入力/未選択への消去と実文脈・要求変更で、識別子と回答を含む独立した不変スナップショットを通知する。供給要求がある初期表示でも通知する。検証結果/プレビューpropの更新だけでは再通知しない。通知は保存/送信/交代確定/実イベントではない。試験は子の`defineExpose`を使わず、親の公開emitから識別子を取得して検証・プレビューを返す形にした。

未取得と明示pendingを別文言にした。通常交代の質問がゼロなら提供側の`valid`でも確認済みと表示せず、過去訂正の`ready.rows`が欠落・空・不正、または状態が未知の場合も取得済みと表示しない。終了ロックの取消対象は、現在の画面文脈と`undoOffer.contextKey`が実際に一致したときだけ「対象あり/なし」と説明する。親ステップ3で`UndoOffer`型と`GameScreen.correctionContextKey`照合を是正中なので、この枝に型変更をコピーせず、文脈キーが無い現行型では対象未確認へ安全縮退する。親の通常merge後に型・表示を追随する。利用者向けの「実操作」「接続」「下流帰属」「試合文脈」は平易な日本語へ変更した。

是正後実測: 関連Vitest **7ファイル125件成功**。`pnpm exec vue-tsc --noEmit`、対象4ファイルのESLint・Prettier check、`git diff --check`成功。公開emitの毎変更/消去/文脈変更、不変性、古い応答拒否、未取得/pending、不正ready/未知状態、質問ゼロ、文脈付き取消表示を確認。全実操作はdisabledのまま直接click dispatchでfetch 0・Storage保存0・保存/送信/確定イベント0。frontend全件・実ブラウザ・実HTTP/DBは主担当の統合後補完として未実施。これは新レビューではなく主担当検査の是正であり、ステップ4のレビュー回数は**0**のまま。ステップ5以降、コミット、push、外部連絡は行っていない。

### ステップ5の実行枝

交代入力32c4085aを継承し、feature/uf8-game-live-displayで承認済みステップ5を実行する。計画frontmatterの実行枝のみ変更し承認/査読履歴/本文は保持。親のレビュー是正は追随する。

## ステップ5 回・打順・終了・鮮度・FR-020〜023の表示

`feature/uf8-game-live-display`で`GameScreenLiveDisplayTypes.ts`にUI専用表示契約、`GameScreenLiveDisplay.vue`に専用表示部品、`GameScreenLiveDisplay.spec.ts`に隔離fixture試験を追加し、`GameScreen.vue`にはpropと部品統合だけを加えた。正式Port、生成formatter、計算、通信、保存、終了宣言、再開処理は追加していない。投影のscope・文脈キーと選手IDが一致した提供値だけを描画し、代打・投手交代の選手選択が変わった時点で旧成績を外す。既存の打者・投手見出しも新選手名へ切り替える。読取失敗、未取得、データなし、当日暫定、シーズン最終取得時刻とオフラインを提供状態のまま表示する。閲覧端末の最終反映時刻、入力端末オフラインも提供値以外から推測しない。

FR-020は両チームの提供済み開始回を順序・件数そのままで回別カードへ折り返し、X・空欄・0・未取得を別表示し、提供済み合計/H/E/K/Bを表示する。FR-021は現投手の当日8欄とシーズン5欄、FR-022は現在/次打者の当日9欄・シーズン3欄・打席履歴7欄、FR-023は当日球種ごとの割合と球数を表示する。値や打席結果名は提供済み表示文字列をそのままVue補間で描画し、合算・率・回切替・終了判定・打順推定・打席履歴からの再集計をしない。回切替、終了宣言、試合追記再開の入口はdisabled。同内容の送信再開は既存の別入口のままdisabled。終了検知、宣言未同期、宣言同期済み、追記再開、再終了未同期/同期済みを別表示とし、未同期を試合完了へ読み替えない。

Vitestの#153**候補fixture**で5セル`X / 空欄 / 3 / 空欄 / 0`を順に確認し、E02の宣言後prompt=false、E09のロック中undo可・交代不可、E10の追記再開後prompt=falseと再終了後ロックを表示契約として確認した。正式#153受理・独立oracle・GAP-05実製品比較・FR-012原子性・全試合完遂の証跡には数えない。別fixtureで12回全表示、両チーム全合計、投手/打者全欄と7列、未取得/読取失敗/0件、現在/次打者と代打/投手交代の初球前切替、遅延した旧選手・旧文脈・別scope応答の排除、Vue自動escapeを確認した。断中fixtureは**提供側が新しい当日投影値を渡した場合**のスコア4・投球82・安打3・球種61%/49球への更新を確認し、古い値への暫定ラベル追加だけを合格としない。これはfixture更新試験であり、共有計算核からの実断中追従合格ではない。シーズンの最終取得12:34+オフライン、初登場未prefetchの未取得、データなしを分けた。

実測: 関連Vitestは`GameScreenLiveDisplay.spec.ts`、`GameScreen.spec.ts`、`GameScreenNarrowWidth.spec.ts`、`GameScreenSubstitutions.spec.ts`、`GameScreenStopDisplay.spec.ts`の**5ファイル67件成功**。最終差分の`GameScreen*.spec.ts`は**16ファイル256件成功**。`pnpm exec vue-tsc --noEmit`、変更4ファイルのESLint/Prettier check、`git diff --check`成功。375/320はjsdomの幅設定下で長文・回別折返しclassと直接dispatch時のfetch/Storage保存/実操作emit 0を確認した構造試験で、実ブラウザのピクセル幅測定ではない。同内容の新参照のlive propsを再供給しても既存投球下書きが残る試験が成功。frontend全件・実ブラウザ・実HTTP/DBは主担当補完へ残す。

不足と接続条件: 544/545の正式投影・生成formatterの公開型/SHA、#153正式セル/独立oracle、U-X1 T3〜T6の当日/シーズン成績とページ付き履歴、断中の共有計算核更新、シーズンprefetch/最終取得時刻、NFR-006の入力/閲覧2端末の正式鮮度契約、終了宣言/再開/再終了の正式提供状態は未受領。これらを仮Portや画面内計算で補っていない。M-T1/M-T2の共同実測、GAP-05、原子性、1試合完遂、全40分析製品の完成は未達。ステップ6以降、コミット、push、外部連絡は行っていない。

### ステップ5確定前の主担当確認への同範囲補完

`InningCell.kind=blank`は可視`textContent`を空文字に保ち、セルの`aria-label`だけで「空欄」と説明するよう是正した。`text`セルは提供文字列をそのまま表示し、X/0/未取得と分離した。DOMで#153**候補fixture**の5セル`X / '' / 3 / '' / 0`、両blankの`textContent=''`と`aria-label='空欄'`、12回目のblank、合計の提供空文字/0の保持を確認した。候補fixtureを正式セル型・独立oracle・GAP-05の受理へ昇格していない。

描画に必要なUI形だけを`GameScreenLiveDisplayShape.ts`で検査する。得点表の2チーム、開始回、各2セル、成績欄、打席履歴、球種列、終了状態・boolean、正式鮮度の文字列/booleanを対象にし、`ready`でもnull・欠損・型不一致・未知終了状態は未取得へ倒す。配列は各own添字を確認し、追加の非添字keyを穴の代わりに数えない。壊れた得点表/履歴/球種のnull要素と疎配列、異常な表示値をDOMへ渡しても例外や取得済み表示にせず、別の有効な成績・得点と既存の送信停止UIを維持する試験を追加した。選手用供給の`playerId`欠落、identityの対象ID欠落をglobal表示と誤認せず、その人物だけ未取得にする。旧選手応答のscope・文脈・ID照合は維持した。これは表示形の検査で、正式wire validatorや得点・アウト・成績・終了条件の計算ではない。

最終実測: `pnpm exec vitest run src/screens/GameScreen*.spec.ts`は**16ファイル260件成功**。`pnpm exec vue-tsc --noEmit`、frontend全体の`pnpm exec eslint .`、`pnpm exec prettier --check .`、`git diff --check`成功。壊れた供給時にもdisabledボタンへの直接dispatchでfetch 0・実保存/送信emit 0を確認した。frontend全件、実ブラウザ、正式提供型/生成formatterとの結合、レビューは主担当補完。ステップ6以降、コミット、push、他枝編集、外部連絡は行っていない。

### ステップ6の実行枝

記録中表示0a8a8002を継承し、feature/uf8-game-entryで承認済みステップ6のみ実行する。実行枝metadataだけ更新し計画本文/承認/レビュー履歴は保持。App.vueの最小追補は未承認なので適用せず、承認済みrouter/Entry範囲で進める。親是正は後で追随する。

## ステップ6 試合一覧・開始/スタメン・再開入口と記録route

`feature/uf8-game-entry`で、`GameScreenEntry*`と`router*`だけに`/games`・`/games/:gameId/record`を追加した。両routeは既存の`requiresAuth`ガードを通し、`getActivePinia`/共有`pinia`、hydration待機、`ensureSessionVerified`、`authEpoch`、tenant一致の条件を維持する。認証前の`redirect`は`GameScreenEntryNavigation`で`/team`・`/games`・canonical UUIDの記録pathnameだけへ制限し、query/hash、外部URL、二重slash、不正IDは`/team`へ倒す。`App.vue`は未承認の追補を適用していないため、ログイン完了後の試合route復帰と通常ヘッダーからの試合導線は**未達**。router側の後追い再遷移は追加していない。

製品routeではU-G1/U-G2の実一覧・詳細・スタメン・規則・権利・下書き復元が未提供であることを表示し、開始/スタメン設定/再開/記録/保存/送信を全条件で封鎖する。`GameScreen`はprops未供給で全機能を未取得表示にし、既存の確定封鎖を保つ。新規HTTP、仮Port、計算、Web Locks・IDB判定や永続化処理はない。表示用の`EntrySupply`はtenant、認証世代、経路、ページ要求キーで文脈を照合し、隔離fixtureで1ページの項目・前後ページキー・開始候補/スタメン/規則/権利/既存状態・再開詳細を供給する。異tenant項目、不正ID、壊れたページ、旧応答は取得済み成功にしない。他tenantの存在と内部原因は表示しない。ページ送りは供給側への表示要求イベントだけで、実取得や全件集計はしない。

NFR-020の観測可能な前提1/5/6は提供された成立/不成立/不明をそのまま受け、単独/複合不足の全番号と内容、開始不可、既存キュー件数/保持、閲覧可能を表示する。未知を成立にしない。前提5のサイトストレージ不可とpersist要求だけの拒否を分け、後者は警告と前提上の継続可能性を表示するが、製品の実開始は未接続のため封鎖したまま。キューを読み書き・消去しない。

隔離DOM試験で、実routeの未取得、保護境界と再検証失敗/異tenant/認証世代変更、正規/不正IDと安全な戻り先、1ページのみの表示と前後要求、正常/拒否/通信失敗/遅延、旧文脈遮断、前提1/5/6単独・複合、persist区別、全実操作の直接dispatchでもfetch/POST 0、Vue escape、375/320pxの縦積み・折返し構造を確認した。jsdomは実ピクセル幅を測れない。最終実測は`pnpm exec vitest run src/screens/GameScreen*.spec.ts src/router.spec.ts`で**18ファイル320件成功**。`pnpm exec vue-tsc --noEmit`、対象`GameScreenEntry*`/`router.ts`のESLint・Prettier check、`git diff --check`成功。実ブラウザ375/320pxとfrontend全件は主担当補完。正式API/実HTTP・DB接続、ログイン後復帰/通常ナビゲーション、記録権取得、実開始/再開/保存/送信、1試合完遂は未達。ステップ7以降、コミット、push、外部連絡は行っていない。

### ステップ6確定前の主担当検査への同範囲補完

`GameScreenEntryRecord`が同一instanceで別試合routeや認証切替後も内側`GameScreen`を再利用し、未供給の`eventIdentity`/観測文脈では球速などの未保存下書きを消せない欠陥を是正した。現在の`authEpoch`、`teamId`、route pathname、gameIdを表示instanceのキーにし、いずれかが変われば実`GameScreen`を作り直す。同じscopeへの同内容新参照ではinstanceと下書きを保持する。実球速入力で試合route変更、tenantと認証世代の個別変更、再検証中とtenant切替を試験し、旧入力・旧metadata・旧未送信件数が残らないことを確認した。画面文言は未保存の入力欄と矛盾しないよう「記録の確定・保存・送信はできません」とした。

一覧の`selectedGameId`と`requestedPageKey`は認証世代/tenant/pathの実変更時だけ消去する。同じscopeへの同内容新参照では選択とページ要求を保持する。旧tenantで次ページを要求したあと新tenantの初期`requestKey=null`ページを表示できること、同一instanceで経路を往復した場合に旧選択を戻さないことを確認した。ページ移動の意味や実APIは追加していない。`existingStateLabel`は文字列かつown既知キーに限り、`constructor`/`__proto__`/`toString`やnullを未取得にする。候補・ページ・詳細のnull、疎配列、未知状態、不正datumも取得済みへ採用せず、別の閲覧表示と`GameScreen`の確定封鎖を維持した。既存のdense検査を再利用し、計算/通信/保存Portは追加していない。

NFR-020前提1/5/6の全不足列挙、persist要求のみ拒否とサイトストレージ不可の区別、未送信キュー保持の文言は**表示上の候補**であり、実Web Locks/IDB・再起動を通したキュー耐久の証拠ではない。実開始/再開/確定/保存/送信は引き続き封鎖し、直接dispatchでもHTTP 0。最終実測は`pnpm exec vitest run src/screens/GameScreen*.spec.ts src/router.spec.ts`で**18ファイル334件成功**、`pnpm exec vue-tsc --noEmit`、frontend全体の`pnpm exec eslint .`と`pnpm exec prettier --check .`、`git diff --check`成功。実ブラウザ/フロントエンド全件試験と既定レビューは主担当補完。正式API未提供、`App.vue`追補未承認による通常ナビゲーション/ログイン復帰未達は維持する。次ステップ、コミット、push、外部連絡は行っていない。

### ステップ7候補の実行枝

入口142003cbを継承し、feature/uf8-game-browser-candidateで承認済みステップ7の候補作成のみ実行する。正式7.7受理・CI/凍結基準の有効化は行わない。計画branchだけ変更し本文/承認/回数は保持。6〜7は同一最小PRとしてentry枝へ通常mergeして提出するため、コードPR査読枠は両ステップを通じた同一枠として管理し、ステップでリセットしない。

## ステップ7 Playwright・CI/凍結候補（正式受理前）

`GameScreen.playwright.config.ts`、`GameScreen.e2e.ts`、`GameScreenE2eSupport.ts/.py`、`GameScreen.real.e2e.ts`と候補境界のVitestを追加した。親が先に加えた`@playwright/test` 1.61.0 のpackage/lock変更は保全し、`test:browser`/`test:browser:real`を追加した。必須封鎖経路は実Vue Appのroute、実 `create_app` / auth/login/session、既存`provisioned_product_catalog`による`--pull=never`の使い捨てPostgreSQL・製品migration/認可DDL・実アプリロールを使う。自前のランダムな認証主体・署名鍵は0700一時ディレクトリとプロセス環境だけに置き、標準出力・artifactへ出さない。製品Portのmock登録、schema/計算の複製、共有DB/role変更、製品側からTestSupportのimportはない。Viteの`envDir:false`と一時HTTPS証明書を使い、Secure Cookieを実ブラウザで検査する設計にした。

封鎖projectは認証なし/失効、正規・不正・未知ID、試合一覧/記録入口の開始・再開・確定disabled、reload、2タブ、auth通信失敗/遅延、tenant切替、375/320幅を対象とする。NFR-020前提1/5/6の単独・複合は既存`GameScreenEntry.spec.ts`の隔離表示fixtureで検査し、実Appからの正式環境供給と混同しない。別`real-game` projectは正式driver未接続の間、SHA/IDの環境文字列があっても明示失敗する。実ゲームfixtureとゲーム作成Portが未提供なので、1試合完遂の合格は主張しない。

CI候補は既存必須frontend jobの後段へ同じ`test:browser`経路を足す。逆依存を機械確認した結果、CIはテナント境界9資産中8資産の外部凍結対象だった。計画で明示されたbase/census以外の6資産にも識別値・投影snapshot更新が必要と判明した。`docs/features/uf8-full-game-followup/step7-candidate/`にCI・影響8資産・比較corpus manifestの全前後ファイル、完全patch、メタデータ、新snapshot9件を保存し、実資産は変更していない。旧履歴23件・旧署名はbefore/after共通prefixとして不変、新1件の人間欄とacceptance IDは空。ソースGit baseは`8e4698f6dc254439b7d5e0c273cc2aef70cda657`、Draft6〜7の単一PR受理単位は未割当。CI前後SHAは`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`→`0206d208474482e4e50dbb6993b9771a7ae86282a4d8e5e2598a7a52ec863718`、corpus入力digestは`b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ce`→`21334bcd53f38962c50a5c968a48a2465ca526e6673e2596b3ba8457898cf835`。他の全識別子、外部hash、射影digest、対象集合は同候補の`metadata.json`に実値を置いた。

初回実測: `pnpm exec playwright test --config src/screens/GameScreen.playwright.config.ts --list`は当時のsealed-ui **5件**、切替式の`real-game --list`は別project **1件**を列挙。frontend全体のVitestは**89ファイル1708件成功**（候補試験追加後）、関連候補・入口のVitestは2ファイル52件成功。`pnpm exec vue-tsc --noEmit`、全ESLint/Prettier、`pnpm exec depcruise src --validate`、`pnpm run build`（build closure conforming）、Python支援/生成器のRuffは成功。候補patchは隔離一時ディレクトリで`git apply --check`成功・適用後の全after bytesと新snapshot bytes一致。既存`validate_snapshot_archive`では前179・後188snapshot、孤児33件は増加せず、新9件の参照漏れなし。候補afterの隔離ツリーで既存`runner.validate_corpus_inputs`成功。`git diff --check`成功。候補を使った正式7.7受理検査は人間欄が空のため未実施・不合格予定であり、候補試験と分ける。

追加downloadは内側sandboxで試みていない。正式ゲームの公開SHAと実入力、前提1/5/6の実供給、未宣言6資産を含む計画追補、PR受理単位と人間本人の7.7記録、CI/凍結実ファイルへの適用は未達。M-T1/M-T2、GAP-05、FR-012原子性、1試合完遂は未達のまま。親ステップ5の是正はこの枝へ先取りせず、主担当の通常mergeに委ねる。次ステップ、コミット、push、外部連絡は行っていない。

### ステップ7確定前の同ステップ補完（2026-10-21）

主担当ホストの封鎖E2E初回はPython import経路不足でsetup失敗、2回目は正しい`PYTHONPATH`で診断して既存`db_fixtures.verify_connection_identities` autouseの`PITCHLOG_TEST_ADMIN_DSN`不足と確定した。Docker/Port不足とは記録しない。初回生成されたrepo内Playwright出力は主担当が`~/.cache/pitchlog-523/uf8-e2e-initial-output-20261021`へ移動保全済み。`outputDir`は自分で生成する0700一時ディレクトリへ移し、ignore規則は追加していない。

是正: Python driverはpytest開始前に既存`disposable_postgres_cluster` factoryから自分のouterクラスタを作り、実管理DSNと、既存fixtureが専用クラスタで作成・破棄する実被検査ロールのDSNを供給する。既存`requires_db` marker、autouse、pytest設定を維持し、接続ID検査の後に既存`provisioned_product_catalog`が別のinner製品クラスタを用意する。外部`PITCHLOG_*` DSNは継承・信頼せず、backendのlocked `.venv/bin/python`でdriverを実行する。runtime資格情報とTLS keyは自分の0700領域内の0600ファイルに置き、標準出力・trace・video・screenshotへ出さない。両クラスタは既存fixtureとfactoryの自前後始末だけで破棄する。`real-game`の旧検査は、任意のSHA/IDから匿名/login redirectと未取得text不在だけで成功し得たため撤去した。固定名`sealed-ui`/`real-game`の二projectを静的定義し、`test:browser`とCI候補は`--project sealed-ui`を明示、realと全projectは正式Port・完全シナリオdriver未接続中に必ず失敗する。環境文字列だけを供給証拠へ数えない。

是正後の実測: 関連Vitest **2ファイル53件成功**、`vue-tsc --noEmit`、全ESLint/Prettier、dependency-cruiser **125 modules/256 dependencies**、build closure conforming、root Ruff、Python helperの明示ty・compile、`git diff --check`成功。Playwright `--list`は両project計6件、`pnpm run test:browser --list`はsealed-ui 5件のみ。backend既定pytest設定でhelper 1件をcollectし、未知marker警告はなく、既にimport済みの`db_fixtures`のassert rewrite警告だけが出た。内側sandboxの`pnpm run test:browser`はsetupで失敗し、診断で共有uv cacheの書込み不可を確認したためlocked `.venv/bin/python`へ切替えた。切替後もsetup失敗するが、同Pythonの秘匿診断は`ADMIN_DSN`欠落やimport不足ではなく専用Docker `run`到達を示し、`docker info`はDocker socket権限拒否を返した。実ブラウザ・実Auth HTTP・専用DBの成功は**未実測**で、主担当ホストの再実行を待つ。

主担当による候補patchの隔離`git apply --check`・実適用・after全bytes・9 snapshot SHA一致は確認済み。patch SHA-256は`4d0f254c91d124a553a3416cdf95c1a6cd994eb81ce67b0b80d26319f37953fc`のまま。`test:browser` scriptの封鎖project明示化はCI候補の`pnpm run test:browser`の意味と一致し、patchを再生成していない。未宣言6資産の計画追補案`step7-scope-extension.md`（SHA-256 `899abea1cdd8e7e3ea069a65c8b8ff79eaf0fdfe40ce2687ccf2559011200f59`）は主担当が人間へ照会中で、編集・承認記録・実資産適用はしていない。6〜7コードPR査読は**0回**で、計画・親・ステップ5の枠を流用しない。正式7.7受理・CI接続・1試合完遂は未達のまま、この候補是正で停止する。

### ステップ7候補の実host封鎖E2E再測定と是正（同ステップ）

主担当ホストの `pnpm run test:browser` 実測（`/tmp/uf8-entry-real-e2e-bootstrap.log`）は、実 Auth HTTP・HTTPS・自分専用 outer/inner PostgreSQL の起動に成功し、sealed-ui **5件中3成功・2失敗、25.3秒**。これは実ゲームPortや1試合完遂の証拠ではない。失敗1はlogoutの素のPOSTが403で、製品 `request_presentation.py` の `X-Pitchlog-Request: 1` と厳密なOrigin許可が欠けていた。失敗2はsession応答遅延後、期待した `/games` ではなく `/login` の「認証状態を確認できません。状態を再確認するか、ログアウトしてやり直してください。」へ着地した。旧Cookieが更新され得る応答の認証相関・不確実性と自動再送禁止を尊重する。

是正では、Nodeがbackend起動前に自分用freeportを選び、Viteを `strictPort:true` で同じloopbackポートへbindする。衝突なら失敗として閉じる。自分の子プロセス環境で渡す `https://127.0.0.1:<port>` をPython driverで形式・範囲検証し、外部 `PITCHLOG_*` を除去した後の `PITCHLOG_ALLOWED_ORIGINS` にその1件だけ設定する。製品CSRF判定は変更しない。logout要求に実custom headerを付け、200応答・保存旧Cookie再提示後の実session 401・保護routeから/loginへの拒否を要求する。login helperは実 `/team-records` GETの200・tenant match証跡・完了と画面の読み込み完了を待つ。遅延テストはその後 `/games` のsession GETを保持してpending中の開始封鎖を確認し、実GET 200後に `/games` のpositive封鎖表示を要求する。既存仕様どおり不確実性へ遷移した場合だけ、画面の「状態を再確認」を明示操作して別の実session GET 200とteam GET成功を確認し、最後に `/games` へ戻す。認証状態注入・自動資格情報再送・旧Cookie復旧・どの画面でも成功という条件緩和はない。失敗時の自動画面snapshotへ使い捨て認証主体を残さないよう、自分のbrowser pageを試験後に閉じる。

この修正後の実host sealed-ui 合否は**主担当の再実行待ち**。内側sandboxのbind/Docker制約を成功値へ転記しない。固定 `real-game` は正式Port・1試合driver未接続のためSHA/ID文字列に関係なく失敗するまま。候補patch・人間欄・実CI・正式凍結資産・scope追補文書は変更しない。6〜7コードPR査読は引き続き**0回**で、この同ステップ検査是正は回数消費に数えない。

内側での是正後検査は関連Vitest **2ファイル53件成功**、`vue-tsc --noEmit`、全ESLint/Prettier、dependency-cruiser **126 modules/257 dependencies**、`pnpm run build` のclosure conforming、root Ruff、Python helperの明示ty・compile、`git diff --check`、sealed/real各projectの`--list`に成功。非loopback OriginのPython driver入力はDocker起動前に拒否されることを確認した。候補patch SHA-256 `4d0f254c91d124a553a3416cdf95c1a6cd994eb81ce67b0b80d26319f37953fc` と未回答追補SHA-256 `899abea1cdd8e7e3ea069a65c8b8ff79eaf0fdfe40ce2687ccf2559011200f59` は保持した。

### ステップ7候補の主担当host2/host3検査への同ステップ是正

主担当ホストの `/tmp/uf8-entry-real-e2e-host2.log` は変更途中のsourceでsealed-ui **3成功・2失敗、36.9秒**。匿名 `/games` の初回表示が空のまま5秒経過した失敗と、ログイン補助の `/team` 待機失敗だった。最終sourceでの `/tmp/uf8-entry-real-e2e-host3.log` も **3成功・2失敗、30.5秒**。正常route、未知/不正ID・複数タブ・認証通信失敗、tenant変更の3件が成功し、匿名/失効と遅延の2件は共にログイン補助の `/team` 5秒待機で失敗した。先に作成したteam一覧GETの待機が失敗後に未処理rejectionを出していた。これらのログにはPOST loginや相関session GETの成否がなく、初期Vite compile/並行host負荷と認証相関のどちらが原因か断定できない。並行root pytest 8 workerのCPU使用は事実だが、timeoutだけを伸ばす根拠にはしない。実logout 200と旧Cookie再提示後401は未測定。

是正したログイン補助は、実LoginScreenの初回 `ensureSessionVerified()` が終わった `form[aria-busy=false]` と入力可能状態を確認してから1回だけ明示loginを押す。実POST `/api/auth/login` 200と自分のfixture tenant、続く実GET `/api/auth/session` の応答とtenantを先に確認し、team画面又は製品の正確な認証不確実表示を待つ。不確実表示かつ再確認ボタンが利用可能なときだけ、資格情報の自動再送なしでUI上の「状態を再確認」を押し、別の実session GET 200・tenant一致を要求する。最終team一覧GET 200・tenant照合・読取完了、画面読み込み完了、Secure/HttpOnly Cookieとsecure contextをすべて要求する。失敗時は段階、method、IDを伏せqueryを除いたpathname、status、経過ms、固定UI状態だけを出し、資格情報・Cookie・nonce・本文・header値を出さない。匿名初回表示も同じ安全な通信観測を使う。team一覧等の全先行待機は終了時rejectionを捕捉する。遅延testの保留GETと明示再確認GETはtenant一致を追加確認し、5件のシナリオと成功条件は維持した。`App.vue`・auth製品・backend製品の変更はない。

この補完後に内側で実測したのは関連Vitest **2ファイル53件成功**、`pnpm exec vue-tsc --noEmit`、frontend全ESLint/Prettier、dependency-cruiser **126 modules/257 dependencies**、`pnpm run build` とclosure conforming、root Ruff、`git diff --check`、封鎖projectの `pnpm run test:browser --list` **5件**。内側ではDocker/socketとbindに制約があるため実Auth HTTP・own DB・browser 5件を再実行しておらず、修正後のhost合否は主担当の再測定待ち。host実測値は3/5のまま、logout 200/旧Cookie 401、正式ゲームPort、1試合完遂はいずれも未達。候補patch SHA-256 `4d0f254c91d124a553a3416cdf95c1a6cd994eb81ce67b0b80d26319f37953fc` と未回答scope追補SHA-256 `899abea1cdd8e7e3ea069a65c8b8ff79eaf0fdfe40ce2687ccf2559011200f59` は不変。実CI・正式資産・人間受理欄は未変更、6〜7コードPR査読は**0回**。次ステップ、commit、push、外部連絡は行わず、この同ステップ候補是正で停止する。


### 2026-10-21 ステップ7候補の保全・結合レビュー準備

- Python import/outer ADMIN DSNの起動不備を是正し、実HTTPS画面・実Auth HTTP・専用outer/inner PostgreSQL起動を主担当hostで実測。既存autouse・製品create_app・実認証を維持し、仮Port/計算/HTTP codec/ACK/キューを追加していない。
- 初回bootstrap試行は5件中3成功/2失敗（logoutのCSRF提示と遅延時認証確認）。必須X-Pitchlog-Requestと自分のHTTPS Originだけの許可、初回確認とPOST/GET/tenant一致・一覧完了、必要時の明示再確認を試験側で是正。製品auth/App/既存チェック器は未変更。
- 変更途上host2/host4はsource変更と重なったので最終検査証跡にはしない。host4はhash照合でもE2E試験ファイル変更を検出した。host3は3成功/2失敗。変更終了後のhost5はsource4ファイルSHA不変で1成功/4失敗。最終ソースの全成功とは記録しない。
- 安全な一時probeでChromiumが配信中にnet::ERR_NETWORK_CHANGEDを返すことを確認（method/path/固定networkエラーのみ、資格情報・Cookie・nonce・応答本文を出力しない）。並行する自分専用の全件DB検査のコンテナ生成/撤去との関係を切り分け、同検査完了後に実ブラウザを直列実行する。retry丸め・timeout拡張・network検知無効化・skipは行わない。DB全件検査とブラウザ全成功はそれぞれ結果回収待ち。
- real-game projectはdummy SHA/IDを与えても未接続driverの明示失敗となった（実行1件/失敗1件）。これは期待どおりの未達検出で、実1試合成功には数えない。
- 関連Vitest53件、型・全ESLint/Prettier・dependency-cruiser・build・root Ruff・明示Python ty/compileは成功。候補patch SHA4d0f254c91d124a553a3416cdf95c1a6cd994eb81ce67b0b80d26319f37953fcと追補提案SHA899abea1cdd8e7e3ea069a65c8b8ff79eaf0fdfe40ce2687ccf2559011200f59は不変。実CI/正式資産の差分は0、新しい受理・署名欄は空。App.vueと追加6資産の追補は未承認のまま。
- 本コミットは7の候補保全であり、7.7正式受理・ステップ7完了ではない。6〜7を同じPR/同じ既定レビュー枠で提出する準備を続ける。既承認原本935bac90、査読3回13件全採用/最終P0限定/最終反映未再査読、親PR群の既存回数を保持する。
