---
feature: ua1-auth-db-layer
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域         # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3ee93b75e687816ca0a8dc47a32d70d9
branch: feature/ua1-auth-db-layer
created: 2026-10-04
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-A1 β — 認証の DB 層(認証関数所有ロール・認証関数・関数種別の一般化)

## 1. 背景・目的

**Notion**: [TSK-468 U-A1 β 認証の DB 層](https://app.notion.com/p/3ee93b75e687816ca0a8dc47a32d70d9)(親 TSK-399)
**要件**: [FR-033](../../requirements/requirements-pitchlog-2026-07-22.md#FR-033) / [FR-035](../../requirements/requirements-pitchlog-2026-07-22.md#FR-035) / [FR-036](../../requirements/requirements-pitchlog-2026-07-22.md#FR-036) / [FR-037](../../requirements/requirements-pitchlog-2026-07-22.md#FR-037) / [NFR-011](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-011) / [NFR-014](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-014) / [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)
**条文の正**: `docs/design/data-model.md` **v0.4**(approved — PR #90。U-A1 α)
**調査メモ**: [research.md](research.md) / **詳細設計**: [design.md](design.md)

U-A1 は α(正本 — 完了)/ **β(本タスク — 認証の DB 層)** / γ = TSK-469(アプリ層・`TenantContext` の生成)/ δ = TSK-470(HTTP の入口)に分かれている。
**U-M1 が入口を開く段(ステップ 5 以降)は γ を要し、γ は β を要する**(U-M1 計画書の依存 6・R1)。β は #87(TSK-443)のマージを待つので、**計画を今つくり、#87 のマージ後すぐ実装に入れるようにする**。

**目的**: v0.4 の認証条文(3-2・3-4 実装待ち・8-1・8-2・8-3・8-6・12-3 不変条件 5)を DB 層で実装する。
**前提として、製品 authz 資産の閉じた集合を一般化する**(関数種別・拡張・スキーマ・ACL・件数・切り替え後の再導出 — research.md 4 節)。**人間の決定 B-1 により 1 本の PR で進める**。

## 2. スコープ

### やること

1. **資産基盤の一般化**(design.md 2 節): 関数種別 `definer`・拡張とスキーマの要素・取り外しの `PUBLIC` 復帰の限定・ACL と件数の導出化・製品状態のランタイム契約の `rederive` モード
2. **migration 0027**(design.md 4 節): `tenants.retired_at`・`tenants.name_normalized`(生成列)・正規化名の部分一意索引・認証主体の一意 2 本・トークンの複合 FK・事前検査・downgrade。ORM・schema manifest・スキーマ監査・移行バッチ用ロールの `UPDATE (retired_at) ON tenants`
3. **ロールと関数**(design.md 1・5 節): `pitchlog_auth_fn_owner`・スキーマ `authn` / `authn_crypto`・pgcrypto・認証関数 8 本と内部関数・付与先・所有ロールの表/列権限(4 表と `tenants`・`system_settings` の読み取り)
4. **計数の器**(design.md 7 節): 不変条件 ③〜⑥(具体設計は δ)
5. **試験**: 単体・越境・故障系・並行(6 節)と、最低要求 ②③④ の改訂
6. **正本の実装追随**: data-model.md 3-4 節の実装待ちの 2 行を主表へ移す(「実装」列を外す)・12-3 不変条件 5 の監査 8 件・12-8 の残件の行・派生資産(digest 2 か所・受入突合シート)
7. **露出の事実**: `exposure-facts.json` の典拠 3 件の差し替え(TSK-453 の残り)と `tenant_tokens.id` の秘密の列への追加

### やらないこと

| 対象 | 送り先 |
| --- | --- |
| 提示値の署名と検証・`TenantContext` の生成・署名鍵・アプリのログ | **γ = TSK-469** |
| HTTP の入口・Cookie と CSRF・レート制限の具体設計の反映・設定値の本番投入・配備先の確認 | **δ = TSK-470** |
| 初期発行・リセット・無効化・管理者ログインの**呼び出し側**(管理関数)と管理者資格情報のハッシュ | **U-A2**(β は限定関数を作って管理関数所有用ロールにだけ付与する) |
| 旧ハッシュの再利用・旧 `team` の重複の扱い | **移行タスク** |
| 制約違反の詳細の秘匿(3-4 規則 3)・トークン検証を通らない経路の有効性検証・`code_hash` の非露出の実装 | **担当が正本に無い**(research.md 1 節)— **7 節 J-1 で受け取り先を決める** |
| 実スキーマへの適用 | **TSK-344** |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/data-model.md` | **実装追随(版は上げない)**: 3-4 節の実装待ちの 2 行を主表へ移し「実装」列を外す(表の注記を整理)/ 12-8 節の残件の行(TSK-468 を解消済みへ)/ 変更履歴 1 行 | PR レビュー(7.6-3 前段) |
| `docs/README.md` | 索引の data-model 行 | PR レビュー |
| 派生資産(正本ではない) | `contracts/authz/shared-preconditions.json`・`contracts/db/schema-manifest.json` の digest / 受入突合シート(`docs/features/orm-schema-migration/acceptance-sheets/`)の再生成と期待行数 | PR レビュー |
| 運用文書 | **反映なし**(配備手順は δ) | — |

## 4. 実装方針

### 重さ分類の根拠 — コア領域

`contracts/authz/*`・`backend/src/pitchlog/authz/*`・`backend/migrations/*`・`docs/design/data-model.md` はいずれもコア領域の paths に一致する(テナント分離ほか)。認証関数はテナント分離の入口を作る。**ADR-001 により敵対レビュー + 人間の逐行確認**。

### 待ち合わせ(**ステップ表の外のゲート**)

- **G-1**: **#87(TSK-443)が develop へマージされていること**。マージ後に develop を取り込んでからステップ 2 以降に入る(ステップ 1 は実測だけで待たない)
- **G-2**: **β のマージは #87 より後**(#87 の S を動かさない — research.md 2 節)

### 衝突面とマージ順

| 相手 | 衝突面 | 扱い |
| --- | --- | --- |
| #81(236・`appendix-e-golden-vectors`) | `contracts/authz/shared-preconditions.json`(別の行)・台帳・索引 | 行単位で解決。先にマージした側の後で取り込む |
| TSK-344(承認済・#87 待ち) | 最低要求④の試験(`test_product_authz_cross_cutting.py:543-567`)・DDL 資産の digest | **β が先なら TSK-344 の判定記録の基準が動く** — 7 節 J-2 |
| TSK-475(在籍区分の seed) | `system_vocabularies` の seed の置き場(migration 不可は同じ) | 重ならない見込み |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **実測で正規化関数の方式と計数の直列化手段を確定する**(design.md 3・7 節)— 使い捨て DB で案 A(migration の `IMMUTABLE` 関数 + 生成列)が移行バッチ用ロールの INSERT で関数 EXECUTE を要るか、生成列の deparse が `alembic check` で差分を出すか、計数の行が無い場合の競合を何で直列化するかを測り、design.md に結果と決定を書く | 測定の手順・値・決定が design.md にある / 差分が `docs/` だけ |
| 2 | **develop を取り込み(G-1)、core-areas へ新しい paths を登録する**(`authn` の関数本体・新しい試験ファイル)。`tests/test_core_guard.py` に正例・負例 | core-guard green / `test_core_guard.py` の新しい行が正例で一致し、外すと red |
| 3 | **資産基盤の一般化 1 — 種別と要素群**: 関数種別 `definer`・拡張とスキーマの要素・適用手順への組み込み・取り外しの `PUBLIC` 復帰を `migration_trigger` に限る・関数 ACL の引数形の導出(`asset_spec.py`・`product_catalog.py`・`product_provisioning.py`・`product_function_acl.py`) | 既存の製品 authz の試験(非 DB・DB)が green / **取り外しで `definer` を `PUBLIC` に戻す変異が red** / 資産に `definer` が 0 件でも挙動が変わらない |
| 4 | **資産基盤の一般化 2 — 閉じた集合の導出化**: ロール集合・列 ACL・表 ACL・保護関数と migration 関数の件数を資産から導く(`scripts/check_authz_catalog.py` と試験 6 か所)。**資産と実カタログの照合は残す** | 既存の検査・試験が green / **資産から 1 要素を消す・実カタログに 1 要素を足す変異がそれぞれ red**(導出がトートロジーでない) |
| 5 | **資産基盤の一般化 3 — 製品状態のランタイム契約の `rederive`**(`runtime_contract_generator.py`)。資産の変更から導出欄を再計算し、7.7-2 の受理記録の雛形を出す | `rederive` が無変更なら差分 0 / 関数を 1 つ足した資産で導出欄が変わり P4 が green に戻る / 生成器の試験 green |
| 6 | **migration 0027**(design.md 4 節)と ORM・schema manifest・スキーマ監査(7 → 8・27 → 29・4 → 5)・`test_alembic_migrations.py` の認証主体 4 件の是正・移行バッチ用ロールの `UPDATE (retired_at) ON tenants`。**data-model.md 3-4 節の実装待ちの 2 行を主表へ移す** | `alembic upgrade head` / `downgrade base` / `alembic check` が green / 事前検査の負例(重複・64 文字超・主体の重複・トークンのテナント食い違い)で migration が止まり行が変わらない / `test_schema_manifest.py`・`test_schema_audit.py`・`test_tenant_models.py`・移行バッチ用ロールの試験 green |
| 7 | **ロールと拡張とスキーマ**: `pitchlog_auth_fn_owner`・`authn`・`authn_crypto`・pgcrypto・所有ロールの表/列権限(資産) | 実 DB で: ロール属性(`NOLOGIN`・`BYPASSRLS`・所属 0)/ 権限が宣言と exact / `authn_crypto` の関数を `PUBLIC`・`pitchlog_app`・移行バッチ用ロールが実行できない / 移行バッチ用ロールの関数 EXECUTE 0 件が維持 |
| 8 | **認証関数(アプリ用)**: `login` / `verify_token` / `logout` / `change_password` / `password_policy_ok` と計数の器(design.md 5・7 節)| 6 節の単体・越境・故障系・並行の該当行が green |
| 9 | **限定関数(管理関数所有用ロールだけ)**: `issue_initial_password` / `reset_password` / `revoke_tenant_tokens` / `record_admin_login_failure` | 6 節の該当行が green / `pitchlog_app` から実行すると `42501` |
| 10 | **最低要求 ②③④ と構成検査の改訂**: ④ の「0 件」を資産で宣言した `definer` 関数の集合との exact へ・認証関数に ②③(`PUBLIC`・信頼しない LOGIN ロールが実行できない / 一時スキーマで乗っ取れない)・名前解決経路の非注入・スキーマ検査 | 該当の DB 試験 green / ④ の集合から 1 件外す変異が red |
| 11 | **ランタイム契約の再導出と受理記録**(ステップ 5 の `rederive`)・**露出の事実**(典拠 3 件の差し替え・`tenant_tokens.id` の追加)・**DB ログにバインド引数が出ない**ことの実 DB 確認 | `check_authz_catalog.py` / `check_tenant_boundary_bypass.py` / 凍結基準の検査が green / 受理記録が 7.7-2 の形 / ログ試験 green |
| 12 | **正本の実装追随と派生資産**: data-model.md 12-8 の残件の行・変更履歴・索引 / digest 2 か所 / 受入突合シートの再生成(判定は内容一致で引き継ぎ・新規行は人間の判定) | `check_docs_status.py`・`check_shared_preconditions.py`・`test_schema_manifest.py`・`test_orm_acceptance_sheets.py` green |
| 13 | **クローズ処理**(`/pr`) | 3 節の宣言と PR 内容が突合 / CI 全ジョブ green(core-guard は人間の逐行確認後)/ 12-4: **対象入口なし** |

## 5. DoD(受け入れ基準)

- [ ] パスワードの保存形式が data-model.md v0.4 8-2 節と一致する(pgcrypto `bf`・コスト 12・DB 内だけで生成と照合・ハッシュを外へ返さない)
- [ ] NFR-019 の越境テスト(DB 層): 認証関数を経由しても他テナントの認証情報・トークンへ届かない / `function_only` 4 表への直接アクセスが `42501` / 付与先が宣言どおり / 一時スキーマで乗っ取れない / 名前解決経路に注入できない
- [ ] v0.4 の β の義務(research.md 1 節)がすべて試験で覆われている — とくに: 世代繰り上げの限定関数 / 失効トークンを復活させない(並行) / PW 変更の対象を自分の主体に限る / リセットでの世代 +1 / 退役していないテナントだけを解決 / 正規化の単一性 / 72 バイト超の受理 / 未設定の有効期限で発行も延長も拒否 / 失敗経路の一様性
- [ ] 資産基盤の一般化が後続の単位(U-A2・U-C1・U-C3)の使える形で、変異試験で守られている
- [ ] data-model.md 3-4 の実装待ちの 2 行が主表へ移り、manifest と全数一致
- [ ] `core-areas.json` への paths 登録を本 PR で行う
- [ ] シークレットをハードコードしない・ログに出さない(NFR-014 — P0)。DB ログにバインド引数が出ない
- [ ] `backend/tests/conftest.py` の差分が 0 行
- [ ] pytest / ruff / ty green
- [ ] 横断: 物理削除しない / テナント分離 / 自動エスケープ

## 6. テスト計画

| 種別 | 内容 | ステップ |
| --- | --- | --- |
| 単体(DB) | ログイン成功・失敗(存在しない名前・誤 PW・無効テナント・退役テナント・未設定の有効期限)の戻り値が一様 / ポリシーの境界(7・8 文字・英字なし・数字なし・72 バイト超を受理)/ 検証(期限切れ・世代違い・無効テナント・テナント食い違い)/ 延長 / ログアウト / PW 変更(現行 PW の誤り・未入力で何も更新しない・成功で世代 +1 と日時)/ 限定関数(リセット・世代繰り上げ・主体なしで成功)/ 計数(失敗がコミットされる・ロック中も既存トークンが有効) | 8・9 |
| 越境 | 他テナントのトークン ID で検証・ログアウトできない(ID は発行の応答以外で返らない)/ PW 変更で別テナントを指せない / `function_only` 4 表への直接アクセスが `42501` / `authn_crypto` を実行できない | 7・8・10 |
| 故障系 | 計数の更新の途中で失敗してもロールバックで計数が消えない / 事前検査の負例で migration が止まる | 6・8 |
| 並行 | 同じ単位への同時の失敗を数え落とさない / ログアウトと検証の並行で失効が勝つ | 8 |
| 構成 | ロール属性・権限 exact・`search_path`・非注入・最低要求 ②③④ | 7・10 |
| 変異 | 取り外しの `PUBLIC` 復帰・導出化した集合・④ の集合 | 3・4・10 |
| ログ | 実 DB でバインド引数が DB ログに出ない | 11 |

## 7. 人間の判断を仰ぐ事項(承認時)

| # | 論点 | 推奨 |
| --- | --- | --- |
| **J-1** | **担当が正本に無い 3 件**(制約違反の詳細の秘匿 / トークン検証を通らない経路の有効性検証 / `code_hash` の非露出の実装)の受け取り先 | 秘匿 = δ(応答層)/ 検証を通らない経路 = U-A2(管理経路)/ `code_hash` = U-C1(招待の所有単位) |
| **J-2** | **β と TSK-344 の順序**(β が先だと TSK-344 の判定記録の基準と④の前提が動く) | **TSK-344 を先**(β は #87 の後・TSK-344 の後にマージ)。β の実装は並行で進める |
| **J-3** | **不変条件 ② の割当**(α の design.md は β の器を ③〜⑥、plan.md は ② を β・γ に置く) | **② の DB 側(計数と判定の一様性)は β、応答の一様性は δ** |

## 8. リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | 一般化の範囲が広く、コア領域の大きな PR になる(人間の決定 B-1) | ステップを細かく切り、各ステップに変異試験を置く |
| R2 | #87 のマージ時期が読めない | ステップ 1 は待たずに進める。計画承認まで並行 |
| R3 | 正規化関数の方式が実測で決まらない | 案 B(生成列 + 同じ式の照合試験)へ落とす |
| R4 | 凍結資産(ランタイム契約・base-allowlist)の取り込み費用 | 受理記録はステップ 11 の 1 回だけ・マージ直前の develop で |
