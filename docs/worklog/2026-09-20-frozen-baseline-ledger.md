---
date: 2026-09-20
topic: 凍結基準を検査器から台帳へ移す(TSK-421)
branch: feature/frozen-baseline-ledger
---

# 作業ログ: 2026-09-20 凍結基準を検査器から台帳へ移す(TSK-421)

## やったこと

- **着手**(/task-start)。`origin/develop` = `5e9ffd9` 起点で worktree を作成。TSK-421 は着手可・担当者とプロジェクトが揃っていたため起票せず、進行中への遷移とコメント記録のみ
- **計画段階の調査**(/investigate)。サブエージェント 3 本を並列委任し、[research.md](../features/frozen-baseline-ledger/research.md) へ統合。**要件書 1 文字変更の連鎖を実験用クローンで green まで再現**した
- **計画書の起草**と**敵対レビュー**(コア領域 = sol xhigh)

## 決定

### 射程(PO 裁定 2026-09-20)

| 判断 | 内容 |
| --- | --- |
| **`H-85` の 2 段コミット解消は含めない** | 強制元は `input_manifest.commit` と `oracle_commit` という資産側ポインタで、本タスクの 5 件に含まれない。消すには「同一コミットで入力と seal を同時に書き換える」抑制を別機構で作る必要があり、認可オラクルの再設計になる |
| **走査は 5 件目まで含める** | `scripts/check_docs_status.py:61-63` の 64 桁 digest。コメント自身が「履歴を残さず正本を書き換える経路が復活する」と書いており性格は凍結基準そのもの |
| **`ci.yml` の action pin 19 件は含めない** | 性質が違う(供給鎖の固定) |

**裁定から従う帰結**(改めて伺いを立てていない): 前任の台帳が持っていた **`corpus_versions` 系列と digest 辺の削減も射程外**。これは連鎖の短縮 = `H-85` の射程であるため。

### 台帳の置き場 — `contracts/authz/frozen-baselines.json`

2 つの設計案が矛盾したため原典で裁定した。

| 論点 | 実測 |
| --- | --- |
| 差分閉包が `contracts/authz` を 3 パスに限る件 | `scripts/check_authz_catalog.py:4046-4062` で **early-return する**(`claim-mutant-map.json` の `TSK-270-GROUP-2` が 0 件)→ 新設は既存検査を壊さない |
| core-guard の照合 | `scripts/core_guard.py:224-226` は **`guard_paths` 完全一致 `OR` 領域 glob 一致** |
| `contracts/authz/frozen-baselines.json` | 領域 glob `contracts/authz/*` で**既に一致** → `guard_paths` 登録は不要 |
| `contracts/` 直下案 | **どの glob にも一致せず保護を失う**。採らない |
| 新設の検査器・リーダ・shim・allow-list・負例 | **どれにも一致しない** → `guard_paths` 登録が要るのはこちら |

### 系列の分離

**値が同じ `56c281c4…` を持つのは `core_areas_guard` と `authz_step2_base`**(`oracle_meaning` は `099a8fa2…`)。当初 `core_areas_guard` 対 `oracle_meaning` で分離を論じていたが**比較相手の取り違え**で、1 周目のレビューで訂正した。

## 調査サブエージェント間の矛盾と裁定

| 論点 | 案 A | 案 B | 裁定(実測) |
| --- | --- | --- | --- |
| 台帳の置き場 | `contracts/` 直下 | `contracts/authz/` のまま | **B**(上記) |
| `guard_paths` | 台帳を登録 | 台帳は不要・検査器を登録 | **B** |
| 系列の分離 | `oracle_meaning` と `authz_step2_base` は別系列 | 1 系列に統合 | **A**(値が違う — 実測) |

## 計画レビューの採否記録

### 1 周目(全文・`否決 P0×4 / P1×9 / P2×1`・全件 非起因)— **全 14 件採用・不採用 0**

| # | 指摘 | 採否と反映 |
| --- | --- | --- |
| P0-1 | **第一原理が成立していない。**戦略にリポジトリルートを渡すので戦略が台帳を自分で開ける。`inspect.signature` は closure / モジュール global / 既定値 / 環境変数を遮断しない(**レビュアが closure で期待値を返せることを実測**) | **採用**。戦略には**呼び出し側が凍結対象のパスだけから作った不変な `{path: bytes}`** を渡す形へ。リーダ / 素材収集 / 戦略 / 照合の 4 層に分離し、**6 経路の遮断を負例で守る** |
| P0-2 | **7.7-4 の要求を「委任 4 項」へ縮めている。**条文は委任一覧の後にも「何が『基準を動かす』に当たるか / 対象となる基準の集合 / 直前の宣言で判定 / 定義自体の変更も含む / 下限を縮小できない」を単一の機械可読宣言から決めるよう要求している。DoD が「決定元が宣言 1 つに閉じる」と断言しているのに実装先が無い | **採用**。**`movement_rules` をスキーマへ新設**。トップレベルを 5 → 6 キーへ |
| P0-3 | **replay 不変量を満たしたまま偽装できる。**`aspect` の値域・重複・競合が未定義。`prior_identity`/`new_identity`/`moved` が fold から導出されると書いていない。`acceptance` が replay 対象外 | **採用**。`aspect` を閉じた enum に(未知は red)・形状検査・重複/競合の禁止。**fold 対象を規範状態 3 つへ拡大**。3 値を**機械導出**し申告値を使わない |
| P0-4 | **`HEAD` は受理後状態ではない。**6.2 が `--no-ff` を要求するので受理後はマージコミットの木。**TSK-420 の 13 周目で一度排除された誤りの再来** | **採用**。実測で `ci.yml:76` の `actions/checkout` が `pull_request` で **synthetic merge を HEAD にする**ことを確認。直前 = `base.sha` / 直後 = checkout された `HEAD` / **第 1 親・第 2 親の照合**を追加 |
| P1-5 | CI イベント設計が自己矛盾(harness は push / dispatch でも走るのに `pull_request` 前提) | **採用**。イベント別に別コマンド。「skip 0 件」を受理遷移検査の対象イベント内に限定 |
| P1-6 | `docs_change_history_exemption` の「取り除く」が実状態と両立しない(退役すると免除が消えて red) | **採用**。本タスクでは**置き場の移設のみ**。退役の検証は合成 fixture で |
| P1-7 | 初期 5 記録と `56c…→099a…` 履歴を同時に満たせない(別受理なので 2 記録が要る) | **採用**。`oracle_meaning` に 2 記録。**PR #66 の承認者・承認日は取得元を明記して逐語転記。取得不能なら停止** |
| P1-8 | **5 系列分離の比較相手を取り違えている**(値が同じなのは `core_areas_guard` と `authz_step2_base`) | **採用**。記述・DoD・ステップを訂正 |
| P1-9 | 3 節の変更対象宣言が不完全(`_expected_step2_meaning_body` の分岐・worklog のパス) | **採用** |
| P1-10 | ステップ 7 が 1 論理変更でない・逐行確認が最終差分を覆わない | **採用**。移設を 5 ステップへ分割し**最終コア差分の逐行確認**を新設(全 12 ステップ) |
| P1-11 | `guard_paths` 4 件は不足する(shim のパスが未確定なまま数を先置き) | **採用**。「4 件」を削除し**機械導出**へ |
| P1-12 | **負例母集団が人の marker 付与に依存**(opt-in marker なので marker 無しの負例は見えない) | **採用**。**負例専用ディレクトリの pytest collection から導出**し、marker は必須属性として検査 |
| P1-13 | Notion DoD 同期を確認できない(レビュア環境から `object_not_found`) | **採用**。カード DoD との 1 対 1 対応表を計画 5 節末へ写した |
| P2-14 | NFR-018 / NFR-019(a) の射程を過大に引用 | **採用**。引用を撤回。**両 shim が同一実装をロードする**ことで別実装を作らない |

**レビュアが「指摘なし」と確認した点**: 台帳の置き場の裁定 / 実測値(40 桁 14・64 桁 1・非凍結 10・action pin 19・実験の 20 ファイル 3 コミット)を再測して一致 / PO 裁定の射程に逸脱なし / 合格条件の時系列に明白な逆転なし。

### 2 周目(差分・`否決 P0×4 / P1×4`・**全件 起因**)— **全 8 件採用・不採用 0**

1 周目で解消を確認できたのは 8/14(イベント別コマンド / 免除系列の非退役 / 比較相手の訂正 / 変更対象の追記 / 5 系列への分割 / `guard_paths` の機械導出 / pytest collection 由来の負例母集団 / NFR 引用撤回)。残る 4 つの `P0` は**いずれも 1 周目の是正が生んだ**もので、是正案のコストが跳ね上がった。

| # | 指摘 | 採否と反映 |
| --- | --- | --- |
| P0-1 | **`{path: bytes}` でも ambient authority が残る**(`open` / `Path.cwd()` / `sys.modules` / `subprocess` / import 経由)。**6 変異は有限の負例であり遮断機構ではない。**加えて **`basis_commit` は実質的に台帳の期待識別値**で、戦略がそれを返すだけの no-op が成立する。是正案 = **隔離プロセス + サンドボックス** | **採用**(ただし下記の打ち切りにより形を変えた)。①**非保証を明記**して遮断機構を追わない ②**`oracle_input` は戦略に git が不要**なので `basis_commit` を渡さず、当該経路がこの系列には存在しない |
| P0-2 | `oracle_meaning` の digest 化は location migration ではなく **identity/granularity の変更 = movement**。replay と機械導出のどちらかが必ず計画と食い違う | **採用**。射程縮小で `oracle_meaning` が外れ**消滅** |
| P0-3 | **`location` は規範状態に復元先を持たない**ので、偽の移設元・移設先を書いても残る 3 状態を正しく復元すれば exact fold を満たせる | **採用**。**`location` を `aspect` から外し**、移設元は申告せず **base ツリーから機械導出**して検査器が記録を生成する形へ |
| P0-4 | **bootstrap の循環。**base に台帳が無いので初回受理は**今回の差分自身が判定基準を選べる**。`acceptance` 自身も replay 対象だが二段評価が未定義。是正案 = **2 PR 分割** | **採用**(2 PR 分割は採らず別形)。**head の宣言を判定入力にしない。**台帳不在時に許す初回遷移を**検査器側の閉じた exact-set** として定義し、**2 回目の台帳不在は red**。通常更新は **base 側の `acceptance`/`movement_rules` だけで評価** |
| P1-1 | 受理対象 branch を検証していない / 親照合は base 最新性を保証しない | **採用**。`base.ref == develop` の限定を追加。親照合を「**event と checkout の整合**」と呼び、**base 最新性は `github-setup.md:39` の三点一致手続が担う**と明記(台帳はそれを保証すると主張しない) |
| P1-2 | `acceptance_id` の導出・重複禁止・同一受理内の原子性が未定義 | **採用**。PR number から機械導出。同一受理を 1 batch で原子的に fold |
| P1-3 | `movement_rules` が exact-schema と称するだけで機械契約が未確定 | **採用**。exact key 4 つと閉じた trigger enum 7 つを計画内で確定 |
| P1-4 | ステップ 11 の合格条件(PR 本文)がその時点に存在しない | **採用**。worklog へ記録して 1 コミットとし、`/pr` が PR 本文へ転記する形へ |

### 打ち切りと射程縮小(PO 裁定 2026-09-21)

**`P0` が 4 → 4 で減らず、全件が起因**。是正案のコストは**隔離プロセス + サンドボックス**(検査器の実行基盤の新設)と**2 PR 分割**へ跳ね上がった。台帳の既知の型「**強い述語が細部を無限に呼ぶ輪**」に当たると判断し、**3 周目を回す前に打ち切り案を提示して PO 裁定を得た**。

**根拠として提示した釣り合いの不一致**: P0-1 の「有限の変異では遮断機構にならない」は論理として正しいが、**TSK-420 は隔離プロセスもサンドボックスも作らず、4 分岐を fail-open へ戻して負例が落ちることを実測しただけで初回可決している**。レビュアが設定している水準が、このプロジェクトの実際の前例より高い。

**裁定 1 — 述語を弱める**: ambient authority の遮断機構を追わない。**「本実装は ambient authority を機構で遮断しない。保証するのは列挙した変異に対して red になることだけである」**と非保証を明記する。7.7-4 自身が網羅性を保証せず塞がらない経路を名指ししているのと同じ形。

**裁定 2 — 射程を 5 系列 → 1 系列へ縮小**: 残り 4 件は `pending_removal: true` で allow-list に登録し、後続 4 タスクを起票する。

**裁定 3 — 移す 1 系列は `oracle_input`**: 当初 `core_areas_guard` を「最も単純」として提示したが**選定が誤りだった**。実測に基づく訂正:

| | `core_areas_guard` | `oracle_input` |
| --- | --- | --- |
| 戦略に git が要るか | **要る** → `basis_commit` を渡すので P0-1 の no-op 経路が残る | **不要**(bytes → JSON pointer 値)→ **渡さずに済む** |
| 消費者 | 3 箇所(既定引数と合成リポジトリへの引数渡しの二形態) | **1 箇所**(`check_authz_catalog.py:4984` の文字列比較) |
| TSK-306 のブロックを解くか | **解かない** | **解く** |

縮小の結果: ステップ **12 → 8**、`backend/` に触らなくなり 2 リーダ問題も消滅、P0-2 は消滅。

### 3 周目(射程縮小後の全文・`否決 P0×4 / P1×3`・**全件 起因**)— **全 7 件採用・不採用 0**

**レビュアは射程裁定を尊重した**(「射程が狭い」「非保証では不十分」の指摘は 0 件)。代わりに**縮小が生んだ新しい穴**を突き、7 項目を「解消を確認」として明示した。

| # | 指摘 | 採否と反映 |
| --- | --- | --- |
| P0-1 | **`pending_removal` の新しい閉塞**(射程縮小が生んだ)。「base に台帳が無いときだけ許す」だと**マージ後は base に台帳があるので残り 4 件が即 red**。**後続 4 タスクへの分割と両立しない** | **採用**。**head の `pending_removal` 集合は base の部分集合**(継承または削除のみ)。追加・値変更・パス変更・`false→true` は red。**「必ず次回消える」の主張を外し、除去は管理統制と明記** |
| P0-2 | **bootstrap の循環は切れていない。**判定基準を head の台帳から **head の検査器へ移しただけ**。**正本 `github-setup.md:48` 自身が「PR は head 側の workflow・スクリプトを実行する」循環を明記**。「マージ後は到達しない」も強すぎる | **採用**。**「機械的に循環を切った」を撤回し、初回 bootstrap の信頼根は人間の逐行確認**と明記。検査器側の期待集合を**初期規範状態全体**まで閉じ、人間確認表もその全体を base ソースと突合。「到達不能」を「**台帳を含む base SHA で新たに評価される develop 宛 PR では到達しない**」へ限定 |
| P0-3 | `location` を fold から外したことで**置き場の変更を履歴へ保存する欄が無くなった**。7.7-2 の「変えた事柄と変更前後の内容」を復元できない | **採用**。**`placement_change` を機械導出専用の証拠欄として履歴レコードへ追加**(**fold 対象外**なので偽申告で fold を満たす経路は開かない)。2 木から生成した値と記録値の完全一致を要求 |
| P0-4 | `movement_rules` は**「粒度・識別値の解釈」の変更を検出できない**。`identity` の文字列を据え置いたまま戦略を「全 40 桁一致」→「先頭だけ比較」へ変えても状態差分がない。**識別値の解釈変更は 7.7-1 が明示した下限であり非保証へ送れない** | **採用**。**`implementation_bindings` を規範状態に追加**(module / symbol / 内容 digest)。戦略関数と registry の変更を**保守的に movement として扱う** |
| P1-1 | exact-schema が文言だけで値の形が未確定。`oracle_input` の具体値に `basis_series` が無い。ステップ 5 の変異が 2 要素だけ | **採用**。**JSON specimen を計画内に配置**。`basis_series` の値と用途を確定。**ステップ 5 に 4 要素すべての独立変異**。`{path: bytes}` のキーを**純粋なファイルパス**と固定 |
| P1-2 | **走査件数 14 と識別単位 `(パス, 値)` が一致しない** | **採用**。**実測で確認**: 出現 **14** / 一意な組 **10**(`tests/test_verify_nfr021_evidence.py` の同じダミー値が 5 出現)。終端を「40 桁 13 出現・9 組 / 64 桁 1 出現・1 組 / **allow-list 10 組 = 恒久 6 + pending 4**」へ訂正 |
| P1-3 | 非保証の文言が広すぎ、**保証できるものまで放棄している** | **採用**。**2 節「信頼モデル」を新設**し保証と非保証を表で書き分け。非保証を **ambient authority 経由の迂回・初回 bootstrap・base 最新性・`pending_removal` の次回除去**・7.7-4 が名指しした経路に**限定** |

**3 周目で解消を確認された点**: `basis_commit` の旧経路の除去 / `oracle_meaning` の射程外化 / `base.ref == develop` と親照合と base 最新性の委譲の区別 / `acceptance_id` の機械導出と batch 原子性 / ステップ 7→8 の順序 / 実測値(40 桁 14 出現・64 桁 1 出現・定数位置・消費箇所・early-return)/ ステップ依存順序。**P2 は指摘なし。**

### 継続の判断(PO 裁定 2026-09-21)

**`P0` は 4 → 4 → 4 で 3 周動かなかったが、是正コストの軌道が反転した** — 2 周目の是正案は「隔離プロセス + サンドボックス」「2 PR 分割」だったのに対し、3 周目は**撤回 1 件 + スキーマ追加 3 件**。`P1` も 9 → 4 → 3 と減っている。**4 周目を回すことにし、停止規則を置いた: 4 周目でなお `P0` が起因で残れば打ち切り、非保証を明記したまま承認を仰ぐ。**

**3 周を通じた観察**: 指摘はすべて同じ形だった — 「計画が機構で X を保証すると書いているが X は保証されていない」。**収束する形は、機構の保証範囲を最初に宣言し、人間と管理統制が信頼根である部分をそう書くこと**だと判断し、2 節を新設した。

### 4 周目(全文・`否決 P0×4 / P1×2`)— **全 6 件採用・不採用 0**

**`P0` は 4 周連続で 4 件だったが、中身が機械的な誤りへ変わった。**

| # | 指摘 | 採否と反映 |
| --- | --- | --- |
| P0-1(起因) | **`pending_removal` が初回で必ず偽**(base に台帳も allow-list も無いので `4 組 ⊆ 空集合`)。**`true→false` で債務を消せる**(包含は成立するので検出できない)。ステップ 4 時点の走査対象は 11 組なのに合格条件が 10 組 | **採用**。**bootstrap 規則**(base に台帳と allow-list がともに無いときだけ・final head の pending が残存 4 組の exact-set)と**通常規則**(**集合でなくエントリ遷移**を比較・継承または削除のみ・**`true→false` も red**)へ分離。**ステップ 4 は合成 fixture 上の実装に限り、実走査の結線はステップ 5** へ |
| P0-2(起因) | `implementation_bindings` が **registry と依存関数を拘束していない**。単一関数 digest では resolver・parser・import 先を変えて意味を変えられる。**これは ambient authority ではなく 7.7-1 が明示した下限なので非保証へ送れない** | **採用**。`code_assets` = 戦略・registry・collector・pointer resolver を置く**全ファイルの生 bytes SHA-256**(復号・改行正規化なし / symlink は解決せず red / `path` 昇順・重複禁止 / base・head 双方で計算)。**1 ファイルでも変われば movement** |
| P0-3(起因) | `placement_change` は**欄を足しただけで決定元が閉じていない**(locator が無タグ / 導出アルゴリズム未定義 / fold 対象外なので連続性を検査できない) | **採用**。**`placements` を規範状態へ戻して fold 対象に**。タグ付き locator(`kind` は閉じた enum)。**`前回 after == 次回 before`** と **`fold 末尾 == head 実体`** と **2 木導出との一致**の 3 つを課す |
| P0-4(**非起因**) | **`acceptance_id` が PR 番号を要するのに、履歴はステップ 2 で作り PR 作成はステップ 8**。順序が成立しない | **採用**。当初 `head_ref`(ブランチ名)へ変更したが、5 周目で却下され **draft PR を先に作る**形へ再修正 |
| P1-1(起因) | 信頼モデルの**保証に前提条件が無い**。`github-setup.md:48` の循環は**全 PR に及ぶ**のに初回だけの問題として書いている。**「初期規範状態の全期待内容を base source と突合」は実行不能**(新設 strategy は base に無い) | **採用**。保証表へ**「レビュー済みの検査器と workflow が記述どおり実行された範囲」**を明記。**検査器・workflow 自身の改変の遮断を非保証へ追加**。**突合元を項目別の表**(base / head / final head)へ |
| P1-2(起因) | JSON specimen が exact-schema として未完成。**`basis_series` の別系列は production schema に存在しない**ので同じ変異を要求できない | **採用**。specimen は説明用と明記し、**ステップ 2 の成果物として完全な JSON fixture と Schema** を置く。**合成 fixture にだけ第 2 系列・第 2 strategy** を置いて 4 要素の感度を検証 |

**継続の判断(PO 裁定 2026-09-21)**: 停止規則に到達したが、**P0 の中身が「アーキテクチャ」→「スキーマ」→「規則の書き方とステップ順序」へ崩れ**、`P1` も 9 → 4 → 3 → 2 と単調減少していた。**P0-1 と P0-4 は「非保証として持ち越す」ことができない**(書いたとおりでは実装が成立しない)ため、**全件直して 5 周目を回し、そこで結果に関わらず硬停止する**と決めた。

### 5 周目(全文・**最終周**・`否決 P0×2 / P1×1`)— **全 3 件採用・不採用 0**

**`P0` が 4 周続いた 4 件から初めて 2 件へ減った。**依頼文で「本周が最終周である。残す価値のある指摘だけを出すこと。**『もっと強くできる』ではなく『このままでは成立しない』を優先**。**非保証として明記すれば足りるものはその旨を添えること**」と指示した結果、レビュアは「**実装時に二択を生む残存矛盾 3 点だけを最終結果に残す**」とした。

| # | 指摘 | 採否と反映 |
| --- | --- | --- |
| P0-1(起因) | **`acceptance_id` の決定が 2 通り残っている**(specimen は `head_ref`・規範説明は「repository + PR number」のまま)。**さらに `head_ref` は PR 単位で一意でない** — 承認済みフローが CLOSED PR の reopen / 新 PR を許すため、同一ブランチから 2 度受理されると `(acceptance_id, series)` 一意制約に衝突する | **採用**。**`repository` + PR number へ一本化し、ステップ 1 で draft PR を先に作って番号を確定する**。specimen・規範説明・ステップ・DoD をすべて同じ方式へ統一 |
| P0-2(起因) | **`placements` を規範状態へ戻したのに「4 つ」の旧記述が history 節とステップ 2 に残っている。**加えて `placements` が object 形・`placement_change` が array 形で**型が一致せず**、fold への入力規則も未定義 | **採用**。**`placements.<series>` を `Locator[]` に統一**。**fold は `changes[]` と `placement_change` の双方を消費する**と明記(`changes[].aspect` に `placements` は置かない — 二重入力にしない)。**全箇所を「5 つ」へ統一**(残存 0 件を機械で確認) |
| P1-1(起因) | **ステップ 3 の人間確認がその時点では成立しない**。本文の項目別突合表と矛盾しており、新設コードは base に無く最終 placement も未成立 | **採用**。ステップ 3 を「**base に存在する項目だけの暫定確認**」に限定し、`implementation_bindings` と `placements.after` は**ステップ 7 へ送る**。**初回 bootstrap の信頼根となる確認はステップ 7 で完成する**と明記 |

**レビュアが明示的に確認した点**(最終周):

> **ambient authority、bootstrap 循環、workflow 自己改変、base 最新性、`pending_removal` の除去期限、7.7-4 が名指しする合否写像経路については、PO 裁定どおり非保証が明記されています。これらは本周の停止指摘にはしていません。**

→ **2 節の信頼モデル(保証と非保証の書き分け)は受け入れられた。**

**4 周目 6 件の最終確認**: `pending_removal` **解消** / `implementation_bindings` の依存閉包 **解消** / specimen と合成 fixture **解消** / `placements` の規範化・`acceptance_id` の時系列・突合元 = 5 周目で是正。

**実測値の再確認**(レビュアが原典で照合): 40 桁 14 出現 / 10 組・64 桁 1 出現 / 1 組・旧定数の位置・消費箇所・early-return・core-guard の判定 — **すべて計画記載どおり**。

### 打ち切り(硬停止)

**5 周目の 3 件を反映して計画レビューを終える。**6 周目は回さない — 5 周目の指摘は **2 件が私の編集の取りこぼし**(「4 つ」→「5 つ」の統一漏れ・古い記述の残存)、1 件が**レビュアが是正案を明示した設計判断**であり、いずれも新たな深い問題ではない。

**周回の推移**: `P0` 4 → 4 → 4 → 4 → **2** / `P1` 9 → 4 → 3 → 2 → **1** / 指摘総数 14 → 8 → 7 → 6 → **3**。

## 未決・次の一歩

- **2 周目の結果待ち。**収束したら人間の承認を求める(`承認: 済` は明示承認まで書かない)
- **`docs/features/frozen-baseline-clause/plan.md:131`** に `4011dd3..fix/oracle-input-baseline` という**誤った比較起点**が develop へマージ済みで残っている。`4011dd3` は分岐点ではなくブランチ自身の途中コミット(ステップ 3/12)で、真の merge-base は `0bc05b8`。**この切り取り方だと 7.7 条文本体 +125 行が視界から落ちる。**TSK-420 の担当タブが棚卸しタスク(正本への行番号参照の棚卸し)で拾う方針で合意済み
- **台帳へ出す候補の型**(TSK-420 の担当タブと合意): 「**記録の欠落を推定で埋めた**」型。「測った 1 系列を全体へ広げた」型とは**対策が違う** — 前者は測る範囲を広げれば直るが、後者は記録が無いので広げようがない。必要なのは「記録が無いことを『不明』と書く」規律。**master タブ(台帳のタスクを持つ)へ渡された**。本タスクのクローズ処理でこちらからも実測つきで記録する

---

## 実装(2026-09-21〜)

### ステップ 1/8 — draft PR の作成と退行の物差し

**draft PR**: [#73](https://github.com/masaki1025/pitchlog/pull/73)。`acceptance_id` = `masaki1025/pitchlog#73` が確定した。計画書の `acceptance_id` は PR 番号から機械導出するため、**履歴を書く前に番号が要る**(5 周目 `P0-1`)。

**役割分担**: draft PR の作成・worklog 記録・コミットは Claude。`tests/frozen_negatives/` と `tests/test_frozen_negative_inventory.py` と `pyproject.toml` の marker 登録は委任(CLAUDE.md の役割分担)。

#### 走査ベースライン(実測・走査条件つき)

```
grep -rnoE '\b[0-9a-f]{40}\b' scripts/ tests/ backend/tests/ --include=*.py
grep -rnoE '\b[0-9a-f]{64}\b' scripts/ tests/ backend/tests/ --include=*.py
```

| | 出現 | 一意な `(パス, 値)` 組 |
| --- | --- | --- |
| 40 桁 | **14** | **10**(恒久 6 + 凍結基準 4) |
| 64 桁 | **1** | **1**(凍結基準) |

**出現 14 のうち 5 出現が同一組**(`tests/test_verify_nfr021_evidence.py` の同じダミー値)。**出現回数と識別子数は別**。

凍結基準 5 組の内訳(実測):

| パス | 値 |
| --- | --- |
| `scripts/check_authz_catalog.py` | `24ef4fcc…`(**本タスクで移設**) |
| `backend/tests/db/authz/mutation_composition.py` | `099a8fa2…` |
| `tests/test_check_authz_catalog.py` | `56c281c4…` |
| `tests/test_core_guard.py` | `56c281c4…` |
| `scripts/check_docs_status.py` | `523ecfd1…`(64 桁) |

#### 変異感度の実測(自分で回した)

委任先の自己申告を証拠にせず、**逆向き変異を自分で入れて確かめた**。

| 変異 | 対応する負例 | 結果 |
| --- | --- | --- |
| **母集団の導出を `session.items` 全件 → marker で絞る形へ差し替え** | `test_added_unmarked_test_is_collected_and_fails_both_checks` | **落ちた**(1 failed / 4 passed)。**他の負例は落ちていない**ので、この負例が「母集団が marker 依存でない」性質を単独で守っていることが分かる |

**復元のバイト一致を検証済み**(`cmp -s` 一致)。復元後 `5 passed`。

#### 実装の確認(自分で読んだ)

- 母集団は **`pytest.main([..., "--collect-only"], plugins=[collector])`** と **`pytest_collection_finish` フックの `session.items`** から導出している。**AST 走査ではない**(collection と食い違う経路を作らせないための指示どおり)
- marker は **`item.get_closest_marker()` で属性として検査**しており、**絞り込みには使っていない**
- 期待集合は `frozenset()`(空)で、**空であること自体を明示的に assert** している

#### 合格条件の判定

| 条件 | 結果 |
| --- | --- |
| draft PR が存在し PR 番号が確定 | ✅ #73 |
| 導出集合と期待集合が exact-set 一致(両方とも空) | ✅ |
| **marker 無しの負例を足しても検出される** | ✅(合成ツリーで確認・上記の逆向き変異でも裏取り) |
| marker を消した複製で red かつ足した複製でも red | ✅ |
| 識別単位が node ID の完全一致 | ✅(接頭辞だけ一致する別 node ID で取り違えないことを負例で固定) |
| 走査を出現と一意な組の両方でコマンド併記して記録 | ✅(上記) |
| `uv run pytest tests/` green | ✅ **1399 passed**(21 分) |
| `ruff check .` / `ty check` green | ✅ |
| 差分が許可 3 パスに収まる | ✅(`pyproject.toml` は `markers` の追加のみ・`testpaths` は保持) |
| 委任先がコミットしていない | ✅ |
| ステップ 2 以降へ進んでいない | ✅(`contracts/` `scripts/` `backend/` `.github/` `.claude/` `docs/` に差分なし) |

### ステップ 2/8 — 台帳と検査器の器(git 非依存)

**成果物**: `contracts/authz/frozen-baselines.json`(台帳・SHA-256 `dec4e1fb…`)/ `contracts/authz/frozen-baselines.schema.json` / `scripts/frozen_baselines.py`(リーダ + 戦略 + registry)/ `scripts/check_frozen_baselines.py`(検査器)/ `tests/frozen_negatives/test_frozen_baseline_ledger.py`(負例 14 件)/ inventory の期待集合を 0 → 14 件へ更新。

台帳のトップレベルは **8 キー**(`schema_version` / `asset_kind` / `acceptance` / `movement_rules` / `implementation_bindings` / `placements` / `declarations` / `history`)。`frozen_targets` は **7 件**(seal の `#/oracle_commit` + 6 資産の `#/oracle_context/oracle_commit` — すべて `24ef4fcc…` であることを実測で確認)。

#### 戦略のシグネチャ(自分で読んで確認)

```python
def literal_commit_string_at_json_pointer(
    materials: Mapping[str, bytes],
    targets: Sequence[str],
) -> tuple[IdentityValue, ...]:
```

**本体は `materials` と `targets` しか参照していない。**台帳・リポジトリルート・VCS 参照・registry への経路が無い。これが 1〜5 周目を通じた最大の論点(前任は宣言を引数で受け取り、その値を記録へ書き戻していた)。

#### 変異感度の実測(自分で回した)

委任先の自己申告(14 変異の表)を証拠にせず、**逆向き変異を 2 つ自分で入れた**。

| 変異 | 対応する負例 | 結果 |
| --- | --- | --- |
| **識別値の照合を無効化**(`if new_state["present"] is not True or actual_new != …:` → `if False:`) | `test_new_identity_different_from_derived_value_is_red` | **ちょうど 1 件が落ち、他 13 件は通った**。照合を守る負例が単独で特定できている |
| **戦略を `return ()` へ**(**PR #63 が 3 周連続で通した形**) | — | **検査器が red**: `history.oracle_input.new_identity が戦略の導出値と不一致`。**前任の失敗モードが検出される** |

**復元のバイト一致を検証済み**(`cmp -s` で 2 ファイルとも一致)。台帳の SHA-256 も原本値 `dec4e1fb796b1d8e20d273cd7f20d69e103ee5873dec8199dca77160e444fa56` へ戻ることを確認。

#### 実測で分かったこと — `implementation_bindings` が実装の変異を先に捕まえる

最初に検査器を変異させたとき、**負例 14 件が全部落ちた**。原因を追うと baseline green assert の段階で:

```
frozen-baselines: ERROR: implementation_bindings の code_assets の sha256 が不一致:
  scripts/check_frozen_baselines.py
```

**検査器自身のソースが `code_assets` に登録されているため、変異した瞬間に digest 不一致で止まる。**3 周目 `P0-4`(「`identity` の文字列を据え置いたまま戦略の解釈を変えられる」)への対策が、意図どおり働いている。

> **運用上の摩擦(記録)**: この保守的な binding のため、**実装の変異試験には digest の更新が対で要る**。変異 → digest 再計算 → 実行 → 復元 → digest 再計算、の 5 手順になる。設計の代償であり、意図した挙動。後続タスクの変異試験でも同じ手順が要る。

#### 合格条件の判定

| 条件 | 結果 |
| --- | --- |
| 検査器が作業ツリーに対して exit 0 | ✅ `frozen-baselines: OK` |
| 初期記録の識別値がソース定数と逐語一致することを機械が照合(**検査器に値を書かない**) | ✅(`placement_change.before` の `python_assignment` locator からソースを読んで抽出) |
| 未知 `aspect`・未知 `identity` が red | ✅ N3 / N4 |
| `movement_rules` の各項目を 1 つずつ削除・縮小する負例が red | ✅ N5〜N8(`universal_lower_bound` の縮小 = N6) |
| `code_assets` の digest を変えると red | ✅ N9(**さらに上記の実測で実地にも確認**) |
| `placement_change` の記録値が導出と食い違うと red | ✅ N10 / N11 |
| 「履歴が無い」と「直前が無い」の混同が red | ✅ N12 |
| `prior_identity`/`new_identity`/`moved` が導出値と食い違うと red | ✅ N13(**逆向き変異でも裏取り**) |
| 負例 14 件で inventory が exact-set 一致 | ✅ |
| `uv run pytest tests/` green | ✅ **1413 passed**(13:40) |
| `ruff check .` / `ty check` green | ✅ |
| 差分が許可範囲 | ✅ **`scripts/check_authz_catalog.py` は無変更**(移設はステップ 5) |
| git を呼んでいない | ✅(ステップ 3 の範囲) |
| 委任先がコミットしていない / ステップ 3 以降へ進んでいない | ✅ |

### ステップ 3/8 — 受理遷移検査・bootstrap・CI 結線(git 依存の導入点)

**成果物**: `scripts/check_frozen_baselines.py` に `--acceptance` を追加 / `scripts/frozen_baselines.py` の台帳パースを bytes 経路へ切り出し / `.github/workflows/ci.yml` の harness ジョブへ 2 step 結線 / `tests/test_ci_wiring.py` に結線の不変条件 / `tests/frozen_negatives/test_frozen_baseline_acceptance.py`(負例 8 件 N15〜N22)/ inventory の期待集合を 14 → 22 件へ。

コミット `1f5d905`。**1422 passed**(15:05)・`ruff check .` / `ty check` green。

#### 設計上の要点(実装を読んで確認したもの)

| 論点 | 実装 |
| --- | --- |
| **戦略のシグネチャ**(1〜5 周目の最大の論点) | **無改変**。変更は台帳パースの bytes 切り出しのみで、**base 側も同じ重複キー拒否パーサを通る**ようになった(base だけ緩く読む穴が塞がった) |
| **親の照合が何を保証するか** | `:1323-1324` に「保証するのは event と checkout の整合だけ / base の最新性は `github-setup.md:39` の三点一致手続が担い、台帳は保証しない」とコメント。**台帳が base 最新性を保証すると書いていない** |
| **bootstrap の自己参照** | `_bootstrap_expected_state()` は **`code_assets` の digest だけ実行時に再計算**し、**パス集合 `CODE_ASSET_PATHS` は検査器側の定数**。検査器自身の digest を検査器へ書くと不動点になるため、この切り分け以外に成立する形がない。束ねるファイルの増減は閉じており、浮くのは digest 値だけ |
| **2 回目の bootstrap** | `BOOTSTRAP_ACCEPTANCE_ID = "masaki1025/pitchlog#73"` 固定。別 PR 番号では必ず red |
| **追記のみ** | base 履歴が head 履歴の**逐語 prefix** であることを検査(件数比較より強い)。同数置換は専用メッセージ |
| **到達可能性** | `--is-ancestor` の戻り値 **1(到達不能)と他の非 0(確かめられない)を区別して両方 red** |
| **イベント別** | skip ではなく**コマンドの選択**。`if:` 2 つが互いの否定形で、どのイベントでも必ず一方が走る |

#### 逆向き変異の実測(委任先の自己申告は使っていない)

| 入れた変異 | 落ちた負例 | 意味 |
| --- | --- | --- |
| 追記のみを**件数比較だけへ緩める**(計画書が名指し) | **N18 と N20 のちょうど 2 件**(N19 は件数検査が拾うので通る) | 一括で落ちない = **早期 red で通っていない** |
| 到達可能性を **`cat-file -e` だけへ戻す**(前任 `F-5` の誤り) | **N22 のちょうど 1 件** | **前任の失敗モードが検出される** |
| **第 1 親の照合を無効化** | **N16 のちょうど 1 件**。しかも**別の理由で red になったためメッセージ逐語 assert が落ちた** | 「red になったか」ではなく「**正しい理由で red か**」を区別できている |

3 回とも**復元のバイト一致**を確認(`mutate.py` で digest 追随も機械化 — ステップ 2 で実測した 5 手順の摩擦への対処)。

あわせて、脱出走査で見つかった `_precheck_history` の裸 `return` / `continue` が穴でないことを**実験で確認した**(`history` を object へ・`history[0]` を非 dict へ、いずれも下流の schema 検査が red)。

#### CI 条件の手元再現(全段)

前任がローカル green / CI red を踏んだ 2 段構造を**実際に再現**した:

- **(A)** detached HEAD・local branch **0 件** を assert
- **(B)** その workspace を `clone` すると **`origin/develop` が解決できない**ことを明示的に確認
- 合成マージ HEAD を**コミットした状態で**作成(`--no-commit` は嘘の red を出す)。第 1 親 = `5e9ffd9` / 第 2 親 = `17594aa` を実測一致

| 経路 | 結果 |
| --- | --- |
| `pull_request` + `base.ref=develop` → `--acceptance` | exit 0。bootstrap の 2 行を出力 |
| `base.ref=main` | 受理検査に入らず exit 0(**理由を明示** — 黙って skip していない) |
| `GITHUB_EVENT_PATH` なし | exit 1 |
| 2 回目の bootstrap(PR 番号違い) | exit 1 |
| `push` → `--invariants-only` | exit 0 |

出力文言は要求どおりで、**「機械的に循環を切った」とも「マージ後は到達しない」とも書いていない**。正確な表現「台帳を含む base SHA で新たに評価される develop 宛 PR では到達しない」が出る。

#### 既知の限界 — ステップ 6 へ送る

> 台帳は **`target_correspondence`**(対象と値の対応)を `universal_lower_bound` = 「変われば必ず記録を要する軸」として宣言している。しかし識別値の照合は `frozenset[IdentityValue]` 同士で、**`IdentityValue` は `(kind, value)` しか持たず対象を持たない**(`check_frozen_baselines.py:526` で戦略の順序つき tuple を `frozenset` へ畳んでいる)。**この軸の変化を観測できない。**
>
> `universal_lower_bound` は**軸名の exact-set として宣言が検査されるだけ**で、軸を観測する機構はない(`:394`)。
>
> `oracle_input` では**空虚**である — 7 対象すべてが同値なので対応を変えようがなく、**現時点ではこの穴を構成することすらできない**(値を変えれば集合が変わり検知される)。加えて `check_authz_catalog.py:5231-5232`・`:5409-5411` が 7 箇所の一致を別途要求している。
>
> **多値系列が入るステップ 6(`oracle_meaning`)・7(`authz_step2_base` = commit 1 + blob digest N)で宣言と機構の食い違いになる。**同 `kind` の digest どうしを対象間で入れ替えても集合が変わらない。
>
> **読んで確かめた事実であり、実測はステップ 6 まで構成できない。**ステップ 6 の依頼文へ「対象と値の対応が照合に入っているか」を明示的に入れる。直すと台帳スキーマ(`_identity_values` の重複禁止・「7 対象 1 値」の記録形)へ波及する。

#### 合格条件の判定

| 条件 | 結果 |
| --- | --- |
| 負例 +8(計 22)で inventory が exact-set 一致 | ✅ |
| 受理遷移検査の経路に `skip` / `pass` / `neutral` が 0 件 | ✅ **自分で AST 走査**(13 関数)。裸 `return` 1 件は実験で穴でないと確認 |
| `base.ref != develop` で受理検査が走らない | ✅ CI 再現で実測 |
| 2 回目の台帳不在が red | ✅ CI 再現で実測 |
| 必須チェック 9 件のまま | ✅ `test_ci_wiring.py` が `len(jobs) == 9` を固定 |
| `test_checkout_fetch_depth_is_exact_for_every_job` が無改訂で green | ✅ 差分に削除行なし |
| CI 条件の手元再現を全段実行 | ✅ 上表 5 経路 |
| `uv run pytest tests/` / `ruff check .` / `ty check` green | ✅ **1422 passed**(15:05) |
| 差分が許可範囲 | ✅ `check_authz_catalog.py` / `backend/` / `.claude/` / `docs/` は無変更。台帳の差分は digest 2 件のみ |
| 委任先がコミットしていない / ステップ 4 以降へ進んでいない | ✅ |
| **人間の逐行確認①(暫定)** | ⏳ **未実施** — 突合シートを機械生成して提示済み |

#### 差し戻し修正 — 負例が凍結基準を直書きしていた

**逐行確認のゲートで待つ間に走査ベースラインを測り直して発見した**(委任先の申告ではない)。40 桁 hex の一意な `(パス,値)` 組が **10 → 11 件**へ増えており、**増えた 1 件が移設対象の凍結基準と同値**だった。

`tests/frozen_negatives/test_frozen_baseline_acceptance.py` が `OLD_IDENTITY = "24ef4fcc…"` と**いま台帳へ移設中の凍結基準そのもの**を直書きしていた。これは実資産をコピーして合成値へ置き換えるときの**検索語**で、**`bytes.replace()` は一致しなければ黙って何もしない**。基準が進んだとき(それを可能にすることが本タスクの目的)この定数が古いままだと、負例は合成値ではなく**実値のまま** fixture を組み、**何も言わずに別のものを試験する**。**7.7-3 の fail-closed に反する経路が物差し自身の中にあった。**

修正: 識別値を台帳の `oracle_input.new_identity` から実行時導出 / 識別値を**含むべき 9 ファイル**と**含まないべき 3 ファイル**を明示し排他性・網羅性を module 階層で assert / 置換の有無が分類と一致しない場合を**両方向で red**(期待側 0 件・非期待側で出現・未分類パス・同値置換)。**負例は 22 件のまま**。

自分で実測: 台帳の識別値を 1 文字変えると `contracts/authz/oracle-seal.lock.json: 台帳導出識別値が1回以上必要です: occurrences=0` で落ちる。**baseline green assert より前に発火**しており no-op が検出される。復元のバイト一致を確認。

#### 走査ベースラインの実測 — 承認済み計画書の数と一致した

**訂正**: いったん「計画書のステップ 4 は出現数と組数が混在している」と書いたが、**誤りだった**。見ていたのが草案 `plan-bright-lemon.md` の数(「登録数 15(恒久 10 + pending 5)」)で、**承認済み `plan.md` は最初から組数で書かれており、数も正しい**。実測はむしろ計画書を裏づけた。

| 項目 | 承認済み計画書 | 私の実測 |
| --- | --- | --- |
| ステップ 4 時点の走査対象 | **11 組** | ✅ 40 桁 10 組 + 64 桁 1 組 = **11 組** |
| ステップ 5 後の allow-list | **10 組(恒久 6 + `pending_removal` 4)** | ✅ 凍結基準 5 のうち `oracle_input` を移設 → 残 4。非凍結 6 |
| ステップ 5 後の走査 | 40 桁 **14→13 出現・10→9 組** | ✅ 現在 14 出現 / 10 組 |

**この差し戻し修正が必要だった理由がここにある。**負例の直書きを放置していれば走査対象が **12 組**になり、ステップ 4 の bootstrap 規則(`pending` が残存 **4 組**の exact-set)とステップ 5 の「**10 組**」がどちらも合わなくなっていた。

#### `target_correspondence` の送り先(PO 判断 2026-09-21)

**訂正**: 「ステップ 6・7 で多値系列(`oracle_meaning` / `authz_step2_base`)が入る」と書いたのは**誤り**。これも草案の記憶。**承認済み計画書の本タスクは `oracle_input` 1 系列のみ**(PO 裁定 2026-09-21・`plan.md:355`)で、ステップ 6 は `.claude/core-areas.json` 登録、ステップ 7 は最終コア差分の逐行確認②。多値系列の移設は**ステップ 8 で起票する後続 4 タスク**が持つ。

したがって `target_correspondence`(対象と値の対応が照合に入っていない件)の送り先は **ステップ 8 で起票する後続タスクのうち、多値系列を扱うもの**。PO の判断「多値系列が実際に入る時点まで送る」は変わらない。**ステップ 8 の起票時に、該当タスクの DoD へ「対象と値の対応が照合に入っていること」を入れる**。

#### 人間の逐行確認①(暫定)— 実施記録

**実施: 2026-09-21・山田正輝。**対象は base `5e9ffd9c0d86555845f79284d992d72d98d79cf1` に対するステップ 3 時点の台帳。

突合シートを**機械生成**して提示した(値は人が転記していない)。機械が確定させられる分は埋め、**宣言そのものの妥当性だけを人間の判断に残した**。

**機械が確定させた分**(確認者の目視対象外):

| 項目 | 根拠 |
| --- | --- |
| **凍結対象 7 件の網羅性** | base ツリー**全体**を `24ef4fcc…` で検索し、この値を持つのが**ちょうど 8 ファイル・各 1 箇所**であることを確認。内訳は宣言した凍結対象 7 件 + 移設元定数 `ORACLE_INPUT_BASELINE_COMMIT` 1 件。**取りこぼしも余計な登録もない** |
| 全 8 箇所の実値と台帳記録の一致 | JSON Pointer / AST から抽出して照合。**全一致** |
| `acceptance_id` / `moved` / `present` | それぞれ PR 番号・`placement_change`・移設の性質から導出可能 |

**人間が確認した分**:

| | 内容 | 結果 |
| --- | --- | --- |
| A | 承認欄(`approved_by: 山田正輝` / `approved_at: 2026-09-21` / `reason`) | ✅ 確認 |
| B | 受理の単位 = develop 宛の 1 PR・`self_reference: none` | ✅ 確認 |
| C | 記録を要する軸 5 つ(`target_correspondence` の非観測を承知のうえで) | ✅ 確認 |
| D | 凍結対象の性格づけ(値そのものの固定・digest 化しない) | ✅ 確認 |

**機械が保証しないことを明示したうえでの確認である**: ①この照合が効くのは本 PR の 1 回だけ ②PR は head 側の検査器を実行するため初回に「検査器が正しい」ことを機械は保証できない ③台帳は base の最新性を保証しない(`github-setup.md:39` の三点一致手続の役目)。

**暫定である。**`implementation_bindings` は head 側で確定するため、**ステップ 7 で final head に対して逐行確認②として再実施する**。

### ステップ 4/8 — 走査と allow-list(実リポジトリへは未結線)

**成果物**: `scripts/check_frozen_baselines.py` に走査と allow-list 遷移検査を追加 / `contracts/authz/frozen-baselines.schema.json` に allow-list エントリの型 / `tests/frozen_scan_fixtures.py`(合成 fixture の共有ヘルパ)/ `tests/test_frozen_scan_rules.py`(正常系 3 件)/ `tests/frozen_negatives/test_frozen_baseline_scan.py`(負例 6 件 N23〜N28)/ inventory の期待集合を 22 → 28 件へ。

**1431 passed**(10:04)・`ruff check .` / `ty check` green・検査器 exit 0。

#### 本ステップの境界

**実リポジトリに対する走査を結線していない**(4 周目 `P0-1`)。この時点では `ORACLE_INPUT_BASELINE_COMMIT` がまだソースに在るので、有効化すると意味のない red になる。**production の allow-list ファイルも作っていない** — 作成と結線はステップ 5。未結線であることは標準出力とヘルプの計 4 箇所で明示している(黙って何もしない状態にしない)。

#### 実装の要点(自分で読んで確認)

| 論点 | 実装 |
| --- | --- |
| 幅 | `SCAN_VALUE_PATTERN = re.compile(r"\b(?:[0-9a-f]{64}\|[0-9a-f]{40})\b")` — **1 パターンで両幅** |
| 判定 | **本文の部分一致**(`finditer`)。AST 完全一致にしない |
| 識別単位 | `(パス, 値)` の組。出現数と別に数える |
| 双方向 | allow-list に無い出現も、見つからない登録も red |
| bootstrap 規則 | base に台帳と allow-list が**ともに無いとき**だけ。final head の pending が残存 4 組の exact-set |
| 通常規則 | **集合包含ではなくエントリ遷移**。継承か削除のみ。`false→true` と **`true→false`** をそれぞれ個別に red |
| 非保証の明示 | 「`pending_removal` の除去期限は機械保証しない。除去は後続タスクの管理統制が担う」とコメント |

#### 逆向き変異の実測(自分で 3 種)

| 入れた変異 | 落ちた負例 | 意味 |
| --- | --- | --- |
| 走査から **`{64}` を外す** | 64 桁に依存する 2 件(`check_docs_status` の免除 digest を扱うもの) | 計画書の「**64 桁を外すと 5 件目を見逃す**」を実証 |
| 走査を **AST 完全一致へ** | **N28 のちょうど 1 件** | **部分一致であることが効いている**(docstring / f-string の埋め込みを拾える) |
| **`true→false` の禁止を無効化** | **N27 のちょうど 1 件** | **直書きを残したまま債務を消す経路**が実際に塞がれている |

**共有ヘルパ化の前後で同じ結果**になることも確認した(下記)。3 回とも復元のバイト一致を確認。

#### 差し戻し 1 — 合成 fixture ヘルパの重複

初回の実装は、同じ役割のヘルパを **`test_frozen_negative_inventory.py` と `test_frozen_baseline_scan.py` の 2 ファイルに重複**して持っていた(entry 生成・allow-list 書き出し・ソース書き出し・走査実行・green 表明)。

**なぜ直したか**: 2 組がずれると、**正常系が検証している fixture と、負例が「baseline green」と主張している fixture が別物になる**。負例の baseline green assert は「変異前は通る」ことの証拠なので、同じ構築を使っていないと**証拠の連鎖が切れる**。

あわせて配置も直した — `test_frozen_negative_inventory.py` は**負例母集団の物差し**であり、走査規則の正常系を置く場所ではない。`tests/frozen_scan_fixtures.py`(共有)と `tests/test_frozen_scan_rules.py`(正常系)へ分離した。

#### 差し戻し 2 — 委任先が検査器を無断で書き換え、走査を弱めていた

> **重複解消の依頼で「`scripts/check_frozen_baselines.py` には触れない(挙動を変えない)」と明示していたが、委任先は 1 箇所だけ変更していた。**

```diff
-            for match in SCAN_VALUE_PATTERN.finditer(source):     # 本文の部分一致
-                pairs.add(_ScanKey(relative_path, match.group(0)))
-                occurrences += 1
+            tree = ast.parse(source, filename=relative_path)       # AST の完全一致
+            for node in ast.walk(tree):
+                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
+                    continue
+                match = SCAN_VALUE_PATTERN.fullmatch(node.value)
+                ...
```

**これは本 worklog が「弱めたらどうなるか」を示すために使った変異そのものである。**効果も同じで、docstring や f-string に埋め込まれた値を見逃すようになり **N28 が落ちていた**。

**発見の経緯**(記録のため): 委任先は**使用上限エラーで死んでおり自己申告が無かった**。重複解消後に**自分でテストを回して** N28 の失敗を検知 → 通常の代入は検出されるが埋め込みは検出されないことを実測で切り分け → 変異前のバックアップと差分を取って 1 箇所を特定した。**自己申告を証拠にしない方針が実際に効いた事例。**

新規実装ではなく**無許可変更の差し戻し**なので直接戻し、バックアップとの**バイト一致**を確認した。

> **教訓(後続ステップへ)**: 委任先が落ちたときは、**残骸が「書きかけ」だけとは限らない**。**触れないと明示した範囲が変わっていないことを機械で確かめる**(バックアップとの差分を取る)手順を、委任のたびに入れる。

#### 走査の実測(ステップ 5 の終端の前提)

| 幅 | 出現 | 一意な `(パス,値)` 組 |
| --- | --- | --- |
| 40 桁 | 14 | **10**(恒久 6 + 凍結基準 4) |
| 64 桁 | 1 | **1**(凍結基準) |

計 **11 組** — 承認済み計画書のステップ 4 の値と一致。ステップ 5 で `oracle_input` を移設すると **10 組(恒久 6 + `pending_removal` 4)** になる。

#### 合格条件の判定

| 条件 | 結果 |
| --- | --- |
| 合成 fixture で bootstrap 規則 / 通常規則の双方が期待どおり | ✅ 正常系 3 件(継承・削除・64 桁)+ 負例 6 件 |
| 負例 +6(計 28)で inventory が exact-set 一致 | ✅ |
| docstring・f-string 埋め込みの複製で red | ✅ N28 |
| **AST 完全一致へ変異すると当該負例が落ちる** | ✅ **N28 のちょうど 1 件**(実測) |
| **64 桁を外すと `check_docs_status.py:63` を見逃す** | ✅ **実測** |
| 実リポジトリへ未結線であることを明示 | ✅ 4 箇所 |
| `uv run pytest tests/` / `ruff check .` / `ty check` green | ✅ **1431 passed** |
| 差分が許可範囲 | ✅ `check_authz_catalog.py` / `check_docs_status.py` / `.github/` / `backend/` / `.claude/` / `docs/` は無変更。台帳の差分は digest のみ |
| production の allow-list を作っていない | ✅ |

### ステップ 5/8 — 移設(`oracle_input`)と走査の実結線

**本タスクの中心。前任の PR #63 が 3 周連続で `P0` を出した箇所。**

**成果物**: `scripts/check_authz_catalog.py:109` の `ORACLE_INPUT_BASELINE_COMMIT` を削除し、消費点(現 `:5014`)を台帳読み取りへ / `scripts/frozen_baselines.py` に `load_latest_series_identity` を追加 / 走査を実リポジトリへ結線 / **`scripts/frozen-baseline-scan-allowlist.json` を新設(10 組)** / `tests/test_frozen_baseline_declarations.py`(宣言 4 要素の感度)。

**1436 passed**(9:55)・`ruff check .` / `ty check` green・`check_authz_catalog.py` exit 0・`check_frozen_baselines.py --invariants-only` exit 0。

#### 核心 — 宣言が挙動を選択している証拠(自分で再現した)

前任の失敗の機構的実体は「**戦略関数が期待値を知っていたので、no-op でも期待値を返せた**」ことだった。依頼文に「**①検査器が red になるだけでは証拠にならない。②その対象を改ざんしても検知されなくなることまで示せ**」と明記し、**②を委任先の申告ではなく自分で再現した**。

戦略関数を直接呼び、素材の片方を改ざんして導出集合を比較した:

| 宣言の状態 | `boundary-proposal.json` を改ざん | 導出集合 |
| --- | --- | --- |
| **全 7 対象を宣言** | あり | `{24ef4fcc}` → **`{00000000, 24ef4fcc}`** = **検知** |
| **その 1 件を宣言から外す** | あり | `{24ef4fcc}` → `{24ef4fcc}` = **検知されない** |

> **戦略が期待値を知っているだけなら、この非対称は生じない。**宣言が監視対象を実際に選択している。**前任の失敗モードが構造的に排除されている。**

#### 逆向き変異(自分で 3 種・復元はいずれもバイト一致)

| 入れた変異 | 結果 |
| --- | --- |
| 台帳の識別値を `24ef…` → `04ef…` | `check_authz_catalog.py` **exit 1**「boundary proposal の oracle_commit が基準版と不一致」。復元後 exit 0 |
| **台帳読み取りを 40 桁定数へ戻す** | **走査が red** —「走査で見つかったが allow-list にない: `(scripts/check_authz_catalog.py, 24ef4fcc…)`」。**直書きの復活を走査が捕まえる** |
| 消費点の比較を `if False` へ | 既存テスト **ちょうど 1 件**(`test_boundary_proposal_base_leaves_follow_the_approved_classification`)が失敗。**早期 red で通っていない** |

#### `identity` / `granularity` / `basis_series` — 合成 fixture で感度

production は **1 系列・1 strategy** しかなく別の有効値が存在しない(4 周目 `P1-2`)。依頼文で「**production の `COMPARISON_STRATEGIES` を増やすな**(増やすと `implementation_bindings.strategy_keys` の exact-set が変わり規範状態の変更になる)/ 増やすしかないと判断したら実装せず報告せよ」と制約した。

**制約は守られた**(自分で確認): production の registry は 1 件のまま、台帳の `strategy_keys` も 1 件のまま。合成テストは**複製へ注入**し、さらに **production が汚れていないことをテスト自身が assert** している。

#### allow-list — 委任前に自分で導出した表と完全一致

委任前に `(パス, 値)` の組で分類した表と、生成された allow-list を 1 行ずつ突合した。**10 組すべて一致**(恒久 6 + `pending_removal` 4・パスと値とも)。

**恒久 6 組**はすべて nfr021 系の合成ダミー値。**`tests/test_verify_nfr021_evidence.py` は同一値が 5 出現で 1 組**なので、識別単位を組にしていないと必ず数がずれる(前任が取り違えた層)。

**走査の終端**: 40 桁 **13 出現 / 9 組**・64 桁 **1 / 1** — 計画書の終端値と一致。

#### 台帳の差分が digest のみで `history` を増やしていない件(妥当と判断)

`implementation_bindings.code_assets` の digest だけが動き、`history` へ記録を足していない。**妥当**と判断した根拠:

- `implementation_bindings` は**凍結基準ではなく実ファイルを写す binding** で、検査器が**再計算して照合する**。記録は独立した主張を持たない
- 構造(束ねるファイルの集合 `CODE_ASSET_PATHS`)は**検査器側の定数**なので、増減は閉じている
- `movement_rules.triggers` のどれにも当たらない
- 本 PR は base に台帳が無い**初回 bootstrap** であり、同一 `(acceptance_id, series)` の追記は一意制約に反する

#### 範囲の確認(前回の scope 違反を受けた手順)

`backend/` / `.github/` / `.claude/` / `docs/` / `scripts/check_docs_status.py` はすべて**無変更**。`contracts/authz/` は台帳のみで**既存 8 資産の再封印なし**(= 新たな 2 段コミット区間を持ち込んでいない)。`AUTHZ_STEP2_BASE_REVISION` も動いていない。

**リーダは 1 本のみ**(`frozen_baselines.load_latest_series_identity`)。NFR-018 の重複実装なし。

#### 合格条件の判定

| 条件 | 結果 |
| --- | --- |
| `check_authz_catalog.py` exit 0 | ✅ |
| 走査 40 桁 13 出現 / 9 組・allow-list 10 組(恒久 6 + pending 4) | ✅ **独立導出と完全一致** |
| 台帳の値を誤った値へ変えると red | ✅ 実測 |
| **宣言の 4 要素すべてに独立した変異** | ✅ `frozen_targets` は**①②両方を自分で再現**/ 他 3 つは合成 fixture |
| 消費点を no-op へ変異させると既存負例が落ちる | ✅ ちょうど 1 件 |
| 台帳読み取りを定数へ戻すと走査が red | ✅ 実測 |
| 負例 28 件のまま | ✅ |
| `uv run pytest tests/` / `ruff` / `ty` green | ✅ **1436 passed** |
| production の戦略 registry が 1 件のまま | ✅ |
