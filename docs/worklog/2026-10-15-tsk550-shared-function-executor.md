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
