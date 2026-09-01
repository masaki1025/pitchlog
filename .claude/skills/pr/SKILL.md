---
description: PR 作成の唯一の入口。クローズ処理のコミット → 正本反映の突合 → push → PR 作成(コア領域なら人間逐行確認チェックを付与)
argument-hint: "[feature slug]"
disable-model-invocation: true
---

# PR 作成(設計書 6.1 / 6.3 / 7.6)

すべて worktree 側で行う(`git -C <worktree>`)。

## 1. クローズ処理(この変更を最後のコミットとして PR に含める — マージ後の develop 直接編集を不要にする)

1. 計画書 frontmatter を `status: in-review` に更新する(merged は Git に置かない — 完了は PR 状態・Notion・worktree 除去から導出する)
2. worklog に結果サマリ(何を実装し何を正本へ反映したか)を追記して締める
3. **ハーネス運用評価台帳への追記を判断する**(`docs/development/harness-evaluation.md`)。**判断するのは PR 作成者**で、**最終コミットを作る前**に行う:
   - **該当する**(このタスクでハーネス運用上の知見が得られた)場合は、**同一 PR で** ① 計画書 3 節の「影響する正本」へ宣言を**先に**追記 → ② 台帳へ `H-*` を追記 ③ 台帳の変更履歴表に 1 行追記(**`H-*` の追記では版を上げない** — 7.6-3 前段)④ `docs/README.md` の台帳行の最終更新日を現行化。②〜④ は同一コミットにする
   - **該当しない**場合は **worklog に「台帳への追記なし」と理由を残す**(判断したことを記録に残し、**忘れたのか判断したのかを区別できるようにする**)
   - 単発事象で傾向として確定していないもの、**制御目的の典拠が確認できず優先度を判定できないもの**は台帳の `## 候補` 節へ(`H-*` を与えない)
4. 上記と未コミットの文書変更をすべてコミットする

## 2. 突合(いずれか NG ならブロックして案内)

1. **未コミット確認**: `git -C <worktree> status --porcelain` が空であること(残があれば 1 に戻る)
2. **正本反映(双方向で突合する)**: 計画書 3 節の宣言と `git -C <worktree> diff origin/develop...HEAD --name-only` を突合し、**次のどちらでも中断**する:
   - worktree 側で `uv run python scripts/check_plan_docs_sync.py --plan docs/features/<slug>/plan.md --base origin/develop` を実行して機械突合する(`--plan` を省略するとブランチ名から導出)。**exit 1 なら中断**する。**「反映宣言なのに差分にない」は plan status が `in-review` のときだけ違反(`active` では警告のみ)**であり、手順 1-1 で `in-review` へ更新する通常経路では違反として扱われる。
   - **宣言済みで未反映**の正本がある → /sync-docs を案内して中断
   - **差分にあるのに未宣言**の正本がある → 計画書 3 節へ宣言を追記してから再突合(**片方向だと、正本を更新したのに宣言し忘れた場合に素通りする** — 実例: `decision-tracer.md` の宣言漏れを人手で拾った)
   - **突合対象**: `docs/README.md` / **索引に掲載されている正本** / 新設する正本の配置先。**除外**: `docs/features/**`・`docs/worklog/**`・`docs/legacy/**`・`docs/development/templates/**`・`.claude/**`・リポジトリ直下の規約ファイル(`AGENTS.md`・`CLAUDE.md`・`README.md`)。**全 `--name-only` を逆突合してはならない**(正本外だが同一 PR で運ぶファイルで誤って中断する)。正本外のファイルは 3 節の別枠(「正本体系外だが同一 PR で更新するもの」)で宣言する
3. **現在地導出の突合**: `uv run python scripts/feature_status.py` を実行し、**出力を PR 本文へ転記する**(警告の有無にかかわらず転記する — 転記しないと実行証跡が残らない)。**警告が出ても中断はしない**(非ブロッキング。人間が是非を判断する)。**限界**: 本手順は PR **作成前**の 1 点であり、その後の追加 push・レビュー往復・マージ時点での再実行は保証しない(機械化は台帳 `H-50` で追跡 — ハーネス設計書 6.1)
4. **品質**: /check が本セッションで未実行または失敗なら中断

## fast path 分岐(設計書 6.1。人間の事前 OK 済みが前提)

- 計画書は /task-start の**雛形がメタデータとして残っている**前提(承認・ステップ表・3節の記入は不要)。手順 1-1 の status 更新と frontmatter(branch・notion)の参照は通常どおり行う
- 突合 2-2(正本反映)は「正本への影響がない」ことの差分確認に置換。2-3(/check)は同じ
- PR 本文に**短縮計画**を必須記載: 目的 / 変更内容 / 確認方法 / 人間の事前 OK への言及
- 以降(push・PR 作成・Notion 遷移)は通常経路と同じ

## 3. 作成

1. `git -C <worktree> push -u origin <branch>`(承認付き。branch は計画書 frontmatter の `branch` — `feature/*` と `fix/*` の両方に対応)
2. `gh pr create --head <branch> --base develop`(**--head を明示** — メインツリーのカレントブランチに依存しない)。本文は `.github/pull_request_template.md` に沿って生成:
   - 概要 / Notion タスク URL / 計画書リンク / 正本反映の要約 / テスト結果
   - **コア領域/検査経路判定**: 変更ファイルは `git diff --no-renames --name-only origin/develop...HEAD` で取得し、rename は**旧・新両パス**を base 側 core-areas.json(`git show origin/develop:.claude/core-areas.json`)の各領域 `paths` と `guard_paths` の**両方**に突合する。コア領域該当 → テンプレのコメントアウト部を有効化(adversarial レビュー + 逐行確認の 2 項目)。guard_paths のみ該当 → 逐行確認チェックのみ有効化。**チェック文言は `scripts/core_guard.py` の `REQUIRED_CHECK_TEXT` と完全一致**させる(CI の core-guard ジョブが `- [x]` を機械検査する — 文言を変えない)。チェック行の直後に**実施記録行** `- 実施記録: 対象= 範囲= 方法=` を含める(設計書 6.3 — 値は逐行確認を実施した人間が記入する。PR 作成時は空欄で置く・機械検証なし)
   - **fast path 判定**: fast の場合はテンプレの fast path コメントアウト部を有効化する
3. Notion タスクの URL プロパティに PR URL を記録し、ステータスを `確認待ち` へ(綴りの正: `.claude/notion-map.json` — 推測しない)。「確認待ち時の依頼事項」欄にレビュー観点を書く(ポータルの規律)

## レビュー導線の案内

反対側レビュー(Codex 実装 → Claude 一次レビュー〔要件適合・規約・NFR-018 — spec-checker 併用可〕/ Claude 直実装 → `python .claude/scripts/codex_run.py review normal -` に差分レビュー指示)→ コア領域は敵対レビュー(`review adversarial`)+ 人間逐行確認 → CI 全グリーン → **人間がマージ**。プラグイン `/codex:*` は使わない(経路はラッパーに一本化)。

- **差し戻しが発生したら**(PR の OPEN/CLOSED を問わない): Notion ステータスを `差し戻し` へ(指摘要約をタスクへコメント — notion-map.json)。**修正の再開時は、先に計画書 frontmatter を `status: in-review → active` に戻してから** Notion を `進行中` に戻す(現在地導出が「実装中(差し戻し修正)」を示す — scripts/feature_status.py。この状態更新コミットにはステップ記法を付けない)。修正は**通常経路では** /implement の `--resume` でステップ単位に行う(修正も 1 まとまり 1 コミット)。**fast path の差し戻しは `codex_run.py fast` の新規実行または Claude 直修正**で行う(`--resume` は使わない — fast にステップ表・保存セッションはない)。**差し戻し修正のたびに fast の 3 条件(非コア・小差分・正本影響なし)と人間の事前 OK を再確認**し、満たさなくなったら通常計画(/plan)へ切り替える。切り替え時は plan frontmatter を `status: active`・`実行方式: 通常`・`承認: 未` へ**一括で**揃える(中途半端な遷移は現在地導出が誤表示する — 設計書 6.1)
- **修正・検証完了(再レビュー依頼)**: 計画書 frontmatter を `active → in-review` に戻し、Notion を `確認待ち` へ。**OPEN の既存 PR には `gh pr create` を行わず再レビュー依頼のみ**。CLOSED の場合は reopen または新 PR(本スキルの手順 3)による
