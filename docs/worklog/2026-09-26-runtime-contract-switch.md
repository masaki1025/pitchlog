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
  - **DB 試験の後は毎回 `docker volume prune -f`**(`db_fixtures.py` の使い捨てクラスタが匿名ボリュームを残す — 別タスクで fixture を修正予定。Docker 29 の prune は未使用の匿名ボリュームだけを消し、名前付きは残る)

- **ステップ 8 の受理の材料(2026-10-04)**: develop(76b9f53a — #82・#74・#91 の後)を取り込み(d4be7141)、ドライランを最終化
  - **S = 76b9f53a4cb8265d570f7cbb2293f9ef8d1ed6ac / H = 92f6fefc57b5ce316aa34701f61d63604f08db1a / D = b03a32b0386189f1f44a5759c39c48d65cfc4f53**
  - 動いた corpus 入力は base-allowlist.json・runtime-authz-contract.json・snapshot の追加 1 件だけ → corpus digest を取り直し
  - ドライランの複製で backend 1125 passed・4 skipped(製品化済みでは行わない切り替えの試験 — 正当)/ ルート 2859 passed。実リポジトリで backend 1129 passed
  - **1 回目の受理と失効**: 山田正輝がセッション上で受理(2026-10-04 — 確認のうえ先へ進める指示。PR へのコメントは本人の判断で省略。代理投稿は自動判定で不可)。実行前に S・H・D の一致を確認し、ステップ 8 を 677129a3 として作成(親 = H、承認の 2 欄を戻した tree = D を確認・影響範囲の試験 green)。**push の前に #90(U-A1 α・d6f5f3c9)が develop へマージされ、design.md 4-1 の 7 により受理は失効**。人間の判断(A)で 677129a3 を外し(未 push)、取り込みからやり直す。#90 は凍結資産・corpus の入力に触れていない(14 ファイル・文書中心)
  - **2 回目の受理とステップ 8**: develop(d6f5f3c9 — #90 の後)を取り込み(7090842d — 衝突 4 件: data-model.md 12-8 と変更履歴〔v0.4 の実装追随〕・README・digest 2 行)。S = d6f5f3c9 / H = 7090842d / D = a65f33c1 を山田正輝がセッション上で受理(2026-10-04「承認」)。実行の直前に 3 つの一致を確認し、**ステップ 8 = fc377669**(親 = H・承認の 2 欄を戻した tree = D を確認)を push。影響範囲の試験 green(ルート 681・backend 801)。確認用の一時ブランチは削除
  - **448 の台帳候補への材料**: 「受理記録を最終ステップの直前に書く」形での手戻りは **1 回**(#90 が受理と push の間に入った)。#90 は凍結資産に触れていなかったので、手戻りの中身は取り込み・ドライラン・受理の取り直しだけで、記録の手での再導出は 0 回
  - 途中で見つけて直したもの: ドライランの TB005(a9f2f26c)・A2 の試験の staged 直書き(cb025e03)・記録の文面の空白(92f6fefc)。**教訓: 「複製の上で DB 試験を含む全試験」を自分で回し切るまで、受理を求めない**

## 決定

- **方式 = Y2(暫定資産をその場で製品化する)**(人間の判断 2026-09-26)。削除する案(TSK-461 待ち)と、凍結対象を向け直す案(`ddl-elements.json` 全体が凍結される)は採らない
- **計画を承認**(2026-09-26・山田正輝)。4 周目の収束確認は行わず、3 周目の反映後に承認した。design.md 6 節の既存の決定の改訂 7 件も含む
- 退去の機構のタスクは **TSK-461**(2026-09-26 起票・`未着手`)。調査の時点で TSK-448 の文書にあった「TSK-452」は番号の衝突で、448 側で訂正済み。448 のセッションへも伝えた

## 未決・次の一歩

- **全 8 ステップ完了**。次: 総合検証(/check)→ /sync-docs → /pr(ready 化・敵対レビュー・人間の逐行確認)。**PR は origin/develop == d6f5f3c9 の間にマージする**(動いたら受理は失効 — design.md 4-1 の 7)
- **ステップ 8 で corpus digest の再 pin が要る見込み**(448 のセッションより 2026-10-03): `tests/fixtures/frozen-archive-cases/manifest.json` の corpus digest は trees `contracts/tenant_boundary`・`tests/fixtures/tenant_boundary` を覆うので、受理記録と revision の変更で動く。手順: ① 動いた入力を列挙し、すべて本 PR の意図した変更だと確認 ② `uv run pytest tests/test_frozen_archive_case_runner.py` で manifest と actual を得る ③ `corpus_inputs.digest` の 1 行だけ置き換える ④ 1 file / 1 行の差分を確認 ⑤ `test_current_corpus_inputs_match_manifest_digest` が green。**develop 取り込みの後、最後の作業にする**。所有者(TSK-466)の同意はあるが、人間の許可は別途要る(計画の改訂として承認を得る)。TSK-467 が先に着地すれば不要
- **ステップ 8 の前提の変化(2026-10-01・448 のセッションより)**: #83 がマージ(f527cddf)。凍結資産は 8 件のまま。**凍結の外部ファイルに `scripts/frozen_archive.py` が加わり 4 件になった**(443 は触れない)。base-allowlist の contract_revision は #82・#74 の後で 22 前後。マージ順は #83 → #82 → #74 → 443。**TSK-466(#89・48302ab1)**: 受理記録の追記では corpus digest が動かない(再導出不要)。`test_current_unpinned_snapshots_are_referenced` が新設され、固定一覧に無い snapshot はすべて構造的に参照されている必要がある → **ステップ 8 で未参照の snapshot を残さない**(ドライランは比較元と HEAD の両方を書くので、全件が記録から参照されるかを確認する)。digest の対象の検査器は 6 本(check_tenant_boundary_bypass.py / frozen_history.py / frozen_archive.py / runner.py / ci.yml / test_check_tenant_boundary_bypass.py)— 443 は触れない。443 が閉じたら「受理記録を最終ステップの直前に書く」形で手戻りが 1 回で済んだかを 448 へ伝える(台帳の候補の昇格条件の判定材料)
