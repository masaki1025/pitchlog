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
