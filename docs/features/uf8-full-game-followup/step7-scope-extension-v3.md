# ステップ7の限定候補追随・追補v3（未承認）

承認済み[計画](plan.md)の3節が求める追加波及の具体化である。旧v2 SHA `253c06e8debb7e399d309a2dd6a0968b05325ecc983543bd7762663767efe63b`と旧提案SHA `899abea1cdd8e7e3ea069a65c8b8ff79eaf0fdfe40ce2687ccf2559011200f59`は未承認の固定履歴として保持し、本書が**最新公表基線に対応する新提案**となる。人間の範囲承認も7.7正式実値受理も代記しない。実CI・正式資産・backend製品への適用は0。

## 提案する正式パスの追加範囲

既承認のCI、base/census、history snapshot、比較manifestは維持する。追加9正式パスだけを次のとおり提案する。範囲判断と7.7の完全実値受理は独立したゲートであり、いずれの保留も封鎖UIの独立提出やローカル候補提示を妨げない。

| 追加する正式パス | 候補差分の意味 |
| --- | --- |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | CI外部入力に伴う識別子・射影・履歴の候補追随 |
| `contracts/tenant_boundary/db-api-inventory.json` | CI外部入力に伴う識別子・射影・履歴の候補追随 |
| `contracts/tenant_boundary/negative-fixtures.json` | CI外部入力に伴う識別子・射影・履歴の候補追随 |
| `contracts/tenant_boundary/repository-contract.json` | CI外部入力に伴う識別子・射影・履歴の候補追随 |
| `contracts/tenant_boundary/runtime-authz-contract.json` | CI外部入力に伴う識別子・射影・履歴の候補追随 |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | CI外部入力に伴う識別子・射影・履歴の候補追随 |
| `backend/src/pitchlog/authz/runtime_contract.py` | 既存生成モジュールの版・source digest追随。製品動作は新作しない |
| `backend/src/pitchlog/repositories/repository_contract.py` | 既存生成モジュールの版・source digest追随。製品動作は新作しない |
| `backend/src/pitchlog/repositories/tenant_context_contract.py` | 既存生成モジュールの版・source digest追随。製品動作は新作しない |

## 現基線・完全前後値

公表`origin/develop`とsource git baseは`161ab6182577e8d4875406d5e48f42f9f2c2c130`、候補生成時HEADは`1c3f000a8a76494df3410dde541487396a3d0370`。正式入力340パスはworking tree・現HEAD・公表基線・生成時HEADのGit blobを照合した。生成器SHA-256は`bab5140635e056640271af7044e0b4a121b51d860c32922f8bbb3e8b1ac4e604`、完全patch SHA-256は`5a012348e3a08b47513804f3a6740094182a025065dbb285c37fa0af12d8306b`。CIは`f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8`→`9bafa8ae1cb7b22b2b47301f2ffb8a5b2a7aeebad3f2f4d5faa5dd937dc2bd65`、corpus入力digestは`f50b17a2bb95e95828ced277c4288dd64a0be11a2e5132fdee691683a877634b`→`688d3ac99709b36bc09b9bd8c51711f001191d146fc8d12fc03a3bc66ca376d0`。前値は既存履歴24件・snapshot180件、候補は同じprefixに空欄の未受理履歴1件・新snapshot9件を追加する。既存#165等の受理と署名を変更しない。

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

8資産の前後識別子、射影、全外部入力hash、候補Git出所は[metadata.json](step7-candidate/metadata.json)に固定し、完全bytesは[before/after](step7-candidate/)、patchは[candidate.patch](step7-candidate/candidate.patch)に置く。`frozen-inputs.json`の識別子は`contract_revision:4`で変化しない。

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

## 判断と未達

候補の`accepted_by/date/on/signature`と新履歴の`acceptance_id/approved_by/on`は全て空欄。追加9正式パスの範囲判断と、7.7のPR受理単位・正式適用前後SHA・本人受理/署名は別途必要である。実CI/正式資産への適用、正式Port/計算/providerの接続、GAP-05・原子性・実1試合は未達。封鎖UI/ローカル候補はこれらを成功と主張せず独立提出できる。

今回の再生成・契約試験・文書差分は独立未再査読である。6〜7のClaude一次11件全採用、敵対基本2回（1回目当時E2E保留、2回目技術査読通過）、P0例外なし、計画査読3回13件/最終P0限定/未再査読と各親PR履歴をそのまま保持し、追加枠や可決を代記しない。
