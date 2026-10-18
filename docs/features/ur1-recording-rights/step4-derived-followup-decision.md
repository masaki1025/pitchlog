# U-R1 新4: #145・#146統合後の派生検査と7.7最終照合（2026-10-18）

## 状態と境界

- #145は`188acf839d4a5f4f42e9c7f5025f8bf3931e3bcb`で`develop`へ統合済み。featureブランチはこれをmergeし、ローカルHEADは`46ac9ea9d4055e5236f6da59ae964baabb9ac4dd`。既受理の#145正本・oracle・履歴は維持する。後述の追加差分は未コミット候補。
- その後#146が`ce0c0e8697252a89bce0c57e69b4821e0a6cac2b`で`develop`へ統合されたため、featureブランチへ再度mergeした（現ローカルHEAD `8780eb0a5c3c4fe7a6b8036ff03bb4e4a5bac0e6`）。#146はpytest一時領域の移送で、9凍結資産・8外部入力・RG1 seed・正本本文には触れない。現`origin/develop`から9資産のbefore、現候補からafterをそれぞれ再投影し、**前後9件のsnapshotと外部入力8件が下記の既受理記録案に全件一致**。#146で追加された`backend/tests/conftest.py`に対してU-R1差分は0行。
- 公開中のDraft PR #143は準備HEAD `cd03ddcb028878ac5c43dc9823463974040a29eb`。候補のpush・PR本文更新・本人逐行確認・Draft解除・マージは未実施。
- POはORM受理シートの再生成・N4新規1行の「一致」、`shared-preconditions.json`の`data-model.md`実blob追随、RG1原子7件の写像、関連するテスト前提追随を承認済み。新しい製品権限は作らない。
- **2026-10-18の最終実測**: 最新`origin/develop`は`ce0c0e8697252a89bce0c57e69b4821e0a6cac2b`で不変。専用使い捨てPostgreSQLで`backend/tests/db`全630件（32分12秒）と、同ディレクトリ外のDB必須27件（79秒）がそれぞれ終了コード0。後者には既存のpytest plugin再読込warningが1件ある。backend/rootのRuff・ty、backend format、`git diff --check`も成功。公開PRのCIではなく、未pushローカル候補の検査である。

## 正本への2種類の束縛値

正本`docs/design/data-model.md` v0.11の実blobは`21a85f5e794baaa05376b06aec7185cada6c33c8`、ファイル内容SHA-256は`a4504bbb2cf3fcbec13ea4fbb0ccd7d8ab2b9b66dafec3fc01f763ed06b16bfc`。正本自体は変更しない。

| 候補資産のフィールド | before | ローカルafter候補 | 根拠 |
| --- | --- | --- | --- |
| `contracts/authz/shared-preconditions.json#/source_documents/1/git_blob_digest` | `7155ddf804ed21ef778cffeb334528df8f5e3f56` | `21a85f5e794baaa05376b06aec7185cada6c33c8` | 承認済み正本の実Git blob |
| `contracts/db/schema-manifest.json#/canonical_source/sha256` | `518ca3f65c9526f5d42550ac7fbac7b2ee2f5354922d525fdc1233f8ca1661ff` | `a4504bbb2cf3fcbec13ea4fbb0ccd7d8ab2b9b66dafec3fc01f763ed06b16bfc` | 最新`origin/develop`の実値→承認済み正本の実ファイル内容SHA-256。あわせてRG1表を45→46表へ追加 |

実統合SHAの`origin/develop`で、`shared-preconditions.json`全blobは`4243eb8f5bcf0ca40c986c55661ec73ece93947a`→候補`53497616665542fb5c98275b8df17316f8da7be6`、内容SHA-256は`7e6299fb59bae0842d3b72888469e9c4615ba86ac3e8ce71a01c7283873db40c`→`c745c6016c44ac09693e102de4dc43714ffa264d6eb01b0175c57a90723169f0`。#145が受理した要件書側digest `ee6d2508dbdecf34d90c34fc022ff162f73dd3d2`はbefore/afterとも不変で、U-R1はdata-model側だけを旧`7155dd…`から実blob`21a85f…`へ動かす。`schema-manifest.json`全blobは実before`ae83ea8484b31574e550aa5fe7df2f1c17432f10`→候補`d0efb89b6b131f9f87461df6dd0dfb511e2cc490`、内容SHA-256は`2655dd8d8c87b967efbb33d883cf6bff43398dcacaf159d46c72b3bb886cb50a`→`e2b2c166e7e63a86f863a595d5fac708fa24d9e1fe6259d1d495f974e4a5c2da`。全差分は正本digest更新と、承認済みRG1単一状態表の完全宣言1件の追加。

今回追加承認された`probe-product-map.json`も、製品原子7件の処分集合を動かす。実before全blob `09d5b7e63d829daff7160c9f455d932d774416bc`→候補`3f23368fd0e004688f12ce344e384766ab4d38f9`、内容SHA-256 `2256cfa57fcc56b394597d606f416c4e7b585fa442a77f17691829b807efe200`→`e755623b0b500ea4e2d3946d43242485e572cb0dca471785f86f08c7dabc99cd`。旧写像行を維持し、追加7行の`reason`はすべて`product_only`。

**7.7の適用確認**: 上記3資産は`baseline_control`と`history_authority`を持たない。既存の承認済み運用（`docs/features/runtime-contract-switch/plan.md` ステップ7、`docs/worklog/2026-10-13-game-type-seed-rls-review.md`）では、`shared-preconditions.json`と`schema-manifest.json`の正本digest追随は新たな7.7正式履歴を要しない派生更新としている。写像も同じTSK-479で`product_only`追加とともに扱われた。今回の3資産の完全before/afterと理由はこの資料・worklogへ記録し、**#143の権威台帳・seed台帳へ別の未受理記録を作らない**。#145に受理済みのoracle入力・seal・履歴も変更しない。新しい凍結宣言や同一性粒度は追加していない。

現候補で`contracts/authz/*.lock.json`、`oracle-seal.lock.json`、`frozen-baselines.json`、#143のtenant-boundary9資産と既受理履歴、seed記録に`origin/develop`取り込み後の追加差分はない。`shared-preconditions.json`と`schema-manifest.json`はoracle sealの8入力にも#143の9資産にも含まれない。#145自身のoracle入力8資産・seal・履歴は受理済みの実基線として保持する。#143の9資産のrevision・snapshotを最新developから再導出し、前後9件すべて従来受理値と一致した。

### #143の7.7正式受理値を実基線で再照合

`frozen_history.py::frozen_projection_content`へ、beforeは`origin/develop`の資産・外部入力、afterは現候補の資産・外部入力を渡して再計算した。#145統合後も、変化する3資産の実値は次のとおりで、既受理の[9資産全表・単一記録案](step4-c1-merged-7.7-record-proposal.json)と完全一致する。残り6資産はrevision・snapshotともbefore=afterであり、その値も同記録案と一致する。

| 資産 | before revision / snapshot SHA-256 | after revision / snapshot SHA-256 |
| --- | --- | --- |
| `base-allowlist.json` | 32 / `20c8f0f71734d244e8734a0ded0903d380cfcae79315549ccd318a8a6e6ebabf` | 33 / `e3dcdd745a721431a5ecdfd0cfa43f9f5839a79678d34e81fa76a3ea15746046` |
| `repository-contract.json` | 20 / `71cb7a8bba95d335571411198044da40b1ac05d06707a9c34a9fb396bf6c2a00` | 21 / `0daf9ec4b9d5dc7eea364a0001804ba187f3bed87e02850f2da5b21613dc0e11` |
| `runtime-authz-contract.json` | 16 / `a335d85ba04eb9d7f002009ecaf2f7229f410c2a5335929b8d2ddf960af0a53a` | 17 / `061eeb9e96f110e059ad51bf3026d9b420f7c636a24045809afa33e7a0f6b393` |

afterの新snapshot3件は既に#143候補に存在し、実サイズは11,864・7,560・6,550バイト。afterの`source_digest`はrepository=`117c924bf5c0174b4846c301d3a6fbb0e2457283fccd2edbf7de7a3139baedae`、runtime=`13eeb95f54a8a713620a12c369505311349e72148c521141ed524ece91b0f62d`で既受理値のまま。seed別系列`rg1_closed_seed`もbefore不存在→after `sha256_canonical_json:d6d05be6344a266d4ec63e2750694aa4b71341c119e03fbd3460f73cab1b7fb0`、投入行`(singleton_id=1,state='closed')`、実承認情報を保持する。#143の受理済み単一履歴、before側、先行履歴、#145の別系列履歴は変更しない。したがって**9資産・snapshot・seedについて新しい受理値への変更はない**。上段の派生3資産の前後値だけが今回提示する追加差分である。

## ORMシートとテスト候補

旧4シート計362行の人間判定・理由をすべて保持した。N1=103、N3=105、N7=100は行数不変。N3の5行ではRG1のmanifest候補表示だけが増え、各行の「列の不変性ではない」という既存`対象外`理由は引き続き該当する。N4は54→55行で、追加行は次の1件だけ。POが2026-10-17に「一致」と判定した。

| 対象 | 正本側 | 実装側 | 確定した判定・理由 |
| --- | --- | --- | --- |
| `rg1_restore_gate` | data-model §11-1の直接割当有無、§3-2の単一状態行 | manifest `lifecycle.deletion=対象外` | `一致`。§3-2の単一状態行は削除操作を持たず、manifestの`対象外`と整合する。§11-1に削除系統の直接割当はない |

`tests/test_orm_acceptance_sheets.py`のN4期待数は55へ更新済み。既存判定を自動持越しで空欄化せず、旧362件を保持した。N4追加1行の正式判定を今回のPO回答に基づき記入した。

backendの旧45表・13件function_only・旧ロール/スキーマ/policy集合のテスト期待値は、RG1の46表・14件・専用owner/schema/2 policyへ追随済み。RG1のclosed行はmigration投入なので、通常の手動seed計画からだけ明示除外し、分類母集合には残した。テスト専用fixtureの表数も46へ追随。製品コード・DDL・認可許可は不変。

## 追加承認済みの写像・migration 試験追随

1. `contracts/authz/product/probe-product-map.json`の`product_only`に、次の製品原子7件を各1行・`reason=product_only`で追加した。独立したprobe側対応物はなく、許可を広げず、双方向exact-set検査を回復する。実資産で232製品原子の全数照合が成功し、RG1原子を1件除いた負例も失敗を確認した。

   - `function:FUNCTION:rg1_api:rg1_assert_open_before_commit(uuid)`
   - `function:FUNCTION:rg1_api:rg1_read_open(uuid)`
   - `policy:POLICY:rg1_restore_gate:rg1_fn_lock_singleton`
   - `policy:POLICY:rg1_restore_gate:rg1_fn_select_singleton`
   - `role:pitchlog_rg1_fn_owner`
   - `schema:rg1_api`
   - `table:rg1_restore_gate`

2. `backend/tests/db/test_alembic_migrations.py::test_0028_preflight_restores_product_force_rls_after_success`は、0028時点の版番号・RG1表不在・既存FORCE状態・テナント表の取消を確認し、HEAD復帰後にRG1閉鎖単一行を確認する。downgradeで失ったRG1表の認可を正規資産から再適用し、HEAD全製品カタログを再検査する。使い捨てDBの単独試験は成功した。検査の削除・skip・許容集合の無限定化と製品migration変更はない。

この2点の追加範囲と、ORM・digest・写像・migration試験の直接影響に限る独立レビュー1回はPOが承認済み。レビュー前の固定候補から変更したときは差分を識別して採否を記録する。

## 実測と次のゲート

- 今回承認された独立差分レビュー1回は、tracked diff SHA-256 `9fc870cf2159ad8de4d016ccb89472e791659df53e0f20d145f0fc6e7c526836`で実施し、P0/P1/P2=0、追加指摘なし。レビュア独立実測の関連146件が成功。その後のDB試験で発見した1ファイル限定のRG1単一行前提修正はPOが採用承認したが、**独立再レビュー未実施**。他表2行以上とapp直接SELECTの42501を維持し、隔離DB関連40件が一括成功。今回の採用は本人逐行確認を代替しない。
- backendの非DB試験は1925成功・4 skip・647 DB必須除外・テスト失敗0。プラグインの「DB必須0件」終了コード1を全件greenには読み替えない。POのN4「一致」判定反映後、ORM受理シート13件全成功、旧362行の判定・理由は全件一致。backend関連126件、backend/root Ruff・ty、backend format、shared preconditions、認可catalog1414・function bodies・frozen-baselines不変、tenant-boundary bypassは成功。DB全件・CIを全成功とは扱わない。

- 追加承認前の実測: 低並列2・専用一時領域で、先の6 timeoutを含むハーネス関連375件が一括成功。backend非DB全件は1919成功・4 skip・5失敗で、5件は当時のprobe写像未登録から生じた。関連期待値136件中、追随後135件成功・残りの手動seed前提を修正して18件成功。backend/root Ruff・format check・ty、authz catalog1414項目、function bodies、shared preconditions、frozen-baselines不変、tenant-boundary bypass、docs-statusは成功。
- 追加承認前の実測: backend DB必須全件は専用使い捨てPostgreSQLへホストTCPで接続し、8分57秒で138成功・上記0028試験1失敗の時点で停止。全件成功ではない。共有DBの初回641 setup errorは既存ロール、`docker exec`による専用DB診断失敗はホスト`/tmp`満杯が原因。共有DB/`/tmp`やtimeout条件を変更せず、隔離接続では3回目の照合で起動成功。
- d815の独立レビュー枠と今回の追加レビュー1回は使用済み。N4新規行はPO判定「一致」を記入済み。#145統合後の#143実7.7値は上表のとおり既受理値と一致し、履歴・snapshot・seedの既受理beforeと先行履歴を維持する。正式受理をやり直す新値はない。

### #145統合後の追加実測

- ORMシート4枚を実正本とmanifestからメモリ上で再生成し、363行の対象・正本欄・実装欄が現候補に完全一致。N4の新規1行はPO判定「一致」、旧362行の判定・理由は全件維持。
- ORM・凍結履歴・archiveの関連146件成功。RG1関連の使い捨てPostgreSQL 40件が一括成功。backend/rootのRuff・ty、backend format、認可catalog1417、function bodies、frozen-baselines、shared preconditions、tenant-boundary bypass、docs-status、`git diff --check`も成功。`backend/tests/conftest.py`の`origin/develop`との差分は0行。
- backend非DBは1925件成功・4件skip・DB必須647件除外。テスト失敗はないが、DB必須0件を拒むプラグインによる終了コード1を成功扱いにしない。ハーネス全件は専用一時領域・2ワーカーで**29,640件成功、2件skip、終了コード0**（25分57秒）。DB全件は別途実行中であり、この時点では完走と記録しない。
- DB全件の初回は152件成功後、合成SQL検査でfrontendの`typescript`が未導入のため`ERR_MODULE_NOT_FOUND`となり停止。RG1の検査失敗とは区別する。`frontend/pnpm-lock.yaml`固定の`pnpm install --frozen-lockfile`で既存ストアの312パッケージを導入した。lockfile・製品ソースの変更はない。
- DB全件の2回目は170件成功後、`test_game_type_seed_round_trip_under_product_rls`で0029へdowngradeした状態に現行HEADの全認可DDLを再適用し、未存在のRG1表へ触れたため停止。0029時点ではRG1表不在と試合区分表のFORCE RLS・seed専用policy継続を確認し、0030 seed投入後にHEADへ戻してから全認可DDLを再適用するよう試験だけを修正した。製品migration・認可資産は変更なし。修正差分のbinary SHA-256は`20ab9e14a0425c2e7be91260bafaf818f3163a69bd46c70f85e2537f6af52dd2`。単独試験は使い捨てDBで成功、Ruff・format・tyも成功。この後発の試験差分は既存独立レビューの対象外で、人間逐行確認対象に含める。
- DB全件の3回目は172件成功後、`test_all_manifest_immutability_declarations_are_enforced`が、RG1の`singleton_id`保護を既存の「全保護列はUPDATEトリガで強制」という一律前提で検査して失敗。RG1の実契約は、manifest宣言から導く`singleton_id`の定数CHECKと同列の主キーで値を固定する。限定候補では、**RG1の宣言から固定値と主キーを導出し、実DBのCHECK式と主キーが完全一致する場合だけ**その1列をトリガ検査から除く。CHECKを除去しIDを書き換える負例、宣言のprotected除去の負例は不合格へ戻る。他表のトリガ検査・N1〜N5変異検査は維持。DDL・manifest・凍結資産は変更せず、同ファイルの隔離DB3件成功、Ruff・ty成功。binary差分SHA-256は`28caf8384acbdec83201b119f9954a3b96dca67033d7ee333389bf93f98b4375`。#146前の後続診断は117件成功時点で意図的に中断し、最新基線の全件で確認する。この試験ロジックの追加は既存独立レビュー外で、本人逐行確認も未了。
- #146後のDB全件の前回実行は606件成功後、`test_force_rls_upgrade_preserves_catalog_and_states`が0029の状態に現行HEAD全カタログを要求して停止。0028/0029のFK形状・対象4表のFORCE状態と参照行保持をその版で確認し、HEAD復帰と全認可DDL再適用後に全製品カタログを確認するよう同ファイルの2試験を限定修正した。修正2件は隔離DBで成功、後続3ファイル22件も成功。binary差分SHA-256は`ac696e5dbab6f1f25edb26c0af33ade961fd3ae9231f302de78fdca6c9ca5593`。製品DDL・凍結資産は不変。これも既存独立レビュー外であり、未レビュー残余を明示する。
- 独立レビューの最終対象識別値はtracked diff SHA-256 `9fc870cf2159ad8de4d016ccb89472e791659df53e0f20d145f0fc6e7c526836`、P0/P1/P2=0。後発のRG1単一行限定テスト差分SHA-256 `91287790aae1dcb1f630a331d66694cd55366c7cf0082c02946090efbe83d31f`はPO採用済みだが未再レビュー。#145取り込みでは製品コード・認可許可の追加変更なし。本人逐行確認は未了。
- #146統合後の関連ハーネス176件（ORM・凍結履歴・archive・一時領域）とbackend一時領域配線1件は成功。backend非DB全件は**1926成功・4 skip・648 DB必須除外**で実テスト失敗0。DB必須0件を拒むプラグインによる終了コード1は維持。backend/root Ruff・ty、backend format、認可catalog1417、function bodies、frozen-baselines不変、tenant-boundary bypass、docs-statusは新基線で成功。専用使い捨てDBの最終候補では`tests/db`全630件が32分12秒で成功し、同ディレクトリ外の`requires_db`27件も79秒で成功した。単独再試験ではなく、それぞれ指定集合の一括実行である。
