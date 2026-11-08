---
feature: mvp-interference-physical-sql
status: active
branch: fix/mvp-interference-physical-sql-20261109
base: 1f08dad11e054a29cc44e770ccc22f5438fbdc93
---

# 妨害の物理証拠 SQL 修復

2026-11-09、実画面 INT-02 の最初の保存が `prepare_play_prefix_projection` の SQLSTATE 42703 で停止した。生成本文の外側 admission 3 箇所は `m` がスコープ外であり、内側物理走者検査 3 箇所とは別式が必要である。root の既 MVP 委任により、この実停止点の限定修復を進める。旧失敗・実 DB 未成功の区別を維持する。

| ステップ | 編集所有 | 完了条件 |
| --- | --- | --- |
| 1 | `backend/src/pitchlog/authz/interference_evidence_sql.py`、`backend/tests/test_interference_evidence_sql.py`、本計画 | 内側の元走者 `m` と物理 `r` の既証拠を保持し、外側 3 箇所は各 source runners と物理 `r` を明示結合した閉式にする。親 hash/宣言と他 78 本文を保持し、旧打球と未知・欠落の負例を追加する。 |
| 2 | `backend/tests/db/test_interference_screen_e2e.py`、新 `backend/tests/db/test_interference_sql_scope.py` | 正本 `input_vocabulary_v1.json` の secondary 3 語を UI 前の管理語彙 fixture に供給する。生成された内外 6 式の SQL スコープを製品配置と独立の owned DB EXPLAIN で検査し、実画面保存とは区別する。 |
| 3 | cache packet、本計画 | before/after SHA、生成本文全差分、純検査、未実施の PG/画面を封印して root に渡す。正式 catalog・manifest・正本・root main は root が直列配置する。 |

PG/browser は root の共通 lock 調整まで開始しない。認可、nonce、owner、ACL、拒否順、物理行全値、旧操作の範囲は変更しない。
