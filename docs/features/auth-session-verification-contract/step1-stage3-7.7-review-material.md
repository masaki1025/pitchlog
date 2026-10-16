# C1ステップ1 第3段 7.7正式判断資料（未承認候補）

この資料はPR #144の7.7正式判断専用である。正式受理前のため、承認者・承認日は記録案で`null`のまま保持する。第3段の資産反映、人間逐行確認、Draft解除、マージを表さない。

## 1. 機械照合元

- 共有実行器A統合後develop: `e7e8d3a4324687ada828b1e4b49692c087af5c44`
- C1第1段: `d5ccc18ef39179857c9a4c793ea28a416432efba`
- C1第2段: `f3acb6b288e30a7378cbddf9b76d34b3d0a7ba25`
- 受理ID: `masaki1025/pitchlog#144`
- tenant-boundary記録は製品の`runtime_contract_acceptance`で上記developをbaseに再生成した。
- authz入力blobはGit object IDをdevelopと第1段から再取得し、seal記載値と一致確認した。
- sealed digest候補は現HEADの6資産を製品検査器`_table_digest`で再計算した。

## 2. tenant-boundary 2資産

| 資産 | revision before → after | base blob | 第1段blob | base file SHA-256 | 第1段file SHA-256 |
|---|---|---|---|---|---|
| `contracts/tenant_boundary/base-allowlist.json` | `contract_revision:31` → `contract_revision:32` | `4d3943d743cc908205cd79a53395b27af026931e` | `1739d89663a20407f64945c74be9f8adc75e1ae0` | `74523360e395baabf341fd83dce44e99c29af89060716f1931f1818335415bc7` | `9a8dad03768ea589d5ade894399fd7c3156d337f76f985278f7dacc350bf4fb1` |
| `contracts/tenant_boundary/repository-contract.json` | `contract_revision:19` → `contract_revision:20` | `7a2bbd22daba6f94af129466f1b67ba3f810855a` | `d71ffad2b3473693595239a2d00999fd522b3cbe` | `f4600e76a1ed789ade5237c37ffc9c90bba070fd4cffe3a15d760cf5518ac84a` | `dbc77a398625290d2127898a16ed3cbd9adfac3de4c79aa27a5d94685d1276f1` |

- repository source digest after: `22ecaa00ad393d2c7695ec53f68fdd23239ada64e293d070fda7793087a0a3b6`
- 第1段と第2段の2資産はbyte一致。第2段はtenant-boundary資産を変更していない。

## 3. tenant-boundary 2 snapshot

| 資産 | before snapshot SHA-256 | after snapshot SHA-256 | after bytes |
|---|---|---|---:|
| `contracts/tenant_boundary/base-allowlist.json` | `0642f1ce39b037248e2fcc32ecc44950887d379d563a564bdcd9d97b31d4b515` | `20c8f0f71734d244e8734a0ded0903d380cfcae79315549ccd318a8a6e6ebabf` | 11578 |
| `contracts/tenant_boundary/repository-contract.json` | `15c416e962e559312bc26502895d2718e508299459bbb6df3258758edf5c1004` | `71cb7a8bba95d335571411198044da40b1ac05d06707a9c34a9fb396bf6c2a00` | 7527 |

- 2 snapshotの完全なbase64内容は同ディレクトリの`step1-stage3-7.7-record-proposals.json`に固定した。復号後SHA-256と参照名の一致を機械確認済み。
- tenant記録の9資産識別値、declaration、movement policy、8 external snapshot、9 asset snapshotの完全before/afterも同JSONに固定した。
- tenant受理記録案canonical SHA-256: `03f1d715e387bda914eb794f865d9bbb081a3a7182b8f50ae76a6c34d910fe8a`

## 4. authz 8入力blob

| 入力資産 | before blob | after blob | 変更 |
|---|---|---|---|
| `contracts/authz/requirement-claims.json` | `61c5e0579fc4b514cdd38cc888ff1cde622bbf65` | `61c5e0579fc4b514cdd38cc888ff1cde622bbf65` | no |
| `contracts/authz/requirement-claims.lock.json` | `a5c278112c17441a178c5ef7d237e83a46a2950f` | `a5c278112c17441a178c5ef7d237e83a46a2950f` | no |
| `contracts/authz/route-registry.json` | `3b29456a03d2ddc0bfd36fc50085ab353d6cd783` | `2cd82db822df203d9608b6d72e4bbfb518dab2ad` | yes |
| `contracts/authz/route-registry.lock.json` | `db3c9f459ca605543577053f6b682ec0ddf8033e` | `e110a75541cca22d349fe6f765e7b8c7ba741e64` | yes |
| `contracts/authz/auth-catalog.json` | `06ffccaf5e21c34991129ee9a636ac0b77984363` | `06ffccaf5e21c34991129ee9a636ac0b77984363` | no |
| `contracts/authz/auth-catalog.lock.json` | `0467a4cbc0ab5a7607058db5fba6b0508e7d970f` | `0467a4cbc0ab5a7607058db5fba6b0508e7d970f` | no |
| `contracts/authz/http-route-matrix.json` | `d9991954a412bfab5882e97a4facb59bcd4c0063` | `c2d03ad51a9d1961e1fdf5c5730e4705acf6907e` | yes |
| `contracts/authz/http-route-matrix.lock.json` | `159cea03a71c5cf89327e306538f0682b937c54a` | `5882c2b918ed8d06feb12fa905434d916b685c7f` | yes |

## 5. authz 6 sealed digest

| sealed資産 | before canonical SHA-256 | 再封印後canonical SHA-256候補 |
|---|---|---|
| `contracts/authz/ddl-elements.json` | `71d541779c0e0acee45bb5532ea2aa207281dd65e95f3209574c14afd24f7135` | `22ba361a9331d714f1ccf75d64fd224acba959d4841cba8bcf0b796a1c3663b1` |
| `contracts/authz/rejected-configs.json` | `980938d443b601578388dddf54bb488e5636f43811752b9b467ac35439e5367a` | `6e1cd82f7890b17ff6e51a53fc0771226fcd84f9aeeeb4d832c07a6073fd5af9` |
| `contracts/authz/claim-mutant-map.json` | `669712f69bb8cee29acd75d296cab98ad5efa6df676e6c88a318457d8c14afde` | `9abfd153d134c7c9cc0839291a45faefa098a1100baeeabd86738592a2ffa70a` |
| `contracts/authz/attack-tree.json` | `cbaa854532cd03b78fa6f3dfe4e12100a7ce3cb1a2ea74665d3bb492ac70e7b1` | `535154875b3eed4b4ecd73f33feee982c03a9ad48f2e3a269a7fdf05a63bdba4` |
| `contracts/authz/boundary-proposal.json` | `3d358a595b59a2976ca634a28f5dc60a1a176b798ae35f117b551b11c54d84e3` | `bbfeaf93c95d6e0b29c76ba074063fd372edd0235a44d9d0721681c07876d627` |
| `contracts/authz/verification-evidence.json` | `187020a83763a1551dd8901bb1978c0399ef97895edafc21853a6f03a6a4153f` | `4f70c83f3b475ab2005ab1678183633c770c789c1f659b94a0bd5b992c928759` |

## 6. 両受理記録案

- tenant-boundary記録案canonical SHA-256: `03f1d715e387bda914eb794f865d9bbb081a3a7182b8f50ae76a6c34d910fe8a`
- authz記録案canonical SHA-256: `e0451a2afa35fdb4807ac36b7980f73131b990a61fb8c7ee9babec6bd183dc3c`
- 完全記録案ファイルSHA-256: `43acdfa1b1e88ad235af019fd230615a702a191d91c3c158ca7b1466b4a0e141`
- tenant: `approved_by=null` / `approved_on=null`。authz: `approved_by=null` / `approved_at=null`。
- 完全な両recordとsnapshot base64、実ファイル・Git blob照合証跡は記録案JSONを正とする。

## 7. U-R1 #143との直列化

- 順序はC1 #144正式受理・統合 → U-R1 #143再導出。
- #143のC1統合前候補はbase allowlist 31→32 / repository contract 19→20だが、C1とsnapshot内容が異なる別候補であり流用しない。
- #143は#144の実merge SHAを含むdevelopからrevision、source digest、snapshot、履歴、archiveを再導出する。

## 8. 正式判断後にだけ行う処理

1. 実承認者・実承認日を両recordへ入力する。
2. tenant authority履歴へrecordをappendし、2 snapshotをcontent addressで追加する。
3. authz oracle_input履歴へrecordをappendし、6 sealed digestを再封印する。
4. archive corpusを実record metadataから再導出する。
5. 第3段コミット、全検査、最終レビュー、人間逐行確認を行う。
