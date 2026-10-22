# PR #174 段階Aステップ3 7.7 正式受理申請（候補）

## 固定識別値

| 項目 | 値 |
| --- | --- |
| 比較元 | `760c04d540b22190cab076165f1b4e35ae473a1f` |
| 候補入力tree（本資料2ファイルを除く） | `a40cfeb62ee20ac32fe2a23b61ed47341404c311` |
| oracle入力commit | `426d0ec84249d5940e7e2de5660a213d45401d0e` |
| 完全値JSON SHA-256 | `19f9281b1aa2277e77e4d690fe3bcccd18c984ee200731fe0b10211e4ce04d1f` |

旧#152の受理行は移植せず、developの既受理tenant 25件・seed 3件・oracle 12件を保持する。承認者・承認日は未記入。#173との正式履歴順は未受諾のため、同じ位置への並行追記をしない。

## tenant-boundary 9資産・外部8ファイル

| 種別 | パス | before SHA-256 | after SHA-256 |
| --- | --- | --- | --- |
| 資産 | `contracts/tenant_boundary/base-allowlist.json` | `e3dcdd745a721431a5ecdfd0cfa43f9f5839a79678d34e81fa76a3ea15746046` | `f532e8e1ea6d99ebfb90d5e9b67f427987cdb91623bac1b27596622e3da65ae2` |
| 資産 | `contracts/tenant_boundary/cache-invalidation-contract.json` | `161d2815a06778fbac0bb679b5a5aa1d1295db2e7e0ed971d2b343a654daf32f` | `b9fec039aa7a9b1a7f04079c8ce0b03f2d21d6df407ffcdf21e6b6e822e8f9f6` |
| 資産 | `contracts/tenant_boundary/census-baseline.json` | `c717da79aee3504ab5176f88cd502ad40170389df7ad1aa60d4fb5c86e5f241f` | `74e525aee95aea6f5ee5cd3648116d3ece3437e53b7687342bc48d3b476a6d4d` |
| 資産 | `contracts/tenant_boundary/db-api-inventory.json` | `66ec5e8410adeab61f78bcb4ce72ec4ea55b32588d96e95d172013b2a8658999` | `6559c7b2802740501cac3a6b2875c8311421b189d8656f2a7d97691c2c7b2465` |
| 資産 | `contracts/tenant_boundary/frozen-inputs.json` | `c2bdb0c1f59b61c537173dba45d428951de00688613770fc16940f1b01c6bb63` | `d0ce3c4c1e0d24e0137cf1701b646ec71cad2611682c78b39d04be7c34a75377` |
| 資産 | `contracts/tenant_boundary/negative-fixtures.json` | `3513677e5ea3dff4db6471ef2b4ade93c91095ef5a3f43e085a5b8ee59c43d82` | `a2b6ea0044c13b96ac5c8e4778da5f03b92cbbe46563a7b94d87a8714b832c24` |
| 資産 | `contracts/tenant_boundary/repository-contract.json` | `9872b2b0d5233193b3e3d76b37b144599d5d2ea8c14a93f1df6cd20a834bd3b0` | `82a81171fe5ccb348181d9ea937fa6def390feb4c49fab05b900ebc9b26703b4` |
| 資産 | `contracts/tenant_boundary/runtime-authz-contract.json` | `f4fcc729d19247df3c6cf01694e9cb6f314e2e9d290b8bc38bbc5fb5f8b124b6` | `f6b12096ff291a2af707ee04bcee67ddf38d77a82fd4ed4edfc31c847d8bfa6c` |
| 資産 | `contracts/tenant_boundary/tenant-context-allowlist.json` | `16e7a9a6a263f00381a327d8f05bce597dd036d67333ebfc55e035f1e8f9e2c2` | `a8b5fdd2ef7a990e8ba28a2408dbbdcfe51a157acd85c7b1b313e36b71c7ac88` |
| 外部 | `.github/workflows/ci.yml` | `f12d1277a8f5815d1c0f9367d34ecee08b5593b255b37ab098dcf88e550bcff8` | `40c58559bd98ab44d015e16295df34b39219ad292e2a6c0b4c67eda0867d829a` |
| 外部 | `scripts/check_tenant_boundary_bypass.py` | `3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883` | `3e2cec0a25096b010973f3734c2746bd4386e413ebf44519ad8db0851846b883` |
| 外部 | `scripts/frozen_archive.py` | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` | `66e198f6c8ba13d213efe9a3d69c7f259ef67ed5f5be9e948934da44a1e81ca6` |
| 外部 | `scripts/frozen_history.py` | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` | `0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8` |
| 外部 | `tests/domain/test_boot_seal.py` | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` | `bb7b51691559bd2c0be6c802c8b15f509b592cb41862787700f178358f74aea2` |
| 外部 | `tests/test_census_baseline_check.py` | `163cb41e19e9d24ee2b30037f5f6614800ed193c21d1c31cc325371f25e9edfd` | `163cb41e19e9d24ee2b30037f5f6614800ed193c21d1c31cc325371f25e9edfd` |
| 外部 | `tests/test_ci_wiring.py` | `36cc456a38247546859e7d06e0c5006ae1e7b3165cfc312d25e62c0fadf0a396` | `f8df20c22e909cbccefe9d740ddaf53059b3b36d33718f8eb08048148780db58` |
| 外部 | `tests/test_plan_generation.py` | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` | `9f3c40956cbc50890e2a2b8dc8f5a17a85a80db5ecaf7f79becad8e9f88151fe` |

各after snapshot参照先と射影対象は[完全値JSON](step3-pr174-7-7-candidate.json)に含む。

## seed

候補配置は `0033_game_rules_immutable` の後続 `0034_stage_a_rule_defaults`。既受理3系列は保持し、変更対象の完全なbefore/afterは以下。

```json
{
  "before": {
    "absent": true
  },
  "after": {
    "allowed": {
      "db_call_counts": {
        "connection.exec_driver_sql": 6,
        "connection.execute": 12
      },
      "revision_id": "0034_stage_a_rule_defaults",
      "row_shape": "stage_a_fixed_five",
      "source_sha256": "51f96e3192781d2077fc89628d48a0e34a4d04c46f21a478029a5177b2da175d",
      "static_violation_counts": {
        "get_bind の束縛先を追跡できない": 8,
        "get_bind 経由の execute() は禁止": 11,
        "禁止 SQL CREATE POLICY": 4,
        "禁止 SQL INSERT INTO": 2
      },
      "target_tables": [
        "rule_sets",
        "game_type_rule_defaults"
      ],
      "temporary_policies": [
        [
          "rule_sets",
          "tsk550_seed_rule_sets_select"
        ],
        [
          "rule_sets",
          "tsk550_seed_rule_sets_insert"
        ],
        [
          "game_type_rule_defaults",
          "tsk550_seed_defaults_select"
        ],
        [
          "game_type_rule_defaults",
          "tsk550_seed_defaults_insert"
        ]
      ],
      "upgrade_rows": {
        "count": 5,
        "rows": [
          [
            "game_official",
            "ca626b2e-8751-530e-a431-9ef5c00f7d95",
            [],
            12,
            {
              "leadoffRule": "continue_lineup",
              "runnerPlacement": "no_out_first_second",
              "startInning": 10
            }
          ],
          [
            "game_semi_official",
            "8fa3b9b7-481b-538b-8093-6af96050d97f",
            [
              {
                "pointDifference": 10,
                "startInning": 5
              },
              {
                "pointDifference": 7,
                "startInning": 7
              }
            ],
            9,
            null
          ],
          [
            "game_open",
            "b679f9f1-86a8-54f7-9466-a5b01d932953",
            [
              {
                "pointDifference": 10,
                "startInning": 5
              },
              {
                "pointDifference": 7,
                "startInning": 7
              }
            ],
            9,
            null
          ],
          [
            "game_intrasquad",
            "45677369-9e25-5220-9a30-1d89b338174c",
            [
              {
                "pointDifference": 10,
                "startInning": 5
              },
              {
                "pointDifference": 7,
                "startInning": 7
              }
            ],
            9,
            null
          ],
          [
            "game_other",
            "6ff51660-bee2-552a-9075-1f3f3d1e0dd7",
            [],
            9,
            null
          ]
        ]
      }
    },
    "frozen_targets": [
      "migrations/versions/0034_stage_a_rule_defaults.py"
    ],
    "granularity": "declaration_series",
    "identity": "sha256_canonical_json"
  },
  "prior_identity": {
    "present": false,
    "values": []
  },
  "new_identity_candidate": {
    "present": true,
    "values": [
      {
        "kind": "sha256_canonical_json",
        "value": "81ac7a6d083b704261d9bf2193acfadcf7a5025fb93091df8607d278eb8e2df9"
      }
    ]
  }
}
```

## oracle入力8資産

| パス | before Git blob | after Git blob |
| --- | --- | --- |
| `contracts/authz/requirement-claims.json` | `ad830901cd6e9427b3becc5e9502934cbb39dfde` | `c4a3e705e24e5ab13a00681a38b210915623fe4d` |
| `contracts/authz/requirement-claims.lock.json` | `4d5fbefae3d0dc5836d9e8b24510e1ce79e4c7c5` | `e7dc82ec47fd9a95add297514794afffa395c16c` |
| `contracts/authz/route-registry.json` | `4198b7039e96d083ebc18f145b4e85a8bd354028` | `462a648d3901721575ea6b711d2baa2e9a36c1c9` |
| `contracts/authz/route-registry.lock.json` | `94d118e93770be103200ab1e8465f3218c3be34d` | `ac1ab1efebde88749836bd66d0eab55fd320619d` |
| `contracts/authz/auth-catalog.json` | `945b90d609147aa85b1cdfdd00fa38df81275809` | `3003b02ecc239485ae464902252d2aff64691388` |
| `contracts/authz/auth-catalog.lock.json` | `5ce421a4ec8180a8df764793c8d098b49c7ed6b3` | `8912540747517ac9a25fbb2bc2db09d6ae04b6be` |
| `contracts/authz/http-route-matrix.json` | `bcd223b31fce14acb25a068b0d0b6265dcd440ce` | `82495694c154e2c61e41582a2c9fba80136e1ad2` |
| `contracts/authz/http-route-matrix.lock.json` | `13fb097fdf63436494923351b99cf6063f2681cf` | `0dc9cb1d8bfb8ca06f12a9a41a0a004d2ffcc44f` |

## oracle seal 6資産

| パス | before canonical SHA-256 | after canonical SHA-256 |
| --- | --- | --- |
| `contracts/authz/ddl-elements.json` | `8a11a4eef84ece58474001171d677904dacc78c21438e15395d1f86ddf70f0a6` | `2160fa910b52390887770cb4965eac78ea1d0be866fdd13cc94769082b43f9ac` |
| `contracts/authz/rejected-configs.json` | `b4c468f1c2a655147337eabc8c651df5482e236df6e80f9d5c40deeb44d93268` | `f818ce4f9bed567e4ca8fcaccfc9a5c94781ebd089c8e7097e3bb3497b822361` |
| `contracts/authz/claim-mutant-map.json` | `1b6b97f1a1f1a13bc01098a6fa2846205845ec1f3284fe4a5f98e56fa7b9cb21` | `dc9a59e368688fb19c579f821ccade55dae9951fc38fa21536fa111ecee18bb7` |
| `contracts/authz/attack-tree.json` | `b225ce42003910a19163e4ecb2f93733e73594e949d989e8683a410f79384e78` | `53f5b23b7501918edc31e48e5fd975bbd52ebd4883de3c02553d2aa5289f9096` |
| `contracts/authz/boundary-proposal.json` | `70ff5e51bc5508076ff8600c048bcefebde0f87afb8eb5e23744e785fe4a811e` | `19ee72e834fa8449ff3ff6e86e84e76be6aa4521adf3a527a483e3596733c741` |
| `contracts/authz/verification-evidence.json` | `94a6d5497c4d582718d472ca33e531019445f185da0835928c775083b7bcc81b` | `4157ccc7b7ed80a12697a52413389bbe961809ee2c0437ce76b409a55bd691c4` |

oracle seal実ファイル SHA-256: before `5d135d72e20fb1311bafe7698af1cf1b0ac3516367fcde6142fda5d4e9895480`、after `1c33e8c802cc48afaf2089f521527073b11802e4f395b72c1a489d4a41f3abe0`。6資産のoracle_context以外の意味行は同一。

比較corpus入力digest: before `b80afca5ca0249990661f0e02ffbe2bd6b53b82271d6204b471a84ddf816cef1`、候補after `85213ad695d02c5051f0b39cfdfa9d1137ad4506de5ff33496472336be3bdf17`。現manifest pinはbeforeのまま（正式受理後に再pin）。

## 記録案

| 系列 | 記録案 SHA-256 |
| --- | --- |
| tenant_boundary | `77b2688cbdd4b94499aef38c03b8f49b907ff079dd698476e766b50f93e38cc4` |
| seed_allowlist | `025aa9a386c49258d8b4b87f8138ba8fd350deec7bdc536207f94890d633881e` |
| oracle_input | `fa6ef1fb6bcd63e946ea87bb99454a57a270bb2b8b8b1a0f1b1a916f89586f8f` |

記録案の全文と各22候補ファイルSHAは[完全値JSON](step3-pr174-7-7-candidate.json)を参照。正式履歴は未変更。要件変更履歴の2.15重複はTSK-550行だけ2.16へ採番訂正し、DRAW-03/04本文を保持した。独立限定レビューは初回P0 0/P1 1/P2 1、同じレビュー内の是正照合でP1/P2解消。

## 残るゲート

- 7.7の今回実値・snapshot・corpus・3記録案の正式人間受理。
- #173との共有履歴の実統合順の担当受諾。
- 受理後の正式反映、全件検査、候補製品差分push、最終CI。
- 本人逐行確認、Draft解除、マージは別判断。
