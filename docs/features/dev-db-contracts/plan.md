---
feature: dev-db-contracts
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3bf93b75e68781429f3cdf678adc64ce
branch: feature/dev-db-contracts
created: 2026-08-17
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: Phase 4-3 開発用 PostgreSQL(docker-compose)+ contracts/ 雛形

<!-- 本ファイルは /task-start が作成した雛形。以降の内容は /investigate → /plan で埋める -->

## 1. 背景・目的

<!-- なぜやるか。Notion タスクと要件 FR/NFR へのリンクを必ず含める -->

- Notion タスク: [TSK-222 Phase 4-3](https://app.notion.com/p/3bf93b75e68781429f3cdf678adc64ce)(優先度 高・見積 3)
- 設計書 13 章「Phase 4 の分割」の論理スロット 4-3。4-2(backend 骨格)とは相互任意
- Phase 4-1 からの申し送り: `frontend/src/lib/display_geometry_263_v1.json` を `contracts/` へ移す(NFR-018・典拠 `docs/features/frontend-skeleton/porting-rules.md` 8 節)
- 着手前調査: [research.md](research.md)(要件突合・旧システム事実・決定経緯。論点 A〜G と抵触なしの確認)

## 2. スコープ

### やること

### やらないこと

## 3. 影響する正本

<!-- この feature が更新・新設すべき正本を列挙。「反映なし」の場合も明示する(空欄禁止) -->

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |

## 4. 実装方針

<!-- 重さ分類(frontmatter)の根拠を明記。コア領域(CLAUDE.md の列挙)に触れるかを必ず判定。
     詳細設計・長文の検討は design.md(テンプレ: design-template.md)へ分離し、本節からは相対リンクで参照する
     (内容を複製しない — 設計書 7.1-1。design.md は任意 — 密度が高くなる場合に /plan が分離) -->

前提となる調査結果と未解決論点は [research.md](research.md) を参照(内容を複製しない)。特に論点 A(NFR-018 実現方式 ADR 未起票)・論点 B(PostgreSQL 版未規定)・論点 C(CI paths filter の追随)は方針決定の前に人間判断が要る。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

<!-- 1 ステップ = 1 委任 = 1 コミット(レビュー可能な粒度・1 論理変更)。/implement がこの表を上から実行する。
     ラッパーは「番号・ステップ・合格条件の3セルすべてが埋まった行」が最低1つ無いと実行を拒否する(空テンプレ不可)。
     番号列は 1 からの連番(欠番・重複不可)。ステップコミットの件名には完全トークン「(ステップ <k>[/<N>][ 付記])」を
     ちょうど 1 個含める(/<N> と付記は任意・全半角括弧可 — feature_status.py が進捗導出)。承認・起票コミットには付けない -->

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |

## 5. DoD(受け入れ基準)

<!-- Notion タスクの DoD と同期させる。全 ON で完了にできる粒度 -->

- [ ] `docker compose up -d` で開発用 PostgreSQL が起動する
- [ ] `contracts/` の雛形がある
- [ ] `display_geometry_263_v1.json` が `contracts/` にあり、frontend からそこを参照している(複製が残っていない)
- [ ] `/check` 全グリーン

## 6. テスト計画

<!-- NFR-019 のどのテスト種別(単体・一致性・越境・E2E・故障系)に何を足すか -->
