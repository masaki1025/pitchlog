---
feature: mvp-lifecycle-gate-draft3
status: in-review
branch: feature/mvp-lifecycle-product-connection
承認: 未
計画レビュー周回: 0
確定ゲート周回: 0
---

# 終了・追記再開の最小7.3確定ゲート案

## 射程

対象は要件書v2.20、同期プロトコルv0.13、データモデルv1.6の３正本を一括した単一ゲート。初回敵対レビューは３文書の全文を対象とする。技術wire・保存境界は既PO委任を根拠に起案する。FR-007/FR-010の野球意味、D5/DI2/DI3/DI5、拒否先行順、ShouldのFR-040、既#1〜#12の裁定は維持する。

## 実施順

1. rootがcache候補の全文・差分・SHAとactual worktreeのHEADを再照合し、適用版v1.19・条文コミット`a7cc3c0baa05fd1a1639e1f98e8f8f7bb39ad229`をworklogに固定して３正本を同時にin-review化する。
2. 非作者が7.3-5形式で初回全文を敵対レビューする。採否と典拠を記録し、採用反映があれば単一周コミットにまとめ、対象planの`確定ゲート周回`を加算する。
3. 7.3 v1.19の回数上限・終端遷移に従い、次周の差分と影響節を審査する。PO委任範囲を越える意味追加または原典矛盾だけrootへ所在を示し、他の独立作業を続ける。
4. 受理できる最終本文・全採否・最終反映差分をroot/PO判断へ渡す。承認前は３正本ともin-reviewを維持し、docs/README.mdの正式currentは切り替えない。

## 完了条件

３正本の全文・差分・SHA、初回全対象、採否記録、受理scope、適用版/条文SHA、残余と実装伝播先が一つのpacketで追跡できること。正式contract/enum/CHECK/DDL/ACL/実PG/実機試験はゲート後の別作業であり、本計画で実施済みにしない。
