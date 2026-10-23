---
feature: mvp-rule-resolver-db-connection
status: active
承認: 済（PO委任によるCodex判断・隔離実DB接続のみ）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-rule-resolver-db-connection
created: 2026-10-23
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 固定段階A providerと公開resolverの実DB接続

## 1. 背景・範囲

合成Sessionで124件成功した公開resolverを、既存承認済みTSK550 step6の実PostgreSQLへ接続する。
固定supplier bc436803（#174/単一codec整数型是正済み）とconsumer89b57ee9（コード0ee701f1/独立2回目0）の2枝だけを
隔離mergeした6caee0e0b3ec232aa8a8d262ce3904820974c308を基線とする。元worktree/PRは編集しない。
候補環境の成功を正式develop・S4公開・U-G1保存成功へ広げない。

編集は既存backend/tests/db/test_stage_a_rule_candidates.pyと本plan/researchの3パスだけ。製品ソース・共通conftest・schema/DDL/ACL資産・凍結/認可契約は変更しない。
2枝の正式閉集合/7.7未反映は残り、checker拒否を成功へ読み替えない。製品HTTP/認証Cookie・RG1・game INSERT・UIは本単位の対象外。

## 2. 実装方針

既存_fresh_schema_databaseと正式advance_stage_a_from_s0でS3まで実DDL/ACL/配置する。S1 fixtureや手動候補関数導入を成功環境の代用にしない。
S3 publishable=Falseを保持し、公開可としない。実pitchlog_app roleでSQLAlchemy製品create_database_engineを使い、
実Session/_tenant_transaction/registry/固定SQL/関数/権限を通す。必要な注入はtransaction.create_database_engineへ同じ実engineを返すfactoryだけ。
Session/認可/DB応答を常時成功stubへ置換しない。DB・port・一時領域は使い捨てfixtureで分離、finallyでengine.disposeする。

接続設定は既存境界試験の隔離app role一時認証方式と明示PITCHLOG_DATABASE_URL/POOLED設定を使い、実.env/共有DB/運用秘密/署名鍵へアクセスしない。
既存make_tenant_contextによる試験専用発行証跡のexact TenantContextを使う。実API認証・Cookie・端末資格の成立を証明しない。
SQLAlchemyのcommit/rollbackイベント・別の実DB接続で観測し、実scopeの失効/tenant GUC非持越し・ロック保持/解放を確認する。

## 3. 影響する正本

反映なし。provider/consumerの受理済み契約と既存step6の検証時点を具体化する。SQL/ACL実値の追加はしない。
原子性の対象はresolverが使う実transactionの終結/ロックで、試合作成/新語彙/game INSERT全取消の証明はU-G1後続へ残す。

## 4. 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 正式S3 DB関数と公開resolver/実scopeを接続検証する | 正常UUID+5値/exactint/encode、他tenant・親大会不存在/無効の同失敗、上書き/割当拒否・fallbackなし、無効規則、実EXECUTE拒否又は実ロック競合のoutcome_unconfirmedを実測。成功scope中FOR SHARE保持と終了後解放、故障rollback・秘匿・再試行なし、GUC非持越しを観測。対象DB pytestと既存単体124を成功、backend/root Ruff/ty・差分検査。独立レビューへ固定HEAD/diffを提出し候補証拠を保全 |

## 5. DoDと検査

同じ実DB/実SQL/実scopeを通すことで単体の合成Sessionから証拠を進める。正式閉集合・7.7・正式DB供給/運用/S4は未完のまま。
既存fixtureのDB役割/認可/型資格と隔離環境を明記する。故障を検出したら必要な是正を具体化し、製品コードの無断追加や判定の書替えをしない。
対象DB/単体と静的検査だけを一度実施し、同じ入力の全件反復は避ける。既知の供給元正本差分を含むdefault計画同期は留保し、
本作業の比較は--base 6caee0e0で区別する。push/PR/正式ステップ完了・MVP完成の宣言はしない。

承認記録: 2026-10-23T14:18:56.999261+00:00、Codex主担当/root。対象plan SHA-256 8d2611a28e7b2f46d0d635477f7dc28dd345e59da4b07a2bcd7b8b8f27989b89、候補基線6caee0e0。独立/root/o5_final_reviewは可決P0=0/P1=0/P2=0。PO指示4/5/6/8/10に基づく実製品コードの隔離DB接合検証を承認する。共有DB・実API認証・S4公開・正式契約受理の代替ではなく、山田正輝の個別確認/署名としない。
