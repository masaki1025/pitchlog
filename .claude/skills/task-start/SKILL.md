---
description: タスク着手の唯一の入口。Notion タスク・feature ブランチ・worktree・計画書雛形・worklog を一括準備する
argument-hint: "<タスク名 or NotionタスクURL>"
disable-model-invocation: true
---

# タスク着手(設計書 6.1 / 11.1 / 12.1)

## 前提チェック(NG なら中断して案内)

- env `PITCHLOG_NOTION_USER_ID` が未設定 → /setup-dev を案内して中断(担当者なしのタスクを黙って作らない)
- メインツリーの `git status` がクリーンであること(未コミット変更があれば先に退避を促す)

## 手順

1. **Notion**: $ARGUMENTS が URL ならタスクを取得、名前なら「✅ タスク」DB(`.claude/notion-map.json` の task_db)に起票する。**この時点ではステータスを遷移させない**(Git 側の準備が失敗すると中途状態が残るため — 遷移は手順 5):
   - プロジェクトリレーション = ⚾ baseball_scorering ページ(map の project_page)
   - 担当者 = env の自分/優先度/期限(わかる範囲)
   - 本文にテンプレどおり DoD 欄を用意
2. **ブランチ + worktree**: slug を決める(英小文字とハイフン)。種別はバグ修正なら `fix/`、それ以外は `feature/`。**worktree 名 = ブランチ名のスラッシュを `-` に置換**(例: `feature/sync-protocol` → `feature-sync-protocol`):
   `mkdir -p ../pitchlog-worktrees`(置き場を先に確保)→ `git fetch origin` → `git worktree add -b <type>/<slug> ../pitchlog-worktrees/<type>-<slug> origin/develop`
3. **計画書雛形**: worktree 内に `docs/features/<slug>/plan.md` を `docs/development/templates/plan-template.md` から作成し、frontmatter(slug / branch / **worktree 相対パス** / notion URL / created / **`Phase4スロット`**)を埋める(**`Phase4スロット` は人間に選ばせる** — `対象外` / `4-1`〜`4-6` / `P4-後` の 8 択を提示して選択を得る。**自動判定しない**(タスク名からの推定は独立入力にならない — 設計書 6.1・確定ゲート 12 周目 P1)。**空欄のままにしない** — `/task-done` が中断する。**Notion タスクの DoD に機械可読マーカー行 `Phase4スロット: <値>` があれば、人間の選択と突合し、食い違えば中断する** — マーカーは `/task-done` が `P4-後`・「Phase 4-6 再試行」を起票するときに書く〔設計書 13 章・確定ゲート 13 周目 P1〕。**マーカーが無いタスクは Phase 4 の分割スロットではない**ので選択は自由)(worktree フィールドは /implement ラッパーの検証に使われる — 単一の情報源。値は worktree ルート = plan.md から `../../..`)。design.md(詳細設計)はここでは作らない — **任意ファイルで、作成判断は /plan**(密度が高くなる場合に分離)
4. **worklog**: worktree 内に `docs/worklog/YYYY-MM-DD-<slug>.md` をテンプレから作成
5. **Notion 遷移**: worktree 作成まで成功したら、ステータスを `進行中` へ(綴りの正: `.claude/notion-map.json` — 推測しない)+ ブランチ名をタスクへコメントで記録
6. 以後の作業はすべて worktree 側(`../pitchlog-worktrees/<type>-<slug>`)で行う。ファイル編集はそのパス配下、git 操作は `git -C <worktree>` を使う

## 報告

worktree パス・ブランチ・Notion タスク URL と、次の導線(/investigate で下調べ → /plan で計画書)。
