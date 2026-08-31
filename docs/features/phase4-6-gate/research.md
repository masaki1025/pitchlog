---
feature: phase4-6-gate
type: research
date: 2026-08-26
---

# 調査メモ: Phase 4-6 — NFR-021 `gate_kind: phase4` 受入判定の実施経路

## 問い

1. 受入の合格条件・証跡の必須項目は何か(要件書の逐語)
2. 検証器 `scripts/verify_nfr021_evidence.py` は何を入力に取り、何を検査するか(実装の事実)
3. 未閉塞予約 `phase4-001-20260819T142916Z` をどう閉じるか
4. 排他区間・マージ後検査・不合格時の経路はどう確定しているか
5. 前タスク(前提 PR 第 2 号)から引き継ぐべき落とし穴は何か

調査サブエージェント 3 本(spec-checker / decision-tracer / 広域探索)を並列で投げ、原典を自分で再確認して裁定した。

## 更新(2026-08-27) — 前提 PR(第 3 号)のマージにより前提が変わった

**本メモは 2026-08-26 に `develop` = `701bf5f` を前提に書いた。** その後 **前提 PR(第 3 号)= TSK-257 / PR #28 が `develop` へマージ**され(`f3b3397`)、正本 4 本が改訂された。**§2 の P0 ブロッカーは解消済み**であり、加えて次の 5 点が本タスクの手順に効く。

| 変わった点 | 現行の規範 |
| --- | --- |
| **受入プロファイル** | 「Windows 11 x64 ホスト + 番号付き x64 WSL イメージ」→「**Windows 11 ホスト(x64 / arm64 のいずれも採れる)+ ホストのアーキテクチャに対応する番号付き WSL イメージ**」。**保証の範囲は「現在の固定版 × 実施した arch × 受入事象」の組**に限り、未実施側は「互換性目標(未検証)」(要件書 v2.3) |
| **証跡のログ参照欄** | 「標準出力またはログ成果物への参照」へ **`host_raw` / `host` / `wsl_uname_raw` / `wsl_uname` / `wsl_dpkg_raw` / `wsl_dpkg` の 6 ラベルを `; ` 区切りの 1 物理行**で直接記載する。**改行・`<br>` は不可**(完全性検査⑩の表抽出が打ち切られ当該欄と判定者欄が欠落する — 実測済み)。**欄名・欄数は不変**なのでテンプレートと検証器は従来どおり |
| **arch の採取手順** | **onboarding v1.2 の 2-2 節**が実行可能なブロックを定める(3 値の採取・正規化表・欠落/表外/3 値不一致で非 0 終了)。**arm64 実機で正常系 + 不適合 4 系統を実測済み** |
| **実施順序(必須)** | 完走 → **人手確認 → 判定者が `passed`/`failed` を判定して `E` の `result` に記録** → `E` をコミット → 候補 SHA 確定 → **検証器** → マージ → **マージ後検査**。**「判定」は検証器より前**(設計書 v1.11 の 10.1) |
| **用語の単一定義** | **「4-6 マージ前条件」**= `passed` が `E.result` に記録済み ∧ 検証器①〜⑩の合格。**これは正式受入ではない** — **正式受入(= Phase 4 の完了)はマージとマージ後検査の合格まで満たして成立**する。本書で「受入合格」等の別名は用いない |
| **本数** | 前提 PR が 3 本になり、**初回合格時は 9 本**(`9+n`) |

**onboarding は v1.1 → v1.2 approved** に上がっている。10.1 の実施順序 ① が要求するのは「**受入開始時点で `develop` に統合済みの approved 版**」(版非依存)なので、**`T` を採る時点の版を証跡へ記録する**形は変わらない。

## 結論(要約)

- **【解消済み(2026-08-27)】受入プロファイルが実機と一致していなかった。** 要件書は「x64」を要求し実機は `aarch64`。**要件書改訂(前提 PR 第 3 号)は 2026-08-27 に `develop` へマージ済み**(PR #28 / `f3b3397`)なので、**`T` はこのコミット以降の `develop` から採る**。検証器はアーキテクチャを検査しないため、**arch の適合は証跡の 6 ラベルと判定者の目視で担保する**(上記「更新(2026-08-27)」)
- Phase 4 完了時の合格条件は要件書 `:921` の **5 項目**と、柱書きの **2 条件**(approved な onboarding を完走 / 8 章の判定者が確認)。NFR-019(a)〜(d)・NFR-018(b) は明示的に対象外
- 証跡の必須項目は **11 個**。加えて設計書が **7 キー**を機械検証用に要求し、うち **5 キーは要件書に対応項目のない設計書独自の追加**
- 検証器は **`--gate-kind phase4` で `--release-version` を渡さない**・`--evidence-path` は候補ツリー収録必須・**候補 SHA を checkout した作業ツリーからしか通らない**(自己同一性検査)
- `T`→`E` の区間で触れてよいのは **allowlist 3 ディレクトリだけ**。`/pr` のクローズ処理(台帳 + 索引)は失効側に落ちるため、**台帳追記はこの PR で行わない**(worklog に「台帳への追記なし」と理由を残す逃げ道が用意されている)

## 詳細と典拠

### 1. 要件書 NFR-021 — 合格条件と証跡(要件突合)

- 条項: 「NFR-021: 開発環境」/ カテゴリ 互換性・**優先度 Must**(典拠: `docs/requirements/requirements-pitchlog-2026-07-22.md:915-916`)
- 測定方法の柱書: 「次の**受入プロファイル**を試験対象として事前に一意化し、**approvedな** `docs/development/onboarding.md` の手順を**完走**できることを**2時点で8章の判定者が確認する**」(典拠: 同 `:918`)
- **Phase 4 完了時の合格条件(5 項目)**: 「ハーネスのpytest・backendのpytest・frontendのVitestが成功し、開発DBへ接続でき、backend/frontendが起動して疎通確認できること(**一致性・越境・E2E・同期故障系は実装期のため対象外**)」(典拠: 同 `:921`)
  - `:921` は NFR-019 の列挙に無い「**ハーネスの pytest**」を含む。合格項目は NFR-019 から導出せず `:921` を直接使う(典拠: 同 `:899`・`:921`)
- リリース候補時の条件(今回は対象外): NFR-019 の全ランナーと (a)〜(d)、および NFR-018(b) の機械検査(典拠: 同 `:922`)
- **証跡の必須項目(11 個)**: 日時 / commit SHA / Windows版 / WSL版 / ディストリビューション版 / onboarding版 / 主要ツールの版(python / uv / node / docker) / 実行コマンドと終了コード / 各合格項目の期待値と実測値 / 標準出力またはログ成果物への参照 / 判定者(典拠: 同 `:923`)
- 判定者: 「**判定者: システム管理者(=プロダクトオーナー)**」(典拠: 同 `:1007`)。要件書に開発担当・Claude の役割規定は無い。「**開発担当・Claude は操作補助と記録の起草のみ**」は設計書側の規律(典拠: `docs/development/dev-harness-design-2026-08-07.md:648`)
- 実機受入を委任できない理由: 「backend / frontend の起動疎通を含む実機の受入は 10.1 の判定者が実施する — sandbox ではソケット bind ができず委任できない〔台帳 H-69 (c)〕」(典拠: 同 `:820`)。背景の実測は `PermissionError: [Errno 1]`(典拠: `docs/development/harness-evaluation.md:982`)
- 受入合格は **NFR-019 の判定に影響しない**(要件書に影響を定める記述なし。NFR-019 の測定方法は CI 構成と実行履歴のみ — 典拠: 同 `:908`)
- Won't(2.2 節)との衝突は**ゼロ**(典拠: 同 `:78-91` の全走査)

#### 設計書の機械検証キー ↔ 要件書項目の対応

| 設計書のキー | 要件書側の対応 | 判定 |
| --- | --- | --- |
| `tested_commit_sha` | 「commit SHA」(`:923`) | 適合。**40 桁化は設計書独自**の厳格化 |
| `onboarding_blob_sha` | 「onboarding版」(`:923`)に**対応するが同一ではない** | 設計書独自の追加(「版番号では内容を一意に識別できない」)。**本文には版と blob の両方を欄として持たせ、機械照合は blob だけ**(典拠: `docs/ops/nfr021-acceptance/README.md:82-86`) |
| `gate_kind` / `result` / `attempt_seq` / `attempt_id` / `release_version` | **対応項目なし** | **設計書独自の追加**。計画書で「要件由来」と書かない(典拠: `docs/development/dev-harness-design-2026-08-07.md:651`) |

- 要件書側の 11 項目は本文の欄として持ち、検証器の合格条件 ⑩ が「欄の存在・空欄・プレースホルダ」だけを検査する。**実測値の妥当性判断は人間のまま**(典拠: 同 `:654`)

### 2. 【解消済み】受入プロファイルと実機の不一致 — arm64(前提 PR 第 3 号で解消)

- 要件書の受入プロファイル: 「**Windows 11 x64 ホスト**＋新規に作成したWSL2ディストリビューション「Ubuntu 26.04 LTS」の**番号付きx64 WSLイメージ**」(既定名 `Ubuntu` および他版は保証対象外 / ホスト側の事前導入は **WSL2 の有効化のみ** / Docker Desktop の事前導入は前提としない)(典拠: `docs/requirements/requirements-pitchlog-2026-07-22.md:919`)
- **実機は `aarch64`**(`uname -m` 実測・2026-08-26 再確認)。要件書に `arm64` / `aarch64` の記述は**1 件も無い**(grep 実測)
- 設計書: 「受入プロファイルに一致する環境のみ。**プロファイル外の環境での結果は合格の証跡にしない**」(典拠: `docs/development/dev-harness-design-2026-08-07.md:649`)
- **PO 裁定(2026-08-25)**: ① 受入はこのマシンでのみ実施する(x64 マシンを別途用意しない) ② **要件書 NFR-021 の受入プロファイルを改訂する(案 B)** — 文言は「ホストのアーキテクチャに対応する番号付き WSL イメージ(x64 / arm64)」の方向で**両方を保証対象**とする。手続きは**版繰り上げ + 7.3 の確定ゲート・別タスクとして起票**(典拠: `docs/worklog/2026-08-24-onboarding-approval.md:160-175`)
- 放置した場合の帰結(同裁定に明記): 「改訂しない限り **Phase 4-6 の受入が実行できず、リリース経路が永久に開かない**」(典拠: 同 `:175`)
- arm64 での完走実績: 「**本日の通しでは、arm64 が原因の失敗は 1 件も無かった。** WSL・uv・gh・mise・Docker Engine・Codex・Claude Code・CPython・Node/pnpm・rolldown・postgres のすべてが aarch64 バイナリを提供していた」(典拠: 同 `:158`)
- **検証器はアーキテクチャを検査しない**(合格条件 ①〜⑩ に該当項目なし — 典拠: `docs/development/dev-harness-design-2026-08-07.md:654`)。したがって**機械検証は通るが要件書 Must を満たさない**穴になる
- 要件書は失効対象(`default: "invalidating"`)なので、**改訂は `T` より前に `develop` へ統合されていなければならない**(典拠: `.claude/nfr021-invalidating-paths.json:4`・`docs/development/dev-harness-design-2026-08-07.md:658`)
- **前タスク(第 2 号)の plan.md・worklog・research に arm64 の記載は 1 件もない**(grep 実測)= 申し送りから落ちていた
- **PO 判断(2026-08-26)**: この改訂を **前提 PR(第 3 号)**として通す(要件書 v2.3 + 設計書 v1.11 を 1 PR・1 確定ゲート)。**TSK-257(10 章 未決事項の決着)も同梱**する。→ TSK-257 を第 3 号タスクへ再スコープ済み

### 3. 検証器 `scripts/verify_nfr021_evidence.py` の契約(実装の事実)

- 引数: `--root`(任意・既定 cwd)/ `--gate-kind`(必須・`phase4|release`)/ `--candidate-sha`(必須)/ `--evidence-path`(必須)/ `--release-version`(`release` のみ)。**引数エラーも fail-closed**(典拠: `scripts/verify_nfr021_evidence.py:2345-2405`)
- `phase4` に `--release-version` を渡すと**入力エラーで即中断**(典拠: 同 `:2408-2432`)
- `--evidence-path` は**リポジトリ相対**・**親が `docs/ops/nfr021-acceptance` と完全一致**(サブディレクトリ不可)・**候補 SHA のツリーに収録済み**(典拠: 同 `:2559-2576`・`:2579-2605`)
- **自己同一性検査**: 実行中のスクリプト自身と `.claude/nfr021-invalidating-paths.json` の作業ツリー blob OID が、候補 SHA のツリーの同パスと一致しなければ `GuardError`(典拠: 同 `:2700-2737`)→ **候補 SHA を checkout した状態でしか通らない**
- 合格条件の要点
  - `result` は `"passed"` のみ(典拠: 同 `:2785-2817`・`:273`)
  - `tested_commit_sha` が候補 SHA の**祖先**(`merge-base --is-ancestor`)(典拠: 同 `:2200-2245`)
  - `onboarding_blob_sha` が **`T` のツリー**の `docs/development/onboarding.md` の blob と一致し、**その blob の frontmatter が `status: approved`**(典拠: 同 `:2841-2876`)
  - **失効判定**: `T..C` の各コミットの変更パスの和集合(`--name-only -m --no-renames -z`)。**2 点差分ではない**(典拠: 同 `:2247-2306`)。分類は invalidating 優先 → allowlist → **どちらにも一致しなければ `default: invalidating` で失効**(典拠: 同 `:2128-2179`)
  - **⑦⑧⑨**: `attempt_id` で予約と結果を畳み込み、名指し証跡が**最大 `attempt_seq`** かつその最大値が**一意**、**同一ゲートキーの予約がすべて閉塞済み**、**名指し結果に対応する予約がちょうど 1 件**(典拠: 同 `:3164-3246`)
  - **⑩ 本文完全性**: `## 証跡` 表のヘッダーは `("項目","記録")` 完全一致・必須欄が文字列完全一致で存在・**空欄禁止**・**`<...>` 形のプレースホルダ禁止**。`## 合格項目` 表は `#` 列と `合格項目` 列が**候補ツリーのテンプレートと行数・内容ともに完全一致**(典拠: 同 `:1379-1497`)
- **`phase4_base_sha` を証跡に書いてはならない** — 未知キーとして拒否され、テストでも負例固定(典拠: 同 `:781-815` / `tests/test_verify_nfr021_evidence.py:676-697` / `tests/test_nfr021_evidence_templates.py:57-61`)。置き場は判定者の手元と PR コメント
- 終了コード: **合格 = 0 かつ stdout/stderr 空**。不合格・判定不能 = 1(stderr に理由行)(典拠: 同 `:3380-3403`)
- **マージ後検査(`M` の両親・ツリー)を実装したスクリプトは存在しない**(grep 実測)= 手作業

### 4. 証跡テンプレート・命名・未閉塞予約

- 命名の正規形(典拠: `docs/ops/nfr021-acceptance/README.md:41-54`)
  - 結果証跡: `YYYY-MM-DDTHHMMSSZ-<gate_kind>-<phase4|vX.Y.Z>-seq<NNN>-<short_sha>.md`
  - **`<short_sha>` = `tested_commit_sha` の先頭 12 文字固定**・**`seq<NNN>` は 3 桁ゼロ詰め**(`seq001` は正・`seq0001`/`seq1` は不正)
  - **先頭タイムスタンプは予約と一致させる必要はない**(レコード間契約はゲートキー・`attempt_seq`・`release_version` の 3 点)
- 未閉塞予約(**`phase4` はこの 1 件だけ**): `gate_key: "phase4"` / `attempt_seq: 1` / `attempt_id: "phase4-001-20260819T142916Z"` / `started_at: "2026-08-19T142916Z"` / `operator: "山田正輝"`(典拠: `docs/ops/nfr021-acceptance/2026-08-19T142916Z-phase4-phase4-seq001-reservation.md:1-7`)
  - → 結果証跡は **`attempt_id: "phase4-001-20260819T142916Z"` / `attempt_seq: 1`(引用符なし整数)/ ファイル名 `seq001`** で作らなければ ⑦⑧⑨ を満たせない
- 証跡テンプレートの全欄(典拠: `docs/ops/nfr021-acceptance/evidence-phase4-template.md:16-52`)
  - frontmatter 5 キー: `gate_kind: phase4` / `tested_commit_sha` / `onboarding_blob_sha` / `result` / `attempt_seq`(引用符なし整数)/ `attempt_id`
  - `## 証跡` 表 **12 欄**(必須 11 + **`onboarding blob SHA`**)。`主要ツールの版（python / uv / node / docker）` は**全角括弧**。`各合格項目の期待値と実測値` の値は **`下表に記載` のまま残す**
  - `## 合格項目` 表 **5 行**(ハーネスの pytest / backend の pytest / frontend の Vitest / 開発 DB へ接続 / backend・frontend が起動して疎通確認)。`#` 列と `合格項目` 列は **1 文字も変えられない**
  - **実測値に `<` `>` を 1 組でも入れると ⑩ で不合格**(`PLACEHOLDER_RE` — 典拠: `scripts/verify_nfr021_evidence.py:104`)
- 合格項目 1〜5 に対応する onboarding の手順: 1 = 6 章項目 3(`docs/development/onboarding.md:299`)/ 2・3 = 7-1 節(同 `:339-360`)/ 4 = 8-2 節(同 `:396`)/ 5 = 8-3 節(同 `:411`)
- 索引カバレッジ: **正規形の結果証跡は索引不要**。非正規形・サブディレクトリ配下・未知の `.md` は `docs-lint` が exit 1(典拠: `scripts/check_docs_status.py:165-193`・`:430-456`)。**証跡に `status:` を書く必要はない**

### 5. CI・スキル・フックの実挙動

- CI の success 必須 **7 本** = `secrets` / `docs-lint` / `core-guard` / `harness` / `nfr021-append-only` / `frontend-changes` / `backend-changes`。**skipped 許容は `frontend` と `backend` の 2 本のみ**(典拠: `.github/workflows/ci.yml:21-199`。PR #27 の run `32954691708` で実測)
- `nfr021-append-only` は **develop 宛 PR のみ**実行(main 宛・push・workflow_dispatch は exit 0)。既存レコードの改変・削除は不合格、新規結果証跡には ⑩ と同じ完全性検査、**base ツリーに対応予約がちょうど 1 件**、**同一 PR に予約と結果を同時追加すると不合格**(典拠: `scripts/check_nfr021_append_only.py:506-936` / `tests/test_nfr021_append_only.py:787`)
  - 今回は予約が既に develop にあるため、結果証跡だけを追加する形は正しい経路
- **H-72**: `check_plan_docs_sync.py` の突合対象は `docs/ops/nfr021-acceptance/` を除外しないため、**新規結果証跡が「差分にあるのに未宣言」で `/pr` が中断する**。対処は**計画書 3 節の別枠に実パスを宣言**すること(典拠: `docs/development/harness-evaluation.md:1008-1017`・`scripts/check_plan_docs_sync.py:611-659`・`.claude/skills/pr/SKILL.md:28`)。前タスクは「H-72 の対処は 4-6 のタスクの計画書で行う」と明記して申し送っている(典拠: `docs/features/phase4-6-acceptance/plan.md:107`)
- 「反映なし」は**リテラル一致**で判定される(典拠: `scripts/check_plan_docs_sync.py:478`)
- `/pr` のクローズ処理は「**この変更を最後のコミットとして PR に含める**」もので、台帳追記時は `docs/development/harness-evaluation.md` と `docs/README.md` を触る(典拠: `.claude/skills/pr/SKILL.md:11-19`)
  - ⚠️ **両ファイルは失効側**(`default: invalidating`)。`T` を採った後にこのコミットを置くと ⑥ で失効する → **本タスクでは台帳追記を行わず、worklog に「台帳への追記なし」と理由を残す**(逃げ道は同 `:16-17` が用意)
- `git_guard`: **detached HEAD では `--abbrev-ref HEAD` が文字列 `HEAD` を返し、`PROTECTED` にも `UNKNOWN` にも該当せずガードが発火しない**(典拠: `.claude/hooks/git_guard.py:147-190`・`:442-476`)。→ 受入は **`switch -C develop <40 桁 OID>`** でブランチ名を `develop` に保って行う(approved 手順: `docs/development/onboarding.md:215-226`)
- push: 位置引数 2 個未満・`HEAD` refspec・force は遮断。**宛先を明示した `push -u origin <branch>`** を使う(典拠: `.claude/hooks/git_guard.py:340-438`)
- `/task-done` は PR が **MERGED** でなければ中断。マージ後検査の記録(4 項目)から **3 分岐**(記録なし=中断 / 合格=`P4-後` 起票 / 不合格=「Phase 4-6 再試行」起票)(典拠: `.claude/skills/task-done/SKILL.md:11-26`)
- `/release` 手順 0 は「**本手順が検証器の実行へ置き換えられるまでは無条件で中断する**」。`gate_kind: phase4` は `/release` を経由せず 4-6 の PR 上で検証器を直接実行する(典拠: `.claude/skills/release/SKILL.md:13`・`:17`)

### 6. 排他区間・マージ・不合格時の経路(確定済み)

- **排他区間**: 禁止対象は「push しないこと」ではなく **`main`・`develop` を進めるあらゆる操作**(直接 push・**GitHub UI/API による他 PR のマージ**・Web エディタ・bot/Actions/スケジュール)。**例外は当該 4-6 PR のマージのみ**。**排他管理者 = 8 章の判定者**。**開始と解除を当該 PR へコメント記録**。解除はマージ後検査の完了時または明示的な中断時。時間切れ・照合不一致なら排他を解除して受入からやり直す(典拠: `docs/development/dev-harness-design-2026-08-07.md:657`)
- **マージ統制**: `phase4_base_sha` を固定 → 排他開始 → GitHub API で head/base を再照合 → `gh pr merge --merge --match-head-commit <E>` → **M の第 1 親 = `phase4_base_sha` / 第 2 親 = E / ツリー = E のツリー**を検査(典拠: 同 `:655`)
- **マージ後検査の記録**: 合否どちらでも 4-6 の PR コメントへ。記録項目 4 つ = **`M` の完全 OID / 検査の実施日 / 合否 / 確認者**。記録主体は判定者(典拠: 同 `:836-837`)
- **不合格(`failed`)時**: 4-6 はマージできないので、**Phase 4 の実装を含まない「結果証跡だけの監査 PR」**で同一 `attempt_id` の `failed` を追記して予約を閉じ、**既存のすべての予約より厳密に大きい `attempt_seq`** を新規予約して再実施(典拠: 同 `:653-654`・`docs/ops/nfr021-acceptance/README.md:197-198`)
- **`P4-後` との境界(4-6 でやらないこと)**: `/release` 手順 0 の置換 / 13 章の現況追随 / 完了証跡の記録 / マージだけでの完了宣言(典拠: 同 `:820-821`・`:828`・`:845`)
- **再提案禁止**(v1.9/v1.10 で「増やさない」と確定): マージ後検査の新キー・媒体 / 論理スロットと Notion の機械化(7 案否決)/ 再試行タスクの初期化項目の追加(典拠: 同 `:839-843`)

### 7. 前タスクから引き継ぐ落とし穴(是正 8 件の確定版)

前タスクは再スコープで 4-6 の実施手順を plan.md から削除したため、**確定版が現存するのは worklog の表だけ**(典拠: `docs/worklog/2026-08-25-phase4-6-acceptance.md:47-58`・`docs/features/phase4-6-acceptance/plan.md:50`)。

1. `/pr` を `E` より前に実行する案は成立しない → **受入完走後に 1 回だけ実行し、そのクローズ処理コミットを `E` とする**
2. `check_plan_docs_sync.py` は**リテラル「反映なし」**を見る
3. `--match-head-commit <E>` は remote head が `E` でないと失敗する → **`E` の push 手順を手順表に入れる**
4. 受入不合格は `/task-done` の前提(MERGED)を満たさない → **別ブランチの監査 PR** へ
5. `check_docs_status.py` は**索引日付 ≥ 変更履歴の最新日付**も検査する(本タスクは正本改訂を含まないため通常は非該当)
6. **detached checkout は撤回**(ガードが発火しない)→ `T` を指すローカル `develop` ブランチで試験
7. CI「全ジョブ緑」は成立しない → **success 必須 7 本・skipped 許容 2 本**
8. 裸の push ではなく **宛先明示**

**実行不能な合格条件の型**(同じ罠を書かないため): ① 変更履歴に歴史的事実として残る文言の `grep = 0 件` ② 「本コミットの OID を記録」は**自己参照で不可能**(push 後に取得する)(典拠: 同 `:60`)

### 8. 実行手順の骨子(計画書へ落とす粒度)

**前提**: 前提 PR(第 3 号)が develop へマージ済みであること(§2)→ **2026-08-27 に充足**(PR #28 / `f3b3397`)。**手順は上記「更新(2026-08-27)」の実施順序に従う**(判定は検証器より前)。

1. `T` を確定して push(以降 allowlist 3 ディレクトリ以外を触らない)
   - `rev-parse HEAD` = `T` / `rev-parse HEAD:docs/development/onboarding.md` = `onboarding_blob_sha`
2. 受入プロファイル上の新規環境で onboarding を完走(判定者 = PO)
   - `fetch origin <branch>` → `switch -C develop <T>` → `branch --show-current` が `develop` → `rev-parse HEAD` が `T` と一致(典拠: `docs/development/onboarding.md:211-228`)
3. 結果証跡を起草(テンプレートのフェンス内を複写・§4 の制約を全て満たす)
4. 証跡コミットを作り、**`/pr` のクローズ処理コミットを `E`** として push
5. 手元で先に落とす: `check_nfr021_append_only.py --base origin/develop --head HEAD` / `check_docs_status.py` / `check_plan_docs_sync.py` / `ruff` / `ty` / `pytest tests/`
6. `E` を checkout した状態で検証器を実行(自己同一性検査のため)
   - `uv run python scripts/verify_nfr021_evidence.py --root "$(pwd)" --gate-kind phase4 --candidate-sha <E> --evidence-path docs/ops/nfr021-acceptance/<証跡>.md` → **exit 0 かつ無出力**
7. PR 作成 → CI success 必須 7 本 → 判定者の合格判定 → 排他区間の開始記録 → `phase4_base_sha` 固定 → head/base 再照合
8. `gh pr merge --merge --match-head-commit <E>` → マージ後検査(手作業)→ 記録 4 項目を PR コメントへ → 排他解除
9. `/task-done`(3 分岐)

## 未解決・申し送り

- **【充足済み 2026-08-27】** 受入プロファイルの arm64 改訂 = 前提 PR(第 3 号)は **PR #28 でマージ済み**(`f3b3397`)。**`T` はこのコミット以降の `develop` から採る**
- **hooks の実行 Python 版が受入プロファイル上でテストされていない** — hooks は 3.12 系でテストされ、`Ubuntu-26.04` では `/usr/bin/python3` = 3.14 系(典拠: `docs/worklog/2026-08-24-onboarding-approval.md:181`)。台帳の候補として申し送られたまま
- **onboarding 6 章のガード確認は git_guard・codex_guard の 2 本のみで、secret_guard・protect_paths は未検証**のまま「動作確認」を名乗っている(典拠: 同 `:148`)。v1.1 で解消されたかは未確認
- **マージ後検査は手作業**(実装スクリプトなし)。v1.9/v1.10 が「機械化しない」と確定済みのため、本タスクで機械化を提案しない
- 台帳 H-77: 並行タスク `feature/sync-protocol-design` が走っている。`H-*` の払い出しは develop と全 OPEN PR の最大値を確認してから(現在の最大は H-84)
