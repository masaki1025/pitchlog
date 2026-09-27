---
date: 2026-09-25
topic: TSK-442 製品 authz の適用器・実 DB 試験(TSK-424 PR A2)
branch: feature/product-authz-apply
---

# 作業ログ: 2026-09-25 TSK-442 製品 authz の適用器・実 DB 試験(TSK-424 PR A2)

## やったこと

- /task-start: worktree 作成、Notion TSK-442 を `進行中` へ、計画書・worklog の雛形作成。カードに DoD 欄が無かったので追加した。重さ分類は**コア領域**(テナント分離・データ移行)。**開始条件の TSK-431 の 7C は未マージ** — 計画の承認までを先に進め、/implement は 7C のマージ後

- /plan: Explore 2 本(TSK-431 の 7C の状態 / 既存の適用器と DB 試験の形)→ [research.md](../features/product-authz-apply/research.md)。A2 の差分の設計を [design.md](../features/product-authz-apply/design.md) に分離(全体の設計の正は A1 の design.md)
- 計画レビュー(sol xhigh・敵対): 1 周目 P0=1 P1=6 → 2 周目 P0=1 P1=3 → 3 周目 P0=0 P1=4 → 4 周目 P0=0 P1=1 → 5 周目(確認周)0 件で収束。**計画レビュー周回 = 4**
  - **P0 は 2 周とも「末端の DB 実行器の転用」**: 1 周目 = 任意の SQL を受け取る実行器が迂回検査を空洞化する → 「検証済みの実行計画の型」を渡す案 → 2 周目 = 型は外から構築でき、手順 ID の一致は文を拘束しない → **末端関数は閉じた指示(`APPLY` / `UNAPPLY`)だけを受け、文の生成を末端の中で正規の資産から行い、資産の置き場も引数にしない**形で閉じた
  - 3 周目以降は、プロセス内の型・モジュールの書き換えを保証の外と明示し(A1 design 10 節と同じ線引き)、閉じた論点の言い換えを P2 以下にした

## 決定

## 未決・次の一歩
- **計画承認(2026-09-26・山田正輝)**。実装は TSK-431 の 7C(PR #78)のマージ後 — 計画書 4 節の関門を通してから /implement に入る

## 関門 2 の下調べ(2026-09-26・PR #78 の head `20ef5fd` 時点 — マージ版で再確認する)

- **記録形式は research.md 1 の見込みどおり**: 置き場 = `base-allowlist.json` の `baseline_control.history`(`history_authority: true` はこの資産だけ)/ v2(`declaration`・`movement_policy`・`external_snapshots`・`aspect` は実差分から機械導出して exact 一致)/ `acceptance_id = {repo}#{PR番号}`・PR 受理モードは検査器が強制 → **draft PR で番号を先に確定**(`docs/features/tenant-boundary-baseline/design.md` D1〜D4)
- **外部ファイル(`external_files`)は 3 つ**: `scripts/check_tenant_boundary_bypass.py`・`scripts/frozen_history.py`・`.github/workflows/ci.yml`。**正例 fixture は入っていない** → A2 はこの 3 つに触れないので、新しい history-snapshot は要らない見込み
- **`contract_revision` は PR #78 で 15**(research.md の「13→14」は古い)。A2 は 16 へ
- **PR #80(TSK-440・迂回検査の条件 5・2 の射程)が先にマージされる** → 検査器が変わるので、マージ後に末端 2 関数の判定(TB005)への影響を確かめる
- 現時点で計画の改訂を要する差は無い

## 実装(2026-09-26)

- **関門 1**: PR #78(7C)がマージ(`b4ae739`・下調べと同じ head `20ef5fd`)→ origin/develop へ rebase し、HEAD がマージコミットを含むことを確認。7C 版の検査器で迂回検査 ok・凍結基準の不変量 OK。**関門 2**: 記録形式は下調べどおりで、計画の改訂は不要。Codex はサービス障害から復旧(疎通確認 OK)
- **順序の判断(人間 2026-09-26)**: PR #80(TSK-440)がまだ OPEN で、#80 も A2 も `base-allowlist.json` に凍結基準の記録を足す(後からマージする側が記録を作り直す)→ **ステップ 1 だけ先に進め、ステップ 2 以降は #80 のマージ後**
- **ステップ 1**(7ea87953): `application-steps.json`(適用 7 手順・逆順の取り外し・製品専用の操作種別)と `AuthzAssetSpec.application_steps_path` と静的検査。Codex が委任の前に「A1 の試験 `test_authz_product_staging.py` も `operation_handlers == ()` を表明しているのに変更許可に無い」と範囲の矛盾を報告 → **`operation_handlers` は空のまま残し(probe の適用器では製品資産を適用できない性質を保つ)、製品の操作種別は `AuthzAssetSpec` の別フィールドに持たせる**方針にして、既存の試験に触れずに収めた。コミット後の迂回検査で TB007 が 2 件(`Path.is_absolute`・`Path.relative_to`)→ 是正して amend(A1 に続き 3 回目 — **Codex の「迂回検査 green」は未コミットの報告なので当てにならない**。コミット後に必ず走らせる)

## master セッションとの重複(2026-09-26)

- 431 を終えた master セッションが、次の最短路として TSK-442 に着手し、同じ worktree でステップ 1 を Codex へ重ねて委任していた(着手前の `feature_status.py` が 0/11 だった時点の 1 点確認)。こちらの連絡で気づいて委任を停止し、**未コミットの差分 4 ファイルを残したまま判断をこちらへ委ねた**
- 対処: こちらの作業は 5384eabe で全部コミット済みだった(作業ツリーはクリーン)ので、差分は master の委任のものだけ。master の退避パッチが現差分と一致することを確かめ、こちらの scratchpad にも控えてから破棄した。差分の中身は A1 の試験の `operation_handlers == ()` の表明を消す方針で、こちらのステップ 1 が採らなかった形だった
- master のコミット **c04339d1 は残す**(関門 2 の照合を実形式で書き足し・research.md の行番号の陳腐化を節名・関数名へ・テスト計画の表頭の限定語の是正)。ただし 2 点を直した: ① **`contract_revision` は「マージ時点の develop の値 +1」**(#80 が先なら 16 → 17。master の書き足しは #80 の前の値だった)② **history-snapshots は無条件で必須**(7C の実装者の実測を正とする) — 上の「関門 2 の下調べ」の「新しい history-snapshot は要らない見込み」は**誤り**
- 知見: **同じ worktree を別のセッションが持っているかは `git worktree list` では分からない**。着手前の 1 点確認では重複を防げない(master の指摘)

## 7C の実装者(master セッション)からの申し送り(2026-09-26 — ステップ 2 以降で使う)

master は人間の判断で 442 から完全に手を引いた(Codex の残存プロセス 0・副作用なしを確認済み)。7C の記録形式について:

1. **仕様の原典は実装**: `scripts/frozen_history.py` の `_validate_v2_record`(必須キーの exact-set・`change` と `before`/`after` の 4 キー)/ `_validate_repository_identifier_record`(7 資産分の識別値 map が実 `current_identifiers` と完全一致・射影が動いた `integer_revision_field` 資産の更新を強制)/ `_reject_v2_reserved_markers`(除外リスト方式で記録全体の文字列を再帰走査)。**7C の design.md の D1〜D6 は裁定で、レビューで実装が動いた箇所がある**
2. **ローカルは必ず不変量モード**(`resolve_evaluation_context` が `GITHUB_EVENT_NAME == "pull_request"` のときだけ PR 受理モード)。実内容の突合・`acceptance_id`・movement と記録件数の一致・merge 形状は **PR の CI でしか走らない** → ステップ 2 の合格は PR の CI で確かめる
3. **`aspect` は手で書くとずれる**(`derive_aspects` と exact 一致)→ 先に検査器を走らせ、エラーメッセージから正しい値を得る
4. **snapshot は追記のみ・現在 47 件**(`_validate_snapshot_append_only`・ファイル名 = 内容の SHA-256)。`asset_snapshots` は 7 件・`external_snapshots` は 3 件で、既存で解決できないものだけ追記する
5. **7C のレビューで 3 周連続した型: 「関数は正しいが本番経路がその結果を使っていない」**。関数を直接呼ぶ試験は 4 件とも捕まえられず、**機構を壊す変異を入れて本番経路の試験が落ちるか**が有効だった → `product_provisioning`・`product_catalog` の試験で同じ型に注意する(詳細: `docs/worklog/2026-09-24-tenant-boundary-baseline.md`)
6. `contract_revision` = マージ時点の develop の値 +1(#80 が先なら 16 → 17)

## TSK-440 の取り込み結果の共有(2026-09-26・448master 経由)

- #80 は 7C を取り込み v2 へ適合済み・7 周目の敵対レビュー中。マージできたら 424 へ一報の予定。**識別値は develop 15 → #80 が 16 → A2 が 17** で先方と一致
- **検査器を単独ファイルとして読むと `ModuleNotFoundError`**(7C で `frozen_history.py` を import するため)。A2 は検査器に触れず前版比較もしないので直接は当たらない。A1 の `test_authz_product_staging.py` は `scripts/` を丸ごと写す形へ直してある
- **孤児 snapshot に注意**: 記録を作り直すと、前の試行の snapshot が参照を失い、追記のみの検査(`_validate_snapshot_append_only`)のせいで回収できない(431 で 29 件・約 1MB)。→ **ステップ 2 の snapshot と記録は、承認が取れて内容が固まってから 1 回だけ書く**。`change.before` と `change.after` の snapshot はどちらも HEAD 側で解決されるので、**記録と同じコミットで両方追記する**。**ステップ 2 の後に `base-allowlist.json` を動かす他の PR が develop に入ると、rebase で記録を作り直すことになる** — その時点でマージ順を人間に確認する

## 440 の申し送り(2026-09-26・448master 経由)— ステップ 2 に効く

- 440 受理後の識別値: base-allowlist 16(authority)/ cache-invalidation 4 / db-api-inventory 6 / negative-fixtures 8 / repository-contract 5 / runtime-authz-contract 4 / tenant-context-allowlist 7。**440 は 7 資産すべてを上げた**(射影が動いた資産は識別値の更新が要る — 検査器の実測)。マージ順の想定は **440 → 442 → 448**
- **未確定(ステップ 2 の着手時に実測で決める)**: 440 で 7 資産が動いたのは、7 資産が共有する `external_files`(検査器)を 440 が変えたためと読める。**A2 が変えるのは `base-allowlist.json` の `allowed_symbols` だけで外部ファイルに触れない**ので、射影が動くのは `base-allowlist.json` だけの可能性がある。**検査器を走らせて、識別値の更新が要る資産の集合を実測で確定する**
- **7 資産すべてが要る場合は計画の改訂が要る**: 識別値を写した配布モジュール 3 つ(`backend/src/pitchlog/repositories/tenant_context_contract.py`・`repositories/repository_contract.py`・`authz/runtime_contract.py` — revision と source_digest の完全一致が必要)も更新が要り、計画 4 節の不変条件「`runtime_contract.py` の差分 0 行」とステップ 2 の「変える既存ファイル」に反する → **改訂して承認を取り直してから**進める
- **CI でだけ落ちる型 2 つ**: ① 配布モジュールとの不同期は、リポジトリルートの pytest では collect されず(`No module named 'pitchlog'`)、**`backend/` で回さないと見えない** ② 合成リポジトリへ `check_repository` を呼ぶ試験が `GITHUB_EVENT_PATH` などを消していないと、**CI では PR 受理モードに入って落ちる**(再現: `GITHUB_EVENT_PATH=<合成 event> GITHUB_WORKSPACE=<repo> GITHUB_REPOSITORY=masaki1025/pitchlog GITHUB_BASE_REF=develop GITHUB_EVENT_NAME=pull_request uv run pytest …`)。440 はどちらも検査器と契約資産に触れず、試験の側だけで解いた(触ると受理記録の `after` がずれて書き直し → 孤児 snapshot)

## #80 のマージ後(2026-09-26)

- PR #80(TSK-440)が `1a404101` でマージ → origin/develop へ rebase(HEAD が #80 を含む)。変わった迂回検査器で ok・凍結基準の不変量 OK・backend の非 DB 588 passed。`contract_revision` は 16
- **識別値の更新が要る資産の実測**(使い捨ての worktree・一時ブランチ。push せず、記録と snapshot は書かず、片付け済み): `allowed_symbols` に 1 記号を足して検査器を回すと、求められた順に ①「射影が動いた資産は識別値の更新が必要: **base-allowlist.json だけ**」② revision field と `current_identifiers` を 17 に揃えよ ③「履歴末尾と 7 資産の識別値が不一致」(= v2 記録が要る)。**ほかの 6 資産の識別値の更新は求められなかった**。配布モジュール 3 つ(写しているのは別の資産)も影響なし(backend の非 DB 588 passed)
- → **A2 は `base-allowlist.json` の `contract_revision` と `current_identifiers` を 16 → 17 にし、v2 記録 1 件(7 資産の識別値の map — 6 資産は現値のまま)を足す**。440 で 7 資産が動いたのは共有の外部ファイル(検査器)を変えたため。**計画の改訂は不要**(`runtime_contract.py` などに触れない)

## ステップ 2・3(2026-09-26)

- **draft PR #84** を作成(人間の OK のあと)。`acceptance_id = masaki1025/pitchlog#84`
- **ステップ 2**(664dde6f): Codex に記号 2 件・正例 fixture・試験と **v2 記録の下書き**だけを作らせ(`aspect` は検査器のエラーから得た `["asset_snapshots","declaration"]`)、**人間が記録の中身を承認**(2026-09-26・山田正輝)してから、記録 1 件と新規 snapshot 1 件を 1 回だけ書いた(snapshot の SHA-256 = ファイル名を独立に確認・孤児 0)。**PR #84 の CI(PR 受理モード)で tenant-boundary-bypass が pass** — 記録が本番の検査で受理された。harness の赤は develop 側の既存の census の 1 件だけ、core-guard は逐行確認待ち
- **ステップ 3**(4024bd69): 適用器と取り外し・fixture `provisioned_product_catalog`。Codex のサンドボックスは Docker と DB に届かないので、DB 試験は Claude が回した(3 passed)。**コミット後の迂回検査で TB007 は出なかった**(委任文で「変更したファイルに検査器の走査関数を直接当てて違反 0 件を確かめる」と指示した)
- **共有の開発 DB の衝突**: 最初の DB 試験が「被検査ロール `pitchlog_test_role` がテスト開始前から存在する」で fail-closed。既存の試験も同じ理由で止まった → **別の worktree(`feature-tenant-session-supply`)が backend の全試験を実行中**で、そのロールが見えていただけ(残骸ではない)。消さずに相手の終了を待ってから流し、3 passed。**開発 DB は複数セッションで共有しているので、DB 試験が準備で止まったら、残骸と決めつけて消す前に他の pytest の実行を確かめる**(消すと相手の試験を壊す)
- 手元の `gh` は `gh pr checks --json` に対応していない(CI 待ちのループが抜けられなかった)。表形式の出力を読む

## ステップ 4〜11 と総合検証(2026-09-26〜27)

- **ステップ 4**(90d3ce9f): カタログ検査。正例だけが red → 原因は比べ方(`pg_get_expr` が検索パス上の `public.` を省く・関数を引数名つきで読んでいた)。**両側から `public.` を消す弱化はせず**、検索パスを `pg_catalog` に固定して PostgreSQL に完全修飾させた(1 文の中の評価順に頼る — `MATERIALIZED` の CTE で縛る。逐行確認の観点)
- **ステップ 5**(120b8270): 適用の故障注入 5 点
- **ステップ 6**(db5f613d): 往復の試験が 2 つの本物の不具合を見つけた — ① 取り外しの文を要素 ID の文字列から組み立てていて構文エラー(ステップ 3 是正 6f99634f)② **カタログ検査が NULL の ACL(= PUBLIC が既定で EXECUTE)を「実行権なし」と読む見逃し**(ステップ 4 是正 ecc8a2f7 — `acldefault` で展開。本番でも migration の直後に起きうる穴)。fixture のカタログの控えも実効の権限で比べる形へ(ステップ 3 是正 3797127b)
- **ステップ 7**(2d6d25ac): 28 表・23 表の越境。付け替えの UPDATE は 5 表で BEFORE トリガが RLS より先に 23514 で拒否 → 期待を緩めず、トリガを migration から導いて関数名まで特定
- **ステップ 8**(a917da20)・**9**(b777cb64 — `UPDATE ... WHERE` には列の SELECT も要る)・**10**(340844d1)
- **ステップ 11**(a862c5e2): **Codex が週次の利用上限(リセット 2026-10-03 02:25)で最終報告の前に止まった**。ファイル 3 つはそろっていたので、合格条件の変異の網羅を Claude が確かめ、ruff の自動修正と整形だけを当てた
- /sync-docs: 12-8 節に A2 の範囲を「使い捨てクラスタで確認済み・未発効」(2bb6f52f)・digest 2 か所(b3062045)
- **総合検証(CI と同じコマンド・同じ場所)**: backend 955 passed(DB を含む全件・`--cov`)・frontend 665・docs 系・迂回検査 ok。**ハーネスで A2 が起こした失敗 3 件**(develop では green)→ ① DB 試験の印の字面・② スキーマ契約テストのコア領域への登録(`.claude/core-areas.json` と `tests/test_core_guard.py` の期待値 — 計画の改訂 2026-09-27 承認)を是正(27de0d87)。③ U-T1 専用の仮定を持つ母集合の試験は、**人間の判断で 235 の census の fix PR に含めてもらう**(依頼済み)
- **共有の開発 DB の衝突が常態化**: `feature-tenant-session-supply`・`feature-runtime-contract-switch` などの全試験と毎回ぶつかった。相手の PID を指定して待つ運用で回した(`ps` の文字列検索の待ちループは自分自身にマッチして抜けられなくなった)。**worktree ごとに試験用の DB を分けるのが根本の対策**(起票は人間の判断)

## 10-03 以降に残ること

1. **実装後の敵対レビュー**(コア領域 — Codex の上限のリセット後)
2. **Claude が直接直した箇所の `codex_run.py review normal`**: 27de0d87 の `test_product_authz_tenant_owned.py`(印の 1 行)・`tests/test_core_guard.py`(期待値 2 行)・ステップ 11 の ruff の自動修正(CLAUDE.md の規則)
3. 235 の census の fix PR のマージ後に develop へ追随し、ハーネスの全試験を再確認
4. /pr(PR #84 の draft を外す)
- **③の再判断(2026-09-27)**: 235 から、TSK-460 には含めないと返答(同セッションの人間の裁定 — ピアの伝聞を承認として扱わず原典で確かめたうえで判断を仰いだとのこと。理由: TSK-460 のブランチでは `introduced_symbols` が偽で分岐に入らず検証できない・develop の解放を遅らせる)。**人間の再判断で A2 の中で直す**(A2 のブランチでは分岐が実際に走る)。計画書 4 節の改訂の記録を更新。実装は 10-03 以降に Codex で

## Codex の復帰と実装後の敵対レビュー(2026-09-27)

- **Codex はエラー文の「10/3」より早く、約 11 時間で復帰していた**(235・236・448 の実測。こちらも疎通確認で OK)。待つ前提を取り下げて再開
- **③ の母集合の試験は A2 で直した**(aa5b539f — 足した記号ごとに所属ファイルの変更行を要求)。444 がこのコミットを #82 へ cherry-pick(件名のステップ記法は #82 の記法へ付け替え)し、#82 の失敗は TSK-460 所有の 1 件だけになった
- Claude が直接直した箇所の `review normal`: 指摘なし
- **実装後の敵対レビュー(sol xhigh)**

| 周 | P0 | P1 | P2 | 扱い |
| --- | --- | --- | --- | --- |
| 1 | 0 | 5 | 0 | 5 件是正(接続の前提を `parameter_status` で判定し SQL 0 本・参照を `backend/src` 全体で・取り外し直後の比較・トリガを止めて RLS の 42501 を独立に観測・移行ロールの PUBLIC 経由の実効 ACL)。移行ロールの試験の日付依存も是正 |
| 2 | 0 | 2 | 0 | 是正(全利用者定義スキーマ・相対 import と再 export) |
| 3 | 0 | 2 | 0 | **参照の洗い出しが周ごとに 1 段ずつ深く突かれた**(他モジュール → 相対・再 export → `import *`・別名代入)→ **人間の判断で構造の規則に置き換え**(外では `from モジュール import 公開名` だけ・末端を `__all__` に入れない) |
| 4 | 2 | 1 | 0 | **規則の書き方の隙**(親パッケージの属性経路・公開名が閉じた集合でない)と、**design.md の書きすぎ**(「呼び出し側が文に触れる経路が無い」→ 正しくは「文を注入する経路を持たない」)。是正 |
| 5 | 0 | 0 | 1 | 確認周で**収束**。P2(`__all__` の珍しい束縛の形)は残余として PR 本文の逐行確認の観点へ |

- **知見(台帳候補)**: A1 の教訓(打ち切りの宣言は承認した文言から写す)を知っていたのに、**2 周目の後の保証範囲の宣言でまた広く書き**(「別名への代入」「モジュールの属性参照」まで閉じると宣言)、3 周目の指摘の入口になった。さらに規則へ置き換えた後も「呼び出し側が文に触れる経路が無い」という書きすぎが 4 周目の P0 の入口になった。**宣言・規則の文言は、守れる最小の主張から書く**

## 最終の総合検証(2026-09-27)

- 1 回目: 共有の開発 DB のコンテナ `pitchlog-db-1` が異常終了(exit 255 — WSL / Docker の再起動に巻き込まれたと思われる)していて DB 試験 296 件が接続拒否。`docker compose up -d` で立ち上げ直した
- 2 回目: 「被検査ロール `pitchlog_test_role` がテスト開始前から存在する」で 296 件 error。**どのセッションも pytest を実行していない**ことを確かめ、コンテナの異常終了で teardown が飛んだ**本物の残骸**と判断。台帳の候補「長時間 DB テストの強制終了が teardown を飛ばし…」の復旧手順どおり、そのロールでの接続 0 件を確かめてから `DROP OWNED BY` → `DROP ROLE`、終了済みの使い捨てクラスタのコンテナ(`pitchlog-authz-…`)も削除
- **3 回目: backend 1016 passed**(DB を含む全件・`--cov`・1 プロセス)/ ruff・format・ty green / **ハーネス 1932 passed・1 failed(develop 側の既存の census — TSK-460 で直る)**。前回 A2 が起こした 3 件は消えた / 凍結基準の不変量 OK / 迂回検査 ok / docs 系 green / 保護パスの差分 0(例外は宣言した digest)/ 最終パスは存在しない
- **知見**: 共有の開発 DB は、コンテナの異常終了 1 回で「接続拒否」→「残骸による全件 error」と 2 段で全セッションを止める。復旧手順は台帳の候補にしか無い(正本に無い)
