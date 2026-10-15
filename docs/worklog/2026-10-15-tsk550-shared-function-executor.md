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
