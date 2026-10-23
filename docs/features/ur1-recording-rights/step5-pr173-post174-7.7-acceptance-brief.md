# #173実#174後の7.7受理候補

固定source HEAD: `36424c536255b6c6e6d9aac82bb55a9c51d7ef46`。実比較元: `1f506675bf15bbb5385b311c139bc80d82e15e43`。作成者: `/root/independent_review`（今回から候補作者）。**新実値は未受理、承認者/日付は未記入、正式履歴・snapshotへ未反映**。旧#173受理はこの新基線へ流用しない。

payload SHA256: `9150071ca34e11ac050030683749826209768e47e82886ef48348ec4231cc96f`
record案 SHA256: `492b1a09fd2c94ce387cc2ba4958785fb0cc5835fb78ee83c33057151e286a13`
corpus入力digest: `271f8615f97591528e4a391334e37a431b720ea20ba485f55e7ecad74a5e5f28`

## 9資産の完全射影

| 資産 | before SHA256 | after SHA256 |
| --- | --- | --- |
| contracts/tenant_boundary/base-allowlist.json | `f532e8e1ea6d99ebfb90d5e9b67f427987cdb91623bac1b27596622e3da65ae2` | `a7429103c115682a0dd61e7838b10a02a410161368065f310110a535446dcf5a` |
| contracts/tenant_boundary/cache-invalidation-contract.json | `b9fec039aa7a9b1a7f04079c8ce0b03f2d21d6df407ffcdf21e6b6e822e8f9f6` | `3fb9dcc55e42899bb527586c07ee2761b16466bde78ddef68efa61e3e4b2d458` |
| contracts/tenant_boundary/census-baseline.json | `74e525aee95aea6f5ee5cd3648116d3ece3437e53b7687342bc48d3b476a6d4d` | `d413624b7c980db81106cf1123586ae8f87ce2948ec35f1f2b7be0678f50027a` |
| contracts/tenant_boundary/db-api-inventory.json | `6559c7b2802740501cac3a6b2875c8311421b189d8656f2a7d97691c2c7b2465` | `84553eb0eb42e928fac713dac459d0e7d2978bb8b108f2614ab35616adf6cbc2` |
| contracts/tenant_boundary/frozen-inputs.json | `d0ce3c4c1e0d24e0137cf1701b646ec71cad2611682c78b39d04be7c34a75377` | `d0ce3c4c1e0d24e0137cf1701b646ec71cad2611682c78b39d04be7c34a75377` |
| contracts/tenant_boundary/negative-fixtures.json | `a2b6ea0044c13b96ac5c8e4778da5f03b92cbbe46563a7b94d87a8714b832c24` | `16b906dd8ce5a8351465db0c4059e9a0f17c7b01759d13018c7337d7b307d627` |
| contracts/tenant_boundary/repository-contract.json | `ca05640633b465694ea638026324f87dd24c2a177a3d6829d651d7d54bc096b6` | `6f63e4493488bcb753fb789983e59e502c569d4af4b7e237a533cdc1fada251f` |
| contracts/tenant_boundary/runtime-authz-contract.json | `f6b12096ff291a2af707ee04bcee67ddf38d77a82fd4ed4edfc31c847d8bfa6c` | `8496f0b7e2ee160d84fede0442c6699a7966688074d890620f3835d8e5b16c92` |
| contracts/tenant_boundary/tenant-context-allowlist.json | `a8b5fdd2ef7a990e8ba28a2408dbbdcfe51a157acd85c7b1b313e36b71c7ac88` | `89197e07d3a35ed956df21e9325e70734c6e07c29c8f64bc67f7b9554d0f9318` |

## 外部8対象

| パス | before SHA256 | after SHA256 |
| --- | --- | --- |
| .github/workflows/ci.yml | `40c58559bd98ab44d015e16295df34b39219ad292e2a6c0b4c67eda0867d829a` | `40c58559bd98ab44d015e16295df34b39219ad292e2a6c0b4c67eda0867d829a` |
| scripts/check_tenant_boundary_bypass.py | `3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883` | `3b7b90f8476b30c0596439b33ce75db1c23c6c930b359e03804f00df280e0e7e` |
| scripts/frozen_archive.py | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` |
| scripts/frozen_history.py | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` |
| tests/domain/test_boot_seal.py | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` |
| tests/test_census_baseline_check.py | `163cb41e19e9d24ee2b30037f5f6614800ed193c21d1c31cc325371f25e9edfd` | `ae5e4d9e4ed0145374acd8036ca13410785f6890fb4e29a0ac93a6b8d0078f01` |
| tests/test_ci_wiring.py | `f8df20c22e909cbccefe9d740ddaf53059b3b36d33718f8eb08048148780db58` | `f8df20c22e909cbccefe9d740ddaf53059b3b36d33718f8eb08048148780db58` |
| tests/test_plan_generation.py | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` |

## 境界と引渡し

- 実baseの26件prefix・末尾#174を保持。旧原状5239・旧proposal・旧受理履歴は変更しない。
- 先行製品56関数・initial_grant/試験のsourceは保持。既存validatorのmovementから8資産の識別値だけを実base+1へ更新、frozen-inputs revision5は不変。
- candidate snapshotはこのfeature隣接のpost174ディレクトリ8件にだけ保存。正式snapshotdirの実base不在・未参照10件は削除せずderivation.jsonへ一覧化。受理後の整理は主担当判断。
- 新173の正式反映と新snapshotの追加は実値受理後。現authorityは26件のため識別値更新との不一致は意図した未達。
- 生成契約の限定検査と受理前/後の検査を分ける。全件backend/root・最終CI・実接続成功を主張しない。
- corpusは既存pinned6履歴/固定snapshot規則により算出。authority suffixと非固定snapshotは除外されるが、それらのappend-onlyと参照妥当性は別検査で確認する。
- PR_ACCEPTANCE本番CLIはGitHubの合成merge（二親: 実base,最終head）上で実行する。通常のfeature HEADへeventを注入しただけでは成立せず、親構造の拒否となる。
- 本資料は独立レビュー・PO委任による新実値受理の前段であり、本人逐行確認・署名を代記しない。

現在未参照の10件のうち2件は新提案が参照するchecker/census外部snapshotのため保持必須。提案受理・反映後にも未参照となる整理候補は8件で、derivation.jsonの `formal_orphan_cleanup_candidates_after_proposed_record_acceptance_only` に分離した。削除は行っていない。

限定検証: 生成契約5 passed/0.47s、安定入力でcensus74 passed/514.27s、runtime check・対象Ruff・diff-check成功。初回inventory binding未追随時の失敗と、その後の既存方式による追随は作業ログに保持。正式履歴未反映の赤・受理後archive/全件/CIは別の未達である。
