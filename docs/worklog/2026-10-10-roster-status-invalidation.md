---
date: 2026-10-10
topic: TSK-447 在籍区分の入口とキャッシュ無効化の発火点(無効化意図の ID 導出規則と原子性の錨)
branch: feature/roster-status-invalidation
---

# 作業ログ: 2026-10-10 TSK-447 在籍区分の入口とキャッシュ無効化の発火点(無効化意図の ID 導出規則と原子性の錨)

## やったこと

### /task-start

- 既存 Notion タスク TSK-447(2026-09-24 起票・U-M1 から分離)に着手: https://app.notion.com/p/3e593b75e6878116ab33fc7eaadd64d9
- ブランチ `feature/roster-status-invalidation` / worktree `../pitchlog-worktrees/feature-roster-status-invalidation`(origin/develop `f79c14e0` 起点 = PR #95 マージ直後)
- 射程: TSK-447(イベント由来でないトリガーの意図 ID 導出規則と原子性の錨・正本 11-2 節の改訂・契約 `cache-invalidation-contract.json` の追随)+ U-M1 第 10 改訂で #95 から外した旧ステップ 11(在籍区分の入口〔プレビュー・適用〕と発火点 — FR-017・トリガー 14)。選手の削除(FR-018)は TSK-459 待ちで射程外
- 位置づけ: FR-017 はリハーサル最小集合 26 件に入り、#95 では判定対象外(U-M1 plan.md:650)なので本 PR でしか着地しない(master 2026-10-10)
- コア領域(テナント分離)

### /investigate

- 調査サブエージェント 6 本(下調べ 3 本 + 追加 3 本)の結果を [research.md](../features/roster-status-invalidation/research.md) に統合した
- 原典で確認した要点: 11-2 節の意図の永続化(`B03`・`B04`)は `I5`(P3)の永続化先として書かれている(`data-model.md:2232`)。発火条件の正である sync-protocol 8-5 の行は D1 付き経路と I5 の 2 つだけで(`sync-protocol.md:1356-1361`)、**同期を通らないトリガーの発火条件の正はどこにも無い**。契約の `durable_intent` は P3 の規則を 14 トリガーすべてに分岐なしで掛けている
- イベント由来でないトリガーは 9 件(5・7〜14)。U-M1 計画書の「7」と Notion の「少なくとも 6」はどちらも数え漏れ
- キャッシュ本体・配信先・意図表へ書くコードは無い。契約と DDL の語彙が食い違っている(既存の記録なし)
- 旧システムに在籍区分は無い(FR-017 はすべて新規)

### /plan

- 計画の骨格が分かれる 4 点を先に人間へ確認した(AskUserQuestion — 4 点とも推奨案)。plan.md 8 節 J1〜J4
- 計画書・design.md を作成。重さ分類 = コア領域。ステップ 5 本(正本の改訂案 → 契約と鍵の型 → 意図の記録と token → 入口と発火点 → 受理記録の最終導出)
- 認可カタログを触らずに済むことを確認(新しい token は経路を要さない — 先例 `CAP:games:read` の `GameTeamLinkReadToken`。HTTP の 2 経路は既存の `ROUTE:RECORD:players:read`/`:update`)
- コア領域の paths: 予定ファイル 18 本を `.claude/core-areas.json` の基線と fnmatch で突き合わせ、全件が既存 glob に当たることを確認(master の照会への回答)。`core_guard.py`・`core-areas.json` に触らない
- 計画レビュー 1 周目(敵対・全文): 否決(P0 1 / P1 8)。**全件採用**(周回 0 → 1)
  - P0: 9 トリガー共通の帰属では 8(全テナント)・10〜13(前後の和集合)の波及を表せない → `B06` を書き分け、帰属と鍵は 5・7・9・14 だけ定め、8・10〜13 は所有単位(U-A2・U-C1)へ送る(plan 8 節 A5 — J1 のうち帰属だけを狭めた)
  - P1: `B05` は既存 ID → `B06` / 契約で同期側の適用範囲も明示(2 集合が互いに素で和 14)/ corpus 再封印をステップ 2・3 にも / 固定期待値テストの更新を明記 / 一括 UPDATE・RETURNING は実行経路を通らない → 既存の 1 行 token を 1 件ずつ(余分な発火は許す — A3)/ TB004 の許可呼び出し一覧にも鍵を登録 / 12-4 の判定記録をステップ 4 へ
- 計画レビュー 2 周目(反映差分): 否決(P0 1 / P1 1)。**全件採用**(周回 1 → 2)
  - P0: 行の数と意図 ID の細部を 9 件共通にすると、同じ範囲に複数の鍵が要るトリガー(5・7)や複数テナントへ波及するトリガー(8・10〜13)で ID が衝突する → 共通則を「発火条件・原子性の錨・意図 ID の骨格(操作 ID を含み、操作の中で行ごとに一意)」に絞り、行の数と行の識別子はトリガー 14 だけ定めた(A5 を改めた)
  - P1: 読み取りの後の更新では競合時に余分に発火し、「値が変わらなければ発火しない」に反する → UPDATE の述語に「区分が実際に違う」を置き、更新件数で発火を決める(A3 を改めた・競合のテストを追加)
- 計画レビュー 3 周目(2 周目 P0 に限る — 設計書 6.3 の上限): **可決**
- **計画承認**: 2026-10-10・山田正輝(A1〜A5 を含む)
- master の訂正(同日): `AREA_PATH_ADDITIONS` は「置き換え式」で、#95 の 7 件が残っていても次の単位は自分の分へ置き換えれば通る。「窓口を空に戻す後続」は不要(当方が TSK-393 の完了報告で残件に挙げたのは誤り)

### ステップ 1(正本 11-2 節の改訂案)

- `docs/design/data-model.md`: 変更履歴に v0.7(in-review・射程宣言つき)、`B01` の節を同期経路に限り経路の表に「同期を通らないトリガー → `B06`」、`B03` の表の直後に `I5` の規則である旨の注記、`B06` を新設(共通の 3 規則・帰属・トリガーごとの規則・④の対象テナント単位の鍵・配信の所有)、一意性の索引表の 11-2 行に `B06` を併記
- **計画からの調整**: 対象テナント単位の鍵は `B02` の表に足さず `B06` の中の別表に置いた。`backend/tests/test_authz_cache_invalidation.py:300-315` が `B02` の表の単位と契約の `source_unit` を集合の完全一致で照合しており、足すとステップ 2 まで赤になるため。ステップ 2 でテストを両方の表を読む形へ直す(design.md 1-3・plan ステップ 2 に反映)
- `docs/README.md`: data-model 行に v0.7 起案中を併記、版 0.7・最終更新 2026-10-10
- 合格条件: `check_docs_status` 違反 0 / `check_design_propagation`・`check_doc_coverage` ok / `check_plan_docs_sync` は作業中の警告のみ / `test_authz_cache_invalidation.py` 14 passed

### 確定ゲート(/finalize-doc — data-model v0.7)

#### 適用版の記録(7.3-1)

```
適用版            ハーネス設計書 7.3 の v1.19(2026-10-07 確定ゲート通過・approved)
条文コミット SHA  945384c5e70ce2ae471edec1d845660918eaee93
```

- 回数の枠(6.3): 基本 2 回(全文 1 + 差分 1)/ 2 回目に P0 が残り 1 件以上採用したときだけ 3 回目(P0 限定)/ 追加は PO 裁定 1 回につき 1 回
- 手順 0: 射程宣言は v0.7 の変更履歴行(in-review)にある
- 手順 1: frontmatter と索引を `in-review` に更新(本記録と同一コミット)

#### 1 回目(全文 / 枠 基本 2 + P0 例外 1)— 否決(P0 0 / P1 3 / P2 0)

| # | 要旨 | 重大度 | 起因 | 分類 | 採否 | 反映 / 理由 | 反例の典拠確認 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1-1 | `B03` の「表」の行(`T7` と同一トランザクションで 1 件書く)が `I5` 限定と読めず、複数範囲に波及する 5・7 と衝突する | P1 | 非起因 | (A) | 採用 | `B03` の表の直後の注記を「表」の行と「一意性」の行の導出が `I5` の規則であり、同期を通らないトリガーの原子性・意図 ID・行の数は `B06`、と書き直した | `data-model.md` の `B03` の表で確認 |
| 1-2 | `B01` の節に「本書が持つのは…だけ」「発火の条件を写さない」の無限定の断定と見出しが残り、`B06` と矛盾する | P1 | 非起因 | (-) | 採用 | 見出しを「同期経路の…— 同期を通らないトリガーは `B06`」へ、2 つの断定を同期経路に限り、`B02` 冒頭の「だけが本書の範囲」を本節の範囲へ狭めた。変更履歴 v0.7 に ⑥ を追加 | 該当 4 行を確認 |
| 1-3 | `(対象テナント)` は意図の粗い指定で ④ の物理鍵の先頭ではない。B の在籍変更で消すのは A 要求の `(G, A, B, 期間)` で、「書くテナントと鍵のテナントが一致」の説明では `B02` の禁止規則と両立しない | P1 | 非起因 | (A) | 採用 | 「対象テナント単位の**選択子**」へ改め、物理鍵ではなく意図が無効化先を選ぶ指定と明記。配信は ④ の鍵の対象テナント成分で照合して展開・①〜③・⑤ と対象テナントが別の ④ は選ばない・他の要求元の ④ を消すのは ④ の波及規則そのもの・分離は「データの持ち主を他テナントが選べない」ことで保つ、と書いた | `B02` の ④ 行・波及先の ④ 行で確認 |

- 確定ゲート周回 0 → 1(反映 1 周目)
- 実装への影響: 契約の `physical_key_adt` に足す予定の variant(design.md 2 節)は「選択子」の性格になる。綴りはステップ 2 で決める(N2)

#### 2 回目(1 回目の反映差分と影響節 / 枠 基本 2 + P0 例外 1)— 否決(P0 0 / P1 2 / P2 1)

| # | 要旨 | 重大度 | 起因 | 分類 | 採否 | 反映 / 理由 | 反例の典拠確認 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2-1 | 正本は「選択子」に改めたのに、承認済み計画は同じ値を `physical_key_adt` の物理キーとして契約・実装する指示のまま | P1 | 起因 | (A) | 採用 | 計画ステップ 2・design.md 2・3 節を改め、選択子は `durable_intent.non_sync_triggers.selectors` に物理キーとは別に登録し、型名を `SharedAggregateTargetSelector` とした(`physical_key_adt` には足さない)。正本の変更履歴 ③ にも「契約では物理キーとは別の選択子として登録する」 | `plan.md:74` で確認 |
| 2-2 | `B06` は他の要求元側の ④ の鍵を消すと書いたが、`B02` の「他テナントの鍵を消せる経路を作らない」が無限定で、適用境界が揃わない | P1 | 起因 | (A) | 採用 | `B02` に「④ の例外の境界」を足した: ④ は波及規則により要求元側の鍵も消すが、消してよいのは対象テナント成分が状態を変えた側のデータの持ち主と一致する鍵に限り、他テナントが対象テナント成分を選べる経路は作らない | `data-model.md` の `B02` の禁止の行で確認 |
| 2-3 | 変更履歴の列挙が ①②③⑥④⑤ の順 | P2 | 起因 | (-) | 採用 | ⑥ を ⑤ の後へ移した | 変更履歴 v0.7 行で確認 |

- 確定ゲート周回 1 → 2(反映 2 周目)
- **基本枠 2 回に到達**。2 回目に P0 は無いので 3 回目(P0 例外)は無い。**本周の反映(反映 2 周目のコミット)は Codex の再レビューを受けていない** — 人間承認の場で最終反映の差分を確認していただく(7.3-2・7.3-8)
- 不採用: なし

#### 承認と要点

- **PO 承認 2026-10-10・山田正輝**(最終反映 `a1b1a013` の差分 = `B02` の ④ の例外の境界 3 行を提示して承認)。data-model を approved・v0.7 に、変更履歴に通過行、README 索引を現行化
- 要点: 2 回・反映 2 周・指摘 6 件(P1 5 / P2 1)全件採用。警告・エスカレーション・PO 裁定は発動なし。重要な是正は「対象テナント単位の鍵」を物理キーではない**選択子**へ改めたことで、計画ステップ 2(契約の登録先)まで波及した

### ステップ 2(契約と純粋な要求生成器)

- draft PR #114 を作成(受理記録の `acceptance_id` 用 — design.md N1)。Notion TSK-447 の URL 欄に記録
- 受理記録の承認値: 山田正輝 / 2026-10-10(人間に確認 — AskUserQuestion)
- Codex 委任: `SharedAggregateTargetSelector`(トリガー 14 専用)・契約 revision 11(`applies_to_trigger_ids` 5 件 / `non_sync_triggers` 9 件・`attribution`・`row_rules`・`selectors`、`physical_key_adt` には足さない)・テスト・受理記録 1 件(比較元 `f79c14e0`・影響資産はキャッシュ無効化契約 1 件)・snapshot・比較 corpus の再封印
- 敵対レビュー(コア領域 — 回数上限 6.3):
  - 1 回目(全差分): 否決(P0 1 / P1 1)→ 採用。P0 = トリガー 14 が物理キー単独・混在・複数選択子を受理 → 選択子ちょうど 1 件だけを受理 / P1 = `B06` の帰属・行規則と契約の照合が空洞 → 表を読み取り双方向に照合
  - 2 回目(反映差分): 否決(P1 1)→ 採用。帰属・鍵のセルを前方一致・部分一致で比べていた → 正規化した全文の完全一致と、「指定した他テナントも可」を足す変異の負例。**上限到達のため本反映は再レビューせず、Claude が完全一致の実装を確認**
- 合格条件: `check_tenant_boundary_bypass.py --base-ref origin/develop` ok / ルート `test_check_tenant_boundary_bypass.py`・`test_frozen_history.py`・`test_frozen_archive.py`・`test_frozen_archive_case_runner.py` 499 passed(Codex)/ `test_census_baseline_check.py` を含め 392 passed(Claude)/ backend `test_authz_cache_invalidation.py` 19 passed・`test_authz_repository_contract.py` green / ruff・ruff format・ty green

### ステップ 3(意図の記録と在籍区分の token)

- Codex 委任: 新規 `repositories/invalidation_intents.py`(`InvalidationIntentInsertToken`・範囲名の写像・`record_invalidation_intent`)/ `roster.py` に `PlayerRosterStatusUpdateToken`(区分が実際に違う行だけを更新する述語・論理削除済みは対象外)と `PlayerRosterLabelUpdateToken` / `PlayerUpdateToken` の許可列から在籍区分の 2 列を外す / 登録・`allowed_symbols`・正例 fixture / 受理記録を PR #114 の 1 件のまま再導出・snapshot・比較 corpus
- **計画からの変更**: 新規 token は計画の 2 件から **3 件**(在籍区分とラベルを許可列ごとに分けた)。plan・design の件数を追随
- 実 DB テストは Codex の sandbox から docker に届かず未実行 → Claude が実行。INSERT の更新件数が -1(不明)で返るのを件数 1 と照合していたテストを直した(行は直後の SELECT で確認)
- 敵対レビュー:
  - 1 回目: 否決(P0 1 / P1 1)→ 採用。P0 = 任意の文字列の `intent_id` で token を作って書ける → token がトリガー・操作 ID・行の識別子を持ち意図 ID を内部で導出、トリガー 14・`shared_aggregate` 以外は構築時に拒否 / P1 = 範囲名の全単射テストが ORM しか見ない → migration 0015・schema-manifest・実 DB の `pg_constraint` と照合
  - 2 回目: **可決**
- 合格条件: `check_tenant_boundary_bypass.py --base-ref origin/develop` ok / 凍結履歴 4 本 499 passed(Codex)/ backend の DB 不要 251 passed(Codex)/ 実 DB を含む `test_invalidation_intents_repository.py`・`test_roster_repository.py` 107 passed(Claude)/ ruff・ruff format・ty green

### ステップ 4(在籍区分の入口と発火点)

- Codex 委任: `players.py` に `POST /players/status-preview`(読み取りだけ)・`POST /players/status-apply`(1 トランザクションで ID ごとに読み → 区分の変わる行を `PlayerRosterStatusUpdateToken` で更新 → 更新件数 0 の行とラベルだけの行は `PlayerRosterLabelUpdateToken` → 区分の更新件数の合計が 1 以上なら `uuid4()` の操作 ID で意図を 1 行)/ `test_api_app.py` の経路の固定 / 新規 `test_roster_status_boundary.py` / `test_roster_boundary.py` から「未実装の入口は 404」の 2 行を削除
- ラベルは DTO で必須(明示 null = 解除)。ラベルだけの変更は発火しない
- 敵対レビュー:
  - 1 回目: 否決(P1 3)→ 2 件採用・1 件は人間の裁定で申し送り。① 無効な区分キー・ラベルキーで 500 → #95 の作成入口と同じく外部キー違反を 404 に写す ② 読み取り後の UPDATE が 0 件になる競合分岐を入口で検証していない → 最初の読み取りだけ古い区分を返す差し替えのテスト ③ 12-4 の実スキーマ判定記録が無い → **本 PR では実施せず申し送る(2026-10-10・山田正輝の裁定)**。12-4 のゲート通過の記録は正本でも保留中(data-model 変更履歴 v0.6 2026-10-08 行)、#95 も記録なしでマージ、実スキーマの実行には `.env` の接続情報と専用インスタンスの作り直しが要る。計画書のステップ 4 合格条件と DoD を書き換え、#95 の分と合わせて master へ申し送った
  - 2 回目: **可決**
- 実 DB テスト(Claude): `test_roster_status_boundary.py`・`test_roster_boundary.py`・`test_api_app.py` 41 passed。差し戻し後の 1 件の失敗はテストの期待値の誤り(404 の本文を FastAPI 既定の `{"detail": "Not Found"}` と期待していた — 既存の約束 `{"error": {"message": "対象が見つかりません"}}` へ Claude が直した)

### ステップ 5(受理記録の最終導出・センサス基準)

- ステップ 4 のコミット後に `tests/test_census_baseline_check.py` が 5 件失敗: ステップ 2 で `SharedAggregateTargetSelector` を TB004 の許可呼び出しに足したことで抑止された検出 4 件(`players.py` の import と呼び出し・`invalidation_intents.py` の import と呼び出し)が、センサス基準の「許可による抑止の実測集合」に無かった。**ステップ 2 の合格条件にセンサスのテストを入れていなかった**ため、ステップ 2〜4 のコミットはこのテストで赤のまま(台帳候補 — クローズ処理で判断)
- Codex 委任: センサス基準 revision 11(TB004 の許可呼び出しの追加による抑止を、許可シンボルを anchor の値へ戻した反実仮想で実測する導出を宣言)・`test_census_baseline_check.py` の判定と負例、PR #114 の記録 1 件の再導出・snapshot・比較 corpus
- develop が `8df9f3d1`(#115 — 文書だけ)へ進んだ。`contracts/` は不変なので取り込まず、記録の比較元だけ新しい develop にした(CI も PR の base を新しい develop で評価する)
- 敵対レビュー:
  - 1 回目: 否決(P1 2)→ 採用。anchor を進めた後に差分ゼロで赤になる / 公開シンボルだけの追加で赤になる → 追加 0 件なら抑止 0 件として受理、追加集合の同一性要求を外して実測した抑止のコードとシンボルだけを照合、4 箇所の固定照合は本 PR の版に限定
  - 2 回目: 否決(P1 1)→ 採用。記録の `change.after.declaration` でセンサス基準の識別子が `contract_revision:10` のまま(実資産は 11)。**ローカルの迂回検査は PR 受理モード(`GITHUB_EVENT_NAME=pull_request`)ではないので通ってしまう** → 9 資産すべての `change.before`/`after` を比較元と作業ツリーから機械的に導出し直した。PR 受理モードの履歴検証関数を一時 event で直接実行して ok(Codex)。CLI での確認は二親マージの HEAD を要するので CI で確認する。**上限到達のため本反映は再レビューせず**
- 合格条件: 凍結履歴・センサス・比較 corpus 185 passed / 迂回検査 ok(Codex)

### 総合検証と是正(2026-10-10)

- ステップ 5 の push 後の CI(`8d9b42f1`)で backend・harness・tenant-boundary-bypass・core-guard が赤、ルートの全件で 2 件失敗。原因は 3 系統:
  1. **data-model v0.7 の改訂に追随していない digest と生成物**(ステップ 1 で取り直すべきだった): `contracts/db/schema-manifest.json` の sha256・`contracts/authz/shared-preconditions.json` の blob digest・ORM 受入シート(N1・N3)と固定行数 → `(ステップ 1 是正)` `303ca965`。受入シートは生成器で作り直し、番号のずれだけの行は旧版の同じ行の判定を持ち越し、内容が新しい 8 行は旧版の同種の行に倣って判定(初回は自作の持ち越しスクリプトがセル内の `\|` を区切りとして分割して行を壊した — 生成器の読み取り関数を使う形でやり直した)。どれも凍結基準・oracle 封印の入力ではない。review normal 可決
  2. **API 規約違反**: API 層が `sqlalchemy.exc.IntegrityError` を import(ステップ 4 の 404 の写し)・経路の固定数 10 → 12 → `(ステップ 4 是正)` `913877ac`(リポジトリ層の `roster_status_transaction_scope` で外部キー違反をドメインの例外へ写す)。review normal 可決
  3. **CI の偽の失敗**: PR の event の `base.sha` が `f79c14e0` のまま、二親マージの第 1 親が `8df9f3d1`(develop が #115 で進んだ)→ develop を取り込んだ(`1058f9ba`・文書だけ・競合なし)
  - core-guard は逐行確認のチェックが空欄のため(想定どおり)
- **取りこぼしの原因**: 各ステップで関係ファイルのテストしか回さず、backend の DB 不要の全件(約 1 分)をステップごとに回していなかった。data-model.md の digest を持つ資産を、正本を変えるステップの合格条件に入れていなかった(台帳候補 — クローズ処理で判断)
- 是正後: backend の DB 不要の全件 1304 passed(終了コード 1 は DB 必須テスト 0 件のゲート)・実 DB を含む関係 5 ファイル 152 passed・ORM 受入シート 13 passed・shared-preconditions 9 passed・schema-manifest 14 passed・迂回検査 ok・authz カタログ ok・凍結基準の不変条件 ok

### /pr クローズ処理

- develop `0e339ed9`(#118 — 文書のみ)を取り込んだ(`4e27bbc0`・競合なし)
- 計画書を `in-review` へ
- **運用評価台帳**: 新規候補・`H-*` は無し。既存候補 3 件へ実測を追記した(同じ根のため新設しない): ①「同じ論旨を別の言い方で述べた箇所は、検索では取り残される」= 正本の digest を持つ資産と生成物を、正本を変えるステップの合格条件に入れていなかった ②「検証コマンドを人が選ぶと…」= 関係ファイルのテストだけを回し、API 規約とセンサスのテストが母集団から落ちた ③「検査器が実行文脈の環境変数で経路を変えると…」= 受理記録の取り残しがローカルの不変量モードを素通りした。変更履歴に 1 行、README の台帳行に追記(候補 129 のまま)

## 結果サマリ

- **正本**: `docs/design/data-model.md` v0.7 — 11-2 節に `B06`(同期を通らない 9 トリガーの発火条件・原子性の錨・意図 ID の骨格、自テナントの状態変更 5・7・9・14 の帰属、トリガー 14 の行規則、④の対象テナント単位の選択子、配信の所有)を新設し、`B01` を同期経路に限り、`B02` に ④ の例外の境界を足した。確定ゲート 2 回・指摘 6 件全件採用 → PO 承認
- **実装**(コア領域・5 ステップ + 是正 2): キャッシュ無効化契約 revision 11 と選択子の型 / 意図の記録(`invalidation_intents.py`)と在籍区分の token 2 件・`PlayerUpdateToken` から在籍区分の列を外す / `POST /players/status-preview`・`POST /players/status-apply` とトリガー 14 の発火点 / センサス基準 revision 11・テナント境界の受理記録 1 件(PR #114・比較元 `8df9f3d1`・承認 山田正輝 2026-10-10)
- **敵対レビュー**: 各ステップ 2 回まで(ステップ 2: P0 1 / P1 2、ステップ 3: P0 1 / P1 1、ステップ 4: P1 3、ステップ 5: P1 3)。不採用は 12-4 の判定記録の 1 件だけで、人間の裁定により申し送り
- **計画からのずれ**: 新規 token 3 件(計画 2 件)/ 対象テナント単位の鍵を `B02` の表ではなく `B06` の中の「選択子」として置いた / 12-4 の判定は本 PR で実施せず申し送り(#95 も未記録 — master へ連絡済み)
- **後続へ送ったもの**: 8・10〜13 の帰属と他の 8 トリガーの行規則(U-A2・U-C1・U-D1 ほか)/ 同期経路の 1・3・4 の意図 ID と「1 行 1 範囲」の関係(TSK-330)/ 配信(その範囲のキャッシュ本体を入れる単位)/ 「OB 化した選手が共有結果に現れない」受け入れ(U-C1 — 共有結果の経路が未実装)/ 画面(TSK-537・frontend の単位)/ 初期ラベル(Should)/ 契約と DDL の配信状態の語彙(`completed` と `delivered`)

## 決定

- J1 同期を通らない 9 トリガーの規則は `data-model.md` 11-2 に新設(実装はトリガー 14 だけ)/ J2 確定ゲート / J3 意図は対象テナント単位の粗い 1 行・展開は配信側 / J4 配信はその範囲のキャッシュ本体を初めて導入する単位(2026-10-10・山田正輝)

## 未決・次の一歩

- 人間の逐行確認(PR #114 本文のチェックと実施記録)→ マージ → /task-done
