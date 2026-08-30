---
date: 2026-08-31
topic: PostgreSQL 認可構成の実機検証(RLS・関数 ACL・search_path・ロール到達性)— TSK-250 の先行 B
branch: feature/pg-authz-verification
---

# 作業ログ: 2026-08-31 PostgreSQL 認可構成の実機検証

## やったこと

- /task-start: 既存の Notion タスク **TSK-270** を取得(TSK-250 の計画レビューで切り出し・起票済み —
  重複起票はしていない)・`feature/pg-authz-verification` の worktree 作成・計画書雛形と本ログの作成
- 重さ分類は **コア領域**(テナント分離)で起票済み。ラッパーが sol xhigh を自動適用する

## 決定

- **本タスクを先行させる**(人間の判断 2026-08-31)。先行 3 本のうち**スキーマ実装を実際にブロックするのは
  本タスクだけ**で、TSK-269(文書検査の機構)と TSK-271(88 列・移行)はブロックしないため。
  **製品コードの着手を最短にする**のが目的。TSK-269 は `ブロック中` で保留した

- /investigate: 調査サブエージェント **3 本**(要件からの認可行列母集合 / 候補案 3 章・8 章の棚卸し /
  認可まわりの過去決定)を並列で投げ、**あわせて Claude 自身が実 PostgreSQL 17.11 で検証**した。
  結果は `docs/features/pg-authz-verification/research.md` へ統合。**実機検証に使った SQL は
  `docs/features/pg-authz-verification/probe/` に保存**(計画・実装の材料)

## 実機検証で分かったこと(要点)

- **前タスクの誤り 2 件はいずれも再現**した。① `SECURITY DEFINER` は RLS をバイパスしない
  (所有者に `BYPASSRLS` が無い版は 1 行・ある版は 2 行)② 新規関数の `proacl` は NULL で
  **`PUBLIC` が実行可**。**無所属ロールから越境関数を実行して全テナントの行が読めた**
- **`search_path` 乗っ取りも成立**した(`SET search_path` なしの関数が偽テーブルを読んだ)。
  ただし**成立には関数所有者が攻撃側スキーマへ `USAGE` を持つ必要**があり、
  最初の試行が失敗したのは `SET search_path` の効果ではなくこの条件を満たしていなかったため
- **方法論上の落とし穴を新たに発見**: **`SET ROLE` の可否はセッションの認証ユーザーで判定される**。
  superuser セッションから `SET ROLE` してロールを模しても検証にならない
  (superuser は任意のロールになれる)。**テストは実接続で書く必要がある**
- **`NOLOGIN` は到達を止めていない**。止めているのは「所属を与えないこと」であり、
  所属を与えれば `SET ROLE` で到達してテーブルを直接読めた
- 候補案 3-3 節の警告(autocommit で `set_config` を分けると効かない)も**実機で再現**した

## 決定

- **本タスクを先行させる**(人間の判断 2026-08-31)。先行 3 本のうち**スキーマ実装を実際にブロックするのは
  本タスクだけ**で、TSK-269(文書検査の機構)と TSK-271(88 列・移行)はブロックしないため。
  **製品コードの着手を最短にする**のが目的。TSK-269 は `ブロック中` で保留した
- 調査は 3 本 + 自分の実機検証。**認可の性質確認をサブエージェントに委ねない**方針をとった
  (前タスクが文書だけで 2 回誤った領域のため)

## 未決・次の一歩

- /investigate で下調べ。**本タスクは文書調査より実機の性質確認が主**になる:
  - 候補案 `docs/features/product-data-model-design/design.md` の **3-2(ロール 3 分割)・3-6
    (`SECURITY DEFINER` 制限関数)・8-2-B(管理者経路の 4 クラス)** が検証対象の「形」
  - **前タスクが 2 回まちがえた箇所**(`SECURITY DEFINER` と RLS の関係 / `NOLOGIN` + 関数 ACL)は
    **拒否系テストだけでは検出できない**(TSK-250 のレビュー P0)。**正例と mutation test が必須**
  - **8-2-B のクラス (c) に「退避イベントの取り込み(挿入位置指定)」が含まれる**が、同期正本が
    TSK-267 へ送った射程外構造なので **DDL 化してはいけない**(TSK-250 の `FORB-01`・`DM-SY-C16`)
- 足回りの既知事項(TSK-250 の調査で確認済み): docker + postgres 17.11 は用意済み /
  worktree 側では `POSTGRES_USER` 未設定で `docker compose` が落ちる(`.env` は参照禁止)/
  `psql` 未インストール / CI の backend ジョブに postgres サービスが無い
- **TSK-250 への受け渡し契約**(TSK-270 の Notion 本文が正): 機械可読 3 資産(AUTH カタログ・
  DDL 要素表・不採用構成表)+ digest / **AUTH カタログとは独立した要件主張母集合** /
  本タスク自体をコア領域として敵対レビュー + 人間の逐行確認

## Supabase(マネージド環境)での実機検証 — 2026-08-31 完了

**人間が実行し、Claude は手順のみ設計した**(接続情報・パスワードは受け取っていない — NFR-014)。
使い捨てプロジェクト・**Data API / 新規表の自動公開 / 自動 RLS をすべて OFF** で作成。
証跡は `docs/features/pg-authz-verification/probe/supabase-managed.sql`(各 Run に実測値を併記)、
まとめは `research.md` 1-7 節。

- **前提条件は満たされた**: Supabase の `postgres` は **`rolsuper = false`** だが **`rolbypassrls = true`** で、
  **`CREATE ROLE … NOLOGIN BYPASSRLS` が成功**した。RLS + FORCE RLS + POLICY も成立。
  → **`REQ:1004` に関する最大の懸念(マネージド環境で構成が組めないのではないか)は否定された**
- **設計の中核が成立**: 同一トランザクション・同一ロールで
  **関数経由 = 2 行(全テナント)/ 直読み = 1 行(自テナント)**。
  `REVOKE ALL … FROM PUBLIC` 後は `public_exec = false` / `app_exec = true`
- **恒久的な到達経路は存在しなかった**: `CREATE ROLE` 直後の自動所属は
  **`admin_option = true` / `inherit_option = false` / `set_option = false`** で、
  **`postgres` は既定では `SET ROLE` できない**。`REVOKE` 後も `SET` / `USAGE` ともに false を実測
- **新たに判明した構築契約**: **`BYPASSRLS` ロールに何かを所有させる操作
  (`CREATE SCHEMA … AUTHORIZATION` / `ALTER FUNCTION … OWNER TO`)は、実行者がそのロールへ
  `SET ROLE` できることを要求する**。→ **一時的に開く → 所有させる → 閉じる**の 5 手順が確定し、
  計画 4 節「プロビジョニング手順」へ実装契約として記載した

### Docker(superuser)環境からの一般化が誤っていた — 実機差の 3 件目

調査時に「`postgres` から `BYPASSRLS` ロールへの到達経路が恒久的に 1 本残る」と見立てていたが、
**Supabase では既定で `SET ROLE` できず、この見立ては覆った**。Docker の `postgres` は superuser なので
任意のロールになれるが、Supabase の `postgres` は superuser ではない。
**1-5 節で見つけた「superuser セッションで模擬しても検証にならない」という落とし穴が、
見立てそのものにも効いていた**。実機検証でしか出ない差はこれで 3 件目
(① `SECURITY DEFINER` と RLS ② `NOLOGIN` の役割 ③ 本件)。

### 残余リスクとして記録(DB 層で塞げない)

| ID | 内容 | 送り先 |
| --- | --- | --- |
| `RES-01` | `postgres` は `admin_option = true` を持つため、資格情報を持つ者はいつでも経路を開ける | 運用統制(申し送り 7 節) |
| `RES-02` | プロビジョニング手順 5(一時所属の `REVOKE`)の漏れ | **カタログ検査の必須項目**(改訂 2 の `R-8`) |
| `RES-03` | Supabase の既定「新規表の自動公開」が ON。`pg_catalog` に現れず検査できない | 本番プロジェクトの作成手順(申し送り 7 節) |

### 実務上の知見

**Supabase の SQL エディタの文分割はドル引用符を解さない**(`DO $$ … $$` が
`unterminated dollar-quoted string` で落ちる)。**`--` コメント中のアポストロフィも分割を壊す**。
→ **人間に実行させる検証 SQL は平文 SQL で書き、ドル引用符とアポストロフィを使わない**。

**後始末**: 使い捨てプロジェクトごと削除する(個別の `DROP` 文も probe ファイル末尾に記録済み)。

## 計画の承認 — 2026-08-31

**第 1 群(ステップ 1〜5)を人間が承認**(山田正輝)。`承認: 済(2026-08-31・山田正輝)`。

- **承認範囲は第 1 群のみ**。第 2 群・第 3 群は**計画改訂 2** で確定し、再レビューを通す。
  3 周分のレビュー指摘は **`R-1`〜`R-8`** として計画書 4 節に保存済み(失わないため)
- 計画レビュー周回は **2 周**(指摘反映を伴う周のみ計上)。**コア領域として敵対レビュー済み**
- **Supabase の使い捨てプロジェクトは削除済み**(人間が実施)。検証環境は残っていない

**次の一歩**: ステップ 1(要件主張母集合の凍結)を Codex へ委任する(`/implement`)。
