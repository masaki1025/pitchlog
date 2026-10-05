---
feature: vocab-category-fk
type: research
date: 2026-10-06
---

# 調査メモ: system_vocabularies の FK に category 強制を入れる(TSK-480)

基点: develop `27ff94eb`(本 worktree の作成時点)。調査は spec-checker / decision-tracer / legacy-analyst / Explore の 4 本(2026-10-06)。
行番号はすべて本 worktree の内容に対するもの。**エージェント報告どうしの食い違いと、カード・申し送りの古い行番号は原典で裁定した**(末尾「裁定」)。

## 問い

1. 案「`UNIQUE (key, category)` + 参照側の category 固定列 + 複合 FK」は要件・正本と矛盾しないか。正本のどこを改訂するか
2. 掛かるゲート(7.3 確定ゲートか、7.6-3 前段の PR レビューか)とコア領域の判定
3. 機械的に連動する資産・検査・テストの範囲と、使える前例
4. 移行バッチ側の追随の要否
5. 射程(system_vocabularies の 3 FK だけか)

## 結論(要約)

- **要件書は改訂不要**。語彙キーの一意性の範囲(区分をまたぐか、区分内か)を定めた条文は無い(requirements:168-179 ほか — 1 節)
- **主キー `(key)` を残して `UNIQUE (key, category)` を「足す」だけなら、正本 3-4 節の一意性の表(:407・:399)は書き換え不要**。前例 `uq_idempotency_ledger_kind` は `roles: ["fk_target"]` で正本表の行を持たない(schema-manifest.json:502)。ただし**正本 10-3 節 :2021-2027 が「category 強制は … スキーマの変更であり確定ゲートを要する」と自ら書いている**(本書で原典確認)。これを「是正済み」へ追随させる改訂がゲートの判断点になる(判断点 A)
- **実装の型は前例どおり**: 定数列(DEFAULT + NOT NULL + `CHECK (列 = '定数')`)+ 参照先 UNIQUE + `MATCH FULL` の複合 FK(0005:60-65,83 / 0007:40-96)。**FK を同名で張り替える手順**は 0028:153-187、**FORCE RLS 下の事前検査**は 0028:22-102。**生成列は避ける**(FK に使った前例が無く、`test_game_state_models.py:132-140` が拒否する)
- **射程は未確定**: 同型の非拘束が `admin_vocabularies`(FK 4 本)と `tenant_vocabularies`(FK 7 本)にもある。正本に記録があるのは system 層の 3 本だけ(判断点 B)
- **「その他」の衝突は案では解けない**: 在籍区分が `other` を取っているので、試合区分の「その他」は別キーにするしかない(TSK-475 で案「戊」を退けた経緯 — roster plan.md:124,143)。TSK-479 の命名に申し送る(判断点 C)
- **TSK-382(feature/real-schema-meaning)が data-model.md を v0.6・in-review で改訂中**(確定ゲート 4 周・PR 未作成)。data-model.md を触るなら版番号・封印 2 件と衝突する

## 詳細と典拠

### 1. 要件・正本(spec-checker)

- 要件書 4.0-3 語彙の 3 層: requirements:168-179。:171 システム固定 = 試合区分(公式戦/準公式戦/オープン戦/紅白戦/その他)と在籍区分(現役/その他/OB)。:175 使用実績のある語彙は削除不可・無効化のみ。**キーの一意性の範囲を述べた条文は無い**(「一意」の全文検索で語彙キーへの言及 0 件)
- 関連 FR: FR-001 :195 / FR-014 :334,:339 / FR-017 :374-383 / FR-037 :768,:770 / 付録F-2 :1291-1298 / 付録D-4 :1242 / 6.2 :996。改善台帳 I-10(improvements:99-107)・I-13(:123-128)にも一意性の言及なし
- data-model.md 10-3(:1995-2027): :2011-2013「システム固定・管理者管理の層は … 一意制約はグローバル」/ :2016-2020 在籍区分のキー / **:2021-2027 ⚠ 項(TSK-480 を受け取り先として記録・「確定ゲートを要する」)**
- 3-4 の業務的一意性の表: :387(チーム拡張可 `UNIQUE (tenant_id, キー名)`)/ :399(管理者管理 `UNIQUE (キー名)`)/ :407(システム固定 `UNIQUE (キー名)`)。全数表と manifest の全数一致の機械検査あり(:426・test_schema_manifest.py:553)。`business_unique` を足すと test_schema_audit.py:762-776 の固定件数(29 件・テナント外 5 件)で red
- FK 規約: 3-4 規則 2(:430-442)は `(tenant_id, …)` の複合参照のみ。**区分を含む複合 FK の規約・MATCH の規約は正本に無い**(harness-evaluation.md:2740-2741)。実装側に `test_full_match_foreign_keys_do_not_mix_column_nullability`(test_schema_manifest.py:727)
- 規律: 「同じ不変条件を 2 箇所で定義しない」(data-model:51)。制約違反の秘匿(規則 3 :445-455)は新 FK にも掛かる
- 無効化(disabled)とは独立(複合 FK は disabled を見ない — 条文と DDL の突合からの推論)。disabled と「変更しない」の張力は TSK-481 が別に持つ(roster plan.md:422)

### 2. 決定経緯・ゲート(decision-tracer)

- TSK-475 の裁定: roster plan.md §4-5「逆方向の誤参照」:384-414 の【裁定 2026-10-03】:400-411 で (ii)「別タスク + 着地条件」を採用。案「戊」(`UNIQUE (key, category)` + 複合 FK)は :124,:129-132 で追加、:134-143 の裁定で不採用(「試合区分の命名を正本で固定すると 7.6-3 の実装追随では扱えず 7.3 に入る」)。research の裁定表 roster research.md:238,:249-250
- 着地条件: roster plan.md:435-439 / data-model:2025-2026
- 射程外 4 件: ① TSK-479 試合区分 seed ② TSK-480(本件)③ TSK-481 disabled の張力 ④ TSK-482 正本 :2421 と DML 禁止検査の食い違い(roster plan.md:418-423)。重複なし(:467-468)
- **PK を key 単独にした採否の記録は無い**(不明)。記録はテナントで閉じるかの軸だけ(data-model:2011-2013・product-data-model-design/design.md:1238-1240・orm-schema-migration/plan.md:781)
- 7.6-3(dev-harness-design:516): 「実装追随の節更新・変更履歴追記は PR レビューで足りる。版繰り上げを伴う構造的変更(アーキテクチャ・スキーマの変更 …)はその部分だけ 7.3」。7.3 の要件 :435-490(射程宣言は変更履歴の in-review 行 — 7.3-7 :488)
- 0028 の前例(TSK-468)は**正本 8-3 が先に「複合参照で強制する」と定めていた**ので実装追随・版据え置きで通った(data-model:10,:1673)。本件は正本が FK の形を定めていない点で条件が違う
- data-model.md の現状: `status: approved`・v0.5(:1-11)。**TSK-382 が v0.6・in-review**(real-schema-meaning worktree の data-model.md:2・plan.md の確定ゲート周回 4・承認 済 2026-10-05)。TSK-469(ua1-auth-app-layer)も :2928 の 1 行を実装追随で直す予定(同 plan.md:96,:264-283)。OPEN PR は #97(TSK-344)・#95(U-M1)・#81 で、TSK-382 の PR は未作成(2026-10-06 `gh pr list`)
- コア領域: `backend/migrations/*`・`backend/tests/db/*`・`contracts/db/schema-manifest.json`・`docs/design/data-model.md` は 5 領域すべての paths に一致(core-areas.json:138-139,159 ほか)。`db/tenant_isolation/*` はテナント分離(:359)、`db/game_state/*` は状況計算(:211)。意味範囲(設計書 6.3 :392-398)はスキーマ FK を名指ししない。「迷えば含む側」(:400)。**TSK-475 は同じ当てはめでコア領域にした**(roster plan.md:470-485)→ ADR-001:50(`gpt-6-sol` xhigh・敵対レビュー・逐行確認)
- 凍結点: `contracts/authz/shared-preconditions.json:16-20`(git blob digest `e0bbe98d…` — 検査 scripts/check_shared_preconditions.py:365-369)/ `contracts/db/schema-manifest.json:5-10`(sha256 `10847d4d…` — 検査 test_schema_manifest.py:171-177,:535-546)。**どちらも `baseline_control` を持たず受理記録は不要**(ua1-auth-app-layer plan.md:266-273)。取り込み費用の原則は候補段階(harness-evaluation.md:4788-4878 — H-* 未採番)

### 3. 機械的な影響範囲(Explore)

- migration head: `0028_tenant_login_identity`(0028:8-9)。新 revision は `0029_…`(32 文字以内 — test_migration_hygiene.py:1351)。**DML 禁止**(同 :26-39)→ 既存行の埋め戻し不可。新列は DEFAULT 必須
- 対象 FK: 0010:98-106 / :116-124 / :134-142(単列・MATCH SIMPLE・NO ACTION)。system_vocabularies 表定義 0010:26-39、不変トリガ :153-179
- ORM: `SystemVocabulary` tenant_isolation/models.py:1145-1174 / `Player` 同 :162-239(FK :175-182・列 :213)/ `Game` game_state/models.py:64-158(FK :72-79・列 :116)/ `GameTypeRuleDefault` 同 :406-447(FK :411-418・列 :434)。ORM の前例 sync_protocol/models.py:124,:199-210,:260-262,:375-380
- manifest(手書き・生成器なし): players :79-107 / games :109-149 / game_type_rule_defaults :251-268 / system_vocabularies :677-694
- 受入シート N7(orm-schema-migration/acceptance-sheets/N7-required-attributes.md :29,:126,:136)が列を持つ → `scripts/generate_orm_acceptance_sheets.py` で再生成・判定欄を記入(tests/test_orm_acceptance_sheets.py:123,:368)
- DB テストの要更新点: test_alembic_migrations.py:4260-4323(3 FK の `confmatchtype='s'` を完全一致 — FULL にすると `'f'`)/ :4127-4199 / :1069-1112。test_roster_status_seed_db.py:225-323 は **FK 名で検査** → 同名で張り替え、downgrade は同名の単列 SIMPLE へ戻す
- head 前提のテスト: test_alembic_migrations.py:8400-8456(0028 までの upgrade で authz カタログ ok を要求)・:8270,:8458-8526(head → 0027 の downgrade を FORCE RLS 下で実行)。**新 migration が関数・ACL を持つ物体を作らなければ影響なし**
- 新列を `protected_columns` に入れるとトリガが要る(test_immutability_enforcement.py:242-262)。**PARTIAL のまま未分類にすれば連動しない**。トリガ関数を新設すると authz 資産一式(ddl-elements・function-bodies・runtime_contract.py:129)が連動 → **関数は作らない**
- product_authz のテストケースは新列を指定せずに INSERT する(product_authz_tenant_owned_cases.py:716-777 ほか)→ **DEFAULT 必須**
- DB テストの実行: `PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN`(environment-expectations.json:195-210・未設定は fail)。使い捨てクラスタ db_fixtures.py:616-680(`postgres:17.11-bookworm`)。CI は `uv run pytest -c pyproject.toml --cov` + alembic `upgrade head` / `current --check-heads` / `check`(ci.yml:327-355)

### 4. 旧システム・移行(legacy-analyst)

- 試合区分: 旧 `game.Kind`(任意 TEXT・初期値空文字 — legacy/research/data-layer.md:52,:154)。写像は付録D-4 の例示 3 件だけ(requirements:1242)。完全な写像表・空文字と自由記述の扱いは**不明**(TSK-479 / 移行の射程)
- 在籍区分: 旧データに列なし(data-layer.md:31-39)。移行は全員 `active`(requirements:383,:790)
- 移行バッチは未実装。権限は表単位 INSERT(contracts/authz/product/migration-batch-role.json:32-35)→ **定数列が DEFAULT なら移行バッチ側の追随は不要**(PostgreSQL の一般仕様からの推論・典拠なし)。`game_type_rule_defaults` は移行先 19 表の外

## 判断点(人間)

- **A. data-model.md を本タスクで触るか・ゲート**: ⚠ 項(:2021-2027)は「確定ゲートを要する」と書く。(a) 7.3 確定ゲートで v0.7(TSK-382 の v0.6 の後に直列) / (b) 7.6-3 前段の実装追随として PR レビュー(⚠ 項を是正済みの記録へ書き換えるだけ。ただし ⚠ 項自身の記述と TSK-475 裁定の当てはめに反する)/ (c) 本 PR では data-model.md を触らず、後続(TSK-382 マージ後)に回す — 3 案
- **B. 射程**: system 層 3 本だけ(カードどおり)か、admin 4 本・tenant 7 本まで含めるか
- **C. 「その他」のキー**: 本タスクでは決めない(TSK-479 の命名)。申し送りのみ

**【裁定 2026-10-06・山田正輝】**
- **A = (b) 実装追随で PR レビュー**。⚠ 項(:2021-2027)を是正済みの記録へ書き換えるだけにし、版は据え置く。**主キー `(key)` は残し、3-4 節の一意性の表(:399・:407)は変えない**。TSK-475 の裁定(7.3 への当てはめ)は今回は当てない。コードはコア領域として敵対レビュー・逐行確認を通す
- **B = system 層 3 本だけ**(カードの DoD どおり)。admin 層 4 本・tenant 層 7 本は別タスク **TSK-489**(https://app.notion.com/p/3f093b75e6878107beead6b336854d26)として起票した

## 未解決・申し送り

- 試合区分のキー名・旧 Kind の写像表(TSK-479・移行)
- U-M1 の計画書(um1 worktree の plan.md)に TSK-480 への言及が 0 件(依存表 :417 は「seed の別タスク起票」のまま)— U-M1 側の現行化は UM01 タブへ申し送る
- admin / tenant 層の同型の非拘束 → TSK-489 へ起票済み(2026-10-06)

## 裁定(エージェント報告・申し送りの食い違い)

- カード・申し送りの `data-model.md:396` は古い。現行は :407(システム固定)・:399(管理者管理)。:396 は 8-2 節の行(TSK-468 の 3-4 節更新でずれた — data-model:10)
- TSK-475 の裁定の位置は §4-3 でなく §4-5 :400-411(§4-5 という見出しは :384 と :416 の 2 つ)
- 定数列 + 複合 FK の前例は 0028 でなく 0005 / 0007。0028 は既存の `tenant_id` を使った複合 FK と、同名張り替え・事前検査の前例
