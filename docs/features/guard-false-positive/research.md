# 調査: ガードの誤検知と fail-open(F1)

- 日付: 2026-08-15
- 対象: `.claude/hooks/git_guard.py` / `.claude/hooks/codex_guard.py` / `.claude/hooks/guard_common.py`
- 台帳項目: **H-2 / H-9 / H-10 / H-11**(すべて `追跡優先度: 高`・`状態: 未対応`)+ **H-17**(負例・故障系テスト 3 種 — `追跡優先度: 通常`)

**すべての事実は実測または `ファイル:行` の典拠つき。** 実測は `.claude/hooks/*.py` へ hook の JSON payload を直接与えて exit code を観測した(スクリプトは scratchpad)。

---

## 0. 調査中に踏んだ実例(4 件)

**本調査のコマンド自身が 4 回、誤検知でブロックされた。**

| # | 実行しようとしたもの | 遮断したガード | 機序 |
| --- | --- | --- | --- |
| 1 | `for cwd in ...; do ... git commit ...; done`(検証ループ) | `git_guard` | `cd` と git の複合と誤認 |
| 2 | `grep -iE 'git\|codex' tests/test_hooks.py` | `codex_guard` | **引用符内の `\|` でセグメントが分断され字句解析不能** |
| 3 | `git commit -m "..."`(本調査の結果をコミット) | `git_guard` | **メッセージ内の引用符で字句解析不能** — `-F <file>` へ切り替えて回避 |
| 4 | `cat > msg.txt <<EOF` … `EOF` + `git commit -F msg.txt`(コミットメッセージをファイル経由で書く) | `git_guard` | **ヒアドキュメント本文が `\n` で分割され、本文中の `git commit` という文字列がコマンドとして解析された**。`guard_common.effective_command` の heredoc 除外は**正規の Codex ラッパー呼び出しにしか効かない**(`:42-50`) |

いずれも**読み取り専用または検証目的**で、止める理由がない。**4 例目はとくに重い** — `git commit` を含むのは**データ(コミットメッセージ本文)**であって実行されるコマンドではない。`:113` の `re.split(..., "\n", ...)` がヒアドキュメント本文を行単位でセグメント化し、本文中の文字列を実コマンドと同列に扱っている。これは §3 で特定した「引用符を無視した分割」と**同じ根**(分割器がシェル構文を理解していない)である。台帳 H-2 の「**ガードが正しい操作を止めると迂回の習慣がつく**」が、F1 の調査中にそのまま再現した形になる。

---

## 1. H-9: fail-open(最優先 — 性質が他 3 件と異なる)

### 実測

| cwd | コマンド | rc | 判定 |
| --- | --- | --- | --- |
| `/home/ymdms/projects/pitchlog`(develop 上) | `git commit -m x` | **2** | 遮断される(期待どおり) |
| `/nonexistent-dir-xyz` | `git commit -m x` | **0** | **通る(fail-open)** |
| `/tmp`(git 管理外) | `git commit -m x` | **0** | 通る |

### 機序

`current_branch`(`.claude/hooks/git_guard.py:26-34`)は例外・非 0 終了で **`None`** を返す。判定は `:97` の

```python
if current_branch(cwd) in PROTECTED:
```

で、`None in {"main","develop"}` は **False** になるため**遮断されない**。

### 宣言との不一致

docstring(`.claude/hooks/git_guard.py:6`)は

> 判定不能な git は安全側でブロック。

と宣言している。しかし**安全側に倒しているのは字句解析失敗のときだけ**(`:67-70` の `tokens is None` 経路)。**ブランチ解決の失敗は判定不能ケースなのに fail-open** している。

### 判断材料

- `/tmp` のような **git 管理外**で通るのは妥当と解釈できる(保護ブランチという概念が無い)
- 一方 **`rev-parse` が例外・タイムアウト・非 0 で失敗したときに通る**のは、宣言とも 7.6-4 系の「判定不能は明示」の思想とも合わない
- **区別が必要**: 「git リポジトリではない(=保護対象なし)」と「git リポジトリだがブランチを解決できなかった(=判定不能)」を、現在の実装は**どちらも `None`** にして同一視している

---

## 2. H-2 / H-11: `git_guard` の過剰遮断

### 機序(共通)

`.claude/hooks/git_guard.py:94-98`:

```python
if VERBS & set(tokens):          # VERBS = {"commit","merge","push","rebase"}  (:23)
    ...
    if current_branch(cwd) in PROTECTED:
        return block("保護ブランチへの直接操作は禁止です。...")
```

**トークン集合に危険動詞が 1 語でも現れれば、コマンドの構造・宛先を一切見ずに遮断する。**

### 実測(カレント = `develop`)

| コマンド | rc | 本来の性質 |
| --- | --- | --- |
| `git log --grep merge` | **2** | **読み取り専用**(H-11) |
| `git log --grep=merge` | 0 | 同じ意味なのに通る |
| `git help push` | **2** | **ヘルプ表示**(H-11) |
| `git log --oneline -5` | 0 | — |
| `git push origin --delete feature/docs-check-hardening` | **2** | **保護ブランチに触らない push**(H-2) |
| `echo "git push; ls"` | **2** | **文字列であり実行しない** |

**`--grep merge` と `--grep=merge` で挙動が変わる**(前者は `merge` が独立トークンになる)。挙動が予測できない。

### 上段の検査との関係

`:76-85` は force push と保護ブランチ宛て refspec を**カレントブランチに関係なく**検査している。したがって `:94-98` は「**保護ブランチに触らない push**」を余分に落としている分だけ純粋に広い。

### 退行させてはならないもの(実測で確認済み)

| コマンド | rc | 理由 |
| --- | --- | --- |
| `git commit -m x`(develop 上) | 2 | 絶対規則 1 |
| `git push origin HEAD:develop` | 2 | 保護ブランチ宛て refspec |
| `git push --force origin feature/x` | 2 | force push |

---

## 3. H-10: `codex_guard` の誤遮断 — 台帳の記述より原因が広い

### 台帳の記述

> `codex` を含むセグメントが `shlex.split` できないだけで exit 2。**bash では正当な二重引用符ネストが shlex では解析不能になる**ため(`harness-evaluation.md` H-10)

### 実測: 引用符ネストでは再現しなかった

| コマンド | rc |
| --- | --- |
| `grep -n "it's codex" README.md` | 0 |
| `python3 -c "print('codex')"` | 0 |
| `awk '{print "codex"}' file` | 0 |
| `grep -c "codex_guard's" ...` | 0 |

**`shlex` は上記をすべて解析できる。** 台帳の原因記述は不正確。

### 実測: 真因は「引用符を無視したセグメント分割」

`.claude/hooks/codex_guard.py:103`:

```python
for seg in re.split(r"&&|\|\||\||;|\n|&", text):
```

**引用符の内側かどうかを見ずに分割する**ため、引用符内にセパレータがあると引用符が分断され、断片が `shlex` で解析不能になる。

| コマンド | 分割結果 | rc |
| --- | --- | --- |
| `grep -nE "codex\|claude" file` | `['grep -nE "codex', 'claude" file']` | **2** |
| `grep -E "codex_run\|codex_guard" AGENTS.md` | `['grep -E "codex_run', 'codex_guard" AGENTS.md']` | **2** |
| `grep -n 'codex; ls' README.md` | `["grep -n 'codex", " ls' README.md"]` | **2** |
| `echo "codex & background" > /tmp/x` | `['echo "codex ', ' background" > /tmp/x']` | **2** |
| `grep -n "codex" a.py && grep -n "codex" b.py` | 正常に 2 分割 | 0 |

**`git_guard` にも同じ分割がある**(`.claude/hooks/git_guard.py:113` — `re.split(r"&&|\|\||\||;|\n", command)`)。`echo "git push; ls"` が遮断されるのはこれが原因。

### 退行させてはならないもの(実測で確認済み)

| コマンド | rc |
| --- | --- |
| `codex exec 'do something'` | 2(生の codex 実行) |
| `python3 .claude/scripts/codex_run.py review normal -` | 0(正規ラッパー) |

---

## 4. 4 件の関係(修正の構造)

```
H-9  fail-open        ← current_branch が None を返す 2 つの理由を同一視している
H-2  過剰遮断(push)   ┐
H-11 過剰遮断(読取)   ┘← VERBS & set(tokens) がコマンド構造を見ていない(同一原因)
H-10 誤遮断(codex)    ← 引用符を無視したセグメント分割(git_guard にも同型あり)
```

- **H-2 と H-11 は同一原因**。台帳は別項目だが、`:94-98` の 1 箇所に集約される
- **H-10 の真因は分割器**であり `codex_guard` 固有ではない。`guard_common` へ**引用符を考慮した分割**を置けば両ガードで直る(NFR-018 — 同じ処理を 2 度書かない)

---

## 5. テストの現況

`tests/test_hooks.py` に **60 件**。内訳は git 関連 13 / codex 関連 4 / secret 関連 2。

台帳は F1 の完了条件として次を指定している:

- **3 種を分けてテストする**(`harness-evaluation.md` の H-2/H-11 対応案近傍 — 確定ゲート 2 周目 P1-4)
- **「止めてはいけないものを止めていないか」の負例を増やす**(同 566 行付近)

---

## 6. 決定経緯の追跡結果(decision-tracer + 原典確認)

### 6-1. 実装方針と完了条件は**既に確定済み**だった

`docs/worklog/2026-08-12-harness-evaluation.md:155-168`(F-ID の定義元)と台帳 H-17 の対応案(`harness-evaluation.md:430`)が、確定ゲート 2 周目 P1-4 で**実装方針とテストの 3 分割を確定させている**。

- **実装方針**: **サブコマンド位置(`git` の直後)のトークンだけを動詞として判定する**(対象動詞から `push` を外すだけでは `merge` の誤認が残る)/ **`current_branch` は fail-closed へ**(**docstring を実装に合わせて弱める案は取り下げ済み**)
- **テスト 3 種**(H-17 が F1 の完了条件に含まれる): **① H-2 用** = 保護ブランチ上からの正当な非保護 push が許可される / **② H-11 用** = 危険語が引数位置にある読み取り操作(`git log --grep merge`・`git help push`)が許可される / **③ H-9 用** = `current_branch` の解決失敗時に fail-closed(故障系)

**F1 の対象は 4 件ではなく 5 件**(H-2 / H-9 / H-10 / H-11 **+ H-17 の負例・故障系テスト 3 種**)。

### 6-2. fail-closed の一般規定は正本に**無い**。ただし判定は決着済み

設計書全文を走査した結果、fail-closed の**横断規定は存在しない**。個別ケースのみ(`:431` の `cd`+git / `:613`・`:36` の NFR-021 受入ゲート / `/research` の秘密走査)。`:36` の「判定不能はすべて fail-closed」は **10.1 NFR-021 の節の確定内容**でありガード hooks には掛からない。

ガード横断の宣言は**コードの docstring にのみ存在**する(`git_guard.py:6` / `guard_common.py:7-8` / `codex_guard.py:11` / `secret_guard.py:9`)。

**しかし台帳の運用規則(`harness-evaluation.md:50`)は docstring を制御目的の典拠として正式に認めており**、H-9 の対応方針は既に決着している(`harness-evaluation.md:342`):

> **ブランチ解決失敗を fail-closed にする**(確定ゲート 2 周目 P1-4 — 当初併記した「docstring を実装に合わせる」という**弱化案は F1 の fail-closed 方針と矛盾するため取り下げた**。docstring `:6` の宣言を正とする)

→ **設計書への fail-closed 規定の新設は不要**。docstring の宣言どおりに実装を直せばよい。

### 6-3. 【重要】設計書 2 箇所が「カレントベース」の文言 — **正本の節更新が必要**

**原典で確認済み。**

| 箇所 | 文言 |
| --- | --- |
| `dev-harness-design-2026-08-07.md:308`(6.2) | 「hooks が **main/develop 上での commit・push をブロック**」 |
| 同 `:431`(8.3 表・git_guard 行) | 「**保護ブランチ(main/develop)上での `commit`・`merge`・`rebase`・`push`** …を**ブロック**」 |

一方 `AGENTS.md:11`(絶対規則 1)が禁じているのは **main/develop という「宛先」への直接コミット・push** であって、保護ブランチに居るときの push 一般ではない。

**切り分け**:

- **規則の要求 = 宛先ベース** → `git_guard.py:76-85` の上段だけで既に満たされている(refspec 右辺・`refs/heads/` 剥がしまで判定済み)
- **実装の過剰 = カレントベースの一律遮断**(`:94-98`)→ commit / merge / rebase は「カレント = 宛先」なので妥当だが、**push は宛先が引数で決まるためカレント判定は宛先の代理にならない**

→ **H-2 の修正は設計書 `:308`・`:431` の literal な記述と食い違うため、節更新が要る。** 台帳・worklog のどちらにも「この記述を書き換える」決定は**見つからなかった(未決定)**。

**ゲート区分の判断材料**: 7.6-3 の決定表は「実装追随の節更新・変更履歴追記 = PR レビュー / 新設・版繰り上げ = 確定ゲート」。ただし台帳 **H-19**(`harness-evaluation.md:66`)が「**『節更新』で起案した判定が連続して確定ゲートへ覆っている**」と記録しているため、見立ては慎重にする。

### 6-4. 脅威モデル — 緩和の是非を測る基準

**宣言内容**(設計書の変更履歴 `:22`・`:26`、PO 承認済み): **誤操作 + 外部入力暴走まで。敵対的 AI のフル想定はしない。**

**hooks の位置づけ**(`:440`): 「hooks は『**Claude が誤ってやりかけた時に止まる**』ための層。規約の一次的な伝達は CLAUDE.md / AGENTS.md が担う」。

**過去の緩和 3 件はすべて承認されている**(v0.15 / v0.16 / v0.17)。共通する形は「**条件を単に外す**」のではなく「**判定の土台を精密化して、遮断すべき集合を保ったまま誤検知集合だけを削る**」。H-2/H-10/H-11 の確定済み対応案(サブコマンド位置判定・コマンド語位置判定)も**同じ形**である。

**否決・保留の前例 2 件**の判断基準は「**防御レイヤの後退になるか**」(`worklog/2026-08-07-wsl2-handover.md:104-105`)。H-2 の緩和は**多層の下位層が残る**(上段の宛先判定 / `settings.json:45` の force push deny / `:28` の push ask)ため、レイヤの後退にはあたらない。

### 6-5. 【新規発見】approved 正本内の不整合(未起票)

設計書 v0.17 の変更履歴(`:25`)は「**2段以上の shell ネスト・文字列難読化は脅威モデル外(12.1)と明記**」と述べているが、**12.1 本文(`:700` 以降)に「脅威モデル」も「2段」も存在しない**(全文 grep で確認 — 「脅威モデル」は変更履歴の 3 行のみ、「2段」は `:25` のみ)。

実在する明記先は**コードの docstring**(`codex_guard.py:9`)。**台帳に起票された記録は見つからなかった**。→ F1 の `/pr` クローズ処理で台帳への追記を判断する。

---

## 7. 要判断(PO 裁定)

| # | 論点 | 状況 |
| --- | --- | --- |
| 1 | **設計書 `:308`・`:431` の節更新のゲート区分** — PR レビュー(7.6-3 前段)か確定ゲート(後段)か | **未決定。着手前に裁定が要る**(H-19 の前例あり) |
| 2 | 「git 管理外」と「ブランチ解決失敗」を区別する実装方針(`rev-parse --is-inside-work-tree` の併用など) | 計画段階で決める |
| 3 | 引用符を考慮した分割の実装方針(`guard_common` へ集約 — NFR-018) | 計画段階で決める |
