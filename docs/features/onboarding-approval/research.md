---
feature: onboarding-approval
type: research
date: 2026-08-24
---

# 調査メモ: onboarding.md の approved 化 + 陳腐化した数値記述の是正(TSK-253)

## 問い

1. `onboarding.md:72` の「正負テスト 103 件」をどう直すのが正しいか(固定値を書くこと自体が適当か)
2. 同種の陳腐化が他にどれだけあるか(台帳 H-79 の再発防止)
3. `onboarding.md` を approved 化するために、この文書は何を満たしていなければならないか
4. approved 化に伴って追随が必要な箇所はどこか

## 結論(要約)

- **件数は「新しい数字に更新」ではなく「除去」が正しい。** 設計書 8.3(approved)が「**固定件数は腐るため書かない**・件数は CI harness ジョブの実行結果を正とする」と既に規範化しており、**設計書 13 章にあった同じ「103件」は 2026-08-16 に除去済み**。`onboarding.md:72` はその是正が届かなかった兄弟であり、**台帳 H-79 の構図そのもの**。
- **Notion タスクの「103 → 406」は誤り。** 当該文は `uv run pytest tests/` の出力を指すので比較対象は **652**(実測)。406 は `def test_` 関数の数。どちらにせよ除去するので採らない。
- **approved 化は「状態を変える」だけでは通らない。** 設計書 13 章 4-6 は approved 化を「**実際の依存導入・DB 初期化・起動・疎通確認まで**」と定義し、要件書 NFR-021 の受入プロファイルは「WSL2 の有効化以外はすべて onboarding の手順内で導入」を要求する。現行 78 行は **Phase 4 の合格 5 項目のうち 4 項目を完走できない**。
- **approved 化すると `tests/test_verify_nfr021_evidence.py:2403` が落ちる**(実測確認済み)。同テストは実リポジトリの onboarding が draft であることを assert している。
- **追随先は 3 系統**: 「draft だから規範ではない」注記 3 箇所 / 索引 1 行 / 上記テスト 1 本。

## 詳細と典拠

### A. 件数記述 — 直し方は「除去」

#### A-1. 実測(2026-08-24・本タスクで実行)

| 対象 | 値 | 取得方法 |
| --- | --- | --- |
| `uv run pytest tests/` の出力 | **652 passed**(37.56s・全グリーン) | 実行 |
| `def test_` 関数の数 | 406(9 ファイル) | `grep -c '^\s*def test_' tests/*.py` |
| `onboarding.md:72` の記載 | 103 件 | `docs/development/onboarding.md:72` |

**Notion タスク本文と申し送り(`docs/worklog/2026-08-23-root-lint-typecheck.md:198`)の「実際は 406 個」は、この文の母集団としては誤り。** 同 worklog の `:64`・`:184` は「652 件全緑」と書いており、同一 worklog 内で 406 と 652 が併存していた。当該文は `uv run pytest tests/` の全グリーンを求める文なので、読者が突き合わせる数は pytest の出力 = 652。

#### A-2. 「固定件数を書かない」は approved 正本の既定方針

> hooks は **pytest で単体テストする**(`tests/` 全件 — P1-13。**件数は CI harness ジョブの実行結果を正とする〔固定件数は腐るため書かない — v1.3〕**…)
> — `docs/development/dev-harness-design-2026-08-07.md:464`(8.3・status: approved)

#### A-3. 同じ「103件」は設計書側で既に除去されている(前例)

- 指摘: `docs/features/harness-design-review/research.md:66`(P2-12)「13 章 Phase 1 完了条件の固定件数「103件」が 8.3 の『固定件数は書かない』方針と矛盾」
- 是正方針: `docs/features/harness-design-review/plan.md:34`「**固定テスト件数を除去**し…『CI harness ジョブの実行結果を正とする』へ置換。**変更履歴表 v0.17 行の「103件」は当時の事実として保持する**」
- 是正後の現物: `dev-harness-design-2026-08-07.md:785`「hooks・ラッパーの pytest(`tests/`。**件数は CI harness ジョブの実行結果を正とする** — 8.3)全グリーン + 実地確認」

→ **`onboarding.md:72` は同じ欠陥を持ったまま取り残された兄弟。** 台帳 H-79(`harness-evaluation.md:542-553`・追跡優先度 **高**・未対応)の定義「同じ欠陥を持つ他の呼び出し箇所・**兄弟節**を確認せずに 1 箇所だけ直す」に正確に該当する。

#### A-4. この数字は過去に 5 回手で追随して力尽きている

`git log -L 72,72:docs/development/onboarding.md` の実測: **44 → 47 → 59 → 71 → 82 → 103**。すべて 2026-08-07 の敵対レビュー各周での手更新(最終更新 `4d7491c`)。以後 **382 コミット**放置。固定値のコストが履歴で実証されている。

#### A-5. 件数だけでなく「射程」も陳腐化している

`onboarding.md:72` は「**hooks・ラッパーの**正負テスト」と書くが、`tests/` の 9 ファイルのうち hooks 分は `test_hooks.py` のみ。残り 8 本は `scripts/` の検査(`check_docs_status` / `check_plan_docs_sync` / `core_guard` / `feature_status` / `nfr021_append_only` / `nfr021_evidence_templates` / `nfr021_invalidating_paths` / `verify_nfr021_evidence`)。**件数より重い齟齬。**

#### A-6. 動作確認 5 章そのものの追随漏れ

CI の harness ジョブは直近 `76d9a8b` で **`uv run ruff check .`・`uv run ty check`** を実行するようになったが(`AGENTS.md:31`・`.claude/skills/check/SKILL.md`)、`onboarding.md:70-74` の動作確認は pytest のみ。

### B. approved 化の前提 — 本文の完成が要る

#### B-1. 正本が要求していること

| 典拠 | 要求 |
| --- | --- |
| `requirements-pitchlog-2026-07-22.md:917` | 「セットアップ・**起動手順**は `docs/development/onboarding.md` に整備する」 |
| 同 `:918` | 「**approved な** onboarding.md の手順を**完走できること**を 2 時点で 8 章の判定者が確認する」 |
| 同 `:919`(受入プロファイル) | 「Windows ホスト側の事前導入は **WSL2 の有効化のみ**を前提とし、**その他の開発ツールはすべて onboarding の手順内で導入する**(**Docker Desktop の事前導入は前提としない**)」 |
| 同 `:921`(Phase 4 合格条件) | ハーネスの pytest・**backend の pytest**・**frontend の Vitest**・**開発 DB へ接続**・**backend/frontend が起動して疎通** |
| 同 `:1004`(8 章 DoD⑦) | 「**approved かつ現行化された**開発者セットアップ手順」 |
| `dev-harness-design-2026-08-07.md:788`・`:808` | 4-6 = 「`onboarding.md` の**完成**と v1.0 approved 化(**実際の依存導入・DB 初期化・起動・疎通確認まで**)」 |

#### B-2. 現行 78 行での完走可否(実ファイル判定)

| # | 合格項目(`docs/ops/nfr021-acceptance/evidence-phase4-template.md:46-52`) | 現行 onboarding | 判定 |
| --- | --- | --- | --- |
| 1 | ハーネスの pytest | `:72` にあり(件数・射程が陳腐化) | 手順あり |
| 2 | backend の pytest | **記述なし**(`backend` の語が本文に一度も出ない) | **完走不可** |
| 3 | frontend の Vitest | **記述なし**(`pnpm install`・`pnpm test` なし) | **完走不可** |
| 4 | 開発 DB へ接続 | **記述なし**(`docker compose up` も環境変数の用意もない) | **完走不可** |
| 5 | backend・frontend の起動疎通 | **記述なし** | **完走不可** |

リポジトリ側の実体(すべて実在): `backend/`(uv・pytest **2 件**)・`frontend/`(pnpm・Vitest)・`contracts/`・`docker-compose.yml`(postgres 17.11・`POSTGRES_USER/PASSWORD/DB` を `:?required` で必須化 — 環境変数の用意なしでは起動しない)・`mise.toml`(node = **24.16.0**)・`frontend/package.json`(`packageManager: pnpm@11.22.0`)。

この不足は **要件書 v1.9 確定ゲート 1 周目 P0-1 で既に approved にできない理由として挙げられている** — `docs/worklog/2026-08-11-req-v1-9-nfr021-wsl2.md:23`「同文書の現状はハーネス疎通確認までで pitchlog 本体の依存導入・DB 初期化・起動・確認を含まない」。

### C. 受入プロファイルとの不整合(approved 化した瞬間に approved 正本間の矛盾になる)

| 箇所 | 現在の文言 | 正本の要求 | 経緯 |
| --- | --- | --- | --- |
| `onboarding.md:15` | 「開発環境は WSL2(**Ubuntu 推奨**)を**標準とする**」 | 要件書 `:919` = Ubuntu **26.04 LTS の番号付き x64 WSL イメージ**に固定(既定名 `Ubuntu` は保証対象外) | v1.9 確定ゲート 3 周目 P0-1 が「**onboarding も Ubuntu を『推奨』止まり**」と名指ししたが、**是正先は要件書側だけ**だった(worklog `:38`) |
| `onboarding.md:15` vs `:17` | 「標準とする」/「## 0. WSL2(**必須**)」 | 用語を「**受入保証対象**」に統一 | v1.9 確定ゲート 1 周目 P1-5 の未処理分。`docs/features/req-v1-9-nfr021-wsl2/plan.md:76` が**本タスクへ明示的に申し送り** |
| `onboarding.md:32` | 「Docker Desktop の WSL2 統合、**または WSL 内ネイティブ導入**」 | 要件書 `:919`「**Docker Desktop の事前導入は前提としない**」 | 同 1 周目 P1-1 が「この記述の『WSL 内ネイティブ導入』は **Docker Engine** の導入方法であり PostgreSQL のネイティブ経路は存在しない」と問題視。**要件書側だけ是正され onboarding は原文のまま**(`plan.md:89`「反映なし」)。以後 `dev-db-contracts` も「4-6 の担当」として先送り(同 `plan.md:50`・`:65`・`:155`) |
| `onboarding.md:33` | 「**Node.js 20+**(実装フェーズからは mise + pnpm)」 | `mise.toml` = node **24.16.0** / pnpm 11.22.0。frontend は既に実在 | 版を定めた決定記録は**見つからず(不明)** |
| `onboarding.md:31` | 「Python **3.12+**」 | `.python-version` = 3.12.3 / `backend/pyproject.toml` = `>=3.12,<3.13` | 「3.12+」は 3.13 を許すように読めるが backend は上限で除外 |
| `onboarding.md:19-21` | WSL2 の確認のみ | 「新規に作成した WSL2 ディストリビューション」から出発する手順が無い | — |

**なぜ矛盾のまま v1.9 が approved になれたか**: 5 周目の収束判定が「onboarding との間にも承認を妨げる矛盾なし」としたのは、**onboarding が draft = 規範ではない**という前提の上に成り立つ(worklog `:49`)。**approved 化した瞬間にこの前提が消える。**

### D. approved 化に伴う追随先

#### D-1. 「draft だから規範ではない」注記 — 3 箇所

| 箇所 | 文言 |
| --- | --- |
| `dev-harness-design-2026-08-07.md:475`(8.4 `/setup-dev`) | 「手順の配置先は `onboarding.md`。同書は現在 **draft** であり、**approved 化までは規範ではなく作業手順として扱う**」 |
| `dev-harness-design-2026-08-07.md:839`(14 章 論点C) | 「配置先は onboarding.md(**同書の approved 化は Phase 4** — approved 化までは規範ではない)」 |
| `github-setup.md:16`(approved v1.1) | 「ローカル環境構築の手順は onboarding.md に置く(同書は現在 **draft** — approved 化までは規範ではなく作業手順として扱う)」 |

これらは設計書 v1.4 確定ゲート 1 周目 P0-2 が「設計書 8.4・10.1・13 章・14 章論点C と `github-setup.md`」の **5 系統を一括で**是正して作った注記(worklog `:55`)。**解除側も同じ 5 系統を洗う**(10.1・13 章は「approved 化を要求する」形なので文言変更は不要だが確認は要る)。これを 1 箇所だけ直すと H-79 の再発。

#### D-2. 索引

`docs/README.md:17` = `| [オンボーディング](development/onboarding.md) | draft | 0.5 | 2026-08-10 |`。**正本 14 行のうち唯一の draft**。frontmatter との不一致は `scripts/check_docs_status.py`(CI ジョブ `docs-lint`)が落とす。approved 行の既存書式は `**approved**(v1.0 — 敵対レビューN周 → PO 承認)`。

#### D-3. テストが 1 本落ちる(実測確認済み)

`tests/test_verify_nfr021_evidence.py:2403-2418` の `test_real_repository_onboarding_draft_is_not_approved` は、**実リポジトリ HEAD の onboarding blob が approved でないこと**を assert する。

実測(本タスクで実行):

```
v.parse_onboarding_status(現行内容)                    -> 'draft'
v.parse_onboarding_status(status を approved にした内容) -> 'approved'
```

`validate_onboarding_blob`(`scripts/verify_nfr021_evidence.py:2871-2875`)は status が approved なら `REASON_ONBOARDING_STATUS` を積まないので、**assert が成立しなくなる**。設計上の根拠は `docs/features/nfr021-evidence-verifier/research.md:419-424`(現 develop では ④ が必ず不合格であることの機械的裏付けに実 blob を使った)。

**なお `tests/` は失効対象パスであり、テスト件数の増減は A の件数記述に波及する**(`docs/features/root-lint-typecheck/plan.md:225` が「件数を増減させない」と申し送っていた理由)。**A で件数記述を除去すればこの相互依存は解消する。**

#### D-4. 正本外の参照(確認のみ・変更不要の見込み)

`.claude/skills/setup-dev/SKILL.md:12,19` / `.claude/scripts/codex_run.py:193` / `docs/ops/nfr021-acceptance/README.md:183`。

#### D-5. 変更してはならない(履歴の保全 — 設計書 7.1-4)

要件書 `:20`・`:21`(v1.9 の 2 行)の「draft のため」記述 / `docs/worklog/**` 全件 / 完了済み feature の `plan.md`・`research.md` / 設計書・`github-setup.md` の過去版変更履歴行。前例: `req-v1-9-nfr021-wsl2/plan.md:73` が「過去事実・履歴の書き換え」を「やらないこと」に置いた。

### E. 機構への影響と順序制約

| 項目 | 内容 | 典拠 |
| --- | --- | --- |
| 実施順序 | **① approved 化 → ② その版で完走 → ③ 証跡コミット(T)→ ④ 判定**。「**draft 版で実行した結果は証跡にならない**」 | 設計書 `:638` |
| 合格条件 ④ | `onboarding_blob_sha` が T 時点の blob と一致し、かつ**その blob の frontmatter が `status: approved`** | 設計書 `:642` / `verify_nfr021_evidence.py:2859-2875` |
| 失効 | `docs/development/onboarding.md` は**明示の失効対象パス**。T→候補の**各コミットの変更パスの和集合**で判定 | 設計書 `:646` / `.claude/nfr021-invalidating-paths.json:9` / `verify_nfr021_evidence.py:2247-2305` |
| 帰結 | **T は approved 化コミット以降でなければならず、T を採った後に onboarding.md を 1 文字でも触ると証跡が失効する** | 上記の合成 |
| 未閉塞の予約 | `docs/ops/nfr021-acceptance/2026-08-19T142916Z-phase4-phase4-seq001-reservation.md` が `attempt_seq: 1` で**結果証跡なし = 未閉塞**。「未閉塞の予約がある間は次の試行を開始しない」 | 設計書 `:640` |

→ **本タスクは受入試行ではないので予約には抵触しないが、T を採る前に develop へ統合されている必要がある。**

### F. 他の陳腐化しうる固定数値(H-79 の全経路 — 棚卸し)

**機構は存在しない。** `scripts/check_docs_status.py`(CI の `docs-lint`)は索引カバレッジ・frontmatter 3 行文法・索引と変更履歴表の突合・見出しバッククォート等を検査するが、**「文書に書かれた N 件」を実体と突合する検査は無い**。台帳にも未決として起票済み — `harness-evaluation.md:1086`「(6) 番号上限の腐りを機構で検出していない」(**3 タスク連続で申し送られ再発が止まっていない**)。

#### F-1. 同一数値が複数箇所に複製されているもの(直すなら全部)

| 数値 | 箇所数 | 場所 | 実測 |
| --- | --- | --- | --- |
| 既定 3 並列 / 調査サブエージェント 3 本 | **6** | `CLAUDE.md:35` / 設計書 `:12,:436,:477,:505` / `investigate/SKILL.md:2,10` | 3(一致) |
| `docs/legacy/research/` 9 本 | **4** | 設計書 `:500,:521` / `legacy-analyst.md:10,14` | 9(一致) |
| NFR-021 正本 4 件 | **5** | `ops/nfr021-acceptance/README.md:14,39,112,116,122` | 4(一致) |
| CI 5 ジョブ | **2** | `github-setup.md:37,39` | 必須 5 / ci.yml のジョブ総数 9(一致) |
| DoD 8 項目 | **4** | 設計書 `:357,:360,:486` / `release/SKILL.md:23` | 一致 |
| 計画書 6 節 | **3** | `plan/SKILL.md:11` / 設計書 `:479` / `implement/SKILL.md:15` | 一致 |

#### F-2. 単独だが実体追随が要るもの

| 箇所 | 記載 | 実測 |
| --- | --- | --- |
| `onboarding.md:72` | 正負テスト 103 件 | **652(不一致 — 本タスクの対象)** |
| 設計書 `:471`,`:786` | skills 13 本 | 13(一致) |
| 設計書 `:785` | hooks 6 本 | 6(一致) |
| 設計書 `:333`,`:41` | コア領域 5 領域 | 5(一致) |
| `README.md:14` | 要件定義完了 **v2.0** | **v2.2 / 2026-08-19(不一致)**。ただし同文が「現行版の正は要件書の変更履歴」とヘッジ |
| `requirements-draft-pitchlog.md:7` | 決定記録 **D-1〜D-37** | **D-44(不一致)**。台帳 `:1092`「(8)」に**起票済み・未決**(同書は変更履歴表を持たない免除文書で、是正に別ゲートが要る) |

#### F-3. 「腐らせない書き方」の前例

- 設計書 `:35`(変更履歴): 「8.5 decision-tracer — 典拠範囲の**番号上限(D-1〜D-41・I-1〜I-24)を撤去**し『全 D-*／全 I-*』へ(**追記で腐るため**)」
- `.claude/agents/decision-tracer.md`: 「**番号上限は書かない — 追記で腐るため**」
- `.claude/agents/spec-checker.md:10`: 「**版数は書かない: 追記で腐るため**」
- 機構化するなら `verify_nfr021_evidence.py:183`(`REASON_ACCEPTANCE_ITEM_COUNT`)が **期待値をテンプレートファイルから読んで比較する = ハードコードしない**モデル

#### F-4. 追随不要(要件の固定値 — 対象外)

`88 列`・`15 万プレイ`・`同時 3 試合`・`1280px`・`375px` 等。典拠: 要件書 `:1161`「本表に載っていない数値——性能目標・**88 列などの契約値**——は設定可能ではなく、**要件の固定値**である」。

### G. 確定ゲート(`/finalize-doc`)の手続きと実績

手続き: `in-review` へ → `codex_run.py review adversarial`(sol xhigh 固定)→ 採用/不採用に分類して反映 → **収束まで反復**(反映を伴う 1 周ごとに plan の `確定ゲート周回` を +1、**反映周ごとに 1 コミット**・件名に `反映<r>周目`・**ステップ記法を付けない**)→ **人間承認** → approved 化・版確定・変更履歴追記・索引現行化 → worklog 記録。

7.6 の決定表上、`draft 0.5 → approved 1.0` は**版繰り上げ + 状態遷移**なので **7.3 の確定ゲート**(設計書 `:423`)。設計書 `:638` も「`onboarding.md` を確定ゲート(7.3)に通し approved 化(Phase 4 初回は **v1.0**)」と名指ししている。

周回実績(見積もりの参考):

| 対象 | 周回 |
| --- | --- |
| `github-setup.md` v1.0(新設・短文書) | 2 周 |
| `github-setup.md` v1.1(版繰り上げ) | 2 周 |
| 要件書 v1.9 | 5 周 |
| `harness-evaluation.md` v1.0(新設) | 9 周 |
| 設計書 v1.8 | 6 周 |
| 要件書 v2.2 / ADR-003 | 25 周 |

短い単一文書は 2 周で収束した実績がある一方、**onboarding は Phase 4-6 の受入前提かつ失効対象パス**という契約上の重みがある。

**確定ゲートの原則**: 「確定ゲートは『レビュー対象の**現状態**を approved にできるか』を判定するものであり、既知の P0 を未来ステップへ送ったまま『approved』とすることはできない」(worklog 2026-08-11 `:32`・2 周目 P0)。→ **B・C・D の是正はすべて確定ゲートより前に済ませる**。前例も「波及追随を両方の確定ゲートより前へ」(同 `:126`)。

台帳へ追記する場合の次番号は **H-82**(現在 H-81 が最大・81 項目)。並行ブランチとの衝突は H-77 の既知問題なので develop と OPEN PR の最大値を確認する。

## 未解決・申し送り

### 裁定が必要(人間)

1. **4-6 から切り出してよいか。** 設計書 `:808` は 4-6 を「**onboarding の完成と v1.0 approved 化 + `win-setup` のランナー選定 + Phase 4 の受入判定**」の 3 点セットとして定義し、`win-setup` のランナー選定には「**後送りは認めない**(認めるなら 10.1 側の改訂が要る)」と明記されている。一方 `:819` は「4-1〜4-6 は論理スロットであり物理 PR 数ではない」とも述べる。**切り出しの可否を明示した決定は見つからなかった(不明)。**

2. **本タスクのスコープ。** 「①件数の是正だけ(PR レビュー)」「②①+ 本文の完成 + approved 化(確定ゲート)」「③②+ `win-setup` ランナー選定」のいずれか。②以上でないと approved 化は正本の要求(B・C)を満たさない。

3. **F-1 の複製数値をどこまで本タスクで触るか。** すべて現在値と一致しており、**是正の必要は無い**(陳腐化していない)。H-79 の観点で「腐らせない書き方へ変える」予防的リファクタは別タスクにするのが自然だが、台帳 `:1086`「(6)」の 3 タスク連続申し送りを本タスクで閉じる選択もある。

### 典拠が取れなかった事項(不明)

- `onboarding.md:33` の Node.js 版・mise/pnpm 導入方針を定めた決定記録
- `docs/adr/` および決定記録 `requirements-draft-pitchlog.md` の D-* に onboarding / WSL / Ubuntu を扱う項目(いずれも該当なし)
- ~~`.env.example` の内容が読めない~~ → **解消(2026-08-24 実測)**。Read ツールでは読める(`.env.example` は AGENTS.md 絶対規則 2 の明示的な例外・正本)。調査エージェントの「deny で読めない」は **Bash 経路のみ**の話で、`secret_guard` が**コマンド文字列**の `.env` 連なりを走査してブロックしたもの。ファイル自体の参照は禁止されていない。必要な変数は `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_PORT` / `DATABASE_URL`

### 本タスクで守る規律

- **H-79**: 是正時に「同じ概念を参照する全節を列挙したか」を問う → D-1 の 3 箇所(+ 10.1・13 章の確認)を同時に扱う
- **H-80**: 実測せずに原因を推定して正本へ書かない → 件数は本メモの実測(652)を典拠にし、除去方針は設計書 8.3 の明文を典拠にする
