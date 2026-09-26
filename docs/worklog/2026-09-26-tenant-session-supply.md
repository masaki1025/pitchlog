---
date: 2026-09-26
topic: TenantRepositoryBase._session を満たす Session の供給(TSK-444 / TSK-424 PR C)
branch: feature/tenant-session-supply
---

# 作業ログ: 2026-09-26 TenantRepositoryBase._session を満たす Session の供給(TSK-444 / TSK-424 PR C)

## やったこと

- **着手**(/task-start)。`origin/develop` = `b4ae7394`(PR #78 = TSK-431 のマージを含む)起点で worktree を作成
- **開始条件の確認**: カードは「**TSK-431 の 7C のマージ**」を開始条件に挙げており、
  **PR #78 が develop へ入っている**ことを実測した(`b4ae7394 Merge pull request #78 from masaki1025/fix/tenant-boundary-baseline`)
- Notion カードに **DoD 欄が無かったので追加**した(横断要求のチェックのみ存在していた)

## 決定

- **重さ分類 = コア領域**。カード自身が「コア領域(テナント分離)→ 敵対レビュー + 人間の逐行確認」を横断要求に挙げており、
  **`base-allowlist.json`(凍結基準)を動かす**ことも明記されている
- **slug = `tenant-session-supply`**。既存の `feature/tenant-boundary-enforcement`・`feature/product-authz-surface` と同じ語彙圏に置く

## 未決・次の一歩

- **/investigate**。中心は次の 3 点:
  1. **トランザクションの単位をどう公開するか** — U-T1 ステップ 9(基底の公開シンボルは exact-set・生 Session と任意クエリを公開しない)と、
     ステップ 8(業務トランザクションの発行 SQL 列の先頭が束縛文)を同時に満たす形
  2. **FR-018 の並行性をどう満たすか** — カードが 2 案を挙げて「計画で比べて決める」としている。
     (a) 行ロック(`SELECT ... FOR UPDATE`)を capability の検査が許すノードの型に入れる /
     (b) 判定と削除を 1 つの operation にまとめ、その operation にだけ宣言付きで複数表の参照を許す。
     **「1 operation = 1 表」は緩めない**のが前提
  3. **凍結基準の動かし方** — `allowed_symbols` への追加を 7.7-2 に適合する形で記録する。
     **TSK-446 で `approved_by` / `approved_at` の出所が取れず敵対レビューが 3 周連続 P0 を出した**ので、
     **今回は着手前に承認記録の出所を決めておく**(TSK-458 が規律そのものを扱う)
- **待っている単位**: DB を使う全単位(帯 2 の葉 6 本・帯 3 の 6 本)。とくに **U-M1(TSK-393)の依存 3 と 8** を本タスクが外す

## ステップ 1: draft PR の番号確定と承認記録の出所(2026-09-26)

### draft PR

**`masaki1025/pitchlog#82`**(https://github.com/masaki1025/pitchlog/pull/82)。

凍結基準の v2 記録は `acceptance_id` = `{repository.full_name}#{pull_request.number}` を要求する
(`../features/tenant-boundary-baseline/plan.md:111`。実例は `contracts/tenant_boundary/base-allowlist.json:72` の
`masaki1025/pitchlog#78`)。**ステップ 4 より前に番号が確定している必要がある**ため、ステップ 1 で開いた。

> **【承認後の追記 — 2026-09-26】** 承認済み計画のステップ 1 は「承認記録の出所を確定し記録する」だけだったが、
> **PR 番号の確定が抜けていた**。TSK-446 でも同じ壁に当たっており(あちらはステップ 1 で draft PR を開く設計だった)、
> **本計画はその教訓を写し損ねていた**。ステップ 1 の内容へ折り込んだ(ステップ数は増やしていない)。

### 承認記録の出所 — 人間の裁定(逐語)

> kimete承認

- **取得元**: 2026-09-26 の Claude Code セッションでの発話
- **決まったこと**: 7 節の未決 2 件を当方が確定させ、計画書を承認する
- **確定した方式**: **凍結基準の承認記録の出所は、本 PR(#82)へのコメントとする**

### なぜコメントなのか(TSK-446 の実績に基づく)

`allowed_symbols` は凍結基準で、**7.7-2 が承認者・承認日を要求する**
(`docs/development/dev-harness-design-2026-08-07.md:596`)。

**PR の自己承認は GitHub が拒否する**:

```
failed to create review: GraphQL: Review Can not approve your own pull request
```

→ **単独メンテナの体制では `APPROVED` review を出所にする統制が原理的に成立しない。**
この知見は TSK-446 で得られ、`docs/development/harness-evaluation.md` の `## 候補` に記録済み。
**規律そのものの見直しは TSK-458** が扱う。

**コメントなら成立する**: 自分の PR にも書け、**`user.login`(認証済み発信者)と
`created_at`(GitHub 側のタイムスタンプ)が機械可読**で、本文に**氏名・日付・対象**を含められる。

### ステップ 4 の直前に行うこと

1. **人間が** PR #82 へ次の形のコメントを投稿する:

```
凍結基準 base-allowlist.json の allowed_symbols へ
pitchlog.repositories.transaction.tenant_transaction_scope を追加することを承認する。
承認者: <氏名>。承認日: <YYYY-MM-DD>。
```

2. **当方が** `gh api repos/masaki1025/pitchlog/issues/82/comments` から**逐語転記**し、
   `reason` に **API パス・comment id・`created_at`** を出所として書く

**推定値を 1 つも入れない。** 取得できなければ **7.7-3 の fail-closed に従い停止する**
(`dev-harness-design-2026-08-07.md:607-610`)。

### 機械側の強制(TSK-431 の 7C・PR #78 でマージ済み)

```
scripts/frozen_history.py:39-41   予約 marker を拒否 {"PENDING","TODO","TBD","未承認","未定","レビュー待ち"}
scripts/frozen_history.py:1521    approved_by は非空・approved_on は実在する ISO 日付
```

**プレースホルダは書けない。** TSK-446 で 3 周連続 P0 になった論点が、機構で塞がれている。

## 承認記録の取得(ステップ 4 の前提・2026-09-26)

**PR #82 のコメントから取得した。推定値はゼロ。**

| 項目 | 値 | 出所 |
| --- | --- | --- |
| API | `repos/masaki1025/pitchlog/issues/82/comments` | `gh api` |
| comment id | `5844655199` | 同上 |
| `user.login` | `masaki1025` | 同上(**認証済み発信者**) |
| `created_at` | `2026-09-26T08:36:30Z` | 同上(**GitHub 側のタイムスタンプ**) |

**本文(逐語)**:

> 凍結基準 base-allowlist.json の allowed_symbols へ pitchlog.repositories.transaction.tenant_transaction_scope を追加することを承認する。承認者: 山田正輝。承認日: 2026-09-26。

**台帳へ入れる値**(**すべて本文からの逐語転記**):

- `approved_by`: **`山田正輝`**
- `approved_on`: **`2026-09-26`**
- `reason`: 上の API パス・comment id・`created_at` を出所として明記する

### TSK-446 との差

TSK-446 では出所が取れず、**敵対レビューが 3 周連続で P0** を出し、最終的に
「P0 を承知でマージする」という人間の判断で決着した。原因は
**PR の自己承認を GitHub が拒否する**ことで、`APPROVED` review を出所にできなかったこと。

**本タスクは計画段階(7-2)で PR コメントを出所と決め、ステップ 4 の前に実際に取得した。**
**推定値が 1 つも無い状態で凍結基準を動かせる。**

### 承認対象の訂正(2026-09-26)

**1 件目の承認は対象シンボル名を誤っていた。** 当方が文面を下書きした際、
**どのシンボルを `allowed_symbols` へ登録するかを実測していなかった**ことが原因である。

**実測**: 迂回検査は **DB 呼び出しを囲む関数**と許可シンボルを突き合わせる。

```
backend/src/pitchlog/repositories/transaction.py:52  self._session.execute(...)
  → 囲む関数は TenantTransaction.run(:39)
backend/src/pitchlog/repositories/transaction.py:96・:133  session.close()
  → sqlalchemy.orm.Session.close は db-api-inventory.json に未登録(実測)→ 許可不要
```

→ **登録すべきは `TenantTransaction.run`。`tenant_transaction_scope` は DB API を直接呼ばないので不要。**

| 項目 | 1 件目 | **2 件目(有効)** |
| --- | --- | --- |
| comment id | `5844655199` | **`5844686316`** |
| `created_at` | `2026-09-26T08:36:30Z` | **`2026-09-26T08:41:56Z`** |
| 対象 | `tenant_transaction_scope`(**誤り**) | **`TenantTransaction.run`** |

**2 件目の本文(逐語)**:

> 訂正。凍結基準 base-allowlist.json の allowed_symbols へ追加する対象は pitchlog.repositories.transaction.TenantTransaction.run である。先の承認で tenant_transaction_scope と書いたのは誤りで、DB 呼び出し(Session.execute)を囲む関数が run であるため。tenant_transaction_scope の登録は不要。承認者: 山田正輝。承認日: 2026-09-26。

**台帳へ入れる値**: `approved_by` = **`山田正輝`** / `approved_on` = **`2026-09-26`**(**2 件目の本文から逐語**)。
`reason` には**両方の comment id と `created_at`** を書き、**1 件目が対象を誤っていた経緯**も残す。

> **Codex は承認対象を勝手に読み替えず、停止して報告した。** 当方が委任プロンプトへ
> 「足りないと分かったら報告して止まること。勝手に inventory を触らない」と書いた歯止めが効いた。
> **黙って登録していたら、承認と実態の食い違いがマージまで残っていた。**

## develop 取り込み(2026-09-26)— ステップ 4 の作業物を破棄した

**作業中に TSK-440(PR #80)が develop へマージされた。** ステップ 4 で書いた受理記録が
迂回検査で落ちた:

```
tenant-boundary contract error: contracts/tenant_boundary/base-allowlist.json.baseline_control.history:
比較元の履歴 prefix は変更・削除できない
```

**当初は「委任先が既存レコードを上書きした」と見たが、実測すると分岐だった**:

```
b4ae7394(起点)  ['(v1)', '#78']
HEAD             ['(v1)', '#78']
origin/develop   ['(v1)', '#78', '#80']
```

**委任先は何も壊していない。** append-only 台帳の検査は、**上書きと分岐を同じ文言で報告する**。

#80 は 6 資産の識別値を繰り上げていた:

| 資産 | 前 | 後 |
| --- | --- | --- |
| `tenant-context-allowlist.json` | 6 | 7 |
| `db-api-inventory.json` | 5 | 6 |
| `negative-fixtures.json` | 7 | 8 |
| `runtime-authz-contract.json` | 3 | 4 |
| `cache-invalidation-contract.json` | 3 | 4 |
| `base-allowlist.json` | 15 | **16** |
| `repository-contract.json` | 4 | **5** |

**受理記録は追随できない。** `previous_baseline_identifiers` が「履歴 2 件の世界」を指し、
snapshot は**内容アドレスなので 1 バイト違えば別ファイル**になる。**識別値も snapshot も
全部取り直し**になるため、ステップ 4 の作業物は破棄し、古い snapshot 2 件と正例 fixture を
削除した。**そのままコミットしていれば旧世界の snapshot が孤児として永久に残った**
(TSK-431 が 47 件中 29 件・1,021,201 バイトを回収不能にしたのと同型)。

**承認記録のコミット(`8ec9a8c2`)は台帳の識別値に依存しないので、取り込みと独立に残った。**
識別値に依存する部分と依存しない部分を別コミットに割っておくと、取り込み時に捨てる範囲が小さくなる。

取り込みは `38d7d0f7`(衝突なし・73 files changed)。**コミットしてから全件実行**した
(`--no-commit` のまま測ると嘘の red が出る)。**取り込み後の基準線 798 passed。**

## ステップ 4(`2027a086`)

**版数の指示が二重に古くなっていた。** 委任プロンプトは `repository-contract` 4→5 /
`base-allowlist` 15→16 と書いていたが、**実際は 5→6 / 16→17**。履歴も **4 件目**になった。
**取り込みを挟んだ時点で、プロンプトに書いた数値は全部疑う必要がある。**

| 対象 | 内容 |
| --- | --- |
| `repository-contract.json` | `public_surface` へ 2 キー・`contract_revision` **5 → 6**・`source_digest` 再計算 |
| `repository_contract.py` | 上記の逐語転記(**生成スクリプトは不在**・手で同期) |
| `test_authz_repository_contract.py` | `_generated_snapshot()` の固定辞書へ 2 キー |
| `base-allowlist.json` | `allowed_symbols` **6 件目**・`contract_revision` **16 → 17** |
| `base-allowlist.json` | v2 履歴 **4 件目**(`acceptance_id` = `masaki1025/pitchlog#82`) |
| `history-snapshots/` | 2 件追加(**既存 55 件は無改変**) |
| `tests/fixtures/.../transaction.py` | 正例 fixture |

**構造の実測**(コミット前に全項目を確認):

- `previous_baseline_identifiers` == `history[2].new_baseline_identifiers` → **True**
- 既存履歴 3 件の prefix 一致 → **True**
- 9 キー exact-set → 一致
- `change.aspect` = `['asset_snapshots', 'declaration']`(`derive_aspects` の導出と exact-set 一致)
- 予約 marker(`PENDING` / `TODO` / `TBD` / `未承認` / `未定` / `レビュー待ち`)→ **なし**
- `allowed_api_ids` = `["SQLA_SESSION_EXECUTE"]` のみ

**`Session.close` は `db-api-inventory.json` に未登録**なので許可不要。**`tenant_transaction_scope`
は DB API を直接呼ばない**ので登録しない。登録したのは `TenantTransaction.run` 1 件だけである。

**迂回検査が green になった**(TB005 が消えた)。**全件 798 passed。**

## ステップ 5(`7e4b7d24`)

計画書 6 節の「factory」行を満たす 1 本を追加。`id()` の一致比較は使わない(**CPython は
解放済みオブジェクトの id を再利用しうる**)。両方への強参照を保持したまま `is` 比較する。

**計画書 6 節の「文脈の混在」行には新しいテストを作っていない。** 2 周目 P0-1 で是正済みで、
実際に固定すべきは「`run` の署名に 2 つ目の `TenantContext` を渡す口が無いこと」である
(公開 API では混在を構成できない)。`:381` が当該行を満たす。

**欠落変異を 7 本すべて実測した**(各検査を無効化して、対応する負例が期待する red を失うこと):

| 変異した箇所 | 落ちたテスト |
| --- | --- |
| 束縛 SQL を `yield` 後へ移動 | `:343` 先頭が読み取り SQL になった |
| `run` に第 2 の `TenantContext` 引数 | `:381` 引数列に `context` が増えた |
| 未登録 token を registry 先頭へフォールバック | `:403` 既存拒否理由と不一致 |
| 例外情報を渡さず transaction を終了 | `:440` `rollback` でなく `commit` を観測 |
| `CursorResult` を直接返却 | `:510` 戻り値の exact 型検査 |
| `Session.close()` を削除 | `:563` close 回数が `[0, 0]` |
| モジュール共有 `Session` を再利用 | `:614` 生成数が 1 のまま |

**変異はすべて隔離環境で行い復元済み。** 検査器は変異させていないので、**台帳 sha256 の
更新実験は不要だった**(TSK-446 の申し送りは今回は発火しない)。

**全件 799 passed。**

## 検証(実 DB・取り込み後)

```
backend 全件                                    799 passed / 0 failed
check_tenant_boundary_bypass.py --base-ref origin/develop   ok
ruff check / ruff format --check / ty check     pass
git diff -- scripts/ contracts/ backend/src/    空(ステップ 5 時点)
```

## PR を止めている 1 件 — TSK-460 へ申し送り

**harness の 2 テストが red。** どちらも PR #80 が入れた**自己参照テスト**で、CI の
`harness` ジョブ(`ci.yml:89`)が走らせる。

| 検査 | develop | 本ブランチ | `product-authz-apply` |
| --- | --- | --- | --- |
| `test_checker_census_matches_merge_base` | **red** | red | — |
| `test_repository_application_population_is_nonempty_and_green` | green | **red** | **red** |

**A は TSK-460 が既に所有。B は所有者不在だった。**

B は `introduced_symbols` が空なら `else` 枝へ逃げるので **develop では green**。
`backend/src` へ新シンボルを足したブランチだけが `if` 枝へ入り、
「`PRODUCT_APPLICATION_PATHS` を全部触っていること」を要求される。**これが真なのは PR #80 自身だけ**。

**TSK-460 は develop と同位置なので、B を一度も評価しない。** A を直して CI が緑になっても
B は残る。TSK-460 の計画書に当該テスト名の出現は **0 件**だった。

**人間の裁定(2026-09-26)**: **B は TSK-460 へ寄せる**(同一ファイル・同一根本原因・develop を
止める PR を 1 本で済ませられる・**#82 を検証台に使える**)。**#82 は draft のまま `/pr` を完走**する。

→ **TSK-460 へ Notion コメントで申し送り済み**(発火条件の差・実測 3 ブランチ・DoD 追加案・
#82 を検証台として提供する旨)。

## 台帳への追記(該当あり)

`docs/development/harness-evaluation.md` の `## 候補` へ:

1. **既存候補「並行ブランチが CI 契約に規則を足すと、先行して設計済みのブランチが後から抵触する」へ 2 例目**
   — **追随では済まず、書いた成果物が再利用不能になる型**。1 例目(TSK-421)は成果物を生かして
   追随できたが、**append-only かつ content-addressed な台帳には追随という操作が存在しない**
2. **新設「マージすると必ず赤になるテストの是正タスクは、同じ欠陥の残りを自分の CI で踏めない」**
   — **欠陥の発見経路と是正の検証経路が同じ位置にあると、その位置で緑になる欠陥は構造的に見えない**。
   **制御目的の典拠は未確認のため `H-*` を与えない**

**`TSK-448` が出す候補「自ブランチでのみ成立する主張をテストに書くと、マージした瞬間に必ず赤になる」
とは別の面**(あちらは**書く側**、本件は**直す側の検証台**)。重複回避の合意を踏んでいない。

変更履歴表へ 1 行追記し、`docs/README.md` の台帳行を現行化した。**`H-*` の採番なし・版は上げない**
(7.6-3 前段)。

## 実装後の敵対レビュー — 変更要求(P0 3 / P1 4 / P2 2)

**コア領域なので必須。** 委任プロンプトには**過去の知見を 2 つ先回りで入れた**:

1. **出力形式の制約** — 「攻撃の再現コードを書くな。どの不変量がどの条件で破れるかを散文と
   ファイル:行で述べよ」。**過去に同種のレビューで解析は完走したのに指摘の出力が提供側の
   分類器でブロックされ、3 周目に 0 件しか届かなかった**(台帳)。今回は**全指摘が届いた**
2. **成果の主張を反証対象として名指し** — 「`base.py` / `binding.py` に触れずに足せたという
   主張が本当に成り立っているか。公開面 exact-set と変異アンカーが**間接的に迂回されていないか**」

**2 が効いた。** 肯定形の確認(無変更か)を依頼していたら、P0 3 件は 1 件も出なかった。

### P0 は 3 件とも当方が原典で裏を取った

**P0-1 公開ハンドルから生の Session へ到達でき、公開コンストラクタで束縛を迂回できる**

`transaction.py:20` `:29` `:36`。**決定的だったのは `db-api-inventory.json` に
`Session` の「構築」が登録されていないこと**(登録はメソッドだけ — 当方が全 API を列挙して確認)。
**葉が `Session(engine)` を作っても迂回検査に当たらない。** それを `TenantTransaction(...)` へ
渡せば `run` が許可シンボルなので `execute` まで通る。
**`run` を許可したことで、呼び出し側が持ち込んだ Session の execute まで許可されていた。**

既存テスト `:387` の exact-set は **`_` 始まりを除外する**ので `__init__` と `_session` を
**構造的に見ていなかった**。

**P0-2 scope 終了後もハンドルが未束縛の SQL を発行できる(実 DB で再現)**

使い捨てのプローブを書いて流した:

```
scope 終了後の発行:   ['SELECT ... FROM tenant_transaction_probe ...']
終了後 run() の結果:  NO_RAISE
束縛文が終了後に出たか: False
```

**例外にならず束縛文なしで SQL が通った。** `Session.close()` はリセットであって使用不能化では
ないため、終了後の `run()` が新しいトランザクションを自動開始する。**中核不変量が破れていた。**

**P0-3 新しい入口だけ発行証跡検査を迂回している**

| 入口 | 型検査 | 発行証跡 |
| --- | --- | --- |
| `TenantRepositoryBase.execute`(`base.py:178-181`) | `type(context) is not TenantContext`(**exact**) | **あり** |
| `tenant_transaction_scope` → `_tenant_transaction`(`binding.py:58`) | `isinstance`(**派生を許す**) | **なし** |

### 凍結基準側は指摘なし

`change.before` / `after` は実内容と一致、`change.aspect` も過不足なし、snapshot 2 件も
ファイル名と内容 SHA-256 が一致。**レビュー側が `origin/develop` と HEAD から独立に再構成**して確認した。

## 差し戻し修正(4 コミット)

| # | コミット | 内容 | 全件 |
| --- | --- | --- | --- |
| 1 | `2af6486b` | **ハンドルの非公開化と失効**(P0-1・P0-2) | 803 passed |
| 2 | `a181ced7` | **発行証跡検査を既存と同じ強さへ**(P0-3) | 806 passed |
| 3 | `960f0cb1` | **statement 種別検査・close 順序・fixture 追随**(P1-4/5/6) | 810 passed |
| 4 | `ecc3ccc7` | **資産の追随と P2-8** | 813 passed |

**改名だけでは機構にならない**(非公開名は規約であって型ではない)ので、**ハンドルが Session を
持つのをやめた** — モジュール私有レジストリへの**不透明キー**に置き換え、生成は scope 私有
センチネル必須にした。**ハンドルの到達グラフから Session が消える。**

**`base.py` / `binding.py` は最後まで 1 行も変えていない。** 既存の防御を弱めるのではなく、
**新しい入口を既存と同じ強さに揃えた**。

**P1-7(Engine・接続プールの所有と dispose)は人間の裁定で別タスクへ起票**した
(Notion: トランザクション単位の Engine・接続プールの所有と破棄を決める)。

## 承認を 3 通取り直した

**非公開化で許可シンボルのパスが変わった**(署名は不変)ため、2 通目が指す対象が消えた。

| # | comment id | created_at | 対象 |
| --- | --- | --- | --- |
| 1 | `5844655199` | 08:36:30Z | `tenant_transaction_scope`(**取り違え**) |
| 2 | `5844686316` | 08:41:56Z | `TenantTransaction.run`(**非公開化で消滅**) |
| 3 | **`5846446071`** | **12:56:08Z** | **`_TenantTransaction.run`(有効)** |

**推定値はゼロ。** `reason` に 3 通すべての id と `created_at`、それぞれが何を承認し
なぜ差し替わったかを書いた。

**投稿の代行は分類器に遮断された。** 当方が人間名義の承認記録を書く行為が
`Instruction Poisoning` として止まった。**迂回していない** — ハーネスの「最終判断は常に人間」と
一致する遮断だと判断し、`!` 付きの 1 行コマンドを提示して**人間に実行してもらった**。

## 資産の書き直し方(版数を上げなかった理由)

**履歴は 4 件目を書き直した。5 件目を足していない**(同一受理で 2 件追記は red)。
**4 件目は develop に存在しない我々のレコード**なので、書き直しても**比較元の履歴 prefix 3 件は
壊れない**(`origin/develop` と一致することを実測)。

**`contract_revision` は 17 と 6 のまま据え置いた。** develop 側は 16 と 5 で、
**develop は 17 と 6 を一度も見ていない**。本 PR 内で内容を書き直しただけなので、
**develop に対する正味の移動は 16→17 / 5→6 で変わらない**。

**snapshot は我々が追加した 2 件だけを削除**して作り直した(未マージなので孤児にしてよい)。
**develop 由来の 55 件は削除・変更ともに 0 件。**

`public_surface` からは **`transaction_handle_type` を落とした** — 非公開型を「公開面」に
宣言するのは意味の取り違えになるため。ハンドル型は `allowed_symbols` 側が固定する。

## 測り方の誤りを 1 つ踏んだ

**資産更新の直後に全件を流したら 1 件落ちた**:

```
WordingScanReadError: 文言走査の候補を読めない:
contracts/tenant_boundary/history-snapshots/089aa8c1...: No such file or directory
```

**snapshot を削除したが未コミットだった**ため、走査が版管理上の一覧から読もうとして落ちた。
**コミット後に測り直して 813 passed。** 台帳の既存候補「**取り込みは必ず先にコミットしてから
全件実行する**」と同じ型で、**削除を伴う変更でも成立する**。

## 台帳への追記(2 度目・該当あり)

1. **新設「既存ファイルが無変更であることは、既存の防御が維持されている証明にならない」**
   — **人間の逐行確認が「無変更であること」だけを見ると P0 3 件は全部通過する**。
   **コア領域の防御はファイルの中身ではなく到達経路の集合で決まる。**
   有効だったのは**反証の依頼**にしたこと。**制御目的の典拠が未確認のため `H-*` は与えない**
2. **既存候補「生成物の陳腐化は、生成物を使う人の手元では分からない」へ 2 例目**
   — **宣言した対象が実装から消えても一致テストは green のまま**(文字列比較だけで
   シンボルを解決しない)。**気づいたのは迂回検査だけ**。**生成スクリプトが存在せず手で
   同期しているので、この一致テストが唯一の担保だったが担保になっていなかった**

## 最終状態

```
backend 全件(実 DB)                                        813 passed / 0 failed
check_tenant_boundary_bypass.py --base-ref origin/develop   ok
harness pytest tests/                                       2 failed / 1923 passed(TSK-460 所有)
ruff check / ruff format --check / ty check(両層)          pass
```

**harness の 2 件は TSK-460 待ち。** 本 PR は draft のまま置く。
