# TSK-550 共有固定関数実行器A 作業ログ（2026-10-15）

## PO承認とステップ1

- POは`2f57e14d`のA専用2ステップ計画と資産ゲート案にある全9資産の**変更範囲**を承認した。第2回レビュー後に反映した差分も確認対象。承認はステップ1着手までで、製品コード・凍結資産・ステップ2・B/C製品登録・マージの許可ではない。
- `origin/develop` `e2e78cfb`を競合なく作業ブランチへ取り込んだ（`1ee73acb`）。8資産のrevisionは計画時点から各1つ進んだため、[資産ゲート案](../features/tsk550-shared-function-executor/asset-gate-proposal.md)のbefore/after候補を更新した。`frozen-inputs.json`は全9資産の識別値マップへ含めるが、Aの変更対象ではない。
- Aの製品固定関数登録は0件。試験専用の閉じた登録だけを同じ`run_function`入口で使う。未登録・偽造token、任意SQL、Session注入、失効scopeの拒否を維持する。ステップ1では製品コード・契約JSON・生成物・fixture・検査器を変更していない。
- 7.7では実装後の実digest、8資産の前後射影、全9資産の識別値、受理済み履歴とsnapshot、比較corpus再pinを最終headで照合し、正式受理を別ゲートにする。現時点で実digest・after状態・正式受理は未確定。

## U-R1同期確認

- U-R1向け同期案`7aea7b44`は担当worktree `feature/ur1-recording-rights` HEAD `19f28ba2`の祖先ではなく、指定コミットそのものの取り込みは未確認。
- 担当側`plan.md`と`rg1-individual-approval-packet.md`には`8a270c2a`を出所とするA=0件、A統合後のB/C独立、旧初回resolver順序制約の変更が記録されている。一方、`7aea7b44`が追加する`rg1-preparing-acceptance.md`の分割受理追記は担当HEADに見当たらない。担当側の採否・取り込み確認を残す。所有worktreeは編集しない。

## 残ゲート

- Aステップ2: 別指示を受けてから着手。実digest・7.7前後状態・正式受理は実装後の最終headで提示する別ゲート。製品登録0件、試験専用fixture分離と拒否系試験、最終head検査、コア敵対レビュー、人間逐行確認が必要。
- B/C: Aの統合後に独立して進める。Bのresolver1登録、CのRG1専用2登録、各関数権限と個別資産受理はAの承認外。TSK-550本体ステップ3の正本人間承認も別ゲート。

## 7.7正式受理の事前照合（2026-10-15・ステップ2未着手）

`origin/develop`は`9b8f9bc6`まで進んだが、`e2e78cfb`以降の5コミットには下表の9資産・共通迂回検査器・比較corpus・repository製品コードの変更がない。以下のSHA-256は現行資産の`baseline_control.identity.frozen_projection`宣言と現行外部ファイルから`frozen_history.frozen_projection_content`で計算した**before射影**であり、実装後のafter digestではない。`python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`は合格。

| 資産 | before識別値 | before射影SHA-256 | Aでの個別確認条件 |
| --- | --- | --- | --- |
| `repository-contract.json` | `contract_revision:17` | `bb2ac29eb7c07dde485cce8a1e69c52813f01b403c229c133e3a4ea02366893c` | 固定関数公開型・同一scope入口・製品ID空集合と生成契約がexact一致。既存DML不変 |
| `base-allowlist.json` | `contract_revision:29` | `5ff5b7b73ed103d96e8365bc9e16f583cca0a24f593ee02c1e581dfae9abc425` | `run_function`だけに第4の`SQLA_SESSION_EXECUTE`行。既存3行・他API不変。9資産の単一受理履歴を追記 |
| `runtime-authz-contract.json` | `runtime_contract_revision:14` | `be46dc4746104d3ad7b0aa0bed534030fe8dffb941b9f521048f6c3b5a7ef970` | 共通検査器の外部射影だけ追随。製品DB権限集合不変 |
| `negative-fixtures.json` | `fixture_set_revision:15` | `22505fb06701f6da3d39edfbe78743611d4769e1c02a2c41af88d2f2e914a5c2` | 新入口からの直接Session実行を`TB005`で拒否し、既存負例を保持 |
| `cache-invalidation-contract.json` | `contract_revision:13` | `db99ba6d35b80fadd35e7aa700736eab347a2ae26765ddf4c59c89bb2f5e2e59` | 共通検査器の外部射影だけ追随。既存無効化契約不変 |
| `census-baseline.json` | `contract_revision:12` | `fa0923c2234fe718af71f25509fc75b4b93a5fd6b7ccd5e4edd30050f7819dea` | 共通検査器の外部射影だけ追随。母集団・合否述語不変 |
| `db-api-inventory.json` | `inventory_revision:13` | `9ae9104b70d11b5ee95cd3a636b2e7b0973bb8cca54d887ffd6270e486edf8c8` | 共通検査器の外部射影だけ追随。既存DB API集合不変 |
| `tenant-context-allowlist.json` | `contract_revision:14` | `092f134dd39d134c6b275e48b70928915f1c1c4ed801f326dd4b8418cb8c428c` | 共通検査器の外部射影だけ追随。tenant発行境界不変 |
| `frozen-inputs.json` | `contract_revision:4` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | 9資産の識別値マップへ含めるが、識別値・射影・本文を変更しない |

**正式受理に必要な未成立証跡**: Aの製品コード・検査器・fixture・凍結資産は未実装なので、8資産のafter射影/digest、新snapshot、生成物一致、比較corpusの再pinと11ケース再検査、9資産の新旧識別値マップを持つ追記履歴、変更者・理由・承認日、最終headの迂回/凍結/guard・backend検査と独立敵対レビューは存在しない。7.7-2の「直前/直後」は同一受理の状態として提出し、中間コミットを受理状態にしない。7.7-3の参照失敗は検査不合格とする。計画・9資産の**変更範囲承認**は成立済みだが、実値・前後状態・正式受理は成立していない。今回の条件付き指示ではステップ2を開始しない。実装後証跡を求めるなら、ステップ2着手の別指示と、実差分に対する別ゲートの正式受理を区別する。

## ステップ2条件付き着手の規則照合（2026-10-15）

POは9資産の既承認範囲に限定した着手を条件付きで指示した。7.7本文は1回の受理による実際のbefore/after遷移を1記録とし、受理単位を各資産へ委任するため、**実装後にdigestを計算し、正式受理を別に行う順序自体は許容する**。しかし現行A計画のステップ2見出しは「個別承認後」であり、同ステップDoDは履歴・比較corpus・関連検査が最終headで緑になることを要求する。`frozen_history.py`のv2履歴は実PR番号由来の`acceptance_id`、予約markerでない承認者とISO承認日、実before/after snapshotを必須とし、PR受理検査ではGitHub eventの番号・2親mergeと照合する。Aブランチは未push・PR未作成で、今回もpushを保留する指示のため、受理IDを確定できない。仮IDや仮承認を記録して合格と扱えない。

**最小追補候補**: ステップ2を「9資産の範囲承認後に候補実装・after digest・前後射影を作る。ただし未受理の候補headは合格/完了としない」と「実PR番号取得後にv2履歴、snapshot、比較corpus、最終head検査を揃え、7.7正式受理を得る」に明示分離する。現行のステップ番号を増やすか同ステップ内ゲートにするかを6.1/6.3の計画レビューで判定する。7.7正本文の変更は不要。PR番号取得には少なくともpushとDraft PRの許可が必要だが、今回は禁止されているため別の人間判断とする。正式受理前の`approved_by`/`approved_on`やPR IDを推定で埋めない。調査中に作った未コミットの製品試作差分は撤去し、worktreeは文書記録以外の変更なし。計画追補の承認まで製品実装を停止する。

## 追補案とレビュー上限（2026-10-15）

[二段階ゲート追補案](../features/tsk550-shared-function-executor/step2-gate-addendum-proposal.md)を起案した。ステップ表の総数2と既存ステップ1コミットを維持し、2A候補実装・実値算出と2B実PR番号を使う履歴・最終検査・正式受理を同じステップ2内のゲートに分ける。6.1の1ステップ1コミットを維持するには、後日の別許可で文書のみのfeature HEADを先にpushしてDraft PR番号を得て、製品候補を未コミット差分として提示し、受理後に1つのステップ2コミットへまとめる順序が必要。現時点のpush・Draft PR禁止を解除したものではない。

A計画の計画レビュー基本2周は使用済み。6.3の追加独立敵対レビューを始めるには、POが追加1回と範囲を裁定する必要がある。推奨範囲は追補案全文と元計画ステップ表・6.1コミット規律・7.7履歴手順の影響節。PO裁定前にレビューを開始しない。人間承認はレビュー結果と最終反映差分を示した後に別途求める。製品コード、9資産、push、Draft PR、マージへの変更なし。

## 追加独立レビューと採否（2026-10-15）

POは6.3に基づく追加レビューを**1回だけ**許可し、対象を追補案全文、元計画のステップ表、6.1のコミット規律、7.7の履歴確定・正式受理、各段階の開始・完了条件とGit操作に限定した。`.claude/scripts/codex_run.py review adversarial`による独立read-onlyレビュー（session `01a13f49-cf70-7720-9e1f-180d0c92f793`）の判定は**否決、P0=0/P1=3/P2=0**。全3件を採用した。

| 重大度 | 指摘 | 採否・追補案への修正 |
| --- | --- | --- |
| P1 | 文書だけを先行pushしてDraft PR番号を取る順序と、2Bの「正式受理後にpush」および6.1の通常`/pr`順序の関係が曖昧 | 採用。文書のみの先行push・Draft PRは**別の個別許可がある場合だけ**行うA限定の番号取得例外と明記。計画は`active`を維持し、ステップ2コミット・ローカル最終HEAD検査後に通常の`/pr`手順へ戻す。製品・資産のpushは正式受理とローカル全緑の後に限る |
| P1 | 未コミットの候補差分を`git diff`だけで提示すると新規未追跡ファイルを漏らす | 採用。新規ファイルへ`git add -N`を適用し、`git diff`と`git status --short`で候補全ファイルを照合してから提示する |
| P1 | 最終HEADを読む検査をステップ2コミット前に緑とすることはできず、コミット後の失敗是正が6.1の1ステップ1コミットと整合しない | 採用。正式受理後に単一の`(ステップ 2/2)`コミットを作り、そのHEADでローカル検査する。失敗時はpushを止め、受理対象の変更を再提示・必要なら再受理した後、未pushコミットをamendして再検査する。push後のCI・レビュー是正は個別判断を求め、force pushや追加コードコミットを自動実行しない |

指摘反映に伴い、計画の`計画レビュー周回`を6.1に従って2から3へ更新した。最終反映の再レビューは今回の許可に含まれない。追補案は**人間承認待ち**であり、現行ステップ表は変更していない。承認者は上表の採否と最終反映差分を確認する。製品実装、凍結9資産の変更、push、Draft PR、マージは行っていない。既承認の9資産範囲、Aの製品登録0件、B/C独立は維持する。

## 二段階ゲート追補の人間承認（2026-10-15）

POは`7aa9bebc`の[最終追補](../features/tsk550-shared-function-executor/step2-gate-addendum-proposal.md)を「承認」と回答した。P1三件の採否と最終反映を確認対象として、ステップ2内の2A/2B開始・完了条件とGit順序を承認済み計画へ適用する。ステップ総数2、ステップ1コミット、9資産の承認済み**変更範囲**、Aの製品登録0件、B/C独立は維持する。2Aの実装着手、凍結資産の実値・7.7正式受理、push、Draft PR、マージは各段階の別の個別許可として管理する。今回、製品コード・凍結資産は変更していない。

## ステップ2A候補と最新develop照合（2026-10-15）

POは承認済み追補に基づく**2Aの実装着手**を個別に承認した。`origin/develop`の`f36d0fee`を競合なく取り込んだ。取り込み分54コミットの変更49ファイルにはAの9資産、`backend/src/pitchlog/repositories/*`、Aの生成契約・共有迂回検査器・比較corpusが含まれない。正本の追加は付録B-7の母集合追随、幾何契約とU-D1の更新で、Aの固定関数実行器、権限、登録0件を変えるものではない。新たな仕様・権限・変更範囲の判断は不要と判定した。既存の7.7 authority履歴19件とsnapshot 154件を保持し、比較corpusの`pinned_prefixes`は既存の履歴先頭6件・snapshot 83件を保持する。

2Aの未コミット候補では、`FunctionOperationRegistration`を固定SQL・schema修飾関数・exact bind・列型/行数/decoderを検証する登録型として追加した。製品`PRODUCT_FUNCTION_OPERATIONS = ()`を維持し、既存DMLとのID/型衝突、未登録/派生/偽造token、任意SQL、入力型不一致を拒否する。同じ`_TenantTransaction`へ`run_function`を加え、既存scopeの発行証跡・tenant・失効検査、Session所有、例外時全取消を用いる。試験専用registryだけで正常系とdecoder故障・文脈改変を確認した。承認済み8可動資産の候補revisionと生成物、共通迂回検査器、第4の`SQLA_SESSION_EXECUTE`行、専用正例/負例fixtureを対応付けた。新規4ファイルに`git add -N`を適用し、`git diff`と`git status --short`で全21ファイルを照合した。製品登録、DB関数、関数権限、B/C登録、9件目の`frozen-inputs.json`は変更していない。

以下は`origin/develop`のbeforeと、作業ツリー候補のafterを、`frozen_history.frozen_projection_content`で各資産が宣言する外部ファイル込みで算出したSHA-256。**候補値であり7.7正式受理値ではない**。追加修正があれば再算出する。

| 資産 | 識別値before→after候補 | before射影SHA-256 | after候補SHA-256 |
| --- | --- | --- | --- |
| `repository-contract.json` | `contract_revision:17→18` | `bb2ac29eb7c07dde485cce8a1e69c52813f01b403c229c133e3a4ea02366893c` | `a087dd84b5bcab7b8b7df25876cd213f6c16910dd1a0cb30daf9c951e20b5359` |
| `base-allowlist.json` | `contract_revision:29→30` | `5ff5b7b73ed103d96e8365bc9e16f583cca0a24f593ee02c1e581dfae9abc425` | `b5e23732b01ee288b9fc1d2de6e57dc466d7612ff624eabe22cfcd5ca6fbb089` |
| `runtime-authz-contract.json` | `runtime_contract_revision:14→15` | `be46dc4746104d3ad7b0aa0bed534030fe8dffb941b9f521048f6c3b5a7ef970` | `655653f2728a517b464abb813c79effe5ac029e03214771e49d21ce1b585ba35` |
| `negative-fixtures.json` | `fixture_set_revision:15→16` | `22505fb06701f6da3d39edfbe78743611d4769e1c02a2c41af88d2f2e914a5c2` | `6dd5cd4dd92c96f58557ca3fe4b15d1f35d4d0b296a8f8d7f03abd3be6137608` |
| `cache-invalidation-contract.json` | `contract_revision:13→14` | `db99ba6d35b80fadd35e7aa700736eab347a2ae26765ddf4c59c89bb2f5e2e59` | `ffef0a5a70c85d963fae91ef22128f79e865055c29a799f5efc05fe522428e5d` |
| `census-baseline.json` | `contract_revision:12→13` | `fa0923c2234fe718af71f25509fc75b4b93a5fd6b7ccd5e4edd30050f7819dea` | `446bd37d21369a65607e61742b15d11b48b5e20e10d5117ee40905349b2e72f3` |
| `db-api-inventory.json` | `inventory_revision:13→14` | `9ae9104b70d11b5ee95cd3a636b2e7b0973bb8cca54d887ffd6270e486edf8c8` | `bbd5af757bd763c6288dbe817b86a84e5d44faa90dcd7e06fb56c7cead254666` |
| `tenant-context-allowlist.json` | `contract_revision:14→15` | `092f134dd39d134c6b275e48b70928915f1c1c4ed801f326dd4b8418cb8c428c` | `b1036cbf01195a1849c911c276f005a112a1f0e0a8c0cafbfa5fa2a6104e74dd` |
| `frozen-inputs.json`（不変） | `contract_revision:4→4` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | 同左 |

比較corpusの候補入力digestは`455349e70538fb51ccacea52d06277c5c9bca0afb4647c5551b7c4d0f7c3ae52`、現行manifestは`759482edef1eb5935fa41251d876f980f7a5ec523ee93bb4a2b44afe4834f068`。manifestの再pinと11シナリオの最終比較は2Bで実履歴とsnapshotを入れてから行う。現時点の`check_tenant_boundary_bypass.py --base-ref origin/develop`は「履歴末尾と7資産の識別値が不一致」で不合格、`test_current_corpus_inputs_match_manifest_digest`は候補入力との差で不合格。仮のPR番号・受理ID・承認者・承認日を置かず、赤い候補状態を合格と呼ばない。

**候補検査**: backend Ruff format/check・ty合格、固定関数13試験合格、関連の非DB試験73件合格。backend全非DB試験は1446件合格・4件skip・483件除外だが、DB必須試験0件を検出する既存session gateによりコマンド終了値1。DBを含む関連実行は72件合格のほか17件が既存共有DBの被検査ロール`pitchlog_test_role`の先存でfixture setup errorとなり、DB経路の合格証跡にはしない。別担当のDB状態を変更しない。root Ruff/ty合格。固定関数の正例・負例・公開面と既存実装変異の関連7件合格。root全迂回試験の初回は329件合格・13件失敗で、うち8件は履歴未受理、5件は合成repoに新規moduleがない判定順の問題。後者を修正し関連7件を再検証した。最終headの基線・core-guard・全試験は2Bゲートで改めて行う。

2Aは候補の提示でありステップ2のコミット・完了ではない。実PR番号の取得、7.7実値/前後状態の正式受理、履歴追記、snapshot・corpus再pin、push・Draft PR・マージはそれぞれ後続の個別ゲートに残す。

## 2Aの隔離DB再検証・独立レビュー引渡し（2026-10-15）

既存共有DBの`pitchlog_test_role`は変更・削除せず、`postgres:17.11-bookworm`の使い捨てコンテナを新規作成した。ランダムな管理者・被検査ロールと認証情報をこのコンテナ専用に発行し、子pytestプロセスの管理用・被検査ロール用DSNだけを隔離先へ差し替えた。`backend/`で`tests/test_authz_tenant_binding.py -m requires_db -q`を実行し、**17 passed、15 deselected、終了値0**。試験終了後にコンテナとvolumeを削除した。前回の共有DBでの17件fixture setup errorはこの隔離再実行では再現しなかった。

独立レビューへ渡す基点は`origin/develop=f36d0fee`を取り込んだfeature HEAD `594fef74`と、同HEAD上の**未コミット候補全22ファイル**。新規4ファイルには`git add -N`を適用済みで、`git diff --binary`と`git status --short`に全候補を表示できる。上表の9資産before/after識別値・SHA-256、比較corpus候補digestと不合格理由を同一候補の照合表として保全する。レビューでは製品`PRODUCT_FUNCTION_OPERATIONS = ()`、試験専用registryの分離、未登録・偽造token、任意SQL、Session注入、失効scopeの拒否、既存DML契約の非緩和、同一scope/tenant束縛・失敗時全取消を確認対象とする。関連非DB試験・隔離DB17件・root迂回検査の結果は前節と本節を証跡とし、凍結・corpus検査の不合格は**7.7未受理・未再pin**として維持する。独立レビューは未実施であり、候補をステップ2完了とは扱わない。

## 最新develop・独立レビュー・PR番号（2026-10-15）

`origin/develop=3f6a935a`（PR #140統合）を取り込み、feature HEADを`5f0eac14`とした。#140の変更はU-T1とmigration等の14ファイルで、Aの9資産・製品固定関数・共有検査器とは重ならない。未コミット候補22ファイルは退避・復元して全数を再照合した。公開したHEADのfeature差分は計画・追補・資産案・作業ログの**文書4ファイルだけ**。そのHEADをpushし、番号取得用Draft PR [#141](https://github.com/masaki1025/pitchlog/pull/141)を作成した。製品コード・候補資産は未push。

実装に関与していない独立Codexレビュアが、HEAD `5f0eac14`上の候補22ファイルを確認した。指摘はP0=1（独立CTEからの任意DML）、P1=2（DML capability衝突、decoder後の結果契約逸脱）、P2=2（SQLAlchemy bind型不一致、上限超過時の全件読込）。5件を全採用し、CTE拒否、capability照合、decoder前後の行・列・型検査、bind型照合、`max_rows+1`件での読取打切りと負例を追加した。レビュアは修正と関連試験（固定関数16件、root関連9件、`git diff --check`）を再確認し、追加のP0/P1は見つけていない。この独立レビューはClaude一次レビューの実施記録ではなく、コア敵対レビューと人間逐行確認のマージ前条件も残す。

修正後、別の使い捨てPostgreSQLで関連3ファイルを再実行し、**94 passed、終了値0**。既存共有ロールは変更・削除せず、コンテナとvolumeは試験後に削除した。8可動資産のafter射影を再計算し、上表の値と一致した。`frozen-inputs.json`を含む9資産のbefore/after表が正式受理候補の完全な識別値・射影SHA一覧である。外部snapshotで値が動くのは`scripts/check_tenant_boundary_bypass.py`だけ（`fca73e2688880a594d8be959c14a1acf01b80cba499f853289bb58801843e4d8`→`b02434c82c3d8c55bee41d472764b0c506e297f4010e6e07e1d0bd834a4f79ee`）。8資産のafter snapshot参照は上表のafter SHAを末尾とする`contracts/tenant_boundary/history-snapshots/<sha256>`で、9番目はbeforeと同一。受理前の候補bytesは`/tmp/tsk550-a-141-candidate-snapshots/`にcontent addressで保全し、完全なbefore/after declaration・movement policy・外部/資産snapshot参照を含む受理記録案は`/tmp/tsk550-a-141-record-candidate.json`に保全した。案の`acceptance_id`は実PR由来の`masaki1025/pitchlog#141`、aspectは`asset_snapshots`・`declaration`・`external_snapshots`。`approved_by`・`approved_on`は**未記入**で、資産の正式履歴へは未反映。

7.7の実値正式受理、履歴・snapshotの資産反映、比較corpus再pin、ステップ2コミット、製品コード・資産のpush、最終HEAD検査・CIは未実施。現時点の凍結・corpus不合格は未受理・未再pinの予期された状態として維持する。PR #141はDraftのまま、人間逐行確認欄は空欄、マージは行わない。

受理記録案JSONのSHA-256は`6145d0570337f8dd5a0b6f844989465d4019cf2b9d1dfc321665569016e4e0e1`。前後状態の外部・資産snapshot参照は重複を除き26件で、候補snapshot 26ファイルの内容SHAと全件一致することを検査した。修正後のbackend Ruff format/check・ty、root Ruff/ty、関連root試験7件と`git diff --check`は合格。凍結検査は「履歴末尾と7資産の識別値が不一致」で終了値2、corpus検査はmanifest `759482edef1eb5935fa41251d876f980f7a5ec523ee93bb4a2b44afe4834f068`と候補`455349e70538fb51ccacea52d06277c5c9bca0afb4647c5551b7c4d0f7c3ae52`の不一致で終了値1。受理前にこれらを緑とは記録しない。

製品・資産・検査器・試験の候補21ファイル（作業ログを除く）のbinary patchを`/tmp/tsk550-a-141-candidate.patch`へ保全した。SHA-256は`b4c908bcb67430b2969449cff91034501fd1c602f2d97580b0e9ad8458128926`。候補コードと資産の正式コミット・pushは7.7実値受理まで行わない。

## PR #141の7.7実値正式受理と反映（2026-10-15）

POは本ログの9資産の識別値・完全なbefore/after射影SHA-256、共通迂回検査器の外部snapshot変更、受理記録案を**今回の候補差分に限定して正式受理**した。製品登録0件は維持し、B/C登録・保護設定変更は対象外。`origin/develop`は受理時の`3f6a935a`から変化しておらず、受理済み射影値を再算出して全件一致した。今回の受理は人間逐行確認の実施記録へ流用しない。

受理済み候補の外部snapshot1件と資産射影8件、合計9件のcontent-addressed snapshotを追記した。受理記録案が参照する前後の26件は既存・新規を含めて全件を内容SHAと照合済み。比較corpusの入力digestだけを候補実測値`455349e70538fb51ccacea52d06277c5c9bca0afb4647c5551b7c4d0f7c3ae52`へ再pinし、既存`comparison_revision`・11ケースの期待値・前版終了コード・履歴6件/snapshot83件の固定prefixは保持した。POは受理記録の実承認者を**山田正輝**、承認日を**2026-10-15**と明示したため、`base-allowlist.json`の履歴へ実PR由来の`masaki1025/pitchlog#141`でv2 recordを1件追記した。履歴は19→20件、既存19件は変更していない。受理済み9資産のafter射影値は履歴反映後も一致する。`check_tenant_boundary_bypass.py --base-ref origin/develop`は合格、比較corpusは29件合格、`check_frozen_baselines.py --invariants-only`は合格。

計画のcore-guard既存globと照合した結果、追加試験ファイルを`backend/tests/test_function_operations_boundary.py`へ改名した。製品moduleと改名後の試験はどちらも`matched_paths`で検出される。試験本文と9資産の受理射影値は不変。独立レビュアが改名後の差分・固定関数試験16件・`git diff --check`を再確認し、初回のP0/P1/P2採否に影響しないと回答した。改名後の関連非DB試験は77件合格、DB17件は最終HEADで再実行する。

## f6b15e87後の追加P1と承認根拠の再照合（2026-10-15）

本会話の人間による発言「PR #141について、今回提示された9資産の識別値・完全なbefore／after射影digest、外部snapshot変更、および受理記録案を7.7として正式受理します」を、7.7実値受理の一次根拠として照合した。続く本会話の人間発言「approved_byには『山田正輝』を記録してください。承認日は2026-10-15です」が承認者・承認日を指定している。対象はこのA候補差分に限り、製品登録0件、B/C登録・権限、逐行確認は受理対象外。作業ログの自記述だけで受理済みとは判定しない。

独立レビュアから追加P1として、`BindParameter.literal_execute=True`と`expanding=True`が登録時に拒否されないことを指摘された。保全した2A候補パッチとステップ2コミット`f6b15e87`の両方に拒否条件・負例試験がないことを照合した。A担当は全bind引数の両flagを登録時に拒否し、tenant_id・追加入力それぞれの両flagに対する負例4件を追加した。関連試験は20件合格、backend Ruff format/check・ty合格。9資産のafter完全射影を現作業ツリーで再計算し、受理履歴の9件と全件一致した。独立レビュアによる修正差分・関連試験・9資産digestの再確認が終わるまで、製品差分のpushは停止する。

独立レビュアは追加P1を**採用・解消**と判定した。`f6b15e87`と先行候補に欠落があったこと、現差分の全引数拒否と4負例を確認した。固定関数試験20件、対象2ファイルRuff format/check、backend ty、`git diff --check`は合格。製品登録0件を維持し、9資産のafter射影を独立再計算して受理履歴の値・同名snapshotのbytesに全件一致した。今回の修正差分に追加P0/P1/P2はない。受理対象の実値は変わらないため、二段階追補に従い未pushステップ2コミットへ修正をamendし、最終HEAD検査から再実行する。これはClaude一次レビューや人間逐行確認の代行ではない。

## 公開後CIの試験是正（2026-10-15）

公開したステップ2 HEAD `196f1e3d`のPR #141 CIでは、harness・frontend・凍結/迂回等は合格した。backend全pytestは`tests/db/test_tenant_transaction_scope.py::test_run_signature_has_no_second_tenant_context`の公開メソッドexact集合が新設`run_function`を含まないため1件失敗した。core-guardの失敗はPR本文の本人逐行確認チェックが未記入であることだけで、基線・path不整合ではない。人間チェック・実施記録は空欄を維持する。

二段階追補のpush後是正ゲートに従って差分を提示し、POは**既公開履歴を維持する別の試験是正コミット**で`run_function`を期待集合へ追加し、push・新HEAD CIを再実行することを承認した。force pushは禁止。是正差分は当該assertionの1行だけで、製品コード・9資産・7.7受理値は変更しない。使い捨てPostgreSQLで該当試験1件が合格、対象試験のRuff format/checkとbackend tyも合格した。9資産のafter完全射影は受理履歴と全件一致。新HEAD CI結果と人間逐行確認対象はPR本文・最終報告で確定する。

## PR #132 統合後の再基線候補（未受理）

TSK-391 / PR #132 の統合点は `origin/develop` `966d7a38`。#141 の `0b203dcd` を未コミットのマージ候補として取り込み、7ファイルの競合を解消した。製品側は `run_function` と U-S1 の `run_in_savepoint` を併存させ、公開メソッド試験も両方を保持する。製品関数登録は0件のまま。資産側は #132 の既受理履歴20件目を保持し、その直後に #141 を21件目として直列化する候補を `/tmp/tsk550-a-132-record-candidate.json` に作成した。候補に `approved_by` / `approved_on` はなく、正本履歴の末尾は #132 のまま。新しい人間受理前に #141 の承認情報や受理済み履歴を代記しない。

9資産のbefore識別値は #132 の `new_baseline_identifiers` と一致する。候補afterは base-allowlist 30→31、cache-invalidation 14→15、census 13→14、db-api inventory 14→15、negative-fixtures 16→17、repository 18→19、runtime-authz 15→16、tenant-context 15→16。`frozen-inputs` は4のまま。旧#141受理after射影から候補after射影は8資産すべて変わり、外部検査器snapshotは `b02434c82…`→`c6fbf8c9…`、比較corpus入力digestは #132 基線 `7237caf5…`→候補 `e73ef274…` となる。完全なSHA-256、前後宣言、9資産識別値、外部・資産snapshot参照は上記候補ファイルへ保全した。候補の8資産射影bytesは `/tmp/tsk550-a-132-merge-snapshots/` にある。意味差分はAの固定関数入口・空の製品登録・拒否fixtureとU-S1の既受理契約の併存であり、B/C登録・権限拡張はない。新しいafter実値と履歴順序には**7.7再受理が必要**で、現時点の凍結・履歴検査は未受理候補として不合格のまま扱う。

Claude一次レビューは旧基線の36ファイル全差分に対する静的確認で、可決 P0=0/P1=0/P2=5。独立Codexの候補査読とは別記録である。P2①実行後例外を呼出元が握りつぶした場合の副作用確定、②関数間のcapability/function ID重複とカタログ裏付け、③型なしbind、④未走行の拒否分岐・実DB関数試験は、Aの製品登録0件を踏まえて今回の製品コード変更に含めず、B/Cの実登録前ゲートとして採用する。⑤7.7人間受理発言の固定リンク不足は残余として採用し、PR本文に原文を記録した上で本人逐行確認で出所を照合する。これらを敵対レビューや逐行確認の実施済みへ読み替えない。新基線のコア敵対レビューと本人逐行確認は未実施。

## #132後の7.7再受理実値と敵対レビュー是正（2026-10-16）

`origin/develop=966d7a38`を基線に、旧#141の20件目は候補から外し、#132の受理済み20件目の**後**に#141を21件目として追記する案を維持する。新受理記録案は`/tmp/tsk550-a-132-record-candidate.json`、新射影bytesは`/tmp/tsk550-a-132-merge-snapshots/`へ保全した。案に承認者・承認日は入れていない。以下の値は新しい人間受理前の**候補値**。

| 資産 | #132既受理after / #141候補after識別値 | 旧#141受理after SHA-256 | #132既受理after SHA-256（今回before） | 新#141候補after SHA-256 |
| --- | --- | --- | --- | --- |
| `base-allowlist.json` | `contract_revision:30` → `contract_revision:31` | `b5e23732b01ee288b9fc1d2de6e57dc466d7612ff624eabe22cfcd5ca6fbb089` | `32bfa4312fb40b0fafe966b7e8b846ba45696e5d94ce9a567d983f8963a111c5` | `a7e75d1a2bb68c6b9e922dcf2d28c6425ac1d2514db478aea5951279b42b2074` |
| `cache-invalidation-contract.json` | `contract_revision:14` → `contract_revision:15` | `ffef0a5a70c85d963fae91ef22128f79e865055c29a799f5efc05fe522428e5d` | `22ed1510c74f331deb566154a8516d68936e34f77ef3e6237d40f7c90d319b55` | `e9eb7eeddfdbaf353505911a8a50c772d2c005b09b16d628b1584d2f4df508e3` |
| `census-baseline.json` | `contract_revision:13` → `contract_revision:14` | `446bd37d21369a65607e61742b15d11b48b5e20e10d5117ee40905349b2e72f3` | `939d79fdd71a3f600e1d645d9fc83c1d54701c22d66dda548bdf65b121f5a365` | `89ef72d277f2ceed0c6f8fe57ec2614e8737bc8d630e781a5e750c6e736e3c17` |
| `db-api-inventory.json` | `inventory_revision:14` → `inventory_revision:15` | `bbd5af757bd763c6288dbe817b86a84e5d44faa90dcd7e06fb56c7cead254666` | `73e6337328e374bfef4ee95eb67f3d474bac1a6b96a0b87391877b365871fbdb` | `a33b21815d133b9e655c3e7ff08ee4ec532c96cf04dd6735adaec38499082a5d` |
| `frozen-inputs.json` | `contract_revision:4` → `contract_revision:4` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` |
| `negative-fixtures.json` | `fixture_set_revision:16` → `fixture_set_revision:17` | `6dd5cd4dd92c96f58557ca3fe4b15d1f35d4d0b296a8f8d7f03abd3be6137608` | `4d0a03dfb02ba8c4e38c274793b9c8498c787620be5f01bf1fb951db8fe9005f` | `48fdca7da6f0f322968a897271100458c24cac32fcf0bf5db3ef783f75768920` |
| `repository-contract.json` | `contract_revision:18` → `contract_revision:19` | `a087dd84b5bcab7b8b7df25876cd213f6c16910dd1a0cb30daf9c951e20b5359` | `d325131cff7b904937af6763b78da61a46a200d3247644e583536e77d0c3ceb3` | `50137016e7c8affbe7e196290067545edf8e47abeb5f272ca8f10a57955804e3` |
| `runtime-authz-contract.json` | `runtime_contract_revision:15` → `runtime_contract_revision:16` | `655653f2728a517b464abb813c79effe5ac029e03214771e49d21ce1b585ba35` | `cebcc315d9b171b226a438fe9c2e4b9c092d8cb7b682dc84428753726216e05e` | `d9de0ca6eb483398f2de602ca91fb469fb01cf178075d7d4d9480c0183aabba7` |
| `tenant-context-allowlist.json` | `contract_revision:15` → `contract_revision:16` | `b1036cbf01195a1849c911c276f005a112a1f0e0a8c0cafbfa5fa2a6104e74dd` | `7d50b29909a7a17223806c24f6d9c302284bce2981dd82170dad0d7fc6d5db61` | `1fb12e41e45ba544f05bc7afb9659b183474a711227435bdcceacaf2d4456b67` |

外部検査器`scripts/check_tenant_boundary_bypass.py`のsnapshotは、#132既受理before `c3e52f7d9366f5453527481f18b8085e7f976e366da584495a267dafd5b1e9fd` → #141候補after `c6fbf8c9cb62a2c1bab2a3cf520eb5d9bddd512786762bf5639e33b60125f65d`。比較corpus入力digestは #132 `7237caf566a8ca34699552f2aeab1f787ae45cd3bb902c08c55d40d4e788f5d0` → 候補 `e73ef2743d03d97630516b4f51db0f8ee648fe069ab4c3bd51c83febff84986e`。候補9資産と外部参照の実内容を再計算し、案のSHA-256と全件一致した。製品登録は0件、U-S1の既受理実装と履歴を保持し、B/C登録・権限拡張はない。

コア領域敵対レビュー第1回は **否決 P0=1/P1=1/P2=0**。P0はTypeDecoratorによるtenant bindのSQL差替え、P1はスカラーSELECTに対する複数戻り列宣言であり、両方採用した。第2回の最初の呼出しは実行環境の安全フィルタで回答がなく、6.3(6)により回数へ算入しない。同一回の静的再依頼は **否決 P0=2/P1=0/P2=0**。P0は戻り列型と組み込み型インスタンスからのSQL変更。両方を採用し、登録元のSQLAlchemyオブジェクトを実行用に再利用せず、検証済み関数ID・入力宣言・戻り列名から安全なSQLを新規組立てするよう変更した。直接TypeDecorator、dialect別variant、戻り列型、単一列の余剰宣言を負例で確認した。第3回は6.3のP0例外で、この是正差分に限定して依頼中。追加のP0が残れば規約どおりPO裁定へ進む。

検査: backend Ruff format/check・tyと関連非DB423件、隔離PostgreSQLの関連35件、root Ruff/ty・core-guard/凍結アーカイブ296件、履歴検証を除いた迂回試験343件が合格。固定関数試験は再組立て修正後23件合格。`check_frozen_baselines.py --invariants-only`は合格。完全な迂回検査は履歴末尾が#132で今回の8資産afterへ未追随のため不合格、corpus runnerは同じ未受理履歴に依存する2件が不合格（27件合格）。これらを緩和せず、7.7再受理・履歴追記後の最終検査へ残す。#141の旧HEAD `0b203dcd`のCIは新候補のCIではない。人間逐行確認欄は未記入のまま。

第3回は**否決 P0=1/P1=0/P2=0**。SQL再生成に使った`func`属性アクセスが関数名末尾の`_`を落とし、検証したidentityと実行identityが異なる点を採用した。検証済みschema・関数名を`Function`へ直接渡す修正と、末尾`_`の回帰試験を加えた。現修正後、固定関数試験24件、backend関連非DB425件、隔離PostgreSQLの関連35件、root core-guard/凍結アーカイブ296件、履歴依存2件を除いた迂回試験343件、backend/root Ruff・ty、凍結不変条件、`git diff --check`が合格。9資産と宣言済み外部snapshotの候補digestは全件不変。第3回でP0が残ったため、**第4回のP0限定差分レビューには6.3のPO裁定が必要**。裁定前に追加レビューを実施せず、現候補を敵対レビュー完了・ステップ2最終完了・7.7再受理済み・新基線CI成功とは扱わない。PR #141はDraft、リモートHEADは旧`0b203dcd`、ローカルmergeは未コミット・未push、本人逐行確認は空欄のまま。

PR #141本文の旧基線資料に逐行確認のチェック7件が入っていたが、実施記録は空欄だった。新基線の本人確認証跡として誤用しないよう、本文のチェック7件をすべて空欄へ戻し、#132後の候補が未push・7.7再受理と敵対レビュー未了である旨を追記した。本人の実施記録は代記していない。これはPR本文のみの更新で、製品差分・受理値・リモートHEADは変えていない。

POは第3回P0の関数名是正と影響箇所だけを対象に**第4回の独立敵対レビュー1回**を許可した。実施直前に`origin/develop=966d7a38aa8dab2113c1d8ec6d30e5d32088ede5`、ローカルHEAD=`0b203dcdd5831c881943657ec915dc96fc3724a4`、候補全差分SHA-256=`9693f3888e05a05f4455c1608637694cbca8c5f018c7455ffb6b7d1898d9f956`、対象2ファイル修正差分SHA-256=`719f7e0251fad6303eae9a2fe15565839d5f8992134e0736f864b3955f9d2570`、7.7記録案SHA-256=`561eaa7e3e90da68135c7f28f301bfc5a0887086cffc6b9f0efa080505e713c7`を固定した。査読後に両差分SHAが不変であることを再確認した。

第4回は**否決 P0=1/P1=0/P2=0**。第3回の末尾`_`落ちP0は解消と判定した。一方、`public.next_value`のようにSQLAlchemy PostgreSQLコンパイラの特殊関数名へ一致すると、構造検証を通った通常の`Function`が実行前コンパイルで失敗するP0を指摘した。採用して、同コンパイラが特殊扱いする関数名を登録時に拒否し、`next_value`と`substring`の負例を追加した。固定関数試験26件、対象2ファイルRuff format/check・backend tyは合格。第4回の許可は1回のみで使い切った。新たな第5回レビューは実施せず、必要ならこの是正差分限定のPO裁定を別途求める。これまでの全文査読・旧基線のClaude一次レビューは維持するが、現在候補の敵対レビュー収束とは扱わない。

POは第4回P0の特殊関数名是正と、identity・引数・戻り契約への影響を対象に**第5回の独立P0限定レビュー1回**を許可した。実施前に`origin/develop=966d7a38aa8dab2113c1d8ec6d30e5d32088ede5`、ローカルHEAD=`0b203dcdd5831c881943657ec915dc96fc3724a4`、候補全差分SHA-256=`ed3db572d2ce35b39c1ee327f8a8f0dfc3da9d71a8ccc29613808bdbb090b932`、対象2ファイル修正差分SHA-256=`feb7778ba97339985054d7202715e8aedfdd09c552c5a75a0cb9ce7a4f07a1fa`、7.7記録案SHA-256=`561eaa7e3e90da68135c7f28f301bfc5a0887086cffc6b9f0efa080505e713c7`を固定した。第5回査読後にも3値が不変だった。

第5回は**否決 P0=1/P1=0/P2=0**。`next_value`のP0は登録拒否と26件の固定関数試験で解消と判定したが、PostgreSQLの識別子長を超えるschema・関数・戻り列名がDB側で切り詰められ、固定identity・列名契約から外れるP0を指摘した。採用して、許可する小文字ASCII識別子をSQLAlchemy PostgreSQL dialectの`max_identifier_length`以下へ制限した。戻り列名の切り詰め後衝突は長い列名自体を拒否して防ぐ。schema・関数名超過、戻り列衝突、上限ちょうどの4試験を追加。使い捨てPostgreSQL 17.11の`SHOW max_identifier_length`は63、dialect値も63。修正後は固定関数30件、backend関連非DB431件、隔離PostgreSQL関連35件、root core-guard/凍結アーカイブ296件、履歴依存2件を除いた迂回試験343件、backend/root Ruff・ty、凍結不変条件、`git diff --check`が合格。9資産と外部snapshot、corpus候補値は全件不変で、受理記録案にも承認者・承認日はない。第五回の許可は使い切ったため、この追加是正の独立再レビューは未実施。第六回が必要なら、6.3に従いこの差分限定のPO裁定を得る。7.7再受理、ステップ2最終完了、マージコミット、push、新基線CI、逐行確認、Draft解除・マージはいずれも未了。

前回チャット報告の「#132受理値＝今回before」の表では、base-allowlist、cache-invalidation、census、db-api、repository、tenant-contextの6行に転記ミスがあった。正しい完全値は本ログの「#132後の7.7再受理実値」表と、受理記録案`change.before.asset_snapshots`を正とする。旧#141受理afterと新#141候補after、受理記録案・資産本体はこの転記ミスでは変更していない。


## 第6回P0限定レビューと#132 before値の機械照合（2026-10-16）

POは第5回の識別子長是正だけを対象に第6回独立レビュー1回を許可した。実施前の`origin/develop=966d7a38aa8dab2113c1d8ec6d30e5d32088ede5`、ローカルHEAD=`0b203dcdd5831c881943657ec915dc96fc3724a4`、全候補差分SHA-256=`ce741f6b2e905c558892f5357bb6aa3a9cd5f191bbfb33534a581733f7dffdc3`、対象2ファイル差分SHA-256=`7797d4a794f50a70c9c7e630b07c5d6e5c95a7a186c6f5bbd67f8d2b1e05ef45`、受理記録案SHA-256=`561eaa7e3e90da68135c7f28f301bfc5a0887086cffc6b9f0efa080505e713c7`を固定した。レビュー後も3 SHAは不変。

#132の受理済み最終履歴`change.after`と#141記録案`change.before`はオブジェクト単位で一致した。`previous_baseline_identifiers`も一致する。`origin/develop`の9基線実ファイルと8外部実ファイルから凍結射影を再計算し、9/9・8/8がbefore案と一致。候補の9基線実ファイルと8外部実ファイルも9/9・8/8がafter案と一致した。9資産の射影bytesは既存または候補snapshotと一致する。外部検査器afterのcontent-addressed snapshotは7.7再受理後に履歴へ反映する未配置候補であり、現時点では現行実ファイルのSHA一致を確認した。比較corpusは旧#141/既受理#132/候補manifestを実ファイルから読み、候補入力を再計算して`455349e70538fb51ccacea52d06277c5c9bca0afb4647c5551b7c4d0f7c3ae52` / `7237caf566a8ca34699552f2aeab1f787ae45cd3bb902c08c55d40d4e788f5d0` / `e73ef2743d03d97630516b4f51db0f8ee648fe069ab4c3bd51c83febff84986e`と確認した。前回報告だけが6行を誤記し、元のJSON案は最初から正しく、バイト変更がないため案SHAは不変。実資産・snapshot・受理履歴の意味差分はない。

|資産|旧報告値（誤）|実値|
|---|---|---|
|`contracts/tenant_boundary/base-allowlist.json`|`93b9d612d6889b8184d25f72e27c362746b48ff331892159664c484f13cb5ba5`|`32bfa4312fb40b0fafe966b7e8b846ba45696e5d94ce9a567d983f8963a111c5`|
|`contracts/tenant_boundary/cache-invalidation-contract.json`|`e24443a1ab637858e59beb87d00e1367e4ebc717d5c9fedcdad93f6a025d4e2d`|`22ed1510c74f331deb566154a8516d68936e34f77ef3e6237d40f7c90d319b55`|
|`contracts/tenant_boundary/census-baseline.json`|`dc67859810105643caeb459758bcaa95ce9bab074911d6750fd9e07802187314`|`939d79fdd71a3f600e1d645d9fc83c1d54701c22d66dda548bdf65b121f5a365`|
|`contracts/tenant_boundary/db-api-inventory.json`|`6d7937e1a9e381813d2a65ce94492b4625007386ec3410951e8d02cf75b4655d`|`73e6337328e374bfef4ee95eb67f3d474bac1a6b96a0b87391877b365871fbdb`|
|`contracts/tenant_boundary/repository-contract.json`|`c85e15c7f0b8fc6a88ce6500d15bf6f3dcb07dca2464b7a85f91c3b641752cbf`|`d325131cff7b904937af6763b78da61a46a200d3247644e583536e77d0c3ceb3`|
|`contracts/tenant_boundary/tenant-context-allowlist.json`|`d325131cff7b904937af6763b78da61a46a200d3247644e583536e77d0c3ceb3`|`7d50b29909a7a17223806c24f6d9c302284bce2981dd82170dad0d7fc6d5db61`|

第6回独立レビューの判定は**否決 P0=1/P1=0/P2=0**。第5回の63バイト超・切詰め衝突P0は解消。新P0は`select.fixed_probe`のような予約語schemaを登録できるが、SQLAlchemyの正規化済み`Function`が`SELECT select.fixed_probe(...)`と未引用でコンパイルされ、実PostgreSQLでは構文エラーになること。使い捨てPostgreSQL 17.11で`"select".fixed_probe(...)`の成功と未引用の構文エラーを確認した（独立レビュアは隔離DB利用不可で実DB試験未実施、その不足を担当側で補った）。同レビュアは候補のbefore/after各9資産・8外部の実SHA照合も再実施し、訂正に疑義なしとした。

**採否**: P0を採用。現在の登録境界は未収束で、製品差分の追加修正と第7回レビューはまだ実施しない。修正案は、schema・関数・入力・戻り列を一つのDB識別子ポリシーで検証し、ASCII小文字・63バイト以下に加えて、SQLAlchemy PostgreSQLの識別子preparerが引用を要する名前を登録時に一律拒否すること。個別予約語の羅列ではなく、生成する未引用SQLと登録宣言の同一性を条件にする。正規化後のscalar/table-valued文のコンパイルを負例と併せて確認し、B/Cの実登録前には隔離PostgreSQLでschema修飾関数のOID/引数型と戻り列名・型の解決先を宣言と照合する。影響はAの登録検証と負例試験、B/Cの将来登録契約と実DB結合試験で、Aの製品登録0件、9資産の意味・digest、#132の既受理履歴には影響しない見込み。次の是正・独立レビューには6.3の追加PO裁定を要する。7.7再受理も未了。マージコミット、push、本人逐行確認、Draft解除・マージは進めない。

## 第6回P0の一括是正候補と横断試験表（2026-10-16）

POは予約語schemaのP0に対し、4種類の名前へ共通規則を適用する実装・負例・隔離DB検証と、その候補に対するP0/P1限定の追加独立レビュー1回を承認した。この裁定は7.7再受理、本人逐行確認、Draft解除・マージを含まない。`_valid_db_identifier`は小文字ASCII・PostgreSQL dialectの識別子長上限に加え、同dialectの`identifier_preparer.quote(name) == name`を要求する。個別予約語表は追加せず、未引用で再生成するSQLで同じ名前として表せない場合を一律拒否する。schema・関数・入力・戻り列はすべてこの1関数を通る。製品関数登録は0件のまま。

|問題群|Aが登録時に保証する境界|自動試験と実測|
|---|---|---|
|引用・大小文字・予約語|4種類すべて同じ未引用識別子ポリシー。不一致なら拒否|`test_registration_rejects_noncanonical_identifiers_across_boundary`の12例（3値×4種）、`test_identifier_policy_matches_postgresql_unquoted_compilation`。隔離DBでは`"select"`は解決し、未引用`select`は構文エラー、修正後の登録は拒否|
|63バイト上限・切詰め衝突|4種類の64バイト名を拒否し、63バイト名を保つ|同パラメータ試験の4例、既存の関数/戻り列衝突試験。隔離DBの63バイトschema・関数・戻り列を`pg_proc`と実カーソル名で照合|
|SQLAlchemy特殊扱い|`visit_<function>_func`に一致する名前を拒否し、再生成した`Function`を実行する|`next_value`/`substring`の負例、末尾`_`の完全一致試験、PostgreSQL dialectコンパイル|
|bind方式と任意SQL|exact順序・型、`literal_execute`/`expanding`/TypeDecorator/variant/追加SQLを拒否|既存の固定登録負例、改変bindと結果型の試験|
|宣言と実関数|Aはschema・関数・bind・戻り列の宣言と生成SQLの綴り・形を固定。DB関数の存在/ACLはA製品登録0件では検証対象がない|隔離DBの試験専用関数でOID所在・引数`uuid,text`・戻り列・実行結果を照合。B/Cの実登録時には各実関数のOID・引数型・戻り列名/型、owner/EXECUTE/RLS/GUCと直呼出し拒否を個別ゲートで照合|

検査: backendのRuff format/check・tyは合格、関連非DB **235 passed / 18 deselected**、固定登録試験 **47 passed**。使い捨てPostgreSQL 17.11では63バイトのschema・関数・戻り列が実`pg_proc`とカーソル列に一致し、予約語・大小文字・長さ超過の登録を拒否。root Ruff/ty、core-guard **260 passed**、凍結不変条件は合格。rootの広い任意試験では、7.7未受理で履歴末尾が#132のままという既知の9失敗に加え、2回目の並列再実行中に`/tmp`容量不足で67失敗が発生した。自分の2実行が作った一時ディレクトリのみ削除して容量を回復し、core-guardを単独・非並列で再検証した。広い失敗を製品検査合格へ読み替えない。7.7履歴・snapshot確定後の完全再実行は別ゲートに残す。

## 追加独立レビュー1回の採否と最終反映候補（2026-10-16）

PO許可の追加レビュー1回は、全候補差分SHA-256=`732f81a2d4fb193913284b5e4cb6a09914499517801e827a2e2d966a2d5a710f`、対象2ファイル差分SHA-256=`ecef4f9b6421690eb6d9bfa29c8fb95c5f4fcef669903af2ce86f5b091aeb103`で固定して実施した。判定は**否決 P0=1/P1=0/P2=0**。予約語・引用・長さの是正自体に新指摘はない。P0は`pg_temp.fixed_probe`が文字規則を通ってしまう点。`pg_temp`は接続ごとの一時schemaへの別名で、固定関数identityとして受理すると接続ごとに解決先が変わる。指摘を採用した。独立レビュアはread-only環境で実DB試験を実施できず、担当側が使い捨てPostgreSQL 17.11の同時2接続で`pg_temp_0`と`pg_temp_1`へ分かれる事実を確認した。

最終反映候補は共通のDB識別子規則を維持したうえで、schemaだけに追加で必要な**固定アプリケーションschema境界**を設ける。`pg_`で始まるPostgreSQLシステム/一時schema群と`information_schema`を登録時に一律拒否する。個別の予約語や`pg_temp`だけの例外追加ではない。`pg_temp`、物理一時schema名、toast一時schema名、`pg_catalog`、`information_schema`の5負例を追加。既存の`public`、`public_`、63バイトの通常schemaは許可を維持。製品登録0件、B/Cの個別DB関数登録・権限は変更しない。

最終反映後の検査はbackend Ruff format/check・ty、固定関数**52 passed**、関連非DB**240 passed / 18 deselected**、root Ruff/ty・core-guard**260 passed**・凍結不変条件・`git diff --check`が合格。隔離DBの同時2接続は別々の一時schemaへ解決され、修正後の登録は拒否した。前節の63バイト実関数/列照合も合格。rootの履歴依存の赤は7.7未受理のまま緩和しない。9資産のbefore/afterと8外部実ファイルの候補SHA、比較corpus、7.7記録案SHAは不変。候補記録に承認者・承認日はない。

この`pg_`/`information_schema`反映は**追加レビュー後の差分**であり、独立レビュー済みとは表示しない。許可された1回を使い切ったため、再レビューを自動追加しない。6.3の最終反映規律に従い、承認者がP0採否と最終反映差分を確認する。追加の独立レビューを要するとPOが判断する場合は別裁定。7.7再受理、本人逐行確認、Draft解除・マージは別ゲートのまま。ローカルマージ候補は未コミット・未push。

## #132後の7.7再受理と最終検査での停止（2026-10-16）

POは今回の会話で、#132→#141の9資産の識別値・完全なbefore/after射影、外部snapshot、比較corpus入力値と受理記録案SHA-256 `561eaa7e3e90da68135c7f28f301bfc5a0887086cffc6b9f0efa080505e713c7`を7.7として再受理した。承認者は明示指定の**山田正輝**、承認日は実際の今回の承認日（JST **2026-10-16**）とする。2026-10-15の旧#141受理日を再利用しない。前後値の完全表は本ログの「#132後の7.7再受理実値」、6行の誤記訂正と機械照合は「第6回P0限定レビューと#132 before値の機械照合」のとおり。

今回の記録は`base-allowlist.json`の#132受理済み20件目を保持し、その後へ実PR ID `masaki1025/pitchlog#141`の21件目として1件追記した。記録の本文は上記SHAの候補JSONと同一で、追加欄は`approved_by`/`approved_on`のみ。after射影8件と外部検査器1件のcontent-addressed snapshotを配置し、既存before参照を変更しない。候補の比較corpus入力digest `e73ef2743d03d97630516b4f51db0f8ee648fe069ab4c3bd51c83febff84986e`は現行manifestと実入力で一致。8資産のafter値、9資産の識別値、外部snapshotの実バイトを再計算して受理値と一致した。A製品関数登録は0件、B/C登録・権限拡張はない。

ローカル`origin/develop=966d7a38`の取込みと7件の競合解消はマージコミット`c18e6613`で確定した。今回の7.7反映と第6回P0後の最終修正は、承認済みAのステップ2コミットへまとめる予定だった。最終反映の独立再レビューは未実施であり、POはこの残余を認識して修正の採用を承認した。本人逐行確認は未実施のまま。

履歴とsnapshotを作業ツリーへ配置した後、専用一時領域`/var/tmp/pitchlog-tsk550-pr141-20261016`を使って`check_tenant_boundary_bypass.py --base-ref origin/develop`を実行したところ、`function_operations.py:206,209`の`sqlalchemy.select`がTB005、`:210`の`builtins.object.__setattr__`がTB007となり不合格だった。前段の履歴未受理エラーが解消して初めて到達した検査である。`check_frozen_baselines.py --invariants-only`と`git diff --check`は合格したが、全件検査・ステップ2完了・新HEADのCI合格には読み替えない。追加の許可シンボルまたはTB007例外を導入すると、受理済み9資産のafter射影の一部、および外部検査器snapshot・corpus入力が変わる可能性があるため、今回の7.7受理値をそのまま最終化できない。対象は固定関数SQL生成の正規許可境界と、`TenantContext`を含まない凍結登録オブジェクトへの初期化操作である。条件5の緩和を隠す回避は行わず、差分・再導出値・必要なレビューと再受理をまとめて人間判断へ戻す。受理履歴とsnapshotは未コミット候補として保持し、製品差分のpush、Draft解除、マージは停止する。

## TB005/TB007限定是正の候補と7.7再導出（2026-10-16）

POは既存の固定関数実行器に必要なTB005/TB007の最小候補作成・試験・digest再導出を許可した。既存境界ではSQLA_SELECTはallowed_symbolsの専用関数で表現できるため、`_build_fixed_function_statement`へ固定文生成を切り出し、この完全修飾シンボルにSQLA_SELECTだけを宣言した。`object.__setattr__`は既存の許可宣言では扱えないため、検査器で`FunctionOperationRegistration.__post_init__`の`self.statement`に、5引数を固定した専用生成関数の戻り値を設定するAST形だけを許した。ファイル全体・汎用SQL・任意objectの除外は追加していない。未登録関数のSELECT、text、INSERT/UPDATE、別属性・別対象・別クラス・別値の負例はTB005/TB007を維持した。製品関数登録は0件。

root全件試験では**29589 passed / 38 failed / 2 skipped**。失敗のうち32件は旧corpus digestのまま検査したこと、6件は新TB007緩和が既存censusの帰属テストから漏れていたことによる。censusは検査器の同じ厳密AST条件を使う帰属照合に追随し、別scopeの負例を追加した。root全件の再実行は正式値未受理のためcorpus依存の赤が残る。是正後のroot迂回・census関連は**422 passed**、CI用`python tests/test_census_baseline_check.py`は`census-baseline: OK`。backend全件はDB反復が長く、7分22秒・78 passedで中断した。関連非DBは**130 passed**（固定関数境界52件を含む）。root/backendのRuffとty、backend Ruff format、単独迂回検査、凍結不変条件、git diff --checkは合格。

第6回後に許可された独立レビュー1回は既に使用済みで、今回の検査器・census追随変更には既存の未使用枠がない。追加レビューが必要なら6.3に従い、このTB005/TB007反映差分と影響箇所に限定したPO裁定を求める。レビュー未実施を実施済みへ読み替えない。受理済み#141履歴21件目と9件のsnapshotは作業ツリーに保持し、新しい値へ書き換えていない。候補記録は作業ツリー外の`/var/tmp/pitchlog-tsk550-pr141-20261016/candidate-7.7-record.json`に承認者・承認日なしで保存し、SHA-256は`e8cea97bb179ba67727fd1b855dc3ab0dafc82b9a6606d6d84defcaefb807281`。新afterのcontent-addressed snapshotも同じ専用一時領域だけに保全した。

新7.7記録案 SHA-256: e8cea97bb179ba67727fd1b855dc3ab0dafc82b9a6606d6d84defcaefb807281

|資産|#132 after / #141 before|今回受理済み#141 after|是正候補 after|
|---|---|---|---|
|`contracts/tenant_boundary/base-allowlist.json`|`32bfa4312fb40b0fafe966b7e8b846ba45696e5d94ce9a567d983f8963a111c5`|`a7e75d1a2bb68c6b9e922dcf2d28c6425ac1d2514db478aea5951279b42b2074`|`4fe17fd51990fc969de873ef4f22487061c2d17dab94892867c7846b4536bd37`|
|`contracts/tenant_boundary/cache-invalidation-contract.json`|`22ed1510c74f331deb566154a8516d68936e34f77ef3e6237d40f7c90d319b55`|`e9eb7eeddfdbaf353505911a8a50c772d2c005b09b16d628b1584d2f4df508e3`|`5c3b41eeff96f89b141ef351ff6f8032af334d65c7ada77185b1c5d3f733db97`|
|`contracts/tenant_boundary/census-baseline.json`|`939d79fdd71a3f600e1d645d9fc83c1d54701c22d66dda548bdf65b121f5a365`|`89ef72d277f2ceed0c6f8fe57ec2614e8737bc8d630e781a5e750c6e736e3c17`|`65d7a62b8030f1ab388a1b40511639c9b52d33917ec615c7addc9245dbc8f4cd`|
|`contracts/tenant_boundary/db-api-inventory.json`|`73e6337328e374bfef4ee95eb67f3d474bac1a6b96a0b87391877b365871fbdb`|`a33b21815d133b9e655c3e7ff08ee4ec532c96cf04dd6735adaec38499082a5d`|`b41f41daa7f33dae4abc8dc832775607dea5844cbe2d6c195e7851d44e6207ba`|
|`contracts/tenant_boundary/frozen-inputs.json`|`c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63`|`c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63`|`c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63`|
|`contracts/tenant_boundary/negative-fixtures.json`|`4d0a03dfb02ba8c4e38c274793b9c8498c787620be5f01bf1fb951db8fe9005f`|`48fdca7da6f0f322968a897271100458c24cac32fcf0bf5db3ef783f75768920`|`79b6a0b2d62629c3381fa9fcd25fcf686f07b06c335189542b663ea42869d68a`|
|`contracts/tenant_boundary/repository-contract.json`|`d325131cff7b904937af6763b78da61a46a200d3247644e583536e77d0c3ceb3`|`50137016e7c8affbe7e196290067545edf8e47abeb5f272ca8f10a57955804e3`|`3243fab16988d892755f1c3f25590663c7f72ed8bd9444c916c6df81c55b3ae2`|
|`contracts/tenant_boundary/runtime-authz-contract.json`|`cebcc315d9b171b226a438fe9c2e4b9c092d8cb7b682dc84428753726216e05e`|`d9de0ca6eb483398f2de602ca91fb469fb01cf178075d7d4d9480c0183aabba7`|`ddd374b5c9ec51ec93a85b3a7e46dabc47023e7c1e4b64bb7bcb1128e93a51b8`|
|`contracts/tenant_boundary/tenant-context-allowlist.json`|`7d50b29909a7a17223806c24f6d9c302284bce2981dd82170dad0d7fc6d5db61`|`1fb12e41e45ba544f05bc7afb9659b183474a711227435bdcceacaf2d4456b67`|`69044390b66610ebbf43297ed6ef261806ff746489ae4858ad3b52adc7362058`|

|外部ファイル|#132 after / #141 before|今回受理済み#141 after|是正候補 after|
|---|---|---|---|
|`.github/workflows/ci.yml`|`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`|`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`|`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`|
|`scripts/check_tenant_boundary_bypass.py`|`c3e52f7d9366f5453527481f18b8085e7f976e366da584495a267dafd5b1e9fd`|`c6fbf8c9cb62a2c1bab2a3cf520eb5d9bddd512786762bf5639e33b60125f65d`|`59e8125880ab7447aa37482e59cc68f6e9eb27ae21173755794127f2c7d198b4`|
|`scripts/frozen_archive.py`|`66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6`|`66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6`|`66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6`|
|`scripts/frozen_history.py`|`0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8`|`0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8`|`0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8`|
|`tests/domain/test_boot_seal.py`|`bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2`|`bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2`|`bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2`|
|`tests/test_census_baseline_check.py`|`4dcb0ee5450a0d8bbd03a3249397943766528b6b338ac3a99cb674150cdbf4bf`|`4dcb0ee5450a0d8bbd03a3249397943766528b6b338ac3a99cb674150cdbf4bf`|`f36af6c1b4ee52658a54e2811b276e409143ec83cb0d39cf9035ab1ee3d6a830`|
|`tests/test_ci_wiring.py`|`36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396`|`36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396`|`36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396`|
|`tests/test_plan_generation.py`|`9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe`|`9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe`|`9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe`|

- corpus 入力digest: 受理済み `e73ef2743d03d97630516b4f51db0f8ee648fe069ab4c3bd51c83febff84986e` → 是正候補 `aacc5f04c0fe5605bf30efbf371fbf3c069031e5447d84d864005394423cedd8`
- 9資産の識別値は現行#141候補の宣言どおり。
- 受理済み履歴21件目は未変更。是正候補の履歴行は未作成。

## TB005/TB007 追加独立レビューと最終候補（2026-10-16）

POが許可した追加独立レビュー1回は、レビュー前候補の`git diff --binary` SHA-256 `6ee1d3e2907342138f6a77f35c4175c49f2a1095766c8a24684d4c0b9eaaee5b`と7.7案SHA-256 `e8cea97bb179ba67727fd1b855dc3ab0dafc82b9a6606d6d84defcaefb807281`を固定して実施した。対象は固定SQL許可シンボル、TB007初期化条件、census帰属、関連負例と影響箇所だけであり、既済み全文レビューは繰り返していない。独立レビュアの結果は**否決 P0=0 P1=2 P2=0**。

|指摘|採否と反映|
|---|---|
|P1: `object.__setattr__`の許可はAST形のみで、固定builderを同名lambdaへ再束縛してもTB007が0件になる。censusも同じ述語を使用。|採用。固定builderと引数生成関数の一意なモジュール定義、保護したSQL生成シンボルの正規import、局所・モジュール再束縛、`self`再束縛を検査し、条件を満たさない場合はTB007を維持。censusも同じ束縛条件に追随。|
|P1: 許可builder内の`select`を`literal_column`または宣言外`Function`に差し替えてもTB005が0件になる。|採用。固定builderと引数生成関数の本文を承認済みのSQL構築ASTと照合し、別関数、任意SQL式、別importの負例を追加。|

関連する既存の別シンボル、別クラス、別属性、別対象、text、INSERT/UPDATEの拒否も維持した。**追加レビュー枠は使用済みで、今回の採用反映差分自体は独立再レビューを受けていない。**6.3の上限到達時の終端に従い、採否一覧とこの最終差分を人間確認へ上げる。7.7再受理、本人逐行確認、Draft解除、マージは別条件であり、受理済み#141の履歴とsnapshotは旧値のまま保持する。新案に`approved_by`/`approved_on`は未記入。

# #141 TB005/TB007 是正候補の機械算出値

新7.7記録案 SHA-256: 494e1a6bd74c8b68acc426cd87fa885f309c10cf36430f90559f2ba055b76b85

|資産|#132 after / #141 before|今回受理済み#141 after|是正候補 after|
|---|---|---|---|
|`contracts/tenant_boundary/base-allowlist.json`|`32bfa4312fb40b0fafe966b7e8b846ba45696e5d94ce9a567d983f8963a111c5`|`a7e75d1a2bb68c6b9e922dcf2d28c6425ac1d2514db478aea5951279b42b2074`|`0642f1ce39b037248e2fcc32ecc44950887d379d563a564bdcd9d97b31d4b515`|
|`contracts/tenant_boundary/cache-invalidation-contract.json`|`22ed1510c74f331deb566154a8516d68936e34f77ef3e6237d40f7c90d319b55`|`e9eb7eeddfdbaf353505911a8a50c772d2c005b09b16d628b1584d2f4df508e3`|`161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f`|
|`contracts/tenant_boundary/census-baseline.json`|`939d79fdd71a3f600e1d645d9fc83c1d54701c22d66dda548bdf65b121f5a365`|`89ef72d277f2ceed0c6f8fe57ec2614e8737bc8d630e781a5e750c6e736e3c17`|`c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f`|
|`contracts/tenant_boundary/db-api-inventory.json`|`73e6337328e374bfef4ee95eb67f3d474bac1a6b96a0b87391877b365871fbdb`|`a33b21815d133b9e655c3e7ff08ee4ec532c96cf04dd6735adaec38499082a5d`|`66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999`|
|`contracts/tenant_boundary/frozen-inputs.json`|`c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63`|`c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63`|`c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63`|
|`contracts/tenant_boundary/negative-fixtures.json`|`4d0a03dfb02ba8c4e38c274793b9c8498c787620be5f01bf1fb951db8fe9005f`|`48fdca7da6f0f322968a897271100458c24cac32fcf0bf5db3ef783f75768920`|`3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82`|
|`contracts/tenant_boundary/repository-contract.json`|`d325131cff7b904937af6763b78da61a46a200d3247644e583536e77d0c3ceb3`|`50137016e7c8affbe7e196290067545edf8e47abeb5f272ca8f10a57955804e3`|`15c416e962e559312bc26502895d2718e508299459bbb6df3258758edf5c1004`|
|`contracts/tenant_boundary/runtime-authz-contract.json`|`cebcc315d9b171b226a438fe9c2e4b9c092d8cb7b682dc84428753726216e05e`|`d9de0ca6eb483398f2de602ca91fb469fb01cf178075d7d4d9480c0183aabba7`|`a335d85ba04eb9d7f002009ecaf2f7229f410c2a5335929b8d2ddf960af0a53a`|
|`contracts/tenant_boundary/tenant-context-allowlist.json`|`7d50b29909a7a17223806c24f6d9c302284bce2981dd82170dad0d7fc6d5db61`|`1fb12e41e45ba544f05bc7afb9659b183474a711227435bdcceacaf2d4456b67`|`16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2`|

|外部ファイル|#132 after / #141 before|今回受理済み#141 after|是正候補 after|
|---|---|---|---|
|`.github/workflows/ci.yml`|`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`|`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`|`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`|
|`scripts/check_tenant_boundary_bypass.py`|`c3e52f7d9366f5453527481f18b8085e7f976e366da584495a267dafd5b1e9fd`|`c6fbf8c9cb62a2c1bab2a3cf520eb5d9bddd512786762bf5639e33b60125f65d`|`3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883`|
|`scripts/frozen_archive.py`|`66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6`|`66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6`|`66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6`|
|`scripts/frozen_history.py`|`0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8`|`0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8`|`0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8`|
|`tests/domain/test_boot_seal.py`|`bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2`|`bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2`|`bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2`|
|`tests/test_census_baseline_check.py`|`4dcb0ee5450a0d8bbd03a3249397943766528b6b338ac3a99cb674150cdbf4bf`|`4dcb0ee5450a0d8bbd03a3249397943766528b6b338ac3a99cb674150cdbf4bf`|`163cb41e19e9d24ee2b30037f5f6614800ed193c21d1c31cc325371f25e9edfd`|
|`tests/test_ci_wiring.py`|`36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396`|`36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396`|`36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396`|
|`tests/test_plan_generation.py`|`9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe`|`9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe`|`9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe`|

- corpus 入力digest: 受理済み `e73ef2743d03d97630516b4f51db0f8ee648fe069ab4c3bd51c83febff84986e` → 是正候補 `0f719807eb1f971e01849ceab0d1c5b0f4abeabf2d7977c495aec09944792c93`
- 9資産の識別値は現行#141候補の宣言どおり。
- 受理済み履歴21件目は未変更。是正候補の履歴行は未作成。

### 最終候補の検査内訳

- `TMPDIR=/var/tmp/pitchlog-tsk550-pr141-20261016 uv run pytest -q -n 8 tests/test_check_tenant_boundary_bypass.py tests/test_census_baseline_check.py --basetemp=/var/tmp/pitchlog-tsk550-pr141-20261016/pytest-root-focused-final --tb=short`: **430 passed**。`tests/test_census_baseline_check.py`単独CI検査も`census-baseline: OK`。
- backend固定関数境界試験: **52 passed**。root Ruff/ty、backend Ruff format/check/ty、`check_tenant_boundary_bypass.py --base-ref origin/develop`、凍結不変条件、`git diff --check`は合格。候補manifestで比較corpus入力digestを再計算・照合。9/9の射影・snapshotと8/8の外部実ファイルSHAを実ファイルから照合。
- 前回のroot全件 **29589 passed / 38 failed / 2 skipped** は旧corpus固定値32件と、当時未追随だったcensus帰属6件による。census帰属は是正し関連430件を再実行したが、root全件の最終候補再実行は未完。backend全件も前回78 passedで中断したまま。旧履歴・corpus値が正式受理されるまで、固定値検査の不合格を緑へ読み替えない。
- 今回の単独逐次実行は旧HEADだけで作る合成リポジトリにも新builderを必須にした検査器の誤りで1件失敗した。旧HEADに新builderの参照がない場合は本限定検査を適用しないよう修正し、該当1件と最終430件で合格。最初の並列実行とcensus単独実行は共有`/tmp`の容量不足で不完走となったため、共有ファイル・共有ロールを操作せず、専用`/var/tmp`に切り替えて再実行した。容量不足は製品不具合ではない。
- ローカル`check_frozen_baselines.py --ci`/`--acceptance`はGitHubイベント情報が無く実行条件を満たさない。7.7正式受理後の新履歴・snapshot・corpus反映、全件検査、push後の新HEAD CIは未実施。今回の受理値差し替え・pushは行わない。

## TB005/TB007最終候補の7.7再受理（2026-10-16）

POは本会話で、最終候補差分SHA-256 `21aaa523d5c4ef3a9dd80e007cd7d17886aaf6c1844321e1b58e3cb3c376c8aa` のP1 2件と未再レビュー最終反映を採用し、直前表の9資産・8外部ファイル・比較corpusの完全な前後値、および承認者・日付欄のない7.7案SHA-256 `494e1a6bd74c8b68acc426cd87fa885f309c10cf36430f90559f2ba055b76b85` を正式再受理した。実承認者は**山田正輝**、承認実日はJST **2026-10-16**。この判断はPR全体の本人逐行確認ではない。

最新`origin/develop=966d7a38aa8dab2113c1d8ec6d30e5d32088ede5`は取込み済み基線と一致。#132までのコミット済み20件の受理履歴は保持した。同じ`acceptance_id=masaki1025/pitchlog#141`の二重行は7.7検査が拒否するため、未コミットだった旧#141ローカル行を今回受理された行に置換し、developとの差分として#132の後へv2履歴1件を直列化した。旧ローカル行と旧snapshot 9件は専用領域`/var/tmp/pitchlog-tsk550-pr141-20261016/`に保全し、履歴から参照されない新snapshotを正式archiveへ残さない。新after snapshotをcontent-addressed名で配置し、比較corpusを受理値に再pinした。反映後の候補案SHAとcorpus入力digestは上記受理値と一致し、凍結不変条件と迂回検査は合格した。製品登録0件を維持する。

本節記入時点ではステップ2コミット、root/backend全件、push、新HEAD CI、PR本文更新、本人逐行確認は未了。完走結果を後続行に追記する。Draft解除・マージはしない。

## コミット済みHEADの品質ゲートで検出したcorpus差分（2026-10-16）

7.7受理値を反映して`48874400342c54e453006d0673e83a35e7a80a73`へ`(ステップ 2/2)`を1件コミットし、最終HEAD検査を開始した。backend Ruff format/check/ty、root凍結不変条件、core-guardは合格。root `uv run ruff check .`は新規正例fixture `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/function_operations.py`のSQLAlchemy import順序1件(I001)で失敗した。

同fixtureの`sqlalchemy.sql.selectable`と`sqlalchemy.sql.sqltypes`の2行を並べ替える最小是正候補を作成し、root Ruff/ty、正例fixture試験1件、候補corpus入力照合は合格。製品コード、9資産射影、外部8ファイルSHA、7.7受理記録案SHA-256 `494e1a6bd74c8b68acc426cd87fa885f309c10cf36430f90559f2ba055b76b85`は不変。ただし比較corpus入力digestは受理済み`0f719807eb1f971e01849ceab0d1c5b0f4abeabf2d7977c495aec09944792c93`から是正候補`96b217bd1c40a4f98277858618e246c759253e7b11d6a99dfb90cdc524c7a4b7`へ変わる。manifest自身の変更はまだ行っていない。

受理値変更の停止条件に従い、是正は未コミットで保持し、7.7のこのdigestだけの再受理までステップ2コミットのamend、root/backend全件、push、新HEAD CI、PR本文更新は進めない。本人逐行確認・Draft解除・マージも未実施。

## 正例fixtureのimport順序とcorpus入力digestの再受理（2026-10-16）

POは本会話で、正例fixtureのSQLAlchemy import順序1件の是正に伴う比較corpus入力digest `96b217bd1c40a4f98277858618e246c759253e7b11d6a99dfb90cdc524c7a4b7` を7.7として再受理した。旧受理値は `0f719807eb1f971e01849ceab0d1c5b0f4abeabf2d7977c495aec09944792c93`。承認実日はJST 2026-10-16。今回の受理対象はこのdigestの差し替えのみで、9資産・外部8ファイルの前後値と7.7受理記録案SHA-256 `494e1a6bd74c8b68acc426cd87fa885f309c10cf36430f90559f2ba055b76b85` は不変。#132と#141の受理済み履歴21件を維持する。今回の判断はPR全体の本人逐行確認ではない。

manifestのcorpus入力digestを受理値へ更新し、正例fixtureのimport順序と合わせて別コミットにする。コミット済みHEADでroot/backend全件と関連ゲートを再実行し、通過後に通常push・新HEADのCI確認・PR本文更新を行う。本人逐行確認、Draft解除、マージは別判断とする。
