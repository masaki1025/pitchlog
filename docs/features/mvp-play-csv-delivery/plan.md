---
feature: mvp-play-csv-delivery
status: active
branch: fix/mvp-play-csv-delivery
承認: PO委任によるCodex/root判断（2026-11-07、既MVP内の欠陥修復・接続）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 毎球CSV候補の6指摘修復と実記録供給

起点d00f925aの既ud2-csv-export計画を再利用する。非作者の固定レビュー play-csv-independent-intake-20261106/REPORT.md（SHA e2047785b0fe7b0fa80b660364c1aa7dfad493e3623e11882bf9598bf1502aec）のP1=6を修復する。作者WTは変更せずrootが本WTを単独所有する。新しい野球意味は採用しない。既承認の記録時producer/同一RR/有限読取/C2/送出前認可/完成ZIP検査の要件を維持する。

| ステップ | 実装 | 検証 |
|---|---|---|
| 1 | frontend apiDownloadの既tenantBoundオプション伝達、gameExportsのC2必須化、必須長さ/SHAと画面破棄/試合変更後の保存拒否 | 実clientのchallenge/tenant/世代拒否、真正SHA照合、欠落・不正・破損・破棄のVitest、型/lint |
| 2 | backend C2 route登録、全イベントkeyset、保存snapshotのsource版照合、manifest全source版、送出直前の認可再確認、有限ディスク抽出へ修復 | pytest、500/501/2001境界、旧snapshot/版変更、撤回/越境/故障、非作者確認 |
| 3 | connected-rehearsal固定候補との通常接合、同TX88列producer/正式資産/実画面導線 | 事前fixture投入なし実新規記録からZIP、旧source無補完、正式資産/独立レビュー/CI。正式受理前は候補扱い |

rootへの既PO委任と2026-11-06の速度優先・品質維持指示に基づく範囲具体化。承認者はCodex/rootでありPO本人の逐行確認や署名ではない。ステップ1の実装を開始する。6指摘とproducerが未解消の間、CSV完成や正式提供とはしない。送出検査を緩めず、既一般apiDownloadの非CSV呼出しとの互換性を維持する。
