# ステップ7: CI・凍結資産の未受理候補

## 現行候補（#169統合後、未受理）

公表済み`origin/develop`は`161ab6182577e8d4875406d5e48f42f9f2c2c130`、生成時feature HEADは`1c3f000a8a76494df3410dde541487396a3d0370`、merge-baseは`161ab6182577e8d4875406d5e48f42f9f2c2c130`。`metadata.json`は正式入力340パスの現在working tree・HEAD・公表基線・生成時HEADのGit blobと、生成器SHA-256 `bab5140635e056640271af7044e0b4a121b51d860c32922f8bbb3e8b1ac4e604`を固定する。`--check`はこの出所と実装コード逆依存閉包を再照合する。旧`9136...`基線の候補値はこの節の現行値へ置き換わった。

候補は**CI、影響8資産、生成3モジュール、比較manifestの完全13 before/after bytes**、適用patch、新snapshot9件で構成する。既受理を含む履歴24件と既存snapshot180件は前後で同じ値を保持し、U-F8の未受理履歴1件を追記する。metadataの`accepted_by/date/on/signature`、追記履歴の`acceptance_id/approved_by/on`は空欄。#165等の受理・署名をU-F8へ転記しない。実CI・正式`contracts/`・実manifest・backend製品への適用は0。

追加6 JSONと生成3 Pythonの**正式パス9件**は[追補v3](../step7-scope-extension-v3.md)の未承認提案であり、7.7の正式実値受理とは別の人間判断を要する。旧[追補v2](../step7-scope-extension-v2.md) SHA `253c06e8debb7e399d309a2dd6a0968b05325ecc983543bd7762663767efe63b`と旧提案SHA `899abea1cdd8e7e3ea069a65c8b8ff79eaf0fdfe40ce2687ccf2559011200f59`は固定履歴として保持する。両判断待ちを独立した封鎖UIやローカル候補提示の停止条件にはしない。

### 完全な前後値

| ファイル | before SHA-256 | after候補 SHA-256 |
| --- | --- | --- |
| `.github/workflows/ci.yml` | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `9bafa8ae1cb7b22b2b47301f2ffb8a5b2a7aeebad3f2f4d5faa5dd937dc2bd65` |
| `backend/src/pitchlog/authz/runtime_contract.py` | `9c12b249f53cacec65c7517d3c2e2666042b04756a3c056851064e437356a155` | `17751948aefc104028828825edf86b80782a824ab12dee56641ae20b902e6a56` |
| `backend/src/pitchlog/repositories/repository_contract.py` | `30d1fffb8a710d0edc3b160a1c586997459482b565effc53c45e8480c86ac543` | `506aceaf7531e2740609db1040e8c96ec3df85dbbe7dd574cc2ce32be7673bf1` |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | `523f763c57119a755b8d633e4834f29c743a4a5bff6482ca287548fb041b7f28` | `335a70402934030b64d63861e47787ec3db3c802720af66bba0f316558b84461` |
| `contracts/tenant_boundary/base-allowlist.json` | `e69679b5c28ef0dfd8cd2089a05f75391ce2521dd807b8b9a9e65f610a60a4fc` | `082538fd18ea0c9785789847b5c92a14cf00a9cdb1c53f702f343e6e0d4a783a` |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | `414d894910c6ec75e6aa28433a86ed08488204362ff1978ec3a37eac53aeb5ba` | `b9e59a21f2f2e3aa78573abc001df7efb883b90f48b292da0e5baac8bc8eedf6` |
| `contracts/tenant_boundary/census-baseline.json` | `392a6f9a42fa6a6976d3ad5eb94384c534a9984d734d2ef6b2eaef8296948968` | `2e5d6cc40ff8a465e195f0c2b8269b3c214339156123c8960f708692d6548a18` |
| `contracts/tenant_boundary/db-api-inventory.json` | `b103a48b6190e6e18cb45e456c75ec26321571c10fafc5d2c2152011f0bed8d3` | `522b6351474f200da48451edd511ba944c05d5159142b675f9ccec095d76b636` |
| `contracts/tenant_boundary/negative-fixtures.json` | `7abd1b2229377ae2ed65a359c6d6094e971177e5f0000c411cf5afc64d5d78dc` | `1d19b86015f97bedbedcc400abca028ecb09a7a2ef572f1008985acdb7863735` |
| `contracts/tenant_boundary/repository-contract.json` | `43123d6b9c879b0b0b14ab6ee285ed82638c4a4dd47d667bdba87514ba3f62f9` | `98db085a4f58f5bfde191bc31305eb0f7b0f12030fe5d1fbed48a6842dfc851c` |
| `contracts/tenant_boundary/runtime-authz-contract.json` | `94405b62eb9d5d79920aa55e158b8aedcc75e83c1126928a63c35afe57fcaf66` | `cf4ff7a8c6416874888a9c914cff164c83b1116b98152b4c9de74dec511508e9` |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | `cf1e3b911e8fb598d3b20779227ad0f8c7d2431cbf251ca2003179284d87ea72` | `2cf76852e68238449f2d1c27a6bcbd64a5d43ed5c40975d6a7133004bf95f879` |
| `tests/fixtures/frozen-archive-cases/manifest.json` | `0b82519740e1069832ba3b53cbbcadfdc7a382fef6a3e13353525ad13afdac74` | `df2ad531676277259c3d035a66e8218652aed332418a79204af6f05e41cc7888` |

| 項目 | before | after候補 |
| --- | --- | --- |
| CI SHA-256 | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `9bafa8ae1cb7b22b2b47301f2ffb8a5b2a7aeebad3f2f4d5faa5dd937dc2bd65` |
| corpus入力digest | `f50b17a2bb95e95828ced277c4288dd64a0be11a2e5132fdee691683a877634b` | `688d3ac99709b36bc09b9bd8c51711f001191d146fc8d12fc03a3bc66ca376d0` |
| 履歴 | 既存24件 | 同一prefix24件＋空欄の候補1件 |
| snapshot | 既存180件 | 同一180件＋新9件 |
| patch SHA-256 | — | `5a012348e3a08b47513804f3a6740094182a025065dbb285c37fa0af12d8306b` |

識別子の前後値は[metadata.json](metadata.json)の宣言位置・射影・外部入力hashとともに固定する。差がある8資産の識別子は次のとおり。`frozen-inputs.json`は集合内だが変更せず`contract_revision:4`を維持する。

| 資産 | 前識別子 | 候補識別子 |
| --- | --- | --- |
| `contracts/tenant_boundary/base-allowlist.json` | `contract_revision:33` | `contract_revision:34` |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | `contract_revision:15` | `contract_revision:16` |
| `contracts/tenant_boundary/census-baseline.json` | `contract_revision:14` | `contract_revision:15` |
| `contracts/tenant_boundary/db-api-inventory.json` | `inventory_revision:15` | `inventory_revision:16` |
| `contracts/tenant_boundary/negative-fixtures.json` | `fixture_set_revision:17` | `fixture_set_revision:18` |
| `contracts/tenant_boundary/repository-contract.json` | `contract_revision:22` | `contract_revision:23` |
| `contracts/tenant_boundary/runtime-authz-contract.json` | `runtime_contract_revision:17` | `runtime_contract_revision:18` |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | `contract_revision:16` | `contract_revision:17` |

### 再生成・検査

リポジトリルートから次を実行する。生成器は変更せず、隔離stagingで既存関数から全候補を導く。前回の未受理出力が全hashで検証できる場合だけ置換し、`--check`は公開せず全bytesを比較する。

```sh
PYTHONPATH=backend/src:scripts:tests/fixtures/frozen-archive-cases backend/.venv/bin/python docs/features/uf8-full-game-followup/step7-candidate/generate.py
PYTHONPATH=backend/src:scripts:tests/fixtures/frozen-archive-cases backend/.venv/bin/python docs/features/uf8-full-game-followup/step7-candidate/generate.py --check
```

生成器は固定`SOURCE_ASSET`・`SOURCE_DIGEST`を含む実装コードを逆走査し、3生成モジュールの閉包を確認する。既存`frozen_history`の射影・movement・snapshot、`runner.corpus_input_digest`、`runtime_contract_state`の描画を利用する。patchは通常`git apply --check`と自分専用隔離copyへの実適用を行い、全13 after bytesと新snapshot SHAを照合する。常設`GameScreenCandidate.spec.ts`は候補内の固定値を検査し、可変な実CI/資産との差を必須にしない。検査の今回の実測はworklogへ記録する。

### CI候補・画面検査の境界

CI候補は既存必須frontend jobへ`backend/**`、生成器、root設定の変更filter、40分上限、既存backend依存、明示Ruff/ty、専用PostgreSQLとChromium、固定`pnpm run test:browser`を加える。実CIは未変更。`sealed-ui`は実App・実Auth HTTP・HTTPS・自分専用outer/inner DBで封鎖を検査する。別`real-game`は正式Port/driver未提供でdummy SHA/IDでも明示失敗し、skipで合格へ変えない。実開始・再開・確定・保存・送信・訂正、GAP-05、原子性、1試合完遂は未達。

主担当の現HEAD`1c3f000a8a76494df3410dde541487396a3d0370`における**frontend90ファイル1793成功/87.26秒、sealed-ui5成功/21.0秒**は候補再生成前の同一E2E/Support/EntryUI sourceの実測である。今回の候補差分で実ブラウザを再測定した結果とは記さない。製品E2E sourceは変更していない。

### 過去の実測・レビュー履歴

以下は旧`51758c41`時点の経過であり、現行の実測や査読回数を表さない。

旧host5実測は並行Docker操作中の封鎖**1/5**だった。その後、主担当がDB全件**3039成功・4既存skip・終了値0**を回収し、Docker操作がないEntry `182ec62c`（旧ステップ7支援+新ステップ6）で実HTTPS/Auth HTTP/専用DBの封鎖**5/5、26.6秒**を測った。ただし現`51758c41`の支援・tenant実値・非0終了値回収を含むsourceは主担当hostで**未再測定**であり、この5/5を現在候補の実測へ転記しない。real-gameの正式Port/driver、GAP-05、原子性、1試合完遂、正式7.7受理は未達。旧計画査読3回13採用と6〜7コードPR/敵対査読の枠は別管理し、6〜7敵対はまだ0回。人間記録・新scope承認を代記しない。

現行の6〜7はClaude通常一次11件全採用、敵対基本第1回`1194ab6e`対象P0/P1/P2=0（当時E2E保留）、第2回`b5dd4972`対象P0/P1/P2=0（技術査読通過）で基本2枠を消費した。今回の基線追随差分は独立未再査読であり、新規査読・P0例外・可決を記録しない。計画査読3回13件採用/最終P0限定/最終反映未再査読、親PR履歴を保持する。
