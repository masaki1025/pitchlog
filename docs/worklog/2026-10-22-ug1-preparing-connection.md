# 2026-10-22 U-G1 preparing限定接続

## 指示・固定基線

- POはCodex Dをpreparing作成・再取得の限定主担当に指定。U-G1全体/開始は移管しない。今回は起案・正式6.1レビューだけ許可、計画最終承認は未。
- 実develop7717b98686395b2c0db9d545a5effa06888885ffからfeature/ug1-preparing-connection専用worktreeを作成。新カード・新PRは作成しない。
- 旧U-G1の67dff5f707dcb2311a35140ae870b44f46e24803、8ステップ/レビュー2周と承認記録を保持。未コミット/未追跡0を2回確認、当該cwdの稼働プロセスを観測せず。ただし担当不在・所有解除とは解釈しない。旧worktree/ブランチは変更しない。
- 親step1はresolver契約差分が残り、step2は未着手。完了ステップへの押込みを避け、6コミットの追加単位を提案する。親を複製・全体再計画しない。

## 所有・外部契約の記録

- [#152既存照会](https://github.com/masaki1025/pitchlog/pull/152#issuecomment-6337294532)へPO指定と予定新規backendパス・共有資産境界を追記。resolverの公開型/operation/担当/提出単位の照会は再送しない。
- [#171既存照会](https://github.com/masaki1025/pitchlog/pull/171#issuecomment-6337294852)へPO指定とGameScreenEntry*/新api/gamesの限定接続候補を追記。U-F8の受理は未。実競合があるパスだけ調整する。
- [#173差分照会](https://github.com/masaki1025/pitchlog/pull/173#issuecomment-6337333569): RG1 SQL2本がfalse固定であることと安全な成功許可/提出単位を確認。既受理①〜⑤の再照会をしない。#173文書だけを実提供と扱わない。
- 送付、PO担当指定、相手の担当受理、実提供は別。現時点で外部3担当から回答未受領。agmsgは本repoの登録がなく別projectのtodoapp候補だけのため、誤チーム参加はせず既存PR/Notionを使った。

## レビュー履歴

- 親U-G1の計画基本2周を維持。本追加単位の6.1レビューは別対象の限定追補として今回POが許可。未実施のレビュー結果・採否は先行記入しない。製品/凍結資産/本人確認の履歴はリセットしない。
- 追加単位の第1回（全文、ラッパーadversarial）はP0=0/P1=2/P2=0で否決。受理範囲はいずれもDoD/成果物の不対応。①新大会語彙の全取消を既存大会の試験だけで代替できる、②二重submitのPOST/保存件数の判定がない、を全件採用した。
- 最小反映: ステップ5/テスト計画へ新大会名の語彙INSERT後故障・RG1直前拒否で試合/新語彙0件・既存語彙不変を追加。ステップ6/画面試験へ送信中二重操作のPOST1件・保存試合1件を追加。API/権限/所有/外部依存・6ステップ数は不変。指摘反映を伴う計画レビュー周回を1へ更新した。
- 第2回は上記反映差分と影響節のみを対象とし、親全体や既受理事項を再レビューしない。判定と未再レビュー差分は終了後に追記する。
- 第2回（反映差分＋影響節、ラッパーadversarial）はP0=0/P1=0/P2=0で可決。前回P1の2件は解消。追加反映なしの確認周なので計画レビュー周回は1を維持する。実実行は本追補2回、親の基本2周とは別に保持する。第2回後の独立未再レビュー差分は本作業ログへの結果/検査記録のみ。
- 計画同期検査は成功、文書状態は20文書0違反、diff-check成功。製品変更がないため製品全件テスト/実画面受入を実行済みとはしない。外部3担当の担当受理/実提供回答は未受領で、同じ照会は再送していない。

## 現状

### 査読後の実develop追随

- 第2回可決後の最終照合で#162が`760c04d540b22190cab076165f1b4e35ae473a1f`へ実統合されたことをremote/refで確認。起案基線7717b986との差分12ファイルはdata-model §6-5/変更履歴、正本参照digest・ORM受入資料/試験で、resolver/RG1/画面/今回の新規backendパスには変更がない。
- 通常mergeで実developを取り込み、競合なし。新しい§6-5は初回INSERT後の異値UPDATE禁止、同値/他列UPDATEの許容、正当なmigration/復旧の別ゲートを明文化し、6-key保存形は不変。本追補の初回保存→保存値read・非遡及・旧行不補完と整合し、API/権限・6ステップ/合格条件は変えない。
- #162の未統合待ちは解消。#152担当がこの実基線からresolver側を再導出する必要がある点は実提供条件として残す。今回の通常mergeを#152/#173の受理/実提供にしない。
- 査読後の追加未再レビュー差分はplanの基線記録1段落と本worklogの結果/影響記録のみ。新しい全体計画審査や第3回レビューを自動開始しない。最終PO承認時の確認対象とする。

起案時点では製品編集0、共有正式資産編集0、実画面作成/reload受入未実施。resolver製品登録/公開型・安全なRG1成功許可・必要な正式7.7は未成立。開始/初期権/1球保存を完了としない。

### 最終承認とステップ1〜3の着手

- 山田正輝が2026-10-22、承認対象98cd9974178a2271235d737afb24f019f9142bb0/基線760c04d5を明示承認。6コミット・合格条件、親8ステップと既受理履歴を維持。6.1第2回可決後の基線記録・作業ログは独立未再レビューであることも保持する。
- 実developは760c04d540b22190cab076165f1b4e35ae473a1fのまま。独立core宣言→JSON登録→DTO/read component・拒否境界を順に進める。今回の計画承認を7.7/本人確認/公開/マージへ流用しない。push/PR許可は本限定単位で未確認のため候補固定までとする。

### ステップ1/6: 宣言と拒否試験

- `services/game_creation.py`と`backend/tests/test_game_preparing*.py`の最小2パターンをtenant-isolation追加層へ宣言。API/repository/frontendは既存登録を再利用。登録済みstage_aは実JSONの両領域に1件ずつ保持し、tenant追加層の消費済み宣言だけを今回の層へ切り替えた。game-stateの旧宣言は保持。判定関数・実JSONは変更なし。
- 隔離履歴で宣言/登録/後続登録と未宣言/部分追加/未記入逐行確認拒否を維持し、実基線のstage_a登録保持と新パス検出を検証。最終core guard試験269成功、root Ruff/ty/diff-check成功。
- 初回委任は担当側プロンプトの「登録済み宣言保持」と追加層契約の矛盾、再委任は正確なglob指定欠落で確認待ちとなり、いずれも自分のプロセスだけを終了。製品/宣言の変更前で、268成功は変更前基線の結果として区別する。確定した2パターンを渡した最終委任は完走した。`--resume`は保存ID未生成のため起動前拒否され、新規実行で継続した。
- 最終委任の初回検査にはuv共有cache書込不可と型注釈2件があった。自分の一時cache指定/注釈是正後に再実行して成功。検査を除外・緩和していない。前2委任の中断を成功扱いしない。
- JSON登録の初回検査では268成功/1失敗。新規試験に実JSON未登録固定の前提が残っていたため、JSON候補を保全して宣言段階へ戻し、当該試験を隔離履歴での前後/後続登録検証へ是正した。修正後269成功、Ruff/ty/diff-check成功。登録後候補の一時JSONでも検査通過。未公開のステップ1コミットへ是正を含め、JSON登録とのコミット分離を維持した。検出や人間確認拒否は弱めていない。

### ステップ2/6: JSON登録

- ステップ1の確定コミット`8ece74b9`の後、`.claude/core-areas.json`だけを`57e73473`へコミット。tenant-isolation末尾に宣言済み2件を追加し、stage_a/U-F5/U-F6/U-F8/U-F13等の既存登録・全guard_pathsは不変。
- 是正後の実JSONでcore全269成功（48.46秒）。コミット後の`verify_area_path_baseline(origin/develop,HEAD)`は760c04d5を返して成功。新規パスの検出と未記入逐行確認の拒否は既存main/隔離試験で確認。frozen-baselines --invariants-onlyも成功。人間のチェック/方法を代記していない。

### ステップ3/6: DTO/read component・拒否境界

- 新規`api/schemas/games.py`に作成入力（5区分・aware日時・両側UUID・既存大会key/新名称の排他・既存任意ラベル）とlimit20/最大100・cursorを実装。既存BaseSchema/PageRequest/Timestampを再利用し、予約/余剰fieldを拒否。独自の大会名称正規化・重複判定・既定大会を追加していない。
- 新規`repositories/games.py`はPreparingGameListToken/DetailTokenと既存CAP:games:readの登録準備候補2件。context由来tenant bind、preparing・可視条件、索引順keyset、一覧limit+1/詳細1件を強制。候補はPRODUCT_OPERATIONSへ追加せず、現実行器の未登録拒否を試験した。SQLを構築/検査したcomponentの成果と、DB読取実接続を区別する。
- `test_game_preparing_components.py`固有45成功、既存API schema/roster schema/repositoryを含む影響試験216成功。backend Ruff format --checkは370ファイル適合、Ruff/ty成功。途中のpytest -n 2はbackendのxdist不在で終了4、通常のserial実行へ戻して完走。型/整形/lintの初回指摘は是正済み、試験除外・timeout緩和なし。
- 正式codec未提供のため、snapshot成功応答DTO/出所・相関証明を新作せず、旧snapshotの補完もしない。旧snapshotの実HTTP/DB拒否、正式read登録・API公開とproviderはステップ4へ残す。登録済みの実resolverと安全なRG1許可が必要な保存・実画面reloadはステップ5〜6へ残す。仮Port/fixtureによる成功を製品接続済みに数えない。
- 承認後の予定UIパス/責任案は[#171の同じ照会](https://github.com/masaki1025/pitchlog/pull/171#issuecomment-6337294852)へ追記。新しい同内容照会は増やさず、未回答を担当受理・所有解除にしない。実際の共有パス並行変更は観測されず、他担当worktreeは変更していない。

### 外部提供・正式ゲート・公開状態

- #152: 正式codec公開型/入力結果、固定operation登録と提供担当/提出単位の回答待ち。#162統合待ちは解消済みだが、#152自体の実提供を成立済みにしない。
- U-R1/#173: 既存RG1呼出し2件/具体例外は提供済み。SQLの常時falseを変更せず、安全な成功許可の条件・担当/提出単位は未提供。D4は作成component/readの一律待機条件ではない。
- U-F8: フォーム/必須大会/providerの具体分担回答は未受領。Dの限定主担当指定と送付済みを相手の受理へ読み替えない。実競合があるパスのみ調整する。
- read/作成HTTPをappへ登録する前に、既存capabilityに閉じたroute/matrix、operation/生成契約・tenant-boundary連動値の候補固定と必要な7.7が残る。今回正式台帳/受理履歴/snapshotを変更せず、承認者/日付・人間確認を先行入力しない。
- 本限定枝のpush/Draft PR許可は未確認。実装候補をローカルcommitで固定し、必要なら通常pushと最小1Draftの操作許可をまとめて求める。実装の最終レビュー・全件/DB/E2Eは後続接続後のゲートであり、今回計画レビュー2回をコード査読や本人確認へ流用しない。

### 最終候補の追跡済み検査と提供状況の差分

- 新3ファイルが未追跡の段階ではtenant-boundary checkerは成功したが、commit後の最終検査は**TB005 2件・終了1**。新`repositories.games.preparing_game_list_statement`と`preparing_game_detail_statement`の`sqlalchemy.select`は、正式な基底symbol許可の外である。前段の成功を最終HEADの成功に流用しない。新しいsource/factory許可と2 tokenのoperation/公開型契約を、ステップ4の基線・認可/7.7候補へ含める必要がある。今回checker/許可台帳を変更して回避せず、全品質ゲート通過・read公開完了とはしない。
- この2件はsnapshot公開型未提供とは別の正式ゲート。既存CAP:games:readのまま2つの閉じたreadだけを許す候補を固定し、既存登録の不変性・未登録拒否・全前後値/snapshot/履歴を照合して7.7へ出す。現時点で実値を正式受理済みにせず、既存履歴へ追記しない。
- 最終候補でcoreの基線照合と実製品3ファイル検出、凍結基線不変量、計画同期、文書状態20件0違反、diff-checkは成功。backendの固有45/影響216・format/Ruff/ty成功とは分けて記録する。
- 外部状況: [#173コメント6337880708](https://github.com/masaki1025/pitchlog/pull/173#issuecomment-6337880708)で#152後続の[#174](https://github.com/masaki1025/pitchlog/pull/174)作成を確認。公開HEAD4caa88c3は引継ぎ文書のみで、公開resolver型/製品operationはステップ3の対象外と明記。#174→#173統合順は先方の提案であり、両担当の受理として代記しない。#152の旧受理値を最新25履歴へ流用しない。Dから同じ照会を再送せず、型/operation/提出単位の実提供待ちを保持する。

### 部分Draft公開とread登録準備の許可

- POが9c4f8f02を受領し、本追加単位の通常pushと最小1本のDraft PRを許可。既存同一目的PRは0件。実装継続中・7.7未成立の部分Draftとしてplan activeを保持し、実際の製品/試験3ファイルを公開HEADで照合する。従前の未許可記述はその時点の履歴として保持する。
- DTO/read componentまで実装済み。正式registry/APIは未接続、TB005は2件、保存成功・実画面reload・本人確認は未実施。マージ不可。計画レビュー2回を製品レビューへ流用しない。
- 台帳への追記なし。未追跡時の検査との差は追跡対象の確認で解決すべき本候補の注意点で、今回新しいハーネス機能・一般化した運用改訂は追加しない。
- 共有パスは#174と#173の双方でbase-allowlist/repository-contract等の実編集を観測した。Dは当該共有ファイルを編集せず、特徴単位の候補資料/拒否試験を独立して準備する。先行提案・通知と担当受理・実統合を区別する。
