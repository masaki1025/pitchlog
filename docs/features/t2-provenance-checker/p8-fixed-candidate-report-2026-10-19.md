# P-8候補の固定版・検証・正式ゲート

更新: 是正後の追加レビュー第2回は60825a0fで0/0/0。push/Draft PR/送付はPO許可済み。以下の未再レビュー/未許可は当時の記録として保持する。[最新の受渡し・ゲート](handoff-and-gates-2026-10-19.md)を参照。545の製品実行証跡は実装後DoDであり、新たな着手条件ではない。

候補への採用5件反映を実装し、レビュー指摘を是正した。正式契約・正本・署名は変更していない。

## 固定点と履歴

- レビュー対象HEAD: `2dce3b32b54f3b4774cb8d985c3ef6c7345f74a7`。最新develop `5bb1ff89306712c1de61c3a0152141c8f771b3a0`を通常マージし、先行履歴を保持。
- レビュー基準: `76037523`以降の本担当候補差分（上流変更を除く）。差分SHA-256=`c95ab7aad1a3d96f063e704d2b56e311d24a366f417192d2c4c225fca5d8ddef`。正確な抽出パスはworklog。
- 元backup ref=`refs/backup/t2-provenance-checker-handoff`、OID=`bced96e84d90683c096fefff8e76fd60a81d896e`を保持。所有移管・POによる受領は成立済み。
- 基本コードレビュー2回: `0ed529f6`で0/1/0、限定是正で0/0/0。計画レビュー2回、確定ゲート0回も保持。
- 追加独立レビューはPO許可の1回のみ。結果 **P0=0/P1=1/P2=0**。開始済み等の表示入力と典拠分岐の変更を検出できないP1を採用し、全入力/典拠を固定証拠へ結合した。正常5件に加え6種の変異を拒否する回帰試験を追加。是正後の独立再レビューは未実施であり、0/0/0と書き換えない。レビュー担当は実装未関与のCodex subagent、正確な実行モデルIDは未取得。P-6には数えない。

## 検証

- 最終コード/候補HEAD: `5a9e37bd263787106f08bb05224f01333e79ffc3`（追加レビューP1是正）。
- レビュー対象HEAD `2dce3b32` の全harness: **29,886 passed / 1 failed / 2 skipped、802.67秒**。失敗は旧人間署名と現物T2 digestの不一致だけ。ログ `/tmp/t2-p8-full-harness-2dce3b32.log`。
- 是正後HEAD相当の関連5ファイル: **707 passed、39.90秒**。ログ `/tmp/t2-p8-review-fix-related.log`。この是正後の全harness再実行・独立再レビューは未実施。
- ruff全体/ty/docs-status/diff-check合格。候補CLIは相関21/decision5/lifecycle3/context5/得点観測2/操作42/表示比較5を実行し、製品比較/正式被覆はfalse。TS loader18 passed（是正前。是正はTS loaderを変更しない）。
- 候補bundle SHA-256: `ec49365e193b91d6224d7f8f586e2760f03525d071d5793adf117d3ce600e58f`。
- 候補schema SHA-256: `057bb8effeace6425f50de8223f4202bff625503444c3a46e5aa1c5b4cc417a4`。
- 境界fixture SHA-256: `63ee2ae009444654320d61981a334182e81bdabae80528df317c3bed1bd40490`。

検査の除外・署名改変・予算緩和なし。専用一時DBのみ使用し、終了時に本担当containerを停止/除去。共有DB/ロール/秘密情報/他担当作業へ変更なし。
旧10失敗の原因・担当は[harness-failure-disposition-2026-10-18.md](harness-failure-disposition-2026-10-18.md)。9件は承認済みdevelop取込み/専用検証環境で解消、残る1件は実施者の再署名待ち。

## P-8の個別判定

| 項目 | 候補の到達点 | 正式/製品/P-6で残るもの |
| --- | --- | --- |
| provenance | schema/検査器/両loader/fixture/予約値偽装拒否を実装・試験済み | 人間再署名/逐行確認・P-6受理。整備の最終完了は未 |
| E01 | 第3アウトのpost-play暫定とpost-turn完了を別receiptで検査 | 製品核で2時点を評価する対のcaseとadapter実接続 |
| E02 | 直前完了評価のdetected/lock/outcome保持、declared/gameEnded=true/prompt=falseを再生検査 | 正式行/全case/公開型反映、製品再起動・履歴再生証跡、P-6 |
| E03 | 既存S22の546→544分担を維持 | 実際の回答・担当受理未取得 |
| E04/E06 | 段配列逆順2件、設定2/成立1・0の候補具体入力 | 共有核の製品出力比較、全プレイ列到達性、正式被覆/P-6 |
| E05 | 同じ対象プレイの前後得点観測2件、scope/event/prefix一致と偽装拒否 | 544共有核投影/545認可adapterへの実接続、サヨナラ期待値の独立再計算 |
| E07 | B裁定の単一decision.xMarkを維持、5セルの候補契約/比較器 | 表示担当受領・独立oracle・製品表示関数比較。GAP-05 open |
| E08 | コールド/通常競合の5case内1件をcold-endとする候補、PO製品裁定のpatch | 正式分岐/展開/全case・P-6・再署名 |
| E09 | ロック中undo可/交代不可・undo後再評価の候補を保持 | T1操作/undo契約・製品受け口への正式反映。宣言後の権限は広げない |
| E10 | 明示phaseと認可済みreopen、lock=false/継続条件detected=true/prompt=true | 実製品入力/履歴投影とのrevision対応、全case/独立期待値 |
| E11 | A裁定どおり既存3行/102caseを維持、評価位置≠攻撃開始の限定patch | 正本確定と対象版のP-6照合。DeepSeek確認を再実施/転用しない |
| E12 | T2候補側の相関21件（拒否6/条件単独非拒否15）、schema/導出器/検査器 | 550追補40933555の統合/版調整、正式型/runner接続・製品保存試験/P-6 |
| E13 | FR-040非採用を既定にし、採用宣言時の正常入力も試験 | 製品manifestと実担当受理。未統合裁定を反映済みとしない |
| E14 | 既存7kind×6payloadタグを正常6/拒否36、未知型/fieldも拒否 | 正式入力型/製品正規化入口への反映、payload内部schema、P-6 |
| DRAW | requiredSet宣言でDRAW-01〜10が未被覆、05のみ別層case参照を実測 | gap_registerのGAP-04=resolved/136caseという記載と、条文別未被覆を混同せず、各条文の保存拒否/実行/表示caseを正式対応づける |
| XMARK-03 | 正式契約はblank 0行/0case、候補はblankセルを含む5件 | GAP-05の実受領と独立期待値/製品比較が成立するまで未完 |

現行要件の正は変更履歴2.15（D-14-m）。550の別内容の同版追補はorigin/developに未統合で、同番号のまま統合済みと記録しない。既存正式T2は8行/248case、正式検査はcases248/invalid12を維持。

## P-6と受領物

P-6の対象版は正式反映後に改めて固定する。対象は既存248caseの全入力projection（phase既定含む）、E11維持3行/102caseの根拠、追加競合/段数/順序case、宣言前保持/再開/第3アウト/undo再評価、対象プレイ前後得点、E12拒否/非拒否21件、E14正常/拒否とFR-040採否、DRAW条文別case、表示5セル以上の独立期待値と製品出力。作者の人工fixtureや今回コードレビューを独立期待値として署名しない。

具体物・公開型・供給責務とreceiverDoDは[candidates/adopted-boundaries-2026-10-19.md](candidates/adopted-boundaries-2026-10-19.md)。544にはscore観測/操作拒否/E12、545にはphase/保持評価参照/認可照合/lifecycle/decision/provenance・両loader、表示側には5セルfixture/比較型/比較器/blank変異試験を渡せる。candidateId=t2-p8-followup-v1/schemaVersion=1、対象commitと各digestを併記する。製品消費248case、全projection、runner/revision/CI、共有核投入、FR-040 manifest、担当実受領は未成立。担当への送信・返信は本セッションで未実施であり、準備済みを受理済みとしない。

## 残る正式ゲートと判断

1. 正本patchの7.6確定ゲート。E11/E07や5件の採用自体を再裁定せず、具体追随文と550追補の統合/版調整を対象とする。
2. 候補から正式契約/schema/descriptor/展開case/runnerへ反映する差分の固定と7.7。先行受理履歴を保持する。今回候補の許可を正式変更承認に代用しない。
3. 対象版・差分・逐行確認材料に対する実際の人間確認/再署名。旧provenanceのみのD1〜D4を規範行変更後に流用しない。未実施のP-6検証者署名は代記しない。
4. 正式版のP-6独立期待値受理と544/545/表示担当の実受領。製品検証・投入は別。
5. 本担当枝のpush/Draft PRは未許可。完成差分・検査結果を添えた一括判断対象。マージ・製品投入は行わない。

判定: **provenance技術是正済み/整備最終完了は未、T2のP-8全成立は未、545製品実装開始可能の判定は未成立**。

是正差分のbinary diff SHA-256は`1b1bcaa0a0bbadc48fc92a6ece84a5cfea991badd969934911db3d2b58a3ea95`（`git diff --binary 2dce3b32 5a9e37bd`）。

## 現在の一括判断対象（既採用5件の再判断ではない）

| 具体対象 | 選択肢・推奨 | 意味/独立期待値への影響 |
| --- | --- | --- |
| `2dce3b32..5a9e37bd`のP1是正と直接影響箇所 | 是正差分の独立レビュー追加1回を許可 / 未再レビュー差分を人間が確認し残余を受容。推奨は追加1回。基本2回+追加1回を使用済みと明示 | 承認済み表示入力を固定する検査強化のみ。期待値の新規確定やP-6の代替はしない |
| `requirements-followup.patch`と550 E12追補の版調整 | 正本の確定ゲートへ提出 / 候補を保持。推奨は具体追随文の正式ゲート提出 | E11/E02/E08/E09/E10の既裁定を再判断せず、原典・版・伝播先を確認。人間承認や逐行確認は未記録 |
| 本担当feature枝の固定候補と検査結果 | push/Draft PR作成を許可 / ローカルを保持。推奨はDraftとして残ゲートを公開 | 正式契約の包括承認・製品投入・マージを意味しない |

再署名・P-6署名そのものはこの判断表で代替しない。正式対象版を確認した実施者による行為と受理が必要。
