---
feature: tenant-context-issuance-guard
type: research
date: 2026-10-05
---

# 調査メモ: TenantContext の発行を専用モジュールへ機械的に封じ込める(TSK-457)

## 問い

1. 本タスクの出所と、約束されている解の形は何か
2. 発行専用モジュールは「入口専用」でよいか。認証済みリクエスト以外に発行を要する経路があるか
3. 実行時 capability でどこまで閉じられるか。既存の保証宣言と矛盾しないか
4. 本タスクの射程は、他単位の射程・人間の裁定と衝突しないか
5. 検査器を変えるとき、凍結資産の費用はいくらか
6. 要件書のどの条文が本タスクを支え、何を制約するか

## 結論(要約)

- **発行モジュールは入口専用でよい。** 移行は専用ロール + `BYPASSRLS` で設計され、`set_config` 方式は却下済み(裁定 A-3)。CLI・運用スクリプト・スケジュールバッチは実体なし。テストは別枠(`allowed_test_modules`)で既に扱われている
- **「発行専用モジュール以外では発行できない」を無条件で名乗ることはできない。** 既存の正本級宣言が「証跡も検査器も**同一プロセス内の任意コードに対する信頼境界ではない**」と置いており、capability の効力をこれより強く書くと矛盾する。**保証単位を機構の境界そのものとして宣言し直す必要がある**
- **射程が人間の裁定と衝突している。** 裁定 b'(2026-10-05)は**検査器の改修**を U-M1 ステップ 8 へ移したが、本タスクの DoD は検査を含む。**計画承認の前に裁定が要る**
- **検査器を 1 バイト変えると凍結資産 8 本の識別値を繰り上げる**(記録は `base-allowlist.json` に 1 件)。配布モジュール 3 本も追随が要る。**1 PR に畳めば 1 回**
- 要件側は **NFR-010 / FR-034 が性質を Must で要求するが、手段は指定していない**。保証範囲の宣言を動かす正本は要件書ではなく `tenant-boundary-enforcement/design.md` 側

## 詳細と典拠

### 1. 本タスクの出所 — 代償ではなく「本来の解」

TSK-440 は条件 5 の保証範囲を縮小したが、**代償は付いていない**。
節題が逐語で「保証縮小に代償は付かない(2026-09-25・6.3-⑤ の敵対レビューで確定)」
(`docs/features/tenant-boundary-scope/plan.md:235`)、
「**代償なしの保証縮小であり、人間が残余リスクを明示的に受容する案件である**」(同 `:259-260`)。

当初案(コア paths へ `api/**`・`services/**` を足す)が承認不可になった **P0 の逐語**(同 `:243-245`):

> `api/**` と `services/**` は、構築可能性ではなく「置かれそうな場所」を選んだヒューリスティックである。
> 保証外にした `registry[k].make_context(t)` は**配置場所に制約がない**ため、
> 静的保証の縮小と釣り合う境界になっていない。

実測で否定された 3 点のうち 1 件は **存在しない例の捏造**(「`services/context_issuer.py` が該当する」— 引用先の行に無い)
(`docs/worklog/2026-09-24-tenant-boundary-scope.md:87-91`)。
**同じ形(ディレクトリ全体の追加)で再提案すると同じ P0 を食う。**

約束された解の逐語(`docs/features/tenant-boundary-scope/plan.md:267-275`):

> **必要なのは追加 glob ではなく、機構的な封じ込めである。**
> - 発行専用モジュール以外から有効な `TenantContext` を作れない実行時 capability
> - 発行モジュール外からの constructor / import / registry 登録を拒否する検査
> - その強制点・検査器・テストだけをコア paths に登録
>
> **DoD は「ファイルを移す」ではなく「そこ以外では有効なインスタンスを発行できない」まで含める。**
> **`TenantContext.__init__` が公開のままでは、合法な発行コードを移しただけでは閉じない。**

`design.md` 側にも申し送りがある — 「**本来の解(発行専用モジュールへの機械的封じ込め)は別タスクで起票する。**」
(`docs/features/tenant-boundary-enforcement/design.md:492`)。**本タスクがその別タスクである。**

### 2. 既存機構の実測 — 定義モジュールの暗黙の免除は無い

- 生成の可否を決めるゲートは **1 本だけ**: `self.module in allowed_modules`、
  `allowed_modules = allowed_test_modules | allowed_product_modules`
  (`scripts/check_tenant_boundary_bypass.py:4605-4607`。判定は `:4613` `:4627` `:4722` `:4946` `:4980` `:4996`)
- `constructor_symbol` の**定義モジュールを特別扱いする分岐は存在しない**。
  したがって発行関数を `context.py` の中に書いても `pitchlog.repositories.context` は両リストに無く TB007 で拒否される
- モジュール名は source root 相対のドット名(`_module_name:1417`)。
  `backend/src` 配下 → `pitchlog.repositories.context`、`backend/tests` 配下 → `test_authz_tenant_context`
- 製品側に `TenantContext(` の呼び出しは **0 件**(`grep`)。
  `backend/tests/test_check_tenant_boundary_bypass.py` の
  `test_tenant_repository_product_definition_passes_bypass_scan` が
  「現行の製品コードそのものが全行検査を通る」ことを assert している
- 0 件の機械強制(`scripts/check_tenant_boundary_bypass.py:1178-1181`):
  非空にすると `ContractError`。**資産の編集だけでは解除できず、検査器のコードを変えないと開かない**
- 配布側にも二重化されている(`backend/src/pitchlog/repositories/tenant_context_contract.py:26` が空タプル)

**帰結**: 発行専用モジュールが実際に構築する以上、
**新規モジュールでも `context.py` の中の関数でも、生成許可への登録が要る**。
「登録なしで成立する形」は存在しない。

### 3. 発行経路は「入口 1 本」でよい

| 経路 | 接続主体 | テナント文脈 | 典拠 |
| --- | --- | --- | --- |
| 移行バッチ | 専用ロール(`LOGIN` + `BYPASSRLS`・期間限定) | **不要** | `docs/design/data-model.md:279-281` `:223`(裁定 A-3・2026-09-08・山田正輝) |
| Alembic DDL | マイグレーション用ロール | 不要 | 同 `:218` `:325` |
| シード投入 | 同上 | 不要(語彙マスタはテナントに属さない) | 同 `:2014-2017` |
| authz 適用器 / probe | 管理 DSN | 不要 | `backend/src/pitchlog/authz/product_provisioning.py:63` `:68` |
| テストフィクスチャ | テスト用 DSN | 要るが**別枠で許可済み** | `backend/src/pitchlog/repositories/tenant_context_contract.py:25` |

決定打は**却下案の記録**(`docs/design/data-model.md:316`):

> **移行バッチもポリシーに従わせ、`set_config` でテナントを切り替えながら投入する**
> | テナント単位に投入が分断され、**ファンアウト(1 旧行 → 複数テナント行)の一括投入が組めない**。
> 移行の再実行の冪等性も担保しにくい

`TenantContext` は `set_config('app.tenant_id', …)` を発行するための値オブジェクトであり
(`backend/src/pitchlog/repositories/binding.py:70-73`)、その発行を却下した以上**移行は利用者ではない**。
移行ロールで接続するとアプリのエンジンを通れない(`backend/src/pitchlog/db/engine.py:143-146` が
`pitchlog_app` 以外を違反として扱う)。
移行は 1 バッチで複数テナントの行を作る(ファンアウト手順 — 同 `:1395-1403`)ため、
**仮に移行用の発行経路を設けても単一テナント文脈では用を成さない**。

- CLI は存在しない(`backend/pyproject.toml` に `[project.scripts]` 0 件)
- 運用スクリプトはカテゴリとしてしか現れない(`docs/design/data-model.md:2573`)。`docs/ops/` は不在
- スケジュールバッチも実体なし(同 `:2574` の 1 行のみ)

**計画書に書くべき申し送り**: 移行実装は `backend/` 配下に置かれる予定(`docs/adr/ADR-003-domain-calc-method.md:274`)で
静的検査の母集団に入る。**U-X5 着手時に「移行は発行モジュールの利用者ではない」と誤解されないよう明記する。**

### 4. 保証の上限 — 「実行時に発行できない」を無条件で名乗れない

既存の宣言(`docs/features/tenant-boundary-enforcement/design.md:83-90`。
同趣旨が `:489-490` にも独立して置かれ、`backend/src/pitchlog/repositories/context.py` の docstring はこの逐語):

> 同一プロセス内で導出経路へ到達できるコードは証跡を作り直せるため、この証跡は
> **同一プロセス内の攻撃者に対する信頼境界ではない**。導出経路への参照を拒否する静的検査も、
> 静的に到達を解決できる範囲だけを検出する。

6-0「守らないもの(明示)」も **同一プロセス内の攻撃者**を名指しで保証外に置いている(同 `:483-490`)。

**判定**: Python では同一プロセス内の任意コードが capability の秘密・導出経路へ到達できるため、
**capability を足してもこの宣言は撤回できない**。
カード DoD の「実行時に保証されている」を字義どおり読むと既存宣言と矛盾する。
**保証単位を機構の境界そのものとして書き直す必要がある**(例: 「発行モジュール外からの構築は、
通常の import・属性参照・registry 登録の経路では成功しない。同一プロセス内で
capability の導出経路へ到達する任意コードは保証外」)。

これはハーネス台帳が既に良形として記録している手当てと同じ —
「**散文で範囲を書かず、機構の境界をそのまま宣言にする**」(`docs/development/harness-evaluation.md:4060-4072`・7 例目)。
逆の失敗形も記録されている — 「『すべての抜け道』を条文の閉じた一覧で捉えようとすると、
敵対レビューが 1 周に 1 件ずつ出し続けて終わらない」(同 `:4014`。U-T1 テナント境界が 4 例目で、
**有効だった手当てが「脅威モデルを設計書へ明文化して線を引いた」**こと — 同 `:4040-4054`)。

**先例(本タスクが同じ場所を通る)**: TSK-444 の敵対レビュー `P0-3` は、
新しい入口 `tenant_transaction_scope` が型検査を `isinstance`(派生を許す)で行い
**発行証跡の検査を持っていなかった**ことを指摘した。是正は
「**既存の防御を弱めるのではなく、新しい入口を既存と同じ強さに揃えた**」
(`docs/worklog/2026-09-26-tenant-session-supply.md:353-358` `:370` `:378-379`)。
**新しい発行専用モジュールを足す本タスクは、同じ P0 を食う位置にいる。**

### 5. 射程の衝突 — 人間の裁定と DoD が同じ対象を別の単位へ割り当てている

**U-T1 の規則**(`docs/features/tenant-boundary-enforcement/design.md:60`):

> allowlist の初期値は「認証を実装する単位(**U-A1** / **TSK-217**)が入るまで、テスト専用の構築経路のみ」。
> **製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる**

同じ条件が計画書の合格条件にもある(`docs/features/tenant-boundary-enforcement/plan.md:172`
「allowlist に製品モジュールが 0 件(U-A1 / TSK-217 待ち)」)。

**人間の裁定 b'**(2026-10-05・山田正輝。`docs/features/ua1-auth-app-layer/plan.md:34-35` 逐語):

> **裁定(b')**: **`allowed_product_modules` への登録・`TenantContext` の生成箇所・7.7 の受理記録・
> 検査器の改修を、最初の入口を開く U-M1 のステップ 8 へ移す。** **本単位は署名と検証までを持つ。**

同計画書は同時に、本タスクを
「**`TenantContext` の発行の実行時封じ込め**(公開 constructor の閉塞)= TSK-457。**最初の入口の前に要る**」
と申し送り表に置いている(同 `:76`)。

**衝突点**: 本タスクの DoD は「発行モジュール外からの構築・import・registry 登録を**検査が拒否**する」を含み、
これは**検査器の改修**である。裁定 b' はそれを U-M1 ステップ 8 へ移している。
**カード DoD と裁定 b' が同じ対象を別の単位へ割り当てている。**

**裁定(本調査での判断)**: `docs/features/ua1-team-auth/design.md:264` と `docs/features/ua1-team-auth/plan.md:110`、
`docs/design/data-model.md:16` は、いまも `TenantContext` の生成を **γ(TSK-469)の射程**と書いている。
これらは裁定 b'(2026-10-05)より前の記述であり、**b' が新しく、かつ人間の裁定であるため b' を採る**。
3 箇所の現行化は本タスクの射程外 — **申し送り**。

### 6. 凍結資産の費用

- 資産集合は **9 本**(`scripts/check_tenant_boundary_bypass.py:69-79` の `FROZEN_BASELINE_ASSETS`)
- うち **8 本**が `frozen_projection.external_files` に `scripts/check_tenant_boundary_bypass.py` を含む。
  含まないのは `frozen-inputs.json` のみ
- **検査器を 1 バイト変えると 8 本の識別値(`contract_revision`)を繰り上げる必要がある。**
  機械強制は `scripts/frozen_history.py:1474-1482`
  (`射影が動いた資産は識別値の更新が必要: {asset_name}`)。**判断の余地はない**
- **記録は `base-allowlist.json` に 1 件追記**(`history_authority: true` を持つのは同資産のみ。
  `tenant-context-allowlist.json:44` は `false`)。
  記録には 9 資産すべてを `previous_/new_baseline_identifiers` に列挙する(動かない 1 本も同値で書く)
- 規範は ハーネス設計書 7.7-2(`docs/development/dev-harness-design-2026-08-07.md:584-608`)

**前例**(`contracts/tenant_boundary/base-allowlist.json` の history):

| PR | 内容 | 動いた資産 |
| --- | --- | --- |
| #80(TSK-440) | 条件 5 の保証単位・条件 2 の裁定 | **7 本すべて +1** |
| #74 | ドメイン計算 DSL の検査基盤 | **8 本 +1**(frozen-inputs が新規加入) |
| #83(TSK-448) | 履歴 snapshot の参照・量 | **8 本すべて +1** |
| #87 / #96 | 資産の中身だけを変えた受理 | **1 本のみ** |

読み取れる規則: `aspect` に `external_snapshots` が入る受理 = 外部凍結対象を触った受理 = **全資産が動く**。

**TSK-440 が踏んだ罠**(`docs/worklog/2026-09-24-tenant-boundary-scope.md:900-918`):

> **こちらの指示「他 5 資産の識別値を変えない」は誤りだった。検査器が 7 資産共通の `external_files` にある以上、
> 7 資産すべての射影が動くので、識別値も 7 資産すべてを上げる必要がある。**

同 worklog が残した手続き上の注意:

- `change.after` は revision を上げた**後**の射影で算出する(revision 欄自身が射影に含まれる)。
  `change.before` は **merge-base 側**の射影であって作業ツリーの更新前値ではない(`:159-171`)
- **承認が先** — 「逐行確認 → 承認 → 記録を書く → CI → マージ」。
  予約 marker(`未承認` `PENDING` `TODO` `TBD` `未定` `レビュー待ち`)は拒否される(`:787-792`)
- 凍結 SHA は**変異テストが走っていない状態で読む**(走行中は偽の不一致 — `:560-569`)
- **配布モジュール 3 本が取り残される**: 識別値を上げると
  `backend/src/pitchlog/repositories/{tenant_context_contract,repository_contract,runtime_contract}.py`
  の revision も追随が要る。**TSK-440 では CI で初めて露見した**(`:953-968`)

### 7. 要件側の根拠 — 性質は Must・手段は射程外

- **NFR-010 チーム間データ分離**(Must)。「他チームのデータ資源は**内容・存在を含め参照できない**」
  「**テナント分離は初日から全機能に適用する**」。測定方法 = 越境アクセスの自動テスト(CI 常設)。
  典拠 `docs/requirements/requirements-pitchlog-2026-07-22.md:846-850`
- **FR-034 データ所有権制御**(Must)。既定拒否 + 許可リスト・単一名指しは 404。同 `:599-645`
- **NFR-010 はどの実装単位にも属さない横断要求**で、
  「各単位の DoD へ『この横断要求を破っていない』を入れる(満たすのではなく破らない)」
  (`docs/features/product-impl-unit-split/design.md:116` `:120-121`)
- **衝突なし**: NFR-018(対象は状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定 — 同 `:892`)、
  NFR-005(対象は集計 — 同 `:816-818`)はいずれも本タスクの対象外
- **制約するのは NFR-019 のみ**: バックエンドのテストは pytest に集約(同 `:925`)、
  越境テストは「経路が実装され外から到達できるようになった時点で発効」だが
  **未発効は網羅の免除ではない**(同 `:933`)
- **「同一プロセス内の攻撃者」「脅威モデル」「信頼境界」は要件書に 0 件**。
  宣言の出所は feature 設計書(`tenant-boundary-enforcement/design.md` 1-1・6-0)であり、
  **保証範囲の宣言を動かすなら正本は要件書ではなく当該 design.md 側**
- **7.1 の制約**「サーバーはステートレス(プロセス内に試合状態を持たない)。
  レート制限カウンタ等の横断状態もプロセス外に置く」(同 `:1016`)。
  現行実装はプロセスローカルな秘密を持つ(`backend/src/pitchlog/repositories/context.py:9`)。
  条文が名指しするのは試合状態と横断状態だけなので**現状は矛盾しない**が、
  **capability の秘密をプロセス外へ出す設計を採ると、この条文の射程に入る**
- **2.2 Won't「個人アカウント・入力者の識別」**(同 `:97`)。
  発行モジュールが「誰が発行したか」を**主体単位**で持つ設計に寄ると Won't に当たる。
  テナント単位に留まる限り衝突しない

### 8. ADR の有無

`docs/adr/` は 4 本(ADR-001〜004)で、`TenantContext` / テナント文脈 / 信頼境界 / 真正性 で**ヒット 0 件**。
当該決定は ADR ではなく feature 設計書 + 計画書 + worklog に載っている。
U-T1 は「`docs/adr/` 新設なし。**既決の制約の適用であり新しい決定を持たない**」と宣言した
(`docs/features/tenant-boundary-enforcement/plan.md:127`)が、
**本タスクは新しい機構を持ち込むので同じ理由は使えない**。ADR 新設の要否は計画で判断する。

## 未解決・申し送り

### 計画承認の前に人間の裁定が要るもの

1. **検査器の改修を本タスクが行ってよいか。** 裁定 b' は検査器の改修を U-M1 ステップ 8 へ移したが、
   本タスクの DoD は検査を含む(§5)。**どちらの単位が検査器を触るかの裁定が要る**
2. **発行専用モジュールが、入口が開く前に生成許可を得てよいか。**
   U-T1 は「製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる」と定める(§5)。
   発行モジュールは製品コードであり、構築する以上どこかに登録が要る(§2)。
   **「機構は入口より先に要る」(TSK-440 の申し送り)と「入口の前に製品モジュールを入れない」(U-T1)が
   正面から当たっている**

### 本タスクの射程外(別の担当へ)

3. `docs/features/ua1-team-auth/design.md:264`・同 `plan.md:110`・`docs/design/data-model.md:16` が
   `TenantContext` の生成を γ(TSK-469)の射程と書いたままになっている。裁定 b' で U-M1 ステップ 8 へ移った
4. 移行バッチの監査ログの書き先(`admin_operation_logs`)が
   `contracts/authz/product/migration-batch-role.json` の `write_targets` に入っていない。
   裁定 A-3 は「このロールでの接続と一括投入を操作ログに残す」と定めている(`docs/design/data-model.md:307`)。
   `write_targets` は「`import_batch_id` を持つ表 + `migration_runs`」の機械導出なので
   (`backend/src/pitchlog/authz/product_catalog.py:791`)落ちるのは導出規則の帰結。
   **TSK-349(移行バッチ用ロールのライフサイクル)の担当へ**

### 典拠が取れなかったもの

5. **6.3-⑤ 敵対レビューの `P1`×4 の個別内容**。件数のみ記録されている
   (`docs/features/tenant-boundary-scope/plan.md:239`)。逐語を持つ文書はリポジトリ内に無い
6. **`tenant-context-allowlist.json` の各欄が U-T1 の何周目で追加されたか**。
   資産の history は PR #72 の 1 件のみで、内容復元可能な snapshot は TSK-431(PR #78)以降しか無い
