---
feature: product-authz-apply
type: design
date: 2026-09-25
---

# 詳細設計: 製品 authz の適用器・実 DB 試験(TSK-424 PR A2)— A1 からの差分

**設計の正は A1 の [design.md](../product-authz-surface/design.md)** である(2-0〜2-3 ロール・4 節 適用経路・6 節 実 DB 試験・7 節 写像・8 節 移行バッチ用ロール)。本書は A2 で**新しく決めること**と、**A1 の実装で変わった事実の読み替え**だけを書く。A1 の本文を書き写さない。調査の典拠は [research.md](./research.md)。

## 0. A1 の設計の読み替え(A1 の実装で変わった事実)

| A1 design / 旧ステップ | 読み替え | 典拠 |
| --- | --- | --- |
| 4-2 手順 7「トリガ関数 33 個」・旧 14「33 個が `SECURITY INVOKER`」・旧 19 | **37 個**(migration 0015・0016・0017・0024 の 4 個を含む) | research.md 4 |
| 1-5 秘密の列 | **3 件**(`tenant_credentials.password_hash`・`admin_credentials.password_hash`・`group_invitations.code_hash`) | 同上 |
| 10 節 capability の登録の検査 | 保証範囲の宣言(10 節末尾)に従う。A2 は登録の検査に触れない | A1 design 10 節 |

## 1. DB 呼び出しの置き場 — 末端 2 関数に集め、実行できるものを閉じる

迂回検査は、`backend/src` の新しい DB 呼び出しを、所属関数の完全修飾名とシグネチャの完全一致で `allowed_symbols` に照らす。記号 1 件ごとに正例 fixture が 1 件要り、既存の DB 呼び出しの行を変えるとその行も「増えた違反」になる(research.md 2)。

→ **製品の DB 呼び出しは、新設モジュールの末端関数 2 つだけに置く**。ただし**末端関数は任意の SQL を受け取らない**(計画レビュー 1 周目 P0 — 任意の文を受け取る実行器を許すと、呼び出し側に DB API が現れないまま DB へ届く経路になり、迂回検査の「DB に届く API は許可された基底シンボルの内側だけ」という目的を空洞化する)。

| 記号(完全修飾名) | 受け取るもの | 役割 | `allowed_api_ids` |
| --- | --- | --- | --- |
| `pitchlog.authz.product_provisioning._run_product_operation` | **閉じた指示だけ**(`ProductOperation` の列挙 = `APPLY` / `UNAPPLY`)。**文も、文を保持する計画も、資産の置き場も受け取らない** | **末端関数の中で**、モジュールから導いた正規の資産の置き場(`contracts/authz/product/`)を読み、生成器で文を作り、1 トランザクションで実行して commit または rollback する。記録点(3 節)を呼び、各記録点で主体を確かめる(1-a) | `PSYCOPG_CONNECTION_CURSOR`・`PSYCOPG_CURSOR_EXECUTE`・`PSYCOPG_CONNECTION_COMMIT`・`PSYCOPG_CONNECTION_ROLLBACK` |
| `pitchlog.authz.product_catalog._fetch_catalog_rows` | **閉じた問い合わせ ID**(モジュール内の定数の列挙。文の本体はモジュール内に固定)と、**束縛値だけ**(OID の列など — 文の一部にならない) | 問い合わせを 1 本実行して行を返す。**読み取りだけ** | `PSYCOPG_CONNECTION_CURSOR`・`PSYCOPG_CURSOR_EXECUTE` |

- **文の生成を末端関数の中に閉じる**(計画レビュー 2 周目 P0 — 1 周目の「検証済みの実行計画の型を渡す」案は、型が不変でも外から構築でき、手順 ID の一致は文の中身を拘束しなかった)。呼び出し側が文に触れる経路が無いので、**実行される文 = 正規の資産から生成器が作る文**に限られる。資産の置き場を引数にしないのは、別の置き場の資産(= 任意の文)を渡せなくするため
- 故障注入は、試験が**記録点**(3 節)を monkeypatch して行う。文や資産を差し替える口は設けない
- **参照を exact-set で固定する**: `_run_product_operation` を参照するコード = `apply_product_authz_ddl`・`unapply_product_authz_ddl` の 2 つ / `_fetch_catalog_rows` を参照するコード = `inspect_product_authz_catalog` の 1 つ。**呼び出しに限らず、名前・属性の参照(別名への代入・関数オブジェクトの受け渡しを含む)を AST で全数列挙**し、同一モジュール内を含めて追加の参照は red
- **接続の前提**: 実行の前に、接続が **閉じていない・autocommit が無効・トランザクションの状態が IDLE**(probe の適用器と同じ — `provisioning.py:681-686`)で、**superuser であり、アプリ用ロール(`pitchlog_app`)でない**ことを確かめ、違えば**文を 1 つも実行せず、commit も rollback もせずに**拒否する(計画レビュー 3 周目 P1 — autocommit の接続では部分適用が残り、進行中のトランザクションを持つ接続では呼び出し側の処理まで commit・rollback の対象になる)
- **シグネチャは実装ステップ 2 で登録した文字列に固定する**。実装(ステップ 3・4)の型注釈がそれと食い違えば TB005 で red になる
- **probe の `provisioning.py`・`catalog.py` の既存の DB 呼び出しの行は変えない**(変えると基準版との相殺が外れる)。製品版は別モジュールに置き、probe と共有するのは DB を触らない部品(資産の読み込み・SQL の生成)だけにする

### 1-a. `SET ROLE` を使わないことの証明

A1 design 4-2 の「適用主体は `SET ROLE` を使わない」は、**端点での `current_user = session_user` だけでは証明できない**(途中でロールを変えて終了前に戻す類型を見逃す — 計画レビュー 1 周目 P1)。→ 次の 2 つを両方置く:

1. **静的**: 生成器が作る適用と取り外しの文の全集合に、主体を変える文(`SET ROLE`・`RESET ROLE`・`SET SESSION AUTHORIZATION`・`RESET SESSION AUTHORIZATION`・`SET ... ROLE` を含む関数の属性 など)が **0 件**
2. **動的**: **各記録点**で `current_user = session_user` を確かめる(commit 後・rollback 後に加えて)。途中の 1 か所だけ主体が変わる変異が red

## 2. 製品の適用手順を資産に持つ

A1 の staged 資産には、probe の `provisioning_claim` に当たる手順の宣言が無い(research.md 3・4)。

→ **新設の資産 `contracts/authz/product/application-steps.json`** に、次を閉じた形で持つ:

- 適用の手順 7 つ(A1 design 4-2 の順序で固定。**補助関数はポリシーより先**)と、各手順が受け持つ要素の種別(`roles` → 手順 1 / `databases`・`schemas` → 2 / 補助関数 → 3 / `tables` → 4 / `policies`・**`predicates`**〔ポリシーの生成の入力。単独では実行しない〕 → 5 / `acl_expectations`・`column_acl_expectations` → 6 / トリガ関数 → 7)。**母集合は `PRODUCT_SPEC` の要素の節の全部**(`asset_spec.py:273-291` — role・database・schema・function・table・predicate・policy・acl・column_acl)で、各要素がちょうど 1 手順に割り当たる(計画レビュー 3 周目 P1)
- `transaction`: `single`(1 トランザクション)
- 取り外しの手順(A1 design 4-3 の逆順。**ポリシーを補助関数より先に落とす**。`pitchlog_owner` は削除しない)
- 製品の操作種別の閉じた集合(A1 design 4-4 — **probe の 5 種と混ぜない**)。`PRODUCT_SPEC` の操作の対応をここから持つ

**静的検査**: 手順が 1 からの連番・種別の割り当てが staged 資産の全要素を 1 回ずつ覆う(過不足 0)・取り外しが適用の逆順・`transaction = single`。staged 資産 `ddl-elements.staged.json` は変えない(A1 の exact-set 検査を壊さない)。

## 3. 記録点と故障注入

- 記録点の ID は `product:<手順番号>:<位置>`。故障注入点は **A1 design 4-2 の失敗点 5 か所**(手順 1 の直後 / 手順 3 の補助関数の作成の直後 / 手順 4 の直後 / 手順 5 のポリシーの作成の直後 / 手順 6 の途中)と、**取り外しの 2 か所**(ポリシーの削除の直後 / 補助関数の削除の直後 — A1 旧 16)
- 資産 `contracts/authz/product/failure-injection-points.json` に置き、`application-steps.json` へ blob digest で結び付ける(probe の形 — research.md 3)
- 試験は probe と同じく、記録点の直後に例外を投げて、失敗前・失敗後・再適用後のカタログを比べる

## 4. 製品のカタログ検査

- **新設モジュール `pitchlog.authz.product_catalog`**。probe の `inspect_authz_catalog` は `role_kind` と `provisioning_claim` に依存するので使わない(research.md 3)。probe の振る舞いは変えない
- 期待値は **staged 資産と `application-steps.json` から導く**。**危険ロールの許可集合** = 製品固定の `pitchlog_owner` ∪ **検査の入力として渡す環境の superuser の OID**(A1 design 2-0・6-3)
- 見るもの(A1 旧 14 を 37 個へ読み替え): 全 45 表の `relrowsecurity`・`relforcerowsecurity` / `pg_policy` / 表・列・スキーマ・関数・DB の ACL / ロールの 7 属性 / DB とスキーマの所有者 / **`pg_auth_members` の製品ロールに接する行 0 件** / LOGIN できる危険ロール = 許可集合 / **37 個のトリガ関数がすべて `SECURITY INVOKER`**

## 5. `allowed_symbols` の追加の順序と記録

- A1 の決定「適用器・fixture と `allowed_symbols` の追加は別のステップ、ただし同じ PR」(A1 plan.md 4 節)に従い、**記号の登録(ステップ 2)を、DB 呼び出しを足すステップ(3・4)の前に置く**。検査器は記号がソースに存在するかを読み込み時に見ない(research.md 2)ので、先に登録しても検査器は落ちない。**ステップ 3・4 の各コミットで迂回検査が green** になる
- 記録は **7C のマージ版の形式**で 1 件残す(research.md 1 の見込み: `contract_revision` +1・v2 記録・history-snapshots・draft PR で番号を先に確定)。**形式が見込みと違えば、計画書を改訂して承認を取り直してから実装する**(計画書 4 節の関門)
- 正例 fixture は記号ごとに 1 件(`tests/fixtures/tenant_boundary/positive/`)
- 7C のマージ版が `contracts/tenant_boundary/history-snapshots/<sha256>` を要求する場合、**その変更パスはステップ 2 の範囲に入る**(計画書 2 節・4 節の不変条件の例外として列挙する)

## 6. 実 DB 試験・移行バッチ用ロール・写像

A1 design 6 節・7 節・8 節どおり。A2 で決めるのは次だけ:

- **試験は manifest の事実からパラメタ化して生成する**(分類資産から期待値を導かない — A1 旧 17)
- 制御資源の正負行列の試験は、**rollback する試験のトランザクションの中でだけ** `pitchlog_app` に一時の権限を与え、rollback の後にカタログが exact-set に戻ることを確かめる(A1 旧 18)
- 移行バッチ用ロールの有効な間の形は A1 design 8-2 の全項目を検査する: **表 ACL が exact・`public` スキーマは `USAGE` のみ(スキーマ ACL を `{public: USAGE}` と exact-set)・DB は `CONNECT` のみ**(計画レビュー 1 周目 P1)
- 実 DB 試験は、**対象の行が存在することを事前条件として表明する**(空の表で「読めない」「0 行」が偶然成り立つ試験を落とす — 同 P1)
- 移行バッチ用ロールの資産 `contracts/authz/product/migration-batch-role.json` と、写像資産 `contracts/authz/product/probe-product-map.json` は **staged 資産と同じ置き場**に置く。写像の製品側の母集合は `ddl-elements.staged.json` だけ(移行バッチ用ロールを含めない — A1 旧 21)

## 7. 正本の追随

- `data-model.md` 12-8: TSK-424 系の行に、**A2 の範囲(適用器・カタログ検査・実 DB 試験・移行バッチ用ロールの資産・写像)を「使い捨てクラスタで確認済み・未発効」**として追記する。**「解消済み」にはしない**(実スキーマへの適用は TSK-344、ランタイム契約の切り替えは TSK-443)
- 変更履歴に 1 行(版は上げない)・`docs/README.md` の索引の行
- **data-model.md を変えると派生資産 2 か所の取り直しが機械的に要る**(A1 で確認・人間が承認した例外 — A1 plan.md 4 節): `contracts/authz/shared-preconditions.json` の `mapping_target.git_blob_digest`(`scripts/check_shared_preconditions.py:359-368`)と `contracts/db/schema-manifest.json` の `canonical_source.sha256`。**許す差分は両ファイルのこのフィールド各 1 行だけ**で、両 digest が更新後の `data-model.md` と一致すること。封印(`oracle-seal.lock.json`)と probe の意味内容は変えない
- **3-2・12-4・12-6 は変えない**(A1 と同じ — TSK-382・TSK-445 の射程)

## 未解決・検討メモ

- 7C の記録形式(5 節)— PR #78 のマージで確定する
- (解消)末端関数の転用 — 1 節で、受け取るものを閉じた指示だけにし、文の生成を末端の中に閉じ、参照を exact-set で固定した(計画レビュー 1 周目・2 周目 P0)
