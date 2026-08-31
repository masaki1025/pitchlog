---
date: 2026-09-01
topic: COURSE_COORDINATE_SIZE の契約一致テストの整備(NFR-018 違反状態の解消 — H-61)
branch: feature/course-coordinate-contract
---

# 作業ログ: 2026-09-01 COURSE_COORDINATE_SIZE の契約一致テストの整備

## やったこと

## 決定

## 未決・次の一歩

## やったこと

- /task-start: Notion タスク **TSK-233**(既存・優先度 高・見積 2pt)を取得・
  `feature/course-coordinate-contract` の worktree を `origin/develop`(`1ab778f`)から作成・
  計画書雛形と本ログを作成

## 着手時に実地で確認した現状(NFR-018 違反状態)

| 箇所 | 内容 |
| --- | --- |
| `frontend/src/lib/courseInputView.ts:4` | `export const COURSE_COORDINATE_SIZE = 263` — **ハードコード** |
| `frontend/src/lib/displayGeometry.ts:6` | `export const DISPLAY_COORD_SIZE = geometry.size` — **契約 `contracts/display_geometry_263_v1.json` 由来** |
| `frontend/src/lib/displayGeometry.spec.ts` | `DISPLAY_COORD_SIZE` が `263` であることだけを固定。**`COURSE_COORDINATE_SIZE` との一致は固定していない** |

→ **同一の座標系スケールが 2 箇所で独立に定義されている**。要件書 NFR-018 の達成条件 (c)
(逐語移植対象の例外は「検証テストが存在し契約値との一致を固定している」ことを例外成立の条件とする)
を満たしておらず、**例外表の当該行は「有効化待ち」**のまま。

## 未決・次の一歩

- /plan で計画書を書く。**論点は 3 つ**:
  1. **要件書 NFR-018 の例外表の状態を「有効」へ更新する**のは**正本の改訂**にあたる。
     **確定ゲート(7.3)の要否を計画段階で判定する**(Notion 本文の指示)。
     表の**行の追加・削除・失効**はいずれも改訂ゲートだが、**状態欄の更新が「実装追随」で足りるか**を
     7.6-3 の決定表で判定する
  2. **評価台帳 H-61 の残余の消し込み**は `docs/development/harness-evaluation.md` に触れる。
     **他の担当者がハーネスを触っている期間**(2026-09-01 時点)なので、**衝突を避ける扱いを決める**
     (最後の 1 コミットに寄せ、着手直前に `origin/develop` を取り直して差分を確認する)
  3. **変異の実測**が DoD に入っている(「値をずらすと落ちることを変異で実測した」)。
     **契約 JSON 側の値を変える / 定数側を変える の両方向**で測る
- **やらないこと**(Notion 本文が明示): **重複定義そのものの解消**
  (`COURSE_COORDINATE_SIZE` を契約参照へ寄せる)。**逐語移植の受入条件を壊すため別タスク**

## /plan — 計画レビュー 4 周で収束・承認(2026-09-01)

`/investigate` は**飛ばした**。確かめるべき事実が 3 つ(要件書 `NFR-018` (c) の例外表 / 台帳 `H-61` /
逐語移植の卒業条件)しかなく場所も分かっていたため、**Claude が原典を直接読んで計画に書いた**。

**重さ分類は コア領域**。根拠は**設計書 6.3 の境界定義表が状況計算の含む側に
「座標変換・捕球選手推定(旧システムで 3 箇所コピー・**静かなデータ破壊**の事故前例 — 改善台帳
`I-4`・`I-17`)」を明記**していること。同節は「**判定に迷うコードは含む側に倒す(fail-closed)**」とも定める。
**2pt はコア領域手続の免除条件ではない。**

### 周回と、各周で潰した穴

| 周 | 判定 | 内容 |
| --- | --- | --- |
| 1 | 否決 P1 5・P2 4 | `NFR-019` の記号の誤り / 変異の帰属 / 卒業の順序が逆 |
| 2 | 否決 P1 5・P2 3 | 例が型検査を通らない / 復元検査が index を見逃す / `ADR-003` の追跡が壊れている |
| 3 | 収束せず P1 3・P2 2 | **すべて前周の修正への指摘**(`H-22` の輪)→ **レビュー自身が打ち切りを提案** |
| 4 | **P1 1 件のみ** | **Claude の書き漏らしによる自己矛盾**(`:378` と `:266`)→ 逐語の是正案を適用 |

**3 周目でレビューが「H-22 型の閉じた輪に入っている。3 件だけ限定修正し、次周はその差分だけを検証する
最終周として打ち切るべき」と結論した**ため、**その提案を採用**して 4 周目を差分限定の最終周とし、
**新しい観点の持ち込みを明示的に禁じた**。**5 周目は回さない**(1 文の不整合で回すのは輪に入るだけ)。

### Claude 自身の誤りとして記録すべきもの(原典で確認)

1. **`NFR-019` の記号を誤っていた** — 正は **(a) クライアント/サーバー一致性・(b) 越境・(c) E2E・
   (d) 同期故障系**。「単体(a)」「一致性(c)」という区分は存在しない。
   **同じ誤記が TSK-270 の計画書(既に develop へマージ済み)の 6 節にもある**
   ((b)=越境・(d)=故障系 は正しいが **(a) と (c) が逆**)。実質の判定は正しいので機能への影響はないが、
   **TSK-270 の計画改訂 2 で直す**
2. **変異の帰属を確かめていなかった** — 「`pnpm test` 全体が red」を合格条件にしていたが、
   **変異 1・3 は既存 `displayGeometry.spec.ts:12` が殺し、変異 2 は `StrikeZone.spec.ts` が殺し得る**
   (同 spec は DOM 矩形をリテラル `263` で固定している)。**新規テストが空でも red になり得た**。
   → 台帳 `H-81` の**裏返しの型**(「落ちた」を観測しても誰が殺したか区別できない)
3. **是正が新しい穴を作った** — 2 周目の指摘に応えて「変異対象を 4 ファイルの閉じた一覧に」した際、
   **その 4 ファイルに新規 spec を入れた**。4 変異はどれも spec を変更しないので、
   **spec 自身を必ず失敗する式へ変えれば期待結果を偽装できた**。`H-81` 型。
   → **spec を変異可能対象から外して oracle として固定**し、**実行時の変異差分検査**を契約化
4. **文書の機械判定を差分行数でやろうとした** — **`NFR-018` の 6 セルは Markdown 上の 1 物理行**なので、
   **2 セル変えても 6 セル全部変えても同じ「1 行削除 + 1 行追加」**になる。→ **構造比較**へ
5. **合格不能条件を書いた** — 存在しない画面受入タスクとの相互リンクを現在確認するよう要求していた

### 発見した追跡の断裂(本タスクで是正する)

- **`ADR-003` の後続表が「例外表の卒業」欄に「検証テスト整備」を書いている** →
  **TSK-233 が終わると ADR 上は卒業済みに見える**が、実際の卒業(失効 + `D-12` の 4 操作)は未着手のまま
- **`docs/worklog/2026-08-18-adr003-domain-calc-method.md:119` も TSK-233 を卒業タスクへ対応付けている**
- **「打席入力画面の逐語移植の受入判定」を行うタスクが Notion に存在しない**
  (未完了 36 件を照会して確認 — TSK-225 は Playwright 視覚比較・TSK-226 は充足度調査)
- **`NFR-018` (c) と `ADR-003` D-12 により、卒業は受入条件を解く同一 PR で行わなければならない**
  (別タスクにすると「失効済み例外 + 重複実装」が併存する)

### 承認

**2026-09-01・山田正輝が承認。** `承認: 済(2026-09-01・山田正輝)` / 計画レビュー周回 **4 周**。

**次の一歩**: `/implement`(コア領域なので ADR-001 により **sol xhigh** が自動適用される)。

## /implement — ステップ 1: 契約一致テストの追加 + 変異による帰属確認

### 追加したテスト

- `frontend/src/lib/courseCoordinateContract.spec.ts` を追加した
- 契約 JSON を直接 import し、`COURSE_COORDINATE_SIZE` と `DISPLAY_COORD_SIZE` を
  `geometry.size` へ別々に照合する 2 テストとした
- `describe` / `expect` / `it` は `vitest` から明示 import した
- 新規 spec の変異前 SHA-256 は
  `267770319818f550fc5f33767299687705ea3e151e3cb46dbebba236b0590adc`

### テスト実行コマンド

新規 spec 単体の帰属確認には、リポジトリルートから次を実行した。

```bash
(cd frontend && NO_COLOR=1 pnpm exec vitest run src/lib/courseCoordinateContract.spec.ts --reporter=verbose)
```

変異 3 の全体実行には次を実行した。

```bash
(cd frontend && NO_COLOR=1 pnpm exec vitest run --reporter=verbose)
```

品質ゲートの全体実行には、`frontend/` で指定どおり次を実行した。

```bash
pnpm test -- --run
```

`pnpm test -- --run src/lib/courseCoordinateContract.spec.ts` はこの package script では
`vitest run -- --run ...` となりファイルを絞らず 4 ファイル全部を実行したため、単体の帰属証跡には採用せず、
上記の `pnpm exec vitest run <spec>` で実行対象が 1 ファイル・2 テストであることを確認した。

### 4 変異の期待と実測

| 変異 | 期待 | 実測で失敗した完全テスト名 | 判定 |
| --- | --- | --- | --- |
| 1. 契約 JSON の `size` だけを `264` | `T-COURSE` だけ | `courseCoordinateContract > COURSE_COORDINATE_SIZE が契約の size と一致する` | **一致**。`T-DISPLAY` は green |
| 2. `COURSE_COORDINATE_SIZE` だけを `264` | `T-COURSE` だけ | `courseCoordinateContract > COURSE_COORDINATE_SIZE が契約の size と一致する` | **一致**。`T-DISPLAY` は green |
| 3. 契約 JSON と `COURSE_COORDINATE_SIZE` を `264` | 新規 spec 単体は green。全体で少なくとも `T-EXISTING` が失敗 | 新規 spec 単体は**失敗なし**。全体は下記 5 件 | **一致**。`T-EXISTING` 以外の失敗も許容する期待どおり |
| 4. `DISPLAY_COORD_SIZE = 263` とし、契約 JSON だけを `264` | 少なくとも `T-DISPLAY` | `courseCoordinateContract > COURSE_COORDINATE_SIZE が契約の size と一致する` / `courseCoordinateContract > DISPLAY_COORD_SIZE が契約の size と一致する` | **一致**。必須の `T-DISPLAY` に加えて `T-COURSE` も失敗。JSON が `264`、`COURSE_COORDINATE_SIZE` が `263` のため |

変異 3 の全体実行で失敗した完全テスト名は次の 5 件だった。

1. `displayGeometry > 座標定義の契約を固定する` (`T-EXISTING`)
2. `StrikeZone > 右打者・捕手側 はタップ座標を捕手側保存座標へ変換する`
3. `StrikeZone > 左打者・捕手側 はタップ座標を捕手側保存座標へ変換する`
4. `StrikeZone > 右打者・投手後方 はタップ座標を捕手側保存座標へ変換する`
5. `StrikeZone > 左打者・投手後方 はタップ座標を捕手側保存座標へ変換する`

### 各変異の実行直前差分検査

各実行の直前に次を機械検査した。

- `git diff --name-only HEAD -- <変異可能対象 3 ファイル>` の集合が期待パスと完全一致すること
- 変更対象の内容が、`git show HEAD:<path>` へ意図した 1 置換だけを行った期待内容と
  `cmp -s` で一致すること
- その変異で変更しない対象が `git diff --exit-code HEAD -- <paths>` で一致すること
- `git diff --cached --exit-code HEAD -- <対象 4 ファイル>` が空であること
- 新規 spec の SHA-256 が変異前の
  `267770319818f550fc5f33767299687705ea3e151e3cb46dbebba236b0590adc` と一致すること

結果は次のとおり。

| 変異 | 実測した差分 | 結果 |
| --- | --- | --- |
| 1 | `contracts/display_geometry_263_v1.json` の `"size": 263` → `264` だけ | **PASS** |
| 2 | `frontend/src/lib/courseInputView.ts` の `COURSE_COORDINATE_SIZE = 263` → `264` だけ | **PASS** |
| 3 | 上記 2 箇所だけ | **PASS** |
| 4 | JSON の `size` と `frontend/src/lib/displayGeometry.ts` の `geometry.size` → `263` だけ | **PASS** |

全変異で新規 spec のハッシュは変異前と一致し、index 差分も空だった。

### 全変異後の復元検査

証跡追記前の変異前状態と、全変異を復元した直後を比較した。

| # | 検査 | 実測 |
| --- | --- | --- |
| 1 | working tree 差分 | **PASS** — `git diff --exit-code -- <対象 4 ファイル>` が空。未追跡の新規 spec は検査 3・4 で別途照合 |
| 2 | index 差分 | **PASS** — `git diff --cached --exit-code HEAD -- <対象 4 ファイル>` と repo 全体の双方が空 |
| 3 | path 付きハッシュ manifest | **PASS** — 下記の種別・mode・SHA-256 が変異前と完全一致 |
| 4 | porcelain v2 | **PASS** — 前後とも `? frontend/src/lib/courseCoordinateContract.spec.ts` の 1 行だけ |

復元後の manifest:

```text
contracts/display_geometry_263_v1.json|type=regular file|mode=644|raw_mode=81a4|sha256=e0c4d336e169e567325c4fd645f595ae856b4bbd7e9be3e5cde53515ff8901f6
frontend/src/lib/courseInputView.ts|type=regular file|mode=644|raw_mode=81a4|sha256=f0f0d1e8b3b2d2944f138e813536e40f8cd0ea7f55268d8c75d711d46f06fdad
frontend/src/lib/displayGeometry.ts|type=regular file|mode=644|raw_mode=81a4|sha256=559430c5d0ebf838c9c9bbf2b5cab4887707ae00ebb976b22ad75494e484ce5a
frontend/src/lib/courseCoordinateContract.spec.ts|type=regular file|mode=644|raw_mode=81a4|sha256=267770319818f550fc5f33767299687705ea3e151e3cb46dbebba236b0590adc
```

逐語移植対象 4 ファイルと既存 `frontend/src/lib/displayGeometry.spec.ts` は、復元後に
working tree / index とも HEAD 比の差分が空であることを確認した。

### 静的検査と品質ゲート

新規 spec の数値リテラルは次で確認した。契約ファイル名の `_263_` は識別子構成文字の `_` に挟まれて
いるため一致せず、独立した数値トークン `263` があれば検出する。

```bash
if rg -n '\b263\b' frontend/src/lib/courseCoordinateContract.spec.ts; then exit 1; fi
```

加えて、契約 JSON の直接 import、`vitest` からの明示 import、2 つの完全テスト名を `rg -F` で各 1 件と
確認し、新規 spec が `frontend/.prettierignore` にないことも確認した。

`frontend/` の品質ゲート結果:

| コマンド | 結果 |
| --- | --- |
| `pnpm exec prettier --check .` | **PASS** |
| `pnpm exec eslint .` | **PASS** |
| `pnpm exec vue-tsc --noEmit` | **PASS** |
| `pnpm test -- --run` | **PASS** — 4 ファイル・11 テスト |

**ステップ 2・3 には進んでいない。コミットも作成していない。**

## 射程の変更 — ステップ 2 を後続へ送った(人間の判断 2026-09-01)

**ステップ 2(要件書 `NFR-018` 例外表の 2 セル更新)を本タスクの射程から外し、
TSK-270 の母集合修正へ合流させる。** 条件は **「ユーザーのふるまいに変化がないこと」**(人間の判断)。

**条件は満たしている**(Claude が実測):

- `develop` との差分は **`.spec.ts` 1 本 + `docs/` のみ**。**製品として出荷されるファイルはゼロ**
- **新規 spec を import している製品コードは無い**(テストからのみ)
- 逐語移植 4 ファイル(`courseInputView.ts`・`displayGeometry.ts`・`spatialInput.ts`・`format.ts`)は無変更

### なぜ外したか — 要件書の 1 文字が 8 資産 + ハーネステストの更新を強制する

**ステップ 2 を実行したところ、`tests/test_check_authz_catalog.py` が red になった。**
TSK-270 の要件主張母集合が**要件書の blob digest を凍結**しているためで、**機構は正しく発火した**
(oracle 先行固定の規律)。

**追随しようとして、連鎖が判明した**(Claude が実測):

| 資産 | 母集合への固定 |
| --- | --- |
| `contracts/authz/route-registry.json` | `requirement-claims.json` + `.lock.json` の blob digest |
| `contracts/authz/auth-catalog.json` | 同(40 桁 digest 179 件) |
| `contracts/authz/http-route-matrix.json` | 同 |
| `contracts/authz/oracle-seal.lock.json` | 同(**`oracle_commit` 上の blob と照合**) |
| **`tests/test_check_authz_catalog.py`** | **`total=1062 auth_claim=184 out_of_scope=878` をハードコード(4 箇所)** |

さらに `_verify_manifest_commit` が **「`commit` フィールドが指すコミットの blob が
`source_blob_digest` と一致すること」**を要求するため、**新しい blob を含むコミットが存在しないと
母集合を更新できない**。`oracle-seal` は同じ制約を **1 段上(`oracle_commit`)**でも課す。

→ **要件書を 1 文字変えると、8 資産 + ハーネステスト + 複数の基準コミットが連鎖する。**

**Claude の見積もりは誤っていた** — 「blob digest と、変わった 1 行の digest、追加された 1 行の分類 —
この 3 点だけ」と人間へ説明したが、実際には上記の連鎖が必要だった。
**Codex は green を無理に作らず、ブロッカーとして正しく報告した。**

### なぜ TSK-270 へ合流させるのが妥当か

- **母集合はどうせ直す必要がある** — マージ後の敵対レビューで **P0 7 件**(分類と `decidable_at` の誤り・
  closed-world 文の落ち・経路レジストリと要件行の結線ほか)+ 下記のインデント表の採取欠陥
- **いま再封印すると、誤った分類を 8 資産へ焼き直す**ことになる
- **あちらは要件書の追随が必須**なので、**例外表の 2 セルもそこで一緒に更新すれば連鎖が 1 回で済む**

### 形式上の残余(隠さず記録する)

**要件書 `NFR-018` の例外表は「有効化待ち」のまま**であり、**形式上は本要件の違反状態が続く**。

**ただし実リスクは解消済み**である — 改善台帳 `I-17` が言う「座標系の二重管理による
**エラーが出ない静かなデータ破壊**」は、**ステップ 1 のテスト(`b89fb03`)で検出可能になった**。
契約 JSON の `size` を変えれば必ず落ちる。

**Notion の DoD から「要件書 NFR-018 の例外表の状態が「有効」になった」を外し、
後続タスクへ移す**(人間の承認として記録する)。

### 発見: インデントされた表行が `paragraph` として採取されている(TSK-270 の射程)

**母集合の採取に欠陥がある。本タスクでは直さない。**

例外表のデータ行は **`table_row` ではなく `NFR-018/paragraph-003`**(段落)として採取されている。
**`NFR-018` 配下 32 件の内訳は heading 1 / list_item 28 / paragraph 3 / `table_row` 0** であり、
**例外表のヘッダ行・区切り行・データ行の 3 行すべてがインデントされているため 3 行とも段落に落ちている**
と考えられる。

→ **TSK-270 の「表行の追加」負例は、インデントされた表を捕捉できない可能性がある。**
**マージ後レビューの P0 7 件に加わる候補**として TSK-270 の修正タスクへ送る。

### 台帳への追記候補(`/pr` のクローズ処理で判断する)

**「oracle の入力凍結が、正本の 1 文字の変更を 8 資産 + ハーネステストの更新へ拡大する」**という型。
**TSK-213 / 214 / 215(要件書 v2.2〜v2.4 改訂)も同じ壁に当たる**ため、単発事象ではない。
`H-81`(変異の有効性)や `H-53`(委任の盲点)とは別の型で、**「oracle の凍結範囲と改訂コストの均衡」**に当たる。
