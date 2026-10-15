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
