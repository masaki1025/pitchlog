---
date: 2026-09-17
topic: U-T1 テナント境界の強制点(app ロール・set_config 文脈束縛・fail-closed・迂回検査)
branch: feature/tenant-boundary-enforcement
---

# 作業ログ: 2026-09-17 U-T1 テナント境界の強制点

## やったこと

- /task-start: TSK-390(U-T1)を着手。worktree `feature-tenant-boundary-enforcement` を origin/develop(4b46c03)起点で作成し、Notion を 進行中 へ
- 依存 U-00(TSK-387)が origin/develop へマージ済みであることを確認
- /investigate: 3 並列(spec-checker / decision-tracer / Explore)+ 原典裏取り → `research.md`(245 行)
  - legacy-analyst は外した(テナント分離は旧システムに対応面のない新規要求 — U-00 と同じ判断)
  - エージェント報告の行番号 5 件を実測で検証し、3 件を是正して記録

## 決定

- **U-T1 は 12-4 のマージゲートの対象ではない**(入口を 1 つも開かないため要求が空)。
  **TSK-344 を待たずにマージできる** — `docs/features/product-impl-unit-split/plan.md:433-443` の【承認後の是正】。
  調査途中で「TSK-344 に依存する」と見立てたが、原典で誤りと確定した
- **Notion カード TSK-390 の「マージの条件」節は ADR-004 approved 前の古い記述**。カード側の追随が要る
- **fail-closed の DB 層での意味は「`set_config` を出さなければ 0 行」まで**。
  テナント文脈の**値の真正性**は API 層の責務(TSK-217)で、既存テストが残余リスクとして期待値に固定している
  (`backend/tests/db/test_authz_trust_boundary.py` / `contracts/authz/boundary-proposal.json:43-47`)
- **FR-034 の「既定拒否の原則」を fail-closed の根拠に使わない**(要件書 :608 が射程を FR-041 に明文で限定)
- **probe → 製品の写像は U-T1 に取り込む**(2026-09-17・山田正輝)。TSK-418 の「やること 1・2」
  (実装入力の名指し・写像規則)を U-T1 の計画書の先頭ステップに置く。TSK-418 には「カードへの依存追記」
  (やること 3)だけを残す。**恒等写像は成立しない** — probe 側は `probe_*` 表、製品側は `Tenant`/`TeamRecord`/
  `Player` 等で名前も粒度も違う。**U-T1 の見積(13pt)は膨らむ**

- /plan: `plan.md`(契約)と `design.md`(詳細設計)を作成。**敵対レビュー 4 周**(sol xhigh)
  - 1 周目 P0 5 → 2 周目 P0 5 → 3 周目 P0 3 → 4 周目 P0 3。**判定は 作り直し → 修正後に進める ×3**
  - **自分の裁定を 2 度是正した**: ① NFR-018 を不採用理由に使ったのは誤り(対象は閉じた列挙で認可関数は入らない)
    ② 12-4 のゲート対象外は正しいが、**12-7/12-8 の実機確定責務まで外せるという結論は誤り**
  - **自分の報告の誤りも 1 件是正**: 「フックが設定テンプレートを遮断する」は事実誤認。
    `secret_guard` は exact `.env.example` を明示的に許可している(解析不能な長大コマンドが安全側で落ちただけ)
- **TSK-424 を起票**し、製品認可面を分離(下記の決定)

## 実装(2026-09-18)

- /implement: 全 11 ステップを Codex へ委任(sol xhigh)。**差し戻しは 1 回**(ステップ 3 の fixture 二重登録)
- 各ステップで実 DB を使って検証。テストの推移: 428 → 466 → 478 → 486 → 528 → 542 passed(error 0)
- 端末固有の問題を 1 件発見: テスト用 DSN 2 本が SQLAlchemy 形式で設定されていたため
  `backend/tests/db` が 194 errors。conftest は libpq 形式を期待する。
  **コードの欠陥ではなく環境設定** — 恒久修正は人手が要る(設定の実値は読み書きしないため)
- ステップ 3 の差し戻し: 平場へ fixture を明示 import すると `db/conftest.py` 側とは別登録になり、
  セッションスコープでも setup が 2 回走る。`tested_role_connection` は `CREATE ROLE` / `DROP ROLE` の
  副作用と「事前に存在しないこと」の前提条件を持つため、`db/` が先に走ると平場側の複製が落ちる。
  **単独実行では表面化しない**。参照カウントで最後の解放時にだけ `DROP ROLE` する形へ是正
- develop(PR #69 で差分閉包の是正・PR #70 で U-01 DTO 基盤)を取り込み。**衝突 0 件**
- 取り込み後の全ゲート: ハーネス **1461 passed / 0 failed**(既知 red 7 件は解消)/
  backend **572 passed / 0 error** / `check_authz_catalog.py` ok / 迂回検査 ok / ruff・ty green

## クローズ(2026-09-18)

- /sync-docs: **正本への反映なし**で確定。`docs/` 配下の正本(requirements / design / adr / development / ops)の
  差分は 0 件で、宣言外の変更も 0 件だった。`docs/README.md` は「進行中の feature」が静的一覧を持たない設計のため更新不要
- 正本体系外で変更したのは宣言済みの 3 ファイル: `.claude/core-areas.json` / `.github/workflows/ci.yml` / 設定テンプレート
- **ハーネス運用評価台帳へ追記した**(判断: **該当する**)。**新規候補 1 件 + 既存候補 2 件へ事例追記**。
  `H-*` の新規採番はせず、版も上げない(7.6-3 前段)
  - 新規: **承認済みの上流計画が割り当てた分担が計画書から落ち、敵対レビューでも 5 周目まで検出されない**
  - 既存へ 3 例目: SQLAlchemy 形式の URL を DSN に渡す問題(**混入元が正本ではなく環境**という新事実つき)
  - 既存へ 11 件目: guard のコマンド文字列部分一致による誤検知

## 未決・次の一歩

- **TSK-418 の指摘は実質的に成立**(「4 つ送っている」は一部成立 — 12-8 節の TSK-317 名指しは 2 行)。
  probe 層では実体が landed しているが、**製品スキーマへの写像が欠けている**ため U-T1 が直接消費できない
- **射程を縮小した**(2026-09-17・山田正輝の裁定): 4 周しても P0 が収束せず、
  残った P0 が**製品の認可面ぜんたい(45 表 × 許可プロファイル × 所有単位・U-C1/U-C2/U-C3/U-A1/U-A2 にまたがる)**
  だったため、**[TSK-424 製品認可面の確定](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc)** へ分離。
  **TSK-418 の取り込み決定をこの範囲について撤回**した。U-T1 はカード本来の射程(ランタイムの強制点 + 迂回検査)へ戻る
- **U-T1 の計画書の責任**(縮小後):
  1. 実装入力の名指し + probe → 製品の写像規則(取り込み決定ぶん)
  2. 製品スキーマの物理 DDL 書式。`ddl-elements.json` の `app_role` に `DELETE` があるが正本 3-2 節の
     アプリ用ロールは `SELECT/INSERT/UPDATE` のみ → 引き渡し時の判断が要る
  3. 迂回検査の検索式の確定(分割計画書は形式だけを拘束し、式は各単位へ委ねている)
  4. スキーマ検査の合格述語の置き場(現在は feature 文書にあり、正本でも `contracts/` でもない)
- **是正 2 件**: Notion カード TSK-390 の「マージの条件」節 / TSK-418 のスコープ縮小(やること 3 のみ)
- 次: /plan(計画書)
