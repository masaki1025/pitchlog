# TSK-372 §6-5限定正本ゲート 作業ログ

## 2026-10-19 起案

- POは§6-5現文から`games.applied_rules`試合行自身のUPDATE禁止を既承認と推定せず、限定改訂で明文化する方針を採用した。これは最終本文・具体資産・7.7実値の承認ではない。
- 設計書7.6-3後段を適用する。保存後異値UPDATE禁止は新しいDB不変条件であり、実装追随の記録更新ではなく、候補版v0.12の正式7.3審査と人間承認が必要。
- 比較元`origin/develop=ba339cf8bdaac4761b8cf437abaf21763617d064`。初回レビューに適用する7.3は現行approved v1.19、条文コミットSHAはこの比較元（in-review化コミットの第一親）を暫定値とする。初回実行時に再照合する。
- 本文案は初回INSERT・同値/他列UPDATE許容、保存後異値UPDATE拒否、既存行の非補完、訂正migration・復旧の別正式ゲートを明記する。SQLSTATE・トリガ・実revisionは実装範囲に残す。
- #156のmanifest/N3と#152のN3は未コミット編集あり。共有ファイルへは触れない。調整案は#156対象パス解除・実統合→本限定単位→#152追随。各担当の受諾は未確認。

## 7.3第1回（全文、基本枠1/2）採否

- 実モデル`gpt-6-sol`・effort`xhigh`。判定は否決、P0 0/P1 1/P2 1。両指摘は今回候補に起因し、分類は(-)。不採用・未終結の指摘はない。§6-5本文の初回INSERT・同値/他列UPDATE・異値拒否・訂正migration/復旧の別ゲートにはFR-014/P-30との矛盾指摘なし。
- P1: `contracts/authz/shared-preconditions.json:17-19`の`mapping_target.git_blob_digest`も正本ファイルを固定し、`scripts/check_shared_preconditions.py:365`が照合するのに、計画の同一統合境界から漏れた。**採用**。計画の射程・ステップ2・DoDに派生blob digest追随を追加した。値の正式変更・7.7受理は未実施。
- P2: `data-model.md`変更履歴と本計画の参照先が本候補ツリーにない。**採用**。変更履歴はこのツリーにある正本ゲート計画へリンクし、承認元の限定計画をcommit`8a45168a`の`git show`で再現できる形へ訂正した。
- 初回レビュー時の適用7.3はapproved v1.19、条文コミットSHA`ba339cf8bdaac4761b8cf437abaf21763617d064`で暫定記録と一致。採用反映により`確定ゲート周回`を1へ。第2回は本反映差分と影響節を対象にする。

## 7.3第2回（反映差分と影響節、基本枠2/2）採否

- 実モデル`gpt-6-sol`・effort`xhigh`。判定は可決、P0/P1/P2は各0。第1回のP1（派生blob digest）・P2（計画リンク）の反映を確認した。新規指摘、採用反映、不採用、未終結はないため`確定ゲート周回`は1のまま。
- 確定ゲートの基本枠は収束した。最終本文と第1回採否・反映差分を人間承認へ提示する。現時点の正本は`in-review`で、`approved`・索引・manifest・shared-preconditions・受入シート・7.7履歴は正式更新していない。共有パスの編集所有回答と個別実値受理は別に残る。

## 2026-10-20 PO承認とstep 2（派生値・シート）

- PO判断（2026-10-20）: §6-5本文・認可資産＋7.7（revision 17→18）・N3判定を承認。統合順は **#163 → #161 → #162** へ入れ替えた（実装が入った状態で §6-5 由来の2行を1回だけ判定するため。実装欄が `protected=[]` のまま「一致」を記録する不整合を避ける）。
- #163（持ち越しキーの出現番号非依存化）を先に取り込んだ。本ブランチのシート再生成は #163 の生成器で行っている。
- step 2 の実値: `canonical_source.sha256` `7394428…`（`sha256sum docs/design/data-model.md`）、`shared-preconditions` の `mapping_target.git_blob_digest` `c4b22e3…`（Git blob SHA-1）、`games.source_sections` に `6-5` を追加。
- 受入シート再生成: N1 103 / N3 107 / N4 55 / N7 100。§6-5由来の新規行は N3 出現060/061・N1 見出し023/029・N4 `games`・N7 候補046 の6行で、判定は 一致5・対象外1（N7）。
- `games` の不変行列が §5-1/11-1/12-3 の候補欄にも現れるため、実装欄が変わった既判定行（N3 6行・N4 8行・N7 10行）は、**同じ出現・同じ正本・同じ理由の既往判定を再掲**した（新しい判断ではない）。
- 検査: `tests/test_orm_acceptance_sheets.py` 24 passed、`check_docs_status` 0 violations、`check_design_propagation`・`check_doc_coverage` 合格、backend `test_schema_manifest.py` 14 passed。
- 未了（人間）: core-guard の逐行確認（`data-model.md` §6-5 と変更履歴の9行ほか）、版の確定（#156 が先なら v0.13）、マージ。

## 2026-10-21 #172（#161置換）基盤への再適用

- #161 は未マージでクローズされ、置換 **#172**（`fix/tsk372-applied-rules-plan`、develop `caf56347` 起点）へ移された。受け取った統合順は **#165 → #172 → #162**。
- 本ブランチを `origin/fix/tsk372-applied-rules-plan`（`fffe298a`）へ載せ替え、§6-5・派生値・受入シート・計画/worklog を再適用した。旧head `1122cea4` は参照用に残す。
- 再適用後も正本派生値は不変: `canonical_source.sha256` `7394428…`、`mapping_target.git_blob_digest` `c4b22e3…`、`games.source_sections` に `6-5`。シートは N1 103 / N3 107 / N4 55 / N7 100。
- 検査: シート・shared-preconditions・docs 系 357 passed、root `ruff check` / `ty check` 合格、tenant-boundary 迂回検査 ok。
- 既知の赤: `tests/test_check_authz_catalog.py` の3件（product runtime contract / pending / product state）は **#172 の tree でも同一に失敗**する。migration 0033 の2関数を正式認可資産へ反映するステップ4（7.7 正式受理後）が #172 側で未了のためで、本PRの変更起因ではない。ステップ4反映後に解消する。
- base は CI の tenant-boundary 検査が PR 受理モードで `base.ref == develop` を要求するため develop とした。残: #172 の実統合後にマージ。

## 2026-10-21 #172からの引継ぎ受諾（値は暫定）

- #161 は未マージでクローズし、置換は Draft **#172**。統合順は **#172 → #162 → #152**。旧#161由来の履歴・7.7値（revision 18・digest・snapshot）は確定値として扱わない。
- 本PRは #172（`fffe298a`）上へ再適用済みだが、`canonical_source.sha256`・`mapping_target.git_blob_digest`・受入シートの行数/判定・7.7 の各値は **暫定**。版（v0.12/v0.13）も未確定。
- #172 の実統合後に最新 develop から migration 親・正本SHA・manifest/ORM シート・7.7値を再導出する。それまで本PRは Draft のまま維持する。
- 現時点の赤は #172 ステップ4（7.7正式受理後）未反映による認可資産の exact-set 不一致（backend の認可系・root 3件・認可DB 2件）。#172 の tree でも同一に再現し、本PRの変更起因ではない。

## 2026-10-22 #172実統合後の最終再導出（候補）

- #172は2026-10-21に実統合（merge `8a43d044`、head `8b10073e`）。developは当該mergeを含む。`8a43d044`を比較元に本ブランチを載せ替え、§6-5本文・変更履歴・派生値・受入シートを再導出した。
- 版は実developの変更履歴から決めた。最新approvedはv0.11で、v0.12はdevelopに存在しないため、候補は**v0.12**。#170は未統合なので含まれていると仮定せず、将来の後続変更として扱う（v0.13を先決めしない）。
- 正本: `docs/design/data-model.md` §6-5（本文は旧候補と同一）と変更履歴v0.12（in-review）。frontmatterと索引もin-review。本文の人間承認・状態確定は未了で、マージを承認の記録にしない。
- 派生値（最終候補）: `canonical_source.sha256` `e49690fe…`、`source_documents`のdata-model行`git_blob_digest` `c9405534…`、`games.source_sections` `["5-1","6-5","11-1","12-3"]`。
- 受入シート: N1 103 / N3 107 / N4 55 / N7 100。比較元`8a43d044`と意味・対応が同一の既存判定だけを持ち越した。**新規・意味変更の6行は判定空欄**: N1 見出し023/029、N3 出現060/061、N4 `games`、N7 候補046。旧候補の一致5・対象外1は再掲しない。本人の逐行確認は未了。
- 7.7: #172の受理はtenant_boundaryの9資産（runtime_contract_revision 18等）の範囲に限る。本変更はdata-model・schema-manifest・shared-preconditions・ORMシートだけで、`base-allowlist`・`frozen-inputs`・`census-baseline`等の凍結対象を変更しないため、追加の7.7受理は不要（最終差分で確認）。旧#161の受理値・digest・snapshotは参照しない。
- migration: #172の`0033_game_rules_immutable.py`と受理履歴を保持し、編集しない。本PRはmigrationを追加しない。
- 旧#161構成の暫定値（`7394428…`/`c4b22e3…`/旧シート判定）は履歴であり最終値ではない。
- ローカル検査: `check_docs_status` 0 violations、backend `test_schema_manifest.py` 14 passed、root `ruff check` / `ty check` 合格。`test_orm_acceptance_sheets.py::test_acceptance_sheet_judgments_are_complete`は上記6行が未判定のため失敗する（人間記入待ち。空欄を判定で埋めて回避しない）。
- 残（人間）: 本文の承認・状態確定、6行の判定、本人逐行確認、Draft解除・マージ、既存DB適用。
