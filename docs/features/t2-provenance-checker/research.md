# T2 provenance — schema・検査器の最小改訂案と拒否系試験計画(案)

- 作成: 538(Opus 5.5)・2026-10-17。基準 develop `188acf83`
- 依頼: PO 裁定(2026-10-17・master 経由)「T2 provenance は 538/236 の所有側で、schema・検査器の最小改訂案と拒否系試験計画を作成する。既存 T1 検査を保持し、T2 の未記載・不正署名も検出対象にする。正式な資産変更は所定ゲートで判断する」
- **調査と改訂案**(/task-start 前の 2026-10-17 に資産外で作成し、本ディレクトリへ移した)
- コア領域(game-state・sync-protocol)。着地には敵対レビュー + 人間の逐行確認が要る。敵対レビューは PO 裁定(2026-10-17)で Claude サブエージェントによる代替 + Codex の追認

## 0. 分担(545 = 旧ブロッカー☑ と合意 2026-10-17)

| 範囲 | 担当 |
| --- | --- |
| T2 の欄の中身: `subjectKind` の値集合と各値の `sufficientSourceKinds`、`sources` の典拠種別、T2 契約に入れる初期の記録(未実施の形) | **545**(TSK-545 の子カード・10/20 起案予定。置き場 `docs/features/tsk545-game-end-unresolved/t2-provenance-field-draft.md`) |
| schema の器(`$defs`・`required`・`x-pitchlog-provenance-policy` の配置)、検査器、拒否系試験、波及先(読み込み器・digest・署名) | **538** |

## 1. 原典で確認した現状

| 事実 | 典拠 |
| --- | --- |
| T1 schema は `provenance` を必須にし、`$defs.provenance`(5 必須キー + 任意 `independentReview`)と `x-pitchlog-provenance-policy` を持つ | `contracts/state-transition/state_transition_contract_schema_v1.json` |
| T2 schema は `provenance` を持たず、`additionalProperties: false`・必須 8 キー。**欄を置く経路が閉じている** | `contracts/state-transition/game_end_contract_schema_v1.json` |
| 検査器は schema を 1 本(T1)しか読まない | `scripts/check_provenance.py:19-21`・`:66` |
| **検査器は CI の手順に無い**。T1 の検査は pytest(`tests/test_state_transition_contract_schema.py`)経由だけ。実契約の記録は「未実施」(`independentVerifierId: not-performed`・宣誓 3 件が不充足値)で、試験は **検査器がこれを赤にすることを期待している** | 同 `:2443-2491` |
| T1・T2 とも、手動 fixture 単位の由来(`authorId`・`sources` だけ)は既にある。契約単位の独立確認の記録が T2 に無い | `game_end_manual_fixture_schema_v1.json` `$defs.provenance`・`tests/test_game_end_contract_schema.py:205` |
| **両 runner の読み込み器が契約トップレベルのキーを exact-set で固定している**(game-end に provenance なし) | `backend/src/pitchlog/domaincheck/runners/handoff.py:155-184`・`frontend/src/testing/handoffLoader.ts:29-68` |
| 引き渡し契約が T2 契約のファイル digest を持つ(`sha256:87052798…` = 現ファイルと一致) | `contracts/state-transition/appendix_e_consumer_handoff_v1.json:131-133` |
| **PO の逐行確認署名 gate6-game-end が T2 契約全体の RFC8785 digest を持ち、CI(pytest)が現ファイルと照合する** | `docs/features/adr003-stage2-runtime/signatures/gate6-game-end.json`・`scripts/check_human_review_signature.py:1189-1196`・`tests/test_human_review_signature.py:151` |

## 2. 用語: 「未記載」と「不正署名」と「未実施」

いまの検査器は「未実施」と「不正」を区別しない(どちらも `ProvenanceCheckError`)。T2 で「未記載・不正署名を検出」しつつ、P-6 前の正当な状態(未実施)を CI で通すには 3 状態に分ける必要がある。

| 状態 | 定義 | CI |
| --- | --- | --- |
| 未記載 | 契約に `provenance` が無い | **赤**(schema の required) |
| 未実施 | 閉じた形だけを認める: `independentVerifierId == "not-performed"`・`independentReview` なし・宣誓 3 件が未実施の値ちょうど(T1 の現行記録と同じ形)。**そのうえで schema・典拠参照(実在)・`subjectKind`・充足典拠は全件検証する**(免除するのは独立性・宣誓・`independentReview` の検査だけ) | 緑。ただし「P-6 未成立」として列挙する。典拠や種別が不正なら赤 |
| 実施済みの主張 | 上記以外のすべて。**ただし予約値 `not-performed` を含む記録は、閉じた形と完全一致しない限り赤**(検証者 ID・`actorId` に予約値を使った偽装を `verified` にしない) | `validate_provenance` を全項目通す。1 つでも外れたら**赤**(= 不正署名) |

「半分だけ署名した」記録(予約値を検証者 ID に置いたまま宣誓だけ充足値にしたもの、検証者 ID は入っているのに宣誓が未実施の値、`not-performed` なのに `independentReview` がある、など)は「実施済みの主張」側に落ちて赤になる。

## 3. 最小改訂案

### 3-1. schema(`game_end_contract_schema_v1.json`)

1. `properties.provenance = {"$ref": "#/$defs/provenance"}` を足し、`required` に `provenance` を足す
2. `$defs` に、**`$defs.provenance` から `$ref` で到達する閉包**(現状 5 つ: `provenance`・`provenanceSource`・`provenanceAttestation`・`provenanceIndependentReview`・`provenanceReviewEvent`)を足す。**T1 の定義と同一の内容**(複製になる — 4-3 の照合試験 D1 で閉包ごと照合し、ずれを赤にする)。4 つだけ写すと `provenanceIndependentReview.chronology.items` の参照がぶら下がり、実施済みの記録を一度も受理できなくなる(未実施の記録はこの参照を辿らないので CI は沈黙する — 計画レビュー 1 回目の指摘)
3. `x-pitchlog-provenance-policy` を足す。`recordLocation`・`recordField`・`attestationItems`・`assuranceBoundary`・`sourceKinds` は T1 と同じ。`subjectKinds` だけ T2 固有(値は 545 の起案)
4. 版は `v1` のまま改訂する(TSK-538 の裁定 D3 の前例)。T2 契約に provenance を足すのと同じコミットにする(required を足した瞬間に現契約が schema 違反になるため)

**採らない案**: 共通の `provenance_schema_v1.json` へ切り出して両 schema から参照する。重複は消えるが T1 schema を書き換える(T1 不変に反する)。検査器の `$ref` 解決が外部ファイルに対応しているかも未確認。

### 3-2. 検査器(`scripts/check_provenance.py`)

1. `SCHEMA_PATH` 1 本を、**閉じた登録表** `CONTRACTS = {"state-transition": (契約パス, schema パス), "game-end": (...)}` に置き換える。`SCHEMA_PATH` は T1 の値で残す(既存の import 先を壊さない)
2. `validate_provenance(root, provenance, *, schema_value=None, contract_kind="state-transition")`。**既定値が T1 なので、既存の呼び出しは引数も挙動も変わらない**
3. 新関数 `classify_provenance(...) -> Literal["not-performed", "verified"]`: 2 節の 3 状態を判定する。まず schema・典拠参照・`subjectKind`・充足典拠を全件検証する。そのうえで、予約値 `not-performed` を含むなら閉じた形と完全一致を要求して `not-performed`(不一致は例外)、含まなければ `validate_provenance` の残り(独立性・宣誓・`independentReview`)を通して `verified` か例外
4. 新関数 `check_repository(root)`: 登録表のすべての契約について、`provenance` の存在 → `classify_provenance` を行い、状態の一覧を返す
5. `main()`: 契約パスを登録表に照らして種別を決める。**登録表に無いパスは赤**(種別の取り違えと未登録の契約を通さない)。`--repository` で 4 を実行
6. 登録表の閉包: 登録表の契約の集合 == `contract_size_limit_v1.json` の `contractPaths`(既存の契約一覧)を試験で固定する。**これで、将来の契約で provenance の登録漏れが出たら赤になる**。検査器が自分の射程外の契約を黙って通す(台帳候補 8「検査器が自分の射程外を沈黙で通す」)ことへの機構的な手当てになる。今回の T2 の欠落はまさにこの形で、T1 しか知らない検査器が T2 の不在を報告しなかった。閉包の基準を `contract_size_limit_v1.json` にするのは、それが契約の一覧を宣言している既存の資産で、新しい一覧を作らずに済むから。この一覧に載らない契約が作られる穴は残る(サイズ上限の検査側の射程)

   **この案で塞がる範囲と塞がらない範囲**:

   | 塞がる | 塞がらない |
   | --- | --- |
   | `contract_size_limit_v1.json` の `contractPaths` に載っている契約で、provenance が無い・検査器の登録表に無い | `contractPaths` に載っていない契約(一覧への登録漏れそのもの)。これはサイズ上限の検査器の射程で、本案では手当てしない |
   | 登録表に無いパスを `main()` に渡す(種別の取り違え) | 契約の形をしていない資産(手動 fixture・カバレッジ宣言など)の由来。fixture 単位の由来は既存の schema が持つが、独立確認の記録は持たない |

**CI への配線は ci.yml を変えず pytest 経由にする**(ci.yml の変更は凍結 corpus の受理記録を伴う — TSK-538 ステップ 16 の前例)。

### 3-3. 同じ変更で直す波及先(直さないと CI が赤)

| 波及先 | 変更 |
| --- | --- |
| `contracts/state-transition/game_end_contract_v1.json` | トップレベルに `provenance`(未実施の形)を足す。中身は 545 の起案 |
| `backend/src/pitchlog/domaincheck/runners/handoff.py`(`CONTRACT_KEYS["game-end"]`) | `provenance` を足す |
| `frontend/src/testing/handoffLoader.ts`(game-end の `contractKeys`) | 同上 |
| `tests/test_game_end_contract_schema.py` | `required` の 8 キー固定(`:455-464`)と最小契約 `_minimal_contract`(`:382-398`)を追随(計画レビュー 1 回目の指摘)。T2 provenance の試験の置き場もここにする(4 節) |
| `tests/domain/runners/test_handoff_loader.py`・`frontend/src/testing/handoffLoader.spec.ts` | 変異適用器に `remove` 操作を足す(現行は directCases・replace・add・unsafeInteger・duplicateField・negativeZero だけで、L1 を表せない) |
| `tests/domain/runners/fixtures/handoff-loader/mutations.json` | 必要なら追随(要確認) |
| `appendix_e_consumer_handoff_v1.json:133` | T2 契約の digest を更新 |
| **`signatures/gate6-game-end.json`** | **digest が変わるので PO の再署名が要る**(PO の明示の再署名が無いまま書き換えると署名の偽造になる。再署名を受けた転記は Claude が行う — 前例 `22cf696f`・計画書 4 節)。確認の補助として「旧版と新版の差がトップレベルの `provenance` キーだけ」を機械で示す |

### 3-4. 波及の実測(2026-10-17・`188acf83`)

- **T2 契約の digest を固定している所は 2 つだけ**: 引き渡し契約の `artifacts[].digest`(生 SHA-256 `87052798…`)と gate6-game-end の署名(RFC8785 `3514e1c6…`)。全リポジトリを両方の値で検索して確認した
- **T2 schema の digest はどこにも固定されていない**(生 SHA-256・RFC8785 の両方で検索)。入力軸 descriptor は T2 契約を `sourcePath` で参照するだけで digest を持たない(`input_axes_descriptor_v1.json:1444`・`:2481`)。したがって descriptor の digest(両読み込み器が `DESCRIPTOR_DIGEST` で固定)へは連鎖しない
- 読み込み器は、トップレベルのキー集合を exact-set で照合する(`handoff.py:444` → `CONTRACT_KEYS`・`handoffLoader.ts:467` → `contractKeys`)。直す箇所は各 1 行
- 凍結の基準線(`check_frozen_baselines.py`)と三点突合(`check_input_axes_three_way_parity.py`)は T2 契約を見ていない
- 読み込み器の変異 fixture(`tests/domain/runners/fixtures/handoff-loader/mutations.json`、16 件)に、**契約トップレベルの未知キーと欠落キーの変異が無い**(未知キーの変異は case 単位と handoff 単位だけ)。4-5 で足す

### 3-5. 再署名の範囲を限る機械的な差分(gate6-game-end)

**依拠する規範**: ハーネス設計書 v1.20 の 6.5 類型 ②(規則が、性質を損なわない変更まで止める)。**6.5 は PR #142 で新設し、まだマージされていない**。正本になる順序は #138 → #142。6.5 の手段の序列((a) 前進の別 PR / (b) 規則改訂 / (c) 保護設定の一時解除 / (d) PO の期限付き裁定)のどれにも当たらず、**人間の行為(署名)のやり直しになる**。署名の digest から provenance を除く (b) は署名検査器(コア)の改訂で、最小ではない。

**示すこと**: PO が逐行確認した文書(署名の `subject.digest`)に、`/provenance` 1 キーを足しただけであること。

**方法**(`~/.cache/pitchlog-538/t2-provenance/provenance_only_diff.py`(資産外) — 資産の外の試作。digest の計算は署名検査器の `compute_subject_digest` を呼ぶので、計算規則は署名照合と同一):

| 判定 | 内容 |
| --- | --- |
| D1 | 新契約のトップレベルに `provenance` がある |
| D2 | **新契約から `/provenance` を除いた文書の RFC8785 digest が、署名記録の `subject.digest` と一致する** |
| D3 | 新契約そのものの digest は署名記録と一致しない(再署名が要ることの確認) |
| D4 | 旧契約(develop の現物)の digest も署名記録と一致する(旧契約が署名対象そのものであることの裏取り) |

**写しでの実演**(実契約には触れていない):

| 入力 | D2 | 判定 |
| --- | --- | --- |
| 現契約 + `provenance`(未実施の形) | 一致 `3514e1c6…` | 成立 |
| 同上を整形だけ変えたもの(キー順・改行) | 一致(RFC8785 が吸収) | 成立 |
| 同上 + 規範行 1 つの `lockFurtherPlayInput` を反転 | 不一致 `37217457…` | **不成立**(rc=1) |

**再署名で PO に出すもの**: D1〜D4 の出力、新しい digest、`reviewScope` に「provenance の追加だけ。規範行 8 行と派生 case 248 件は 2026-10-15 の確認から不変(D2 で機械照合)」と追記する案。**TSK-545 が同じ PR で規範行や case を変えると D2 が不成立になる** — その場合は再署名の範囲が行の確認まで広がる(差分の出し方は別に要る)。

**資産に入れるか**: 入れない(計画書 4 節で確定)。`scripts/` に置くとコア領域の参照検出と登録が要る。資産外の試作を、リポジトリのルートを引数で受け(現状は本体のチェックアウトに固定)、`safeIntegerLimit` を署名 schema の policy から読む(現状は直書き)形に直して使い、出力を worklog と PR 本文に貼る。

## 4. 拒否系試験計画(NFR-019 の単体・故障系)

置き場: 既存の `tests/test_game_end_contract_schema.py`(両コア領域に登録済み。**新しい試験ファイルはコア領域の参照検出で赤になる**ため作らない — 計画書 4 節)。T1 の試験ファイルは**1 バイトも変えない**(T1 不変の判定基準)。T2 の合成 schema と合成契約は `schema_value` で差し替える。

### 4-1. 未記載(④)

| # | 負例 | 期待 |
| --- | --- | --- |
| N1 | T2 契約から `provenance` を削除 | schema 検査で赤「必須キー不足: provenance」 |
| N2 | `provenance` を `null`・配列・空 object | 赤 |
| N3 | `provenance` の必須 5 キーのいずれか 1 つを削除(5 通り) | 赤 |
| N4 | `provenance` に未知キーを追加 | 赤(`additionalProperties: false`) |
| N5 | 登録表から game-end を外した検査器で `--repository` を実行 | 赤(登録表の閉包試験) |
| N6 | 登録表に無いパスの契約を `main()` に渡す | 赤(未登録の種別) |

### 4-2. 不正署名(④)

| # | 負例 | 期待 |
| --- | --- | --- |
| S1 | `authorId == independentVerifierId` | 赤「作成者と独立確認者が記録上同一」 |
| S2 | 検証者 ID は実名、宣誓は未実施の値のまま(半署名) | 赤「宣誓応答が充足値でない」 |
| S3 | `not-performed` なのに `independentReview` がある | 赤(未実施の閉じた形に一致せず、全検証で失敗) |
| S4 | 宣誓の欠落・重複・未知の ID(3 通り) | 赤 |
| S5 | 実施済みの主張で `independentReview` が無い | 赤 |
| S6 | `chronology` の順序が 1 始まりの連番でない / 検証者が `actorId` に現れない(2 通り) | 赤 |
| S7 | `authorWorkExposure` と宣誓 `author-work-exposure` の不一致 | 赤 |
| S8 | 未知の `sourceKind` / 実在しない `req:` ID / 旧調査資料だけの典拠(3 通り) | 赤 |
| S9 | `subjectKind` が T2 の policy に無い / T1 の `subjectKind` を T2 に流用 | 赤(種別の取り違え) |
| S10 | T2 の policy で `sufficientSourceKinds` を満たさない典拠だけ | 赤 |
| S8'〜S10' | S8〜S10 を**未実施の記録の上で**(宣誓・検証者は未実施の閉じた形のまま) | 赤(未実施でも典拠と種別は検証する) |
| S11 | 予約値の偽装: `independentVerifierId: "not-performed"`・宣誓 3 件が充足値・`chronology` の `actorId` に `not-performed`・exposure は整合 | 赤(予約値は閉じた形と完全一致する場合だけ) |

### 4-3. 器のずれ

| # | 負例 | 期待 |
| --- | --- | --- |
| D1 | T2 schema の `$defs.provenance` から `$ref` で到達する閉包(現状 5 つ)のいずれかを T1 とずらす / 閉包の 1 つを欠く | 赤(閉包を計算して T1 と完全一致を照合) |
| D2 | T2 policy の `subjectKinds` 以外のキーを T1 とずらす | 赤 |
| D3 | T2 の `x-pitchlog-provenance-policy` を削除 / `required` から provenance を外す | 赤(`_policy` の既存検査) |

### 4-4. 正例(T1 の保持と T2 の受理)

| # | 正例 | 期待 |
| --- | --- | --- |
| P1 | T1 の既存試験(`tests/test_state_transition_contract_schema.py`)を無変更で実行 | 全件緑 |
| P2 | `validate_provenance` を `contract_kind` 省略で呼ぶ | T1 の schema で検証される(固定の期待結果: T1 の合成の実施済み記録は通り、T1 の実契約の記録は「宣誓応答が充足値でない」で落ちる — 既存の T1 試験と同じ期待) |
| P3 | リポジトリの T1・T2 契約で `--repository` | 両方 `not-performed` として列挙、終了コード 0 |
| P4 | 全項目を満たす合成の T2 署名 | `verified` |
| P5 | 読み込み器(Python・TS)が provenance つきの T2 契約を読む | 緑。キー集合の exact-set は維持(provenance 以外の未知キーは引き続き赤) |
| P6 | gate6-game-end の再署名後、署名照合 | 緑 |

### 4-5. 読み込み器(Python・TS の両方で同じ結果)

`mutations.json` へ足す変異(どちらの runner でも同じ code で拒否されることを、既存の対の試験で確かめる):

| # | 変異 | 期待 code |
| --- | --- | --- |
| L1 | T2 契約のトップレベルから `provenance` を削除(新設の `remove` 操作) | `UNKNOWN_FIELD`(`handoff.py:224-229` の `_keys` が欠落も同じ code で拒否する) |
| L2 | T2 契約のトップレベルに未知キーを追加 | `UNKNOWN_FIELD` |
| L3 | T1 契約のトップレベルに未知キーを追加(T1 側にも欠けていた変異) | `UNKNOWN_FIELD` |

L1 の code は計画レビュー 1 回目で確認した(`UNKNOWN_FIELD`)。

### 4-6. 変異で確かめること(試験が効いていることの確認)

`classify_provenance` の未実施判定から 1 条件ずつ外す変異(3 通り)、未実施の記録の典拠検証を飛ばす変異、予約値の完全一致を外す変異、登録表から game-end を外す変異が、上の負例のどれかで落ちること(計画書のステップ 1 の合格条件)。

## 5. 実装の分け方

計画書 [plan.md](plan.md) の 4 節(実装ステップ 1〜4 と人間ゲート)が正。本節の旧表は計画レビュー 1 回目の反映で plan.md へ一本化した。

## 6. 未決(判断が要るもの)

1. **gate6-game-end の再署名を PO が受けるか**。受けない場合の代替は「署名の digest から provenance を除く射影」だが、署名検査器(コア)の改訂になり最小ではない
   - 再署名は 2 回になる見込み: ① 本案の着地時(provenance の追加だけ。D2 で範囲を機械で限れる形式的な再署名)② 545 の契約整備((e)・G6-E の PO 裁定 9 件待ちで日付未定)の着地時(規範行・case の中身が変わる実質的な逐行確認)
   - **② では digest だけでなく `reviewScope` の本文も書き換えが要る**。いまの本文は「条文が決めていない点(G6-E01〜E14)は確認の範囲外で、TSK-545 へ送った」で、(e) の着地でこの文が事実と合わなくなる。①では本文は変わらない(545 の指摘)
2. **タスクの器 — D2(再署名の範囲を限る機械的な差分)の成否と連動する**: provenance の追加を規範行・case の変更と同じ PR に載せると D2 が不成立になり、再署名の範囲を限れない。**別タスク(provenance だけの PR)なら D2 が成立し、再署名を「provenance の追加」に限れる**。545 の契約整備の子カード(下記)の一部にすると、(e) と同居して D2 が崩れるうえ、(e) の裁定待ちに provenance が止められる(P-6 の署名の置き場が開かない)。538・545・master とも**別タスクを推奨**
   - 545 側の器: TSK-545 本体(T2 終了判定の対象計算・ブロック中)ではなく、新設の子カード https://app.notion.com/p/3fc93b75e6878190ba92eb1cc4abdd61(`feature/tsk545-game-end-unresolved`)。本書で「TSK-545 (d)」と書いた所はこの子カードを指す
3. **L1〜L3(読み込み器の変異 fixture の穴)を今回の射程に入れるか**: 入れると `mutations.json` と両 runner の対の試験が増え、ステップ 2 が重くなる(着地が後ろへ動く)。入れない場合は L1(T2 の provenance 欠落)だけを本案に残し、L2・L3(トップレベル未知キー — 本案と独立に以前からある穴)は別タスクへ送る、という分け方もできる
4. T2 の `subjectKinds` の値と、初期記録の `sources`(545 の起案 — 10/20)。545 の実測では、現行 8 行の典拠は `req:` 4 件(F-1・FR-005・FR-009・FR-020)だけで、新しい典拠種別は要らない見込み(= `sourceKinds` は T1 と完全一致のまま)。**`subjectKinds` は 1 種で 545 と合意した(2026-10-17)**。判定基準は「`sufficientSourceKinds` が違うときだけ別の種別を宣言する」で、T1 の形から取った。T1 の `vocabulary-origin` は実記録が名乗っていないが、`legacy-vocab-mirror` 単独を許す点で `sufficientSourceKinds` が実際に違い、試験がその差を固定している(`tests/test_state_transition_contract_schema.py:2863-2870`)。T2 の分岐(5 欄)と表示値 `xMark` はどちらも `[requirements, official-baseball-rules]` に落ちて差が無いので、1 種でよい。2 種目が要るのは、XMARK が requirements 以外の典拠種別を必要とするようになったとき。policy への加法的な追加なので、後からでも安く済む
5. 着地の主体: PO 裁定(2026-10-17)で Claude の実装・レビューで代替 + 追認。Codex の利用枠は 10/22 17:45 まで停止(562 の報告)で、追認は 10/22 以降
