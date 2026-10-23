---
feature: mvp-rule-resolver-registration
status: active
承認: 済（PO委任によるCodex判断・公開resolver登録）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-rule-resolver-registration
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 公開規則resolverの正式登録接続

## 1. 背景・目的

TSK-550（[親計画](../ux1-fr014-rule-resolution/plan.md)のステップ4〜6）とFR-014の既採用段階Aを、正式developへ接続する。規則ID+5値の単一codec、固定関数operation、公開resolver/4失敗・同一scopeと、検証済み実DB接合を再利用する。試合作成HTTP/INSERT・RG1を別責任に保ち、部品の供給不足を解消する。

実baseは31194a39c9083bbef6c14bde19c24a3e49d09f2e。既存承認済みoperation/service/DB計画の固定候補f5371ee35955ed9e351b29a55682b2c6d378d3f1を通常mergeし、手動競合0の3da4e441028af25cdfcc30b271a3b55a4dc4a07aへ隔離組立した。旧173履歴を含めない。組立は同じresolver供給単位だけで、既存枝・レビュー・保全物を保持する。

## 2. スコープ

候補sourceは組立済みの`backend/src/pitchlog/repositories/{function_operations,operation_registry,rule_resolution}.py`、既存`backend/tests/{test_function_operations_boundary.py,db/test_stage_a_rule_candidates.py}`。原固定候補から意味・byteを変えず再利用する。単一codecは既に正式174のものを保持する。

新規編集は次に限定する。

| パス | 差分 |
| --- | --- |
| contracts/tenant_boundary/base-allowlist.json | 完全修飾_build_stage_a_rule_statementだけのSELECT許可/signature/正例fixture。既存全許可と正例の拒否を維持 |
| contracts/tenant_boundary/repository-contract.json | product_function_operation_idsへRULE:resolve_stage_aを1件追加。他全fieldを保持 |
| backend/src/pitchlog/repositories/repository_contract.py | JSONから既存canonical digestと全生成fieldを決定的に追随 |
| tests/fixtures/tenant_boundary/positive/pitchlog/repositories/rule_resolution.py | exact factory/signature/SELECTだけの正例 |
| backend/tests/test_authz_repository_contract.py | 全生成field/固定関数ID/既存RG1/実registryのexact対応を検証 |
| tests/test_check_tenant_boundary_bypass.py | 新正例と別module/署名/関数/任意SQL・未登録拒否を検証 |
| 凍結9資産/外部8の実照合 | 既存方式で完全before/afterを導出。上記2JSON以外にrevision/digest/corpus追随が必要なら、実差分根拠を固定して同じ単位で扱う。意味fieldの拡大はしない |
| contracts/tenant_boundary/history-snapshots/*、tests/fixtures/frozen-archive-cases/manifest.json | rootの実新PR受理後、必要で実baseにない参照分だけ追加。比較元snapshot/historyは不変 |
| docs/features/mvp-delegated-core-review/policy.json | 実新PR番号/本branchの1組だけtargetsへ追記。既存authority/失効/検証を保持し独立レビュー |
| 本feature plan/research | 対象版/結果/旧全レビュー系列/未完の記録 |

新DB権限・migration・関数body・認可catalog・route/matrix・RG1・HTTP/create・T1/T2・大会割当/上書きは変更しない。stage_a_startupのS3/publishable=Falseを成功へ変えない。初期付与の正常置換とread登録は別単位、共有正式資産の受理はrootが直列化する。

## 3. 影響する正本

反映なし。既存TSK-550段階Aの意味・公開型・4失敗・scope境界と既確定正本を変えず、登録不足を実装追随する。旧親9段階・元レビュー回数を維持し、本2段階で全体完了を認定しない。source/実行試験/新正例は実baseの既存core globで全て捕捉されることを確認済み。新しいguard宣言/JSONは不要であり、検出/拒否条件を変更しない。

## 4. 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 固定operation/公開resolverのmetadata登録・全field生成・正負例を接合 | 正確な1factory/1function IDを実sourceへ対応させ、既存RG1/DML/tenant注入/単一codecを保持。未受理候補として局所検査を実行、正式履歴赤を成功にしない。sourceを含むDraft PRで実番号を取得する |
| 2 | 実新PRの完全7.7受理と必要snapshot/policy対象を反映し最終確認 | 正常初期付与PR等の実統合後、実baseのprefixと全snapshotを保持して完全9資産/8外部を再導出・非作者照合・root委任受理。実IDの単一rowだけを追加。最終HEAD/diff/policy/履歴を非作者レビューし、GitHub実2親mergeのguardと全必須CI成功後に通常merge |

source候補の隔離実装を前PR統合待ちの一律条件にしない。正式受理は実統合後の実baseで直列に行い、無関係な基線移動で意味を再裁定しない。新番号/承認者を仮入力しない。既存受理行・旧外部snapshotを差し替えない。ステップごとに1commitし、rootが個別指示した1段階だけ実施する。

## 5. DoD・提供境界

正式版で固定RULE:resolve_stage_a operationと公開resolver/単一codecを呼べる状態を作る。4失敗・同一scopeのrollback/非漏洩を維持する。旧operation81、service124、実DB155成功・非作者各0指摘と後発差分を区別して記録し、旧成功を新版の完走としない。試合作成、RG1安全解除、S4運用公開、開始/1球/MVP全体は後続に残す。人間署名や山田正輝の逐行確認を代記しない。

## 6. 検査

backendの既存function_operations_boundary/authz_repository_contractとrootのbypass正負例を実行し、生成全field/実registry/既存RG1を突合する。静的Ruff/ty・docs/plan-sync・diff検査。実DB試験は既存使い捨てPG17.11/正式S3/実app roleだけを使い、必要な接合/故障を検証する。運用鍵・TLS新発行なし。.env/秘密/共有DB/legacy/P6封印へ触れない。

最終必須CIでbackend/root全件を確認し、同一sourceの長い全件を不用意に並列反復しない。core履歴predicate/全既存paths/実PR2親merge/最終証拠を固定する。CI失敗/skip/取消は原結果を保持。正式checkerの赤は原因別に残し、検査除外や固定成功で通さない。

計画承認: 2026-10-23T17:28:53.385803+00:00、Codex主担当/root、PO委任4/5/6/7/8/10。対象plan6e7e113057fcb56de6596e069fa1ba805ed4952c4910008d355e5fbfdae6540d/research50fd77c6b6f28e54c909257231f6684d3d4f02b02bb60fa7dd346d9d66accbc5を、非作者/root/resolver_ledger_plan_reviewの第1回全文計画レビュー可決0/0/0に基づき承認する。既存固定sourceの意味・全正本を保持した正式登録不足の解消だけを対象とし、指定した1ステップのみ実施する。実新PR/完全7.7/最終非作者レビュー・CIを別条件とし、山田正輝の本人逐行確認/署名を代記しない。


実175統合後の正式baseはa10bcd5e、製品差分を含む実Draft PRは#181 / feature/mvp-rule-resolver-registration。旧source/レビューを保持した通常merge50c1fcd9でmain全登録/28履歴/204snapshotを保全し、candidate revision36→37/25→26の完全9/8値をこの実baseから再導出する。policy targetsは実PR181/本branchの1組だけ追記し、他全対象/authority/期限/拒否は保持する。更新flagなし最終検査/正式受理/最終非作者/必須CI/通常統合が揃うまでは未完。
