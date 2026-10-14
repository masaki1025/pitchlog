---
date: 2026-10-08
topic: U-S1 同期適用核 — べき等キー・連番と採番の不可分性・墓標/改訂(TSK-391)
branch: feature/us1-sync-apply-core
---

# 作業ログ: 2026-10-08 U-S1 同期適用核 — べき等キー・連番と採番の不可分性・墓標/改訂(TSK-391)

## やったこと

### /task-start(2026-10-08・455 タブから切り替え)

- Notion TSK-391 を 進行中 へ。ブランチ `feature/us1-sync-apply-core`(起点 develop `1fdf1eec`)
- カードの出所は TSK-363(`docs/features/product-impl-unit-split/plan.md`。2026-09-13 承認)。帯 1(核)。主所有 FR-012
- コア判定: sync-protocol × recording-rights の重複帰属(`docs/features/product-impl-unit-split/design.md:101`)。レビューは敵対レビュー + 人間の逐行確認
- 依存先 U-T1(TSK-390)は Notion で「完了」と再確認した。U-T1 から分離した TSK-424(製品認可面)は「確認待ち」
- 前のタスク TSK-455 は `feature/vitest-vector-runner` の `b181b261` まで(調査済み・/plan 前)で中断した。Notion のステータスは 進行中 のまま

### 469 master からの衝突面の実測(2026-10-08)

- core-areas.json の追加窓口(`AREA_PATH_ADDITIONS`。`scripts/core_guard.py` の 310 行付近で回転式)には、236 と UM01 の 2 本がすでに乗っている。U-S1 が 3 本目を足すと、どの順でマージしても途中で赤になる
- UM01 が `backend/tests/test_*_boundary.py` と `backend/tests/test_*_repository.py` の glob を追加中(人間承認済み)。U-S1 の越境テストをこの命名に合わせれば、core-areas.json に触れずに済む可能性がある。ただし DoD の「重複帰属の明示」に JSON の変更が要るかは、別に切り分ける
- 同期適用核を触っている他タブはない(backend 側に同期適用核は存在しない)。`frontend/src/lib/sync/` の契約の写しと検査器を先に読む
- TSK-455 の Notion ステータスは 469 master が「保留中」に変えた
- 見積り: 13pt はコードの量で、計画レビューと承認の日数は別にかかる(他単位の実績は 1〜9 周)

### /investigate(2026-10-08)

- spec-checker・decision-tracer・Explore の 3 本を並列で実行し、`research.md` に統合した。決定的な主張 5 件は原典で確認した(transaction.py:109-113 が Select 限定、base-allowlist.json:8102-8113 の TB002、sync-server-apply/plan.md:60-66 の TSK-330 受け取り、DM:803-812 の C10、TSK-330/331/332/392 の Notion ステータス)
- 要旨: サーバー側の適用実装は TSK-330 が受け取り先(未着手)で、U-S1 との線引きがない。機構の詰まりは TB002・Select 限定・core-areas の窓口の 3 つ。依存は記録権の判定(U-R1)と状態遷移(U-X1・凍結中)が逆向き。裁定事項は R-1〜R-8

### /plan 計画レビュー 1 周目(敵対・sol xhigh・2026-10-08)

所見: **不可**(P1×8・P2×2)。NFR-018(Q-2)は P0 違反ではないと判定(要件の対象列挙に同期がなく、TS 側は正本の写しでトランザクション処理はサーバーの責務と明記)。1 イベント = 1 トランザクションは正本と整合。

| # | 指摘 | 扱い |
| --- | --- | --- |
| P1-1 | R-1(全部吸収)と Q-1(runner を TSK-332 側へ)が矛盾 | 人間へ再裁定を依頼 → 人間の判断で**スパイクを打つ**(feature/us1-sync-spike)。結果を見て決める |
| P1-2 | `sync_apply.py` を定義しても registry に接続されない(`operation_registry.py` は ROSTER_OPERATIONS だけ)。契約資産・生成物・凍結履歴も要る | 採用予定。ステップ 4 に明記する。スパイクの S-3 で実測 |
| P1-3 | ポートの同一トランザクションを型・合格条件で拘束していない | 採用予定。スパイクの S-2 で実測 |
| P1-4 | ④ の事前分類と、イベントごとのトランザクションの間で D5・D3 が古くなる | 採用予定。スパイクの S-5 で実測 |
| P1-5 | I5 の配信と再試行の担当、RG1 の全変更経路の保証範囲が未定 | 採用予定。配信の実装は既存にない(`repositories/cache_invalidation.py` は要求生成だけ)。担当の線引きを書く |
| P1-6 | P4(T8 のみ)・P5(T9 のみ)には「T 要素の間」の注入点がない | 採用予定。T8・T9 の内部の保存境界を名前付き注入点にする。スパイクの S-1 |
| P1-7 | TB002 の免除(ステップ 1)が core paths の登録(ステップ 13・14)より先で、一致条件を満たせない | 採用予定。core paths の宣言・登録を先頭へ移す(UM01 の注意: #95 マージ後に develop を取り込み、自分の分だけ宣言) |
| P1-8 | B5・B11(認証失効)は入口がないので到達しない | 採用予定。到達可能な境界結果を列挙し、B5・B11 は入口 PR へ送る |
| P1-9 | `backend/tests/db/` は全 5 領域に当たる。テストは平場に置き、テスト paths も登録する | 採用予定 |
| P2-1 | ステップ 6 の合格条件が後のステップに依存 | 採用予定。経路全体と ACK の合格条件を公開入口のステップへ移す |
| P2-2 | SP に「TSK-330」の記述はない。逆に `idempotencyCollision.ts:3` が漏れている | 採用予定(原典で確認済み) |

追加で分かったこと: TSK-330 には runner のほかに、復元ライフサイクルの故障シナリオ 12 本が繰り延べられている(`docs/features/sync-server-apply/design.md:392-405`)。R-1 の「全部吸収」はこれも含む。

## 決定

- 2026-10-08 人間の裁定(research.md の R-1・R-2・R-5):
  - R-1: **U-S1 が TSK-330 を全部吸収する**(runner・P3 の T7・I5・I6 を含む)。TSK-330 は取り下げか統合として扱う。`canonOracle.spec.ts:685-688` の「TSK-330」文字列も追随させる
  - R-2: 記録権の判定(V12・D4・RG1)と状態遷移(T4・再計算)は、**注入境界で受ける**。本物は U-R1・U-X1 が差し込む。FR-012 は U-S1 では部分充足とする
  - R-5: **UM01 の #95 の上に積む**(起点を feature/um1-player-roster-opponent にする)
  - R-3: **HTTP 入口は U-S1 では開かない**。サービス層は入口から直接呼べる形で作る。入口は TSK-331 で形式が決まった後に、小さな PR で開く。人間の判断基準は「製品コードが早く develop に入る方」

### スパイクと計画書の改訂(2026-10-08)

- 人間の判断でスパイクを打った(`feature/us1-sync-spike`。Codex。敵対レビュー 3 周で承認。3 ステップ・DB テスト 20 件 green)。結果は research.md「スパイクの結果」
- スパイク中に、#95 の UPDATE が CompileError になる欠陥を見つけ、UM01 へ報告した。UM01 が #95 で是正する
- R-9: **U-S1 が TSK-332(NFR-019(d) の資産契約の再設計とシナリオ資産)も吸収する**(2026-10-08・人間。スパイクで資産の実際の形が見えたため)。復元ライフサイクルの故障シナリオ 12 本の送り先は、計画書の Q-9 で人間の確認を待つ
- 計画書と詳細設計を全面改訂した: レビュー 1 周目の 10 件、スパイクの結果、TSK-332 の吸収を反映。ステップは 14 → 18

### 計画レビュー 2 周目(敵対・2026-10-08)

所見: **不可**(P1×6・P2×1)。1 周目の 10 件のうち、P1-1(全部吸収)と P1-4(D5 の競合処理)が未解消と判定された。

| # | 指摘 | 扱い |
| --- | --- | --- |
| P1-1 | 資産の比較単位が正本 10-3(SP:1716)と食い違う | 人間の裁定 R-10: 正本を v0.5 に改訂する |
| P1-2 | 繰り延べ 12 ID は復元系 10 + P3 配信途中 + O4。送り先が未定 | 人間の裁定 R-11: 復元系 10 は U-R1、残り 2 は U-S1 |
| P1-3 | 一意制約違反の後の復旧方法が未定。スパイクの実測範囲を超えた記述 | 採用: SAVEPOINT で戻して再照合。INSERT 直前で止める並行試験を追加。記述を実測範囲に狭めた |
| P1-4 | 同じスレッドの検査だけでは、別スレッドのポートを防げない | 採用: ポートに TenantContext を渡さず、発行 allowlist で作れなくする(1 層目)。同じスレッドの検査は 2 層目 |
| P1-5 | T6 の一時 ID 写像は別表で、注入点 1 個では見えない | 採用: 写像表の保存の前後に注入点 |
| P1-6 | P3 に加わる期待フィールドと、トランザクション外の 3 注入点の検査がない | 採用: ステップ 14 の合格条件に追加 |
| P2-1 | 既存 4 資産を v2 にすると spec の版の期待集合が落ちる | 採用: ステップ 15 の範囲に spec を明記 |
- R-10: **正本 sync-protocol.md 10-3 の比較単位を改訂する(v0.5)**。U-S1 の PR に確定ゲートを含める(2026-10-08・人間。計画レビュー 2 周目で、資産の比較単位が正本と食い違うと判定されたため)
- R-11: **TSK-330 の繰り延べ 12 ID のうち、復元ライフサイクルの 10 件は U-R1(TSK-392)へ送る**。`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence` は U-S1 で作る(2026-10-08・人間)

### 計画レビュー 3 周目(敵対・2026-10-08)

所見: **不可**(P1×2・P2×2)。P2 の 2 件(新規資産の件数の不一致・T6 の書き込み単位の記述)は反映した。

| # | 指摘 | 扱い |
| --- | --- | --- |
| P1-1 | 外から有効な文脈を持ち込んだポートが、別スレッドで独自スコープを開ける | 人間の判断 R-12: アプリの層で最大限(登録表・推移的 import の静的検査・同じスレッドの拒否)にし、残りは記録。DB のトリガは U-X1 へ申し送り |
| P1-2 | I6 の「サーバー確定後・端末永続化前」の検査が、サーバー側 runner ではできない | R-12: Vitest 側の runner をステップ 18 として追加(既存の failureScenarioAdapter と durableQueue の I6 注入口を使う) |

途中で人間に 3 案(推奨 = 静的規則と繰り延べ / そのまま承認 / 完全に閉じる)を出し、人間は「完全に閉じる」を選んだ。ただし P1-1 はアプリの層では閉じられない(待たずに戻る預け入れは、適用核のトランザクションの後に走る)と分かったため、DB のトリガ案と比べ直し、人間が R-12 を選んだ
- R-12: **ポートの別スレッドへの書き込みの預け入れは、アプリの層で最大限に防ぎ、残りは記録する**。DB のトリガ案は採らず、投影の表の持ち主 U-X1 へ申し送る。I6 の端末側の検証は U-S1 で閉じる(Vitest 側の runner)(2026-10-08・人間。計画レビュー 3 周目)

### 計画レビュー 4 周目(敵対・2026-10-08)

所見: **不可**(P1×2)。3 周目の I6・件数・T6 は解消。残り 2 件とも採用して反映した。

| # | 指摘 | 扱い |
| --- | --- | --- |
| P1-1 | 禁止 import に DB 接続がない。`pitchlog.db.engine` から別接続を作れば同じスレッドでも書ける(R-12 が受容した穴とは別) | 採用: `pitchlog.db.engine`・`sqlalchemy`・`psycopg` を禁止に加え、別接続を作るポートの負例を置く |
| P1-2 | 登録表が空なので、「独自スコープを開くポートで失敗」はポートが呼ばれなくても通る | 採用: テスト中だけ合成ポートを登録し、呼び出しの後にスコープの入口で拒否されたことを spy で確かめる |

### 版番号の衝突と論点 17 の帰属(2026-10-09)

- sync-protocol.md の **v0.5 は #81(TSK-236)が 2026-09-28 に approved で使用済み**だった(`origin/feature/appendix-e-golden-vectors:docs/design/sync-protocol.md:10` を実見)。develop は v0.4 なので空いて見えた。山田正輝の裁定(469 master 経由): **#81 の v0.5 は動かさず、U-S1 は v0.6**。本書の規律「同一版番号を別内容で確定しない」と、v0.2 を TSK-267 に空けた前例に沿う。plan.md(:36・:77・:81・:143)・design.md Q-8・research.md R-10 を v0.6 に改めた。**U-S1 の確定ゲートは #81 のマージ後に通す**(先に通すと v0.5 が 2 つ develop に入る)
- 10-1 の (B) 論点 17(D5・D4・復旧世代の生成と物理形式。受け取り先 =「同期・記録権の最初の実装タスク」)の割り振り:
  - **D5 の側は U-S1 が引き取る**。物理形式は既に `uuid`(`backend/src/pitchlog/db/sync_protocol/models.py:259`)で、クライアントが生成する。内容同一性の判定は design.md Q-4 で決めた(入力原本の正規化 JSON の全フィールド比較)
  - **D4・復旧世代の生成方式と保存場所は U-S1 では引き取らない**。R-2 で記録権の判定を注入境界の外に置いたので、記録権の実装である U-R1(TSK-392)の射程と読む。U-R1 側との合意はまだ取っていない
  - TSK-331(wire 形式)は論点 17 を射程から外してよい、と 331 タブへ伝えた

## 未決・次の一歩

- #95 のマージ待ち(実装の開始条件)。ステップ 1・2 は #81 のマージも待つ
- 論点 17 の D4・復旧世代の側は、U-R1(TSK-392)の計画時に受け取りを確認する

## 2026-10-11 引き継ぎと測り直し(UM01/447 タブ)

- **引き継ぎ**: master の盤面確認で TSK-391 の所有者が空(以前の 391 タブは TSK-455 を担当して終了)。Notion は「進行中」・担当者は山田正輝のまま。本ブランチと `feature/us1-sync-spike` は origin に無かった(master は当初「計画書が無い」と誤認 — 未 push の worktree を見ていなかった)
- develop `8060b8d0`(#114 を含む)を取り込んだ(`607ed4cc`・574 コミット・競合なし)
- **測り直し**(decision-tracer 1 本・読み取りのみ): 開始条件(#95・#81 着地済み)・R-3(TSK-331 マージ済み・正本を改訂しない・入口 PR = TSK-506)・R-1/R-9/R-11・sync-protocol v0.6 の予約(現行 v0.5)は維持。変更が要るのは ① #114 と重なる I5 の周り(1 行 1 範囲と意図 ID・配信状態の語彙・I5 用の token・D1 付き経路の発火が計画に無い・`B06` の配信の行が I5 にも読める)② 受理記録を 1 件にまとめるステップが無い ③ 窓口(`authStore*` の置き換え)④ 基底の拡張のうち registry の集約は #114 で導入済み
- **人間の裁定**(2026-10-11・山田正輝 — AskUserQuestion): R-13 I5 の配信と再試行は U-S1 / R-14 同期経路の意図は範囲ごとに 1 行・`B03` を改訂 / R-15 契約の語彙を DB に合わせる
- 計画書を**第 1 改訂**(ステップ 19 → 22 本へ振り直し・3 節に data-model・契約・digest 資産を追加・DoD 4 項目・7 節に承認事項 A-1〜A-3)。design.md に注記
- スパイク: 自身の計画が「転記の後に削除」と定め、research.md に転記済み。削除は改訂の承認の後(A-3)
- **第 1 改訂の計画レビュー 1 回目**(敵対・改訂全体): 否決(P0 1 / P1 2 / P2 1)→ **全件採用**(周回 4 → 5)
  - P0: R-14(範囲ごとに 1 行)が sync-protocol の「安定した意図 ID で 1 件だけ永続化」(8-1 `T7` `:1229`・10-2 P3 `:1669`・10-3 `T7` `:1724`)と衝突 → 新ステップ 1 を data-model v0.8 と **sync-protocol v0.6(「1 件」の追随)** の単一の確定ゲートにし、R-10 の 10-3 の資産構造の改訂を v0.7 へ繰り下げた。**R-14 の裁定の時点で作成者がこの条文を見落としていた**(data-model だけの改訂で足りると説明した)ので、改訂の承認の場で併せて報告する
  - P1: data-model の一意性の索引表(`:414`)にも旧導出が残る → 新ステップ 1 の範囲に追加 / 新ステップ 9 の合格条件が実経路の発火と再掲を要求していた → 記録部の直接呼び出しで検証し、実経路と再掲は新 10・13 へ
  - P2: 3 節の repository-contract の行から registry の集約を外した
- **計画レビュー 2 回目**(反映差分): 否決(P1 3)→ **全件採用**(周回 5 → 6)。① sync-protocol 10-3 の P3 の期待結果「安定した意図 ID」(単数 `:1715`)も v0.6 の範囲へ(範囲ごとの全意図 ID・永続状態・再掲後の件数を観測対象と明記)② 新ステップ 13 に「P3 の初回受理で範囲ごとの意図が同一トランザクションで保存される」を追加 ③ R-10 の版指定を v0.7 に統一。**上限(基本 2 回)到達・P0 なしのため 3 回目は無く、本反映は再レビューを受けていない** — 改訂の承認の場で差分を確認していただく
- **第 1 改訂の承認**: 2026-10-11・山田正輝(7 節 A-1 D1 付き経路の意図 ID = イベントの D5 + 範囲 / A-2 行の量を受け入れる / A-3 スパイクの削除 を含む)。R-14 の影響範囲の見落とし(sync-protocol の「1 件」)は承認の場で報告済み

### 新ステップ 1(正本の改訂案 — data-model v0.8・sync-protocol v0.6)

- **data-model**: 11-2 節 `B03` の表の「表」(`I5` は `T7` と、D1 付き経路は D3 を前進させたイベントの適用と同一トランザクションで、対象範囲ごとに 1 件)・「一意性」(意図 ID = 対象イベントの識別 + 範囲 — `I5` は `V10` + 確定版 + 範囲、D1 付き経路は D5 + 範囲)・直後の注記 / `B06` の「配信の所有」を同期を通らないトリガーに限り、同期経路は同期側が持つと明記 / 一意性の索引表の 11-2 行の注記 / 変更履歴 v0.8(in-review・射程宣言)
- **sync-protocol**: 8-1 の `T7` の段落・10-2 の P3 の行・10-3 の P3 の期待結果と `T7` の必須観測を「範囲ごとに 1 件」「範囲ごとの安定した意図 ID の全集合」へ(意味規則は不変)/ 変更履歴 v0.6(in-review・射程宣言)
- **追随**(#114 の教訓どおり同じステップで): `contracts/db/schema-manifest.json` の sha256・`contracts/authz/shared-preconditions.json` の blob digest・ORM 受入シート(N3 の判定 90 行を持ち越し、新しい 3 行〔v0.8 の変更履歴行・v0.6 の変更履歴行 2 行〕を旧版の同種の行に倣って判定)・固定行数 N3 103 → 104・`docs/README.md` の 2 行
- **途中の失敗 2 件**: ① 一意性の索引表の 2 列目(業務上の一意性の名前)を manifest が完全一致で写しているのに、そこへ補足を足して `test_schema_manifest.py` が赤 → 補足を 4 列目へ移した ② 受入シートを `--carry-judgments-from` なしで生成し直して判定を空にした → develop の版に戻して持ち越しからやり直した
- `test_authz_cache_invalidation.py` の正本の文言照合(「T7 と同一トランザクション」)を保つ語順にした
- 合格条件: `check_docs_status`・`check_design_propagation`・`check_doc_coverage`・`check_shared_preconditions` ok / `check_authz_catalog` ok(`requirement-claims.json` の抜粋の digest には当たらず、oracle の再導出は要らない)/ backend の DB 不要の全件は既知の偽の赤 44 件(「HEAD の履歴に staged 製品資産がありません」— develop を第 2 親で取り込んだ形)以外 green / ORM 受入シート・shared-preconditions・doc profiles 30 passed

### 確定ゲート(/finalize-doc — data-model v0.8 と sync-protocol v0.6 の単一の確定ゲート)

#### 適用版の記録(7.3-1)

```
適用版            ハーネス設計書 7.3 の v1.19(2026-10-07 確定ゲート通過・approved)
条文コミット SHA  945384c5e70ce2ae471edec1d845660918eaee93
```

- 回数の枠(6.3): 基本 2 回(全文 1 + 差分 1)/ 2 回目に P0 が残り 1 件以上採用したときだけ 3 回目(P0 限定)/ 追加は PO 裁定 1 回につき 1 回
- 対象: 2 文書の一括検証(単一ゲート・記録は 1 件 — 7.3-1)
- 手順 0: 射程宣言は両文書の変更履歴行(in-review)にある
- 手順 1: 両文書の frontmatter と索引を `in-review` に更新(本記録と同一コミット)

#### 1 回目(全文 / 枠 基本 2 + P0 例外 1)— 否決(P0 0 / P1 4 / P2 0)

| # | 要旨 | 重大度 | 起因 | 分類 | 採否 | 反映 / 理由 | 反例の典拠確認 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1-1 | 同期経路の「範囲ごとに 1 行」が、複数の物理鍵(例: 2 グループで共有される ④)をどう選ぶか定めていない | P1 | 非起因 | (A) | 採用 | `B03` の表に「各行が選ぶ無効化先(同期経路)」の行を新設: 1 行は当該イベントのデータを含む鍵すべてを選ぶ選択子(① = `(tenant_id, 試合)`、②③⑤ = 当該試合のデータを含む鍵すべて、④ = `B06` の対象テナント単位の選択子)。展開は配信側 | `data-model.md` の `B02`・`B06` で確認 |
| 1-2 | 5-4 節に「安定した意図 ID で 1 件だけ」が残る | P1 | 非起因 | (A) | 採用 | 5-4 節を「1 回の論理無効化につき、対象範囲ごとに 1 件・再掲ではその全集合を新設しない」へ | `data-model.md:1094` で確認 |
| 1-3 | `RG1` の行が意図の永続化を一律に `T7` の一部とし、D1 付き経路の錨と矛盾 | P1 | 非起因 | (A) | 採用 | `I5` では `T7` の一部、D1 付き経路では D3 を前進させたイベントの適用のトランザクションの一部、へ | 該当行で確認 |
| 1-4 | D1 付き経路にも意図の原子保存を要求したのに、故障系の資産契約で観測を必須にしたのが P3 だけ | P1 | 非起因 | (A) | 採用 | sync-protocol 10-2 の P1・P2 の行と 10-3 の契約に、D3 を前進させた各イベントの範囲ごとの意図の全集合・再掲と全件重複で新設しないことを必須観測として追加。変更履歴 v0.6 の射程宣言を追随 | `sync-protocol.md:1668`・`:1716` で確認 |

- 確定ゲート周回 0 → 1(反映 1 周目)。data-model の digest(schema-manifest・shared-preconditions)を取り直し、ORM 受入シートは行の構成が変わらず green のまま
- **実装への影響**: 新ステップ 9 の記録部は、範囲ごとの行に選択子の列(①②③⑤ = `game_id`、④ = `target_tenant_id`)を埋める。新ステップ 18 の新規資産と 16 の資産契約は、P1・P2 の意図の観測を含む

#### 2 回目(1 回目の反映差分と影響節)— 否決(P0 0 / P1 1 / P2 0)

| # | 要旨 | 重大度 | 起因 | 分類 | 採否 | 反映 / 理由 | 反例の典拠確認 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2-1 | ②③⑤ の「当該試合のデータを含む鍵」は、鍵が試合を含むかの情報を持たないので機械的に選べない。undo の後の状態だけで判定すると取り消し前に含んでいた鍵を見落とす | P1 | 起因 | (A) | 採用 | ②③⑤ を「当該テナントの当該範囲の鍵すべて」へ(試合で絞り込まない — 広めに消す向き)。行の冒頭も「範囲の鍵の集合を選ぶ選択子」へ | `data-model.md` の `B02` の ②③⑤ 行・`sync-protocol.md:1153` で確認 |

- 確定ゲート周回 1 → 2(反映 2 周目)。**基本枠 2 回に到達**。2 回目に P0 は無いので 3 回目は無い。**本周の反映は Codex の再レビューを受けていない** — 人間承認の場で最終反映の差分を確認していただく(7.3-2・7.3-8)
- 不採用: なし
- **実装への影響**: 新ステップ 9 の記録部の選択子の列 — ① = `game_id`、②③⑤ = テナントだけ(対象列はすべて NULL)、④ = `target_tenant_id`

#### 承認と要点

- **PO 承認 2026-10-14・山田正輝**(最終反映 `c1f0387e` の差分 = `B03` の「各行が選ぶ無効化先」の ②③⑤ を当該テナントの当該範囲の鍵すべてへ、を提示して承認)。両文書を approved・data-model v0.8・sync-protocol v0.6 に、変更履歴に通過行、README 索引を現行化。data-model の digest と ORM 受入シートを追随
- 要点: 2 回・反映 2 周・指摘 5 件(P1 5)全件採用。警告・エスカレーション・PO 裁定は発動なし。重要な是正は「範囲ごとの 1 行が選ぶ鍵」を定めたことで、新ステップ 9 の記録部の列の埋め方(① = `game_id`・②③⑤ = テナントだけ・④ = `target_tenant_id`)が決まった

### develop の取り込み(2026-10-14)と data-model の版の繰り下げ

- develop `2a456828`(57 コミット)を取り込み、4 件の競合を解いた: `docs/design/data-model.md`(変更履歴の先頭)・`docs/README.md`(data-model と sync-protocol の行)・`contracts/db/schema-manifest.json` と `contracts/authz/shared-preconditions.json`(data-model の digest)
- **develop で TSK-479 が data-model の v0.8 を先に確定させていた(2026-10-13 — 10-3 節の試合区分の seed)。本 PR の改訂を v0.9 へ繰り下げた**(変更履歴の 2 行・11-2 節と 5-4 節と索引表の版の表記・README・sync-protocol の変更履歴の参照・計画書)。**内容は承認されたものから変えていない**(確定ゲートの承認は 2026-10-14 の版の番号だけが変わる)
- data-model の digest を取り直し、ORM 受入シートを develop の版から生成し直して判定を持ち越した(新しい 3 行は従来どおり判定)。固定行数 N3 104
- **直列点**(2026-10-14 時点の open PR): #125(U-F8)・#127(U-F5)が `scripts/core_guard.py`・`.claude/core-areas.json` の窓口を動かしている / #119(δ)が `contracts/tenant_boundary/base-allowlist.json`・`docs/design/data-model.md` を動かしている。新ステップ 2・3(窓口)の前にマージ順を master と調整する

### 新ステップ 2(コア領域の窓口の置き換え — 2026-10-14)

- 1 回目の委任は U-F6 の窓口を前提にしたが、その間に develop が #125(U-F8)で窓口を回転させたため差分を捨て、develop `ef5c8711` を取り込んでから(`f1187438`・競合なし)やり直した。1 回目の Codex がテストの基線を merge-base へ変えた回避策も戻した(取り込み後は不要)
- **develop 自身で `tests/test_core_guard.py` の 2 件が赤**(#125 が「自分のマージ後に必ず落ちる」表明を残した)。master が山田さんへ上げ、**U-S1 には抱き合わせない**判断(射程外)。窓口の置き換えに付いてくる `test_uf8_game_screen_paths_are_registered_in_all_areas` の書き換えは入れ、`test_product_rls_paths_remain_in_develop_baseline` は develop の版のまま(1 failed は develop と同じ)
- Codex 委任: `AREA_PATH_ADDITIONS` を U-F8 の 5 件(基線へ取り込み済み)から U-S1 の宣言(sync-protocol・recording-rights × `backend/src/pitchlog/sync/*`・`backend/src/pitchlog/repositories/sync_apply.py`・`backend/tests/test_sync_apply_*.py`)へ置き換え、`tests/test_core_guard.py` の期待値を追随
- 敵対レビュー(検査経路):
  - 1 回目: 否決(P1 1)→ 採用。U-F8 のテストが U-F8 の glob を基線の「末尾」と表明 → U-S1 の登録が develop に入った後に必ず落ちる → 包含の検査へ
  - 2 回目: 否決(P1 3)→ 1 件採用・2 件不採用(上限到達 — 反映は再レビューなし)
    - 採用: U-F8 のテストが U-S1 の宣言内容を完全一致で表明 → 外した(U-S1 の宣言は既存の登録テストが検査する)
    - 不採用: `test_product_rls_paths_remain_in_develop_baseline` の末尾固定 — develop 側の赤で射程外(master の判断)
    - 不採用: 登録テスト(`:2440` 付近)と合成リポジトリの補助関数(`:604` 付近)の件数・末尾の固定 — 窓口を回す単位がそのたびに更新する設計で、U-S1 自身のマージ後には通る。**「宣言の窓口を使う PR がマージ後に必ず落ちる表明を残せる」型の台帳候補**(master の指摘 — 本日 3 件目)として、本 PR のクローズ処理で判断する
- 合格条件: `tests/test_core_guard.py` 234 passed / 1 failed(develop と同じ赤)/ ruff・ty green / 差分は `scripts/core_guard.py`・`tests/test_core_guard.py` だけ

### U-G1 との接合(2026-10-14)

- **U-G1 からの照会**(master 経由・山田さんの指示): 共通ロック順・初期 D4 の発行時点・D3・RG1 境界を、既存契約で確定できる範囲と U-R1 待ちに分けて回答した(decision-tracer 1 本・読み取り)。要点: ロック順は既存契約に無い(U-S1 設計は試合行と世代行の 2 つを `FOR UPDATE` で取るが順序が未定)/ 初期 D4 は正本が食い違う(REQ 4.0-1:151・FR-013:337 = 開始時、SP 9-5:1531 = 作成時)/ D3 = 0 は確定(DM:817,830)・置き場は記録権世代行 / RG1 は規則が確定・ゲート本体は U-R1
- **山田さんの裁定**(2026-10-14): ② 初期記録権は「試合開始」で付与(準備中の作成時は付与しない)/ ④ 共通ロック順は「試合行 → 記録権世代行」(U-S1 の提案)。U-G1 の準備中の作成は、規則解決・RG1 停止条件・認可契約が成立した時点で先行する
- 計画書を**第 2 改訂**(R-16 ロック順・R-17 開始時付与と sync-protocol 9-5 の RG1 表の行の分割を v0.7 の確定ゲートへ)。design.md 3 節・Q-3 を共通ロック順に。要件書は改訂しない(FR-001 に作成時の記録権の記述なし)
- **RG1 の照会への回答**: RG1 は全通常書き込みを止める共通ゲート(SP:694・:720)で、作成行は理由を記録権に置いていない。作成が記録権を作らなくなっても、復元調整中は試合を作れない(B7)
- **第 2 改訂の計画レビュー 1 回目**(敵対): 否決(P0 1 / P1 3)→ **全件採用**(周回 6 → 7)
  - P0: U-G1 が先にマージすると、作成時に記録権を作らない実装と正本 9-5 が食い違う(改訂予定の参照では解消しない)→ **山田さんの判断(2026-10-14 — AskUserQuestion)で 9-5 の行の分割を単独の小さな PR にする**。その PR が sync-protocol の v0.6 を取り、U-S1 の改訂は v0.7(「1 件」の追随)・v0.8(R-10)へ繰り下げる
  - P1: 共通ロック順の対象を「認可を通り試合行が存在してイベントのトランザクションへ進む経路」に限定(B6・B12 はロックの前に止まる)/ ロック順の実入口からの検査を新ステップ 15 に置き、10〜13 は局所の検査に。新ステップ 8 の競合試験は別の試合の同じ D5 で / DoD に第 2 改訂の 3 項目
- **第 2 改訂の計画レビュー 2 回目**(反映差分): 否決(P1 2)→ **全件採用**(周回 7 → 8)。① 版の繰り下げを計画の実行箇所(3 節・4 節・DoD・design Q-8)に揃えた(単独 PR の取り込み順で決まるので「ブランチ内 v0.6 → 取り込み時に v0.7」「R-10 = v0.8」と書く)② R-16 本文と新ステップ 15 を「イベントのトランザクションへ進む経路」に揃え、RG1 などで事前に停止する経路はロックを取らないと明記。**上限(基本 2 回)到達・P0 なしのため本反映は再レビューを受けていない**
- **第 2 改訂の承認**: 2026-10-14・山田正輝。**最終反映(計画レビュー 2 回目の P1 2 件 — 版番号の表記をブランチ内 v0.6 → 取り込み時 v0.7・R-10 = v0.8 に揃えたことと、ロック順の対象を「イベントのトランザクションへ進む経路」に限定したこと)は、上限到達のため再レビューを受けていない**。承認は計画に限り、正本の確定(9-5 の単独 PR を含む)・凍結資産の更新の承認を兼ねない
- 承認と同時の指示: ① U-G1・U-R1 へ契約(共通ロック順・試合開始時の記録権付与・RG1)を正式に提示し、受理と未確定事項を各計画書・作業ログへ記録する ② 9-5 を直す単独 PR の Notion タスクを起票する(重複確認・開始時付与との整合に必要な最小限)— 正式ゲートを通し U-G1 のマージより前に統合する ③ develop の guard 試験 2 件は別 fix の方針を維持 ④ Claude 向け申し送り(`2026-10-13-claude-mvp-handoff.md`)へ追記
- **契約の正式提示**(2026-10-14): 共通ロック順(試合行 → 記録権世代行)・初期記録権は試合開始で付与・RG1(作成・開始・終了は B7)を、U-G1(TSK-395 のコメント `3f893b75-e687-8178-a3ab-001d39bfb632` と U-G1 の作業ログ `/tmp/pitchlog-ug1-game-lifecycle/docs/worklog/2026-10-14-ug1-game-lifecycle.md` の「やったこと」末尾)・U-R1(TSK-392 のコメント `3f893b75-e687-8169-9d5e-001d887b6b9f` — 担当・計画書・作業ログが未作成のため Notion に置く)へ提示した。**受理は各担当が計画書に記録する — 2026-10-14 時点ではどちらも受理待ち**
- **単独 PR のタスクを起票**: **TSK-547**「sync-protocol 9-5 の RG1 表で「試合作成」と「試合開始(初期記録権の付与)」を分ける(U-G1 のマージ前に確定)」https://app.notion.com/p/3f893b75e6878131bfcff40f4d1c2937 。重複は Notion 検索で確認(該当なし)。範囲は 9-5 の 1 行の分割・変更履歴・README だけ。sync-protocol の v0.6 を取り、本ブランチ内の v0.6 は取り込み時に v0.7 へ繰り下げる
- develop の guard 試験 2 件(#125 由来)は別 fix の方針を維持(本ブランチでは `test_product_rls_paths_remain_in_develop_baseline` を develop の版のまま)


## ステップ 3(2026-10-14)

- **develop の取り込み**(`8607eec7`): #130(U-F8 統合後の guard 試験の修正 = 「develop の guard 試験 2 件は別 fix」の着地)がステップ 3 で触る `tests/test_core_guard.py` と重なるため先に取り込んだ。衝突は Claude が解消(関数名と U-F8 の包含検査は U-S1 側、隔離履歴の「未登録 → 宣言のみ → 登録済み」の段は #130 側を残し、宣言のない領域は空の追加として扱う)。直接編集のため `codex_run.py review normal` を通し、**可決(P0 0 / P1 0 / P2 0)**。取り込み後、develop で赤だった 2 件も含めて `tests/test_core_guard.py` は green
- **ステップ 3 を 2 コミットに分けた**: `verify_area_path_baseline()` は `.claude/core-areas.json` と基線定義(`scripts/core_guard.py`・`tests/test_core_guard.py`)を同一コミットで変えると拒否する(Codex が一時リポジトリで実測)。U-F8 の前例(#125 の「検査準備」「登録」)に倣い、`ec4d0969`(JSON だけ — 既存 235 件 green)→ `b1f1e3f6`(登録後の検査を足す — 236 件 green)の順にした。計画書のステップ表の「1 ステップ = 1 コミット」からの逸脱は guard の制約による
- 実履歴(origin/develop..HEAD)に `verify_area_path_baseline` を掛けて通過。`ruff check .`・`ty check` green
- ハーネス全件: `tests/test_check_authz_catalog.py` に既知の偽の赤(「HEAD の履歴に staged 製品資産がありません」— develop を第 2 親にマージしたブランチだけで出る)。それを除いた全件で **`tests/test_check_design_propagation.py` の 1 件が赤** — ステップ 1 の sync-protocol v0.6(10-3 を「保存済み結果再掲後の**範囲ごとの**意図件数」へ)で旧文言の部分一致が外れた。ステップ 1 の時点では `check_design_propagation` スクリプトだけを回し、ルートのテストファイルを回していなかった(取りこぼし)
- **ステップ 1 の是正**: 期待文字列を新しい本文へ合わせた。Claude の直接編集のため `review normal` → P2 1 件(「範囲ごと」の改訂を 8-1・10-2・10-3 で固定する表明が無く、単数の旧文言でも通る)を**採用**し、`対象範囲ごとに 1 件だけ永続化する`(8-1)・`範囲ごとの安定した意図 ID の全集合`(10-2)・`範囲ごとに安定した意図 ID で 1 件だけ永続化`/`安定した意図 ID の全集合・各行の永続状態`(10-3)の表明を足した。215 passed。反映後の再レビューは行っていない(P2 の表明追加のみ)
- backend の DB 不要の全件: 34 failed + 10 errors = 既知の偽の赤 44 件だけ(全件が「staged 製品資産がありません」)。1291 passed

## ステップ 4(2026-10-14)

- 1 回目の委任は呼び出し側のセッションが落ちて中断。途中の差分を Codex に点検させて完遂した
- **draft PR #132 を先に開いた**(山田正輝の判断 2026-10-14 — #114 と同じ運用)。凍結資産の受理記録に PR 番号が要るため。受理記録は PR #132 の 1 件(承認 山田正輝・2026-10-14)で、ステップ 22 で本 PR の全変更を覆う形へ導出し直す
- 変更: `base-allowlist.json` の条件 2 に `owner_paths`(`backend/src/pitchlog/sync/*`・`backend/src/pitchlog/repositories/sync_apply.py`)。検査器は owner_paths と検査時点の `.claude/core-areas.json` の sync-protocol の paths の**両方**に一致するファイルだけ条件 2 を適用しない(core-areas.json が無ければ免除しない)。条件 1・3・4 は所有パス内でも効く。`backend/tests/...` は TB002 の走査対象外なので所有宣言に入れない
- 検査器の変更で 8 資産(base-allowlist ほか、frozen_projection の external_files に検査器を持つ 7 資産)の凍結射影が動き、revision を上げた。backend の生成定数 3 ファイル(`runtime_contract.py` は生成器で再生成、`repository_contract.py`・`tenant_context_contract.py` は生成器が無いため資産から同期 — `docs/features/runtime-contract-switch/design.md:278`)を追随
- **敵対レビュー**: 1 回目 P1 1 件(owner_paths だけを広げると core-areas に登録済みの `db/engine.py` まで免除される)→ **採用**: 検査器に承認済みの 2 件を定数 `APPROVED_CONDITION2_OWNER_PATHS` で固定し、集合が一致しなければ拒否。負例(追加・欠落・置換)。2 回目 **可決(0 件)**
- 観察(ステップ 9 へ): 条件 4(TB004)は所有パス内でも効く。`sync/invalidation.py` の識別子が `invalidate*`・`cache_invalidation` に当たる場合は、既存の公開シンボル・許可 call の経路で通るかを確認する(`scripts/check_tenant_boundary_bypass.py:4207` 付近)
- 検査: 迂回検査・凍結履歴・凍結 archive・センサス 571 passed / backend の DB 不要の全件は既知の偽の赤 44 件以外 green / root の ruff・ty green

## ステップ 5(2026-10-14)

- design.md 4 節は 10-11 時点の実測。委任前に Codex に現状を実測させた: **JSONB の不変表現への実体化は既存**(`base.py` の `_materialize_value`)・**FOR UPDATE は U-M2 の限定形だけ既存**(`lineup_memory.py`)・**複合主キー UPDATE と適用中の印は未導入**
- 変更: `OperationRegistration` に `primary_key_bindings`・`for_update`・`use_capability_lock_shape`。UPDATE と行ロックは**正本の ORM の `Table`(`is` で照合)の主キー全列の等値**で行を識別する(宣言の有無を問わない)。主キー bind と SET bind は互いに素、テナント列の主キー束縛は文脈から注入する bind 名だけ。FOR UPDATE は宣言と文の一致・通常ロックのみ。U-M2 の 2 登録は限定形を明示宣言。`transaction.py` に適用中の印(ContextVar)と、印があるときの新スコープの拒否(`_sync_apply_active`)。repository-contract を改訂し、PR #132 の受理記録 1 件・snapshot・比較 corpus・生成定数を取り直した
- **敵対レビュー**: 1 回目 否決(P1 2・P2 1 — 宣言なし UPDATE の主キー部分省略 / 主キー bind と SET bind の共用・テナント主キーの bind 矛盾 / U-M2 の表名の直書き)→ すべて採用。2 回目 否決(P1 1 — 登録側で作った同名の別 `Table` で主キー全列検査をすり抜けられる)→ **採用**(正本の `Table` と同一性照合)。**この最終反映は上限到達のため再レビューを受けていない** — PR の人間の逐行確認で受ける
- 検査: 関係テスト 304 passed / 凍結資産一式 571 passed / backend の DB 不要の全件 1318 passed(失敗は既知の偽の赤 44 件だけ)/ backend と root の ruff・ty green / `backend/tests/conftest.py` 差分 0 行。**DB 必須の試験はローカル未実行**(CI に任せる)

## ステップ 6(2026-10-14)

- 変更: `sync/model.py`(要求・A5・B1〜B14・ACK・P3 結果の不変型。**S-1 の外形だけを型の生成境界で検査**し、V12・V5〜V11 と D4・復旧世代の値の照合は処理段階へ — TSK-331 の決定。欠落 `ABSENT` と JSON の `null` を区別。P3 の結果は受理型と拒否型に分け、受理型で I6 の全項目を必須)/ `sync/ports.py`(ポート 4 種・`PortWriter` — 内部の発行用の印と閉鎖後の拒否・登録表 `PORT_IMPLEMENTATIONS` は空)/ `sync/port_guard.py`(登録表の照合と import 閉包の静的検査)。製品にポートの既定実装なし
- **ポートが使う token 型の契約を U-S1 で確定**(敵対レビュー 1 回目 P1): ポートが使う token 型は sqlalchemy・登録処理を import しないモジュールに置き、登録は repositories 側に置く。**ステップ 7 の同期表の token はこれに従う**。U-R1・U-X1 へ引き渡す(TSK-392 への追記が要る)
- **敵対レビュー 3 回 + 人間の裁定**:
  - 1 回目 否決(P0 2・P1 4): `__module__` 詐称 / 動的 import での迂回 / `PortWriter` の発行と期限 / token 配置と import 禁止の衝突 / S-1 の外形 / P3 受理型の I6 → すべて採用(登録表を「モジュールとクラス」の同一性照合に、標準ライブラリを allowlist に、など)
  - 2 回目 否決(P0 1): 許可した `typing.get_type_hints` が注釈文字列を評価して `pitchlog.db.engine` を import できる → 採用(許可を「モジュールと名前の組」へ)
  - 3 回目(P0 例外)否決(P0 1): `import pitchlog` の属性連鎖で `create_database_engine` に届く → **山田正輝の裁定(2026-10-14)「直して打ち切る」**: pitchlog のモジュールをオブジェクトとして扱うことを全面禁止(モジュールでない名前の import だけ許可)し、**静的検査は補助であって安全の境界ではない**と位置づける。境界は (a) 登録表を持つ `sync/ports.py` が core-areas の sync-protocol に属し、ポートの登録はコア領域の変更として敵対レビューと人間の逐行確認を経ること (b) U-X1 が本物の投影ポートを作るときに入れる DB 側の遮断(適用核の印を要求するトリガ)。**追加レビューなし**(最終反映は再レビューを受けていない)
- **残る穴(逐行確認と PR 本文への申し送り)**: 実行時の monkeypatch / 許可名や callable の組み合わせ / Python の反射・descriptor・decorator・metaclass / 別の実行単位への処理委譲(R-12)。静的検査ではこれらを遮断できない
- 検査: 型・ポートの試験 118 passed / backend の DB 不要の全件 1436 passed(失敗は既知の偽の赤 44 件だけ)/ 迂回検査 ok / backend と root の ruff・ty green / 凍結資産・`conftest.py` 差分なし

## ステップ 7(2026-10-14)

- 変更: `repositories/sync_apply.py` に同期表 9 表の operation(read・insert・update・共通ロック順の 2 つの行ロック — 試合行と記録権世代行)を登録し registry に接続。token 型は sqlalchemy を import しない `sync/tokens.py`(ステップ 6 の契約)。同期経路の意図 insert は #114 の token と別型で同じ capability。④共有集計は専用 token で対象テナントを文脈の `tenant_id` に固定。意図 ID は `sync:<イベント識別>:<範囲>`(`sync/intent_ids.py`)。未配信一覧は `pending` とキーセット(`intent_id > :after`)・上限。T4 は投影ポートの責務として SQL operation を作らない。`contracts/authz/` は変更なし。repository-contract・census を改訂し PR #132 の受理記録 1 件・snapshot・比較 corpus・生成定数を取り直した
- **敵対レビュー**: 1 回目 否決(P0 1・P1 2 — 他テナントの共有集計の意図を作れる / 未配信一覧に同期経路以外の意図が混ざる / 次ページを取れない)→ すべて採用。うち P1-2 は Codex が「DDL に発生経路の列がなく、`LIKE` は認可の登録検査器が拒否」で停止 → **山田正輝の裁定(2026-10-14)「アプリ側で絞る」**: DDL と認可検査器は変えず、同期の意図 ID に接頭辞 `sync:` を付け、受け取る側の純関数で判定。2 回目 否決(P1 1 — 将来の B06 トリガー値 `sync…` との衝突)→ 採用(#114 の token の構築時検査で `sync` で始まるトリガー値を拒否)。**この最終反映は上限到達のため再レビューを受けていない**
- **今後の課題**: 未配信の意図の SQL 側の絞り込み(DDL の発生経路列、または認可検査器の限定 `LIKE`)。現方式では同期を通らない未配信の意図が溜まるほど、同期側の配信が読み飛ばすページが増える
- 検査: 関係テスト 194 passed / 凍結資産一式 571 passed / backend の DB 不要の全件 1447 passed(失敗は既知の偽の赤 44 件だけ)/ 迂回検査 ok / backend と root の ruff・ty green。**DB の越境テストはローカル未実行**(接続設定なし・Docker 権限なし)— push 後の CI で確かめる

## ステップ 7 の是正・develop の取り込み・CI の是正(2026-10-14)

- **DB の越境テストが空洞だった**(Claude が push 後に検出): ステップ 7 の DB テストは `PITCHLOG_DATABASE_URL` が無いと skip する形で、CI はこの変数を設定しないため**CI でも常に skip されていた**。`backend/tests/db/` の使い捨て DB の fixture(`provisioned_product_catalog`)へ移した(`(ステップ 7/22 是正)`)。**以後の DB テストは最初から `tests/db/` の流儀で書かせる**。ローカルの DB テストは `PITCHLOG_TEST_ADMIN_DSN`(秘密設定 — Claude は読めない)が要るので Claude は実行できない — CI で確かめる
- **develop の取り込み**(#126・#128・#127 U-F5・#133): PR が DIRTY だと CI が走らず、ステップ 5〜7 の DB 動作を確かめられないため、凍結資産の取り込み費用を払って取り込んだ。窓口は U-S1 の宣言を採り、core-areas.json は自動合成(U-F5 は基線)。`tests/test_core_guard.py` の衝突 13 箇所は Codex が解消(245 passed)。tenant_boundary の入力は develop 側で変わっておらず、受理記録はそのまま
- **CI の DB テストで 12 件の失敗**(run 38528642526): ステップ 5 の「正本 ORM の Table との同一性照合」が、合成表で基底を試す既存試験を拒否(10 件)/ ステップ 7 の越境試験の INSERT の rowcount の仮定(2 件)。製品の検査は弱めず試験側を追随(`(ステップ 5/22 是正)`)。**ステップ 5 の敵対レビューでも、ローカルの DB 不要の全件でも見えなかった** — DB を伴うステップは CI を回すまで完了と言えない

## ステップ 8(2026-10-14)

- 変更: `sync/idempotency.py`(入力イベントの正規化 JSON の指紋・D5 の 3 分類〔保存済み結果候補・B3b/B13 候補・未使用〕・要求内の先行分類。導出した拒否理由は指紋に含めない)/ `repositories/transaction.py` に登録済み operation を SAVEPOINT 内で実行する入口(台帳 INSERT が D5 を含む主キー・一意制約に衝突したときだけ戻して再照合、他の DB エラーは伝播)/ TB005 の SAVEPOINT 許可で base-allowlist を改訂し PR #132 の受理記録 1 件・snapshot・比較 corpus を取り直し
- DB テスト(`tests/db/test_sync_apply_idempotency_boundary.py`): 3 分類・順序固定の並行試験 2 種(テスト側の Event で固定、別の試合の同じ D5)・他テナントの同じ D5。**ローカル未実行 — CI で確かめる**
- 敵対レビュー 1 回目 **可決(0 件)**
- 検査: DB 不要の全件 1443 passed(既知の偽の赤 44 件以外)/ 迂回検査・凍結一式 green / backend と root の ruff・ty green

## ステップ 8 の CI 是正とステップ 9(2026-10-14)

- **CI(run 38534439094)**: 前回の DB テスト 12 件の失敗はすべて解消し、ステップ 8 の DB テスト(並行試験を含む)も green。新たに 1 件 — ハンドルの公開メソッドを固定する既存試験が、ステップ 8 で足した `run_in_savepoint` で落ちた。Claude が試験を直接修正(`(ステップ 8/22 是正)`)し、`review normal` の P2 2 件(引数の種類の固定・`run_in_savepoint` での未登録 token と失効済みハンドルの拒否)を採用
- **ステップ 9**: `sync/invalidation.py` に P3 と D1 付き経路の記録部(範囲ごとに 1 行を呼び出し元のトランザクションへ。INSERT は SAVEPOINT で保護し、SQLSTATE 23505 かつ `pk_invalidation_intents` のときだけ先着行を再読)。#114 の範囲名の写像を公開して共有。`cache-invalidation-contract.json` の配信状態を `pending`/`delivered`・検索列を `delivery_status` へ、`durable_intent` の同期経路の規則を `B03` に追随。PR #132 の受理記録 1 件・snapshot・比較 corpus を取り直し。TB004 は検査器を変えず既存の許可経路で通す。発火条件とロック順は記録部に持たせず、後続の呼び出し元(ステップ 10・13)が決める
- **敵対レビュー**: 1 回目 否決(P1 2 — 同じ意図 ID の並行挿入でトランザクション全体が失敗し得る / DB テストが期待 ID を実装と同じ関数で作っていた)→ すべて採用(SAVEPOINT 保護と並行 DB テスト / 期待 ID を材料から文字列で組み立て)。2 回目 **可決(0 件)**
- 検査: DB 不要の全件 1457 passed(既知の偽の赤 44 件以外)/ backend と root の ruff・ty green / 凍結一式は 570 passed・1 件未達 — **develop に #129 の凍結履歴が入り、`test_repository_is_green` の履歴 prefix の比較が origin/develop とずれた**(merge-base を比較元にすると通る)。次の develop の取り込みで解消する。**DB テストはローカル未実行 — CI で確かめる**

## develop の取り込み 2 回目 — #129 と data-model の版の繰り下げ(2026-10-14)

- ステップ 9 の push 後、develop に #129(U-T1 / TSK-543)が入り PR が再び DIRTY。CI を走らせるため取り込んだ
- **data-model の版の衝突(2 度目)**: #129 が data-model **v0.9** を 2026-10-13 に先に確定させていた。本ブランチの TSK-391 の改訂(v0.9 で 2026-10-14 承認)を **v0.10 へ繰り下げた**(内容は承認時のまま・版番号だけ)。変更履歴に繰り下げの注記、本文の版の参照(8 箇所)・README・sync-protocol の変更履歴の参照・計画書・設計伝播の試験のコメントを追随。**教訓は既存の memory「起案前に未マージ分も含めた最大版を実測」と同型** — 承認後に別の PR が同じ版を先にマージすると、取り込みのたびに繰り下げが要る
- 凍結資産: `cache-invalidation-contract.json` は #129 の B06 トリガー 5 とステップ 9 の B03 同期経路の規則・配信状態の語彙を合成 / `base-allowlist.json` は #129 の受理記録を保持し、PR #132 の 1 件を比較元 `93e1482a` で導出し直し / schema-manifest・shared-preconditions の digest を取り直し / N3 受入シートは判定を引き継いで再生成(本ブランチ 104 件 + develop 1 件)
- 衝突解消の敵対レビュー 1 回 **可決(0 件)**。関係テスト 1044 passed、backend の DB 不要の全件は既知の偽の赤 44 件以外 green

## CI の確認とステップ 10(2026-10-14)

- **CI(run 38549938342・head `078db203`)**: core-guard 以外すべて green。**backend は実 DB 込みで 1973 passed** — ステップ 1〜9(5・7・8 の是正を含む)の DB 動作を確認した。core-guard は PR 本文の人間の逐行確認のチェック待ち(draft のため想定どおり)
- **ステップ 10**: `sync/prefix_path.py` に P1 の 1 イベントの適用(T1・T6 の台帳の確定結果は同じ INSERT / T2 / T3 は世代行を `FOR UPDATE` で読み直して前進 / T4 は登録確認済みの投影ポートへ `PortWriter` 経由 / T6 の一時 ID 写像は別表へ同じトランザクション / D1 付き経路の発火は D3 が前進したときだけ / ロック順は試合行 → 記録権世代行)
- **敵対レビュー 3 回**:
  - 1 回目 否決(P0 3・P1 2): **墓標・改訂が確定済みイベントの置換に使える(正本 SP の W2 違反)** / V9 と別引数の不一致 / 拒否位置の改訂のテストが空洞 / 連番の判定が記録権より先 / 一時 ID 解決が任意の集合に依存 → すべて採用。**design.md 6 節の「改訂: 旧版の `replaced_at` を設定する」は W2 に反していたので Claude が直した**(墓標・改訂は内容拒否の始末に限る)
  - 2 回目 否決(P0 1・P1 2): 墓標・改訂の V10 を照合していない / 拒否原本の試合・D4 の負例がない / W2 違反を境界結果へ渡す契約がない → すべて採用(V10 を必須にして拒否原本と照合、別試合・別 D4・他テナントの負例、`P1PreconditionError.category` で区別し、境界結果への写像の申し送りを design.md 6 節へ)
  - 3 回目(P0 例外)**可決**
- **申し送り**: `w2_violation` / `recording_rights` / `other` の境界結果への写像は、ステップ 12(T9)とステップ 15(公開入口)で正本 6-2・6-3 と照合して確定する
- 検査: DB 不要の全件 1461 passed(既知の偽の赤 44 件以外)/ 迂回検査・凍結一式 green / backend と root の ruff・ty green。**DB テスト 19 件はローカル未実行 — CI で確かめる**

## ステップ 10 の CI 是正・ローカル DB 試験のスパイク・ステップ 11(2026-10-14)

- **ステップ 10 の CI(run 38561951910)で DB 試験 8 件の失敗**: `operation_events` の `ck_operation_events_state_diff_by_kind` 違反 7 件 + 期待文言 1 件。原因は**実装側** — V8 がないとき Python の `None` を JSONB の `null` として束縛していた(`state_diff IS NULL` を満たさない)。固定 SQL の NULL を書く形にし、種別表に従う V 条件(V6・V8・P1 で禁止の V11・通常イベントの V10)を保存前に検査して黙って捨てない形へ(`(ステップ 10/22 是正)`)。是正の敵対レビュー(Codex)1 回 — P1 2 件(V11 を黙って捨てる / V8 必須種別の実経路の試験がない)採用。`state_correction` は種別表で禁止(FR-040 未採用)のため拒否の試験にした
- 是正とステップ 11 の分離のため、ステップ 11 の差分を一時退避してから是正をコミットし、戻した後の `prefix_path.py` の衝突を Codex が解消
- **スパイク(利用者の許可 2026-10-14)**: ローカルで DB 試験を回せるようにした。`backend/tests/db/` の一部の fixture はシェル環境の `PITCHLOG_TEST_ADMIN_DSN`・`PITCHLOG_TEST_ROLE_DSN` が指す**共有 DB** を使い被検査ロールを作るため、**別タブの実行中は「被検査ロールがテスト開始前から存在する」で全件 setup エラー**(実測 — 共有 DB に被検査ロールで接続中のセッションがあった。触れていない)。**専用の使い捨て Postgres(`pitchlog-391-spike-db`・127.0.0.1:55491)を立てて両 DSN をそこへ向ける**と、U-S1 の DB 試験 34〜54 件が 2〜3 分で green(CI は約 20 分)。以後 push 前にローカルで回す
- **ステップ 11**: `sync/ordering.py` に P2 の T5(O1 = 試合行ロックの下での D2 の採番 / O2 = 指定位置が空いていればその値、重なれば直前の隙間、尽きたときだけ局所再採番、bigint 上限では左の空き / O4 = 同値で B3・A5「拒否」、投影を止めて戻す)。T1〜T4・T6・D5 の再照合・意図・V 条件の検査は `prefix_path.py` を共有(コピーなし)。内容の検査(V5〜V11)は D5 の分類の後
- **敵対レビュー(Codex)2 回**: 1 回目 否決(P1 2 — 隙間が残っていても再採番 / V5 検査が D5 分類を迂回)→ 採用。2 回目 否決(P1 2 — V9 の検査が D5 分類を迂回 / bigint 上限の試験が更新先の誤りを検出しない)→ 採用(同型の指摘が続いたので共通経路の検査順を全点検)。**最終反映は上限到達のため再レビューなし** — ローカル DB 試験 54 passed で確認
- **レビューの運用変更(利用者の許可 2026-10-14)**: 以後のステップ単位の敵対レビューは**複数ステップをまとめ、Claude のサブエージェントが実施**する(12〜15・16〜21・22)。PR 段階の敵対レビューと正本の確定ゲートは Codex のラッパーのまま
- **RG1 の共有直列化点(U-R1 への回答 2026-10-14)**: 提案(③-a はロックなし、⑧ は試合行 → 世代行の後に RG1 行を FOR SHARE で再読、復元開始は RG1 行だけを閉鎖して確定)は U-S1 のロック順と矛盾せず、デッドロックの輪もない。**U-S1 側の前提作業 2 つ**: ① 基底が FOR SHARE を拒否する(`repositories/base.py:177-182` — ロックの種類の宣言の拡張が要る。**計画書のステップ表にないので、U-S1 で持つなら計画の改訂と承認が要る**)② `RecordingRightsPort.is_restoration_active` が 1 本で、③-a と ⑧ を区別できない(ステップ 14 で口を分ける)。確定前の留意: FOR SHARE ちょうど(FOR KEY SHARE は復元開始の FOR NO KEY UPDATE と衝突しない)/ 復元開始の最初のトランザクションは RG1 行以外に触れない / 後着の共有ロックの追い越しで復元開始が待たされ続けうる(推論・要 DB 試験)/ 同期を通らない書き込みも RG1 は FOR SHARE だけに揃える

## 他単位との接続契約(2026-10-15)

**Claude向け申し送り — U-R1・C1 への回答と記録(2026-10-15)**: 計画書 8 節に表で記録した(範囲の変更ではない)。
- **U-R1(TSK-392)**: ③-a・⑧ の Port 署名(`read_rg1_before_d5(writer) -> bool` / `check_rg1_before_commit(writer) -> bool`・`game_id` なし・True = 通過・False と Port の例外はスコープ全体を取り消して B7〔P3 は B10〕)= **採用**。呼び出し位置(スコープを開いた直後・どのロックよりも前に PortWriter を発行 → ③-a〔試合行ロック・D5 照合より前〕→ 試合行 → 世代行 → ④ → 書き込み → ⑧〔commit 直前〕。P1・P2・P4・P5・P3 の全経路で両方。内部配信は ③-a だけ)= **採用**。TSK-550 の固定関数を呼ぶ `PortWriter.run_function(token)` = **条件付き採用**(固定関数の exact token 型だけ・同じスコープへ委譲・token 型はポートの token 契約と port_guard を満たす・`sync/ports.py` の変更はコア領域の変更 — U-R1 新ステップ 6)。失効条件(スコープの終了で失効・失効後は拒否)= **採用**。回答は TSK-391 の照会スレッド(コメント `3f993b75-e687-8116-a83e-001d29547fdc`)
- **U-G1(TSK-395)**: 作成側の RG1 契約 `79e3da4a` は受理済みのまま維持(U-S1 は同期経路だけを答えた)
- **C1(TSK-528 追補)**: `CAP:tenants:read` の `TenantProfileReadToken` / `TENANT_PROFILE_OPERATIONS` の 1 件 = **採用**。#132 の head で、`tenants.c.id = :tenant_id`(`tenants` は `tenant_id` 列を持たず `id` がテナント ID)の登録がテナント条件の検査と登録文の検査を通ることを実測。変更箇所は #114 と同じ範囲。C1 の「非共有部分を先行し、共有 registry と凍結資産は #131 → #132 の統合後」も採用。未確認: `tenants` の RLS と SELECT の付与(C1 の DB 試験で)
- **実装**: U-S1 ステップ 14(実装中 — 上の契約どおりに委任)・15
- **気づき(判断待ち)**: 計画書 7 節 **A-1(承認済み)は D1 付き経路の意図 ID を `<トリガー>:<イベントの D5>:<範囲>`** と定めるが、**ステップ 7 の実装は `sync:<イベント識別>:<範囲>`**(固定の接頭辞 `sync` — 裁定「アプリ側で絞る」で同期経路の意図を判定するため)。D5 と範囲から決定的に導く点は同じ。人間の判断を仰ぐ
- **以前の「Claude 向け申し送り」の別ファイル**(`/tmp/pitchlog-claude-handoff` の未追跡ファイル `docs/worklog/2026-10-13-claude-mvp-handoff.md`)は、worktree ごと消えていてディスク上に無い(2026-10-15 確認・Claude は消していない)。以後の申し送りは本作業ログの「Claude向け申し送り」段落に書く(他単位の作業ログと同じ形)
- **裁定(山田正輝 2026-10-15)**: A-1 の意図 ID の文字列形式は **`sync:` を採る**(実装どおり)。計画書 8 節の末尾に記録

## Codex の停止とステップ 15・sync-protocol v0.8 の起案(2026-10-15)

- **Codex が使用量の上限に到達**(ステップ 15 の最終検証中 — 「try again at Oct 21st, 2026 2:37 PM」)。ステップ 15 の実装は完了しており、Claude がローカルの専用 DB で DB 試験を回して、注入点 `after_transaction` の試験の意図の数え方(①以外の範囲は `game_id` を持たないのに試合で絞っていた)を直接直した(43 passed)
- **裁定(山田正輝 2026-10-15)「Claude が実装を続ける」**: 2026-10-21 14:37 までは、U-S1 の残り(ステップ 16〜21)を Claude が直接実装し、Codex の review normal の代わりに Claude サブエージェントの敵対レビューを通す。**ADR-001 のモデル対応表からの逸脱**として PR 本文にも明記する。PR 段階の敵対レビューと正本の確定ゲートは 10-21 以降に Codex で行う
- **ステップ 12〜15 のまとめた敵対レビュー**: Claude サブエージェントで実施中
- **裁定(山田正輝 2026-10-15)「改訂案だけ先に作る」**: 計画書 4 節(154 行)は「ステップ 15 の後・16 の前に sync-protocol 10-3 の資産構造の改訂(v0.8・R-10)を /finalize-doc で確定させる」と定めるが、確定ゲートの敵対レビューは Codex で 10-21 まで使えない。**改訂案を in-review で起案し、その案に従ってステップ 16〜21 を進め、確定ゲートは 10-21 以降に Codex で通す**(指摘が出たら資産側も直す)。**計画の順序(確定 → 16)を入れ替えた**
- **起案の内容**: 10-3 の資産契約に case 構造・共通の期待フィールド(`prefix`・`idempotentResult`・`temporaryIdMapping`・`recordingRight`・`tElementCommitment`)・`tElementCommitment`(T の内部単位・`no-write`/`no-change`)・P5 の判別共用体・到達性(`expectedReachability: "unreached"`)・注入点の組の導出元(8-1 の経路表 = `R-TXN-ROUTE`)とトランザクション外の 3 注入点の exact-set・契約検査と結果検査の分離・母集合の組の exact-set を足し、比較単位を `scenarioId × caseId × 注入対象 × 観測点 × expected の全フィールド` へ。意味規則は変えない。変更履歴 v0.8(射程宣言つき・in-review)・frontmatter `in-review`・README の索引を更新。出典は design.md 7 節(承認済みの計画の詳細設計)
- **適用版の暫定記録(設計書 7.3-1)**: ハーネス設計書 **v1.19**(条文コミット `945384c5` — 2026-10-08 時点の最新)。初回の敵対レビュー(10-21 以降)の時点で異なっていれば更新してから開始する
- 検査: `check_docs_status`・`check_design_propagation`・`check_shared_preconditions`・`check_authz_catalog` ok、設計伝播・文書状態・文書被覆の試験 333 passed

## ステップ 12〜15 のまとめた敵対レビュー(2026-10-15 — Claude サブエージェント・Codex 停止中)

- **1 回目 否決(P1 3・P2 6)**: ① gap より後ろの既存 D5 の候補(B3b・保存済みの退避)を ⑥ より前に外部結果として確定していた ② B4 の要求で既存 D5 を再掲せず、2 件目以降の未使用 D5 を退避しなかった ③ 保存済み退避の再掲が要求の境界を B4 にして後続を止めた(U-14 違反)/ P2: 再掲でも ⑧ を呼ぶ・ACK の D3 が現世代・配信ポートにテナントと選択子がない・記録権の競合が素の例外・⑧ の全取消の DB 試験が P1 だけ・注入試験が選手行を数えない → **P1 3 件と P2 4 件を Claude が直接直した**(公開入口で ⑥ を経路より先に判定 / ⑤ 不成立の要求は境界 B4・既存は再掲・未使用は全件 T8・止めない / 退避の再掲は境界を決めない / 再掲で ⑧ を呼ばない / `DeliveryIntent`〔tenant_id・intent_id・範囲・選択子〕を配信ポートへ / P2・P4・P5 の ⑧ の全取消の DB 試験 / 選手行の数)。直す途中で Claude 自身の誤りにも気づき、⑥ の「欠落」を「要求の中で直前に処理した D1 の次」に改めた
- **2 回目 否決(P1 2・P2 4)** — どちらも 1 回目の直しが生んだ欠陥: ① **P4 の要求の再掲を P1 の指紋で照合し、保存済みの退避が B3b に化けた**(P4 の退避は P4 の指紋)→ P4 の要求の再掲は拒否・退避の経路(P4 の指紋)へ ② **⑥ の起点が現世代の D3 なので、引き継ぎ後の旧世代の再送が B2 に化けて永久に再送する**(D3 は `(試合, D4)` ごと — SP R1)→ 現世代の番号を読み、要求の D4 が現世代でなければ既存 D5 の再掲に入口の ⑥ を掛けない / P2: B4 の要求に含まれる B3b・保存済みの拒否・退避の写し方 → DB 試験(退避は退避を再掲・異内容は拒否〔理由つき〕・境界は B4・`b3_branch` なし)/ 退避の再掲の試験の判定を `(B1, 0)` へ強める / ⑧ の全取消の試験を実際の P4 の要求にして陽性対照を置く / 配信の試験で選択子(game_id・chart_kind)を見る — **すべて採用**。**上限到達のためこの最終反映は再レビューを受けていない** — ローカル DB 試験 128 passed で確認。PR 段階の Codex の敵対レビュー(10-21 以降)で受ける
- **送り(直していない)**: ACK の D3 を要求の D4 の世代の値にすること — ⑥ の判定は直したが、ACK に載せる D3 は現世代のまま。D4 の物理形式・世代の読み取り operation は U-R1 の決定事項なので、U-R1 の接続時(U-R1 新ステップ 6)に揃える / 記録権の前処理と取引内の判定の競合で素の例外になる件 — HTTP 入口(TSK-331)の例外の写像で扱う
- **Claude サブエージェントのレビューについて**: 別タブ(238)が「Claude サブエージェントのレビューは Codex の敵対レビューの指摘を取りこぼす」と記録している。本件は 2 回で P1 5 件を拾ったが、取りこぼしの可能性は残るので、PR 段階で Codex の敵対レビュー(10-21 以降)を必ず通す
- 検査: DB 不要の全件 1583 passed(既知の偽の赤 44 件以外)/ U-S1 の DB 試験 + トランザクション試験 128 passed / backend と root の ruff・ty green / 迂回検査 ok(merge-base 比較)

## ステップ 16 — (d) 資産契約の検査器(2026-10-15 — Claude が直接実装・Codex 停止中)

- 置き場: `backend/tests/test_sync_apply_failure_contract.py`(既存の glob `backend/tests/test_sync_apply_*.py` に収まり、core-areas の窓口を使わない)。契約検査 `validate_failure_scenario_contract` と結果検査 `validate_failure_scenario_result` を別関数にし、母集合 `validate_population`・注入被覆 `validate_injection_coverage` を exact-set で持つ。ステップ 19 の runner はこのモジュールを読み込む
- 資産の形(`schemaVersion: 2`): 根 = `schemaVersion`・`scenarioId`・`version`・`input`・`cases`・`comparisonUnit`。`input` に `p5Branch` を足して 12 件(P5 以外は省略理由)。case = `caseId`・`faultInjection`(`target`・`injectionPoint`・`stopOperation`・`restartOperation`・`expectedReachability`)・`observations`。注入対象は `transaction`(経路 × T 要素)/ `outOfTransaction`(P3 の 3 点)/ `client`(操作)。比較単位 = `scenarioId × caseId × injectionTarget × observationPoint × expectedField`
- 結果の形: `{scenarioId, cases: [{caseId, hookCalls, observations}]}`。到達しない注入点は `hookCalls == 0`、到達する注入点は 1 回以上。契約が省略理由を書いたフィールドは結果に現れてはならない
- **Claude の判断(逐行確認・PR 段階のレビューで見てほしい点)**:
  - **省略できるフィールドの表**(`OMITTABLE_FIELD_IDS`): クライアント側 = 後半 5 件 / P1・P2 = 端末側 4 件(`queue`・`lock`・`acceptanceDisplay`・`reinputAvailability`)/ P3 = 端末側 4 件 + `d1`・`prefix`・`temporaryIdMapping`・I6 の 6 件 / P4・P5 = 端末側 4 件 + `temporaryIdMapping`。**sync-server-apply design 3-2 の「P1/P2/P4/P5 は 10 件すべて実値必須」から外れる**: サーバー側 runner は端末を観測しないため。正本 v0.8 草案の「経路によって意味を持たないフィールドは省略理由を明示して省略してよい」の範囲に入るかは確定ゲートで問う。`tElementCommitment`・`idempotentResult`・`recordingRight` と P1・P2・P3 の無効化意図のフィールドはサーバー経路で省けない
  - **P1・P2 に加わる期待フィールド 4 件**(正本 10-3「契約」v0.6 の無効化意図): `invalidationIntentIds`・`invalidationIntentRows`・`intentCountsAfterReplay`・`intentCountsAfterFullDuplicate`。**P3 の 13 件**: 復旧世代照合・意図 ID・各行・配信状態・消費側反映・配信完了記録・再掲後の件数・I6 の 6 件(4 項目 + 保持期限 + 退避状態)
  - **T 要素の内部単位**(`T_ELEMENT_UNITS`): 実装の書き込み単位に合わせ、P1・P2 の T2 = slot・event、T6 = result・mapping、P3 の T7 = targetVersion・intents、P4 の T8・P5 の T9 = ledger・original。P3 の T2・T6 は単一値
  - **到達性**: 到達しない注入 case は、注入対象の T 要素の全単位が `no-write` / `no-change`。到達する注入 case は確定・非確定の観測を少なくとも 1 つ持つ。B3b は到達するトランザクション内 case を宣言せず、T9 の到達しない case を必須にする。B3a は T9 の到達する case を必須にする
- 合格条件の確認: 正例 5 種(クライアント側・P1・P3・P5 の B3a / B3b)と結果検査の正例、負例(部分確定・T 集合の食い違い・孤立した観測点・重複注入・B3b の値関係 3 種・判別共用体・到達性・P3 / P1・P2 の固有フィールドの欠落・語彙の外・誤字・schemaVersion と構造の組・母集合と注入被覆の 1 件変異)の 56 件 green。**検査器の分岐を 8 か所無効化する変異でそれぞれ赤**を確認(均一性・B3b の同一内容・重複注入・呼び出し 0 回・省略可否・18 組の被覆・到達しない対象の状態・B3b の到達 case)
- 実在する資産の照合(ディレクトリの走査・宣言した被覆と資産の case の一致)はステップ 17・18 で足す(この時点の資産は旧構造の 4 件だけ)
- 検査: backend の ruff・ty green / DB 不要の範囲は既知の偽の赤 44 件だけ(共有 DB に他タブの被検査ロールが残り、DB 試験は setup で ERROR — 本変更は DB 試験に触れない)

## ステップ 17 — 既存 4 資産の版移行と frontend の追随(2026-10-15 — Claude が直接実装)

- 4 資産を `_v2.json`(`version: 2`・`schemaVersion: 2`)へ一度だけ移した。旧 `faultInjection` は 1 件の case(`caseId` = `concurrent-confirm`・`freeze-then-terminate`・`input-while-waiting`・`append-failure`、注入対象 `{kind: client, operation: <旧 target>}`、`expectedReachability: reached`)へ、旧 `expected.observations` はその case の観測点へ移した。期待値の中身は変えていない。後半 5 件(`prefix`・`idempotentResult`・`temporaryIdMapping`・`recordingRight`・`tElementCommitment`)は省略理由つきで足し、入力に `p5Branch`(省略理由)を足した
- 同じコミットの中で「v2 を足す → 参照を移す → v1 を消す」の順にした(正本 10-3 の版付け — 旧版を参照するテストが残る間は消さない)
- frontend: `failureScenarioContract.ts` を case 構造へ。**深い意味検査(経路と T 要素・内部単位・P5 の値関係・母集合と注入被覆)は Python 側を正とし、TS は消費側として構造を検査する**(二重定義を避けるため)。共通の期待フィールド 10 件と、クライアント側で省けない 5 件だけを TS にも持ち、**Python 側の試験が TS の表を読んで一致を検査する**。結果検査は Python と同じ規則(省略したフィールドの不在・呼び出し回数と到達性)
- `failureScenarioAdapter.ts`: runner は case 1 件の結果(`caseId`・`hookCalls`・観測点)を返す。`hookCalls` は注入を実行した回数を配列の長さで数える(期待値のリテラルを adapter に書かない規則を保つ)
- spec: `_v1` の決め打ちを現行版の宣言表 `CURRENT_VERSIONS` に置き換えた(sync-server-apply design 3-7)。`prohibitions.spec.ts` の export 表を追随(値 9・型 10)
- 検査: frontend 全件 984 passed・vue-tsc・eslint・prettier green / Python の契約検査 58 passed(実在する 4 資産が契約検査を通る)
