# TSK-424向け要件書確定後の分類・7.7準備

2026-10-17。これは**隔離生成した未受理の受理資料候補**であり、7.7の人間確認や凍結JSONの正式更新を代行しない。今回限定の分類・追随範囲はPO代替受理済みだが、TSK-424本人の受理とは記録しない。確定正本の起案時基線は`e7e8d3a4324687ada828b1e4b49692c087af5c44`。C1/#144統合後の`origin/develop`は`3052e0db743877c7f15c0ec10daa0142cba7ab7e`、正本確定コミットは`e7e32a8302c0be9e214523565c04a931743e98ef`。その後の本枝の作業ログ・計画候補コミットでは要件書を変更しない。

| 識別値・対象 | 直前 | 確定後 | 判断 |
| --- | --- | --- | --- |
| 要件書Git blob（`contracts/authz/requirement-claims.json#/input_manifest/source_blob_digest`と`shared-preconditions.json#/source_documents`の要件書行） | `c8975e5257ee5f8d4b86b96f3fc779bebd978da4` | `ee6d2508dbdecf34d90c34fc022ff162f73dd3d2` | 値の実測のみ確定。追随の受理・編集はTSK-424側 |
| `requirement-claims.json#/input_manifest/commit` | `7ea324d1ac38057e5b743633bdefd020a4ba1daa` | 正本を収録する候補`e7e32a8302c0be9e214523565c04a931743e98ef` | 最終の入力コミットは所有側が検査規約に従って固定 |
| 抽出全数（`extract_source`） | 1,414行 | 1,417行 | 追加ID 3、削除ID 0、同一IDの本文差分87。番号移動を意味変更と混同しない |
| oracle入力・sealed資産のdigest | C1統合後`oracle_commit=d5ccc18ef39179857c9a4c793ea28a416432efba` | 隔離候補`e6a0ca0ab6cee5c779851518463eafba6ae146b3`（未受理） | 下表に8入力blob・6 sealed digestの完全値を記録。正式再封印は7.7実値承認後 |

Git本文差分の実体は、変更履歴1行の追加、NFR-018とNFR-019のT1/T2限定適用条文各1行の追加、10章の既存表1行と付録A-1の既存書式規定1行の追随、frontmatterの`approved`化である。構造抽出の新IDは`CHANGELOG/table_row-049`、`NFR-018/list_item-035`、`NFR-019/list_item-013`。同一ID差分87の内訳は変更履歴48、NFR-018 26、NFR-019 11、10章1、付録A-1 1で、挿入後の既存行の番号移動・本文入替えを含む。TSK-424はGit本文差分だけで判定せず、**旧主張がどの新IDへ移ったか**、新条文が読取・操作の認可主張を新設するか、既存owner/派生資産へ影響するかを行ごとに確定する。旧ownerを番号が同じだけの別本文へ流用しない。

`difflib.SequenceMatcher(autojunk=False)`で旧/新の`(source_kind, source_text)`を全数整列すると、実際の編集は**挿入3・置換2**で、削除は0だった。これが下表の分類候補の母集合である。抽出IDの末尾が変わった行は、同一本文を保持したままの番号移動として別扱いにする。

| 本文操作と確定後ID | 旧ID・旧分類 | 候補分類と根拠 |
| --- | --- | --- |
| 変更履歴追加 `CHANGELOG/table_row-001`（末尾ID `-049` は既存履歴の番号移動） | なし。既存変更履歴は`OUT_DOCUMENT_METADATA` | `out_of_scope` / `OUT_DOCUMENT_METADATA`。過去の承認と変更射程の記録であり操作許可ではない |
| T1/T2対象別の検査適用時期 `NFR-018/list_item-009`（旧`-009`以降は+1、末尾`-035`） | なし。既存NFR-018の全list_itemは`OUT_NON_AUTH_REQUIREMENT` | `out_of_scope` / `OUT_NON_AUTH_REQUIREMENT`。入力軸射影・比較相手・3層検査の適用時期を定める計算保証で、利用者ロール・テナント資源への許可を定めない |
| 生成formatterの対象別適用時期 `NFR-019/list_item-002`（旧`-002`以降は+1、末尾`-013`） | なし。既存NFR-019のlist_itemは`OUT_NON_AUTH_REQUIREMENT` | `out_of_scope` / `OUT_NON_AUTH_REQUIREMENT`。生成・表示経路の時期規定であり操作権限を増減しない |
| 10章 `SECTION-10/table_row-007`の本文追随 | 同ID / `out_of_scope`・`OUT_NON_AUTH_REQUIREMENT` | 既存分類を維持。未決事項/整備対象の現況であり実行権限の規範ではない |
| 付録A-1 `APPENDIX-ITEM-A-1/list_item-009`の本文追随 | 同ID / `out_of_scope`・`OUT_NON_AUTH_REQUIREMENT` | 既存分類を維持。数値/表示書式の境界であり認可の許可/拒否ではない |

同一本文で移動した既存行の中に、旧分類`auth_claim`の行は**0件**。NFR-019の既存`auth_claim`である`NFR-019/paragraph-001`は本文・IDとも不変だった。従って現時点の候補は「新規auth_claim 0、既存auth_claimのowner移転0、認可意味変更0」。**この分類と追随範囲は2026-10-17のPO裁定で今回のADR-003追随に限る代替受理済み**（TSK-424本人の同意とは記録しない）。JSON/lockと派生資産は全数・blobの変化に追随する必要があり得るため、意味変更0を以て7.7や再封印を省略しない。

追随対象は隔離候補で実差分を確認した`requirement-claims.json`とlock、`shared-preconditions.json`、`route-registry`・`auth-catalog`・`http-route-matrix`と各lock、oracle入力8資産・sealed6資産・`frozen-baselines.json`の適用系列である。分類・追随範囲は今回限定のPO代替受理済みで、**実値の7.7・再封印は未受理**。同一セマンティクスの番号移動について新たな意味変更宣言は不要との候補判断を維持し、既存受理履歴を上書きしない。PR受理IDが未取得のまま7.7履歴を捏造しない。

正本確定直後の再現結果: `test_repository_catalog_covers_the_entire_requirements_file`は旧blobを期待するため失敗（期待`c8975e5257ee5f8d4b86b96f3fc779bebd978da4`、実際`ee6d2508dbdecf34d90c34fc022ff162f73dd3d2`）。当時の`test_repository_derived_assets_are_valid`と`test_repository_oracle_assets_are_valid`は成功。C1統合後の隔離候補に対する検査結果は末尾に別記する。検査の緩和・除外は行わない。7.7-2の直前/直後の**完全な**識別値・変更理由・実際の承認者/日付を人間確認へ提示してから正式追随・検査する。正本確定コミットには凍結資産を混ぜない。

連絡: TSK-424親カードへ確定後の値と受理依頼を追記（Notion comment `3fb93b75-e687-815f-b62b-001de3cf24c8`）。TSK-424本人の回答は未確認。独立査読と2026-10-17のPO対象限定裁定を代替受理の根拠とし、無回答をTSK-424同意とは扱わない。

## 所有側不在時の独立査読・PO代替受理資料

候補作成に関与していない独立Codexセッション`/root/authz_delta_independent_review`が、`origin/develop`と正本確定コミットから全数を読み取り専用で再計算した。結果は**P0 0/P1 0/P2 1**。3挿入2置換、旧auth_claim **187行すべてID・本文不変**、owner移転0、上表の5編集は既定の`out_of_scope`でよいとの判定。P2は正式approved要件書の新2条文に「本改訂候補」が残る表記で、今回の分類・認可意味には影響しない。既承認の正本をこのP2だけで再審査へ戻さず、次の適切な正本文書追随で表記整理の候補とする。**独立査読単体は受理ではなく、2026-10-17のPO裁定が対象限定の代替受理を与えた**。

POが2026-10-17に次の対象**だけ**を代替受理した: (1) 5編集の`out_of_scope`分類と既存87同ID差分の番号移動、(2) auth_claim187行・ownerの不変、(3) 要件書blobの最終前後値と、派生資産は実差分で絞る手順、(4) C1/U-R1との編集順。**凍結資産の具体的なafter digest、7.7履歴、oracle再封印値の承認は別**。この代替受理が無ければ分類を正式決定せず、凍結JSONを編集しない。

## 共有資産の編集順（2026-10-17に確認した実状態）

| 系列 | 実際の状態と重なる資産 | 順序 |
| --- | --- | --- |
| TSK-443 / PR B | PR #87は2026-10-04に`85fce8a7b652217e82116435878faf6c092603f9`で統合済み（GitHubの`mergeCommit`で再確認）。現行`origin/develop`に含まれる。ランタイム契約と`data-model.md`の追随は既存基線として保持 | **既済み基線**。別の「B」を指す場合は対象IDの確認が必要 |
| C1 / PR #144 | **2026-10-17 JSTまでに統合済み**。統合SHA=`3052e0db743877c7f15c0ec10daa0142cba7ab7e`。統合前の`route-registry`・`http-route-matrix`と各lock、`frozen-baselines.json`、`oracle-seal.lock.json`、sealed6資産の`oracle_context`、`check_authz_catalog.py`等を実際に変更。HEADは確認時`a417d2a54af55ce82921212e29f02f211c54279d` | **先行統合済み**。実統合コミットを要件主張候補の入力基線にし、C1の新規GET/認証経路と受理済み履歴を保持。未統合C1ブランチを基線にしない |
| U-R1 / PR #143 | open Draft。現PR差分は`.claude/core-areas.json`・`scripts/core_guard.py`・`tests/test_core_guard.py`とU-R1 feature文書で、現時点の要件書・authz JSONとは重ならない。新ステップ2のRG1製品認可/凍結資産は**候補**で未承認 | #143のguard部分を一律の待ち条件にしない。新2が正式に資産編集へ入る前に単一編集者と統合順を確認。先に統合された側の実developへ後行側が再生成・再受理する |
| 本候補 | `requirement-claims`・lock、`shared-preconditions`、分類で必要ならroute/catalog/matrix各lock、oracle/frozen履歴 | **C1統合後の`3052e0db`基線から隔離生成済み。U-R1新2と共有する`data-model`/製品DDL/tenant-boundary基準は本候補の範囲外で編集しない。両系列のoracle/frozen履歴が重なる場合は直列化し、双方のafterを併記して解消しない |

## PR番号を要する受理の非循環手順

1. TSK-424分類・追随範囲のPO対象限定代替受理と、C1の実統合基線を得た。読み取り専用の隔離領域で候補JSON/lock・派生資産の全実差分を生成し、意味変更宣言・oracle再封印の要否を判定する。ここでは正式資産を更新しない。
2. PR番号だけが必要なら、計画・作業ログと受理値未確定の明示だけを準備コミットとしてpushし、**Draft PRを作成する例外承認**をPOから得る。候補の凍結JSON・未受理履歴を先にpushしない。今回の指示からpush/PRの許可は推定しない。
3. oracleが入力コミットSHAを要求する場合、**対象の8入力資産だけ**を固定するローカル中間コミットの限定例外を別途得る。正式authority履歴・意味変更承認宣言・sealed6・再封印を混ぜず、中間コミットは未pushに保つ。必要が無ければこの例外を使わない。
4. Draft番号、比較元develop、入力コミット、8入力blob、6 sealed digest、7.7の直前/直後の完全識別値、意味変更の前後行、既存履歴の保持を一覧で提示し、人間に**7.7・意味変更・再封印を各別に**確認してもらう。受理値が変われば再提示する。
5. 承認済み実値だけを正式反映し、コアレビュー、凍結/認可/oracle/CI検査を最終HEADで通す。既存受理履歴を上書きせず、他担当のafterをそのまま併記しない。PRは人間判断までDraft/未マージのまま維持する。

## C1統合後の隔離候補と7.7実値（2026-10-17）

PR #144の実統合SHAは`3052e0db743877c7f15c0ec10daa0142cba7ab7e`。隔離枝`feature/adr003-authz-candidate`の入力固定コミット`e6a0ca0ab6cee5c779851518463eafba6ae146b3`は**oracle入力8資産だけ**を含み、pushしていない。要件書は正本確定の`ee6d2508dbdecf34d90c34fc022ff162f73dd3d2`、台帳の旧blobは`c8975e5257ee5f8d4b86b96f3fc779bebd978da4`。追加3/置換2はPO対象限定代替受理の分類どおりで、auth_claim187行とownerは全件不変。C1の`GET /auth/session`、route/catalog/matrixの本体配列、#144を含む既存11件の凍結履歴を保持する。

| 8 oracle入力のpath | C1統合後の直前blob | 今回の隔離候補blob |
| --- | --- | --- |
| `contracts/authz/requirement-claims.json` | `61c5e0579fc4b514cdd38cc888ff1cde622bbf65` | `ad830901cd6e9427b3becc5e9502934cbb39dfde` |
| `contracts/authz/requirement-claims.lock.json` | `a5c278112c17441a178c5ef7d237e83a46a2950f` | `4d5fbefae3d0dc5836d9e8b24510e1ce79e4c7c5` |
| `contracts/authz/route-registry.json` | `2cd82db822df203d9608b6d72e4bbfb518dab2ad` | `4198b7039e96d083ebc18f145b4e85a8bd354028` |
| `contracts/authz/route-registry.lock.json` | `e110a75541cca22d349fe6f765e7b8c7ba741e64` | `94d118e93770be103200ab1e8465f3218c3be34d` |
| `contracts/authz/auth-catalog.json` | `06ffccaf5e21c34991129ee9a636ac0b77984363` | `945b90d609147aa85b1cdfdd00fa38df81275809` |
| `contracts/authz/auth-catalog.lock.json` | `0467a4cbc0ab5a7607058db5fba6b0508e7d970f` | `5ce421a4ec8180a8df764793c8d098b49c7ed6b3` |
| `contracts/authz/http-route-matrix.json` | `c2d03ad51a9d1961e1fdf5c5730e4705acf6907e` | `bcd223b31fce14acb25a068b0d0b6265dcd440ce` |
| `contracts/authz/http-route-matrix.lock.json` | `5882c2b918ed8d06feb12fa905434d916b685c7f` | `13fb097fdf63436494923351b99cf6063f2681cf` |

| 6 sealed資産のpath | C1統合後の直前canonical SHA-256 | 今回の隔離候補canonical SHA-256 |
| --- | --- | --- |
| `contracts/authz/ddl-elements.json` | `22ba361a9331d714f1ccf75d64fd224acba959d4841cba8bcf0b796a1c3663b1` | `8a11a4eef84ece58474001171d677904dacc78c21438e15395d1f86ddf70f0a6` |
| `contracts/authz/rejected-configs.json` | `6e1cd82f7890b17ff6e51a53fc0771226fcd84f9aeeeb4d832c07a6073fd5af9` | `b4c468f1c2a655147337eabc8c651df5482e236df6e80f9d5c40deeb44d93268` |
| `contracts/authz/claim-mutant-map.json` | `9abfd153d134c7c9cc0839291a45faefa098a1100baeeabd86738592a2ffa70a` | `1b6b97f1a1f1a13bc01098a6fa2846205845ec1f3284fe4a5f98e56fa7b9cb21` |
| `contracts/authz/attack-tree.json` | `535154875b3eed4b4ecd73f33feee982c03a9ad48f2e3a269a7fdf05a63bdba4` | `b225ce42003910a19163e4ecb2f93733e73594e949d989e8683a410f79384e78` |
| `contracts/authz/boundary-proposal.json` | `bbfeaf93c95d6e0b29c76ba074063fd372edd0235a44d9d0721681c07876d627` | `70ff5e51bc5508076ff8600c048bcefebde0f87afb8eb5e23744e785fe4a811e` |
| `contracts/authz/verification-evidence.json` | `4f70c83f3b475ab2005ab1678183633c770c789c1f659b94a0bd5b992c928759` | `94a6d5497c4d582718d472ca33e531019445f185da0835928c775083b7bcc81b` |

`oracle_input`系列の7.7前後識別値は **`d5ccc18ef39179857c9a4c793ea28a416432efba` → `e6a0ca0ab6cee5c779851518463eafba6ae146b3`**。配置・宣言・同一性の粒度と既存履歴は維持。6資産は`oracle_context.oracle_commit`のみの差分で、認可/owner/oracle内容に新たな意味変更はない。`shared-preconditions.json`の候補差分は要件書blobの1行だけ。

**受理記録案（まだ正式JSONへ追記しない）**: 番号取得用の文書Draft PRは **#145**。`acceptance_id=masaki1025/pitchlog#145`、`series=oracle_input`、`prior_identity={present:true,values:[{kind:literal_commit_string,value:d5ccc18ef39179857c9a4c793ea28a416432efba}]}`、`new_identity={present:true,values:[{kind:literal_commit_string,value:e6a0ca0ab6cee5c779851518463eafba6ae146b3}]}`、`changes=[]`、`placement_change`前後同一、`moved=false`。`approved_by`/`approved_at`は7.7の実値承認前のため**未記入**。理由案: 「ADR-003 D-14-m/要件書v2.15の確定に伴い、認可外5編集の分類と要件書入力blobを更新。C1/#144のGET経路・既存履歴を保持し、oracle入力8資産の変更を直列に再封印。認可主張187行、owner、同一性粒度、配置、oracleの意味は不変」。この理由・完全値をPOが正式確認してから記録する。

正式台帳へ追記する**1件の構造案**は次のとおり。`approved_by`・`approved_at`のプレースホルダーは**未受理を示す資料用**であり、正式JSONには書かない。#144を末尾とする既存11件の後ろへ直列に1件だけ加え、既存要素は変更しない。

```json
{
  "acceptance_id": "masaki1025/pitchlog#145",
  "series": "oracle_input",
  "new_identity": {"present": true, "values": [{"kind": "literal_commit_string", "value": "e6a0ca0ab6cee5c779851518463eafba6ae146b3"}]},
  "prior_identity": {"present": true, "values": [{"kind": "literal_commit_string", "value": "d5ccc18ef39179857c9a4c793ea28a416432efba"}]},
  "changes": [],
  "placement_change": {
    "before": [{"kind": "ledger_series", "path": "contracts/authz/frozen-baselines.json", "series": "oracle_input"}],
    "after": [{"kind": "ledger_series", "path": "contracts/authz/frozen-baselines.json", "series": "oracle_input"}]
  },
  "moved": false,
  "reason": "ADR-003 D-14-m/要件書v2.15の確定に伴い、認可外5編集の分類と要件書入力blobを更新。C1/#144のGET経路・既存履歴を保持し、oracle入力8資産の変更を直列に再封印。認可主張187行、owner、同一性粒度、配置、oracleの意味は不変。",
  "approved_by": "<7.7実値承認後に記入>",
  "approved_at": "<7.7実値承認後に記入>"
}
```

**検査とレビュー**: 母集合・lock単独検査は`1417/187/1230`で成功、派生lock再封印検査は`db_claims=191 routes=48 cells=12`で成功。`check_shared_preconditions.py`は6件成功。`validate_oracle_seal`は入力固定コミット・8blob・6digestの照合に成功した。通常の全oracle検査と`test_repository_catalog_covers_the_entire_requirements_file`は、未承認の`frozen-baselines.json`が直前値を保持するため`boundary proposal の oracle_commit が基準版と不一致`で停止する（対象2試験は1成功/1失敗）。検査を緩めず、7.7実値の人間受理後に再実行する。独立Codex査読はP0 0/P1 0/P2 1で、P2は本資料のC1統合前記述だったため今回是正した。**この査読は7.7・oracle再封印の人間受理ではない**。

**正本文言P2の処置**: 確定要件書の新2条文にある「本改訂候補」は、採用済み条文であることとの表記不整合として記録する。今ここで正本本文を直すと要件書blobと承認済みの3挿入/2置換という分類母集団が変わるため、今回の認可候補には混ぜない。次の正本文書改訂または規約7.6で認められる独立の表記是正ゲートへ送る。意味上の例外・認可主張の追加とは扱わない。

### 8入力のファイルSHA-256（判断資料の追加固定値）

上表のGit blob digestはSHA-1形式のGitオブジェクト識別値である。次表は同じ2コミットから読んだ**ファイルの生バイト列**のSHA-256で、sealed6資産のcanonical SHA-256とは算定対象が異なる。候補側の8入力は2026-10-17のPO指示で**今回限定のローカル中間コミット**として許可されたが、pushと7.7正式受理は別である。

| 入力path（`contracts/authz/`配下） | #144統合コミットの生ファイルSHA-256 | ローカル入力コミットの生ファイルSHA-256 |
| --- | --- | --- |
| `requirement-claims.json` | `2e6d1a80620dbd9e7b0a9b3aa2913d8b6448004f70d56d15835a3f9acebd560e` | `91982af7c97eb373a99ac20730056d11a747b1233f63a3d30819a3f1748ec821` |
| `requirement-claims.lock.json` | `8364d93bba2f865d649b84a042447d389978029af4b887342f13a3825580c579` | `3fc36dc92ff56a5f066e8e8499523458df4601ecb51fdf3f855627e9191edb50` |
| `route-registry.json` | `b859c6e53dbace7a6cafc4268da4a97110c21cbbc48d614c8617a2b56347ccc1` | `7157896098cd99001876fecaa3e46367f6f3940031e6b676d87aedb62c5d41d6` |
| `route-registry.lock.json` | `d25871e3b2996f67afa41c8a83cb89ea3f58bd1890d45542d31039ead15865fb` | `7a2f0679ce2d952c59a8fa7468d31b4b8a85ab7f709a0854a22291e260f24698` |
| `auth-catalog.json` | `40de57dada8139cec3ad535c210117e44ba11ee44bde8d7bcc2692ec7036a077` | `84f7be77119093f4b872a7049174363c388afdb5f9e5e49b62d33084d6048140` |
| `auth-catalog.lock.json` | `59f3b4c9553b45c73a7130932234359827ee5c9ce575d5c2e9077871ec2d3dab` | `018ce5619393c1f06e65f22989ec11e2bc39d9da49c18d881279c133ea0281ac` |
| `http-route-matrix.json` | `bea3d8453ac0f5ffc7ceab3faf4a8b75264c016b4a4eb727ddd553f8f305b67e` | `80bc1fb43cf7d2dcfb26fc3b64c7b6f39ec30e64032553c8d26c18bc068a31db` |
| `http-route-matrix.lock.json` | `c14b3e85d56012425d66264b0711a5db16af4f4d51fecd00ae85e3cf75ab0f2b` | `baa8185ac6103527a3d03388986c5e8745f2bb4164f43aa5955aeaa4846e8cb4` |
