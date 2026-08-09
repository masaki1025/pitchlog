---
feature: ci-foundation
type: research
date: 2026-08-10
---

# 調査メモ: Phase 3 — CI 先行分(secrets・docs-lint・harness)+ ブランチ保護

## 問い

Phase 3(CI 先行分 + ブランチ保護 + github-setup.md)の実装計画を書くために、(1) 要件書上の根拠と制約、(2) 設計書・過去決定で確定済みの仕様と未決事項、(3) リポジトリ現状の機構(CI が動く前提・障害点)を確定する。

調査体制: spec-checker(要件突合)・decision-tracer(決定経緯)・Explore(リポ実査)の 3 並列。legacy-analyst は本テーマに旧システムとの接点がないため除外。

## 結論(要約)

- CI 必須・直コミット禁止の**枠組み**は要件書に直接根拠がある(7.3「PRベース+CI全グリーン必須」・NFR-019・DoD②)。**具体的手段**(gitleaks・docs-lint・hooks テスト・GitHub ブランチ保護)はすべてハーネス設計書 10.1/10.2 が出典で、要件書との矛盾はない
- **Phase 3 のジョブ集合が文書間で不一致**(10.1 表 = secrets/docs-lint/core-guard/harness の 4 本、13 章 = 2 本、worklog = 3 本)。core-guard の扱いは計画で要決定(core-areas.json の paths は Phase 4 まで空)
- 確定済み: secrets = **gitleaks** / 保護対象 = **main と develop の両方**(main のみは要件書 7.3 に矛盾)/ 「直 push 禁止・PR 必須・CI 必須・force-push/削除禁止(管理者含む)」/ 手順は github-setup.md に正本化 + `scripts/setup_branch_protection.py`(gh api)
- 未決(計画で決める): docs-lint のツールと検査範囲(設計書の「正本 frontmatter 検査」は**現状の正本の実体〔変更履歴表・frontmatter なし〕と食い違う**)・gitleaks の実行方式/範囲・`on:` トリガーと paths filter・必須チェック名・レビュー必須数・Rulesets vs classic
- リポ現状: `.github/workflows/` なし・ルート pyproject は pytest のみの harness プロジェクト(uv.lock コミット済み)・テストは Linux 前提(geteuid)で ubuntu ランナー可。ただし **HEAD ブランチ名依存・実行パス依存のテストが 2 件**あり、CI トリガー設計と /check 実行場所に制約を課す
- Web 調査(Codex /research・2026-08-10)で技術選定は確定: gitleaks-action v3.0.0 / setup-uv v9.0.0 / lychee-action v2.9.0(いずれも SHA ピン留め・タグ→SHA は本セッションで実照合済み)
- **ブロッカー発見**: リポジトリは個人(masaki1025)所有の private で、**所有者は Free プラン — branch protection / Rulesets が使えない**(rulesets API が 403「Upgrade to GitHub Pro or make this repository public」を返すことを実機確認)。Phase 3 の「ブランチ保護適用」は **PO 判断(Pro 化 / public 化 / Org 移管 / 保護の後送り)が必要**

## 詳細と典拠

### 1. 要件書上の根拠(spec-checker)

正本: `docs/requirements/requirements-pitchlog-2026-07-22.md`(v1.7)

| 項 | 文言(要旨) | 本タスクへの含意 | 典拠 |
| --- | --- | --- | --- |
| 7.3 | 「Git Flow運用(main/develop直接コミット禁止)を新リポジトリでも適用。PRベース+CI全グリーン必須(NFR-019)」 | ブランチ保護の設定内容の直接根拠。**develop も保護必須**(main のみだと矛盾) | :748-750 |
| NFR-019 | 「PRごとにCIで自動実行、全グリーンでないとマージ不可」 | マージブロック機構化は Must。列挙テスト (a)〜(d) は製品コード用 = Phase 3 のジョブは列挙外だが「含む」であって上限ではなく矛盾なし | :672-675 |
| NFR-014 | 「リポジトリに含めず環境変数で管理」「測定方法: リポジトリの走査」 | secrets スキャンは測定方法の機構化として適合。gitleaks というツール名は要件書にない | :647-650 |
| NFR-021 | 「開発環境はWindows 11で完結する」 | CI ランナー OS の規定はなし(開発環境の規定)。ただし **CI ジョブに bash/jq 依存を持ち込むと緊張**(設計書 :372 も hooks を Python のみとする理由に明記)。NFR-021 の検証自体は Phase 4 のゲート(設計書 :672) | :682-685 |
| 8章 DoD② | 「CI全グリーン: NFR-019 のテスト一式がすべて成功」 | CI はリリース判定の直接前提。secrets/docs-lint/harness は DoD② の列挙外(必須化は矛盾しない) | :759 |
| 8章 DoD⑦ | ドキュメント現行化 | docs-lint は補助手段になり得るが要件書は機械検査を要求していない | :764 |
| 7.1 | 技術スタック変更に承認 | GitHub Actions は実行時スタック列挙外 = 抵触しない | :734 |

- 2.2 Won't に CI・リポ運用関連の項目はなし(:62-77)。GitHub Secrets の利用は NFR-014「環境変数で管理」と整合(リポ内平文ではない)
- 改善台帳: Phase 3 を直接規定する項はなし。思想的根拠は追記候補「新リポではCI・テスト規約を最初から定める」(`docs/improvements-from-baseball-scoring.md:218`)・I-2(:24)・I-27(:211)

### 2. 設計書・過去決定(decision-tracer)

正本: `docs/development/dev-harness-design-2026-08-07.md`(v1.0 approved)

**10.1 ci.yml のジョブ表(:526-538)** — Phase 3 指定は以下の 4 本:

| ジョブ | 内容 | 確定粒度 | 典拠 |
| --- | --- | --- | --- |
| `secrets` | gitleaks(NFR-014 の機構化)「コード前から常設」 | ツール名確定。実行方式(Action/CLI)・範囲(差分/全履歴)・`.gitleaks.toml` 要否は**不明** | :533 |
| `docs-lint` | markdown リンク切れ検査・正本 frontmatter 検査(status 必須等) | ツール名**不明**。検査対象範囲**不明**(§4 の食い違いあり) | :534 |
| `core-guard` | コア領域パス変更検知 → 人間逐行確認の必須チェック化(P1-11) | `.claude/core-areas.json` の paths は**現状すべて空**(Phase 4 で埋める — core-areas.json:2) | :535 |
| `harness` | hooks・ラッパーの pytest(`tests/`) | 実体は `uv run pytest tests/`(8.3 :383・/check SKILL.md:10-12 と整合) | :536 |

- 横断規定: concurrency で旧実行キャンセル・uv/pnpm キャッシュ(:539)、「CI 全ジョブ green をマージ条件」(:540)
- `on:` トリガー・Phase 3 ジョブの paths filter は**記載なし = 計画で決める**(paths filter の明記は backend/frontend 行のみ :529-530)
- Phase 4 との境界: backend・frontend は Phase 4(:529-530, :672)、consistency・e2e は実装期(:531-532)、win-setup は Phase 4 以降(:537)、deploy.yml 雛形(:130)の導入 Phase は記載なし

**10.2 ブランチ保護(:542-545)**:

- 「main / develop: 直 push 禁止・PR 必須・CI 必須・force-push/削除禁止(管理者含む)」(:544)
- 「設定手順は `docs/development/github-setup.md` に正本化し、`scripts/setup_branch_protection.py`(gh api 使用)で再現可能にする」(:545)。scripts/ は Python・OS 非依存(:140)。permissions 上 `gh api` は ask(:364)
- 未決: レビュー必須数・required status checks に入れる具体ジョブ名・strict 可否・Rulesets vs classic・冪等性/dry-run 仕様

**github-setup.md**: 言及は 4 箇所(:545, :147, :300, :671)。明示された中身は「ブランチ保護の設定手順」のみ。`docs/development/` は確定ゲート必須(:300、AGENTS.md:14)→ **新設正本として /finalize-doc(敵対レビュー+人間承認)の対象**。索引 `docs/README.md`(:5-15)に現状未掲載

**13 章 Phase 3 完了条件(:671 逐語)**: 「保護設定が有効・PR で CI が回る」

**踏んではいけない過去決定**: PR 自動レビューは Phase 5(:547-552)/ openai-codex プラグイン不使用(:66, :408, :722)/ CI は Notion に依存しない(:610)/ スクリプトは Python・OS 非依存(:140, :372)

### 3. リポジトリ現状(Explore)

- `.github/` は `pull_request_template.md` の 1 本のみ。**workflows・YAML ファイル・CODEOWNERS・gitleaks/secretlint/pre-commit 設定はすべて存在しない**
- ルート `pyproject.toml`(全 13 行): `name = "pitchlog-harness"`・`requires-python = ">=3.12"`(:7)・依存は `dev = ["pytest>=8"]` のみ(:9-10)・`testpaths = ["tests"]`(:12-13)。**uv.lock はコミット済み**。`.python-version` なし。ruff/ty 等のツール設定なし。`backend/`・`frontend/`・`contracts/`・`scripts/`・`package.json` は**未存在**
- `tests/test_hooks.py`(525 行・test 関数 42 本・parametrize 展開で 103 ケース): python は `sys.executable`(:20)で venv 可 / `git init -b` 使用 = **git ≥ 2.28 必須**(:227)/ git identity 不要(`-c` 明示 :229-231)/ `os.geteuid`・`chmod 0o000` で **Linux/macOS 前提**(:429-438。Windows 不可・root 実行時 1 件 skip)/ ネットワーク・DB・Docker 依存なし
- `.claude/hooks/` 7 本のうち **format_on_save.py のみテストなし**(backend/frontend 未作成で実質未使用)。`.claude/settings.json` のフック配線(JSON 妥当性・パス実在)を検証するテストは存在しない
- `.env` 系ファイルは未作成(`.env.example` も未作成)。`.gitignore` に NFR-014 パターンあり(:8-11)

### 4. 裁定・注意事項(エージェント報告の突合)

1. **docs-lint の「正本 frontmatter 検査」は現状の実体と食い違う**: 正本(requirements・design・ADR・onboarding)は frontmatter を持たず、**変更履歴表**で状態管理している。しかも表形式が 2 種類に分裂(`| 版 | 日付 | 変更内容 | 状態 |` = design/onboarding、`| 版 | 日付 | 変更内容 | 変更者 |` = requirements。ADR はメタ表)。frontmatter を持つのは plan/worklog/テンプレのみ → **docs-lint の検査仕様は「現実に合わせて定義」するか「正本側を統一」するかの二択。計画で決める**
2. **CI トリガー設計への制約(テストの環境依存 2 件)**:
   - `test_git_guard_allows_feature_push_and_commit`(:47-50)は実行リポジトリの HEAD ブランチ名に依存 — **develop/main をチェックアウトした状態で pytest を回すと落ちる**。PR イベント(detached HEAD)なら通る → harness ジョブは pull_request トリガー前提が安全。**ローカルの /check をメインツリー(現在 develop)で回しても同様に落ちる**点は運用注意
   - `test_wrapper_rejects_fast_outside_worktree`(:378-380)は実行パスに `pitchlog-worktrees` を**含まない**ことに依存 — GitHub ランナー(`/home/runner/work/...`)は問題ないが、**worktree 内で pytest を回すと fast ガードを通過して実 codex 起動を試みる**。/check は worktree ではなくメインツリー側(かつ非保護ブランチ)で回すか、テスト側の改修が必要
3. **要件書 1.2 の「改善台帳 I-1〜I-24」は台帳の現状(I-27 まで)と乖離**(spec-checker 発見)。本タスク範囲外だが docs-lint/sync-docs の検討材料として記録
4. Phase 3 ジョブ集合の不一致(10.1 = 4 本 / 13 章 = 2 本 / worklog = 3 本)は両エージェントの報告が一致しており原典確認済み。**設計書 10.1 の表が最も詳細な正**とみなすのが自然だが、core-guard は paths 空の間「検知 0 件で常に green」になるため、Phase 3 で入れる価値(P1-11 の機構を先に立てておく)と虚偽の安心感のトレードオフを計画で判断する

### 5. Web 調査(/research — Codex 委任・調査確認日 2026-08-10)

委任: `codex_run.py research`(read-only + live search・terra high)。重要事実は本セッションで URL・API・タグ照合により追検証済み(下記「検証」)。

**(1) secrets ジョブ = gitleaks/gitleaks-action v3.0.0(SHA ピン留め)**

- 現行版 v3.0.0(Node 24 ランタイム)。**v2 は 2026-09-16 に GitHub ホストランナーで動作不能になる予定**のため新規採用不可
- ピン留め: `gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e # v3.0.0`(**検証**: `git ls-remote` でタグ→SHA 一致確認済み)
- ライセンス: **個人(User)所有リポジトリは private/public を問わず GITLEAKS_LICENSE 不要・無料**。Organization 所有はキー必要 → 将来 Org 移管する場合は CLI 直接実行への切替も選択肢
- 既定範囲: PR = PR のコミット範囲、push = push 範囲(全履歴ではない)。`workflow_dispatch`/`schedule` + `fetch-depth: 0` で全履歴。**初回に一度だけ全履歴監査を実施し、以後は差分検査**が推奨形
- `.gitleaks.toml` 不要(組込み既定ルール)。誤検知は `.gitleaksignore` で対処
- GitHub 純正 secret scanning は User 所有 private では利用不可(公開リポは無料)
- 参照: https://github.com/gitleaks/gitleaks-action/releases/tag/v3.0.0 / https://github.com/gitleaks/gitleaks-action/blob/master/LICENSE.txt / https://github.com/gitleaks/gitleaks#load-configuration
- 初回全履歴監査用 docker イメージ(**検証**: buildx imagetools で照合・2026-08-10): `ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f`(gitleaks 本体最新 = v8.30.1)

**(補) actions/checkout = v7.0.1(2026-07-20 公開)**

- ピン留め: `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`(**検証**: gh api でタグ→SHA 照合済み・2026-08-10)
- 既定 fetch-depth は 1 — base...head の diff や全履歴スキャンには fetch-depth の明示が必要

**(2) uv セットアップ = astral-sh/setup-uv v9.0.0 + `uv python install 3.12`**

- ピン留め: `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0`(**検証**: gh api でタグ→SHA 一致確認済み)
- `enable-cache: true` + `prune-cache: true`(GitHub ホストランナー推奨)。キャッシュキーは OS・Python・uv.lock 等
- Python は `actions/setup-python` 併用より **uv 自身に解決させる**(`uv python install 3.12` → `uv sync --locked --dev` → `uv run pytest`)。`--locked` でコミット済み uv.lock との一致を強制
- 参照: https://docs.astral.sh/uv/guides/integration/github/ / https://github.com/astral-sh/setup-uv/releases/tag/v9.0.0

**(3) docs-lint(リンク検査)= lycheeverse/lychee-action v2.9.0 + `--offline`**

- ピン留め: `lycheeverse/lychee-action@e7477775783ea5526144ba13e8db5eec57747ce8 # v2.9.0`(lychee 本体 v0.24.2。**検証**: `git ls-remote` でタグ→SHA 一致確認済み)
- `--offline --root-dir "$(pwd)"` でネットワーク遮断・リポ内相対リンクのみ検査(主目的に合致)。外部 URL 検査は後から追加可能
- markdownlint-cli2 はリンク到達性を検査しない(書式 lint)ため代替にならない。併用は任意
- **日本語パスの動作保証は公式資料に記載なし** → 導入 PR に日本語ファイル名の fixture を 1 つ含めて実ランナーで確認する
- frontmatter/status 検査は既製ツールにないため自前スクリプト(Python・scripts/ に配置)になる見込み — §4-1 の決定と連動
- 参照: https://github.com/lycheeverse/lychee-action/releases/tag/v2.9.0 / https://github.com/lycheeverse/lychee/releases/tag/lychee-v0.24.2

**(4) ブランチ保護 = Rulesets 推奨、ただしプラン制約が先決**

- **実機確認(2026-08-10)**: `gh api repos/masaki1025/pitchlog/rulesets` → **403「Upgrade to GitHub Pro or make this repository public to enable this feature.」** = 所有者 Free プラン + private では branch protection / Rulesets とも利用不可
- 選択肢: **個人 Pro(最小変更・推奨)**/ public 化(未公開ドキュメントの機密性から通常不適)/ Org 移管は **Team 以上でないと解決しない**(Org Free も不可)/ 保護の後送り(CI のみ先行導入、hooks のローカル強制で暫定運用)
- 方式: 新設なら Rulesets が現行推奨(積層・bypass 管理・閲覧性)。classic も廃止はされていない
- 要求機能の対応(Rulesets): required status checks = job 名完全一致 + `strict_required_status_checks_policy: true` / force push 禁止 = `non_fast_forward` / 削除禁止 = `deletion` / 管理者適用 = `bypass_actors: []`(所有者が設定自体を変えられる点は残余リスク)
- 冪等適用: `GET /repos/{o}/{r}/rulesets` で名前→ID 解決 → あれば PUT・なければ POST。classic なら `PUT /repos/{o}/{r}/branches/<branch>/protection`(全置換なので読み取り→生成→PUT を一単位に)
- job 名はワークフロー横断で一意にする(required check の曖昧化防止)
- 参照: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets / https://docs.github.com/en/rest/repos/rules / https://docs.github.com/en/rest/branches/branch-protection

## 未解決・申し送り

- **PO 判断済み(2026-08-10)**: ブランチ保護は**後送り(選択肢 d)**。Phase 3 は CI のみ先行し、保護ブランチ規律は hooks のローカル強制で暫定運用。github-setup.md に制約(Free + private で不可)・再開条件(Pro 化等)・適用予定の設定内容(Rulesets)を記録して将来の適用に備える。※設計書 10.2/13 章 Phase 3 の完了条件「保護設定が有効」との差分は計画書 3 節(影響する正本)で扱う
- **計画で決める事項**: core-guard の Phase 3 導入可否 / docs-lint の frontmatter 検査仕様(§4-1 の二択。リンク検査は lychee で確定、status 検査は自前スクリプト)/ gitleaks の初回全履歴監査の実施方法 / 3〜4 ジョブの `on:` トリガーと paths filter / required status checks の具体名と strict 可否 / レビュー必須数 / setup_branch_protection.py の冪等性・dry-run(Rulesets API 前提)/ github-setup.md の記載範囲と /finalize-doc をどのタイミングで通すか
- **Web 調査は完了(§5)**: ツール選定 3 件は SHA 照合済み。Rulesets 推奨・プラン制約は実機確認済み
- **テスト改修の要否**: §4-2 の 2 件(HEAD 依存・パス依存)を CI 導入と同時にテスト側で頑健化するか、トリガー設計で回避するか
- format_on_save.py が唯一テスト未カバー(Phase 4 で backend/ 出現時に追加が自然)
- `.claude/settings.json` のフック配線の妥当性検査(JSON・パス実在)は現状どの層にもない — docs-lint ならぬ harness-lint として拾うかは任意
