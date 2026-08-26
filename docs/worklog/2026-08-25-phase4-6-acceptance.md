---
date: 2026-08-25
topic: Phase 4-6 — win-setup ランナー選定 + NFR-021 Phase 4 受入判定
branch: feature/phase4-6-acceptance
---

# 作業ログ: 2026-08-25 Phase 4-6(win-setup ランナー選定 + NFR-021 Phase 4 受入判定)

## やったこと

- /task-start: Notion タスク起票(Phase 4-6)・`feature/phase4-6-acceptance` の worktree 作成・計画書雛形と本ログの作成

## 着手時点の事実(調査済み)

- Phase 4 の順序(設計書 13 章)のうち **4-1〜4-5・予約レコード監査 PR・前提 PR(onboarding v1.0 approved 化 = TSK-253)はすべて完了**。残りは 4-6 のみ
- 予約レコード `docs/ops/nfr021-acceptance/2026-08-19T142916Z-phase4-phase4-seq001-reservation.md`(`attempt_seq` 1)が **未閉塞**。4-6 はこれを同一 `attempt_id` の結果証跡で閉じる
- `.claude/nfr021-invalidating-paths.json` の失効対象に `/backend/**`・`/frontend/**`・`/contracts/**` が含まれるため、**product 実装より先に 4-6 を閉じる必要がある**(実装コミットが受入証跡を失効させ続ける)

### /investigate(調査サブエージェント 3 並列)

spec-checker(要件突合)/ decision-tracer(決定経緯)/ 広域探索(機構実態)を並列で投げ、`docs/features/phase4-6-acceptance/research.md` へ統合した。

## 決定

- **裁定 1: 受入は `develop` ではなく feature ブランチのツリーで実施する。** onboarding 2 章が develop への切り替えを指示する理由は注記(`onboarding.md:206`)のとおり **`main` を避けること**であり、develop 限定の根拠は書かれていない。受入 README `:191` は「**予約を含む候補ツリー**で完走」と定めており、候補ツリー = `T` = feature ブランチ上のコミットになる。ただし approved な手順の逐語からずれるため、判定者の了解を計画書へ記録する(research.md F-1・G-2)
- **裁定 2: onboarding 6 章 項目 6 は negative test。** `codex exec "test"` を codex_guard がブロックすることが合格条件(`onboarding.md:312`)で、CLAUDE.md の規約と矛盾しない(research.md F-2)

### /research(Codex 委任・Web 調査)

win-setup ランナー選定の判断材料を Codex へ委任(read-only + live search + terra high)。**出力を鵜呑みにせず、5 点を自分で URL 再取得して裏取り**した(設計書 9.2)。結果は research.md H 節。

- **裁定 3(新規事実): `Vampire/setup-wsl` は `Ubuntu-26.04` に非対応**(受理は `Ubuntu-24.04` まで)。受入プロファイルが要求するディストリを CI で再現する手段が未確立である
- **裁定 4(本リポジトリ固有の決定的制約): scheduled workflow は default branch でしか走らない**。本リポジトリの default branch は `main`(実測)で、**`origin/main` には `backend/`・`frontend/`・`docker-compose.yml`・`mise.toml` が無い**(`git ls-tree` 実測)。かつ `main` が進むのはリリース時だけで `/release` は `P4-後` まで中断されている。→ **win-setup の定期実行は、どの案を採っても初回リリースまで発火しない**。この制約は設計書にも前回調査にも記載が無い
- Codex の推奨は (c)。ただし本調査者の評価では、(a) の週次 Linux 検査は既存 CI と重複し、(b)(c) は上記 2 点により**今 実装を確定させる根拠が弱い**。台帳 H-68 の分類でいう「(B) 実装時に決めれば足りる」側にあたる

### 決定(PO・2026-08-25)

- **win-setup ランナー選定 = (d)**「WSL 固有部分は self-hosted runner または手動チェックリストへ寄せる」。**GitHub-hosted ランナーは採用しない**
- **4-6 の範囲は「選定の記録」まで。`ci.yml` への実装は含めない**(導入時期は 10.1 の表が定める「Phase 4 以降」に従う)
- この扱いは設計書 `:810` の「後送りは認めない」に反しない — 禁じられているのは**選定**の後送りであり、選定は本タスクで確定させる
- **(d) の下位二択は「手動チェックリスト」に一本化**する。self-hosted runner は将来の選択肢として台帳へ送る。これで**未決を一切残さず**、要件書 `:1037` の暫定方針「手動再現」とも一致する

### /plan(実装計画書の作成 — 計画レビュー 5 周で収束)

`review normal` を 5 周。**P0 は 4 → 1 → 2 → 1 → 0**、P1 は 4 → 4 → 2 → 0 → 0。**全件採用・不採用 0 件**。`計画レビュー周回` は 4(収束確認の 5 周目は数えない)。**2026-08-26 に PO 承認**。

指摘の大半は「機構が実際にどう振る舞うか」の確認であり、**計画段階で潰さなければ実機受入の完走後に証跡が失効して全部やり直しになる**類だった。主要な是正 8 件:

| # | 当初の誤り | 是正 | 典拠 |
| --- | --- | --- | --- |
| 1 | `/pr` を `E` より前に実行する案 | **成立しない**(`/pr` がクローズ処理コミットを作り HEAD が動く)。`/pr` を受入完走後に 1 回だけ実行し、**そのクローズ処理コミットを `E`** とする | `.claude/skills/pr/SKILL.md:11` |
| 2 | 3 節で「本 PR では変更しない」と記載 | `check_plan_docs_sync.py` は**リテラル「反映なし」**を見る。全非該当行を統一 | `scripts/check_plan_docs_sync.py:478` |
| 3 | `E` の push 手順が無い | `--match-head-commit <E>` は remote head が `E` でないと失敗する。マージ統制を 9 手順の表へ | — |
| 4 | 受入そのものが不合格の経路が無い | `/task-done` は PR **MERGED** が前提。受入不合格は別ブランチの監査 PR で予約を閉じる経路へ | `.claude/skills/task-done/SKILL.md:13` |
| 5 | 索引更新をステップ 2 に配置 | `check_docs_status.py` は状態・版に加え**索引日付が変更履歴の最新日付以上**であることも検査。ステップ 1 で状態・版・日付を同一コミット更新し、approved 化は `/finalize-doc` 手順 6 へ | `scripts/check_docs_status.py:693` |
| 6 | **detached checkout で `T` を試験** | **撤回**。`git_guard.py` の `current_branch` は detached 時に文字列 `HEAD` を返し `PROTECTED` にも「解決不能」にも該当せず**ガードが発火しない** → onboarding 6 章 項目 5 が落ちる。**`T` を指すローカル `develop` ブランチ**で試験する形へ | `.claude/hooks/git_guard.py:467-473` |
| 7 | CI「全ジョブ緑」 | 文書のみの PR では成立しない。**success 必須 7 本**(secrets/docs-lint/core-guard/harness/nfr021-append-only/**frontend-changes**/**backend-changes**)、**skipped 許容は frontend・backend の 2 本のみ** | `.github/workflows/ci.yml:107-175` |
| 8 | 裸の `git push` | 本ブランチは `/task-start` が `origin/develop` 起点で作ったため **upstream が `origin/develop`**(実測)。宛先を明示した `git push -u origin feature/phase4-6-acceptance` へ | `.claude/hooks/git_guard.py:340` |

**実行不能な合格条件を 2 件書いていた**のも収穫だった — ① `grep 'ランナーは未決' = 0 件` は変更履歴と 13 章に歴史的事実として残るため達成不能(検査を 10.1 節内へ限定)② 「本コミットの OID を `T` として記録」は自己参照で不可能(push 後に取得し、記録先を証跡と `E` の worklog へ)。

### ゲート区分の判断を改めた(重要)

当初は設計書 10.1 の更新を**実装追随(版は上げない)**と判定していた。前例 3 件(v1.8 の `nfr021-append-only` 行追加・v1.8 の `harness` 行現行化・v1.3 の codex-plan-status-guard)を根拠にしたが、**いずれも「確定済み規範の実装・現行化」であり本件とは性質が違う**。本件は「CI の定期ジョブ候補」から「GitHub-hosted を採らず手動運用へ一本化」への変更で、**行の意味と実行主体そのものを変える**。加えて `:652`「**ランナー未決の間は**本ゲートのみが根拠」という条件付き規定を恒常の規定へ変える。**PO 裁定(2026-08-25)により版繰り上げ v1.10 + `/finalize-doc` を 4-6 内で通す**ことにした。

### 確定ゲート(2026-08-26)— タスクの再スコープ

**本タスクは「Phase 4 完了時受入の前提 PR(第 2 号)」へ再スコープされた(PO 決定 2026-08-26)。**

- **確定ゲート 2 周目の P0**: `onboarding.md` v1.1 の approved 化と受入判定を同一の 4-6 PR で行うと、10.1 実施順序 ① の「**`develop` に統合済みの** approved 版で完走」と v1.9 の「**判定単位は `develop` の状態**」を満たせず、**v1.9 が閉じた前提と結論の循環が再発する**。検証器は `T` 内の blob と `status: approved` は検査するが、**その版が受入前に `develop` へ統合済みだったかは検査しない**
- **したがって: 本タスク = 前提 PR(第 2 号。正本 3 本 = 設計書 v1.10 / `onboarding.md` v1.1 / 受入証跡 README v1.2)/ 4-6 の受入判定 = 別タスク・別ブランチ**
- **「残るのは 4-6 のみ」という上記の記述は、この再スコープ前のものである。** 現在は **前提 PR(第 2 号)→ 4-6** の 2 本が残っている
- 13 章へ第 2 号の節を新設し、対象・順序・マージ条件・**本数(7 → 8 本)**・歯止めを確定した。**v1.9 の歯止めが定める「版繰り上げ + 7.3 の確定ゲートで改めて確定する」手続に従ったもので、類推適用ではない**(確定ゲート 3 周目で「循環と自己定義については問題なし」と判定)

## 未決・次の一歩

**以下は再スコープ前の記述であり、現行の順序は計画書 4 節が正**(失効対象パスの制約そのものは有効だが、「同一 PR 内で `T` より前」ではなく「**前提 PR として先に `develop` へマージする**」形に変わった)。

- **最大の発見**: 失効対象パスの正本は `default: "invalidating"` で、allowlist は 3 ディレクトリのみ。**設計書・要件書・索引・台帳はすべて失効対象**である(受入証跡 README は allowlist 配下だが、実行用手順そのものなので順序上は `T` より前に置く)

**現行の次の一歩**:

1. 確定ゲートを収束させ、**正本 3 本(設計書 v1.10 / `onboarding.md` v1.1 / 受入証跡 README v1.2)を approved 化**する
2. ステップ 2(台帳へ follow-up 2 件 + 観測 1 件・索引の台帳行)
3. `/check` → `/pr` → 通常 PR 要件でマージ(**受入判定は課さない**)
4. **4-6 の受入判定タスクを別 slug で起票**し、本タスクと相互リンクする
5. **要件書 10 章 未決事項行の決着記録タスク**を起票し、`P4-後` の着手前提として明記する
