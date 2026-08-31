---
status: approved
---
| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 1.0 | 2026-08-19 | 新設(Phase 4-4)。敵対レビュー 6 周 → PO 承認 | approved |

# NFR-021 予約レコードのテンプレート

予約レコードを作成するときは、下のブロックを複写して直下の新規ファイルへ保存する。
ファイル名は[受入証跡の運用](README.md)の「レコード種別の閉じた命名文法」を参照する。

```
---
gate_key: "<phase4 または release-vX.Y.Z>"  # ゲートキーの合成形。結果証跡の gate_kind / release_version から導く
attempt_seq: <ゲートキー単位の連番。引用符なしの 10 進整数(1 以上)>
attempt_id: "<発行した識別子>"
started_at: "<YYYY-MM-DDTHHMMSSZ>"
operator: "<実施者>"
---

# 予約レコード

`release` の版は `gate_key` の合成形が保持するため、本文に別欄を設けない
（二重記録は不一致の余地を作る）。
```
