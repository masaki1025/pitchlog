---
status: draft
---

# GitHub リポジトリ設定手順

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-08-10 | 初版起案(ci-foundation / Phase 3): ブランチ保護のプラン制約と実測・暫定運用・再開手順・CI 必須チェック名・Secrets 方針を正本化 | draft |

> **本書の位置づけ**: GitHub 側のリポジトリ設定(ブランチ保護・Actions・Secrets)の再現手順の正本(ハーネス設計書 10.2)。ローカル側の環境構築は [onboarding.md](onboarding.md)、CI ジョブの設計根拠は [設計書 10.1](dev-harness-design-2026-08-07.md) を正とする。

## 1. 現状の制約(2026-08-10 実測)

- 本リポジトリ(`masaki1025/pitchlog`)は**個人(User)所有の private** で、所有者は Free プラン
- この構成では **classic branch protection / Rulesets とも利用不可**。実測: `gh api repos/masaki1025/pitchlog/rulesets` → HTTP 403「Upgrade to GitHub Pro or make this repository public to enable this feature.」
- **PO 判断(2026-08-10): ブランチ保護は後送り**とし、CI のみ先行導入する(選択肢の比較は feature 調査メモ `docs/features/ci-foundation/research.md` §5-4)

| 解消の選択肢 | 可否 | 備考 |
| --- | --- | --- |
| 所有者が GitHub Pro へアップグレード | ○(最小変更・推奨) | 個人 Pro で private の保護が有効化できる |
| リポジトリを public 化 | △ | 受託開発の未公開ドキュメントを含むため通常不適 |
| Organization(Team 以上)へ移管 | △ | Org Free では解決しない。gitleaks-action が **GITLEAKS_LICENSE 必須**になる副作用あり |

## 2. 暫定運用(保護が未適用の間 — 必須)

- **NFR-019「全グリーンでないとマージ不可」のリモート強制は未達**である(要件書 :674。CI は表示されるが GitHub はマージをブロックしない)
- 代替の強制層はローカル hooks(git_guard による main/develop 直接操作の遮断)のみ。従って**マージは必ず人間が以下を確認してから行う**:
  1. PR の CI 4 ジョブ(`secrets` / `docs-lint` / `core-guard` / `harness`)がすべて green
  2. **guard_paths(`.claude/core-areas.json` の定義)に触れる変更が含まれる場合、PR 本文の逐行確認チェックが `- [x]` である**こと
- **core-guard の残余リスク(循環参照)**: `pull_request` は PR 側(head)の workflow・スクリプトを実行するため、PR 自身が `ci.yml` / `core_guard.py` を書き換えると検査そのものを無効化できる。guard_paths は「未改変 PR への検知」であり**防止ではない**。保護有効化までは上記 2 の人間確認が唯一の防衛線。保護有効化後に base 側検査への分離を検討する(別タスク)

## 3. ブランチ保護の再開手順(制約解消後に適用)

再開トリガー: 1 章の選択肢のいずれかが実施されたとき。適用は **Rulesets** を推奨(新設に適する — 積層・bypass 管理・閲覧性)。

対象: `main`・`develop`。適用内容(設計書 10.2「直 push 禁止・PR 必須・CI 必須・force-push/削除禁止〔管理者含む〕」に対応):

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
        "required_review_thread_resolution": false } },
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

- `bypass_actors: []` = 管理者にも適用(ただし**所有者は設定自体を変更できる**ため、所有者からも逃れられない保護にはならない — 残余リスクとして記録)
- `required_approving_review_count: 0` の理由: 現状 1 人開発のため(レビューの実体は 6.3 の反対側 AI レビュー + 人間確認)。チーム化したら引き上げる
- 適用(冪等): `GET /repos/{owner}/{repo}/rulesets` で同名 ruleset の有無を確認 → あれば `PUT /repos/{owner}/{repo}/rulesets/{id}`・なければ `POST /repos/{owner}/{repo}/rulesets`。gh CLI 例:

```bash
gh api repos/masaki1025/pitchlog/rulesets --input ruleset.json   # 新規(POST)
gh api -X PUT repos/masaki1025/pitchlog/rulesets/<id> --input ruleset.json  # 更新
```

- 適用の自動化スクリプト(`scripts/setup_branch_protection.py` — 設計書 10.2)は**保護が利用可能になってから**別タスクで実装する(API 検証不能なコードを先に書かない — ci-foundation 計画 2 節)
- 必須チェック名は CI の **job id と完全一致**(`secrets`・`docs-lint`・`core-guard`・`harness`)。ジョブ名を変える場合は本書と Rulesets を同時に更新する

## 4. CI 運用メモ

- ワークフロー: `.github/workflows/ci.yml`(トリガー: pull_request / push〔develop・main〕/ workflow_dispatch)。設計根拠と採用ツール・SHA は設計書 10.1 と `docs/features/ci-foundation/research.md` §5
- **gitleaks の全履歴スキャン**: `workflow_dispatch` で起動すると全履歴を検査する(通常の PR/push は差分のみ)。workflow_dispatch は **ci.yml が既定ブランチ(main)に反映されてから**利用可能になる。それまでの全履歴監査はローカル docker で実施する:

```bash
docker run --rm -v "$(pwd)":/repo \
  ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
  git /repo --no-banner
```

- 検出時の扱い: **誤検知**のみ人間確認の上 `.gitleaksignore` に理由コメント付きで登録 / **真のシークレット**は作業を停止し、失効・ローテーション・履歴対処を人間が判断する(NFR-014)。記録(worklog 等)に秘匿値を書かない

## 5. GitHub Secrets

- 現状の CI が要求する追加 Secret は**なし**(`GITHUB_TOKEN` は Actions が自動提供。gitleaks-action は個人所有リポジトリではライセンスキー不要)
- Organization へ移管した場合は `GITLEAKS_LICENSE` の登録が必要になる(1 章)
- 将来 CI から Codex 等を使う場合(設計書 9.3)は `CODEX_API_KEY` を **GitHub Secrets** に登録する(リポジトリ内に置かない — NFR-014)
