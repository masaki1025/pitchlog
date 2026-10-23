# 固定providerと公開resolverの隔離実DB接続候補

2026-10-23、rootのPO委任承認 `97946ea7e0b066448a4a634cb469ca0c630623b5` に従い、計画の1ステップだけを実施した。supplier `bc436803902a9cde2b54e6a72636acbe522e9e20` とconsumer（コード `0ee701f10f29ce56d192536f70e8f50b7c56649d`）の2枝隔離merge `6caee0e0b3ec232aa8a8d262ce3904820974c308` を継承する。

変更は既存 `backend/tests/db/test_stage_a_rule_candidates.py` と本researchだけ。製品ソース、共通fixture、plan、正式DDL/ACL/認可/閉集合/7.7資産、元worktreeは変更しなかった。

## 実接続と資格の範囲

新5試験に閉じた `public_resolver_database` fixtureは、既存 `_fresh_schema_database` と正式 `advance_stage_a_from_s0` でS0→S3の実revision/配置/認可を適用する。`completed_stage=S3` / `publishable=False` を確認し、S1 fixtureや手動候補関数適用で代用していない。隔離DB内に2テナント・各大会親・無効親を準備し、試験専用の一時passwordをapp roleへ付与した。

既存の正式app接続方式どおり `PITCHLOG_DATABASE_URL`（local/sslmode=disable）と `PITCHLOG_DATABASE_POOLED=false` を明示し、実session_user/current_userがともにpitchlog_appと照合した。製品 `create_database_engine()` を呼び、transactionのengine factoryだけを同じ実engineへ接続した。実Session、`_tenant_transaction`、製品registry/固定SQL、DB関数、app role/権限・engineのcheckout真正性検査は置換していない。engineはfixtureのfinallyでdisposeした。

TenantContextは既存allowlist内の `test_authz_tenant_context.make_tenant_context` による試験用発行証跡を持つexact型である。実API認証・Cookie・端末資格の成立を証明しない。S3準備のadmin接続/データseedは環境準備であり、製品の大会登録/試合作成を通過した証拠ではない。

## 検証した5ケース

1. 実公開resolverの正常UUID+5値/6-key encode・整数exact型。scope中は別接続の規則行FOR UPDATE NOWAITが拒否され、成功scope終了後には取得できる。失効handleの再利用は拒否する。
2. 他tenantの大会親・存在しない親・無効親は同じrule_not_availableでrollback。別tenant自身の親は成功し、tenant束縛を維持する。
3. override指定と実大会割当行がある場合はstage_a_unsupportedでrollbackし、全体既定へfallbackしない。
4. 管理側で不整合にした実規則行をinvalid_ruleとして拒否・rollbackする。規則行lockは終了後に解放する。
5. 実appの関数EXECUTEを取り消し、実SQL権限拒否をoutcome_unconfirmedへ写す。SQLAlchemy rollbackイベント、公開例外/traceback/ログの内因秘匿、実関数SQL試行1回を確認する。

成功/失敗の実transaction終了はSQLAlchemyのcommit/rollbackイベント、lock保持/解放は別の実DB接続、tenant GUC非持越しは実app接続の再checkoutで観測した。結果や認可を常時成功stubへ写す処理はない。

## 隔離・cleanup

外側にも既存disposable factoryで専用管理クラスタを1個起動し、既存autouseのadmin/tested role用DSNを明示供給した。`verify_connection_identities` を無効化せず、実認証ユーザー照合を維持した。新5件は各自のinnerクラスタ1個ずつで、outerとの最大同時稼働は2個。既存26件の独立起動/後始末も既存fixtureへ委ねた。各portはDockerのloopback動的割当、pytest一時領域は本実行専用のTemporaryDirectoryへ分離し、実行後に除去した。

内外のコンテナは各factoryのfinallyでvolumeごと削除し、pytest終了後にdisposable authzコンテナ残数0を確認した。資格文字列/DSN/秘密はログ・本記録へ出していない。共有DB、.env、運用秘密、署名鍵にはアクセスしていない。

## 検査結果

- 実測DB版: **PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)**。既存fixtureの固定イメージを使用した。
- 専用一時runnerから既存factoryで管理用クラスタ/DSNを供給し、`pytest tests/db/test_stage_a_rule_candidates.py tests/test_function_operations_boundary.py -q --basetemp <専用一時領域>` を通常backend環境で実行。**155 passed / 87.46s / exit0**（DB既存26＋新5、単体124）。失敗・skipなし。frontend/nodeの追加setupは不要だった。
- 初回静的検査で追加importの整列と長いSQLリテラル3行をRuffが指摘。対象ファイルだけ整理・改行し、製品や検査規則を変更せず解消。backend対象Ruff format・全backend Ruff/ty、root Ruff/ty、空白検査は成功。root Ruffには既存test_core_guard docstring警告1件、終了0。
- 計画同期 `--base 6caee0e0` はexit0。default origin/develop比はsupplier由来の5正本（docs/README、data-model、product-authz-surface、deployment、requirements）未宣言でexit1。本単位の正本変更ではなく、計画・検査を緩和せず留保した。
- 対象試験ファイルSHA-256: `f0da4cc9cd35bc7ce610511c8565f39131c8d60efb0e664d55e51c76d94bf97b`。

この候補は実DBのresolver transaction終結とlockを検証したもので、正式閉集合/7.7受理、S4公開、実API認証、RG1、game INSERT/新語彙を含む全取消、実画面/reload、正式step5/6完成やMVP完成を宣言しない。次は固定差分の独立コードレビュー。push/PR・公開は未実施。

## 独立コード・実DB再実行

2026-10-23T14:55:35.046773+00:00、候補作成非関与/root/o5_final_reviewは可決P0=0/P1=0/P2=0。対象7af797c73e98136356d2f836d268a27111c51b48/base97946ea7、binary full-index差分8b20f65beab05118168f22aa3123c922e9ec114e35a8795e61e363f66d1556e8一致。指定2paths・fixture・identity検査を読み、PG17.11の別一時資格/動的port/専用一時領域で155 passed/86.32s/exit0を独立再実行、残存対象コンテナ0・tree cleanを確認。DSN/資格出力なし。正式閉集合/7.7/S4/実API認証/RG1/game INSERT/UIの未達は継続。後発差分は本記録だけで、独立再実行を正式develop成功へ拡張しない。
