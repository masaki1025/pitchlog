---
feature: mvp-pr197-identical-definition-recovery
status: active
branch: fix/pr197-identical-definition-recovery
worktree: /home/ymdms/projects/pitchlog-worktrees/fix-pr197-identical-definition-recovery
重さ分類: コア領域
notion: 未接続（既PR197とPO委任を作業根拠とする）
created: 2026-11-07
実行方式: 通常
反映周コミット: 適用
承認: 済（PO委任によるCodex主担当/root判断、2026-11-07。本人署名ではない）
計画レビュー周回: 0
確定ゲート周回: 0
---

# PR197の同一定義履歴だけを回復する

公開CIが実コミット6f17f72dのcore-areas.jsonと基線定義の共変更を拒否した。既登録areas/guard_pathsと全関数・クラスAST、旧定義指紋の同値を実Git全byteで検査したうえで、その1コミットだけに限定した回復を行う。一般共変更許可や拒否条件の削除は行わない。追加13除外のうち未guard6経路を後続の別JSONコミットで登録する。旧11除外が全てguard済みとは主張しない。

## 所有・対象

この専用WTのwriterはCodex。本計画の対象は `scripts/core_guard.py`、`scripts/check_human_review_signature.py`、`.claude/core-areas.json`、`tests/test_core_guard.py`、`tests/test_human_review_signature.py`。正式 `contracts/tenant_boundary/frozen-inputs.json` と従属9資産はcache候補のみ作り、rootが直列統合・公式再派生する。main/develop、共有DB、`.env`、他WTに書き込まない。

## 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 6f一件の固定Git同値・旧5a原典と正規successorの閉検査を先行実装 | 実6fのOID/親/JSON/guard/test全byte、旧2fa pin、関数・クラスAST、13除外を照合。別commit/変異/誤HEAD/欠pinを拒否。旧5a原典を保持し、正式typed候補をcacheへ固定。 |
| 2 | 未guard新6だけを別コミットでguard_pathsへ登録 | HEADで新13全てがcore/guard対象。area縮小なし、cochange回復定義とJSONを同一コミットにしない。 |

## テスト・受渡し

pytestで旧cochange拒否、実6f限定成功、JSON/AST/byte/pin/HEADの拒否対向を実行する。ハーネスのlint/型、公開CIと7.7はroot統合後の別証拠とし、この候補の純試験を正式受理へ広げない。source-first→typed後続の履歴順、候補全path SHAと適用順をpacketに残す。
