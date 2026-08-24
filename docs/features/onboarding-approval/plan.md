---
feature: onboarding-approval
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-08-24・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3c593b75e6878129a772ea258c4aea3c
branch: feature/onboarding-approval
created: 2026-08-24
計画レビュー周回: 5        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 4          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: onboarding.md の完成と v1.0 approved 化(TSK-253)

## 1. 背景・目的

`docs/development/onboarding.md` は **正本 14 本のうち唯一の `draft`**(`docs/README.md:17`)であり、**NFR-021 受入(Phase 4-6)の前提**として approved 化が必要。

- Notion タスク: [TSK-253](https://app.notion.com/p/3c593b75e6878129a772ea258c4aea3c)
- 要件: **NFR-021**(`docs/requirements/requirements-pitchlog-2026-07-22.md:917-923`)/ **8 章 DoD⑦**(同 `:1004`「**approved かつ現行化された**開発者セットアップ手順」)/ **9 章 R-1**(同 `:1016`)
- 設計: **10.1 NFR-021 受入ゲート**の実施順序 ①(`docs/development/dev-harness-design-2026-08-07.md:638`)/ **13 章 4-6**(同 `:788`・`:808`)
- 調査: [research.md](research.md) — 本計画の判断はすべて同メモの典拠に依る

**なぜ「件数を直すだけ」で終わらないか**: 設計書 `:808` が 4-6 の成果物を「`onboarding.md` の**完成**と v1.0 approved 化(**実際の依存導入・DB 初期化・起動・疎通確認まで**)」と定義し、要件書 `:919` の受入プロファイルが「Windows ホスト側の事前導入は **WSL2 の有効化のみ**、その他の開発ツールは**すべて onboarding の手順内で導入する**」を要求しているため。現行 78 行では **Phase 4 の合格 5 項目のうち 4 項目が完走不可**([research.md](research.md) B-2)。

**確定ゲートの原則**(`docs/worklog/2026-08-11-req-v1-9-nfr021-wsl2.md:32`)により、既知の矛盾を未来ステップへ送ったまま approved にはできない。したがって本文の完成・受入プロファイルとの整合・波及追随・**13 章の衝突解消**を**すべて確定ゲートより前**に置く。

### 人間の裁定

| # | 日付 | 論点 | 裁定 |
| --- | --- | --- | --- |
| 1 | 2026-08-24 | 本タスクのスコープ | **本文の完成 + approved 化**。`win-setup` のランナー選定と Phase 4 受入判定そのものは 4-6 に残す |
| 2 | 2026-08-24 | 設計書 13 章への追随 | ~~追随なし(論理スロット解釈)~~ → **計画レビュー 1 周目 P1-1 で撤回**。下記 3 で再裁定 |
| 3 | 2026-08-24 | 13 章との衝突解消 | **13 章を改訂して先行を明文化する**。「onboarding の完成と approved 化は 4-6 の前提として先行 PR で実施する」を 13 章へ明記し、4-6 には `win-setup` 選定と受入判定を残す。**設計書は v1.9 として確定ゲートを通す**(本タスクの確定ゲートは 2 本になる) |
| 4 | 2026-08-24 | onboarding 本文での Docker Desktop の扱い | **言及しない**。WSL 内 Docker Engine の一本道にする(要件書 `:919`「Docker Desktop の事前導入は前提としない」に最も単純に従う) |
| 5 | 2026-08-24 | 確定ゲート 1 周目 P1-2 のスコープ | **スコープを拡張する**。`docs/ops/nfr021-acceptance/README.md` の実務手順へ前提 PR を挿入し、`.claude/skills/release/SKILL.md` の陳腐化表現も是正する。**README は確定ゲート対象**(10.1 `:649`)なので**本タスクの確定ゲートは 3 本**になる。規範(設計書)と実行用手順の不一致を残さないことを優先した |

#### 裁定 2 を撤回した理由(計画レビュー 1 周目 P1-1)

当初は設計書 `:819`「4-1 〜 4-6 は論理スロットであり、物理 PR 数ではない」を切り出しの根拠とした。しかし原文は続けて「**4-6 には 0 回以上の再試行 PR が属する**ため、実際の本数は**成功時 6 本**・再試行が n 回なら 6+n 本になる」と述べており、**再試行による増加を説明した文であって、前倒しの分割を許す文ではない**。

さらに `:808` は **4-6 のマージ条件を「`gate_kind: phase4` の判定に合格していること」**と定めているため、**4-6 を名乗る PR は受入合格まで develop へマージできない**。approved 化を受入より先に develop へ入れる本計画は、13 章側の明文化なしには成立しない。

### 計画レビュー 1 周目の指摘と反映(P1×5・全件採用・不採用 0 件)

| # | 指摘 | 検証 | 反映 |
| --- | --- | --- | --- |
| P1-1 | 4-6 からの切り出しの根拠が成立しない | 設計書 `:819` 原文と `:808` のマージ条件で**確認** | 裁定 3。ステップ 5〜8 で 13 章を改訂し確定ゲートを通す |
| P1-2 | 実 HEAD の approved 回帰ガードを外すのは誤り | `check_docs_status.py:830-836` は frontmatter と索引の**一致**しか見ず `draft` も許容 → **両方を draft に戻せば通る**ことを確認 | ステップ 10 で既存テストを**正例へ反転**。反転前に変異確認(H-81) |
| P1-3 | 索引の複数行更新が漏れており `docs-lint` が落ちる | `check_docs_status.py:705-713`「索引の最終更新が変更履歴表の最大日付より古い」で violation・`:830-836` で状態不一致が violation。**実装で確認** | 3 節で索引 4 行の更新を宣言。in-review 中間状態でも索引を同期する |
| P1-4 | 「CI と同じ手順」が実態と違う | backend CI = `uv sync --locked --dev`/`ruff check`/`ruff format --check`/`ty check`/`pytest --cov`、frontend CI = mise→`corepack enable`→`pnpm install --frozen-lockfile`/`eslint`/`prettier --check`/`vue-tsc`/`pnpm test -- --run` を **ci.yml で確認** | ステップ 3 で「NFR-021 の合格項目」と「CI 相当の品質検査」を**別節**として書き分ける |
| P1-5 | ステップ 4 の疎通条件が一意でない | backend は `/health` のみ・Vite proxy は `/api` 接頭辞を**残して** `:8800` へ転送 → `/api/health` は 404。`DATABASE_URL` は backend/src・tests から**参照 0 件**。すべて実測確認 | ステップ 4 に**実行契約**(コマンド・期待値・ポート・終了方法)を明記。`.env` 作成は人間の責務として切り分け |

あわせて指摘された 3 点も反映した: ①「backend pytest 2 件」「次番号 H-82」の**動的値を計画へ固定しない**(本計画の趣旨である固定件数排除と同型の誤り)② ステップの残存 `draft` 検証を**意味限定 grep + allowlist** の機械検証にする ③ Docker Desktop の扱いを**ゲートへ後送りせず裁定 4 で確定**。

### 計画レビュー 2 周目の指摘と反映(P0 なし・P1 4 系統が未閉鎖・全件採用)

**P1-4(CI との書き分け)のみ閉鎖。**残る 4 系統は、1 周目の反映が**浅かった**ために深掘りされたもの。

| # | 2 周目の指摘 | 検証 | 反映 |
| --- | --- | --- | --- |
| P1-1 | v1.9 は `:817`(順序)・`:819`(本数)まで改訂しないと矛盾する。先行 PR をスロット内外どちらに置くか・マージ順序・「6 本」の意味が未定義 | 設計書 `:817`「4-5 → 4-6」・`:819`「成功時 6 本」を**確認** | ステップ 5 の改訂対象へ `:817`・`:819` を追加し、**明記する 4 項目**と**維持する 2 規則**を条文レベルで指定 |
| P1-2 | **変異確認が現在の手順では成立しない**。対象テストは作業ツリーではなく **`HEAD` のコミットツリー**を読むため、ファイルを書き換えても変異が効かない | `tests/test_verify_nfr021_evidence.py:2405-2411` が `rev-parse HEAD` → `{sha}:docs/development/onboarding.md` を読むことを**確認**。`validate_onboarding_blob` も `git_tree_object_oid` 経由でコミットツリーを参照 | 変異確認を**一時コミット方式**へ全面変更(下記)。**本計画が守ろうとしている H-81 そのものを踏んでいた** |
| P1-3 | ステップ 9 が frontmatter と索引だけを `in-review` にし、**変更履歴表の行を追記していない**。`/finalize-doc` 手順 1 に反する。`check_docs_status.py` はこの誤りを検出しない | `.claude/skills/finalize-doc/SKILL.md:13`「対象の**変更履歴表**/frontmatter を `in-review` に更新する」/ `check_docs_status.py:694` 以降が状態・最大版・最大日付しか見ないことを確認 | 両書とも **`in-review` 行 → `approved` 行の 2 行方式**へ(前例: 要件書 `:20`・`:21`)。機構が検出しないため**人手確認**を合格条件に明記 |
| P1-5 | 実行契約に 6 件のシェル上の欠陥(ホスト側変数展開・`ps` は待機でない・`select 1` の出力非固定・curl 本文の破棄・`pnpm dev` のポート移動・環境変数の必須分類の誤り) | `docker-compose.yml:6-9` で `POSTGRES_PORT` に既定値 `:-5432` があること、`DATABASE_URL` が backend から**参照 0 件**であることを確認 | 実行契約の表を全面差し替え(コンテナ内展開・`--wait`・`-tAc`・本文照合・`--strictPort`・環境変数の 3 分類) |

### 計画レビュー 3 周目の指摘と反映(P0 なし・P1 2 系統が未閉鎖・全件採用)

**P1-3・P1-4・P1-5 は閉鎖を確認。**残る 2 系統はいずれも 2 周目の反映が浅かったもので、**うち 2 件は私の記述が事実として誤っていた**。

| # | 3 周目の指摘 | 検証 | 反映 |
| --- | --- | --- | --- |
| P1-1 | 条文契約が `:817`・`:819` だけでは閉じない。**`:778`「Phase 4 のみ分割」・`:780`「1 PR の例外は監査 PR だけ」・`:795`「8 系統」・`:812`「範囲は 4-1〜4-6 で閉じる」**とも衝突する | 4 条文すべてを**原文で確認** | 条文契約を**明記 4 項目 → 7 項目**へ拡張し、改訂対象へ `:778`・`:780`・`:812` を追加。**onboarding を成果物から前提へ移し 8 系統 → 7 系統**、前提 PR を**監査 PR に次ぐ第 2 の例外**として `:780` に追加、**本数の定義を「監査 PR と `P4-後` を除く、論理スロット + 前提 PR」**に確定 |
| P1-2 ① | 「一時コミットを作り `--amend` で元へ戻す」は**不正確**。`--amend` は親へ戻すのではなく**自分自身を置換**する | Git の仕様どおり。**私の記述の誤り** | ステップ 9 後を `B` とする **`F0` → amend → `F1` → amend** の 4 段手順へ差し替え。ステップ 9 以前を改変せず、最終履歴にステップ 10 が 1 本だけ残る形 |
| P1-2 ② | 正例が `REASON_ONBOARDING_STATUS not in reasons` では不足。**frontmatter が壊れると status 理由が積まれず誤って通る** | `verify_nfr021_evidence.py:2871-2875` の分岐(`status is None` → FRONTMATTER / `!= approved` → STATUS)を確認 | 正例の assert を **`reasons == ()`** に確定 |
| P1-2 ③ | 「4 要素のどれかを別コミットにすると必ず pytest が赤」は**誤り**。対象テストは onboarding blob しか読まないので、変更履歴だけ・索引だけの中間コミットは緑 | 指摘のとおり。**私の主張の誤り** | 分割禁止の根拠を **pytest から「状態同期規則 + docs-lint 整合」と「frontmatter と正例テストの相互依存」へ差し替え**(→ 4 周目でさらに訂正) |

### 計画レビュー 4 周目の指摘と反映(P0 なし・P1 2 系統・全件採用)

3 周目で閉鎖した P1-3・P1-4・P1-5 に**退行なし**を確認。残る 2 件はいずれも**狭い整合の問題**で、**2 件とも私の側の誤り**。

| # | 4 周目の指摘 | 検証 | 反映 |
| --- | --- | --- | --- |
| P1-1 ① | 順序 `4-5 → 前提 PR → 4-6` が、**10.1「Phase 4 のブートストラップ」(`:641`)が定める経路**と衝突する。`:641` が改訂対象に入っていない | `:641` に「予約は受入前に統合済み」「4-6 は受入合格時にのみマージ可」を含む経路規定があることを**確認** | 改訂対象を **8 条文 → 9 条文**へ(`:641` を追加)。明記項目 6 に「10.1 のブートストラップ経路にも同じ挿入を行う」を追記 |
| P1-1 ② | **ステップ 5 の行がまだ「明記 4 項目」「5 条文」のまま**で、下段の条文契約(7 項目)・DoD と食い違っている | plan.md の当該行を**確認** — **私の編集漏れ** | ステップ 5 を「**明記 7 項目・維持 2 規則・9 条文**」へ同期 |
| P1-2 | **「分割すると中間コミットで docs-lint が落ちる」も誤り**。`check_docs_status.py` は **変更履歴表の状態セルを照合しない**ため、変更履歴の `approved` 行だけを次コミットへ回す分割は通ってしまう | `check_docs_status.py:830`(状態一致)・`:694`(版・日付)の検査範囲を**確認** | 「**機構は分割を止めない**」ことを明記したうえで、分割禁止の根拠を**規律(人手 + `git diff`)と、frontmatter・正例テストの相互依存の 2 点に限定**。あわせて **`F0` 作成と 3 回の `--amend` は Claude が行い、Codex へ委任するのは正例テストの実装差分だけ**であることを明記(`codex_run.py implement` はコミットを作らない) |

## 2. スコープ

### やること

- `onboarding.md:72` の**固定テスト件数を除去**(設計書 8.3 `:464`「固定件数は腐るため書かない」への追随)と、同行の**射程記述の是正**
- **動作確認章を CI harness ジョブの現行へ追随**(pytest だけでなく `ruff check`・`ty check`)
- **受入プロファイルとの整合**: Ubuntu 26.04 LTS の番号付き x64 WSL イメージへの固定 / 新規ディストリビューションからの出発 / **Docker Desktop に言及しない WSL 内 Docker Engine 一本道**(裁定 4) / 「標準」「必須」の**「受入保証対象」への用語統一** / Node.js・Python の版表記の是正
- **本文の完成**: backend の依存導入と pytest / frontend(mise + pnpm)の導入と Vitest / 開発 DB の初期化・起動・接続確認 / backend・frontend の起動疎通
- **設計書 v1.9**: 13 章へ「onboarding の完成と approved 化は 4-6 の前提として先行 PR で実施する」を明記(裁定 3)+ `:475`・`:839` の draft 注記の解除 → **確定ゲート**
- **`github-setup.md:16` の draft 注記の解除**(版は上げない)
- **`tests/test_verify_nfr021_evidence.py:2403` を正例へ反転**(approved 化コミットと同一コミット)
- **`/finalize-doc` による onboarding の確定ゲート** → **`status: approved` / v1.0** / 変更履歴追記 / `docs/README.md` 索引の現行化
- 台帳 `harness-evaluation.md` の **H-79 へ本タスクの観測を 1 件追加**

### やらないこと

- **`win-setup` のランナー選定**(4-6 に残す — 裁定 1・3)
- **Phase 4 の受入判定(`gate_kind: phase4`)の実施**(4-6)。本タスクは実施順序 ① を満たすだけ
- **受入プロファイル上での完走試験**。本タスクの手順確認は既存 WSL2 環境で行うため、要件書 `:919` の「新規に作成した Ubuntu 26.04 LTS」ではなく**証跡にならない**
- **他の陳腐化しうる固定数値の予防的リファクタ**([research.md](research.md) F-1 の複製数値 6 群)。**すべて現在値と一致しており陳腐化していない**ため是正対象がない。腐らせない書き方への転換は台帳 `:1086`「(6)」の課題として別タスク
- `README.md:14`(要件定義完了 v2.0 — 実際は v2.2)・`requirements-draft-pitchlog.md:7`(D-1〜D-37 — 実際は D-44)の是正。**別文書**であり、後者は台帳 `:1092`「(8)」に起票済み・変更履歴表を持たない免除文書のため別ゲートが要る
- 履歴の書き換え(要件書 `:20`・`:21` の「draft のため」記述、worklog、完了済み feature の plan/research、各書の過去版変更履歴行 — 設計書 7.1-4)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/onboarding.md` | **全面改訂**(件数除去・射程是正・動作確認追随・受入プロファイル整合・用語統一・依存導入/DB/起動疎通の新章)+ **`draft` 0.5 → `approved` 1.0**・変更履歴に 1.0 行(0.1〜0.5 は原文保存) | **/finalize-doc**(版繰り上げ + 状態遷移 = 7.6-3 後段・設計書 `:638` が名指し) |
| `docs/development/dev-harness-design-2026-08-07.md` | **v1.9**: ① **13 章へ「onboarding の完成と v1.0 approved 化は 4-6 の前提として先行 PR で実施する」を明記**し、4-6 の定義から当該項目を外す(裁定 3)② `:475`(8.4 `/setup-dev`)・`:839`(14 章 論点C)の「同書は現在 draft — approved 化までは規範ではない」注記を解除 ③ 変更履歴に v1.9 行 | **/finalize-doc**(**4-6 のマージ条件の適用範囲を変える規範追加** = 7.6-3 後段。前例 `github-setup.md:14` v1.1「マージ可否の手続を変える規範追加であるため実装追随ではなく確定ゲートを通す」) |
| `docs/development/github-setup.md` | `:16` の draft 注記を解除 + 変更履歴表に 1 行(**版は上げない** — 7.6-3 前段) | PRレビュー(参照先の状態表記の是正。本書の内容・決定は不変 — 前例 `docs/features/req-v1-9-nfr021-wsl2/plan.md:90`) |
| `docs/development/harness-evaluation.md` | **H-79 へ本タスクの観測を 1 件追加**(2026-08-16 の `harness-design-review` が設計書 13 章の固定件数「103件」を除去した際、同じ「103件」を持つ `onboarding.md:72` を確認しなかった)+ 変更履歴表に 1 行(**`H-*` の追記・更新では版を上げない** — 前例 `:33`) | PRレビュー |
| `docs/README.md`(索引) | **4 行を更新**(P1-3): ① onboarding 行 → `**approved**(v1.0 …)` / 版 `1.0` / 承認日 ② 設計書行 → 版 `1.9` / 承認日(状態は in-review を経て approved へ)③ github-setup 行 → 最終更新を変更履歴の最新日へ ④ 台帳行 → 同左。**中間状態(in-review)でコミットする際も frontmatter・変更履歴の最新日と同期させる** | PRレビュー(各 /finalize-doc 手順 6 の一部を含む) |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし**。NFR-021 `:918`・DoD⑦ `:1004`・R-1 `:1016` は「approved な onboarding」を要求する条文であり、approved 化によって**充足側へ動くだけ**で文言変更は不要 | — |
| `docs/improvements-from-baseball-scoring.md`(改善台帳) | **反映なし**(I-* に onboarding への要求なし) | — |
| `docs/adr/ADR-001` / `ADR-002` / `ADR-003` | **反映なし** | — |
| `docs/ops/nfr021-acceptance/README.md` | **スコープ拡張(裁定 5 — 確定ゲート 1 周目 P1-2)**: 「Phase 4 のブートストラップ手順」の番号付き手順へ **Phase 4 完了時受入の前提 PR を挿入**する(現行は `4-5` → `4-6` で前提 PR を飛ばしている)。**同書は「規範として競合した場合は設計書が優先する」と宣言しているが、実行用手順が旧経路のままでは別経路が残る**(H-79 の同型) | **/finalize-doc**(10.1 `:649` の文書分類が `README.md` とテンプレートを**確定ゲート対象**と定める。**本タスクの確定ゲートは 3 本目**) |
| `docs/ops/nfr021-acceptance/` のテンプレート 3 件 | **反映なし**(証跡の様式は変わらない) | — |
| `.claude/skills/release/SKILL.md` | **スコープ拡張(同上)**: 「`gate_kind: phase4` の受入判定は…**Phase 4 PR 上**で」を、**v1.8 で廃止した曖昧表現**のため「**受入を実施する 4-6 の PR 上**」へ是正する | PRレビュー(正本ではない。設計書 v1.8 の既存規範への追随) |
| `.claude/nfr021-invalidating-paths.json` | **`description` のみ更新**(ステップ 7 — 確定ゲート 2 周目 P1-3)。「読み手 = `verify_nfr021_evidence.py`(Phase 4-5 で**実装予定**)」を**実装済み**へ。**規則(`default`・`invalidating`・`allowlist`)は変更しない**(`:9` に既に `onboarding.md` を含む — 確認のみ) | PRレビュー(正本ではない。実装追随) |
| `.claude/skills/setup-dev/SKILL.md` / `.claude/scripts/codex_run.py` | **反映なし**(正本ではない。`SKILL.md:12,19`・`codex_run.py:193` の onboarding 参照は「配置先」を指すのみで draft 前提の語がないことを確認する) | — |

## 4. 実装方針

**重さ分類 = 通常**の根拠:

- **コア領域に触れない**。CLAUDE.md が列挙する 5 領域(同期プロトコル / 状況計算 / 記録権 / テナント分離 / データ移行)のいずれにも該当しない。変更対象は開発者向け手順書・プロセス設計文書・NFR-021 検証器のテスト 1 本で、製品ドメインのロジックを含まない。機械可読の正 `.claude/core-areas.json` は **全 5 領域の `paths` が空**(実測 — Phase 4 で埋める前提。台帳 H-12)なので `core_guard` も発火しない
- **軽微ではない**。approved 正本 **5 本**(onboarding・設計書・github-setup・台帳・**受入証跡 README**)へ波及し、**確定ゲートを 3 本**通す(確定ゲート 3 周目 P1-2)
- **機械的軽作業でもない**。本文の新章は受入プロファイルの制約を満たすよう設計判断を伴う

**役割分担**: ドキュメントは Claude が直接書く(CLAUDE.md「Git 操作・PR・ドキュメントは Claude の役割」)。**ステップ 10 は `tests/` の実装コードを含むため `/implement`(Codex 委任)で行う**。

**design.md は作らない**。本文の設計判断は受入プロファイル(要件書 `:919`)と合格 5 項目(同 `:921`)から一意に決まり、長文の検討を要しない。

### 順序の制約(必ず守る)

1. **設計書 13 章の改訂とそのゲート(ステップ 5・7・8)は onboarding のゲート(ステップ 9)より前**。先行 PR を許す規範が立ってから onboarding を approved にする。前例 `docs/worklog/2026-08-11-req-v1-9-nfr021-wsl2.md:126`「波及追随を両方の確定ゲートより前へ」
2. **確定ゲートは「レビュー対象の現状態を approved にできるか」を判定する**(同 `:32`)。既知の矛盾を未来ステップへ送らない
3. **テストの反転(ステップ 10)は approved 化と同一コミット**。`tests/test_verify_nfr021_evidence.py:2403` は実 HEAD の onboarding が approved **でない**ことを assert しており、approved 化すると必ず落ちる(実測確認済み — [research.md](research.md) D-3)。`draft`・`in-review` の間は落ちないので、ステップ 9 までは触らない
4. **状態を変えるコミットでは frontmatter・変更履歴・索引を同一コミットで同期**する(P1-3)。`check_docs_status.py` は状態不一致(`:830-836`)と索引日付の遅れ(`:705-713`)をいずれも violation にする
5. **本 PR が develop へ統合されてから 4-6 の受入が始まる**。`onboarding.md` は失効対象パス(`.claude/nfr021-invalidating-paths.json:9`)、**`tests/` も失効対象**なので、**受入の `tested_commit_sha`(T)を採る前に本 PR の全変更を統合する**(設計書 `:646`)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **数値・射程の是正と動作確認章の追随** — `:72` の「(hooks・ラッパーの正負テスト **103 件**)」を、設計書 8.3 `:464` の既定方針どおり**固定件数を書かない**表現へ置換(設計書 `:785` の前例に倣い「件数は CI harness ジョブの実行結果を正とする」を参照する形)。あわせて**射程の是正**(`tests/` のうち hooks は `test_hooks.py` のみで、残りは `scripts/` の検査)。動作確認章へ **`uv run ruff check .`・`uv run ty check`** を追加(CI harness ジョブの現行 — `AGENTS.md:31`) | `rg -n '103[[:space:]]*件' docs/development/onboarding.md` が **0 件** / 同ファイルに「hooks・ラッパーの正負テスト」という射程限定の表現が残っていない / **本文に `tests/` の本数・件数を主張する固定数値が存在しない**(`rg -n '[0-9]+\s*(件\|本\|個)' docs/development/onboarding.md` のヒットを 1 件ずつ分類し、テスト規模を主張するものが 0)/ 動作確認章に `ruff check`・`ty check` が現れる / `uv run python scripts/check_docs_status.py` exit 0 |
| 2 | **受入プロファイルとの整合** — `:15` の「WSL2(**Ubuntu 推奨**)を**標準とする**」を要件書 `:919` の受入プロファイル(**Ubuntu 26.04 LTS の番号付き x64 WSL イメージ**・既定名 `Ubuntu` は保証対象外)へ。**「標準」「必須」の混在を「受入保証対象」に統一**(v1.9 確定ゲート 1 周目 P1-5 の申し送り — `docs/features/req-v1-9-nfr021-wsl2/plan.md:76`)。**新規ディストリビューションの作成手順**を 0 章へ追加。`:32` の Docker 行を **WSL 内 Docker Engine の導入手順一本**へ(**Docker Desktop に言及しない** — 裁定 4)。`:33` の「Node.js 20+(実装フェーズからは mise + pnpm)」を `mise.toml`・`packageManager` の実体へ。`:31` の「Python 3.12+」を backend の `>=3.12,<3.13` と整合する表記へ | `rg -n 'Ubuntu 推奨\|標準とする' docs/development/onboarding.md` が 0 件 / `rg -n '26\.04' docs/development/onboarding.md` がヒット / **`rg -ni 'docker desktop' docs/development/onboarding.md` が 0 件**(裁定 4)/ `mise` と `pnpm` が前提ツール表に行として存在 / **Node・Python の版表記が `mise.toml` と `backend/pyproject.toml` の実値と一致**(目視突合)/ `check_docs_status.py` exit 0 |
| 3 | **本文の完成 ① — 依存導入** — 「WSL2 有効化のみを前提に、その他はすべて手順内で導入する」形へ。**NFR-021 の合格項目**(backend: `uv sync --locked --dev` → `uv run pytest` / frontend: mise → `corepack enable` → `pnpm install --frozen-lockfile` → `pnpm test -- --run`)と、**CI 相当の品質検査**(backend: `ruff check`・`ruff format --check`・`ty check`・`pytest --cov` / frontend: `eslint`・`prettier --check`・`vue-tsc --noEmit`)を**別の節として書き分ける**(P1-4 — 前者だけが受入の合格項目) | 既存 WSL2 環境で本文どおりに実行して **backend の pytest と frontend の Vitest がともに green**(**件数は記録せず結果だけを記録する** — 本タスクの趣旨)/ 品質検査節のコマンド列が `.github/workflows/ci.yml` の backend・frontend ジョブと**一致**(1 コマンドずつ突合)/ **受入の合格項目と品質検査が本文上で明確に分離**されている / `check_docs_status.py` exit 0 |
| 4 | **本文の完成 ② — DB 初期化・起動・疎通(実行契約つき)** — 下記「疎通の実行契約」の表をそのまま手順化する。`.env.example` から環境変数ファイルを作る手順(**必須 3 変数・既定値あり 1 変数・現時点で未使用 1 変数**の分類は下記表のとおり — P1-5)→ 起動 → DB 接続確認 → backend・frontend の起動と疎通 → **終了手順**。`dev-db-contracts` の申し送り(やり直しにはボリューム再作成が要る — `docs/features/dev-db-contracts/plan.md:155`)を反映。**`DATABASE_URL` は現時点で backend から参照されていない**ため、DB 接続確認は DB コンテナに対して行い、その旨を本文に注記する | 下記実行契約の**4 項目すべてが期待値どおり**(実測・応答を worklog に記録)/ **`/api/health` を疎通条件に使っていない**(Vite proxy が接頭辞を残すため 404)。**検証は意味限定で行う** — `rg -n 'curl.*api/health' docs/development/onboarding.md` が 0 件(**裸のゼロ件検査にしない**: 「`/api/health` は使わない」という注記自体は読者の誤用を防ぐため本文に置く。ステップ 6 の `draft` と同じ理由 — 実施中に判明し是正)/ `docs/ops/nfr021-acceptance/evidence-phase4-template.md` の合格項目表の各行に対応する手順が本文に存在(項目単位で突合)/ **`.env` の内容をコミット・ログ出力しない**(AGENTS.md 絶対規則 2)/ `check_docs_status.py` exit 0 |
| 5 | **設計書 v1.9 の起案** — 下記「13 章改訂の条文契約」の**明記 7 項目・維持 2 規則**を反映し、**9 条文**(`:641`・`:778`・`:780`・`:788`・`:795`・`:808`・`:812`・`:817`・`:819`)を整合させる(P1-1)。あわせて ② `:475`・`:839` の draft 注記を解除 ③ 変更履歴に **`1.9` / 状態 `in-review` の行**を追記(**v1.8 以前は原文保存**)④ frontmatter を `in-review` へ ⑤ **索引の設計書行を `in-review` / 版 1.9 / 起案日へ同時更新**(P1-3) | 下記条文契約の**明記 7 項目がすべて反映されている**(13 章 8 条文 + 10.1 の `:641`)**し、**維持 2 規則が改変されていない**(項目単位で突合)/ `:808` の 4-6 定義に onboarding の approved 化が残っていない / **`:817` の順序に先行 PR が位置づけられている** / **`:819` の「6 本」がスロット数か全 PR 数かが一意** / **意味限定 grep**: `rg -n 'draft' docs/development/dev-harness-design-2026-08-07.md` の全ヒットを分類し、**残ってよいのは①状態語彙の定義・列挙 ②過去版の変更履歴行 ③ onboarding 以外の文書の状態記述**のみ(allowlist を worklog に記録し、それ以外が 0 件)/ **変更履歴に `1.9` 行があり状態セルが `in-review`**(人手確認 — 機構は検出しない)/ frontmatter と索引がともに `in-review`・版 1.9 で `check_docs_status.py` exit 0 |
| 6 | **`github-setup.md` の追随** — `:16` の draft 注記を解除 + 変更履歴表に 1 行(**版は上げない**)+ **索引の github-setup 行の最終更新を変更履歴の最新日へ同期**(P1-3)。あわせて `.claude/skills/setup-dev/SKILL.md:12,19` と `.claude/scripts/codex_run.py:193` に draft 前提の語がないことを確認(変更なしの見込み) | 意味限定 grep(ステップ 5 と同じ分類基準)で `github-setup.md` に onboarding を draft と述べる記述が 0 件 / 索引の github-setup 行の版セルが**未変更**・最終更新が変更履歴の最新日と一致 / `check_docs_status.py` exit 0 / `uv run pytest tests/` 全 green(skills を確認するため回帰) |
| 7 | **実装追随: `.claude/nfr021-invalidating-paths.json` の `description`**(確定ゲート 2 周目 P1-3・3 周目 P1-1)— 「読み手 = `verify_nfr021_evidence.py`(Phase 4-5 で**実装予定**)」を**実装済み**へ。**確定ゲートの反映周コミットに混ぜない**(同ファイルは `.md` でも `docs/` 配下でもないため `feature_status.py` が実装コミットと分類し、現在地導出が壊れる — 実測で確認)。`/finalize-doc` も「指摘反映でコード修正が要るなら `/implement`」と定めている | `rg -n '実装予定' .claude/nfr021-invalidating-paths.json` が 0 件 / `python3 -c 'import json;json.load(open(...))'` が成功(JSON 構文)/ `uv run pytest tests/test_nfr021_invalidating_paths.py` green / **`uv run python scripts/feature_status.py` の進捗が「不明」にならない** |
| 8 | **設計書の確定ゲート** — `/finalize-doc docs/development/dev-harness-design-2026-08-07.md`。**指摘反映を伴う周ごとに 1 コミット**(件名に `反映<r>周目`・**ステップ記法を付けない**)し、その都度 `確定ゲート周回` を +1 | 収束記録(採用/不採用の一覧)が worklog にある / `反映<r>周目` コミットが `{1..確定ゲート周回}` と**集合として**一致(設計書 `:295`)/ **人間の承認を明示的に取得** |
| 9 | **設計書の approved 化** — **同一コミットで** frontmatter を `approved` / 変更履歴表に **`1.9` / 状態 `approved` の行**を実承認日で追記(**ステップ 5 の `in-review` 行は原文保存** — 前例: 要件書 `:20`・`:21` の 2 行方式)/ **索引の設計書行を `approved`・版 1.9・承認日へ** | frontmatter がちょうど 3 行で `approved` / 索引 3 セルが frontmatter・変更履歴最新行と一致し `check_docs_status.py` exit 0 / **`1.9` の行が 2 行(in-review / approved)ある**(人手確認)/ **v1.8 以前の変更履歴行が未変更**(`git diff` で確認) |
| 10 | **受入証跡 README の確定ゲート** — `/finalize-doc docs/ops/nfr021-acceptance/README.md`(**v1.1**。ステップ 7 の反映で既に `in-review` 行・frontmatter・索引は同期済み)。反映ループはステップ 7 と同じ | 収束記録が worklog にある / `反映<r>周目` コミットが `確定ゲート周回` と**集合として**一致 / **人間の承認** |
| 11 | **受入証跡 README の approved 化** — **同一コミットで** frontmatter を `approved` / 変更履歴へ **`1.1` / `approved` 行**を実承認日で追記(`in-review` 行は原文保存)/ **索引の当該行を `approved`・版 1.1・承認日へ** | frontmatter がちょうど 3 行で `approved` / 索引 3 セルが一致し `check_docs_status.py` exit 0 / **`1.1` の行が 2 行(in-review / approved)ある**(人手確認) |
| 12 | **onboarding の確定ゲート** — `/finalize-doc docs/development/onboarding.md`。開始時に **①変更履歴表へ `1.0` / 状態 `in-review` の行を追記 ② frontmatter を `in-review` ③ 索引の onboarding 行を `in-review` / 版 `1.0` / 起案日へ**、の 3 点を**同一コミットで**行う(P1-3 — `/finalize-doc` 手順 1 は**変更履歴表も**対象)。以降はステップ 7 と同じ反映ループ | **変更履歴表に `1.0` / `in-review` 行がある**(人手確認 — `check_docs_status.py` は状態・最大版・最大日付しか見ないため検出しない)/ ステップ 7 と同じ(収束記録・周回カウンタの集合一致・人間承認)/ **in-review 中の各コミットで `check_docs_status.py` exit 0** |
| 13 | **onboarding の approved 化 + テストの正例反転(`/implement` — Codex 委任)** — 下記「ステップ 10 の実行手順」に従い、**単一の未 push コミット**として: ① frontmatter を `status: approved` ② 変更履歴表に **`1.0` / `approved` 行**を実承認日で追記(**0.1〜0.5 と `in-review` 行は原文保存**)③ 索引の onboarding 行を `**approved**(v1.0 …)` / 版 `1.0` / 承認日へ ④ `tests/test_verify_nfr021_evidence.py:2403` の `test_real_repository_onboarding_draft_is_not_approved` を、**実 HEAD が approved であることを assert する正例へ反転**(名称も実態に合わせる。合成負例 `:2208`・`:2225` は変更しない)。**分割しない**(理由は下記) | 下記「ステップ 10 の実行手順」の **4 段すべてを実施**し、**双方向の変異確認がいずれも赤を観測**している(観測できなければ変異が無効なので手順を見直す — H-81)/ frontmatter がちょうど 3 行で `approved`(設計書 7.1-5)/ 索引 3 セルが一致し `check_docs_status.py` exit 0 / **v0.1〜v0.5 と `in-review` 行が未変更**(`git diff`)/ **コミット後の HEAD に対して** `uv run pytest tests/` 全 green / `uv run ruff check .`・`uv run ty check` exit 0 |
| 14 | **台帳への追記** — `docs/development/harness-evaluation.md` の **H-79 の「事象」へ観測を 1 件追加**(2026-08-16 の `harness-design-review` が設計書 13 章の「103件」を除去した際、**同じ「103件」を持つ `onboarding.md:72` を確認しなかった**)+ 「再発」件数の更新 + 変更履歴表に 1 行(**`H-*` の追記・更新では版を上げない**)+ **索引の台帳行の最終更新を同期**(P1-3) | H-79 の事象・再発が更新されている / 台帳の frontmatter・索引の版セルが**未変更** / 索引の最終更新が変更履歴の最新日と一致し `check_docs_status.py` exit 0 / **新規 `H-*` を起こす場合は、その時点の develop と全 OPEN PR の最大値を確認してから採番する**(台帳 H-77。**番号を本計画に固定しない**) |

### 13 章改訂の条文契約(ステップ 5 — P1-1)

**改訂対象の条文(9 件)**: **`:641`**・`:778`・`:780`・`:788`・`:795`・`:808`・`:812`・`:817`・`:819`(`:778`・`:780`・`:812` は 3 周目 P1-1 で、**`:641` は 4 周目 P1-1** で追加)

**明記する 7 項目**:

| # | 明記事項 | 対象条文 |
| --- | --- | --- |
| 1 | onboarding 先行 PR は **`4-1`〜`4-6` の論理スロットの外**に置く(新しいスロット番号を与えない)。呼称は「**Phase 4 完了時受入の前提 PR**」 | `:808`・`:812` |
| 2 | **`:780` の「1 PR」の例外へ第 2 の例外として前提 PR を追加**する。現在の例外は**監査 PR(予約レコード PR・失敗閉塞 PR)だけ**であり、前提 PR を明記しないと `:778`「Phase 4 のみ分割」と衝突する | `:778`・`:780` |
| 3 | **onboarding を Phase 4 の「成果物」から「前提」へ移す**。`:795` の **8 系統を 7 系統へ**(`onboarding.md` の v1.0 化を除く)、`:788` の成果物欄からも外す | `:788`・`:795` |
| 4 | 前提 PR は **監査 PR でも `P4-後` でもない**。マージ条件は「**通常 PR 要件 + 本 PR に含まれる確定ゲート**」— **同 PR に含まれる確定ゲート対象の正本はすべて approved 化してからマージする**(onboarding v1.0 / 設計書 v1.9 / **受入証跡 README v1.1** の **3 本** — 確定ゲート 2 周目 P1)。、**`gate_kind: phase4` の判定は課さない**(課すのは 4-6 だけ) | `:780`・`:808`・`:812` |
| 5 | 同 PR は **4-6 の受入開始前に `develop` へマージ済み**であること(`onboarding.md` は失効対象パスであり、T を採った後に触れば証跡が失効するため) | `:808`・`:817` |
| 6 | 順序は **`4-5` → Phase 4 完了時受入の前提 PR → `4-6`**。**10.1「Phase 4 のブートストラップ」が定める経路(`… → 4-5 → 4-6`)にも同じ挿入を行う**(4 周目 P1-1 — `:817` だけ直すと 10.1 と衝突する) | `:817`・**`:641`** |
| 8 | 本数は「**監査 PR と `P4-後` を除く、論理スロット + 前提 PR の数**」と定義し、**成功時 7 本**・4-6 の再試行が n 回なら **7+n 本**。**監査 PR はブートストラップと失敗閉塞で可変なので「物理 PR 総数」は固定しない** | `:819` |

**維持する 2 規則**(改変しない — レビュー 2 周目が明示・3 周目が再確認):

| # | 維持事項 |
| --- | --- |
| A | **10.1 の実施順序 ①〜④**(`:638`)。① approved 化 → ② その版で完走 → ③ 証跡コミット(T)→ ④ 判定 |
| B | **`gate_kind: phase4` を実施し、合格後にのみマージできるのは 4-6 だけ**(`:808` のマージ条件)。**`P4-後` が Phase 4 の成果物ではない**という `:812` の再分類も維持する |

### ステップ 10 の実行手順(P1-2 — 計画レビュー 3 周目で再修正)

**なぜ作業ツリーの書き換えでは駄目か**: 対象テストは `git rev-parse HEAD` → `{sha}:docs/development/onboarding.md` で **コミットツリーの blob** を読む(`tests/test_verify_nfr021_evidence.py:2405-2411`)。`validate_onboarding_blob` も `git_tree_object_oid` 経由でコミットツリーを参照する(`scripts/verify_nfr021_evidence.py:2841`)。**したがってファイルを編集しただけでは変異が一切効かない** — 「落ちない」を観測しても変異が無効だっただけ、という H-81 の空振りになる。

**また、正例へ反転したテストはコミット前に必ず赤くなる**(旧 HEAD の onboarding は `in-review` のため)。「検証してからコミットする」通常手順が成立しない。

**ステップ 9 後のコミットを `B` として、以下の 4 段で行う**。`--amend` は**常に自分自身**を置換するので、子コミットを作ってから amend しても `B` の状態には戻らない(3 周目 P1-2 — 2 周目の反映時に私が誤っていた点):

| 段 | 実施内容 | 確認 |
| --- | --- | --- |
| 1 | onboarding の frontmatter・変更履歴・索引を **approved の最終形**へ更新し、**旧テストのまま**、未 push の暫定コミット **`F0`** を作る | **旧テストを名指しで実行して赤**(`uv run pytest tests/test_verify_nfr021_evidence.py::test_real_repository_onboarding_draft_is_not_approved`)。赤くならなければ旧テストは既に空振りしていたので手順を見直す |
| 2 | 正例テストへ反転(`assert reasons == ()`)し、**`F0` 自身を amend** して **`F1`** にする | **全テスト緑**(`uv run pytest tests/`) |
| 3 | `F1` の onboarding を **`draft` に戻して `F1` 自身を amend** する | **新テストが赤**(逆向きの変異確認) |
| 4 | `approved` に戻して**再度 amend** し、全検査と差分確認を行う | `uv run pytest tests/` 全緑 / `check_docs_status.py` exit 0 / `ruff check`・`ty check` exit 0 / `git diff B..HEAD` が意図した 4 変更のみ |

この形なら **ステップ 9 以前や push 済みの履歴を改変せず**、最終履歴に残るステップ 10 のコミットは **1 本だけ**になる。

**正例の assert は `reasons == ()` にする**(3 周目 P1-2)。`REASON_ONBOARDING_STATUS not in reasons` だけでは、**frontmatter が壊れた場合に `REASON_ONBOARDING_FRONTMATTER` が積まれて status 理由が消え、誤って通る**(`scripts/verify_nfr021_evidence.py:2871-2875` の分岐)。

**ステップ 10 を分割しない理由**(3 周目・4 周目 P1-2 で根拠を 2 度差し替えた):

まず、**機構は分割を止めない**。この点を正確に押さえる:

- ~~中間コミットで必ず pytest が赤くなる~~ は**誤り**(3 周目)。対象テストは onboarding blob しか読まないので、**変更履歴だけ・索引だけの中間コミットでは pytest は緑**
- ~~中間コミットで docs-lint が落ちる~~ も**誤り**(4 周目)。`check_docs_status.py` は **frontmatter と索引の状態一致**(`:830`)と**索引の版・日付が変更履歴の最大値と整合するか**(`:694`)しか見ず、**変更履歴表の状態セルは照合しない**。したがって「frontmatter・索引・正例テストだけを approved 側へ進め、変更履歴の `approved` 行を次コミットへ回す」分割は **docs-lint を通ってしまう**

**機構で止まらないからこそ、規律として守る**。分割しない根拠は次の 2 つに限る:

1. **本計画自身の状態同期規則**(4 節「順序の制約」4)と **`/finalize-doc` の履歴要件**を、**人手と `git diff` で守る**(機械検証に頼れない — H-1 と同型)
2. **frontmatter と正例テストは相互依存**する(どちらか片方だけのコミットは必ず赤)。ここだけは機構が止める

**コミットの作成者は Claude**(4 周目 P1-2)。`codex_run.py implement` はコミットを作らず、コミットはステップごとに Claude が作る(AGENTS.md「コミットはステップごとに Claude が作成する」)。したがって **`F0` の作成・3 回の `--amend`・変異の適用と復元はすべて Claude が実施**し、Codex へ委任するのは**正例テストの実装差分だけ**。

### 疎通の実行契約(ステップ 4 — P1-5)

**実測で確認した前提**: backend のエンドポイントは `/health` のみ(`backend/src/pitchlog/main.py:8`)。Vite の proxy は `/api` を**接頭辞を残したまま** `http://localhost:8800` へ転送する(`frontend/vite.config.ts:21-25` — rewrite なし)ため **`/api/health` は 404**。`DATABASE_URL` は `backend/src`・`backend/tests` から**参照 0 件**(実測)。

**環境変数の分類**(`docker-compose.yml:6-9` の実測 — P1-5):

| 分類 | 変数 |
| --- | --- |
| **Compose に必須**(`:?required` で未設定なら起動しない) | `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` |
| **既定値あり**(未設定でも動く) | `POSTGRES_PORT`(`:-5432`) |
| **現時点で未使用** | `DATABASE_URL`(`backend/src`・`backend/tests` から参照 0 件 — 実測。将来 backend が使う前提の予約) |

| # | 合格項目 | コマンド | 期待値 | 備考 |
| --- | --- | --- | --- | --- |
| 1 | 開発 DB へ接続 | `docker compose up -d --wait --wait-timeout 120` → `docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select 1"'` | `--wait` が healthy を待って終了コード 0 / `psql` の**標準出力がちょうど `1`** | **変数はコンテナ内で展開する** — 環境変数ファイルは Compose の変数展開に使われるだけで**呼び出し元シェルへ export されない**ため、ホスト側 `"$POSTGRES_USER"` は空になる(P1-5)。`docker compose ps` は待機ではないので `--wait` を使う。`-tAc` で出力を固定する。**backend 経由ではなく DB コンテナに対して確認する**(backend は `DATABASE_URL` 未使用 — この事実を本文へ注記) |
| 2 | backend が起動して疎通 | `cd backend && uv run fastapi dev src/pitchlog/main.py --port 8800`(別ペイン)→ `curl -fsS http://127.0.0.1:8800/health` | **標準出力が `{"status":"ok"}`**(本文を照合する。`-f` により非 2xx は終了コード 22) | ポート **8800** は Vite proxy の target(`frontend/vite.config.ts:23`)に合わせる。起動待ちは最大 30 秒でポーリングし、超えたら失敗とする |
| 3 | frontend が起動して疎通 | `cd frontend && pnpm dev -- --host 127.0.0.1 --port 5173 --strictPort`(別ペイン)→ `curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:5173/` | **200** | **`--strictPort` を必須にする** — 付けないと 5173 が埋まっているとき Vite が別ポートへ移り、期待値が一意でなくなる(P1-5)。`vite.config.ts` に `server.port` の指定はない(実測)。**`/api/health` は使わない**(proxy が接頭辞を残すため 404) |
| 4 | 終了 | 各ペインで `Ctrl-C` → `docker compose down`(データを消す場合は `docker compose down -v`) | 終了コード 0 | ボリュームを消すと初期化からやり直しになる(`dev-db-contracts/plan.md:155`) |

**環境変数ファイルの作成は人間が行う**。AGENTS.md 絶対規則 2 により Claude は当該ファイルを読まない・書かない。手順書には作成手順を記述するが、ステップ 3・4 の実測時は**人間がファイルを用意した状態から Claude が以降を実行する**。`.env.example` は同規則の明示的な例外(正本)なので参照してよい。

## 5. DoD(受け入れ基準)

- [ ] `onboarding.md` から**固定テスト件数が消え**、設計書 8.3 の既定方針に沿った表現になっている
- [ ] 「hooks・ラッパーの」という**射程の記述が実体と一致**している
- [ ] 動作確認章が CI harness ジョブの現行(pytest・`ruff check`・`ty check`)に追随している
- [ ] 本文が**受入プロファイル**(Ubuntu 26.04 LTS の番号付き x64 WSL イメージ)と整合し、**Docker Desktop への言及がなく**、「標準」「必須」が**「受入保証対象」に統一**されている
- [ ] **Phase 4 の合格 5 項目**を**新規 WSL2 環境から完走できる手順**が本文にあり、各項目に**コマンドと期待値**が書かれている
- [ ] **NFR-021 の合格項目**と **CI 相当の品質検査**が本文上で書き分けられている
- [ ] **設計書 v1.9** に「条文契約」の**明記 7 項目**が反映され(**9 条文** = 13 章の `:778`・`:780`・`:788`・`:795`・`:808`・`:812`・`:817`・`:819` + **10.1 の `:641`**)、**維持 2 規則**が改変されておらず、確定ゲートと人間承認を経て `approved`
- [ ] 13 章の **8 系統が 7 系統**になり、onboarding が「成果物」ではなく「前提」に移っている
- [ ] 設計書・onboarding・**受入証跡 README** とも変更履歴表が **`in-review` 行 → `approved` 行の 2 行**になっている(機構は検出しないため人手確認)
- [ ] **受入証跡 README v1.1** がブートストラップ手順へ前提 PR を含み、確定ゲートと人間承認を経て `approved`(確定ゲート 2 周目 P1 — **同 PR の確定ゲート対象の正本を `in-review` のままマージしない**)
- [ ] 「draft のため規範ではない」注記 **3 箇所**が解除され、意味限定 grep で同種の記述が残っていない
- [ ] `/finalize-doc` で onboarding の**敵対レビューが収束**し、**人間の承認**を得て `status: approved` / **v1.0**
- [ ] `tests/test_verify_nfr021_evidence.py` の実 HEAD テストが**正例へ反転**し、**一時コミットによる双方向の変異確認**でいずれも赤を観測している(作業ツリー編集では変異が効かないため)
- [ ] `docs/README.md` 索引の **4 行**が現行化し `check_docs_status.py` exit 0
- [ ] 台帳 `harness-evaluation.md` の **H-79 に本タスクの観測**が追加されている
- [ ] CI 全 green・PR マージ

## 6. テスト計画

**NFR-019 の種別: 単体のみ。** 一致性・越境・E2E・故障系は本タスクの変更範囲(手順書・プロセス設計文書・検証器のテスト 1 本)に該当しない。

### 変更するテスト

| 対象 | 変更 | 理由 |
| --- | --- | --- |
| `tests/test_verify_nfr021_evidence.py:2403-2418` `test_real_repository_onboarding_draft_is_not_approved` | **実 HEAD が approved であることを assert する正例へ反転**(ステップ 10・approved 化と同一コミット) | 現状は実 HEAD が draft であることを assert しており approved 化で必ず落ちる(実測: `parse_onboarding_status` が `'draft'` → `'approved'` を返し、`validate_onboarding_blob` が `REASON_ONBOARDING_STATUS` を積まなくなる)。**削除ではなく反転**するのは、実リポジトリが approved を保つことを守る唯一の機構になるため(下記) |
| `tests/test_verify_nfr021_evidence.py:2208` `test_rejects_draft_onboarding_blob` / `:2225` `..._despite_blob_replacement` | **保持**(変更しない) | 合成リポジトリを使うため状態非依存。合格条件 ④ の draft 拒否を機構として検査し続ける |

### なぜ正例ガードが要るか(計画レビュー P1-2 で当初判断を撤回)

当初は「検証器 ④ が fail-closed だから二重化不要」としたが、**誤り**だった。実測で確認した穴:

- `check_docs_status.py:830-836` は **frontmatter と索引の一致**しか見ず、`draft` も許容語彙(`:14`)。したがって **frontmatter と索引を両方 draft に戻せば `docs-lint` は通る**
- 通常 PR の CI は named evidence に対する onboarding 検証を実行しない

→ **approved が静かに剥がれても止まらない**。合成負例は「検証器が呼ばれたとき draft を拒否する」ことの検査であり、「実リポジトリが approved を保つ」こととは別物。

### 変異確認(H-81 の規律 — 計画レビュー 2 周目 P1-2 で手順を全面変更)

**当初の手順は成立しなかった。** 対象テストは作業ツリーではなく **`HEAD` のコミットツリー**の blob を読む(`tests/test_verify_nfr021_evidence.py:2405-2411` → `validate_onboarding_blob` → `git_tree_object_oid`)。したがって「ファイルを一時的に書き換えて赤くなるのを見る」では**変異が一切効かず**、「落ちない」を観測しても変異が無効だっただけになる — **本タスクが台帳へ追記しようとしている H-81 そのもの**。

正しい手順は 4 節「ステップ 10 の実行手順」に置いた。要点は **変異を一時コミットとして作る**こと、および **正例テストはコミット前に必ず赤くなる**(旧 HEAD が `in-review` のため)ので通常の「検証してからコミット」が成立しないこと。

**無効だった変異があれば worklog に記録する**(H-81 対応案③)。

### 手順そのものの検証

ステップ 3・4 で **既存 WSL2 環境で本文どおりに実行して実測**する(上記「疎通の実行契約」の 4 項目 + backend pytest + frontend Vitest)。**テストの件数は記録せず、結果(green か否か)だけを記録する** — 固定件数を残さないという本タスクの趣旨に従う。

**これは NFR-021 の証跡にはならない。** 要件書 `:919` の受入プロファイルは「**新規に作成した** WSL2 ディストリビューション『Ubuntu 26.04 LTS』の番号付き x64 WSL イメージ」を要求しており、既存環境での実行はプロファイル外(設計書 `:637`「プロファイル外の結果は合格の証跡にしない」)。**受入の実施と判定は 4-6 で、判定者は要件書 8 章の判定者(PO)**(設計書 `:636`「開発担当・Claude は操作補助と記録の起草のみ」)。

### 回帰確認

各ステップの合格条件に `uv run python scripts/check_docs_status.py` exit 0 を置く。ステップ 6・10 では `uv run pytest tests/` 全 green と `uv run ruff check .` / `uv run ty check` exit 0 も確認する。**テスト件数は合格条件にしない**(増減が `onboarding.md` へ波及しなくなったため — ステップ 1 で件数記述を除去済み)。
