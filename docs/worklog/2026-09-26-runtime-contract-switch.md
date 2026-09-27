---
date: 2026-09-26
topic: ランタイム契約の製品資産への切り替え(TSK-443 / TSK-424 PR B)
branch: feature/runtime-contract-switch
---

# 作業ログ: 2026-09-26 ランタイム契約の製品資産への切り替え(TSK-443 / TSK-424 PR B)

## やったこと

- `/task-start` — TSK-443(既存カード・ステータス `未着手`)から着手。
  `feature/runtime-contract-switch` + worktree を `origin/develop`(`1a40410`)起点で作成
- 開始条件の確認(カード本文の 2 条件):
  - TSK-424 PR A1 — develop へマージ済み(`product-authz-surface`)
  - TSK-431 の 7D — **最小限の 7D だけが develop にある**(比較元にあって HEAD に無い凍結資産は無条件で不合格)。
    残りを担う TSK-448(`feature/frozen-history-7d-remainder`)は **PR B を解錠しない**と射程を見直し済み
    (同ブランチ `docs/features/frozen-history-7d-remainder/design.md` 3-4・:535)
  - PR A2(TSK-442)は未マージ(ステップ 1/11)— カード上は「望ましい」で必須ではない
- `/investigate` — 調査サブエージェント 3 本(spec-checker / decision-tracer / 実装構造)+ 主要な主張の原典での再確認
  → [research.md](../features/runtime-contract-switch/research.md)
  - 削除する案 (a)(b) は、いまの develop では必ず不合格になる(TSK-452 待ち)
  - 削除しない案 (c) は、U-T1 の二状態テスト(`test_authz_runtime_contract.py:135-139`)と衝突する
  - 9 節に書かれていない必須作業がある: 生成器が存在しない・製品資産のキー集合の exact な検査・件数 33 のべた書き・8 フィールドの導出規則が未定義

- `/plan` — [plan.md](../features/runtime-contract-switch/plan.md)(8 ステップ)+ [design.md](../features/runtime-contract-switch/design.md)
  - 計画の敵対レビュー 1 周目: P0 2・P1 5・P2 2 → すべて反映(計画レビュー周回 1)
    - P0-1: `change.aspect` に `baseline_value` は書けない(許されるのは 4 種)→ `["asset_snapshots", "declaration"]`
    - P0-2: 生成器を `scripts/` に置くと、コア領域にも backend の CI にも入らない → `backend/src/pitchlog/authz/` へ
    - P1-1・P1-3: 切り替えと受理の記録を別コミットにすると、間が red になる → 最終フェンスで 1 コミットにし、比較元を固定する
    - P1-5: 既存の DB 試験は製品の保護対象 2/45/38 を証明しない → A2 の適用器で製品 DB の統合試験を足す
  - 2 周目: P0 1・P1 6・P2 2 → すべて反映(周回 2)
    - P0-1: v2 記録の自然言語の欄は予約語(`PENDING`・`未承認`・`レビュー待ち`)を拒否する → 9 節 5 項の「旧値をそのまま記録」は書けない。旧値は v1 の記録に残す
    - 既存の違反 ID の引き継ぎ表・固定の宣言値の述語・共有 API(`runtime_contract_state.py`)・受理の手動ゲート
  - 3 周目: P0 0・P1 1・P2 3 → すべて反映(周回 3)
    - P1-1: 受理の手動ゲートを S(比較元)・H(レビューした HEAD)・D(ステップ 8 の tree の SHA)で縛る

- `/implement` ステップ 1〜5(2026-09-26〜27)
  - 548b769f(1)・a932fed7(2)・1b214d45(3)・06dd5f98(4)・03a1ba91(1 是正)・1bc9c99b(5)
  - **ステップ 4 は委任先が利用上限で最終報告の前に止まった**(週次上限 — リセット後に再開)。差分と合格条件はこちらで検証してコミットした
  - **ステップ 1 の見逃し**: 生成器の `.flush()` が迂回検査の名前駆動の TB005(Session.flush)に当たっていた。ステップ 1 の時点ではファイルが未追跡で検査の差分に入らず、ルートの全試験を回したステップ 4 で初めて出た → 03a1ba91 で是正。**教訓: backend/src に新しいファイルを足したステップは、コミットの後にルートの迂回検査の試験を回す**
  - 環境: ローカルの DSN は `+psycopg` 付きで psycopg が読めない → 実行時だけ外す。共有のローカル DB に `pitchlog_test_role` が残っていた回がある(並行セッションの衝突と見られる。消していない)
  - ルートの `test_checker_census_matches_merge_base` は develop でも落ちる既知の不具合(`fix/census-baseline-pin`)

## 決定

- **方式 = Y2(暫定資産をその場で製品化する)**(人間の判断 2026-09-26)。削除する案(TSK-461 待ち)と、凍結対象を向け直す案(`ddl-elements.json` 全体が凍結される)は採らない
- **計画を承認**(2026-09-26・山田正輝)。4 周目の収束確認は行わず、3 周目の反映後に承認した。design.md 6 節の既存の決定の改訂 7 件も含む
- 退去の機構のタスクは **TSK-461**(2026-09-26 起票・`未着手`)。調査の時点で TSK-448 の文書にあった「TSK-452」は番号の衝突で、448 側で訂正済み。448 のセッションへも伝えた

## 未決・次の一歩

- **ステップ 6 は PR A2(#84・OPEN)のマージ待ち**。マージ後に develop を取り込み、draft PR を作って `acceptance_id` を確定する
- ステップ 8(切り替えと受理)は、人間が PR 上で受理を明示した後
