---
date: 2026-10-17
topic: T2 終了判定契約の由来記録(provenance)の器と検査器
branch: feature/t2-provenance-checker
---

# 作業ログ: 2026-10-17 T2 終了判定契約の由来記録(provenance)の器と検査器

## やったこと

- /task-start(山田正輝の起動)。Notion https://app.notion.com/p/3fc93b75e687812d83bdd45890f4844a ・worktree `../pitchlog-worktrees/feature-t2-provenance-checker`(develop `188acf83` 起点)
- /task-start 前に資産外(`~/.cache/pitchlog-538/t2-provenance/`)で作った改訂案と計画書の下書きを、`docs/features/t2-provenance-checker/research.md`・`plan.md` へ移した。D2 の試作(`provenance_only_diff.py`)と実演の写しは資産外に残す

## 決定

- PO 裁定(2026-10-17・master 経由): T2 provenance は 538/236 の所有側で、schema・検査器の最小改訂案と拒否系試験計画を作成する。既存 T1 検査を保持し、T2 の未記載・不正署名も検出対象にする。正式な資産変更は所定ゲートで判断する
- PO 裁定(同日・master 経由): 本タスクは「Claude の実装・レビューで代替 + 追認」の対象。**敵対レビューと review normal は、実装に関与していない Claude サブエージェントで代替する(Codex 敵対レビューの代替)**。PO の逐行確認と gate6-game-end の再署名は代替しない。計画レビューも代替の射程に入る、と master が読んだ(PO へ確認中 — 違っていれば追認の対象が増える)
- **追認が残る**: 代替でレビューした版を Codex で 1 回追認する。期限は master 提案で 10/28(確定は PO)。追認が済むまで Notion を「完了」にしない
- 分担(545 と合意): 欄の中身(subjectKinds 1 種・初期の sources)は 545 の TSK-545 子カード(10/20 起案)、器・検査器・試験・波及先は本タスク
- 別タスク・別 PR にする(538・545・master が一致): provenance を規範行・case の変更と同居させると D2 が崩れ、再署名の範囲を限れないため。再署名は 2 回になる(本タスクの形式的な再署名と、545 の (e) の実質的な逐行確認)

## 未決・次の一歩

- PO 判断: ① gate6-game-end の再署名を受けるか ③ L1〜L3 を射程に入れるか / 計画レビューの代替の確認
- 次: /plan(計画レビューを Claude サブエージェントで代替実施 → PO の計画承認)

## 計画レビュー 1 回目(全文)— Codex 敵対レビューの代替として Claude で実施

- 主体: 起案・実装に関与していない Claude サブエージェント(general-purpose・Opus 5.5)。依頼文は Codex 向けと同じ形(受理範囲 3 種・6.1 の重大度・名指しの軸 A〜H・判定行)— `~/.cache/pitchlog-538/t2-provenance/plan-review-r1-prompt.md`
- 判定: **否決 P0=2 P1=5 P2=3**。10 件とも 538 が原典で確認し、**全件採用**(`計画レビュー周回` 0 → 1)

| # | 重大度 | 要旨 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | P0 | 既存の T2 schema 試験が `required` を 8 キーで固定(`tests/test_game_end_contract_schema.py:455-464`)・最小契約が provenance を持たない(`:382-398`)。更新対象に無くステップ 2 が緑にならない | 採用。3 節とステップ 2 に追加 |
| 2 | P0 | 新しい試験ファイルはコア領域の参照検出(`tests/test_core_guard.py:1127-1180`・`:2973-3007`)で赤。登録には二層契約とゲートが要る | 採用。新ファイルを作らず、両領域に登録済みの `tests/test_game_end_contract_schema.py` に置く。4 節の重さ分類の根拠を直した |
| 3 | P1 | 写す `$defs` は 4 つでなく閉包 5 つ(`provenanceReviewEvent`)。4 つだと実施済みの記録を受理できず、未実施は参照を辿らないので沈黙 | 採用。閉包で定義し、D1 を閉包の照合に |
| 4 | P1 | 未実施の閉じた形に一致すると典拠・種別の検証が丸ごと飛ぶ(新しい沈黙の穴) | 採用。未実施でも schema・典拠・`subjectKind`・充足典拠は全件検証。S8'〜S10' を追加 |
| 5 | P1 | 予約値 `not-performed` を検証者・actorId に置いた偽装が verified で通る | 採用。予約値は閉じた形と完全一致の場合だけ。S11 を追加 |
| 6 | P1 | L1 の削除操作が両 runner の変異適用器に無い。code は `UNKNOWN_FIELD` に決まる | 採用。両試験ファイルに `remove` を足す。期待 code を確定 |
| 7 | P1 | 再署名の記入とコミットの主体が無い。前例 `22cf696f` では Claude が転記している | 採用。ステップ 4(PO の明示の再署名を受けた転記)を新設し、転記の条件(artifactAuthorId・reviewer・シート SHA・reviewScope 追記)を 4 節に。「Claude が書き換えると偽造」は言い過ぎで、「明示の再署名が無いまま書き換えると偽造」に直した |
| 8 | P2 | D1〜D4 の道具の置き場が未定・ROOT 固定・上限値の直書き | 採用。資産化しない(出力を貼る)と確定。ルートは引数・上限値は policy から読む形に直して使う |
| 9 | P2 | P4・4-6 がステップの合格条件に無い。P2 の前後比較は試験にならない | 採用。ステップ 1 に割り当て、P2 を固定の期待結果に |
| 10 | P2 | `handoff.py:150-185` の範囲ずれ・「③」の多義 | 採用。`:155-184` に直し、③ を名前に置き換えた |

- 軸の結果(サブエージェントの報告): B(T1 不変)・C(NFR-018)・D(NFR-023・シークレット・テナント)・H(545 への依存)は該当なし。CI 配線は harness が `pytest tests/` を流し、harness は必須チェック(`.github/workflows/ci.yml:97-102`・`docs/development/github-setup.md:125`)
- 次: 2 回目(反映差分 + 影響節)を、1 回目と別の未関与のサブエージェントで

## 計画レビュー 2 回目(反映差分 + 影響節)— Codex 敵対レビューの代替として Claude で実施

- 主体: 起案・実装・1 回目に関与していない別の Claude サブエージェント。依頼文 `~/.cache/pitchlog-538/t2-provenance/plan-review-r2-prompt.md`(終結済み一覧つき・前周指摘の全文は並記しない)
- 判定: **可決 P0=0 P1=2 P2=4**。1 回目の 10 件は 9 件解消・1 件一部未解消(→ 下の 3・4)。6 件とも 538 が原典で確認し、**全件採用**(`計画レビュー周回` 1 → 2)。基本枠 2 回を使い切り、P0 が無いので P0 例外の 3 回目は無い。**最終反映(本節の 6 件)は再レビューを受けていない** — 承認者は差分を確認する(6.3 (4))

| # | 重大度 | 要旨 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | P1 | 予約値 `not-performed` の判定キーが未定義で、検証者 ID だけを見る実装でも S11 が通る | 採用。判定キーを 4 か所に閉じて列挙(authorId・independentVerifierId・attestations[].response・chronology[].actorId)、完全一致・宣誓は集合一致と明記。S11a〜S11c(単独キー)をステップ 1 の合格条件に |
| 2 | P1 | ステップ 4 の「CI 全緑」は人間の逐行確認(core-guard の必須チェック)を待たないと満たせない | 採用。ステップ 4 は「core-guard 以外の必須チェックが緑」、全緑は逐行確認の後と書き分けた |
| 3 | P2 | `handoff.py:155-184` がまだ 1 行ずれ(正しくは `:156-184`) | 採用 |
| 4 | P2 | 丸数字 ④ の多義 | 採用。名前に置き換えた |
| 5 | P2 | DoD の代替レビュー・追認にステップもゲートも無い | 採用。DoD に「ステップ外」の付記、人間ゲートに PR 段階の代替レビューと追認ゲートを追加 |
| 6 | P2 | S8'〜S10' がステップ 1 の合格条件に明記されていない | 採用。合格条件とテスト計画に明記 |

- 観察(受理範囲外・指摘に数えない): 読み込み器は game-state・data-migration の登録で sync-protocol ではない → 4 節の重さ分類の根拠の書き方を直した(結果は変わらない)
- 次: PO の計画承認(採否一覧と最終反映の差分を添える)。計画レビューの代替は追認の対象(Codex・10/22 以降)

## 計画承認

- **PO 承認(2026-10-17・山田正輝)**。HEAD `94075794` の計画(計画レビュー 2 回・全件採用・不採用なし)を、最終反映の差分(2 回目の 6 件 — 再レビューなし)の提示のうえで承認
- 計画レビューは Codex 敵対レビューの代替として Claude で実施した。**Codex の追認が残る**(期限 10/28 案)
- 次: ステップ 1(検査器の拡張 — Claude が実装。review normal は未関与の Claude サブエージェントで代替)

## ステップ 1(検査器の拡張)— `5024721b`・是正 `a0ce576c`

- 実装: Claude(538)。PO 裁定による
- 確認(538): T1 の試験ファイルは無変更のまま 282 件 passed / T2 の試験(`tests/test_game_end_contract_schema.py`)は是正後 92 件 passed / harness 全件 29,671 passed・失敗 3(新しい worktree で `backend/.venv` が無い既知の原因。`uv sync` 後に 3 件 passed)/ ruff・ty 緑
- 変異確認(資産外 `~/.cache/pitchlog-538/t2-provenance/mutate_step1.py`): 初回は pytest のオプション(`-p no:xdist`)が設定とぶつかり、全変異が**起動エラー**で落ちていた — 「殺した」は無効。変異なしの基準実行が緑であることを先に確かめ、試験の失敗(rc=1・failed)だけを数える形に直して再実施。M9 は置換の誤りで別の理由で落ちていたので直して再実施。**最終: 12 種すべて試験の失敗で落ちた(生存 0)**
- 545 の起案(`t2-provenance-field-draft.md` — 承認前の素案)を受領。T2 契約の `req:` は重複を除いて 21 件で起案の列挙と一致し、全件が要件書の条項 ID として実在(538 が照合)。`subjectKind` は既存の `normative-branch-or-state-effect` を再利用(policy は T1 と完全一致)、`adr:D-11` は `sources` に含めない(案 1)— research.md 6 節の 6・7

### コード差分レビュー — Codex `review normal` の代替として Claude で実施

- 主体: 実装・計画レビューに関与していない Claude サブエージェント。依頼文 `~/.cache/pitchlog-538/t2-provenance/step1-review-prompt.md`(6.3 のコア領域 PR の重大度・名指しの軸 A〜F)
- 判定: **可決 P0=0 P1=2 P2=3**。検査器が不正を緑にする経路は無し(軸 A 該当なし)。T1 の挙動は不変(軸 B)。全件採用 → `a0ce576c` と本ドキュメント修正

| # | 重大度 | 要旨 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | P1 | 未実施の閉じた形の 2 条件(宣誓の重複・宣誓項目の宣言との照合)に試験が無く、外しても緑 | 採用。S4'・S12 を追加 |
| 2 | P1 | `main()` から検証へ契約種別を渡す処理と、引数の排他に試験が無い | 採用。N7(呼び出しの種別を照合)・N8(終了コード 2)を追加 |
| 3 | P2 | `check_repository` の閉包検査の呼び出しに試験が無い | 採用。登録表を差し替えて拒否する試験を追加。**538 が追加で発見**: `check_registry_closure` の既定引数が定義時の登録表に固定され、差し替えが効かない — 呼び出し時点で解決する形に直した |
| 4 | P2 | S2 の期待メッセージ・「判定キー 4 か所の各単独」・S9' の記述が実装と食い違う | 採用。research.md と plan.md を実装に合わせた。検証者 ID 単独の偽装は actorId の照合で必ず赤になる(等価)ので単独の負例は置かない |
| 5 | P2 | 期待メッセージの `match` が部分文字列で、別の理由に滑っても緑のまま | 採用。文言全体で照合 |

- 次: ステップ 2(T2 の器の着地 — 545 の起案を入力に)

## ステップ 2(T2 の器の着地)— `fd42e240`・是正 `0e9f32ff`

- 実装: Claude(538)。PO 裁定による。入力は 545 の起案(承認前の素案 — 中身が変われば追随する)
- schema: T1 の `$defs` の閉包 5 つと policy を文字列のまま写し(書式を崩さないため)、閉包と policy が T1 と完全一致することを機械で確認
- 確認(538): T2 の試験 + T1 の試験 394 passed / 読み込み器の試験 Python 106 passed・TS 18 passed(L1 は両方 `UNKNOWN_FIELD`)/ backend の契約を読む試験 154 passed(DB 必須分は CI)/ frontend の prettier・eslint・vue-tsc 緑 / harness 全件 29,698 passed・**失敗は gate6 の署名照合 1 件だけ(予定どおり — ステップ 4 で閉じる)** / `check_provenance.py --repository` は両契約 not-performed / 変異 12 種すべて試験の失敗で落ちた

### コード差分レビュー — Codex `review normal` の代替として Claude で実施

- 主体: 実装とこれまでのレビューに関与していない Claude サブエージェント。依頼文 `~/.cache/pitchlog-538/t2-provenance/step2-review-prompt.md`
- 判定: **可決 P0=0 P1=1 P2=2**。契約の規範行・case・validationErrors はバイト単位で不変(provenance の行を除くと旧ファイルと一致)・T1 不変・両 runner の一致・他の検査は緑(軸 B〜G)。全件採用 → `0e9f32ff` と research.md 6 節の 6

| # | 重大度 | 要旨 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | P1 | 実資産の記録の照合が `req:` だけを抽出して網羅を主張(545 と同じ型の誤り)。`obr:` や別の `adr:` が増えても沈黙 | 採用。母集団を接頭辞を問わない構造化引用のすべてにし、除外集合 `{adr:D-11}` と接頭辞→典拠種別の対応を固定。req: 以外が増えたら記録漏れとして現れる試験を追加 |
| 2 | P2 | 閉包の計算が `"$ref": "#/$defs/…"` の文字列形しか拾わず、別の形の参照で閉包の外のずれを見逃す | 採用。辞書の再帰走査にし、`#/$defs/<名前>` 以外の参照があれば照合を失敗させる。負例を追加 |
| 3 | P2 | 地の文の `XMARK-01`・`XMARK-02` が記録に無い(`COLD-08/09` は入っている) | 採用(記述)。母集団は構造化引用だけと research.md に明記。地の文の言及は母集団外 |

## ステップ 3(再署名の材料)

**PO に確認していただくもの**(gate6-game-end の再署名 — ステップ 4 の前提)

1. **差が `/provenance` の追加だけであることの機械出力**(資産外の道具 `~/.cache/pitchlog-538/t2-provenance/provenance_only_diff.py --root <worktree> --base origin/develop`。digest は署名検査器の `compute_subject_digest`、上限値は署名 schema の policy から読む):

```
対象: contracts/state-transition/game_end_contract_v1.json(新 = worktree の作業ツリー / 旧 = origin/develop)
署名記録: sha256:3514e1c6225f3a4da4ebf960d918388508a2d1c72ce02ddb4df0af0de0f77863(safeIntegerLimit=9007199254740991)
D1 新契約に /provenance がある: True
D2 /provenance を除いた digest == 署名記録: True (sha256:3514e1c6225f3a4da4ebf960d918388508a2d1c72ce02ddb4df0af0de0f77863)
D3 新契約そのものの digest != 署名記録(再署名が要る): True (sha256:e93f30f75b97f580d3ee0984ff4300bb7a35544a4568a0fedfabf32da81e1ec4)
D4 旧契約の digest == 署名記録: True (sha256:3514e1c6225f3a4da4ebf960d918388508a2d1c72ce02ddb4df0af0de0f77863)
判定: 差は /provenance の追加だけ
```

   写しでの実演(research.md 3-5): 整形だけ変えた写しは成立、規範行 1 つの `lockFurtherPlayInput` を反転した写しは不成立
2. **追加した `/provenance` の中身**(契約の 10〜114 行): 対象種別 `normative-branch-or-state-effect`・要件書の典拠 21 件(契約の構造化引用のうち `adr:D-11` を除くすべて)・作成者 `codex`・独立確認者 `not-performed`・宣誓 3 件が未実施の値・`independentReview` なし
3. **署名記録の更新案**(ステップ 4 で Claude が転記する。`artifactAuthorId`・`recordedReviewerId`・`recordedMethod`・`attestations`・逐行確認シートの名前と SHA-256 は変えない):
   - `subject.digest`: `sha256:e93f30f75b97f580d3ee0984ff4300bb7a35544a4568a0fedfabf32da81e1ec4`
   - `recordedOn`: 再署名の日
   - `reviewScope` の末尾に追記: 「<再署名の日> 再署名: T2 provenance のタスク(Notion https://app.notion.com/p/3fc93b75e687812d83bdd45890f4844a)で、契約のトップレベルに provenance(未実施の閉じた形・要件書の典拠 21 件)を加えた。provenance の中身の起案は TSK-545 の子カード、器と記入は Claude(538)。規範行 8 行・派生 case 248 件・validationErrors は 2026-10-15 の確認から不変で、provenance を除いた RFC8785 digest が旧署名の digest(sha256:3514e1c6…)と一致することを機械で照合した。記録上の確認者は差分と照合の出力を確認して再署名した。provenance が記す典拠による主張の支持(独立確認)は本署名の範囲外で、P-6 の独立検証に送る」

**PO に決めていただくこと**
- 再署名を受けるか(上の 1〜3 を確認のうえ)。受ける場合、`reviewScope` の追記文の可否・修正
- L1〜L3 の射程(現状は計画の初期値どおり L1 だけ。L2・L3 を入れる場合はステップを足す)
