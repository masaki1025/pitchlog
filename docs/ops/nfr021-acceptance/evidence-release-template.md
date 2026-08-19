---
status: in-review
---
| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 1.0 | 2026-08-19 | 新設(Phase 4-4) | in-review |

# NFR-021 結果証跡のテンプレート(release)

リリース候補時の結果証跡を作成するときは、下のブロックを複写して直下の新規ファイルへ
保存する。ファイル名は[受入証跡の運用](README.md)の「レコード種別の閉じた命名文法」を
参照する。証跡の項目と合格項目は[要件定義書](../../requirements/requirements-pitchlog-2026-07-22.md)
の NFR-021 を参照する。

```
---
gate_kind: release
tested_commit_sha: "<試験した commit SHA>"
onboarding_blob_sha: "<onboarding の Git blob SHA>"
result: "<passed または failed>"
release_version: "<vX.Y.Z>"
attempt_seq: <ゲートキー単位の連番。引用符なしの 10 進整数(1 以上)>
attempt_id: "<予約レコードの識別子>"
---

# リリース候補時の結果証跡

## 証跡

| 項目 | 記録 |
| --- | --- |
| 日時 | `<記録する日時>` |
| commit SHA | `<試験した commit SHA>` |
| Windows 版 | `<Windows の版>` |
| WSL 版 | `<WSL の版>` |
| ディストリビューション版 | `<ディストリビューションの版>` |
| onboarding 版 | `<onboarding の版>`(人間可読の記録。機械照合の対象ではない) |
| onboarding blob SHA | `<onboarding の Git blob SHA>` |
| 主要ツールの版（python / uv / node / docker） | `<各ツールの版>` |
| 実行コマンドと終了コード | `<コマンドと終了コード>` |
| 各合格項目の期待値と実測値 | 下表に記載 |
| 標準出力またはログ成果物への参照 | `<参照先>` |
| 判定者 | `<判定者>` |

## 合格項目

| # | 合格項目 | 期待値 | 実測値 |
| --- | --- | --- | --- |
| 1 | NFR-019 の pytest | `<期待値>` | `<実測値>` |
| 2 | NFR-019 の Vitest | `<期待値>` | `<実測値>` |
| 3 | NFR-019 の Playwright | `<期待値>` | `<実測値>` |
| 4 | NFR-019(a) の一致性 | `<期待値>` | `<実測値>` |
| 5 | NFR-019(b) の越境 | `<期待値>` | `<実測値>` |
| 6 | NFR-019(c) の E2E | `<期待値>` | `<実測値>` |
| 7 | NFR-019(d) の同期故障系 | `<期待値>` | `<実測値>` |
| 8 | NFR-018(b) の機械検査 | `<期待値>` | `<実測値>` |
```
