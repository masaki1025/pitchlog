# 共有固定関数実行器Aの凍結資産ゲート案（未承認）

2026-10-15。基線は`origin/develop` `e6e1a867`。本書は変更前後の対象・検査を固定する審査資料であり、資産や製品コードを変更しない。実際のrevision・digest・7.7受理記録は、個別承認された実差分の最終headで確定する。Aの製品登録は0件で、B/Cの関数identity・権限は本ゲートへ含めない。

## 変更対象とbefore→after

| 対象 | 現状 | Aで必要な差分 |
| --- | --- | --- |
| `contracts/tenant_boundary/repository-contract.json`（revision 16） | `public_surface`にDML `transaction_scope_entry`だけ、製品token型はDML集合。固定関数登録ID欄なし | `public_surface.function_registration_type = "pitchlog.repositories.function_operations.FunctionOperationRegistration"`、`function_transaction_entry = "pitchlog.repositories.transaction._TenantTransaction.run_function"`、`function_operation_registry = "pitchlog.repositories.operation_registry.PRODUCT_FUNCTION_OPERATIONS"`を追加。`function_executor.signature = "run_function(self, operation: TenantOperationToken) -> TenantOperationResult"`、`product_function_operation_ids = []`を新設する。Aの実行時registryとID集合はexactな空集合で一致させる。製品token型・capability IDの既存集合は不変。生成`backend/src/pitchlog/repositories/repository_contract.py`とschema/検査を追随 |
| `contracts/tenant_boundary/base-allowlist.json`（revision 28） | `SQLA_SESSION_EXECUTE`はbinding・基底実行器・`_TenantTransaction.run`の既存3行で許可 | `_TenantTransaction.run_function`に`SQLA_SESSION_EXECUTE`だけの**第4行**を追加し、signatureは上記と一致させる。既存3行のsymbol/signature/API集合は不変。`SQLA_TEXT`、任意SQL builder、Session公開を許可しない。positive fixtureは同じsignatureだけを追加 |
| `scripts/check_tenant_boundary_bypass.py`と対応試験 | 固定関数用の登録・実行境界を検査しない | 新公開面・空の固定関数ID集合と実行器が宣言に一致することを検査し、宣言欠損・未知token/ID・許可外`Session.execute`を不合格にする。製品registryの`PRODUCT_FUNCTION_OPERATIONS`と資産のID集合のexact-set照合、登録型/ID/固定文/decoderの起動時検査を強制する。基準の実値は資産側に置き、検査器へ複製しない |
| `contracts/tenant_boundary/runtime-authz-contract.json`と生成物 | アプリロール・DB保護対象を凍結（runtime revision 13） | DB関数・owner・ACL集合は不変。ただし共通迂回検査器が凍結射影の`external_files`に入るため、revision **13→14候補**・digest・履歴・snapshotを変更し、生成`backend/src/pitchlog/authz/runtime_contract.py`を同期する。集合不変を資産差分0と扱わない |
| `contracts/authz/product/capability-catalog.json`と派生資産 | 既存DML capabilityだけ | Aの製品関数登録0件のため新capabilityは**0件**。Aに実capabilityを足さず、B/Cの個別ゲートで固定関数と対応づける |
| `contracts/tenant_boundary/{negative-fixtures.json,cache-invalidation-contract.json,census-baseline.json,db-api-inventory.json,tenant-context-allowlist.json}` | 共通迂回検査器を凍結射影の外部ファイルに含む。現行識別値は順に14/12/11/12/13 | 検査器変更の`pass_fail_mapping`移動として候補識別値を順に**15/13/12/13/14**へ改訂し、各before/after射影・履歴・snapshotを追随。新しい負例ファイルを追加する場合は`negative-fixtures.json`の行とexact-set検査も更新。非対象資産`frozen-inputs.json`は検査器を外部対象に含まないため本理由では不変 |
| `contracts/tenant_boundary/history-snapshots/**`、`base-allowlist.json`の履歴authority、`tests/fixtures/frozen-archive-cases/manifest.json` | 上記8資産の現行基準と比較corpus digest | 8資産それぞれのbefore/after射影・snapshotを示し、既存履歴を維持して単一A受理に対する識別値・理由・承認者/日付をallowlistの受理記録へ追記。比較corpusは検査器・`contracts/tenant_boundary`・fixture入力が動くため`corpus_inputs.digest`を再pinし、既存`pinned_prefixes`と11ケースの期待結果を保持する。変える必要が実測で判明した場合は別差分として審査。中間コミットや未承認値を受理済みとしない |

## 適用・試験境界

先にAの計画を人間承認し、この具体資産差分を所有担当・7.7審査へ出す。個別承認後の同じPRでコードと資産を変更し、rootの迂回検査・凍結基線・履歴・比較corpus、backendのRuff/ty/pytest、core-guardの既存glob検出を最終headで確認する。資産を変えずに新`Session.execute`だけを入れた中間headはroot迂回検査が失敗するため、合格・公開対象にしない。

`FunctionOperationRegistration`はfrozen/slotsで、`token_type: type[TenantOperationToken]`、固定`capability_id: str`、固定`function_id: str`、構造検査済み`statement: Select[Any]`、`input_fields: tuple[tuple[str, type], ...]`、固定結果列とdecoderを保持する案とする。callerへ登録API・SQL・Session・関数identity・tenant IDを渡す引数を公開しない。登録時はschema修飾された単一関数呼出しとexact bind集合/型・戻り列を検査し、実行直前にexact token型・capability ID・全入力を再検査する。製品registryはコード固定`PRODUCT_FUNCTION_OPERATIONS = ()`で、製品ID集合は資産の`[]`と完全一致する。試験では**同じ`run_function`入口**から実行・decoder・例外時全取消まで通すため、テストプロセス内だけで私有registryを`monkeypatch`し、終了時に必ず空へ復元する。試験用登録を製品registry・凍結契約へ混ぜない。DB直接関数EXECUTEの可否はB/Cの認可ゲートで別途判定する。

**個別判断**: repositoryの新公開面・空固定ID欄、allowlistの`run_function`第4行、8資産の識別値移動と検査器/fixture/生成物・7.7前後状態、比較corpus再pinをAとして受理するか。上のrevisionは`e6e1a867`基線からの**候補**であり、統合基線が変われば再計算する。digestは実差分の最終候補で照合し、値の先取りをしない。TSK-550のステップ3正本やB/C関数権限をこの判断に抱き合わせない。

**予備敵対レビュー第1回と採否**: P0=1/P1=2/P2=1で否決、全4件採用。P0は共通迂回検査器の変更が8資産の凍結射影を動かすのにruntime-authz等を差分0としたこと。P1は公開型/固定ID欄/製品空registry一致と試験注入境界の不足、負例fixtureと既存3件の`SQLA_SESSION_EXECUTE`許可行の見落とし。P2は比較corpusの`pinned_prefixes`と11ケース維持の未記載。上表と適用境界にすべて反映した。これは7.7の個別受理や資産変更承認ではない。
