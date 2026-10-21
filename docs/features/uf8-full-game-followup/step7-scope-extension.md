# ステップ7の凍結候補追随範囲の最小追補（未承認）

承認原本SHA-256 `935bac90426571acf1c9a66b8d41ff0097e14232421fc5f80ff966e9f5551cf4` の3節は、CI変更に伴うbase/census/history-snapshots/比較manifestの限定候補を宣言している。実基線8e4698f6dc254439b7d5e0c273cc2aef70cda657の逆依存照合で、同じCIをexternal_filesに持つ追加6資産が確認された。計画3節の「追加波及が判明したら…人間へ計画追補」「未宣言ファイルへ広げない」に従い、実資産は未変更とする。

## 推奨する追補

下表6資産の**候補生成・提示**を計画3節/ステップ7へ追加する。基準の意味・対象集合・検査器・合否規則は変えず、CI外部入力に連動する識別値/射影/追記履歴・snapshotの候補だけを作る。原本の査読3回13件と最終P0限定/最終反映未再査読の履歴は維持し、追加レビュー枠や可決を代記しない。

| 追加資産 | 現識別子 | 後候補 |
| --- | --- | --- |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | `contract_revision:15` | `contract_revision:16` |
| `contracts/tenant_boundary/db-api-inventory.json` | `inventory_revision:15` | `inventory_revision:16` |
| `contracts/tenant_boundary/negative-fixtures.json` | `fixture_set_revision:17` | `fixture_set_revision:18` |
| `contracts/tenant_boundary/repository-contract.json` | `contract_revision:21` | `contract_revision:22` |
| `contracts/tenant_boundary/runtime-authz-contract.json` | `runtime_contract_revision:17` | `runtime_contract_revision:18` |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | `contract_revision:16` | `contract_revision:17` |

候補全体は[完全な前後値](step7-candidate/metadata.json)、[全ファイルと検査説明](step7-candidate/README.md)、[適用可能な差分](step7-candidate/candidate.patch)で確認できる。候補patch SHA-256は `4d0f254c91d124a553a3416cdf95c1a6cd994eb81ce67b0b80d26319f37953fc`。主担当が隔離ディレクトリでgit apply --check/実適用とafter全bytes一致、追加9snapshotの内容SHA一致を確認した。実CI/実資産への適用ではない。

既存23履歴と179snapshotは保持し、新履歴1件/新snapshot9件は未受理候補。CI SHA-256はf12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8から0206d208474482e4e50dbb6993b9771a7ae86282a4d8e5e2598a7a52ec863718、corpus入力はb3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ceから21334bcd53f38962c50a5c968a48a2465ca526e6673e2596b3ba8457898cf835の候補である。

## 承認範囲と別ゲート

この照会は計画の追随対象追加だけで、**7.7の実値受理、担当受理、署名、CI/基準の適用を含まない**。accepted_by/on/signature、履歴のacceptance_id/approved_by/onは空欄を維持する。PR番号と最終受理前後SHAは実PRの同一受理単位が決まった後に再固定し、完全な前後値を改めて人間の7.7受理へ提示する。

別案はCI・凍結候補の追補を保留し、実CI/基準を維持したまま入口とローカルブラウザ検査を部分提出すること。ステップ7の正式完了は未達となるが、独立した画面実装/検査/提出は継続する。App.vueの入口ナビ/ログイン復帰についての別照会も未承認・未適用のままであり、本照会へ混ぜない。
