# ステップ7の7.7正式受理へ渡す現基線候補（未受理）

本書は受理記録ではない。候補は公表`origin/develop` `161ab6182577e8d4875406d5e48f42f9f2c2c130`、feature生成時HEAD `1c3f000a8a76494df3410dde541487396a3d0370`、正式入力340パスのGit blobと照合した。旧`9136...`基線の受理briefは現行値として使わない。[範囲追補v3](step7-scope-extension-v3.md)は追加9正式パスの**未承認提案**、本7.7の完全実値受理は別ゲートである。旧v2/旧提案の固定bytesを維持し、実CI/正式資産/backend製品への適用は0。

候補はCI・影響8資産・生成3モジュール・manifestの完全13前後ファイルと、旧履歴24件/旧snapshot180件を不変prefixとする空欄の新1履歴/9snapshotで構成する。[metadata.json](step7-candidate/metadata.json)に識別子・射影・外部入力・Git出所を固定し、[candidate.patch](step7-candidate/candidate.patch)に完全差分を置く。

- patch SHA-256: `5a012348e3a08b47513804f3a6740094182a025065dbb285c37fa0af12d8306b`
- CI SHA-256: `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` → `9bafa8ae1cb7b22b2b47301f2ffb8a5b2a7aeebad3f2f4d5faa5dd937dc2bd65`
- corpus入力digest: `f50b17a2bb95e95828ced277c4288dd64a0be11a2e5132fdee691683a877634b` → `688d3ac99709b36bc09b9bd8c51711f001191d146fc8d12fc03a3bc66ca376d0`
- 生成器SHA-256: `bab5140635e056640271af7044e0b4a121b51d860c32922f8bbb3e8b1ac4e604`

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

候補の空欄`accepted_by/date/on/signature`、新履歴`acceptance_id/approved_by/on`を人間の受理として埋めない。正式適用前には6〜7 Draft PRを単一受理単位として、現行基線に対する正式前後SHAとPR番号を固定し、本人の7.7判断を別途得る。今回の候補再生成・隔離検査はその判断を代替しない。範囲未承認または7.7未受理は独立した封鎖UI/ローカル候補提出を停止させない。

主担当の現HEAD`1c3f000a8a76494df3410dde541487396a3d0370`のfrontend90ファイル1793成功/87.26秒と実App・実Auth HTTP・HTTPS・専用outer/inner DBのsealed-ui5成功/21.0秒は、同一E2E/Support/EntryUI sourceでの実測である。今回の候補再生成によるE2E再測定とは区別する。`real-game`は正式Port/driver未提供で明示失敗し、実開始/再開/確定/保存/送信/訂正、GAP-05・原子性・1試合完遂は未達。追加scope/正式7.7の人間欄・署名を代記せず、今回差分の独立追加査読も未実施である。
