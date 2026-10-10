---
date: 2026-10-11
topic: U-F6 共通 API・形式契約
branch: feature/uf6-api-contract
---

# 作業ログ: 2026-10-11 U-F6 共通 API・形式契約

## やったこと

### /task-start

- 既存 Notion タスク TSK-521 に着手(master の依頼 — U-F2 の後続。画面 8 単位の結節点): https://app.notion.com/p/3f493b75e6878145aa82d873e8cb65f3
- ブランチ `feature/uf6-api-contract` / worktree `../pitchlog-worktrees/feature-uf6-api-contract`(`origin/develop` = `8060b8d0` — #116 マージ後)

### /investigate

- 4 並列(legacy-analyst / spec-checker / decision-tracer / Explore)。legacy-analyst へは `dd03160` の api・lib の 26 ファイルと import 一覧を主セッションが書き出して渡した
- 結果は [research.md](../features/uf6-api-contract/research.md)。要点: 旧 `endpoints.ts`・`types.ts`(74 関数・147 型)は develop の backend(業務 8 経路・カーソル・別のエラー封筒・`/api` 接頭辞なし)とほぼ噛み合わない / 旧 `mock.ts` はドメイン計算を自前で持つ(NFR-018)・モックの移植は未決 / 同期の通信層は TSK-506 の担当 / `format.ts` は移植済み / 2026-08-16 の「API 契約を踏襲」裁定と U-M1 の新しい形をすり合わせた記録がない

## 決定

## 未決・次の一歩

### /plan

- /plan 前に PO へ分岐 4 点を確認(2026-10-10・山田): Q1 いまの backend に合わせる / Q2 モックは移植しない / Q3 U-F6 は土台だけ(同期は TSK-506)/ Q4 `/api` を付けて送り proxy で外す。すべて推奨案
- 5 領域判定を当て直し: T のみ該当(S・G・R・D は持つ範囲から外れた)。`vite.config.ts` が機械判定に当たるため PR 全体はコア領域

#### 計画レビュー 1 回目(adversarial・全文)— 否決 P0 3 / P1 2、全件採用

| # | 指摘 | 処理 |
| --- | --- | --- |
| P0-1 | 応答のテナント照合を後送りし、NFR-010 の DoD を示せない | 採用。決定 N(往復の前後で認証世代を照合し、変われば応答を捨てる)を足す。Cookie 先行の残りの窓は、δ の照合契約が入るまで「テナント所有データを表示する画面を本番に出さない」利用条件として DoD と申し送りへ |
| P0-2 | 封筒でない 409(同期 P3 の拒否本文)を `HTTP 409` に畳んで失う | 採用。`ApiError.body: unknown` で本文を損なわず保持(決定 F) |
| P0-3 | `client.ts` は同期の送信路で S・R の契約を変え得る | 採用。`client.ts` を S・R・T に当て直し、paths も 3 領域へ(重複帰属) |
| P1-4 | active Pinia 前提で、U-F13 前の実行経路が成立しない | 採用。Pinia が無ければ fetch 前に例外(fail-closed)+ 試験。U-F13 へ申し送り |
| P1-5 | proxy の検査が転送先を見ていない | 採用。rewrite の入出力 spec をステップ 5 に |

#### 計画レビュー 2 回目(adversarial・反映差分と影響節)— 否決 P0 2 / P1 3、全件採用

1 回目の P0-2・P0-3・P1-4 は閉じたと判定。

| # | 指摘 | 処理 |
| --- | --- | --- |
| P0-1 | 往復中に B へ切り替わった後に A の 401 が後着すると、決定 H が B まで失効させる | 採用。決定 N の世代照合を状態コードの解釈より先に固定。世代が変わった 401 では失効させない(ステップ 1 ④・4 ⑤) |
| P0-2 | 捨てた保存・同期の応答の顕在化が未定(NFR-015) | 採用。`ApiStaleAuthError` に method・path・status と「結果未確認」の文言。受け取る側の義務(利用者に示す・キューを完了扱いにせず同じべき等キーで再送)を DoD と TSK-506・画面単位への申し送りへ |
| P1-3 | `/^\/api/` は `/apix` も削る | 採用。`/^\/api(?=\/|\?|$)/` + 空なら `/` |
| P1-4 | ステップ 7 が JSON と `test_core_guard.py` を同一コミットで変える(機構が拒否) | 採用。ステップ 7 は JSON だけ、登録を固定する試験はステップ 8 に分離(全 9 ステップ) |
| P1-5 | 文書の合格条件に決定 N が無い | 採用。「決定 A〜N と利用の条件」へ |
