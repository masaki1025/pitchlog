# TSK-424向け要件書確定後の分類・7.7準備

2026-10-17。これは**読み取り専用の受理資料候補**であり、TSK-424の分類受理、7.7の人間確認、凍結JSONの更新を代行しない。基線は`origin/develop`=`e7e8d3a4324687ada828b1e4b49692c087af5c44`、正本確定コミットは`e7e32a8302c0be9e214523565c04a931743e98ef`。その後の本枝の作業ログ・計画候補コミットでは要件書を変更しない。

| 識別値・対象 | 直前 | 確定後 | 判断 |
| --- | --- | --- | --- |
| 要件書Git blob（`contracts/authz/requirement-claims.json#/input_manifest/source_blob_digest`と`shared-preconditions.json#/source_documents`の要件書行） | `c8975e5257ee5f8d4b86b96f3fc779bebd978da4` | `ee6d2508dbdecf34d90c34fc022ff162f73dd3d2` | 値の実測のみ確定。追随の受理・編集はTSK-424側 |
| `requirement-claims.json#/input_manifest/commit` | `7ea324d1ac38057e5b743633bdefd020a4ba1daa` | 正本を収録する候補`e7e32a8302c0be9e214523565c04a931743e98ef` | 最終の入力コミットは所有側が検査規約に従って固定 |
| 抽出全数（`extract_source`） | 1,414行 | 1,417行 | 追加ID 3、削除ID 0、同一IDの本文差分87。番号移動を意味変更と混同しない |
| oracle入力・sealed資産のdigest | 現行`oracle_commit=62fdfe81de7029d49b2b5d80683f49b2dce3e327` | **未生成・未受理** | 8入力blob、6 sealed digest、派生参照の実差分が確定してから再封印要否を判断 |

Git本文差分の実体は、変更履歴1行の追加、NFR-018とNFR-019のT1/T2限定適用条文各1行の追加、10章の既存表1行と付録A-1の既存書式規定1行の追随、frontmatterの`approved`化である。構造抽出の新IDは`CHANGELOG/table_row-049`、`NFR-018/list_item-035`、`NFR-019/list_item-013`。同一ID差分87の内訳は変更履歴48、NFR-018 26、NFR-019 11、10章1、付録A-1 1で、挿入後の既存行の番号移動・本文入替えを含む。TSK-424はGit本文差分だけで判定せず、**旧主張がどの新IDへ移ったか**、新条文が読取・操作の認可主張を新設するか、既存owner/派生資産へ影響するかを行ごとに確定する。旧ownerを番号が同じだけの別本文へ流用しない。

`difflib.SequenceMatcher(autojunk=False)`で旧/新の`(source_kind, source_text)`を全数整列すると、実際の編集は**挿入3・置換2**で、削除は0だった。これが下表の分類候補の母集合である。抽出IDの末尾が変わった行は、同一本文を保持したままの番号移動として別扱いにする。

| 本文操作と確定後ID | 旧ID・旧分類 | 候補分類と根拠 |
| --- | --- | --- |
| 変更履歴追加 `CHANGELOG/table_row-001`（末尾ID `-049` は既存履歴の番号移動） | なし。既存変更履歴は`OUT_DOCUMENT_METADATA` | `out_of_scope` / `OUT_DOCUMENT_METADATA`。過去の承認と変更射程の記録であり操作許可ではない |
| T1/T2対象別の検査適用時期 `NFR-018/list_item-009`（旧`-009`以降は+1、末尾`-035`） | なし。既存NFR-018の全list_itemは`OUT_NON_AUTH_REQUIREMENT` | `out_of_scope` / `OUT_NON_AUTH_REQUIREMENT`。入力軸射影・比較相手・3層検査の適用時期を定める計算保証で、利用者ロール・テナント資源への許可を定めない |
| 生成formatterの対象別適用時期 `NFR-019/list_item-002`（旧`-002`以降は+1、末尾`-013`） | なし。既存NFR-019のlist_itemは`OUT_NON_AUTH_REQUIREMENT` | `out_of_scope` / `OUT_NON_AUTH_REQUIREMENT`。生成・表示経路の時期規定であり操作権限を増減しない |
| 10章 `SECTION-10/table_row-007`の本文追随 | 同ID / `out_of_scope`・`OUT_NON_AUTH_REQUIREMENT` | 既存分類を維持。未決事項/整備対象の現況であり実行権限の規範ではない |
| 付録A-1 `APPENDIX-ITEM-A-1/list_item-009`の本文追随 | 同ID / `out_of_scope`・`OUT_NON_AUTH_REQUIREMENT` | 既存分類を維持。数値/表示書式の境界であり認可の許可/拒否ではない |

同一本文で移動した既存行の中に、旧分類`auth_claim`の行は**0件**。NFR-019の既存`auth_claim`である`NFR-019/paragraph-001`は本文・IDとも不変だった。従って現時点の候補は「新規auth_claim 0、既存auth_claimのowner移転0、認可意味変更0」。**これは作成側の候補であり、TSK-424または独立査読者の分類受理前に正式決定しない**。JSON/lockと派生資産は全数・blobの変化に追随する必要があり得るため、意味変更0を以て7.7や再封印を省略しない。

追随対象の候補は`requirement-claims.json`とlock、`shared-preconditions.json`、分類結果に応じて`route-registry`・`auth-catalog`・`http-route-matrix`と各lock、oracle入力8資産・sealed6資産・`frozen-baselines.json`の適用系列である。**ここでは変更対象を確定しない**。同一セマンティクスで番号移動だけなら、意味変更宣言の要否もTSK-424が根拠付きで判断する。既存受理履歴を上書きせず、PR受理IDが未取得のまま7.7履歴を捏造しない。

再現結果: `test_repository_catalog_covers_the_entire_requirements_file`は旧blobを期待するため失敗（期待`c8975e5257ee5f8d4b86b96f3fc779bebd978da4`、実際`ee6d2508dbdecf34d90c34fc022ff162f73dd3d2`）。`test_repository_derived_assets_are_valid`と`test_repository_oracle_assets_are_valid`は成功。検査の緩和・除外は行わない。所有側が分類・変更順序・最終候補を受理し、7.7-2の直前/直後の**完全な**識別値・変更理由・実際の承認者/日付を人間確認へ提示してから、別コミットで正式追随・検査する。正本確定コミットには凍結資産を混ぜない。

連絡: TSK-424親カードへ確定後の値と受理依頼を追記（Notion comment `3fb93b75-e687-815f-b62b-001de3cf24c8`）。現時点で分類・受取担当・順序の回答は未確認であり、無回答を受理としない。

## 所有側不在時の独立査読・PO代替受理資料

候補作成に関与していない独立Codexセッション`/root/authz_delta_independent_review`が、`origin/develop`と正本確定コミットから全数を読み取り専用で再計算した。結果は**P0 0/P1 0/P2 1**。3挿入2置換、旧auth_claim **187行すべてID・本文不変**、owner移転0、上表の5編集は既定の`out_of_scope`でよいとの判定。P2は正式approved要件書の新2条文に「本改訂候補」が残る表記で、今回の分類・認可意味には影響しない。既承認の正本をこのP2だけで再審査へ戻さず、次の適切な正本文書追随で表記整理の候補とする。**独立査読はTSK-424の受理やPO代替受理そのものではない**。

TSK-424側の明示回答が得られない場合、POへ次の対象**だけ**を代替受理として提示する: (1) 5編集の`out_of_scope`分類と既存87同ID差分の番号移動、(2) auth_claim187行・ownerの不変、(3) 要件書blobの最終前後値と、派生資産は実差分で絞る手順、(4) C1/U-R1との編集順。**凍結資産の具体的なafter digest、7.7履歴、oracle再封印値の承認は別**。この代替受理が無ければ分類を正式決定せず、凍結JSONを編集しない。

## 共有資産の編集順（2026-10-17に確認した実状態）

| 系列 | 実際の状態と重なる資産 | 順序 |
| --- | --- | --- |
| TSK-443 / PR B | PR #87は2026-10-04に`85fce8a7b652217e82116435878faf6c092603f9`で統合済み。現行`origin/develop`に含まれる。ランタイム契約と`data-model.md`の追随は既存基線として保持 | **既済み基線**。別の「B」を指す場合は対象IDの確認が必要 |
| C1 / PR #144 | open。`route-registry`・`http-route-matrix`と各lock、`frozen-baselines.json`、`oracle-seal.lock.json`、sealed6資産の`oracle_context`、`check_authz_catalog.py`等を実際に変更。HEADは確認時`a417d2a54af55ce82921212e29f02f211c54279d` | **C1の正式受理・統合を先行**。その実統合コミットを要件主張候補の入力基線にし、C1の新規GET/認証経路と受理済み履歴を保持。未統合C1ブランチを基線にしない |
| U-R1 / PR #143 | open Draft。現PR差分は`.claude/core-areas.json`・`scripts/core_guard.py`・`tests/test_core_guard.py`とU-R1 feature文書で、現時点の要件書・authz JSONとは重ならない。新ステップ2のRG1製品認可/凍結資産は**候補**で未承認 | #143のguard部分を一律の待ち条件にしない。新2が正式に資産編集へ入る前に単一編集者と統合順を確認。先に統合された側の実developへ後行側が再生成・再受理する |
| 本候補 | `requirement-claims`・lock、`shared-preconditions`、分類で必要ならroute/catalog/matrix各lock、oracle/frozen履歴 | **C1統合後**に隔離生成。U-R1新2と共有する`data-model`/製品DDL/tenant-boundary基準は本候補の範囲外で編集しない。両系列のoracle/frozen履歴が重なる場合は直列化し、双方のafterを併記して解消しない |

## PR番号を要する受理の非循環手順

1. TSK-424の分類・追随範囲の受理（無回答なら上記の対象限定PO代替受理）と、C1の実統合基線を得る。読み取り専用の隔離領域で候補JSON/lock・派生資産の全実差分を生成し、意味変更宣言・oracle再封印の要否を判定する。ここでは正式資産を更新しない。
2. PR番号だけが必要なら、計画・作業ログと受理値未確定の明示だけを準備コミットとしてpushし、**Draft PRを作成する例外承認**をPOから得る。候補の凍結JSON・未受理履歴を先にpushしない。今回の指示からpush/PRの許可は推定しない。
3. oracleが入力コミットSHAを要求する場合、**対象の8入力資産だけ**を固定するローカル中間コミットの限定例外を別途得る。正式authority履歴・意味変更承認宣言・sealed6・再封印を混ぜず、中間コミットは未pushに保つ。必要が無ければこの例外を使わない。
4. Draft番号、比較元develop、入力コミット、8入力blob、6 sealed digest、7.7の直前/直後の完全識別値、意味変更の前後行、既存履歴の保持を一覧で提示し、人間に**7.7・意味変更・再封印を各別に**確認してもらう。受理値が変われば再提示する。
5. 承認済み実値だけを正式反映し、コアレビュー、凍結/認可/oracle/CI検査を最終HEADで通す。既存受理履歴を上書きせず、他担当のafterをそのまま併記しない。PRは人間判断までDraft/未マージのまま維持する。
