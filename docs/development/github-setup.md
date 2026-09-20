---
status: approved
---

# GitHub リポジトリ設定手順(ブランチ保護と CI Secrets)

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-08-10 | 初版起案(ci-foundation / Phase 3): ブランチ保護のプラン制約と実測・暫定運用・再開手順・CI 必須チェック名・Secrets 方針を正本化 | draft |
| 0.2 | 2026-08-10 | 敵対レビュー(判定=要修正・P0×3/P1×6)の全件反映: 暫定運用を「機械的強制でなく管理手続」として正確化(git_guard の適用範囲・チェック対象 = コア領域∪guard_paths・最新 HEAD 基準)/ core-guard 循環参照は**保護有効化後も未解消**と境界を明記 / gitleaks ローカル監査コマンドを worktree 対応 + `--redact=100` 必須へ修正(NFR-014)/ Ruleset 冪等適用の前提・検証・復旧手順 / context 名の将来変更耐性 / `--no-ff` 整合(allowed_merge_methods)/ 10.2 自動再現要件の未達を明示 / NFR-019 参照修正 | draft |
| 0.3 | 2026-08-10 | 敵対レビュー 2 周目(P0×1/P1×3)の反映: **`pull_request: edited` を CI トリガーに追加**(本文チェック編集で core-guard を再評価 — 従来はチェックしても再実行されず green にならない構造欠陥)/ push のたびの最新 HEAD 再確認を手続化 / 保護後の管理手続の対象を「コア領域 ∪ guard_paths」に訂正(縮退修正)/ NFR-019 の参照を要件書 5 章に修正 / gh api 全コマンドに API バージョンヘッダ(2026-03-10)を明示 / 適用前提に allow_merge_commit 確認を追加 | draft |
| 1.0 | 2026-08-10 | **確定ゲート通過(approved)**: 敵対レビュー 2 周(P0×3/P1×6 → P0×1/P1×3。全件反映)→ PO 承認(2026-08-10・徳光 尋弥) | **approved** |
| 1.0 | 2026-08-22 | **Phase 4-5 の実装追随(版は上げない — 設計書 7.6-3 前段の実装追随の節更新)**: 必須チェックを **4 ジョブ → 5 ジョブ**へ更新(`nfr021-append-only` を追加 — NFR-021 受入証跡の append-only 統合時検査。設計書 10.1 のジョブ表が正)。2 章のマージ手続 2 項・4 項の列挙と 3 章 Ruleset の `required_status_checks` を同時更新した(本書 3 章の「必須ジョブの追加・削除・改名時は本書と Ruleset を 同時更新する」に従う)。**保護の適用状況・暫定運用の内容は変更していない**(縮退は継続中)。計画: `docs/features/nfr021-evidence-verifier/plan.md` | approved |
| 1.1 | 2026-08-22 | **2 章のマージ手続へ 5 項目目を新設(版繰り上げ — 7.3 の確定ゲート)**: **NFR-021 の受入証跡 PR を競合単位で並行させない**。`nfr021-append-only` は PR イベントの `base.sha` を基準に評価するため、**同じ base から作った 2 PR は互いを見ておらずどちらも green になる**(品質レビュー起点・実測で確認)。競合単位は**予約 = 同一 `gate_key`** / **結果証跡 = 同一 `attempt_id`** / 混在 PR は各レコードへ適用(**確定ゲート 1 周目で結果証跡を追加** — 同一 `attempt_id` の結果証跡が 2 件統合されると 10.1 の統合時検査 (d) に反し、append-only のため**恒久的に不合格**になる。予約の競合より重い)。**ゲートキーが異なる予約は並行してよい**。取り込み後の再実行が red なら**先行試行を閉じて後続を再採番**する(同 1 周目で追加)。**3 章の継続範囲も限定**(手続 3・4 の逐行確認は継続 / 手続 5 は strict policy 適用で終了 — 同 1 周目)。**マージ可否の手続を変える規範追加であるため実装追随ではなく確定ゲートを通す**(品質レビュー 3 周目 P1-5 の指摘を採用)。**確定ゲート通過(approved)**: 敵対レビュー **2 周**(1 周目 P1×1/P2×2 を**全件採用・不採用 0 件** → 2 周目 P0/P1/P2 いずれも 0 件で収束)→ **人間承認(2026-08-22・山田正輝)**。計画: `docs/features/nfr021-evidence-verifier/plan.md` | **approved** |
| 1.1 | 2026-08-24 | **参照先の状態表記の是正(版は上げない — 7.6-3 前段)**: 位置づけ注記の `onboarding.md` への参照を「**draft のため approved 化までは規範ではない**」から「**正とする**」へ。同書が Phase 4 の前提 PR で approved v1.0 になることへの追随であり、**本書の内容・決定は変えていない**。計画: `docs/features/onboarding-approval/plan.md` | approved |
| 1.2 | 2026-09-01 | **2 章マージ手続 3 へ「逐行確認の実施記録」の確認を追加(版繰り上げ — 7.3 確定ゲート・設計書 v1.12 と同一ゲートで一括検証)**: チェック行(PR 単位 1 ビット)と実確認範囲の乖離を記録で埋める設計書 6.3 の様式新設への追随。記録行の様式の正は設計書 6.3。**CI は記録行を検証しない**(設計書 7.3-8 の残余リスク)ため、本手続がマージ前の唯一の確認点。**あわせて手続 2・4 と 3 章 Ruleset の必須チェック一覧へ `frontend` / `backend` / `frontend-changes` / `backend-changes` を追加**(実装済みジョブが必須一覧から脱落し「5 ジョブ green でマージ可」になっていた欠落と、変更検知ジョブ失敗 → 下流 skipped = required 充足でマージ可能になる GitHub 仕様経路の是正 — 本ゲート敵対レビュー 2〜3 周目 P1。skipped の required 充足は適用時に実測確認)。**手続 2 へマージ直前の base 前進確認も追加**(同 4 周目 P1 — test merge commit の古い統合結果でのマージを防ぐ)。**射程宣言(設計書 7.3-7)**: 本改訂で確定する範囲 = 手続 2〜4 の確認内容と Ruleset 一覧 / 実装時に確定する範囲 = skipped 挙動の実測(保護適用時)。**確定ゲート通過(approved)**: 設計書 v1.12 と一括検証(敵対レビュー反映 12 周・指摘全採用・**PO 判断 2026-09-01 で 12 周をもってクローズ** → PO 承認 2026-09-01・徳光尋弥)。計画: `../features/gate-convergence-rules/plan.md` | **approved** |
| 1.2 | 2026-09-20 | **public 化と保護適用への追随(版は上げない — 7.6-3 前段の実装追随)**(TSK-429): **1 章** — 制約が 2026-09-19 に解消した旨の現況ブロックを冒頭へ置き、既存記述を「2026-08-10 時点の記録(履歴)」と明示 / **公開の根拠を新設**(公開対象・旧リポジトリ由来物の許諾範囲 = リポジトリ全体・条件と期限はいずれも無し・公開の実施は PO 指示。**個人を特定する情報は記録しない**)/ 選択肢表は**一般的な評価を変更せず**、本リポジトリが当該選択肢を採用した事実のみ追記。 **2 章** — 見出しを「暫定運用」から現況へ / **NFR-019 の書き分け**(リモート強制の未達は解消したが**条文全体は未達のまま**。(a)〜(d) のジョブは不在。`required_approving_review_count: 0` であり「PR 必須」と「人間レビュー必須」は別物)/ **手続 5 は終了**(strict policy 適用が既定の終了条件)・**手続 3・4 は継続**。 **3 章** — **二段階記述**(設定の適用は完了 / **運用の実地検証は未完** → 後続タスク F-2)/ **JSON を API 実測の全現値へ同期**(**`require_extra_approval_for_unattributed_changes` のキーが欠落しており、旧 JSON の再適用で実設定が失われる状態だった**。`required_reviewers`・`do_not_enforce_on_create` も補完)/ `integration_id` 未指定の影響を明記。 **4 章** — `.gitleaksignore` の現況(誤検知 3 件・判定根拠)/ **fingerprint がコミット単位のため本方式は再発する**旨(実測: 10 日で 1 件増加)/ 登録形式はリポジトリ履歴モードであり `dir` とは一致しないこと。 | **approved** |

> **本書の位置づけ**: GitHub 側の**ブランチ保護設定と CI が要求する Secrets** の再現手順の正本(ハーネス設計書 10.2)。Actions ポリシー全般(Organization ポリシー・許可 Action 方針等)は対象外 — Organization へ移管する場合は移管タスク側で確認する。ローカル環境構築の手順は [onboarding.md](onboarding.md) を**正**とする(受入条件の正は要件書 NFR-021)、CI ジョブの設計根拠は [設計書 10.1](dev-harness-design-2026-08-07.md) を正とする。

## 1. 現状の制約(2026-08-10 実測)

> **現況(2026-09-20 更新・TSK-429)**: **本節が記録する制約は 2026-09-19 に解消した。** リポジトリを **public 化**し、Ruleset **`protect-main-develop`(id `23694095`)** を `main` / `develop` へ適用済み(適用内容と API 実測値は 3 章)。**以下の箇条書きと選択肢表は 2026-08-10 時点の記録**であり、現在値ではない。

**公開の根拠(2026-09-19)**

- **公開対象**: 2026-09-19 時点の本リポジトリ
- **旧リポジトリ由来物の公開許諾**: 口頭で取得済み。**範囲 = リポジトリ全体**。**条件・期限はいずれも付いていない**(2026-09-20・PO 確認)
- **公開の実施**: PO の指示による
- 本記録の目的は**許諾範囲を明確にすること**である — `docs/worklog/2026-08-13-req-v2-legacy-parity.md` が記録する許諾は**別リポジトリへの private ミラーへの複製**が対象であり、**本件(公開)には及ばない**
- **個人を特定する情報は本書に記録しない**(本リポジトリは public であるため)

**以下は 2026-08-10 時点の記録(履歴 — 現在値ではない)**

- 本リポジトリ(`masaki1025/pitchlog`)は**個人(User)所有の private** で、所有者は Free プラン
- この構成では **classic branch protection / Rulesets とも利用不可**。実測: `gh api repos/masaki1025/pitchlog/rulesets` → HTTP 403「Upgrade to GitHub Pro or make this repository public to enable this feature.」
- **PO 判断(2026-08-10): ブランチ保護は後送り**とし、CI のみ先行導入する(選択肢の比較は feature 調査メモ `docs/features/ci-foundation/research.md` §5-4)
- **設計書 10.2 の「`scripts/setup_branch_protection.py` で再現可能にする」要件は本書の時点では未達**(手動手順 = 3 章が暫定の正本)。この後送りは設計書 v1.1 の改訂(確定ゲート)で例外として明文化する。再開タスクの DoD: スクリプト実装(冪等 GET→POST/PUT・重複検知・dry-run)+ 適用後検証まで

| 解消の選択肢 | 可否 | 備考 |
| --- | --- | --- |
| 所有者が GitHub Pro へアップグレード | ○(最小変更・推奨) | 個人 Pro で private の保護が有効化できる |
| リポジトリを public 化 | △ | 受託開発の未公開ドキュメントを含むため通常不適 ／ **本リポジトリでは 2026-09-19 にこの選択肢を採用した**(根拠は本節冒頭。一般的な評価はここでは変更していない) |
| Organization(Team 以上)へ移管 | △ | Org Free では解決しない。gitleaks-action が **GITLEAKS_LICENSE 必須**になる+Org の Actions ポリシー確認が必要 |

## 2. マージの管理手続(保護適用後の継続範囲を含む)

> **現況(2026-09-20 更新・TSK-429)**: 本節は 2026-08-10 に「保護が未適用の間の暫定運用」として置かれたが、**保護は 2026-09-19 に適用済み**(3 章)。**手続 5 は終了した**。**手続 1〜4 は継続する**(理由は各手続に付記)。

- **NFR-019 の現況(2026-09-20 更新)**: 要件書 [5 章 非機能要件](../requirements/requirements-pitchlog-2026-07-22.md) の NFR-019 は「PR ごとに CI で自動実行、**全グリーンでないとマージ不可**」を求める。**このうち「リモートでの強制」は 2026-09-19 の Ruleset 適用で達成した**(設計書 10.2 のリスク受容記録が対象としていた未達はこれ)。
  - **ただし NFR-019 の条文全体は未達のままである。** 同条が CI に含めることを求める **(a) クライアント/サーバー一致性・(b) 越境アクセス・(c) 主要分岐の E2E・(d) 同期プロトコルの故障系**のジョブは**いずれも存在しない**(導入時期 = 実装期。設計書 10.1 のジョブ表が正)。**「例外の解除」と「条文の充足」を混同しないこと。**
  - **`required_approving_review_count: 0` である**(3 章の実測値)。すなわち Ruleset が強制するのは「**必須チェックが全て green**」であって「**人間のレビュー承認**」ではない。**「PR 必須」と「人間レビュー必須」は別物**である。
- 以下のうち**機械が強制するのは手続 1・2 の一部のみ**であり、**手続 3・4 は所有者が遵守する管理手続**である(`core-guard` はチェックボックス 1 行の有無しか見ない)。ローカルの git_guard は Claude Code の PreToolUse フックであり、**人間の端末・別 clone・GitHub UI/API からの操作は遮断しない**(過信しない)
- マージの手続(すべて必須):
  1. **統合は PR 経由のみ**。main / develop への直接 push・GitHub UI での直接編集・チェック失敗状態でのマージは禁止
  2. マージ前に、**PR の最新 HEAD SHA に対して CI の全ジョブが green** であることを確認する(古い green run で判断しない): 常時実行 5 ジョブ(`secrets` / `docs-lint` / `core-guard` / `harness` / `nfr021-append-only`)+ 変更検知 2 ジョブ(`frontend-changes` / `backend-changes`)+ **paths filter により発火した場合の `frontend` / `backend`**(スキップが許されるのは filter 非該当のときのみ — 発火して red なら NFR-019「全グリーンでないとマージ不可」に反する)。**PR に push が追加されたら、そのたびに本手続をやり直す**(逐行確認・チェックも最新 HEAD に対して再実施)。**base SHA の 3 点一致と head の拘束を確認する**(取得元を固定 — ローカルの stale な `origin/<base>` や `potentialMergeCommit` で代用しない): ① 最新 HEAD で green の workflow run が検査した **test merge commit SHA を run から取得**(`gh run view <run-id> --json headSha` — pull_request run の headSha は merge commit)し、`git fetch origin <SHA>` の上 `git rev-parse <SHA>^1` で**第一親 = CI 検査時 base** を得る ② `gh pr view --json baseRefOid` で **GitHub 上の現在の base 先端**を取得し ① と一致することを確かめ、head SHA(`headRefOid`)とともに PR コメントへ記録する ③ **マージ操作の直前に ② を再取得して同一 SHA である**ことを照合し、**head は `gh pr merge --match-head-commit <記録した head SHA>` で原子的に拘束する**(UI マージの場合は直前に `headRefOid` の一致を再確認する)。①〜③のいずれかが不一致なら、develop 宛は base 取り込み・main 宛は中断(10.1 の OID 固定)で CI からやり直す。同一 base への複数 PR のマージは 1 件ずつ直列に行う(排他区間)。進んでいた場合の扱い: **develop 宛 PR** は base を取り込んで(head を更新して)CI を再実行し、本手続をやり直す(`pull_request` の CI は head 単体でなく test merge commit を検査するため、確認後に base が進むと合格対象が古い統合結果になる。Ruleset 適用後は `strict_required_status_checks_policy` がこれを機械強制する)。**main 宛(リリース・受入)PR は設計書 10.1 の head/base 完全 OID 固定が優先** — base が進んだら取り込みではなく**中断し、新しい SHA から受入をやり直す**(受入対象とマージ対象のずれを許さない)
  3. 変更ファイルが**コア領域(`.claude/core-areas.json` の `areas[].paths`)または検査経路(`guard_paths`)に該当する場合**(該当判定は **base ブランチ側の `core-areas.json` を正**として行う — CI の core-guard は PR 側 HEAD の定義を読むため、PR 自身が対象パスを削除・縮小すると機械判定から外れる〔2 章末尾の循環参照リスク〕。本手続がその補償であり、paths の削除・縮小を含む PR は削除前の一覧で判定する)、マージ担当者自身が最新 HEAD の差分を逐行確認し、**確認した本人が** PR 本文のチェック `- [x] コア領域/検査経路の変更: 人間による逐行確認を実施した` を付ける(チェックは人間確認の証拠にならない — AI でも付けられる。**付けた人 = 確認した人**の運用規律で担保する)。あわせて、チェック行の直後の**実施記録行**(`- 実施記録: 対象= 範囲= 方法=` — 様式の正は設計書 6.3)に**確認した本人が値を記入済みであること**、および**最新 HEAD への追随**(記録後に対象ファイルへ push が追加されたら記録も更新されていること)を確認する。**記録が未記入ならマージしない**(CI は記録行を検証しない — 運用規律)
  4. チェックを付ける(= PR 本文を編集する)と CI が再実行される(`pull_request` トリガーに `edited` を含めているため — これがないと本文編集では core-guard が再評価されず、チェック後も red のままになる)。チェック後に core-guard を含む**手続 2 の全ジョブ**が最新 HEAD で green になったことを確認してからマージする
  5. **【2026-09-19 終了】NFR-021 の受入証跡 PR を競合単位で並行させない**(**本手続は `strict_required_status_checks_policy: true` の適用をもって終了した** — 下記の終了条件のとおり。以下は経緯の記録)(`nfr021-append-only` の残余リスク)。同検査は **PR イベントの `base.sha`(= PR 作成・更新時点の develop)** を基準に評価するため、**同じ base から作った 2 つの PR は互いを見ておらず、どちらも個別には green になる**。先の PR をマージしても後の PR の head SHA は変わらないので、古い green のままマージできてしまう。**競合単位**は次のとおり:
     - **予約レコードを追加する PR**: 同一 **`gate_key`**。並行させると同一ゲートキーに未閉塞の予約が 2 件並ぶ(設計書 10.1「ゲートキー単位で同時に進行できる受入試行は 1 件だけ」に反する)
     - **結果証跡を追加する PR**: 同一 **`attempt_id`**。並行させると同一 `attempt_id` の結果証跡が 2 件統合され、設計書 10.1 の統合時検査 **(d)**「同一の `attempt_id` に対する結果証跡が 2 件目にならない」に反する。**証跡は append-only で削除も訂正もできないため、このゲートキーは恒久的に不合格になる**(予約の競合より重い)
     - **予約と結果証跡が混在する PR**: 含まれる各レコードについて上記をそれぞれ適用する
     - **ゲートキーが異なる予約は並行してよい**(`phase4` と `release-vX.Y.Z` は独立した排他単位)
     当面は**競合単位ごとに直列**に扱う。先行 PR のマージ後、後続 PR へ develop を取り込んで(= head SHA を更新して)CI を再実行してからマージする。**再実行が red になった場合はマージしない** — 例えば先行の予約が未閉塞のまま後続の予約を残していると (e-2) で red になる。その場合は**先行試行を結果証跡で閉じて develop へ統合し**、後続の予約を**新しい `attempt_seq`・`attempt_id`・ファイル名で作り直して**から取り込み・再実行する(不要になった重複 PR は閉じる)。**3 章の Ruleset を適用すれば `strict_required_status_checks_policy: true` が base 最新化を必須にするため、本手続きは終了できる**
- **core-guard の残余リスク(循環参照)**: `pull_request` は PR 側(head のマージブランチ)の workflow・スクリプトを実行するため、PR 自身が `ci.yml` / `core_guard.py` / `core-areas.json` を書き換えると検査そのものを無効化・形骸化できる(必須チェックは**ジョブ名の存在と結果**を強制するが、**ジョブの意味は固定しない**)。guard_paths は「未改変 PR への検知」であり防止ではない

## 3. ブランチ保護の適用手順(2026-09-19 適用済み — 運用実地検証は未完)

> **現況(2026-09-20 更新・TSK-429)— 二段階で読むこと**
>
> 1. **Ruleset 設定の適用: 完了。** `protect-main-develop`(id **`23694095`**)を `main` / `develop` へ適用済み。**下記 JSON は 2026-09-20 に GitHub API で実測した全現値と一致する。**
> 2. **運用の実地検証: 未完。** 本節が下で要求する「docs-only PR で下流 skipped がマージ可能」「変更検知ジョブ失敗時にマージがブロック」の**両方の実測は未実施**である。→ 後続タスク **Notion `TSK-433`「ブランチ保護の実地検証」**(担当: PO / 完了条件 = 両方の実測 PR URL の記録と本節の二段階記述の解消)。
>
> **したがって「適用済み」と「運用開始可」は別である。** 本節を根拠に運用開始を主張しないこと。

再開トリガー: 1 章の選択肢のいずれかが実施されたとき。適用は **Rulesets** を推奨(新設に適する — 積層・bypass 管理・閲覧性)。

**Ruleset を有効化しても防げるのは「必須チェックの欠落・failure のままのマージ」と「直接 push・force push・削除」まで。検査ロジック自体の改変(2 章の循環参照)は防げない** — **2 章の管理手続のうち、コア領域 ∪ guard_paths への人間逐行確認(手続 3・4)は、base 側検査への分離(別タスク)が完了するまで保護有効化後も継続する**(**手続 5 は `strict_required_status_checks_policy: true` の適用で終了できる** — 同 policy が base 最新化を強制するため)。

前提条件:

- 対象リポジトリの admin 権限(または fine-grained PAT の `Administration: write`)
- API バージョンを固定して実行する(本書のコマンドは `2026-03-10` を使用。改訂時はサポート中の版を選び直し、全コマンドで統一する)
- リポジトリ設定で **merge commit が許可されている**ことを確認する(`allowed_merge_methods: ["merge"]` との積で全マージが遮断されるのを防ぐ): `gh api repos/masaki1025/pitchlog -H "X-GitHub-Api-Version: 2026-03-10" --jq .allow_merge_commit` が `true` であること。false なら Settings → General → Pull Requests で Merge commits を有効化する

対象: `main`・`develop`。適用内容(設計書 10.2「直 push 禁止・PR 必須・CI 必須・force-push/削除禁止〔管理者含む〕」+ 6.2「マージは --no-ff」に対応):

```json
{
  "name": "protect-main-develop",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["refs/heads/main", "refs/heads/develop"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "required_reviewers": [],
        "require_extra_approval_for_unattributed_changes": true,
        "allowed_merge_methods": ["merge"] } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "secrets" },
          { "context": "docs-lint" },
          { "context": "core-guard" },
          { "context": "harness" },
          { "context": "nfr021-append-only" },
          { "context": "frontend-changes" },
          { "context": "backend-changes" },
          { "context": "frontend" },
          { "context": "backend" }
        ] } }
  ],
  "bypass_actors": []
}
```

- `allowed_merge_methods: ["merge"]` = マージコミットのみ許可(squash/rebase を遮断 — 設計書 6.2 の `--no-ff` 整合)
- `bypass_actors: []` = 管理者にも適用(ただし**所有者は設定自体を変更できる**ため、所有者からも逃れられない保護にはならない — 残余リスクとして記録)
- `required_approving_review_count: 0` の理由: 現状 1 人開発のため(レビューの実体は設計書 6.3 の反対側 AI レビュー + 人間確認)。チーム化したら引き上げる
- **必須チェックの `context` は「status check context 名」**であり、現状は ci.yml の job id と一致する(`name:` 未指定・matrix なしのため)。**適用前に実 PR の Checks 表示で実際の context 名を再確認**すること。必須ジョブの**追加・削除・改名時は本書と Ruleset を同時更新**する(v1.2 で `frontend` / `backend` に加え**変更検知ジョブ `frontend-changes` / `backend-changes` も追加** — GitHub は skipped の check run を required の充足として扱うため、**上流の変更検知ジョブが失敗すると下流が skipped になりマージを阻止しない**〔[GitHub Docs: Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)〕。常時実行の変更検知ジョブを required に含めることでこの経路を塞ぐ。**適用時に docs-only PR で下流 skipped がマージ可能となること・変更検知失敗時にマージがブロックされることの両方を実測確認**してから運用する)。可能なら各 context に GitHub Actions の `integration_id` を指定する(未指定だと任意ソースの同名 status を受け入れる)

適用手順(冪等):

```bash
# 1) JSON を保存
#    (上記 JSON を ruleset.json として保存)
# 2) 既存の同名 ruleset を検索(親 Org の ruleset を含めない・branch 対象のみ)
gh api "repos/masaki1025/pitchlog/rulesets?includes_parents=false&targets=branch&per_page=100" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  --jq '.[] | select(.name == "protect-main-develop") | .id'
# 3a) 見つからない → 新規作成(POST)
gh api repos/masaki1025/pitchlog/rulesets -H "X-GitHub-Api-Version: 2026-03-10" --input ruleset.json
# 3b) 1 件見つかった → 更新(PUT)。複数見つかった場合は停止して手動確認
gh api -X PUT repos/masaki1025/pitchlog/rulesets/<id> -H "X-GitHub-Api-Version: 2026-03-10" --input ruleset.json
# 4) 適用後検証: 両ブランチに全ルールが効いていることを確認
gh ruleset check main -R masaki1025/pitchlog
gh ruleset check develop -R masaki1025/pitchlog
```

- **JSON は省略を既定値と同一視しないこと(2026-09-20・TSK-429 で是正)**: 従来の本 JSON には **`require_extra_approval_for_unattributed_changes` のキーが存在しなかった**が、**実設定は `true`** である。GitHub は省略時 `false` 扱いのため、**旧 JSON をそのまま再適用すると実設定が失われる**。照合は `null`・省略・空配列を区別して行う。
- **`integration_id` は未指定**(9 context とも)。**未指定だと任意ソースの同名 status を受け入れる**ため、指定の可否は F-2 で判断する。
- 誤設定時の復旧: 同じ PUT で `"enforcement": "disabled"` に変更(削除せず無効化 — 設定内容を保全)

## 4. CI 運用メモ

- ワークフロー: `.github/workflows/ci.yml`(トリガー: pull_request / push〔develop・main〕/ workflow_dispatch)。設計根拠と採用ツール・SHA は設計書 10.1 と `docs/features/ci-foundation/research.md` §5
- **gitleaks の全履歴スキャン**: `workflow_dispatch` で起動すると全履歴を検査する(通常の PR/push は差分のみ)。workflow_dispatch は **ci.yml が既定ブランチ(main)に反映されてから**利用可能になる。それまでの全履歴監査はローカル docker で実施する。**worktree では `$(pwd)` をマウントしない**(worktree の `.git` はメインリポジトリへの参照ファイルであり、単体マウントでは履歴を読めない)。**`--redact=100` は必須**(v8.30.1 の既定は redact なし = 検出値が出力に出る — NFR-014):

```bash
repo_root="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
docker run --rm -v "$repo_root":/repo \
  ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
  git --no-banner --no-color --redact=100 /repo
```

- 合格条件: exit 0 に加えて、出力に `ERR`・partial scan がなく、走査対象コミットが 0 でないこと
- 検出時の扱い: **誤検知**のみ人間確認の上 `.gitleaksignore` に理由コメント付きで登録 / **真のシークレット**は作業を停止し、失効・ローテーション・履歴対処を人間が判断する(NFR-014)。記録(worklog 等)に秘匿値を書かない

- **`.gitleaksignore` の現況(2026-09-20・TSK-429)**: **登録済み 3 件**。いずれも `tests/fixtures/profile-sample/profiles/registry.json` の `pins.asset_digests.auth_catalog` / `auth_ddl_map`(ルール `generic-api-key`)で、**値は資産から導出される SHA-256 の内容ハッシュ**(`scripts/doc_check_profile.py` が再計算して照合する)。**人間確認済みの誤検知**であり NFR-014 の対象 4 種のいずれにも該当しない。判定の根拠と全文は当該ファイルの冒頭コメントにある。
- **本方式は恒久対処ではない(再発する)**: gitleaks の fingerprint は **`<コミット SHA>:<パス>:<ルール>:<行>`** で**コミット単位**のため、**当該資産のダイジェストが更新されるたびに新しい fingerprint が生まれ `secrets` が再び落ちる**。**実測: 2026-09-04 → 2026-09-14 の 10 日間で 1 件増加した**(同じ `auth_catalog` が値の更新により別 fingerprint として再検出)。**その都度 1 行追加する運用とする**。恒久化にはパス単位の allowlist(`.gitleaks.toml`)が要るが、**独自 config は組込みルールセットを置換しうる**ため、走査の空洞化を招かないことの確認を前提とする(未実施)。
- **ローカル監査は git モードで行う**: `.gitleaksignore` に登録した fingerprint は**コミット SHA を含む git モードの形式**であり、`dir` サブコマンド(作業ツリーのみ)の fingerprint とは**形式が異なるため一致しない**。`dir` での確認時に上記 3 件が検出されるのは想定どおりで、CI(git モード)では抑止される。

## 5. GitHub Secrets

- 現状の CI が要求する追加 Secret は**なし**(`GITHUB_TOKEN` は Actions が自動提供。gitleaks-action は個人所有リポジトリではライセンスキー不要)
- Organization へ移管した場合は `GITLEAKS_LICENSE` の登録が必要になる(1 章)
- 将来 CI から Codex 等を使う場合(設計書 9.3)は `CODEX_API_KEY` を **GitHub Secrets** に登録する(リポジトリ内に置かない — NFR-014)
