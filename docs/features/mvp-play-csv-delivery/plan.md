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

## ステップ1実装結果（2026-11-07）

既apiDownloadへtenantBoundを後方互換で伝達し、毎球CSVに限ってtrueを必須とした。Content-Lengthの非安全整数はnullへ閉じ、componentは正の安全整数長さ・小文字64桁SHAの両方と実bytes一致を要求する。破棄/試合変更/認証世代変更後は保存を止める。実crypto SHAで長さだけ正しい破損も拒否し、実clientのchallenge応答欠落/不一致はBlob未消費を確認。対象3suite76passed、Vue型・対象ESLint成功。最初の2失敗はnative async digest終了前の試験観測をvi.waitForで是正したもので、検査/期待を緩和していない。backend C2登録はステップ2で行うため、現時点で製品CSV成功とはしない。非作者確認は未実施。

ステップ1固定d06e8356の非作者確認 `play-csv-fixed-independent-20261107/REPORT.md` SHA256 `0b434a4363e91626e2155c6db4e92f355c86443065ca4005794ae494ca3ec240` はP0/P1=0（read-only、独立試験再実行なし）。P2旧要求finallyのbusy上書きを同controller一致時だけへ限定し、A取得→Bへ切替/取得→A完了後もBがbusyを保つ対向を追加。対象3suite77passed。後発2path差分の確認は別記し、前レビューが後発HEAD全体を確認したとは扱わない。

## ステップ2の途中固定（未完）

全イベントをaccepted条件の500行keyset（d2 NULLはid独立系列）にし、2000件打切りを撤去。SQLite実SQLの500/501/2001件＋NULL3件/別tenant/退避混在で欠落・重複0を確認（PG ACL証拠ではない）。snapshotはtenant/game/source_event_id/play_version/generation/d2の全一致を要求し、候補DDLへ原本ID/版を追加した。旧fixtureの値を実原本へ追随しただけでproducer成功とはしない。manifestは全イベント/補助資源/保存projectionを束縛する。C2 route_class/閉operation追加と、完成ZIP後の提示token再照合・新RR可視性再確認/拒否cleanupを実装。関連94pytest、Ruff/Ty成功。送出拒否4caseは依存置換した単体試験であり真正認可の実DB証拠ではない。

**未完**: 全量RAM materializationは残り、repository/formatterを有限ページ→ディスクZIPへ接ぐ修復を継続する。製品app/正式資産登録と既registry完全一致検査の追随、実PG/C2/認可撤回実測、88列producerは後続。6指摘が全解消した、正式readが提供されたとはしない。
