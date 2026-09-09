---
date: 2026-09-09
topic: ORM 導入(SQLAlchemy 2.x・Alembic)と models・migration — TSK-343
branch: feature/orm-schema-migration
---

# 作業ログ: 2026-09-09 ORM 導入と models・migration(TSK-343)

## やったこと

- **/task-start**(2026-09-09): Notion [TSK-343](https://app.notion.com/p/3d593b75e68781469990ca4e61fca9d2) を取得し、
  ブランチ `feature/orm-schema-migration` + worktree `../pitchlog-worktrees/feature-orm-schema-migration` を
  `origin/develop`(`1424d67`)から作成。計画書雛形 `docs/features/orm-schema-migration/plan.md` と本 worklog を作成。
- **開始条件の充足を確認**: TSK-342 の成果 `docs/design/data-model.md` は frontmatter `status: approved`
  (確定ゲート 13 周・PO 承認 2026-09-09)。PR #50 が develop へマージ済み(`1424d67`)。
- **/investigate**(2026-09-09): 調査サブエージェント **4 並列**(既定 3 本 = spec-checker / legacy-analyst /
  decision-tracer + 衝突 5 箇所の実測 1 本)。結果を
  [`docs/features/orm-schema-migration/research.md`](../features/orm-schema-migration/research.md) へ統合した。
  **エージェント報告の食い違い・誤りは原典を自分で読んで 7 件裁定した**(research.md 6 節)。
  主な裁定: ① 88 列の正本は `docs/legacy/research/data-layer.md`(`docs/design/data-layer.md` は**存在しない**)
  ② 接続 URL の統一で配線検査が壊れるという「深刻度 高」の報告は、**範囲を切れば消える罠**
  (テスト用 DSN は `psycopg.connect()` / `conninfo_to_dict()` に渡る libpq conninfo で、
  SQLAlchemy URL 形式 `postgresql+psycopg://` を入れてはいけない)
  ③ NFR-019 の種別は **4 種**((a) 一致性 /(b) 越境 /(c) E2E /(d) 同期故障系)で「単体」は列挙に無い。

## 決定

- **slug は `orm-schema-migration`**(タスク名由来の `data-model-schema-orm` は使わない)。
  **理由**: `docs/features/data-model-schema-orm/plan.md` は TSK-342 が使用済みで、`scripts/feature_status.py` は
  plan の期待 slug をブランチ名から導出する(`expected_feature_slug` — `feature/<slug>` の `<slug>`)ため、
  同名にすると現在地導出が「plan 重複」になる。
- **重さ分類 = コア領域(テナント分離)**。Notion タスクの制約欄どおり — `sol xhigh`・敵対レビュー・
  人間の逐行確認必須(PR 作成者以外)。frontmatter に反映済み(根拠は計画書 4 節で明記する)。
- **`tests/test_ci_wiring.py:1272` は 10.1 改訂と同一 PR・同一コミットで運ぶ**(人間決定 2026-09-09)。
  **理由**: Notion タスクが「② 依存追加は ① と同一コミット必須」と定めており、分けると依存追加の瞬間に
  旧形の assert が必ず落ちる red の中間コミットができる。設計書 6.1 の段階実装は各ステップに合格条件を
  要求するので、その中間状態には合格条件が書けない。裁定 `R-2`(models と 10.1 改訂を同一タスクに保つ)とも整合。
  → **1 コミットの内容** = 設計書 5.1 の ORM 留保解除 + 10.1 の「ORM は入れない」改訂 +
  `backend/pyproject.toml`・lock の依存追加 + `test_psycopg_is_exact_product_dependency_without_orm_packages` の更新。
- **/investigate**(2026-09-09)の結果を受けた人間の裁定 4 件(**2026-09-09・山田正輝**)。
  詳細な典拠は [research.md](../features/orm-schema-migration/research.md) の該当節を参照する(本 worklog に複製しない)。

  | ID | 事項 | 裁定 |
  | --- | --- | --- |
  | **`Q-1`** | 設計書 5.1・10.1 の改訂のゲート水準(`R-5` の受け皿が消滅) | **(A) 設計書自身を `/finalize-doc` で回す**(7.6-3 後段)。**版を v1.14 へ繰り上げる** |
  | **`Q-2`** | 「型を損失なく受け取る境界」の定義が正本に無い | **本タスクで線を引く** — 既存の型分離の型(**原本事実をそのまま保持 + 解決結果は別の nullable 列**)を 88 列側へ一般化する |
  | **`Q-3`** | DoD の 2 条件(exact-set テスト / `downgrade`)に典拠が無い | **両方維持し「正本の典拠なし・本計画の自主基準」と明記する** |
  | **`Q-4`** | マージ順序 | **TSK-348 → TSK-317 → 本タスク**(当初の原案どおり) |

- **`Q-1` は裁定 `R-5` の変更である**(記録しておく)。`R-5`(TSK-335・2026-09-08)は
  「**版は上げず**、差分を確定ゲートの敵対レビュー対象に含める」という折衷だったが、
  相乗り先の `data-model.md` の `/finalize-doc` が TSK-342 の approved 化で閉じたため受け皿が消滅した。
  **本裁定は「版は上げず」を外して 7.6-3 後段(版繰り上げ + 7.3 の確定ゲート)を採る**もので、
  `R-5` より**厳しい側**へ寄せた判断である。
  → **帰結**: 設計書の変更履歴表へ **v1.14** 行を追記し、`docs/README.md`(索引)を現行化する。
  `/finalize-doc` の**反映周コミットは `反映<r>周目` 記法**(ステップ記法を付けない — 設計書 6.1)。
- **`Q-4` の副作用(有利な方向)**: 本タスクが最後になるので、**TSK-317 のマージ済み `conftest.py` の上に
  自由に追記できる**。実衝突として唯一残っていた `backend/tests/db/conftest.py` の競合が**順序で解消する**。
  `.claude/core-areas.json` も TSK-317 の改訂 3 と逐次になるので競合しない。

## 未決・次の一歩

- **本タスクは /plan までで止める**(人間の指示 2026-09-09)。**実装フェーズへ入らない**。
  `Q-4` の裁定により、**実装着手は TSK-348 → TSK-317 のマージ後**。
- **次の一歩: 人間が `/plan` を実行する。** `/plan` は `disable-model-invocation: true` のため
  Claude 側からは起動できない(スキルの手順を代替実行することも禁じられている)。
  計画書に落とすべき材料は本 worklog の「決定」節と research.md に揃っている。
- **計画書で明示的に書くこと**(人間の指示 + 上記裁定):
  1. 競合 6 箇所の**所有**を 3 節「影響する正本」と**別枠宣言**で明記(申し送りの 5 箇所 + `.claude/core-areas.json`)
  2. `tests/test_ci_wiring.py:1272` は **10.1 改訂と同一 PR・同一コミット**(理由を 4 節と実装ステップ表へ)
  3. **マージ順序 = TSK-348 → TSK-317 → 本タスク**(4 節)
  4. `Q-1`〜`Q-3` の裁定と、`Q-1` が `R-5` の変更である旨
  5. **本タスクの裁量 3 点**の決定 — Alembic の**置き場**(論点 15)/ **`D5` の「経路と種別の一致」の強制機構** /
     **ADR 起票の判断**。加えて **`D3` の後退禁止の機構**(条件付き `UPDATE` か `BEFORE UPDATE` トリガ)
- **競合 6 箇所**(5 箇所は人間の申し送り・6 番目は本調査で判明):
  `tests/test_ci_wiring.py:1272`(改訂 3 とのみ衝突)/ 設計書 10.1(**衝突なし** — TSK-317 が手放し済み)/
  `backend/tests/db/conftest.py`(**唯一の実衝突**。`Q-4` の順序で解消)/
  `backend/tests/db/environment-expectations.json`(**衝突なし** — TSK-317 の合格条件が「差分 0」)/
  **`backend/uv.lock`**・`backend/pyproject.toml`(**衝突なし**。なおルート `uv.lock` も実在するが ORM 検査の対象外)/
  **`.claude/core-areas.json`**(申し送りに無い潜在衝突 — 両者が同じ `tenant-isolation.paths` を編集予定)
- **依存 TSK-344**(越境テスト再実行ゲートの実行 — 実スキーマ適用後の再実行・TSK-342 の裁定 `A-2`)。
  `docs/design/data-model.md` 12-4 節(2439 行)の**通過条件は「① RLS のポリシーとロールの DDL が実スキーマへ
  適用されている ② その実スキーマに対して越境テストが green である」**(原文を確認済み)。
  **① の「実スキーマ」は本タスクの migration の成果**であり、**RLS の DDL 自体は本タスクの射程外**(裁定 `A-2`)。
  したがって TSK-344 は **本タスク(スキーマ)と TSK-317(RLS DDL)の両方**が入らないと通過判定ができない。
  → マージ順序の決定に直結する。
- **関係タスクの実状**(Notion 実測 2026-09-09): TSK-342 = 完了 / TSK-348(`data-model.md` v0.2 の改訂ゲート・
  search_path 契約の是正 1 件)= 未着手だが worktree `feature/data-model-v0-2` は実装完了・/pr 前 /
  TSK-317 = 進行中(7/21)/ TSK-344 = 未着手 / TSK-250 = 進行中。
