# U-R1 新ステップ 2: RG1 物理・認可・凍結資産の候補差分

2026-10-14。**別承認前の候補。資産そのものは未変更**。調査時の比較元は `origin/develop` `e6e1a867`、repository-contract revision 16、base-allowlist revision 28。U-S1 の直列化点は依頼者転送の回答で条件付き受理され、Port の分離は担当確認待ち。#132 や TSK-550 の共有実行器が先行すれば識別値・digest を再計算する。以下の表名・列名・関数名は候補であり、PO の方式承認を個別の DDL・認可・凍結資産承認へ読み替えない。**2026-10-15 の[共有実行器追補案](shared-function-executor-addendum-proposal.md)と[認可審査資料](rg1-authz-review-packet.md)が後発の正**であり、前半の `authz_private` 配置案・revision 16→17 / 28→29 は採用しない旧試算である。

**2026-10-15の状態訂正**: 本書の「Port担当回答待ち」は作成時点の記録。U-S1コミット済み計画8節・作業ログで2署名、呼出位置、同一transactionの固定`run_function`口を条件付き受理済みと確認した。現在の残条件は[接続契約](connection-contract.md)と[作業ログ](../../worklog/2026-10-15-ur1-recording-rights.md)を正とし、TSK-550共有実行器Aの統合とRG1個別資産承認に絞る。

## DDL と操作境界の候補

| 資産 | before → after 候補 | 制限 |
| --- | --- | --- |
| 次の製品 migration と `db/recording_rights/models.py` | RG1 行なし → `public.rg1_restore_gate` を追加。`singleton_id smallint PRIMARY KEY CHECK(singleton_id = 1)`、`state text NOT NULL CHECK(state IN ('closed','open'))`、既定値と migration seed は `closed`、1 行だけ。`ENABLE ROW LEVEL SECURITY` と `FORCE ROW LEVEL SECURITY`。アプリ用ロールには表の直接 `SELECT/INSERT/UPDATE/DELETE` を付与しない | migration/復元経路以外から行数と識別値を変えない。欠損・複数行・未知状態は拒否。物理削除なし |
| 制限関数 | `authz_private.rg1_read_open()` と `authz_private.rg1_assert_open_before_commit()` を候補とする。前者は同じ行を非ロック読取、後者は**関数内で** `FOR SHARE` を取得し、呼出 transaction の終了まで保持。両方とも固定の singleton だけを読み、状態の真偽以外の業務行を返さない。`pitchlog_app` にこの 2 関数の `EXECUTE` のみ付与 | `SECURITY DEFINER` の固定 `search_path`、PUBLIC の既定 `EXECUTE` 剥奪、引数による表/行/SQL の選択なし。テナントの直接 token 実行でも `open` を偽装できないよう、起動時閉鎖の判定は operation の内側で毎回行う。SQLAlchemy の汎用 `lock.read` を広げない |
| 復元開始側 | `authz_private.rg1_begin_restore()` を候補とし、同じ行だけを `closed` に `UPDATE` する。新 2 では通常アプリロールへ `EXECUTE` を付与せず、既存の所有者/復元運用経路からの実行と DB 競合試験に限定。ゲーム・世代行は同 transaction でロックしない | 製品の管理 HTTP 入口や `open`/解除関数を作らない。将来の管理入口の主体認証と実行権は新 5 で別途確定 |
| 起動・再接続ゲート | 新 2 の製品 operation はプロセス開始・再接続後とも開放許可を**常に閉**とし、DB の `open` だけから成功へ遷移しない。新 2 に開放操作を置かず、DB 関数単体の `open`/競合は隔離 DB/試験専用の明示状態で検証する | 復元された古い `open` 行、DB 欠損/読取失敗、接続断のいずれからも自動開放しない。将来のプロセス間解除・復元証明は新 5 の別ゲート。新 2 単独では本番通常書込みは停止 |

## 変更対象の資産と承認単位

| 群 | 候補となる具体差分 |
| --- | --- |
| 正本・分類 | `docs/design/data-model.md` に非テナントかつ更新を制限関数へ閉じる RG1 制御行の事実を追加する必要がある。`contracts/authz/product/exposure-facts.json` にその典拠を持つ行、`table-classification.json` に `function_only` と U-R1 所有を追加する。現行の `classification.py` は `non_tenant` を例外なく `global_read_only` へ強制し、`FUNCTION_OWNER_UNITS` に U-R1 がない。**RG1 の単一行だけ**に限定して、非テナントかつ制限関数専用の分類を表現できる検査変更が必要。7.6 の正本改訂ゲートを省略しない |
| 製品認可 | `contracts/authz/product/ddl-elements.json` と対応する `function-bodies/` に新表・制限関数・所有/ACL・FORCE RLS の宣言を追加。`schema-manifest.json`、`runtime-authz-contract.json`、生成 `backend/src/pitchlog/authz/runtime_contract.py` と認可カタログ/検査を同じ候補へ追随。既存ロールの権限を広げるのではなく、関数所有と最小の表権限を固定する。管理関数の `EXECUTE` は `pitchlog_app` に追加しない |
| repository 凍結 | `contracts/tenant_boundary/repository-contract.json` に `read_rg1_open` と `assert_rg1_open_before_commit` の閉じた operation token 型だけを追加する。候補シンボルは `pitchlog.repositories.rg1._build_rg1_read_statement`（`SQLA_SELECT` のみ）。復元開始の閉鎖関数は通常テナント repository の token/SQLA_UPDATE 許可に含めない。`base-allowlist.json` にはその**正確なシンボルと SELECT のみ**を追加し、他の許可や未定義 kind は変えない。**現行 repository は全 operation に tenant-owned 表・capability を要求し、SQL 形検査は `pg_catalog` 外の関数を拒否するため、制限関数呼出しの RG1 専用例外とその負例試験が必要**。比較元が不変なら候補 revision は repository 16→17、base 28→29。#132 等が先に統合した場合は before と revision を取り直す |
| 履歴・派生・試験 | 同一 PR の単一未マージ 7.7 受理記録の after 側・snapshot・archive を実際の候補 SHA/digest へ追随し、before 側と受理済み履歴を維持する。schema/認可/凍結資産から導出する lock/census/oracle が動く場合だけその差分を列挙し、必要な再封印・人間確認を別に行う。内部 token 直実行、通常テナントの更新拒否、欠損/不明/読取失敗、復元先行と通常側先行、再接続での閉鎖、全取消を DB/認可試験に含める |

**未確定**: 制限関数所有ロールの最小 ACL、`function_only` の非テナント例外と制限関数呼出しの RG1 専用登録を既存検査へどう組み込むか、復元開始用関数を実運用で誰が呼ぶか、起動時確認のプロセス間・再接続時の実装方法。これらは候補をコード化する前に詰め、具体的な before/after の JSON・SQL・revision/digest を固定して、独立レビューと個別の人間承認へ出す。現時点で「資産差分承認済み」や「U-S1 Port 接合済み」としない。

### 凍結資産の識別値候補（現行基線が動かない場合）

```text
repository-contract.json: contract_revision 16 → 17
  product_operation_token_types += pitchlog.repositories.rg1.RG1ReadToken
  product_operation_token_types += pitchlog.repositories.rg1.RG1CommitCheckToken
  product_capability_ids: RG1 表の直接 read/update 能力は追加しない
base-allowlist.json: contract_revision 28 → 29
  allowed symbol += pitchlog.repositories.rg1._build_rg1_read_statement
  allowed_api_ids = [SQLA_SELECT]
  SQLA_UPDATE / SQLA_INSERT / 未知 kind は不許可
```

これは**識別値と追加集合の候補**であり、SHA/digest・履歴 after は実差分固定後に算出する。既存の受理済み行、PR #72 の `PENDING_ACCEPTANCE`、新 PR の before 側は変更しない。

## 2026-10-14: 固定関数実行器との統合差分（承認候補、資産未変更）

TSK-550 の受理シート（`feature/ux1-fr014-rule-resolution` の `step1-contract-acceptance.md` §「固定function operationの最終契約案」）は、既存表 DML の `OperationRegistration` / `run` を緩めず、別の `FunctionOperationRegistration` / 同一 scope の `run_function` を設ける契約として PO 代替受理済み。ただし**実装・具体資産変更は未承認**で、TSK-550 ステップ 4 の予定である。上記の「RG1専用例外」を基底にもう一つ作ると実行器が重複するため、以下に絞る。

| 所有・順序 | 具体範囲 | ゲート |
| --- | --- | --- |
| TSK-550 側の先行小単位（担当へ受理依頼中） | `FunctionOperationRegistration`、`_TenantTransaction.run_function`、DML と関数の登録 ID/型重複拒否、固定 SQL 構造・bind/戻りの検査、偽造 token/失効 scope/任意 SQL/Session 拒否の共通部分だけ。段階 A の規則関数は含めない | TSK-550 承認済みステップ順の追補と、共通実行器に対応する正本・認可・凍結 7.7 の個別承認が必要。実装担当は TSK-550 側。TSK-550 全体の完成は待たない |
| U-R1 新ステップ 2 | 上記統合済み基線を使い、**RG1 2 関数だけ**を固定登録。`RG1PrecheckToken` と `RG1CommitCheckToken`（いずれも frozen/slots、業務引数なし、tenant/context/SQL/function 名/decoder の caller 注入なし）を exact 型で登録。RG1 operation と関数の単体・DB競合試験、DDL/ACL、RG1 用拒否試験まで。**U-S1 の PortWriter 変更と実入口接合は承認済み計画の新ステップ 6** | U-S1 Port 署名・呼出位置の受理と U-R1 個別の正本 7.6、認可/凍結 7.7、人間承認。TSK-550 の規則 resolver・D4 発行は含めない |

**候補となる登録と SQL**: `FunctionOperationRegistration` の ID は `RG1:precheck` / `RG1:commit_check` の 2 件、固定関数 identity は `authz_private.rg1_read_open()` / `authz_private.rg1_assert_open_before_commit()` の 2 件とする。前者の SQL は `SELECT authz_private.rg1_read_open() AS is_open`、後者は `SELECT authz_private.rg1_assert_open_before_commit() AS is_open` のみ。両者の bind 集合は空、戻りは **1 行・`is_open` exact bool**。0 行・複数行・NULL・型違い・未知状態・DB 例外は失敗で scope を全取消。`false` は復元調整中として B7（終了後 P3 は B10）へ写す。DB 関数内部で RG1 行が 1 行のみ存在することを確認し、後者はその同じ行を `FOR SHARE` でロックして transaction 終了まで保持する。関数名、SQL、bind、戻り decoder は登録時固定で token から受け取らない。`game_id`/`tenant_id` 引数は持たず、tenant context の実在性は共通実行器が直前に再検証する。**関数の直接 EXECUTE は実行器を通らないため**、両 DB 関数自身でも tenant GUC の欠損/不正を拒否する候補とし、直呼出しによるロック待機の影響を認可審査へ出す。復元開始の UPDATE 関数はこの登録集合にもアプリ用ロールの EXECUTE にも含めない。

**凍結契約の追加集合**: 共通実行器の公開面 (`run_function`、登録型、検査器、実行器の `SQLA_SESSION_EXECUTE`) は TSK-550 の別受理単位で先に確定する。U-R1 がその後追加するのは `repository-contract.json` の `product_operation_token_types` に上記 exact 2 型、固定登録 ID に 2 件、`base-allowlist.json` の `pitchlog.repositories.rg1._build_rg1_read_statement` 1 シンボル（`_build_rg1_read_statement(kind: Literal["precheck", "commit_check"]) -> Select`、`SQLA_SELECT` **だけ**、`fixture=tests/fixtures/tenant_boundary/positive/pitchlog/repositories/rg1.py` 候補）に限る。現行 JSON には固定関数 ID 宣言欄がないため、その欄を設ける共有契約は TSK-550 の受理対象とし、U-R1 が独自の並行欄を足さない。RG1 用 migration・分類・runtime authz・DDL/function body・派生 lock/oracle は U-R1 の個別差分として固定する。**revision 16→17 / 28→29 は共通実行器が先行した場合の実値ではない**ので撤回し、統合時の比較元から採番/digest/7.7 before・after を再計算する。既存履歴は改変しない。fixture を含む実 JSON/SQL/派生資産と 7.7 の before/after はこの時点で未確定なので、これをもって個別承認は求めない。

**残る担当回答**: U-S1 は③-a/⑧の Port 署名、PortWriter 発行位置、通常同期・終了後 P3・内部配信の正確な呼出位置を回答する。さらに現行 `PortWriter.run` は既存 DML の `_TenantTransaction.run` へだけ接続するため、**同一 scope の `run_function` へ exact token だけを渡す閉じた口**と失効条件を U-S1 所有の PortWriter に追加するか、安全な代案を受理する必要がある（Notion `3f993b75-e687-81d8-ae7c-001d2afae493`）。TSK-550 は共通実行器の先行小単位の所有・追補・統合順を回答する。認可面所有者は RG1 関数 owner の最小権限、`FORCE RLS` 下の実行、PUBLIC 剥奪、アプリの 2 関数限定 EXECUTE、復元側 UPDATE 関数の運用ロールを審査する。回答がない部分を受理済み・承認済みとは扱わない。

**独立敵対査読と採否**: 固定 SHA256 `a5f827385fe1d93f18940a47a02e6165e3210927a44c6c911f94f681350b1728` に対する別 Codex セッションの読取専用査読は P0=0、P1=7、P2=1。査読中の PortWriter 追記で文書 SHA は `bbbc0912f2a44a3b9a0c69fa551aec818a78e52fc29b7f14b1d2f34edc14901b` へ変わったため、同追記は固定候補の正式査読済み部分とは扱わない。指摘は全件採用し、次の承認前条件へ移した。

| 指摘 | 採用した最小反映・残る根拠 |
| --- | --- |
| P1-1 `FORCE RLS` と関数 owner | 読取・閉鎖それぞれの owner/表 ACL/RLS 適用・EXECUTE を SQL と実 DB 負例で固定するまで個別認可承認不可 |
| P1-2 非テナント `function_only` | `non_tenant` 例外だけでなく特別露出事実と U-R1 owner の閉じた分類条件・負例を正本 7.6 から確定する |
| P1-3 Port 接合のステップ越境 | 新2は operation/DB 試験に限定し、PortWriter 変更と実入口接合は新6へ戻した。署名・位置の事前合意だけを新2着手条件にする |
| P1-4 TSK-550 先行単位 | 提案は未受理。TSK-550 側の正式追補・個別凍結受理・統合基線が揃うまで U-R1 の実 revision/digest を確定しない |
| P1-5 アプリロールの関数直接呼出し | `run_function` の context 検査だけでは DB 直呼出しを防げない。関数内で欠損/不正 tenant GUC を拒否し、直接呼出しが共有ロックで復元を待たせ得る境界を認可レビューと負例へ明示する。「同一 scope からしか実行できない」とは主張しない |
| P1-6 起動時 fail-closed | 新2ではプロセス/接続の開放許可を**常に閉**に固定し、DB に古い `open` があっても operation 成功へ遷移しない。復元 snapshot・再起動・再接続の拒否を試験する。安全な open と D4 開始の不可分性は新5の別ゲート |
| P1-7 7.7 実差分 | 許可行の fixture を候補へ追加。共有実行器統合後の full JSON/SQL/生成物・識別値・digest・before/after が未確定なので、人間の個別承認へ進めない |
| P2-1 待機の追越し | 三接続の UPDATE 待機・後続共有ロック・timeout/全取消を実 DB 試験へ追加し、追越しを事実として先取りしない |

**現時点の承認判断**: RG1 物理方式の既承認は有効。U-S1/TSK-550/認可面の回答と TSK-550 先行統合後の exact 資産差分がまだないため、新ステップ2の個別 DDL・認可・凍結承認は**提示待ち**。本資料の候補 ID/関数名/fixture を承認済み識別値として使わない。

## preparing 作成だけの早期解除を分けられるか

`preparing` 作成は D4 を発行しない。一方、[sync-protocol 9-5](../../design/sync-protocol.md)は**試合作成を含む全通常書込み**を RG1 中に止め、**解除と非再利用の新 D4(D3=0)開始を不可分**にする。したがって RG1 行が古い snapshot の `open` に戻った場合、DB 内の状態や「その試合はまだ D4 がない」という事実だけでは復元完了と全旧 D4 の失効を証明できない。安全な解除を新 5 の D4 確定・回収/退避/確認に結ぶ理由はこの終端条件にある。

preparing だけを先に開けるなら、正本上の新しい例外状態と、既発行 D4 を含む復元履歴から独立した安全証明、全通常経路がその例外を誤用しない認可/試験、復元中に新規試合が回収/退避対象を乱さない条件が必要。現在その契約と証明源はない。**分離は現行正本のままでは不可**と判定し、未承認の外部台帳や自動 open を採用しない。新 2 の正常系は隔離試験で検証し、本番の U-G1 作成成功は安全な解除が承認・実装されるまで未達とする。
