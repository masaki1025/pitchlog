# TSK-424向け要件書確定後の分類・7.7準備

2026-10-17。これは**読み取り専用の受理資料候補**であり、TSK-424の分類受理、7.7の人間確認、凍結JSONの更新を代行しない。基線は`origin/develop`=`e7e8d3a4324687ada828b1e4b49692c087af5c44`、正本確定コミットは`e7e32a8302c0be9e214523565c04a931743e98ef`。その後の本枝の作業ログ・計画候補コミットでは要件書を変更しない。

| 識別値・対象 | 直前 | 確定後 | 判断 |
| --- | --- | --- | --- |
| 要件書Git blob（`contracts/authz/requirement-claims.json#/input_manifest/source_blob_digest`と`shared-preconditions.json#/source_documents`の要件書行） | `c8975e5257ee5f8d4b86b96f3fc779bebd978da4` | `ee6d2508dbdecf34d90c34fc022ff162f73dd3d2` | 値の実測のみ確定。追随の受理・編集はTSK-424側 |
| `requirement-claims.json#/input_manifest/commit` | `7ea324d1ac38057e5b743633bdefd020a4ba1daa` | 正本を収録する候補`e7e32a8302c0be9e214523565c04a931743e98ef` | 最終の入力コミットは所有側が検査規約に従って固定 |
| 抽出全数（`extract_source`） | 1,414行 | 1,417行 | 追加ID 3、削除ID 0、同一IDの本文差分87。番号移動を意味変更と混同しない |
| oracle入力・sealed資産のdigest | 現行`oracle_commit=62fdfe81de7029d49b2b5d80683f49b2dce3e327` | **未生成・未受理** | 8入力blob、6 sealed digest、派生参照の実差分が確定してから再封印要否を判断 |

Git本文差分の実体は、変更履歴1行の追加、NFR-018とNFR-019のT1/T2限定適用条文各1行の追加、10章の既存表1行と付録A-1の既存書式規定1行の追随、frontmatterの`approved`化である。構造抽出の新IDは`CHANGELOG/table_row-049`、`NFR-018/list_item-035`、`NFR-019/list_item-013`。同一ID差分87の内訳は変更履歴48、NFR-018 26、NFR-019 11、10章1、付録A-1 1で、挿入後の既存行の番号移動・本文入替えを含む。TSK-424はGit本文差分だけで判定せず、**旧主張がどの新IDへ移ったか**、新条文が読取・操作の認可主張を新設するか、既存owner/派生資産へ影響するかを行ごとに確定する。旧ownerを番号が同じだけの別本文へ流用しない。

追随対象の候補は`requirement-claims.json`とlock、`shared-preconditions.json`、分類結果に応じて`route-registry`・`auth-catalog`・`http-route-matrix`と各lock、oracle入力8資産・sealed6資産・`frozen-baselines.json`の適用系列である。**ここでは変更対象を確定しない**。同一セマンティクスで番号移動だけなら、意味変更宣言の要否もTSK-424が根拠付きで判断する。既存受理履歴を上書きせず、PR受理IDが未取得のまま7.7履歴を捏造しない。

再現結果: `test_repository_catalog_covers_the_entire_requirements_file`は旧blobを期待するため失敗（期待`c8975e5257ee5f8d4b86b96f3fc779bebd978da4`、実際`ee6d2508dbdecf34d90c34fc022ff162f73dd3d2`）。`test_repository_derived_assets_are_valid`と`test_repository_oracle_assets_are_valid`は成功。検査の緩和・除外は行わない。所有側が分類・変更順序・最終候補を受理し、7.7-2の直前/直後の**完全な**識別値・変更理由・実際の承認者/日付を人間確認へ提示してから、別コミットで正式追随・検査する。正本確定コミットには凍結資産を混ぜない。

連絡: TSK-424親カードへ確定後の値と受理依頼を追記（Notion comment `3fb93b75-e687-815f-b62b-001de3cf24c8`）。現時点で分類・受取担当・順序の回答は未確認であり、無回答を受理としない。
