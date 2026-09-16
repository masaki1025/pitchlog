---
date: 2026-09-13
topic: 入力ベースラインが動かせない欠陥を 5 箇所まとめて解く
branch: fix/oracle-input-baseline
---

# 作業ログ: 2026-09-13 入力ベースラインが動かせない欠陥

Notion: TSK-386。計画書: `docs/features/oracle-input-baseline/plan.md`。
**送り元**: TSK-379(PR #60・マージ済み `0bc05b8`)のステップ 9 で顕在化。

## やったこと

**調査**(`research.md`)→ **詳細設計**(`design.md`)→ **実装計画**(`plan.md`)を起票し、
**計画レビューを 6 周回して収束させた**(`codex_run.py review adversarial`)。

| 周 | 判定 | 起因 / 非起因 | この周で変わったこと |
| --- | --- | --- | --- |
| 1 | 否決 `P1 7 / P2 1` | — | **設計を作り直した** — 宣言の置き場・承認の機械的検証・上げ忘れの検出 |
| 2 | 否決 `P1 6 / P2 1` | — | **保証範囲を表で限定した**(ブランチ保護が無い) |
| 3 | 否決 `P1 6 / P2 1` | 3 / 3 | **`core_areas_guard` を独立系列に** / **`ci.yml` へ結線** |
| 4 | 否決 `P1 6 / P2 3` | 4 / 2 | **台帳の digest 要件を片方向へ**(初版から 4 周持ち越した自己矛盾) |
| 5 | 否決 `P1 3 / P2 2` | 3 / 0 | **version 型から `supersedes` を落とす** / **`pending_removal` に機械の期限** |
| 6 | **可決 `P0 0 / P1 0 / P2 2`** | 2 / 0 | 収束。総合判定「**実装に入れる状態である**」 |

**自分の側の失敗を 38 件、`design.md` 8 節へ全件記録した。** 型は 5 つ:

1. **測らずに数を書く**(「4 段 → 3 段」「6 本減」)
2. **機械の保証範囲を過大に言う**(「逐行確認で守られる」「`F-4` で使い回しを塞ぐ」)
3. **母集団を手で列挙する**(直書きを 3 件と数え、4 件目を落とした)
4. **訂正を全文へ波及させない**(3・4・5・6 周目で連続再発)
5. **新設要素を既存の要件と突き合わせない**(`corpus_versions`・4 系列化・allow-list)

**対策 6 つのうち 4 つは効いた**(効きは同 8 節の表)。**節参照の機械突合を 5 周目に足して 0 件にした。**

### ステップ 1: 退行の物差し

`frozen_negative` marker で N1・N2 を一括実行できるようにし、marker の付いたテスト名が
期待する 2 件と完全一致する exact-set テストを追加した。N1・N2 は一時ディレクトリへ
`git clone --shared` した複製上で、改ざんが検査器に拒否されること(red)を確認する。

- 変更前: `uv run pytest tests/test_authz_mutation_composition_full.py` — **5 passed**
- 変更後(負例集合): `uv run pytest tests/test_authz_mutation_composition_full.py -m frozen_negative -v` —
  **2 passed, 4 deselected**(N1・N2 が期待する例外を発生させ、負例として red)
- 変更後(ファイル全体): `uv run pytest tests/test_authz_mutation_composition_full.py -v` — **6 passed**

## 確定ゲートの適用版(設計書 7.3-1 — 暫定記録)

**対象**: `docs/development/dev-harness-design-2026-08-07.md` の **`v1.14 → v1.15`**
(`7.7 凍結基準の更新経路` の新設 — **7.6-3 後段**)。

| 項目 | 値 |
| --- | --- |
| **適用版(7.3 の版数)** | **1.14** |
| **条文コミット SHA** | **`bbd6b169a799af216b5b5217f91a1a3a08bc00d2`** |
| 根拠 | **in-review 化コミットの第一親**。同コミット時点で 7.3 は `v1.14` の approved 状態で収録されている |
| 記録日 | 2026-09-14 |

**適用版 = 初回敵対レビュー実行時点で approved の 7.3 の版**(7.3-1 の唯一の定義)。
**本改訂は 7.3 自身を変更しない**ので、直前 approved 版がそのまま適用版になる。

**本記録は暫定である。** **初回敵対レビュー実行時点で異なっていれば更新してから開始する**
(更新も本 worklog へ残す)。**当該ゲートはこの版で最後まで運用し、途中で切り替えない。**

**本ゲートの対象は 1 正本のみ**なので、一括検証(7.3-1 後段)には当たらない。適用版の記録は 1 件。

### 索引の版セルに「起案」と書けない

**`docs/README.md` の版セルは数値でなければならない。** `scripts/check_docs_status.py` が
`正本一覧の版が不正: 1.15(起案)` で exit 1 になる(実測)。**「起案(in-review)」は説明側へ書く。**
**TSK-379 でも同じところで詰まっている**(あちらは「暫定」を変更内容へ移した)。

## 確定ゲートの採否記録(7.3-2)

### 1 周目(全文・`否決 P0 1 / P1 4 / P2 0`)

**全 5 件が 起因・(A)。** 全件採用。

| # | 重大度 | 要旨 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | **P0** | **7.7-3・7.7-4 が「記録を残さずに基準を動かす経路が無い」と断定しながら、同じ節で base 側の直接書き換えが塞がらないと認めている。同時に成立しない** | **採用**。**`7.7-7 本節が保証する範囲` を新設**し、保証を「**信頼できる比較元に対して検査が実行されたとき、7.7-2〜7.7-5 を満たさない変更は受理されない**」の 1 つに限定。保証しないもの 3 件(承認の真正性 / 比較元の正しさ / 検査が実行されたこと)を明記 |
| 2 | P1 | **7.7-2 の「ちょうど 1 本」が判定可能な規範でない。** 経路の同一性・数え方・正当性の決め方が無く、経路名を宣言するだけで条文を満たせる | **採用**。**「受理条件」で書き直した** — 基準を別の値へ遷移させる受理条件を宣言が持ち、満たさない遷移を受理しない。**「1 本」は受理条件を満たす遷移だけが通ることを指す**と明示 |
| 3 | P1 | **7.7-4 に新しい基準の識別値が無く、検査器が現に用いる基準と履歴末尾の一致も無い。** 形式的な記録を足す実装を排除できない | **採用**。必須項目を 3 つに整理し、**不変条件を 2 つ明示**(追記の「直前」= 追記前の末尾の「新」/ **検査器が現に用いる基準 = 履歴末尾の「新」**)|
| 4 | P1 | **7.7-6 の委任が広すぎる。** 「どの述語で判定するか」を無限定に委任すると 7.7-3〜7.7-5 まで実装側で緩和できる。不一致時の優先元も無い | **採用**。委任を **2 つに限定**(何を凍結するか / 同一性の粒度と識別値)。**7.7-2〜7.7-5 の判定は委任しない**と明記。**宣言が優先**を追加 |
| 5 | P1 | **射程宣言が「6 項」で本文と一致しない。** 7.7-6 は自項を除外し、「保証しないこと」の段は 6 項の外にある | **採用**。**7.7-7 として項番を与え、射程宣言を 7 項へ**。保証境界を規範内に置く先例は本書にある(`:305`・`:350` の v1.5「本例外が保証する範囲」/ `:481` の 7.3-8)ので、**内容ではなく項番と射程からの脱落が問題**だった |

**不採用: 0 件。** **(B) の送り先: 無し**(全件が本改訂の射程内)。

**自己点検で確認したこと**: 保証境界を規範の中に置く先例が本書に 3 つある
(`:305`・`:350` — v1.5 確定ゲート 7 周目「**何を保証しないかを含めて一意にする**」/ `:481` — 7.3-8)。
**7.7-7 はこの先例と同型にした。**

**条文の機械検査(反映後)**: 個別の資産名 0 件 / 検査器名 0 件 / 40 桁 hex 0 件 / 述語 ID 0 件。
`check_docs_status.py` exit 0。

### 2 周目(反映差分・`否決 P0 0 / P1 2 / P2 1`)

**全 3 件が 起因。** 全件採用。**(B) の送り先: 無し。**

| # | 重大度 | (A)/(B) | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- |
| 1 | P1 | (A) | **7.7-2 の「受理条件」と 7.7-3〜7.7-5 の関係が一意でない。** 総称なら宣言への重複記載が要るのか不明、別物なら **7.7-6 の「委任は 2 つに限る」に対する第三の委任事項**になる | **採用**。**受理条件は 2 つで尽きると明記** — ①7.7-3〜7.7-5 の要求(**資産によらず同一・委任しない・宣言は書き写さなくてよい**)②7.7-6 が委任する識別値・粒度の指定(**宣言が明示的に持つ**)。**第三の要素を足さないと宣言した** |
| 2 | P1 | (A) | **7.7-7 の「信頼できる比較元」が未定義。** 同項は比較元の正しさを保証しないと言っており、どの状態なら信頼できるかで分岐する。**v1.5 の先例・7.3-8 の精度に達していない** | **採用**。**「信頼できる」を外し**、条件を「**検査が実行され、かつ比較元が本節の外で改変されていないとき**」へ。**信頼性は本節が判定できる性質ではない**と明記。**保証しないもの 4 件を「発火しない状態」つきの表に**した(**4 件目「複数変更の合成」は反映時に自分で追加**)|
| 3 | P2 | (-) | **変更履歴の起案行が反映前の要約のまま。** ① は「ちょうど 1 本」、③ は新識別値と第 2 不変条件を落としている | **採用**。起案行を本文へ同期(①受理条件と 2 要素 / ③3 項目 + 2 不変条件 / **⑤ 7.7-7 を追加**)|

**自己点検で 1 件**(レビュー指摘ではない): **7.7-6 の「宣言と実装が食い違う場合は宣言が優先する
(7.3-1 と同型)」は誤りだった。** **食い違いを検出して宣言の値を黙って採る実装は、食い違いが
起きたこと自体を隠す** — **7.7-4 の 2 つ目の不変条件の違反として赤にする**のが正しい。
**7.3-1 は人が読む 2 文書の優先順位**であり、**機械が検出できる不一致とは形が違う**。
**1 周目の反映で立てた類推が誤っていた。**

**周ごとの推移**: `P0 1 / P1 4` → `P0 0 / P1 2 / P2 1`。

### 3 周目(反映差分・`否決 P0 1 / P1 2 / P2 0`)

**全 3 件が 起因。** 全件採用。**(B) の送り先: 無し。**

| # | 重大度 | (A)/(B) | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- |
| 1 | **P0** | (A) | **7.7-6 が「宣言と実装のあらゆる食い違いは 7.7-4 の第 2 不変条件違反」としているが事実誤認。** 同条件が比べるのは**基準の識別値だけ**で、**7.7-6 が委任する凍結対象集合や粒度の食い違いは検出できない**。**識別値が履歴末尾と一致したまま対象を狭める実装が成立する** | **採用**。**食い違いを 2 種類に分けて拒否条項を表にした** — 識別値の食い違いは **7.7-4 の 2 つ目の不変条件**、**凍結対象・識別値・粒度の食い違いは 7.7-6 自身(独立の要求)**。「**2 つ目を 7.7-4 に帰属させてはならない**」と理由つきで明記。起案行も同期 |
| 2 | P1 | (A) | **7.7-2 の「2 つで尽きる」が 7.7-1 を含まない。** **履歴を正しく追記したうえで末尾と同じ値を検査器へ直書きする変更**は、列挙 2 条件と 7.7-4 の不変条件を満たしながら **7.7-1 に違反できる** | **採用**。**受理条件を 3 つへ** — 1 つ目に **7.7-1 の構造要求**(基準が宣言側にあり検査器のソースに直書きされていないこと)を置き、**「7.7-1 は検査の構築時だけの規律ではなく、遷移のたびに満たされていなければならない」**と明記 |
| 3 | P1 | (-) | **起案行が受理条件の第 2 要素を「識別値・粒度の指定」と要約し、本文が明記する「凍結対象」を落としている。** 合否条件について起案行と本文が一致しない | **採用**。起案行を本文へ同期 |

**レビューが確認した点**: 7.7-7 の表は条件 1 ↔ 行 3、条件 2 ↔ 行 2 で対応し、
行 1(承認真正性)は独立の残余リスク、行 4(合成)は個別検査済み変更の合成が検査されない具体例。
**条件の裏返しを表に記すこと自体は矛盾ではない**(2 周目の反映は妥当と判定された)。

**この周で分かったこと**: **1 周目の「宣言が優先する」を 2 周目に撤回して
「すべて 7.7-4 の違反」へ置き換えたが、それも誤りだった。**
**間違った主張を別の間違った主張で置き換えている。**
**3 周目でようやく「拒否する条項が 2 つに分かれる」という形に落ちた。**

**周ごとの推移**: `P0 1 / P1 4` → `P0 0 / P1 2 / P2 1` → `P0 1 / P1 2 / P2 0`。
**起案行の同期漏れは 2 周連続**(2 周目 `P2`・3 周目 `P1`)。

### 4 周目(反映差分・`否決 P0 1 / P1 2 / P2 0`)+ **PO スコープ裁定**

**全 3 件が 起因。** 全件採用。**(B) の送り先: 無し。**

| # | 重大度 | (A)/(B) | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- |
| 1 | **P0** | (A) | **「食い違いは 2 種類」が網羅していない。** **実装がどの宣言レコード/系列を参照するかという結線の食い違いが欠けている** — **値が同じ 2 系列のうち誤った側へ結線すると、7.7-4 の値一致も 7.7-6 の対象・粒度一致も通り、一方の更新が他方の基準を暗黙に動かす** | **採用**。**PO 裁定(範囲確定)を起動し、7.7-6 を導出要求へ組み替えた**(下記)|
| 2 | P1 | (A) | **2 行の分類が「識別値」で重複。** 第 1 行は履歴末尾との現在値、第 2 行も「実装が現に用いる…識別値」で、どちらへ帰属させるか割れる | **採用**。**分類表そのものを廃止**(導出要求に置き換えたので比較の帰属が消えた)|
| 3 | P1 | (A) | **7.7-6 の独立拒否要求が、受理条件 3 つにも 7.7-7 の保証にも収まっていない。** 「受理条件 3 の一部」「禁止された第 4 条件」「保証外の独立条件」で解釈が割れる | **採用**。**受理条件 3 を「宣言が 3 指定を持ち、実装がそれを導出していること」へ**。**独立した第四の条件ではないと明記し、7.7-7 の保証が及ぶことを本文に書いた** |

**レビューが確認した点**: **7.7-1 を遷移時にも要求することは 7.7-2 が束ねる関係であり、重複ではない**
(3 周目の反映は妥当と判定された)。

### PO スコープ裁定(7.3-6)— **範囲確定**

**発火**: **母集団 = 当該周の P0+P1**(7.3-6)。**4 周連続で `起因件数 × 2 > 母集団` が成立していた。**

| 周 | 母集団 | 起因 | 判定 |
| --- | --- | --- | --- |
| 1 | 5 | 5 | 10 > 5 ✓ |
| 2 | 2 | 2 | 4 > 2 ✓ |
| 3 | 3 | 3 | 6 > 3 ✓ |
| 4 | 3 | 3 | 6 > 3 ✓ |

**2 周連続の時点(2 周目終了時)で上げるべきだった。** **4 周回してから上げたのは運用ミスである。**

**裁定**: **範囲確定**(2026-09-14・山田正輝)。

**確定範囲の変更点**:

| 変更前 | 変更後 |
| --- | --- |
| **7.7-6 は「実装と宣言の食い違いを検査する」** | **「実装は委任先を宣言から導出する」**(**一致の検査は種類の数え上げになり終わらない**)|
| **委任先は 2 つ**(何を凍結するか / 粒度・識別値) | **3 つ**(+ **どの宣言レコード〔系列〕を基準とするか**)|

**実装時に確定する範囲は不変。**

**同じ段落を 4 回書き直した記録**(**規範本文には残さない** — 本書に先例がない):

1. 1 周目 「**宣言が優先する**(7.3-1 と同型)」→ 自己点検で撤回(黙って宣言を採る実装は食い違いを隠す)
2. 2 周目 「**すべて 7.7-4 の第 2 不変条件違反**」→ 3 周目 `P0`(7.7-4 は識別値しか比べない)
3. 3 周目 「**食い違いは 2 種類**」→ 4 周目 `P0`(**結線という 3 種類目**を数え落とし)
4. 4 周目 「**実装は宣言から導出する**」← **数え上げをやめた**

**型**: **列挙で塞ごうとして、毎周 1 つ数え落とす。** **`design.md` 8 節の「母集団を手で列挙する」型**が、
**計画レビューではなく確定ゲートで再発した。** **構造で塞ぐ形(導出)に替えて終息させた。**

**裁定後の次周は全文レビュー**(7.3-4 の射程変更周)。

**周ごとの推移**: `P0 1 / P1 4` → `P0 0 / P1 2 / P2 1` → `P0 1 / P1 2` → `P0 1 / P1 2` → (5 周目・全文)

### 5 周目(**全文** — 射程変更直後・`否決 P0 2 / P1 1 / P2 0`)

**起因 2 / 非起因 1。** 全件採用。**(B) の送り先: 無し。**

| # | 重大度 | 起因 | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- |
| 1 | **P0** | **非起因** | **7.7-7 の保証は検査器自身の改変で破れる。** **検査器を同一変更内で弱めて不正な遷移を通した場合も、「検査は実行された」「比較元は改変されていない」の 2 条件は成立する。** **`design.md` 自身が既知の非保証として挙げている経路**であり、条文の保証は事実誤認 | **採用**。**条件を 3 つへ**(③ 当該変更が検査器自身を弱めていない)+ **保証しないもの 5 件目**(検査器自身の改変 — 既知の循環参照)。**「検査は自分自身の改変を判定できない」**と明記 |
| 2 | **P0** | 起因 | **完全一致要求が「読み落とし」を尽くして塞がない。** **全対象を走査しつつ粒度・識別方式を固定値で保持する実装**や、**現在値が同じ別系列を読む実装**は、**対象集合の完全一致を通る** | **採用**。**検査が「自分が現に用いた 3 指定」を出力し、宣言と完全一致することを示す**形へ。**「対象集合だけでは足りない」**と反例つきで明記 |
| 3 | P1 | 起因 | **委任の決定主体が割れている。** 節冒頭と 7.7-6 冒頭は「宣言と実装が決める/両者へ委任」、後段は「宣言が持ち実装は導出し自分で保持してはならない」。**索引の要約も前者のまま** | **採用**。**委任先を宣言に一本化**(実装へは委任しない)。**節冒頭・7.7-6 冒頭・起案行・索引の 4 箇所を同期**。`data-model.md` より狭い委任であることも明記 |

**全文レビューにしたことで、1 周目から居座っていた `P0`(非起因)が出た。**
**4 周の差分レビューでは出ていない。** **射程変更周を全文にする 7.3-4 の規則が効いた実例である。**

**周ごとの推移**: `P0 1 / P1 4` → `P0 0 / P1 2 / P2 1` → `P0 1 / P1 2` → `P0 1 / P1 2`(PO 裁定)
→ `P0 2 / P1 1`。

**エスカレーション判定(7.3-6)**: 母集団 3・起因 2 → `2 × 2 = 4 > 3` **成立**。
**ただし PO 裁定(範囲確定)で連続カウントは 0 にリセット済み**(7.3-6 の表 — 「いずれも連続カウントを
0 にリセットする」)。**本周が裁定後の 1 周目**なので、次周も成立したら再度エスカレーションする。

### 6 周目(反映差分・`否決 P0 1 / P1 0 / P2 1`)

**全 2 件が 起因。** 全件採用。**(B) の送り先: 無し。** **`P1` が 0 になった。**

| # | 重大度 | 要旨 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | **P0** | **条件 ③ が「当該変更による弱体化」しか除外していない。** **先行変更で検査器だけを弱め、後続変更で不正な遷移を行えば、後続変更では ①〜③ がすべて成立する。** 表の #5 は同一変更内、#4 は個別受理の合成に限定されており、**この経路を列挙していない** | **採用**。**③ を変更の条件から状態の条件へ**(「検査器が本節の要求どおりに動作するとき」)。**先行変更の経路を明示**し、**「③ は本節が検証する条件ではなく前提である」**と書いた。表 #5 も状態の言い方へ改め、**同一変更内・先行変更のどちらも塞がらない**ことを明記 |
| 2 | P2 | **「条件は 2 つとも」が 3 条件と不一致**(残存誤記) | **採用**。3 つへ |

**この P0 は 5 周目の反映が作った。** **「検査器自身の改変」を条件へ入れるとき、
「当該変更が」と書いて時間軸を狭めた。** **穴を塞ぐつもりで、塞ぐ範囲を自分で限定していた。**

**周ごとの推移**:

| 周 | 範囲 | P0 | P1 | P2 | 母集団 | 起因 | 起因比 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 全文 | 1 | 4 | 0 | 5 | 5 | 100% |
| 2 | 差分 | 0 | 2 | 1 | 2 | 2 | 100% |
| 3 | 差分 | 1 | 2 | 0 | 3 | 3 | 100% |
| 4 | 差分 | 1 | 2 | 0 | 3 | 3 | 100% → **PO 裁定(範囲確定)** |
| 5 | 全文 | 2 | 1 | 0 | 3 | 2 | 67% |
| 6 | 差分 | 1 | 0 | 1 | 1 | 1 | 100% |

**エスカレーション判定(7.3-6)**: 母集団 1・起因 1 → `1 × 2 = 2 > 1` **成立**。
**5 周目も成立していたので 2 周連続**。**ただし PO 裁定は 4 周目に済んでおり、
裁定の効果でカウンタは 0 にリセットされ、5 周目が裁定後 1 周目・6 周目が 2 周目**である。
**したがって再度のエスカレーション条件を満たす。**

**あわせて `確定ゲート周回` が 6 に達したため、7.3-6 の 6 周警告を PO へ提示する。**

### 6 周警告への PO 判断(7.3-6)— **続行の明示指示**(2026-09-14・山田正輝)

**提示した内容**: 上表(周回・重大度推移・起因比)+ 次の 3 点。

1. **指摘の性質が変わった** — 3 周目までは「規範として成立していない」型、いまは「1 語の時間軸が狭い」型
2. **起因比 100% が続くが母集団は 5 → 1 へ縮小**(新しい論点が出ていない)
3. **留保**: **「穴を塞ぐつもりで、塞ぐ範囲を自分で限定する」型が 5・6 周目と 2 周連続**

**判断: 続行。** **7.3-6 の表に従い、編集なし・カウンタ加算なし・差分再レビューを続行する。**

**あわせて 5・6 周目のエスカレーション条件成立(2 周連続)についても、本判断が
「続行の明示指示」として処理する**(4 周目の範囲確定に続く 2 度目の PO 判断)。

**打ち切りの目安**(自己申告): **7 周目でも「前周の反映が塞ぐ範囲を狭めた」型が出たら、
打ち切り 3 案を提示する。**

### 7 周目(反映差分・**`可決 P0 0 / P1 0 / P2 1`**)

**初めて `P0`・`P1` がともに 0 になった。** 残る `P2` 1 件を **7.3-2 の「P0/P1 ゼロ・P2 あり」行**に従い
一括裁定・採用・反映。

| # | 重大度 | 起因 | (A)/(B) | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P2 | 起因 | (-) | **起案行の「保証しないもの #5」が旧来の「検査器自身の改変」のまま。** 本文は状態条件「検査器が本節の要求どおりに動作すること」へ更新済み。**規範の欠落ではなく要約語の反映漏れ** | **採用**。起案行を本文へ同期 |

**レビューが確認した点**(私が観点として挙げたもの):

- **③ を「前提」と位置づけることと 7.7-5 の fail-closed に矛盾はない**
- **保証条件そのものは起案行でも正しい。同一変更・先行変更の両経路も本文で列挙済み**
- **6 周目に危惧した「前周の反映が塞ぐ範囲を狭める」型は再発しなかった**(**打ち切りの目安に到達せず**)

**周ごとの推移**:

| 周 | 範囲 | P0 | P1 | P2 | 母集団 | 起因 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 全文 | 1 | 4 | 0 | 5 | 5 |
| 2 | 差分 | 0 | 2 | 1 | 2 | 2 |
| 3 | 差分 | 1 | 2 | 0 | 3 | 3 |
| 4 | 差分 | 1 | 2 | 0 | 3 | 3(**PO 裁定: 範囲確定**)|
| 5 | 全文 | 2 | 1 | 0 | 3 | 2 |
| 6 | 差分 | 1 | 0 | 1 | 1 | 1(**6 周警告 → PO 判断: 続行**)|
| 7 | 差分 | **0** | **0** | 1 | **0** | — |

**エスカレーション判定**: 母集団 0 のため**不成立**(連続が切れた)。

**次は最終全文確認周**(7.3-2)。**approved になる版そのものを全文で確認する。**

### 最終全文確認周 1 回目(**`可決 P0 0 / P1 0 / P2 1`**)

| # | 重大度 | 起因 | (A)/(B) | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P2 | **非起因** | (-) | **起案行に `****`(強調記号 4 連続)が残り、CommonMark で文字として露出する。** 規範の意味は変えないが**継ぎ接ぎの痕** | **採用**。修正 |

**自己点検で 1 件追加**: **本文 7.7-6 の見出し末尾にも同じ編集痕**(`)**。**` の宙ぶらりんな強調)があった。
**同時に修正した。** **修正後、文書全体の `****` は 0 件**(機械走査)。

**`**。**` 自体は欠陥ではない** — **本書全体で数十箇所使われている記法**である
(`:39`・`:447`・`:1075` ほか)。**指摘は `****`(4 連続)に限られる。**

**7.3-2 の「最終全文確認周: P2 のみ」行**に従い、**採用反映があったので最終全文確認周を再実施する**
(approved になる版そのものを必ず全文確認するため)。

**レビューが全文で確認した結果**: **P0・P1 とも 0 件。**
**7 周の編集による矛盾・重複・規範の欠落は検出されなかった。**

### 最終全文確認周 2 回目(再実施)— **`可決 P0 0 / P1 0 / P2 0`・指摘なし → 収束**

**7.3-2 の「最終全文確認周: 指摘ゼロ → 収束(人間承認へ)」。** **本周はカウントしない**(収束確認周)。

**確定ゲートの全経過**:

| 周 | 範囲 | P0 | P1 | P2 | 母集団 | 起因 | 特記 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 全文 | 1 | 4 | 0 | 5 | 5 | 7.7-7 新設 |
| 2 | 差分 | 0 | 2 | 1 | 2 | 2 | 「信頼できる比較元」除去 |
| 3 | 差分 | 1 | 2 | 0 | 3 | 3 | 食い違いの帰属分割 |
| 4 | 差分 | 1 | 2 | 0 | 3 | 3 | **PO 裁定: 範囲確定** → 導出要求へ |
| 5 | 全文 | 2 | 1 | 0 | 3 | 2 | 検査器改変で保証が破れる(非起因)|
| 6 | 差分 | 1 | 0 | 1 | 1 | 1 | **6 周警告 → PO 判断: 続行** |
| 7 | 差分 | 0 | 0 | 1 | 0 | — | P2 一括反映 |
| 8 | 最終全文 | 0 | 0 | 1 | 0 | — | 体裁不備 → 再実施へ |
| 9 | 最終全文(再) | **0** | **0** | **0** | 0 | — | **収束** |

**`確定ゲート周回` = 8**(採用反映を伴った周のみ計上。9 周目は収束確認周で計上しない)。
**指摘 22 件・全件採用・不採用 0 件・(B) の送り先 0 件。**
**`P0` は 1・3・4・5・6 周目に計 6 件**、**すべて「保証範囲の過大主張」か「塞ぐ範囲の限定」**だった。

**PO の関与は 2 回**: 4 周目の**範囲確定**、6 周目の**続行の明示指示**。

**人間承認待ち**(7.3 手順 5)。

### 人間承認(7.3 手順 5)

**承認: 2026-09-14・山田正輝。**

**提示した内容**: 条文 7 項の要約 + **7.7-7 が「保証しない」と明記した 5 件**
(承認の真正性 / 比較元の内容 / 検査が実行されたこと / 複数変更の合成 / 検査器が要求どおり動作すること)
+ ゲートの経過(8 周・22 件・全件採用・不採用 0 件・`P0` 6 件はすべて同一の型)。

**承認の実質は「保証しない 5 件を受け入れるか」**であることを明示したうえで承認を得た。

**承認後の処理**(7.3 手順 6): frontmatter を `approved` へ / 変更履歴行へ**確定ゲート通過の記録**
(周ごとの重大度内訳・PO 裁定 2 回・`P0` の型)を追記し状態を `approved` へ / `docs/README.md` 索引を現行化。

### ステップ 4: 基準台帳と検査器

`contracts/authz/frozen-baselines.json` に commit 型 3 系列の初期記録を置き、
`scripts/check_frozen_baselines.py` で F-1〜F-7 を検査する。CI は `harness` ジョブの
`fetch-depth: 0`(`.github/workflows/ci.yml:78`)の下で、専用 step(`:89`)として実行する。

- CI と同一コマンド・引数 `uv run python scripts/check_frozen_baselines.py --base origin/develop` —
  正常台帳は **exit 0**
- N9 を仕込んだ `git clone --shared` の一時複製で同じコマンド・引数を実行 — **exit 1**。
  `F-7: baselines.oracle_input[0].commit が base 側の ORACLE_INPUT_BASELINE_COMMIT と一致しない`
- 検査器ソース内の 40 桁 hex 直書き — **0 件**

### ステップ 5: oracle_input の移設と allow-list 走査

`scripts/check_authz_catalog.py` の `oracle_input` 基準を、台帳の同系列末尾から fail-closed で
読む形へ移した。40 桁 hex はソース本文を部分一致で走査し、
`scripts/frozen-baseline-scan-allowlist.json` の `(パス, 値)` と双方向で完全一致させる。
`pending_removal: true` の 3 件は、台帳が base に存在しない移行中だけ許可する。

- 変更前(同一正規表現で `HEAD` を走査): **14 出現**
- 変更後: `check_frozen_baselines.py --base origin/develop` — **exit 0**、
  `scan_occurrences=13 scan_pairs=9 scan_values=5 pending_removal=3`
- N11(走査にだけ存在)・N12(allow-list にだけ存在): 一時 `git clone --shared` 上でそれぞれ
  **exit 1**。`tests/test_check_frozen_baselines.py` は **8 passed**
- `check_authz_catalog.py` — **ok**、ルート `ruff` / `ty` — **green**、
  ルート `pytest tests/` — **1354 passed**
- backend `pytest --ignore=tests/db` — **199 passed**、`-m frozen_negative` —
  **2 passed, 4 deselected**(N2 を含む負例が引き続き期待どおり red)

### ステップ 6: fail-closed 化と F-8

`.git` がある実行経路では、oracle commit 上の入力 blob を `git rev-parse` で解決できなければ
即座に red とし、エラーへ commit・対象パス・Git stderr を含める形へ変えた。
`.git` を持たない凍結資産コピーの既存経路は残し、正常資産が green のままであることも固定した。

- N4 変更前: 到達不能 commit へポインタと封印を追随させた一時 `git clone --shared` で
  `validate_oracle_seal` — **green**(`rev-parse` の非0終了を黙って通過)
- N4 変更後: 同じ変異を **`CatalogError` で red**。commit・入力パス・実際の Git stderr を
  テストで完全一致確認
- F-8: CI の `run` コマンドから凍結基準検査へ到達するジョブを機械抽出し、
  **`harness` / `backend` の exact-set** と両 checkout の **`fetch-depth: 0`** を確認
- N14: 一時 clone の `harness` から `fetch-depth: 0` を除去 — **F-8 で red**
- `check_authz_catalog.py` / `check_frozen_baselines.py --base origin/develop` — **exit 0**
- ルート `ruff` / `ty` — **green**、ルート `pytest tests/` — **1358 passed**
- backend `pytest --ignore=tests/db` — **199 passed**、`-m frozen_negative` —
  **2 passed, 4 deselected**(N1・N2 が引き続き期待どおり red)

### ステップ 7: oracle_meaning と core_areas_guard の移設

`STEP2_BASE_REVISION` と重複していた `AUTHZ_STEP2_BASE_REVISION` は、台帳の
`oracle_meaning` 系列末尾を読む形へ統合した。`AUTHZ_GUARD_BASE_REVISION` は対象が異なるため、
独立した `core_areas_guard` 系列末尾から読む。ルート側の 2 テストは共通の台帳読取関数を利用し、
別 pytest root の backend 側はデータ読取境界だけを持つ。いずれも読取不能・空系列・不正値を
fail-closed で扱う。

- allow-list 走査: **13 → 10 出現**、`scan_pairs=6 scan_values=4 pending_removal=0`
- 一時 `git clone --shared` の台帳で `oracle_meaning` だけを 1 件進めても、
  `core_areas_guard` の履歴と末尾は不変で、core-guard の exact-set 検査も **green**
- `check_authz_catalog.py` / `check_frozen_baselines.py --base origin/develop` — **exit 0**
- ルート `ruff` / `ty` — **green**、ルート `pytest tests/` — **1359 passed**
- backend `pytest --ignore=tests/db` — **199 passed**、`-m frozen_negative` —
  **2 passed, 4 deselected**(N1・N2 が引き続き期待どおり red)
- `pytest tests/test_core_guard.py` — **134 passed**

### ステップ 8: corpus_versions と corpus_version の新設

台帳へ version 型の `corpus_versions` 初版を追加し、母集合と派生 3 資産へ
`corpus_version: 1` を追加した。version 記録は `version` / `canonical_sha256` / 承認 3 項目の
exact-set で、`supersedes` は持たない。commit 型の F-1・F-2・F-5〜F-7 は適用せず、
共通の F-3・F-4 と G-1〜G-5 を検査する。

- 母集合の canonical digest は既存 authz 資産と同じ正規化で算出し、台帳末尾と一致
- N7: 母集合本文だけを変え、版と派生 3 資産を据え置いた一時 `git clone --shared` —
  **G-2 だけで exit 1**
- N8: 母集合と台帳を version 2 + 同一 canonical digest へ進め、派生だけ据え置いた複製 —
  **G-5 だけで exit 1**
- version 系列の F-3、F-4/G-3、1 からの連番 G-4、母集合と台帳の版一致 G-1 も独立負例で確認。
  G-5 は派生 3 資産を 1 件ずつ未追随にして全入口を確認し、
  `tests/test_check_frozen_baselines.py` は **16 passed**
- `check_frozen_baselines.py --base origin/develop` — **exit 0**、
  `scan_occurrences=10 scan_pairs=6 scan_values=4 pending_removal=0`
- `check_authz_catalog.py` — **exit 1**。唯一の理由は
  `contracts/authz/requirement-claims.json: oracle input blob が不一致`
- 未再封印の入力差分は母集合・派生 3 資産・派生 lock 3 資産の **exact-set 7 件**。
  `--reseal-oracle` は未実行
- ルート `ruff` / `ty` — **green**、ルート `pytest tests/` — **1367 passed**
- backend `pytest --ignore=tests/db` — **199 passed**、`-m frozen_negative` —
  **2 passed, 4 deselected**(N1・N2 が引き続き期待どおり red)

### ステップ 9: 派生 3 資産の digest 辺を版参照へ置換

派生 3 資産の `input_manifest` から、母集合と母集合 lock を指す blob digest 2 キーを
それぞれ削除した。`corpus_version` の一致は `check_frozen_baselines.py` の G-5 に一元化し、
共用の `_validate_derived_input_manifest` では入力元を示すパス 2 キーの exact-set、
リポジトリ内への解決、参照先の存在だけを検査する。パスは生成元の所在を示す provenance として
意味を持つため残した。

- design.md 4-1 と同じ機械走査を `check_frozen_baselines.py` に実装し、変更前
  (ステップ 8 終了時)は **22 本**、変更後は **16 本**。変更前の内訳は
  oracle seal 14 / 派生 3 資産 6 / 母集合 1 / 台帳 1、変更後は
  oracle seal 14 / 母集合 1 / 台帳 1
- ステップ 8 の台帳追加前を起点にしたタスク全体では **21 → 16 本**で純減 5 本。
  派生 3 資産の `requirement_claims_blob_digest` と
  `requirement_claims_lock_blob_digest` は **0 件**
- `--reseal-derived --skip-oracle` — **exit 0**。派生 lock 3 資産は各
  `asset_digest` だけが追随し、通常の派生資産検査も green。
  **`--reseal-oracle` は実行していない**
- `check_frozen_baselines.py --base origin/develop` — **exit 0**、
  `scan_occurrences=10 scan_pairs=6 scan_values=4 pending_removal=0 digest_edges=16`。
  N7・N8 を含む `tests/test_check_frozen_baselines.py` は **16 passed**
- `check_authz_catalog.py` — **exit 1**。唯一の理由は
  `contracts/authz/requirement-claims.json: oracle input blob が不一致`
- 二段コミット中の入力差分が N1 の意味改ざん検出を先取りしないよう、負例用の一時 clone だけで
  seal が指す入力 8 資産を固定基準版へ戻す。N1・N2 の assertion は変更せず、
  `-m frozen_negative` は **2 passed, 4 deselected**
- ルート `ruff` / `ty` — **green**、ルート `pytest tests/` — **1367 passed**、
  backend `ruff` / `ty` — **green**、`pytest --ignore=tests/db` — **199 passed**

### ステップ 10: oracle_input 基準の追記と再封印

台帳の `oracle_input` 系列へ、ステップ 9 の完了コミット
`b64fdefc784c6cdc802ff674903f31b0b0ec83e7` を 2 件目として追記した。既存 1 件は
HEAD 上の記録とバイト相当で一致したままで、追記の `supersedes` は直前の
`0cf994f4aa6ca51331a62c05fcd6e0756c4492d2` と一致する。

`--reseal-oracle` は `oracle_commit` を動かさない実装であることを先に確認し、seal と封印 6 資産の
ポインタをステップ 9 コミットへ揃えてから実行した。母集合・派生資産の再封印はステップ 8・9 で
完了済みのため、本ステップでは実行していない。

- `--reseal-oracle` — **exit 0**、`oracle-resealed`。seal の `oracle_commit` は
  `0cf994f… → b64fdef…`
- `input_assets` 8 件のうち、ステップ 8・9 で内容が変わった **7 件の
  `git_blob_digest` を更新**。不変だった `requirement-claims.lock.json` の 1 件は動かなかった。
  更新後は 8 件すべてで worktree blob = `b64fdef…` 上の blob = seal 記録値
- `sealed_assets` 6 件は `oracle_context.oracle_commit` の更新を内容へ反映し、
  **6 件すべての `canonical_sha256` を更新**。各値は現在の資産内容と一致
- seal から `oracle_commit` と計算対象 digest を除いた全フィールドは変更なし。
  封印 6 資産も `oracle_context.oracle_commit` 以外は変更なし
- `failure-injection-points.json` は更新後の `ddl-elements.json` を直接参照するため、
  `source_asset.git_blob_digest` 1 件を現在の blob へ追随。これはルート `source_asset` 配下であり、
  design.md 4-1 の digest 辺には含まれないため `digest_edges` は 16 のまま
- 同様に `mcdc-map.json` の `sources.claim_mutant_map.blob_digest` 1 件を、更新後の
  `claim-mutant-map.json` の blob へ追随。こちらもルート `sources` 配下のため
  `digest_edges` の対象外
- `check_authz_catalog.py` — **exit 0**、通常実行で `ok`。
  `check_frozen_baselines.py --base origin/develop` — **exit 0**、`digest_edges=16`
- N1・N2 の assertion は変更せず、`-m frozen_negative` は
  **2 passed, 4 deselected**。正当な再封印後も意味改ざんと未承認入力変更を拒否
- ルート `ruff` / `ty` — **green**、ルート `pytest tests/` — **1367 passed**、
  backend `ruff` / `ty` — **green**、`pytest --ignore=tests/db` — **199 passed**

### ステップ 11: 負例 14 件の通し確認と効果測定

#### 負例の exact-set

両 pytest root の Python ソースを AST で走査し、`pytest.mark.frozen_negative` が付いた
`(リポジトリ相対パス, テスト名)` の組を数える横断検査を追加した。テスト名の接頭辞は識別に使わないため、
本タスクと無関係な `tests/test_orm_acceptance_sheets.py` の
`test_n7_catalog_claim_is_covered_by_schema_audit` は母集団に入らない。

| 負例 | marker の付いたテスト |
| --- | --- |
| N1 | `backend/tests/test_authz_mutation_composition_full.py::test_frozen_oracle_rejects_meaning_tampering_after_reseal` |
| N2 | `backend/tests/test_authz_mutation_composition_full.py::test_frozen_oracle_rejects_input_change_without_baseline_advance` |
| N3 | `tests/test_check_frozen_baselines.py::test_n3_empty_approved_by_is_red` |
| N4 | `tests/test_check_authz_catalog.py::test_n4_unreachable_oracle_commit_is_red` |
| N5 | `tests/test_check_frozen_baselines.py::test_n5_changed_existing_approval_is_red` |
| N6 | `tests/test_check_frozen_baselines.py::test_n6_unlinked_supersedes_is_red` |
| N7 | `tests/test_check_frozen_baselines.py::test_n7_changed_corpus_without_version_advance_is_red` |
| N8 | `tests/test_check_frozen_baselines.py::test_n8_derived_assets_must_follow_corpus_version` |
| N9 | `tests/test_check_frozen_baselines.py::test_n9_initial_commit_mismatch_is_red` |
| N10 | `tests/test_check_frozen_baselines.py::test_n10_changed_base_source_constant_is_red` |
| N11 | `tests/test_check_frozen_baselines.py::test_n11_unlisted_source_pair_is_red` |
| N12 | `tests/test_check_frozen_baselines.py::test_n12_stale_allowlist_pair_is_red` |
| N13 | `tests/test_check_frozen_baselines.py::test_n13_pending_removal_after_ledger_introduction_is_red` |
| N14 | `tests/test_ci_wiring.py::test_n14_missing_fetch_depth_is_red` |

N13 は計画の割り当て漏れ(`3dbbf95` で記録)を補修した。台帳が存在する clone の `HEAD` を base にし、
実在する allow-list 登録 1 件を `pending_removal: true` に変えると、検査器は **exit 1**、
`台帳が base に存在するため pending_removal=true` となった。

- 横断 exact-set と欠落変異: **2 passed**。一時コピーから N14 の marker だけを消すと、
  `missing=[(..., 'test_n14_missing_fetch_depth_is_red')]` で exact-set 自体が red になる
- harness root の `-m frozen_negative`: **14 passed, 1358 deselected**。論理識別子は N3〜N14 の
  12 件で、N8 を派生 3 資産について実行するため pytest case は 14 件
- backend root の `-m frozen_negative`: **2 passed, 4 deselected**(N1・N2)
- marker で数えた論理識別子は、両 root 合計で **ちょうど 14 件**

#### digest 辺と手計算対象の変更前後

`git clone --shared` の一時複製を `origin/develop@569954d1a8a58af72f7c827090920e4f1697ef21`
へ detached checkout し、現在の `_enumerate_digest_edges` を両ツリーへ適用した。

| 時点 | digest 辺 | 機械出力の内訳 |
| --- | ---: | --- |
| `origin/develop` | **21** | oracle seal 14 / 派生 3 資産 6 / 母集合 1 |
| 現在(`3dbbf952c63e3dc706f81f9e54cc197cfb46c3cc`) | **16** | oracle seal 14 / 母集合 1 / 台帳 1 |

同じ一時複製に対し、派生 3 資産の `requirement_claims_blob_digest` /
`requirement_claims_lock_blob_digest` と、台帳の `corpus_versions[].canonical_sha256` を機械列挙した。

- `origin/develop`: **6 件**(派生 3 資産 × 2 キー)
- 現在: **1 件**(`frozen-baselines.json:corpus_versions[0].canonical_sha256`)

#### 要件書 1 バイト改訂の追随実測

現在 HEAD の `git clone --shared` 上だけで実施した。要件書 frontmatter の
`status: approved` の末尾へ空白 1 バイトを足し、**260023 → 260024 bytes(delta=1)** を確認した。
既存の分類判断は使い回し、抽出器の 1080 source item から母集合の本文・digest・manifest を再生成した。

1. 要件書だけをコミット: `5c9fba5a72f460524ba2c6be5705785c5ec25d58`
2. 母集合と派生 3 資産を `corpus_version: 2` へ進め、母集合・派生 lock を再封印し、
   `corpus_versions` を追記: `8680f2e06c077bf2b8463baf21d9d828b6f83a18`
3. `oracle_input` を同コミットへ追記(`supersedes=b64fdefc784c6cdc802ff674903f31b0b0ec83e7`)し、
   oracle 6 資産と seal を追随して `--reseal-oracle`:
   `133e045f53d564b1bc15c0e2842f0446ea048175`

`--reseal` は `ok total=1080 auth_claim=184 out_of_scope=896 resealed`、
`--reseal-derived` は同件数に加えて `db_claims=187 routes=37 cells=12 derived-resealed`、
`--reseal-oracle` は `oracle_claims=198 ... mutants=231 cut_sets=24 oracle-resealed` で完了した。
通常の `check_authz_catalog.py` も **exit 0** となった。一時 clone の最終 worktree は clean だった。

初期 `3dbbf95` と最終 `133e045` の間を
`git diff --name-only/--numstat -- scripts backend/tests tests` で比較した結果は、開始・終了マーカー間が
どちらも**空**であり、検査器と両 test root のソース変更は **0 ファイル・0 行**だった。

初回の追随実測では、`corpus_versions` の追記自体が `baselines` 配下の digest 辺を
1 本増やすため、`check_frozen_baselines.py --base 3dbbf95...` が **exit 1**、
`digest 辺: ... actual=17, expected=16` となった。検査器が現在本数 16 をソース定数で持つため、
正当な version 追記のたびに検査器ソースの編集が必要になる欠陥をここで検出した。

ユーザー判断によりステップ 11 内で補修した。固定合計を削除し、資産ごとの期待を次の構成から導出する。

- oracle seal = `len(input_assets) + len(sealed_assets)`
- 母集合 = 1
- 台帳 = `len(baselines.corpus_versions)`
- 派生 3 資産 = 各 0
- それ以外の `contracts/**/*.json` = 0

正当な `corpus_versions` 追記は `digest_edges=17` で green、派生資産へ
`requirement_claims_blob_digest` を 1 本戻す変異は、当該資産が `(actual=1, expected=0)` となって red
になることをテストで固定した。関連する台帳・exact-set テストは **21 passed**。新しい述語・負例番号は
追加していない。

修正版を基準とする別の一時 clone で同じ 1 バイト追随を再実行した。要件書は再び
**260023 → 260024 bytes(delta=1)**、母集合は 1080 item、`corpus_version: 2` として再生成した。

1. 修正版の測定基準: `627bd614e9d3beb1dc26ac4d8677de3e477e0ffa`
2. 要件書 1 バイト改訂: `5248edd8cfb39495b271ca82f1727e2fcbce4da2`
3. 母集合・派生・版台帳の追随: `e2b3aa650789452eb5c0a0f1136d0c26e36c6906`
4. oracle_input 追記と再封印: `1a839cebb09a08d9c422fd5213a55599cfe801b8`

修正後は通常の `check_authz_catalog.py` が **exit 0**、
`check_frozen_baselines.py --base 627bd614...` も **exit 0**、
`pending_removal=0 digest_edges=17` となった。初期と最終の
`git diff --name-only/--numstat -- scripts backend/tests tests` はいずれも空で、ソース変更は
**0 ファイル・0 行**。最終 worktree も clean であり、検査器ソースを編集せず追随を完走できた。

#### DoD 突合

| # | 計画書 5 節の項目 | 状況 | 根拠・残件 |
| ---: | --- | --- | --- |
| 1 | 7.7 が approved・v1.15 | 充足 | 正本 frontmatter と変更履歴が approved・v1.15 |
| 2 | 凍結基準 SHA のソース直書き 0 | 充足 | allow-list 走査 10 出現は全件 NFR-021 のダミー値。基準値は台帳から読む |
| 3 | 未登録 `(path, value)` を拒否(N11) | 充足 | N11 が red を確認 |
| 4 | 消えた allow-list 登録を拒否(N12) | 充足 | N12 が red を確認 |
| 5 | 本文部分一致走査、14→13→10 | 充足 | ステップ 5・7 の機械出力を記録済み。現在 10 |
| 6 | `pending_removal=0` と期限(N13) | 充足 | 現在 0。N13 を本ステップで補修し red を確認 |
| 7 | 4 系列・追記のみ(N5) | 充足 | 台帳 4 系列、N5 が red |
| 8 | commit/version 型の述語分離 | 充足 | version 記録に `supersedes` なし。F-3/F-4 + G-1〜G-5 |
| 9 | 台帳へ入る digest 参照が無い | 充足 | seal の入力・封印対象外で、`contracts/authz` 内に台帳パスへの参照なし |
| 10 | meaning 更新と core guard の独立 | 充足 | ステップ 7 の一時 clone 実測を記録済み |
| 11 | 記録なしの基準移動を拒否(N3・N6) | 充足 | 両負例が red |
| 12 | 到達不能 oracle commit を拒否(N4) | 充足 | N4 が red |
| 13 | F-8 と `fetch-depth: 0`(N14) | 充足 | 到達 2 ジョブを固定し、N14 が red |
| 14 | N1・N2 を維持 | 充足 | backend marker 実行 2 passed |
| 15 | 両 root の負例 14 件を exact-set | 充足 | marker の `(path, name)` が 14 件。1 marker 除去も red |
| 16 | 母集合/派生の版上げ忘れ(N7・N8) | 充足 | N7 と N8 の 3 派生 case が red |
| 17 | 移行初期値すり替え(N9) | 充足 | N9 が red |
| 18 | F-7 が base 側ソースを読む(N10) | 充足 | N10 が red。検査器に基準値なし |
| 19 | CI 結線と N9 の同一コマンド実測 | 充足 | ステップ 4 に exit 1 と CI 行を記録済み |
| 20 | digest 辺 21→16 | 充足 | 本ステップで `origin/develop` と現在を機械列挙 |
| 21 | 手計算 digest 6→1 | 充足 | 本ステップで対象キーを機械列挙 |
| 22 | 1 バイト改訂をソース編集なしで追随 | 充足 | 修正後はソース差分 0 行で authz・台帳検査とも green。台帳は履歴 2 件から17本を導出 |
| 23 | H-85 対応・候補解消・候補 6 件を台帳へ追記 | **未充足** | ステップ 12 のクローズ処理範囲。`harness-evaluation.md` へ未追記のまま渡す |
| 24 | 敵対レビューと人間の逐行確認 | **一部充足** | 正本の確定ゲートと PO 承認は完了。実装差分の逐行確認はステップ 12 |
| 25 | design.md 3-4 の保証しない欄と実挙動 | 充足 | 承認欄コピー・base 自体の改変・同一 base の複数 PR・検査器弱体化は、実装も保証していない |

突合結果は **23 項目充足 / 1 項目一部充足 / 1 項目未充足**。残る 2 項目はいずれも
ステップ 12 のクローズ処理に割り当てられている。

**ステップ 12 への未充足**: ① `harness-evaluation.md` の H-85 対応・候補解消・新規候補 6 件が未追記
(ステップ 12 のクローズ処理で行う) ② コア領域の実装差分に対する人間の逐行確認が未実施。

指定検証の結果:

- ルート `ruff check .` / `ty check` — **green**
- ルート `pytest tests/` — **1372 passed**
- `check_authz_catalog.py` — **exit 0**、`ok total=1080 auth_claim=184 out_of_scope=896 ...`
- `check_frozen_baselines.py --base origin/develop` — **exit 0**、
  `scan_occurrences=10 scan_pairs=6 scan_values=4 pending_removal=0 digest_edges=16`
- backend `pytest --ignore=tests/db` — **199 passed**


## 結果サマリ(クローズ処理)

**TSK-379 から持ち越した「入力ベースラインが永久に動かせない」欠陥を、規範と機構の両方で解いた。**

### 何を作ったか

| 層 | 成果物 |
| --- | --- |
| **規範** | ハーネス設計書 **`7.7 凍結基準の更新経路`(v1.14 → v1.15・approved)** — 7 項。確定ゲート 8 周・指摘 22 件を全件採用・不採用 0 件 |
| **機構** | `contracts/authz/frozen-baselines.json`(**追記のみの基準台帳・4 系列**)/ `scripts/check_frozen_baselines.py`(述語 `F-1`〜`F-8`・`G-1`〜`G-5`)/ `scripts/frozen-baseline-scan-allowlist.json`(両方向 fail-closed の走査)/ `ci.yml` への結線 |
| **連鎖** | `H-85` 対応案② — 派生 3 資産の digest 固定を `corpus_version` の版参照へ |

### 測れた効果

| 指標 | 前 | 後 |
| --- | --- | --- |
| 凍結基準の直書き | **4 箇所** | **0** |
| 資産全体を指す digest 辺 | **21** | **16**(純減 5)|
| 手で計算する digest | **6** | **1** |
| `git rev-parse` 失敗時 | **黙って緑**(fail-open) | **red**(fail-closed)|
| 40 桁 OID の出現(走査) | 14 | **10**(全部ダミー)|
| **要件書 1 バイト改訂への追随** | **検査器のソース編集が必須** | **0 ファイル・0 行** |

**最後の行が本タスクの目的そのもの**である。一時複製で 4 コミット分の追随を完走し、
`scripts` / `tests` / `backend/tests` の差分が空であることを `git diff --numstat` で確認した。

### 負例 14 件(両 pytest root 横断の exact-set で固定)

**すべて変異で「空洞でない」ことを確かめた。**

| 変異 | 落ちる負例 |
| --- | --- |
| `F-7` の比較元を検査器へハードコード | `N10` |
| `F-4`(追記のみ)を no-op 化 | `N5` |
| 走査の未登録方向を無効化 | `N11` のみ |
| 走査の古い登録方向を無効化 | `N12` のみ |
| fail-closed を fail-open へ戻す | `N4` |
| `fetch-depth: 0` を外す | `F-8` ほか 6 件 |
| **`core_areas_guard` を `oracle_meaning` へ統合** | **暗黙リベース検出テスト** |
| `G-2` を無効化 | `N7` のみ |
| `G-5` を無効化 | `N8`(派生 3 資産すべて)|
| 負例の marker を 1 件外す | **横断 exact-set** |

### 自分の側の失敗

**計画レビュー 6 周 + 確定ゲート 8 周で受けた指摘は、私の設計の欠陥である。**
**全 38 + 22 件を `design.md` 8 節と本 worklog に残した。** 繰り返した型は 5 つ:

1. **測らずに数を書く**(「4 段 → 3 段」「6 本減」)
2. **機械の保証範囲を過大に言う**(`P0` 6 件中の多数がこれ)
3. **母集団を手で列挙する**(直書きを 3 件と数えて 4 件目を落とした)
4. **訂正を全文へ波及させない**(計画レビュー・確定ゲートの両方で再発)
5. **新設要素を既存の要件と突き合わせない**(**本タスクが新設した条文に本タスクの実装が反した**)

**6 つすべてを台帳の候補へ記録した。**

### 残件

- **運用評価台帳の候補 6 件**は未採番(昇格条件を各件に記載)
- **`function-bodies/manifest.json` の `source_commit`** は射程外・**未調査**
- **一度きりの移行検査(`F-7`)の畳み方**は未決

## 決定

| # | 決定 | 理由 |
| --- | --- | --- |
| D-1 | **台帳の要件は「連鎖の外」ではなく「連鎖の入口を持たない」** | **台帳 → 他資産の digest は anchor に必要**。**他資産 → 台帳が不可**(seal の入力になると再封印で鶏と卵) |
| D-2 | **`core_areas_guard` は `oracle_meaning` と統合しない** | **値が同じでも対象が違う**。統合すると oracle 意味基準の更新が core-guard の基準まで暗黙にリベースする |
| D-3 | **allow-list の識別単位は `(パス, 値)` の組** | 値単位だと既存の値を別ファイルへ足しても通る |
| D-4 | **走査はソース本文の部分一致**(AST 完全一致ではない) | 完全一致だと**より長い文字列に埋め込まれた 4 出現**を見落とす |
| D-5 | **`ci.yml` へ新設検査のステップを足す**(2 周目の不採用を部分的に取り消し) | **base/HEAD を要る検査は `pytest tests/` の経路では走らない** |
| D-6 | **version 型は `supersedes` を持たない** | `G-4`(1 から連番)が同じ役目。3 通りに割れていた仕様を 1 つに |

## 未決・次の一歩

**人間の計画承認待ち**(`承認: 未`)。**承認欄は人間のゲートなので自分では書かない。**

**承認後の最初のステップは 1(退行の物差し)**である — **`N1`・`N2` が現行で red になることを
先に固定してから**、機構を触る。

### 他タスクとの干渉(申し送り)

**TSK-317 PR #3 と封印手順の同じ場所を触る**(`contracts/authz/auth-catalog.json` + `oracle-seal.lock.json`)。
**PR #3 を先に**する見立てを別セッションへ回答済み(理由は同回答)。

## 差し戻し修正(PR #63 敵対レビュー)

計画書 5 節直前の「差し戻し修正」に従い、ステップ表を増やさず P0 3 件・P1 1 件と
`.git` 無し経路の明示化を補修した。先の DoD 表 #8 と決定 D-6 に記録した
「version 型は `supersedes` を持たない」は、訂正済みの設計 3-3 と本節で明示的に取り消す。

| 指摘 | 修正と実測 |
| --- | --- |
| 7.7-6 の委任 3 指定 | 台帳の4系列へ `declarations` を追加。検査器は seal と母集合の構造から対象宣言を導出し、`frozen_targets` / `identity`・`granularity` / `basis_series` の実使用値を JSON で出力する。出力4件と台帳の宣言4件が exact-set・内容とも完全一致。旧固定値定数の機械走査は0件 |
| version 型の直前基準 | `corpus_versions[0].supersedes = null` を補完し、以降は直前の `version` を要求。不連鎖へ変異すると `F-2: ... 直前の version と一致しない` で red |
| F-5 の到達可能性 | `cat-file -e` に加え `merge-base --is-ancestor <commit> HEAD` を実行。テスト内で `commit-tree` により dangling commit を作り、前者 exit 0・後者 exit 1・含む branch 0件を確認したうえで red |
| `.git` 無し | 履歴なし資産コピーは従来どおり内容検査を通すが、標準出力へ `履歴照合を省略した` と `凍結の保証対象外` を明示 |
| oracle meaning 更新経路 | 固定2資産集合を削除し、宣言対象について `基準 → HEAD` の意味差分を導出。一時 clone の台帳へ `56c281c… → 3fcc3c9…` を追記すると差分 `frozenset()` で green。承認済み意味本文との内容照合は維持し、N1 は改ざん・再封印を実際に commit した後も red |

宣言から導出した現行の3指定は `check_frozen_baselines.py` の出力で次のとおり確認した。

- `oracle_input`: 8対象 / `git_blob_digest` / `blob` / `oracle_input`
- `oracle_meaning`: sealを含む7対象 / `canonical_json` /
  `asset_without_movable_pointers` / `oracle_meaning`
- `core_areas_guard`: `.claude/core-areas.json` / `canonical_json` / `asset` /
  `core_areas_guard`
- `corpus_versions`: 母集合・派生3資産 / `canonical_sha256_and_corpus_version` /
  `canonical_json_asset` / `corpus_versions`

回帰確認では、ルート一括 **1376 passed**(authz 検査 94 件とそれ以外 1282 件)、backend は
format・ruff・ty が green、DB 除外 201 件が green。負例 inventory の exact-set は従来どおり
N1〜N14 の14件で、追加した dangling commit の F-5 負例は番号を増やさず別テストとして固定した。
`check_authz_catalog.py` と `check_frozen_baselines.py --base origin/develop` はともに exit 0、
後者の観測値は `scan_occurrences=10 pending_removal=0 digest_edges=16` のままである。

## 差し戻し修正 2 周目(7.7-6 の実装方針作り直し)

前節の `frozen-declaration-used=` は、比較処理から得た証跡ではなく台帳をそのまま表示した
エコーだった。宣言を狭めても、未知の比較方式へ変えても実処理に影響しないという敵対レビュー
2 周目の実測を受け、設計 3-4-2-B の R-1〜R-6 に従って経路を作り直した。

| 要求 | 実装と実測 |
| --- | --- |
| R-1 dispatch | `(identity, granularity)` を鍵に 4 比較戦略へ dispatch する registry を新設。4 系列をそれぞれ `unknown_identity` へ変える変異は全件 red。未登録鍵と、どの宣言からも参照されない追加戦略の両方を red にした |
| R-2 実行記録 | 各戦略が独立に導出して実際に比較した対象、registry で選んだ鍵、参照した系列を `frozen-strategy-executed=` として記録する。記録関数を no-op にする変異は stdout が空のまま `実行記録が宣言の exact-set と一致しない` で red |
| R-3 宣言変更 | base と HEAD の宣言が異なる系列は、履歴の長さが base より増えていなければ red。対象集合を変えず配列順だけを変えた変異も `基準記録の追記が伴っていない` で red |
| R-4 独立集合 | oracle input は seal の `input_assets`、oracle meaning は `sealed_assets + seal`、corpus は母集合と `input_manifest` の参照、core areas は `core_guard.py` が実際に読む定数から導出。各系列の対象を 1 件欠かす 4 変異はすべて独立集合との不一致で red |
| R-5 履歴なし | `validate_oracle_seal` は `.git` 無しを既定で例外にする。`--allow-historyless-oracle` 相当の明示時だけ処理を続け、戻り値の `history_status=skipped` と標準出力の `凍結の保証対象外` で検証済みと区別する。通常の Git 経路は `verified` |
| R-6 テスト導出 | oracle meaning の正例から旧 2 パスの固定集合を削除。clone の台帳末尾を HEAD へ進めるテストは、テストソースの bytes が不変のまま差分集合 `frozenset()` と検査 green を確認した |

比較戦略の出力は宣言から再構成せず、戦略の実行後にだけ生成する。現行実行では 4 系列すべてで
出力した対象集合・鍵・基準系列が台帳と完全一致した。`check_authz_catalog.py` と backend の
oracle meaning、core guard の基準読取もそれぞれ registry を通り、実比較後の記録を出力する。

検証結果:

- ルート `ruff check .` / `ty check` — **green**
- ルート `pytest tests/` — **1387 passed**(`615.21s`)
- `tests/test_check_frozen_baselines.py` — **33 passed**
- 変更した authz catalog / core guard の通し — **229 passed**
- backend `ruff format --check .` / `ruff check .` / `ty check` — **green**
- backend `pytest --ignore=tests/db` — **201 passed**
- 負例 inventory exact-set — **2 passed**。root の marker 実行は **14 passed**、backend の
  N1・N2 は **2 passed**で、いずれも仕込んだ負例が非 0 / 例外になることを維持
- `check_authz_catalog.py` — **exit 0**、比較戦略の実行記録 1 件を出力
- `check_frozen_baselines.py --base origin/develop` — **exit 0**、比較戦略の実行記録 4 件、
  `scan_occurrences=10 scan_pairs=6 scan_values=4 pending_removal=0 digest_edges=16`
