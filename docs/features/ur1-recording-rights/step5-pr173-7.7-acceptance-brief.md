# PR #173 新5 fixture是正込み7.7受理待ち資料

- 比較元: `760c04d540b22190cab076165f1b4e35ae473a1f`（#172の受理済み25件、末尾 #172 を保持）
- 受理単位: `masaki1025/pitchlog#173`。承認者・承認日は未記入。正式履歴へ#173行は未追加。
- payload案SHA-256: `eefc3f6b5496c75427ce15a05d947315f55671bfe5094a4b61fb5d1afb5999ac`
- 単一記録案SHA-256: `9e8f7ed75a2edff26934b0baf389492167c12b54543f8bc49794e66015861f19`
- archive corpus入力digest: `3af89d8e8e2b7f2057025660d17837c1f7be9b71d549f861f5765e7e275c3513`
- 未受理の新snapshot内容10件: `step5-pr173-candidate-snapshots/`（正式台帳へ未移動）

## 9資産の前後snapshot

| 資産 | before SHA-256 | after SHA-256 |
| --- | --- | --- |
| `contracts/tenant_boundary/base-allowlist.json` | `e3dcdd745a721431a5ecdfd0cfa43f9f5839a79678d34e81fa76a3ea15746046` | `8e7f41fcf9d1edca4e4bac871bebc6094fec37763b65659f246bb80379030f9e` |
| `contracts/tenant_boundary/cache-invalidation-contract.json` | `161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f` | `c6b7450246c54d7b7661ae2c66f7fcf6f891d9fe7488238ac6b2e13385a232e9` |
| `contracts/tenant_boundary/census-baseline.json` | `c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f` | `bebc29609e9dfd7e453c22f411710b38e0b79e9fc31e63c95397990c175b8565` |
| `contracts/tenant_boundary/db-api-inventory.json` | `66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999` | `21a15b0f90a35c2f0ffe42387cd5f7f39dac142c0987bfee9f0dcda37fa11bd7` |
| `contracts/tenant_boundary/frozen-inputs.json` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` |
| `contracts/tenant_boundary/negative-fixtures.json` | `3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82` | `9b5197e65f12bbdec64e87a4bf09470efffb0e7618efa0ec09e96428d337bc02` |
| `contracts/tenant_boundary/repository-contract.json` | `9872b2b0d5233193b3e3d76b37b144599d5d2ea8c14a93f1df6cd20a834bd3b0` | `b93408f31683e671e03e89ffbeda10999ac54226de3b78a7643a2a1622955040` |
| `contracts/tenant_boundary/runtime-authz-contract.json` | `f4fcc729d19247df3c6cf01694e9cb6f314e2e9d290b8bc38bbc5fb5f8b124b6` | `e20c325bc4ae4742e9e06adab4306fd3e1280be3ef19e707e2402cfb24725128` |
| `contracts/tenant_boundary/tenant-context-allowlist.json` | `16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2` | `fe056d4b4b96058d5e9d72899f17fca69bcbb19f87d78f9ab32d430631d74129` |

## 8外部対象の前後snapshot

| パス | before SHA-256 | after SHA-256 |
| --- | --- | --- |
| `.github/workflows/ci.yml` | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` |
| `scripts/check_tenant_boundary_bypass.py` | `3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883` | `3b7b90f8476b30c0596439b33ce75db1c23c6c930b359e03804f00df280e0e7e` |
| `scripts/frozen_archive.py` | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` |
| `scripts/frozen_history.py` | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` |
| `tests/domain/test_boot_seal.py` | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` |
| `tests/test_census_baseline_check.py` | `163cb41e19e9d24ee2b30037f5f6614800ed193c21d1c31cc325371f25e9edfd` | `ae5e4d9e4ed0145374acd8036ca13410785f6890fb4e29a0ac93a6b8d0078f01` |
| `tests/test_ci_wiring.py` | `36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396` | `36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396` |
| `tests/test_plan_generation.py` | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` |

## 受理前の境界

- この資料は#172統合後の実ファイルから再導出した**未受理候補**。#156と文書のみ統合した#170の承認値を流用しない。25件の既受理履歴、before側、#172のsnapshotを維持する。
- 旧checker43件・独立AST18件の正解digest2値はJSON fixtureへ移し、exact照合と欠損・改変・余剰・不正形式の拒否を維持する。fixture是正では検査器、通常allow-list、合否条件を変更しない。PR全体のchecker限定差分は旧レビュー対象から移植した。
- #162は`760c04d540b22190cab076165f1b4e35ae473a1f`で実統合済み。#173は同developを取り込み、data-model・schema-manifest・shared-preconditions・ORMシートを保持する。U-R1の未統合§6-1は別の正本ゲートで扱う。
- 既存#170限定レビューは旧固定差分の0/0/0。#173追加レビュー1回は候補tree`d6c4753bad0a2280d3d77bff5e6ee4e4b393710d`、差分SHA-256`dea41a8516d5f8758e3f26ebda80e60e6cd5d133fa0069c3e68becf7d2341d88`を固定し、P0/P1/P2=0/0/1。P2はこの資料の状態表示で採用・修正済み。製品・7.7値への影響はない。旧レビューの対象・回数・採否を変更しない。
- 今回の独立レビューは、`tests/test_census_baseline_check.py`のfixture読込・exact照合・負例、`tests/fixtures/tenant_boundary/census-scoped-digests.json`、#172の25件目を保持した`base-allowlist.json`、runtime契約revision 18→19とsource digest追随、corpus・9資産snapshot・#173単一記録案の直接差分を照合した。旧レビュー済みの製品コード全文を再審査した扱いにはしない。
- #162統合後のcensus全74件、限定census関連17件、backend隔離候補20件、backend契約84件、core-guard関連270件、archive corpus・凍結ソース走査2件、root/backend Ruff・tyは候補で確認。途中で候補資産を是正した最初のcensus全件は中断として記録した。正式履歴未反映のためrepository greenと全件CIは未完了。
- 正式7.7受理までは#173の正式履歴・snapshotを反映しない。本人逐行確認、Draft解除、マージ、既存DB適用は行わない。
