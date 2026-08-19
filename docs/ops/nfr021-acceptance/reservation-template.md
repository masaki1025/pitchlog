---
status: draft
---
| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 1.0 | 2026-08-19 | 新設(Phase 4-4) | draft |

# NFR-021 予約レコードのテンプレート

予約レコードを作成するときは、下のブロックを複写して直下の新規ファイルへ保存する。
ファイル名は[受入証跡の運用](README.md)の「レコード種別の閉じた命名文法」を参照する。

```
---
gate_key: "<phase4 または release-vX.Y.Z>"
attempt_seq: "<ゲートキー単位の連番>"
attempt_id: "<発行した識別子>"
started_at: "<YYYY-MM-DDTHHMMSSZ>"
operator: "<実施者>"
---

# 予約レコード

| 項目 | 記録 |
| --- | --- |
| release_version | `<vX.Y.Z>`（`release` の場合に記載し、`phase4` ではこの行を削除） |
```
