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

> **本書の位置づけ**: GitHub 側の**ブランチ保護設定と CI が要求する Secrets** の再現手順の正本(ハーネス設計書 10.2)。Actions ポリシー全般(Organization ポリシー・許可 Action 方針等)は対象外 — Organization へ移管する場合は移管タスク側で確認する。ローカル環境構築は [onboarding.md](onboarding.md)、CI ジョブの設計根拠は [設計書 10.1](dev-harness-design-2026-08-07.md) を正とする。

## 1. 現状の制約(2026-08-10 実測)

- 本リポジトリ(`masaki1025/pitchlog`)は**個人(User)所有の private** で、所有者は Free プラン
- この構成では **classic branch protection / Rulesets とも利用不可**。実測: `gh api repos/masaki1025/pitchlog/rulesets` → HTTP 403「Upgrade to GitHub Pro or make this repository public to enable this feature.」
- **PO 判断(2026-08-10): ブランチ保護は後送り**とし、CI のみ先行導入する(選択肢の比較は feature 調査メモ `docs/features/ci-foundation/research.md` §5-4)
- **設計書 10.2 の「`scripts/setup_branch_protection.py` で再現可能にする」要件は本書の時点では未達**(手動手順 = 3 章が暫定の正本)。この後送りは設計書 v1.1 の改訂(確定ゲート)で例外として明文化する。再開タスクの DoD: スクリプト実装(冪等 GET→POST/PUT・重複検知・dry-run)+ 適用後検証まで

| 解消の選択肢 | 可否 | 備考 |
| --- | --- | --- |
| 所有者が GitHub Pro へアップグレード | ○(最小変更・推奨) | 個人 Pro で private の保護が有効化できる |
| リポジトリを public 化 | △ | 受託開発の未公開ドキュメントを含むため通常不適 |
| Organization(Team 以上)へ移管 | △ | Org Free では解決しない。gitleaks-action が **GITLEAKS_LICENSE 必須**になる+Org の Actions ポリシー確認が必要 |

## 2. 暫定運用(保護が未適用の間 — 必須の管理手続)

- **NFR-019(要件書 [5 章 非機能要件](../requirements/requirements-pitchlog-2026-07-22.md)「テスト規約の CI 強制」)の「全グリーンでないとマージ不可」のリモート強制は未達**である(CI は表示されるが GitHub はマージをブロックしない)
- 以下は**機械的強制ではなく、所有者が遵守する管理手続**である。ローカルの git_guard は Claude Code の PreToolUse フックであり、**人間の端末・別 clone・GitHub UI/API からの操作は遮断しない**(過信しない)
- マージの手続(すべて必須):
  1. **統合は PR 経由のみ**。main / develop への直接 push・GitHub UI での直接編集・チェック失敗状態でのマージは禁止
  2. マージ前に、**PR の最新 HEAD SHA に対して** CI 4 ジョブ(`secrets` / `docs-lint` / `core-guard` / `harness`)がすべて green であることを確認する(古い green run で判断しない)。**PR に push が追加されたら、そのたびに本手続をやり直す**(逐行確認・チェックも最新 HEAD に対して再実施)
  3. 変更ファイルが**コア領域(`.claude/core-areas.json` の `areas[].paths`)または検査経路(`guard_paths`)に該当する場合**、マージ担当者自身が最新 HEAD の差分を逐行確認し、**確認した本人が** PR 本文のチェック `- [x] コア領域/検査経路の変更: 人間による逐行確認を実施した` を付ける(チェックは人間確認の証拠にならない — AI でも付けられる。**付けた人 = 確認した人**の運用規律で担保する)
  4. チェックを付ける(= PR 本文を編集する)と CI が再実行される(`pull_request` トリガーに `edited` を含めているため — これがないと本文編集では core-guard が再評価されず、チェック後も red のままになる)。チェック後に core-guard を含む 4 ジョブが最新 HEAD で green になったことを確認してからマージする
- **core-guard の残余リスク(循環参照)**: `pull_request` は PR 側(head のマージブランチ)の workflow・スクリプトを実行するため、PR 自身が `ci.yml` / `core_guard.py` / `core-areas.json` を書き換えると検査そのものを無効化・形骸化できる(必須チェックは**ジョブ名の存在と結果**を強制するが、**ジョブの意味は固定しない**)。guard_paths は「未改変 PR への検知」であり防止ではない

## 3. ブランチ保護の再開手順(制約解消後に適用)

再開トリガー: 1 章の選択肢のいずれかが実施されたとき。適用は **Rulesets** を推奨(新設に適する — 積層・bypass 管理・閲覧性)。

**Ruleset を有効化しても防げるのは「必須チェックの欠落・failure のままのマージ」と「直接 push・force push・削除」まで。検査ロジック自体の改変(2 章の循環参照)は防げない** — **2 章の管理手続(コア領域 ∪ guard_paths への人間逐行確認)は、base 側検査への分離(別タスク)が完了するまで保護有効化後も全項継続する**。

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
        "allowed_merge_methods": ["merge"] } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "secrets" },
          { "context": "docs-lint" },
          { "context": "core-guard" },
          { "context": "harness" }
        ] } }
  ],
  "bypass_actors": []
}
```

- `allowed_merge_methods: ["merge"]` = マージコミットのみ許可(squash/rebase を遮断 — 設計書 6.2 の `--no-ff` 整合)
- `bypass_actors: []` = 管理者にも適用(ただし**所有者は設定自体を変更できる**ため、所有者からも逃れられない保護にはならない — 残余リスクとして記録)
- `required_approving_review_count: 0` の理由: 現状 1 人開発のため(レビューの実体は設計書 6.3 の反対側 AI レビュー + 人間確認)。チーム化したら引き上げる
- **必須チェックの `context` は「status check context 名」**であり、現状は ci.yml の job id と一致する(`name:` 未指定・matrix なしのため)。**適用前に実 PR の Checks 表示で実際の context 名を再確認**すること。必須ジョブの**追加・削除・改名時は本書と Ruleset を同時更新**する(将来 Phase 4 で backend / frontend が加わる — 設計書 10.1)。可能なら各 context に GitHub Actions の `integration_id` を指定する(未指定だと任意ソースの同名 status を受け入れる)

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

## 5. GitHub Secrets

- 現状の CI が要求する追加 Secret は**なし**(`GITHUB_TOKEN` は Actions が自動提供。gitleaks-action は個人所有リポジトリではライセンスキー不要)
- Organization へ移管した場合は `GITLEAKS_LICENSE` の登録が必要になる(1 章)
- 将来 CI から Codex 等を使う場合(設計書 9.3)は `CODEX_API_KEY` を **GitHub Secrets** に登録する(リポジトリ内に置かない — NFR-014)
