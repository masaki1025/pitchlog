---
feature: feature-status
type: design
date: 2026-08-10
---

# 詳細設計: feature 現在地の導出機構

計画書([plan.md](plan.md))の 4 節から参照される詳細設計。調査の典拠は [research.md](research.md)。

## 1. 原則

- **保存ではなく導出**: 現在地はいかなるファイルにも保存しない。導出源は plan frontmatter・実装ステップ表 × git log・PR 状態(gh)・Notion 照合(対話時のみ)。保存型 state.yaml は二重正本のため不採用(v0.10 P1-4 の先例 — research.md §5 で出典訂正済み)
- **出力は派生表示**であり正本ではない(設計書 7.1-5 の索引と同じ位置づけ。ただし索引と異なり CI 検査対象外の一時表示)
- **無言縮退の禁止**: 取得できない情報は「未取得」と明示する(NFR-015 の類推 — 設計書 :436/:619 の援用前例)
- **書き換えない**: feature_status.py は Git・GitHub・Notion のいずれにも書き込まない(読み取り専用)

## 2. plan frontmatter 拡張キー

**契約の正は設計書 6.1(v1.3)の拡張キー表**(1テーマ1正本 — 確定ゲート 1 周目 P2 で本節の表を正本へ移管)。本節は実装・運用の詳細のみ:

- `実行方式` はキーが存在して値が列挙外(空値・`fastt` 等)の場合、stage 判定せず「**未取得(実行方式不正)**」と顕在化(無言で通常扱いにしない — 7/8 周目 P1)
- **機構が読むキーの重複**(同名キーが同一 frontmatter に 2 行以上)は「**未取得(frontmatter 解析失敗)**」(確定ゲート 1 周目 P2 — last-wins で黙って解釈しない)

- **配置規則: 既存 8 キーの後(`created` の後)= frontmatter 末尾**。`status:`・`branch:` を前方に保つ(§4 の一本化完了までの互換と、以後の恒久規則)
- 文法は codex_run.py の行パーサ互換(`key: value`・行末 `#` コメント可・ネスト/リスト不可 — codex_run.py:76-86)。**値検証**: 非整数・負値は feature_status.py が「不正値」と表示する(パースは fail-open — 例外で死なない)
- **更新先の解決規則(レビュー 1 周目 P1)**: `確定ゲート周回` の更新先は**実行中 feature の plan.md** — /finalize-doc 実行時の worktree の `docs/features/*/plan.md` で `status: <active|in-review>` かつ `branch` が worktree 実ブランチと一致するもの。一意に解決できない場合は**人間に確認**する(黙って省略しない)。/finalize-doc スキル手順に更新対象 plan パスの明示を追記する
- **正本 status の複製禁止**(設計書 7.1-1)。plan frontmatter に置けるのは **feature 作業自身の進行事実のみ**。確定ゲートの対象正本は計画書 3 節の宣言から導出し、正本の現在状態は当該正本自身の frontmatter から読む(research.md §1 欠落 3)
- 差し戻し回数は導出可能性が残るため(Notion 差し戻し履歴)今回は保存キーにしない。必要が実証されたら同文法で追加する

## 3. scripts/feature_status.py

### 3.1 入力と列挙

- 基準ディレクトリは `--cwd`(既定 = カレント)。そこから `git worktree list --porcelain` で全 worktree を列挙(session_context.py:29-43 と同方式)。保護ブランチ(main/develop)上の worktree は除外(マージ済み plan 複製の排除 — session_context.py:70-72 と同じ理由)
- 各 worktree の `docs/features/*/plan.md` を走査。frontmatter は先頭 `---` 〜 次の `---` のブロック全体を解析(**安全上限 8KiB・先頭 N 文字の切り詰めをしない** — 800 文字問題の恒久解消。この解析器が唯一の実装〔§4 で hook 側は削除〕)
- 対象判定は**厳密一致**(2 周目 P1・3 周目 P1 で精密化): status 行の**候補抽出は `^status\s*:`**(check_docs_status.py:22 の STATUS_PREFIX_RE と同一 — `status : active` も候補に数える)。候補が frontmatter ブロック内に**ちょうど 1 行**あり、その行全体が `^status:\s*(active|in-review)(?:\s+#.*)?$` に**完全一致**すること(check_docs_status.py:332-342 と同じ要求水準 — `activeX`・余剰トークン・`status : active`(コロン前空白)・候補行の重複は**解析失敗**。行末 `#` コメントは適合)。かつ `^branch:` が worktree の実ブランチと完全一致すること
- **評価順**(3 周目 P2 → 確定ゲート 1 周目 P1 で worktree 期待解決へ改訂): ①保護ブランチ worktree を無言除外 → ②frontmatter/status の解析(**失敗は「未取得(frontmatter 解析失敗)」として顕在化**)→ ③**worktree 単位の期待解決** — 対応 plan = **期待パス `docs/features/<branch の slug>/plan.md`** にあり(6.1 の配置規約 — 確定ゲート 2 周目 P1)、解析可能かつ `branch` が worktree 実ブランチと完全一致するもの。期待パスに無い branch 一致 plan(誤配置)は**正常採用せず顕在化**。該当 0 件は「**未取得(plan 不在 / branch 不整合)**」(期待 slug ディレクトリの有無で区別)・複数該当は「**未取得(plan 重複)**」と text/hook 双方で顕在化(「worktree の現存を正とする」7.6-4 に整合 — 現存 worktree を無言で消さない)。**歴史的な他 feature の plan**(branch 不一致かつ期待 slug でもない)のみ無言スキップ(全 worktree に全 feature の plan が同梱されるため)。解析失敗と branch 不一致が同時のケース(例: `activeX` + branch 不一致)は**解析が先 = 表示される**
- **除外と顕在化の区分**(2 周目 P1): 無言除外は上記①③のみ。feature ディレクトリに plan.md がありながら**解析不能**なもの(frontmatter ブロックが閉じない・8KiB 超・status 候補行数 ≠ 1・status 値不適合)は「**未取得(frontmatter 解析失敗)**」として text/hook 双方に表示する(無言で消さない — §1。健全な feature が併存しても互いの表示に影響しない)
- **git 取得失敗の出力契約**(3 周目 P2): `git worktree list` の失敗は「**進行中 feature: 未取得(worktree 列挙失敗)**」を出力(「0 件の正常」と区別する)。feature 単位の git 失敗(merge-base・log)は当該 feature の進捗を「**未取得(git 失敗)**」と表示。いずれも exit code は 0 のまま(fail-open — 表示で顕在化し、呼び出し元を殺さない)

### 3.2 現在地(stage)判定表

- **承認判定は実装ラッパーと同一**(2 周目 P1): `承認` の値が `済` で始まるか(codex_run.py:223-225 の `startswith("済")`。正文法 = `済(YYYY-MM-DD・承認者)` — plan-template.md:4)
- **ステップ進捗は 3 値**(2 周目 P1): `known(k)` / `unknown` / `inconsistent`(§3.3 で導出)

上から順に評価し、最初に該当した段階を表示する:

| 順 | 条件 | 現在地表示 |
| --- | --- | --- |
| 0 | `実行方式` キーが存在し値が `通常`・`fast` 以外(空値含む) | **未取得(実行方式不正)**(8 周目 P1 — stage 判定せず顕在化。無言で通常扱いにしない) |
| 1 | `status: in-review` | **PR 段階**(+ PR 状態: OPEN/MERGED/CLOSED/未取得 — §3.5) |
| 2 | `実行方式: fast` | **fast path 実装中**(計画書ゲート省略 — 人間事前 OK。7 周目 P1。表検証・ステップ進捗導出は適用しない — ステップ表なしが正当) |
| 3 | 承認が `済` で始まらない | **計画段階**(計画レビュー周回 n・承認待ちを併記。確定ゲート 1 周目 P1 — 差し戻し履歴より先に評価: fast → 通常へ降格した未承認 plan を「差し戻し修正」と誤表示しない) |
| 4 | **承認済み** かつ `status: active` かつ base..HEAD の履歴中に plan.md が `status: in-review` だったコミットが存在(= 直近の in-review → active が**未解消**) | **実装中(差し戻し修正)**(9 周目 P1 — k 判定より優先。全ステップ完了済みでも「実装完了・/pr 前」と誤表示しない) |
| 5 | 承認済み かつ 進捗 = unknown | **実装状況: 不明**(コミット規約未検出 — 実装前/完了と断定しない) |
| 6 | 承認済み かつ 進捗 = inconsistent | **実装状況: 不整合(要確認)**(欠番・範囲外・ステップ表なし) |
| 7 | 承認済み かつ known k = 0 | **実装前**(全 N ステップ) |
| 8 | 承認済み かつ known 0 < k < N | **実装中**(ステップ k/N 完了) |
| 9 | 承認済み かつ known k = N | **実装完了・/pr 前** |

- **差し戻し修正中の導出方法**(9/10 周目 P1 — 保存キーを増やさない): base(= `git merge-base origin/develop HEAD`)を一度求め、worktree 相対の plan パスで **`git -C <worktree> log --format=%H <base>..HEAD -- <plan_path>`** により**ブランチ内のコミットだけ**を列挙し、各時点のスナップショット **`git -C <worktree> show <sha>:<plan_path>`** の status 行を**既存の厳密 frontmatter パーサ(§3.1)**で読む。**ブランチ内に `in-review` の時点が存在し現在が `active`** なら行 3 に該当 — **base 側(origin/develop 以前)の履歴は走査しない**(過去タスクの in-review 痕跡による誤検出を防ぐ)。git 失敗時は既定どおり「未取得(git 失敗)」へ縮退(§3.1)。修正完了で `active → in-review` へ戻すと行 1(PR 段階)へ復帰する — これで往復遷移「PR 段階 → 実装中(差し戻し修正) → PR 段階」が全ステップ完了済みのケースでも成立する。subprocess は timeout 付き(§3.7)

- **差し戻しライフサイクルは往復で定義する**(7/8 周目 P1 — PR 状態を問わない。notion-map の review_rejected は CLOSED 限定ではない):
  - **差し戻し再開**(修正作業に入る — PR CLOSED でも OPEN の変更要求でも): **先に plan の `status: in-review → active` を戻す**(Notion は 進行中 へ)。無いと本表 1 行目により修正作業中も永続的に「PR 段階」と表示される
  - **修正・検証完了(再レビュー依頼)**: `active → in-review` へ戻す(Notion は 確認待ち へ)。**OPEN の既存 PR では `gh pr create` を行わず再レビュー依頼のみ**。CLOSED の場合は reopen または新 PR の手順による
  - この往復を /pr スキルの差し戻し節と設計書のライフサイクル記述(6.1/7.6-4)に新設する。状態更新コミット(plan.md のみ)は計画系コミット(§3.3)として進捗導出に影響しない。両経路の表示遷移(PR 段階 → 実装中 → PR 段階)をテストで固定する

- 完了(merged)は plan に置かない原則(設計書 6.1:260)のとおり、本判定の対象外 — マージ済み feature は worktree 除去により列挙から消えるのが正(7.6-4)
- `確定ゲート周回 > 0` の feature は段階表示に「確定ゲート n 周」を併記する

### 3.3 ステップ進捗の導出(実装ステップ表 × git log)

- **コミット件名の固定記法(1 周目 P1 — 既存慣行の規約化・3/4 周目 P1 で文法確定)**: ステップコミットの件名は**完全トークン** `(ステップ <k>[/<N>][ 付記])` を含む — 開き括弧(半角 `(` or 全角 `（`)+ `ステップ` + 整数 k + 任意の `/<N>` + 任意の付記(空白区切り)+ **同種の閉じ括弧**。例: `(ステップ 2/2)`・`(ステップ 4 周回 4)` — 従来慣行はいずれも適合。本タスクで設計書 6.1・/implement スキル・plan-template に明文化する
- **抽出は完全トークンのみ・不正形は顕在化**(3/4 周目 P1): 括弧を伴わない文言(例: `docs: ステップ 2 の補足`)や数値を含まない括弧書き(例: `(ステップ実行の見直し)`)は**不算入**(無視)。一方、「開き括弧 + ステップ + 数値」まで一致しながら**完全文法を満たさないもの** — 未閉止 `(ステップ 7`・括弧種不一致 `（ステップ 7)`・数値直後の非境界 `(ステップ 2abc)`・k = 0・トークン内 `/<N>` が表の N と不一致 `(ステップ 4/3)` — は **inconsistent**(黙って読み飛ばして誤算入・誤除外しない)
- **表の整合検証が最優先**(3 周目 P1): plan.md の「実装ステップ」見出し配下の表(見出し配下判定・3 セル判定は codex_run.py:57-73 と同一規則)について、**番号列が {1..N} の連番・重複なし・N ≥ 1** を検証する。不成立(N = 0・表番号の欠番/重複)→ **コミット数にかかわらず inconsistent**
- **1 コミット = 最大 1 トークン**(6 周目 P1): 各コミット件名に許容する完全トークンは**ちょうど 1 個**まで。1 件名に 2 個以上の有効トークン(例: `(ステップ 1/6) (ステップ 2/6)`)→ **inconsistent**(「1 委任 = 1 ステップ = 1 コミット」〔設計書 6.1:247〕に反する状態を黙認しない)
- **k(完了ステップ)の導出**: 表検証を通過した後、worktree で `git log <base>..HEAD`(base = `git merge-base origin/develop HEAD`)の件名から完全トークンを**全収集**した集合を S とし、進捗 3 値(§3.2 で使用)を決める:
  - 不正形トークン・複数トークン件名を 1 つでも検出 → **inconsistent**(前 2 項)
  - S = {1..max(S)} を連続で満たし max(S) ≤ N → **known k = max(S)**(同一 k の重複は**異なるコミット間に限り**正常 — 差し戻し再委任等)
  - 欠番・max(S) > N → **inconsistent**(黙って k を採用しない)
  - **コミット分類**(確定ゲート 1/2 周目 P1 で拡張): ①トークン付き ②**計画系**(変更パス 1 件以上・全件が当該 feature の `docs/features/<slug>/` + `docs/worklog/` 配下)③**文書系**(変更パス 1 件以上・全件が「`docs/` 配下」または「拡張子 `.md`」— `.claude`/`.github` の実行コード・設定〔`.py`・`.yml`・`.json` 等〕は含まない)④**develop 取り込みマージ**(2 親かつ第 2 親が origin/develop 系統 — `git merge-base --is-ancestor` で検証)⑤**実装系無記法**(コードパスに触れるのにトークンなし)⑥**不確実**(side branch マージ・diff-tree 取得失敗)。パス判定は `git diff-tree --no-commit-id --name-only -r`
  - **S 非空のとき**: ⑤⑥が 1 件でもあれば **unknown**(「不明(無記法の実装コミット混在 / 分類不能)」— 有効トークンがあっても素通りさせない)。①〜④は許容
  - **S が空のとき**(4/5 周目 P1 — 承認直後の通常経路を「実装前」と正しく導出する): ②③のみ → **known k = 0**(実装前 — 承認・起票・文書整備のみ)/ ④⑤⑥が 1 件でもある → **unknown**(保守的に誤 known(0) にしない)。base..HEAD が 0 件の場合も known k = 0
- **承認・起票コミットはステップ表の外**(5 周目 P1): 計画承認後の plan・research・design・worklog の起票コミットは /plan の承認後処理であり、実装ステップに数えない。**ステップ記法を付けない** = 計画系コミットとして進捗導出から除外され、直後の現在地は「実装前(全 N ステップ)」と表示される。最初の実装コミットが `(ステップ 1/N)` を持つ(採番の起点)

### 3.4 PR 状態(gh)

- `gh pr view <branch> --json state,url`(settings.json:21-24 で許可済みの範囲。`gh api` は使わない)
- subprocess timeout 10 秒(session_context.py:19-26 と同値)。gh 不在・非 0・タイムアウト → 「PR 状態: 未取得(縮退)」

### 3.5 Notion 照合(対話時のみ — スクリプトは API を呼ばない)

- 設計書 11.3(:624)により CI・ヘッドレスから Notion を使わない。**NFR-014 系の統制として自前トークンも持たない**(認証は対話セッションの MCP に委譲 — research.md §1)
- スクリプトの出力は**期待値まで**: 導出 stage → `.claude/notion-map.json` の `transitions` から期待ステータスを引き(ハードコード禁止・11.1)、`Notion 期待: 確認待ち(実値の照合は対話セッションで)` と表示。対応表(レビュー 1 周目 P1 — 綴りは表示時に notion-map.json から引く。下表の値は説明用):

  | 導出 stage(+PR 状態) | notion-map 遷移事象 | 期待ステータス |
  | --- | --- | --- |
  | 計画段階〜実装完了(`status: active`) | task_start | 進行中 |
  | PR 段階 + OPEN | pr_created | 確認待ち |
  | PR 段階 + MERGED(worktree 現存) | pr_created(**状態維持** — 新しい遷移事象は未発生) | 期待値は `transitions.pr_created.status` を map から引く(3 周目 P1 — 直書きしない)+ 表示に「**/task-done 待ち**」を併記。完了への遷移は /task-done が worktree 除去とともに行う(task-done/SKILL.md)ため、worktree 現存中に done 事象を期待値にすると正常運用を偽の不一致として表示する(2 周目 P1) |
  | PR 段階 + CLOSED(未マージ) | **判定不能** — review_rejected(差し戻し)か withdrawn(取り下げ)かは Git から導出不能 | 「人間判断(差し戻し or 取り下げ)」と表示 |
  | PR 状態 未取得(縮退) | — | 「未取得」 |

  notion-map.json が読めない・破損している場合も期待値を「未取得」とする(fail-open・無言縮退禁止)
- 実値照合は対話セッションの手順: Claude が MCP でタスクの実ステータスを取得し、期待値と突合。**不一致は表示で顕在化するのみで、Notion を書き換えない**(裁定規則は既存規定に無いため本計画で新設 — 7.1-5 の「黙ってどちらかが勝たせない」前例に整合)。人間運用に開放された 5 選択肢(未着手・準備中・保留中・着手可・作業中 — 設計書 :599-600)は「ハーネス管理外」と表示し異常扱いしない。6.4 例外の終端「PR closed + Notion 取り下げ」も正常終端として扱う

### 3.6 出力形式と縮退ラダー

| モード | 用途 | 内容 |
| --- | --- | --- |
| `--format text`(既定) | 人間・対話セッション | feature ごとに複数行(段階・ステップ・PR・Notion 期待・縮退注記) |
| `--format hook` | SessionStart(session_context.py から起動) | 1 feature = 1 行の要約。**git のみで導出**(gh・Notion 呼び出しなし — SessionStart を遅く・脆くしない) |

縮退ラダー: hook = git のみ → 対話 CLI(text)= git + gh → 対話セッション = + Notion 実値照合(Claude 手順)。全レベルで欠落項目は「未取得」表示。

### 3.7 実装制約

- **Python 標準ライブラリのみ**(hooks から起動されるため — 設計書 :383)・OS 非依存(`scripts/` の規約 — :150)・全 subprocess に timeout
- 失敗方針は **fail-open**(表示系。git/gh の失敗は該当項目「未取得」に縮退し、例外でフック・CLI を殺さない)。ガード系の fail-closed(core_guard 等)とは役割が異なる

## 4. session_context.py 改修

責務を一本化する(レビュー 1 周目 P1 — hook 側に frontmatter 読み取りを残さない):

1. **進行中 feature ブロック(:63-90)を削除**し、feature_status.py の起動に置換: `/usr/bin/python3 <repo>/scripts/feature_status.py --format hook --cwd <入力 JSON の cwd>`(スクリプトパスは hook 自身の `__file__` から解決・timeout 10 秒)。frontmatter 解析(8KiB 上限・切り詰めなし)は feature_status.py の**単一実装**(§3.1)— 800 文字問題はインライン実装の削除で解消し、同一判定の二重実装を作らない(NFR-018 の精神)
2. **縮退の統一**: 子プロセスの失敗・非 0 終了・timeout 時は「**進行中 feature: 未取得(導出失敗)**」を注入する(現行の無言省略をやめ、§1 の未取得明示原則に統一)。進行中 feature が 0 件の正常時は行を出さない(現行踏襲)
3. 出力は従来どおり**単一の additionalContext**(settings.json:95-104 は変更なし → 配線テスト test_hooks.py:56-69 は不変)
4. テスト: 正常注入(1 行要約が additionalContext に含まれる)/ 800 字超 frontmatter の feature 検出(回帰)/ 8KiB 超 frontmatter / 非ルート cwd / 子プロセス失敗・timeout → 「未取得(導出失敗)」

## 5. A 案: 3 ファイル役割分担

| ファイル | 役割 | 状態検査 |
| --- | --- | --- |
| plan.md | **契約**: frontmatter(状態・承認・拡張キー)+ 必須 6 節の骨格 + 実装ステップ表 + DoD | docs-lint(status 行 1 行)・codex_run.py 機構検証 |
| research.md | 調査メモ(/investigate・/research の統合先 — 既存のまま) | 無検査(現行どおり) |
| design.md | **詳細設計・検討メモ**(plan 4 節から相対リンク参照。補助資料枠 — 設計書 6.1:246) | 無検査(lychee のリンク整合のみ) |

- 不変条件(research.md §3)の遵守: **機構が読む状態**(status・承認・worktree・branch・重さ分類・拡張キー)と**実装ステップ表**は **plan.md のみ**に置き、design.md へ複製しない(7.1-1)。research.md・design.md の frontmatter は `feature / type / date` の 3 キーに限定し **`status:` 行を持たない**(2 周目 P2 — docs-lint・選別機構の検査対象は plan.md のみのため)。拡張キー欠落時は既定値 0 として扱う(後方互換 — テストで固定)
- テンプレ: `docs/development/templates/design-template.md` を新設(frontmatter は research-template と同形式の 3 キー)。plan-template.md 4 節に「詳細設計・長文の検討は design.md へ(相対リンク)」の導線を追記。docs/README.md のテンプレート一覧にも design-template を追記(レビュー 1 周目 P1)
- design.md は**任意**(小さな feature は plan.md だけでよい)。作成責務は /plan(計画時に肥大が見えた時点で分離)。/task-start には「design.md は任意 — 作成判断は /plan」を明記して追随漏れを防ぐ(レビュー 1 周目 P1)
- 本 feature 自身がこの構成の最初の実例(ドッグフーディング)
