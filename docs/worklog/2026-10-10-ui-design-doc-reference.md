---
date: 2026-10-10
topic: UI 設計書の不在 — ADR-002 が委任した先が存在しない
branch: feature/ui-design-doc-reference
---

# 作業ログ: 2026-10-10 UI 設計書の不在 — ADR-002 が委任した先が存在しない

## やったこと

### /task-start

- 既存 Notion タスクに着手(TSK-508「frontend の実装単位を定義する」の申し送り 2 として 2026-10-10 に起票): https://app.notion.com/p/3f493b75e68781efbe95d9931001f747
- ブランチ `feature/ui-design-doc-reference` / worktree `../pitchlog-worktrees/feature-ui-design-doc-reference`(`origin/develop` = `62fc5bfc` 起点)
- **着手の判断は master の盤面**(2026-10-10)。理由は下記。

### なぜこのタスクが先なのか(着手時点の実測)

**UF1 タブが U-F1(TSK-516)に着手している** — `feature/uf1-common-ui` の worktree を `62fc5bfc` 起点で確認した。
射程は `components/ui/**` で、**旧 React の `.tsx` を Vue 3 へ移すのが最初の仕事**になる。
そこで **ADR-002 の「コード再利用はしない」と PO 裁定 2026-08-16 の「機械的な逐語移植」**に正面からぶつかり、
**コンポーネント設計規約の引き元も無い**。**TSK-508 が定義した 14 単位すべてが毎回ここで詰まる。**

**`req-legacy-frontend-gaps`(TSK-306/310)を先にしない理由**: 要件書の改訂は確定ゲートの規模が大きく、
**リリース判定③の合格条件は「正解照合は紙スコアまたは現行システムの並行記録との突合」**
(`docs/requirements/requirements-pitchlog-2026-07-22.md:1085`)であって要件チェックリストではない。
**判定③へ行くのにこれを待たない。**

- **行番号の訂正**: master は同じ条文を `:1041` として渡してきたが、**実測は `:1085`**(44 行ずれ)。
  主張の中身は正しい。台帳の既知の型(「正本の行番号引用が、行ずれと用語違いで二重に外れる」)に当たる。

### 2 枚のカードの扱い(計画段階で提案する)

同じ送り元から **2 枚が起票されている**:

| カード | 内容 |
| --- | --- |
| https://app.notion.com/p/3f493b75e68781599143db84ce919fa5 | ADR-002「コード再利用はしない」と「機械的な逐語移植」の並存 |
| https://app.notion.com/p/3f493b75e68781efbe95d9931001f747 | ADR-002 が参照する UI 設計書が `docs/design/` に無い(**本タスク**) |

**どちらも「ADR-002 を改訂する」という同じ 1 つの作業に帰着する可能性がある。**
**正本 1 本の改訂を 2 枚で二重にゲートへ掛けると、確定ゲートを 2 回回すことになる。**

**合流させるかは人間の判断**なので、**`/plan` の中で案として出す。カードは勝手に統合しない。**

### 新しい worktree の全件実行で、`backend/.venv` の不在が DB 接続エラーに化けた(台帳の候補)

**2 つのセッションが独立に「共有開発 DB の問題」と誤診した。**

| 場所 | `backend/.venv/bin/python` | `uv run pytest tests/domain/mut/ -q` |
| --- | --- | --- |
| 新 worktree `feature/ui-design-doc-reference` | **不在** | **3 failed**, 82 passed |
| メインツリー `develop` | 存在 | **85 passed** |

失敗の実体は `subprocess` が `backend/.venv/bin/python` を起動できないことなのに、
**例外が `psycopg.OperationalError: connection to server at "127.0.0.1", port 5432 failed:
Connection refused` の形で表に出る**。測定スイートを子プロセスで回す試験
(`test_cost_record` の `differential` スコープ)が連鎖して落ちるため、
**「DB が落ちている」という読みが自然に見えてしまう。**

**誤診の経路**:

1. こちらが「共有開発 DB が落ちている」と報告(**この時点では実際に落ちていた** — `docker ps` が空)
2. `docker compose up -d db` が環境変数ファイルの変数補間で止まる(**これは実測どおり**・`docker-compose.yml:25` が自己注記)
3. master が「`docker compose down -v` を誰かが打った」と推定(**後に撤回**)
4. master が別の場所で 85 passed を得て「DB は落ちていない」と結論
5. **実測で切り分け** — DB は稼働中(`Up About an hour`)だが、**赤の原因は `backend/.venv` の不在**だった

**変数補間で compose が止まる件は、赤の原因とは別の事実である。**
2 つの独立した問題が同時にあり、**片方の解消がもう片方の説明に使われた。**

**運用上の含意**: **新しい worktree で全件を回す前に `backend` の依存を入れる。**
「実 PostgreSQL が要る試験は除く」という運用例外は**不要**(原因の取り違えに基づく)。

**観測の限界**: 2 セッション・1 日。**同型が再発するかは未確認。**


## 決定

## 未決・次の一歩

- `/investigate` で下調べ(ADR-002 の原文・委任の射程 / `porting-rules.md` が実質その役を果たしているか / `H-68` の型に当たるかの判定材料)
- `/plan` で計画書。**2 枚の合流の可否を人間へ上げる**
