---
feature: ua1-auth-db-layer
type: research
date: 2026-10-04
---

# 調査メモ: U-A1 β — 認証の DB 層(TSK-468)

調査方式: 調査サブエージェント 3 本(decision-tracer / spec-checker / Explore)を並列で実行し、計画の形を決める主張は Claude が原典で再確認した。
表記: **[確認済]** = Claude が原典を読んで裏を取った / **[報告]** = エージェントの報告(典拠付き・未再確認)/ **[実測]** = 稼働中の開発 DB(`pitchlog-db-1`・postgres:17.11)への SELECT で測った値(エージェント実施)。

前提の調査: α の [research.md](../ua1-team-auth/research.md)(本文 + 追補 2026-10-03)と [design.md](../ua1-team-auth/design.md) 3 節(β の射程)。条文の正は `docs/design/data-model.md` **v0.4**(approved — PR #90・2026-10-04)。

## 問い

1. β が満たす義務の全数(v0.4 の条文から)と DoD との差
2. PR B(#87 — TSK-443)のマージ後に、製品 authz 資産へロール・関数を足す手順
3. 実装の仕組み — 退役述語・正規化関数・pgcrypto・migration の連鎖・システム設定値・試験基盤
4. 人間の判断が要る論点

## 結論(要約)

1. **β は 1 つの PR に収まらない規模**である。**製品 authz 資産の基盤の一般化**(関数種別・スキーマ・拡張・列/表 ACL の閉じた集合・migration 由来関数の固定数・切り替え後のランタイム契約の再導出)が、認証そのもの(ロール・関数・migration 0027)とは別に要る。前者は U-A2・U-C1・U-C3 も通る共通の前提である(4 節)
2. **migration に置けないもの**がある: ロール作成・DML を含む関数・設定値の seed(`backend/tests/test_migration_hygiene.py:16-28` が `CREATE ROLE` / `ALTER ROLE` / `INSERT INTO` / `UPDATE … SET` / `DELETE FROM` を全 migration で禁じる **[確認済]**)。**認証関数とロールは製品 authz 資産に置く**ことになる
3. **`tenants` に `retired_at` 列が無い**ので、正規化名の部分一意索引(`WHERE 退役していない`)を置くには列の追加と移行バッチ用ロールの権限が要る(3-1)
4. **正規化に使う組み込み関数はすべて IMMUTABLE**([実測])。ただし「DB の 1 つの関数」(v0.4 8-1)を利用者定義関数で置くと、migration 由来関数の固定数(37)・EXECUTE 権限・式索引と manifest の検査に当たる(3-2)
5. **PR B のマージ後に資産へ関数を足す手順は定めが無い**。製品状態のランタイム契約を再導出する生成器のモードも無い(2 節)
6. **人間の判断が要る論点は 4 件**(5 節)

## 1. β の義務(v0.4 の条文から — spec-checker)**[報告 — 典拠は data-model.md の行]**

全 61 項目のうち **β の担当が典拠で明示されているもの**の要約(全数は計画書の DoD とテスト計画で網羅する):

| 群 | 義務(要約) | 典拠(data-model.md) |
| --- | --- | --- |
| ロール | 認証関数所有用ロール(`NOLOGIN` + `BYPASSRLS`・DDL 不可・無 `GRANT`)/ 到達先は認証前 4 表とテナント表・システム設定値の読み取りに限る / 関数群ごとの `EXECUTE` 付与先 / `search_path`・一時スキーマ・名前解決経路の非注入 / スキーマ検査の試験 | `:217`・`:234`・`:248-252`・`:250` |
| 一意性 | 実装待ちの 2 行を migration・manifest と同じ PR で主表へ / `UNIQUE (正規化(チーム名)) WHERE 退役していない` / 認証主体の `UNIQUE (tenant_id)` / 複合参照の参照先 `UNIQUE (tenant_id, id)` / 一意化前の検査 | `:419`・`:423-424`・`:1511`・`:1517`・`:1663` |
| 照合 | DB 内の `SECURITY DEFINER` 関数だけで生成・照合(pgcrypto・コスト 12)/ 有効テナントにだけ発行・無効の拒否も同じ応答 / PW 変更の対象は検証済みトークンの主体 / 現行 PW の照合 → 1 トランザクション / ハッシュを外へ返さない / ポリシー判定は唯一の関数 / 72 バイト超を拒否しない / 失敗経路を分岐させない | `:1526`・`:1532-1545` |
| トークン | 発行時の世代 / 1 回の呼び出しで存在・期限・世代・有効性・テナント一致を照合 / 同じ関数で延長 / 有効期限は設定値から自分で読み・未設定なら発行と延長を拒否 / ID は DB 側の暗号論的乱数で発行の応答以外に返さない / ログアウト / 無効化と同時の世代 +1 の限定関数 / 失効トークンを復活させない(並行しても失効が勝つ)/ PW 変更の応答で新トークンを発行しない | `:1663-1692` |
| 計数 | 不変条件 ③〜⑥(同一コミットで確定・直列化・関数の内側・物理削除しない)の器 / 管理者用の計数の限定関数 | `:1781-1785` |
| 監査 | 退役の不変条件 5 を 8 件へ(スキーマ監査も)/ exposure-facts の典拠差し替え(TSK-453 の残り)と `tenant_tokens.id` の秘密の列への追加 | `:2437`・ua1-team-auth/design.md 3 節 ⑦⑧ |

**DoD(Notion TSK-468)に無いが義務表にあるもの**: 世代繰り上げの限定関数 / 失効トークンの非復活 / PW 変更の対象の限定 / リセットでの世代 +1 / ログイン解決を退役していないテナントに限る / 正規化関数の単一性 / 72 バイト超の受理 / 延長も未設定で拒否 / 到達先の限定・スキーマ検査・非注入 / 12-4 の判定記録。**計画書の DoD はこれらを含めて書く**。

**担当が典拠から決まらないもの(不明)**: 制約違反の詳細の秘匿(3-4 規則 3 — 応答層)/ トークン検証を通らない経路の有効性検証(`:1518-1520`)/ 物理削除しない・ウィンドウ外を参照しない(器と具体設計の両方に掛かる)/ `code_hash` の非露出の実装(表は `effective_group_control`)/ 12-8 の実装追随。**計画書で割り振るか、受け取り先を明記して外す**。

**不変条件 ② の割当が食い違う**: ua1-team-auth/design.md 3 節は β の器を「③〜⑥」、同 plan.md 6 節は ② を「β・γ」に置く **[報告]**。

## 2. PR B(#87)のマージ後に資産を足す手順(decision-tracer)

| 事実 | 典拠 |
| --- | --- |
| #87 はステップ 7 まで済み。ステップ 8(staged → 最終資産への `git mv`・`provisional_contract_additions` の除去・`switch --base S`・受理記録)は **`origin/develop == S` の間にマージ**の拘束付き。**#90 のマージで受理が失効し、取り込みからやり直し中**(2026-10-04) | runtime-contract-switch `plan.md:86-95`・`design.md:230-247`・worklog `:45-50` **[報告]** |
| 製品状態では保護対象を最終資産の `schemas`・`tables`・`functions` の全件から導き、資産の導出欄との一致を常に照合する(P4 `DERIVED_FIELDS_STALE`) | 同 `design.md:45-47`・`:177`、`runtime_contract_state.py:152-193`・`:428-429` **[報告]** |
| 生成器のモードは `check` / `render` / `switch` だけで、**製品状態のランタイム契約を再導出するモードが無い** | `runtime_contract_generator.py:264`・`:111-146` **[報告]** |
| **切り替え後に後続単位が資産を足す手順は定めが無い**(不明) | 同 `design.md:275-278` **[報告]** |
| ランタイム契約の値を動かすと、凍結基準への受理記録(7.7-2)を `base-allowlist.json` に 1 件・snapshot・corpus digest の取り直しが要る(PR B の先例) | 同 `design.md:35-36`・`:214`、worklog `:47`・`:62-63` **[報告]** |
| `check_authz_catalog.py` の該当関数は PR B で `state` 引数を取る形に変わる(関数 ACL・補助関数・表 ACL・資産キー集合・保護対象) | PR B の `check_authz_catalog.py:3711-4348` **[報告]** |
| TSK-344(承認済)は資産を読むだけで、**ロール集合を資産から導く**(運用正本 `docs/ops/product-rls-real-schema.md:153-165`)。最低要求④は「越境関数 0 件の間は 0 件の表明」。**認証関数が④(共有の越境)の対象かは未決** | product-rls-boundary-tests `plan.md:75`・`:244-249`・`:469` **[報告]** |

**β への含意**: **β の実装は #87 のマージ後**(既定どおり)。関数を足すには **製品状態の再導出手段(生成器の拡張か手順)** と受理記録が β の射程に入る。**β が develop に入ると #87 の S がまた動く**ので、β のマージは #87 より後に限る。

## 3. 実装の仕組み(Explore)

### 3-1. 退役述語 **[報告 — 一部確認済]**

- 既存の 7 件は**行ごとの `retired_at timestamptz NULL` 列**と述語 `retired_at IS NULL`(バッチ表は参照しない)— 0003:96-100 ほか。ORM は `RetirementMixin`(`backend/src/pitchlog/db/mixins.py:36-41`)
- **`tenants` に `retired_at` 列は無い**(0002:19-30)。manifest も `migration_retirement: "持たない"`
- スキーマ監査は表ごとに `retired_at` 列と述語を要求(`backend/tests/db/test_schema_audit.py:684-698`)
- → **`tenants.retired_at` の追加**(ORM・manifest の列と lifecycle・`allowed_update_columns`)と、**移行バッチ用ロールへの `UPDATE (retired_at) ON tenants`**(`contracts/authz/product/migration-batch-role.json`・試験 `test_product_authz_migration_batch_role.py:282-323`)が要る

### 3-2. 正規化関数 **[実測]**

| 関数 | 揮発性 |
| --- | --- |
| `pg_catalog.normalize(text, text)` | **IMMUTABLE**(Unicode 15.1) |
| `lower(text)` / `btrim(text)` | **IMMUTABLE** |

- `lower(btrim(normalize(x, NFKC)))` は全角空白・全角英字・半角カナを期待どおり正規化する。照合順序は libc `C.UTF-8`
- **組み込み関数だけなら式索引に使える**。ただし v0.4 8-1「**正規化は DB の 1 つの関数に置き**、一意索引・ログイン時の解決・登録時の重複チェック・カウント単位がすべてそれを使う」を**利用者定義関数**で満たすと、次に当たる:
  - migration 由来関数の固定数 37(`scripts/check_authz_catalog.py:3962-3969` と試験 6 か所)と `migration_trigger` 種別の exact 照合 **[報告]**
  - 式索引は manifest の検査が「一意制約の構成列が実在」を要求(`backend/tests/test_schema_manifest.py:319-320`)・ORM 試験が `index.columns` を使う(`test_tenant_models.py:195-237`)**[報告]**
  - 索引式の利用者定義関数の `EXECUTE` が挿入ロール(移行バッチ用ロール — 関数 EXECUTE 0 件が要求)に要るか **[推測・要実測]**
- **[推測]** `btrim(text)` は U+0020 だけを除く(タブ・改行は残る)。libc の `lower` と Unicode 表は版更新で結果が変わり得る(索引の再構築)

### 3-3. pgcrypto **[実測]**

- 利用可能(1.3・未導入)・**trusted**。関数 36 個はすべて既定で `PUBLIC` が `EXECUTE` できる。`gen_random_uuid()` はコアにあり、トークン ID に pgcrypto は不要
- `public` / `authz_private` に置くと「移行バッチ用ロールが利用者定義関数を実行できない」検査に当たる(`backend/src/pitchlog/authz/product_catalog.py:423-435`・`:1144-1172`)**[報告]**
- **専用スキーマ**(`PUBLIC` に `USAGE` なし・認証関数所有用ロールにだけ `USAGE`)なら当たらない見込み **[推測]**。trusted 拡張のメンバー関数の所有者と `REVOKE` の可否は **[未実測]**
- 前例なし(`CREATE EXTENSION` は migration・contracts・tests に 0 件)

### 3-4. migration 0027 の連鎖 **[報告 — 一部確認済]**

| 対象 | 要る変更 |
| --- | --- |
| `contracts/db/schema-manifest.json` | tenants の `retired_at` 列・一意索引(`business_unique`・scope `outside`)/ 認証主体の `UNIQUE (tenant_id)`(`business_unique`)と `UNIQUE (tenant_id, id)`(`fk_target`)/ トークンの複合 FK / `canonical_source.sha256`(data-model.md を変えるため) |
| `backend/tests/db/test_schema_audit.py` | 退役述語の辞書に tenants(`:42-51`)・7 → 8(`:680`)・**business_unique 27 → 29(`:728`)・テナント外 4 → 5(`:732`)** |
| `backend/tests/db/test_alembic_migrations.py` | **`:4738-4749` が 1 テナントに認証主体を 4 件入れる**(`UNIQUE (tenant_id)` で red)**[確認済]** |
| ORM `models.py` | Tenant に `RetirementMixin` と索引 / TenantAuthSubject に一意 2 本 / TenantToken に複合 FK |
| alembic check / 往復試験 | 式索引の deparse 差分(`NORMALIZE`)が出るか **[推測・未実測]** / downgrade も要る |
| 受入突合シート | 再生成と期待行数(α の前例 — ua1-team-auth worklog) |
| `contracts/authz/shared-preconditions.json` | data-model.md の digest(3-4 の主表へ 2 行を移すため) |
| 複合 FK の書式 | `match="FULL"`・`ondelete="NO ACTION"`(0002:70-76・0007:88-96)。PK の上位集合の `UNIQUE` を参照先にする前例は `uq_idempotency_ledger_kind`(0007:40-45) |

- **[推測]** 製品 DDL 適用後に `pitchlog_owner` が migration を流すと `FORCE` で tenants が 0 行に見え、一意化前の検査は空振りし得る(索引の作成自体は実データで失敗する)

### 3-5. システム設定値 **[報告]**

- `system_settings`(`key TEXT` PK / `value JSONB` / `updated_at`)— 0010:85-95。**seed は無く、キー名(トークン有効期限・閾値)の定義もリポジトリに無い**。migration での seed は hygiene が禁止
- 認証関数所有用ロールは**現状では読めない**(表の権限なし・schema public の `USAGE` なし)。前例は共有関数所有用ロールへの列単位の `GRANT`(`COLUMN-ACL:public:tenants:{id,enabled}:pitchlog_shared_fn_owner.sql`)
- → **キー名の定義・seed の担い手・所有ロールの読み取り権限**が要る。**未 seed の間はログインと発行が拒否される**(v0.4 の fail-closed)

### 3-6. 試験基盤 **[報告]**

- `provisioned_product_catalog`(`backend/tests/db_fixtures.py:949-1015`): owner で `alembic upgrade head` → superuser で `apply_product_authz_ddl()`
- `pitchlog_app` としての呼び出しは `SET LOCAL ROLE` か実接続。最低要求 ②③ の形は `test_product_authz_cross_cutting.py:414-540`、④ は `:543-567`(関数を足すと red)

## 4. 一般化の担い手(decision-tracer)**[報告]**

- 一般化を β に割り振った記録は ua1-team-auth の文書だけ(`design.md` 3 節 ① — 承認済み計画)。U-A2・U-C1・U-C3 の側にこれを前提とする記録は無い
- 一般化で開く閉じた集合: 関数種別(`asset_spec.py:244-253`)/ 適用手順 7 つ / ロール集合 4 件(`check_authz_catalog.py:208-249`・試験 `roles == 4`)/ 列 ACL 8 件 exact(`product_control_access.py:22-31`)/ 表 ACL のプロファイル由来 exact / migration 由来関数 37 件 / 保護関数 38 件(試験 3 か所)/ `product_provisioning.py:349`(取り外しで `rls_helper` 以外を `PUBLIC` へ戻す危険)

## 5. 人間の判断が要る論点

| # | 論点 | 選択肢 |
| --- | --- | --- |
| **B-1** | **β を 2 つに分けるか** | (a) **β1 = 製品 authz 資産の基盤の一般化**(U-A2・U-C1・U-C3 と共通)+ **β2 = 認証の DB 層** / (b) β を 1 本のまま |
| **B-2** | **「正規化は DB の 1 つの関数」の実現** | (a) 利用者定義の `IMMUTABLE` 関数(生成列か式索引から使う。migration 関数の固定数・EXECUTE の検査を開く)/ (b) 正規化名の生成列 + 認証関数は入力にも同じ関数を適用(関数は資産側)— 実測しだい |
| **B-3** | **チーム名の長さの上限値** | 要件・正本に典拠なし。登録とログインで同じ値・既存行が超えれば migration を止める |
| **B-4** | **システム設定値のキー名と seed の担い手** | migration で seed できない。β がキー名を定め、seed は管理経路(U-A2)か配備手順(δ)か |

### 人間の決定(2026-10-04・山田正輝)

| # | 決定 |
| --- | --- |
| B-1 | **β は 1 本のまま**(基盤の一般化と認証を TSK-468 の中でステップとして順に進める) |
| B-2 | (人間に問わず)**計画の最初のステップで実測して確定**する(式索引・生成列・利用者定義関数の EXECUTE の挙動) |
| B-3 | **チーム名の長さの上限 = 64 文字**(正規化後の文字数。登録とログインで同じ値) |
| B-4 | **β が設定値のキー名と値の形を定め、試験では fixture で投入する。本番の投入は δ の配備手順**(10 章の相談で決まる閾値もここで入る)。管理コンソール(U-A2)ができたら変更はそちら |

## 未解決・申し送り

- 認証関数が最低要求④(共有の越境)の対象か — TSK-344 と調整(2 節)
- 不変条件 ② の β/γ の割当の食い違い — 計画書で確定する(1 節)
- 担当が不明な 5 件 — 計画書で割り振るか受け取り先を明記する(1 節)
