---
feature: mvp-p3-batted-followers
status: active
承認: PO委任rootの明示移管・既MVP内実装指示（2026-11-08、起点b9948fa9）
重さ分類: コア領域
branch: feature/mvp-p3-batted-followers-20261108
created: 2026-11-08
計画レビュー周回: 0
確定ゲート周回: 0
---

# P3後続打球の真正再評価

既 mvp-past-correction-product plan step2/4、FR-007、sync-protocol P3/I6、ADR-003 D-14-lに従い、対象以降を唯一artifactで再評価する。既paging計画の同TX/25件page/二走/seal/CAS/原子性を変えない。旧計画のdomainファイル所有はroot今回指示により本担当へ限定移管（Recovery受領済み）。過去訂正対象は現行4通常球、置換はball/called-pitchのまま。

編集所有は `backend/src/pitchlog/domainrt/past_correction_lineup.py`、新専用BE純試験、本docsのみ。Recoveryのpaged/HTTP/authority、他作者domain/schema、同期核、正式assets/台帳は非編集。PGは後続root接合後、今回純実装から進める。

| ステップ | 内容 | 検査 |
|---|---|---|
| 1 | 元V7/計算/ID/D1/D2/前後連鎖を照合した4安打を非対象原本carryへ許し、唯一hostで旧/新を順次再評価 | 旧対象4球維持、batted target/未知閉拒否、ページ境界/元応答改変拒否 |
| 2 | 元打球観測を訂正後の実計算へ再束縛し、参加者/名簿/走者ID不成立を閉拒否。旧保存の再生はlegacy資格、新訂正はcurrent RBI必須を分離 | 4安打/無得点走者進塁の実host正例、欠測RBI/元観測改変/走者ID不一致の負例 |
| 3 | 影響回帰・型・最終固定packetをrootへ渡す | 純成功を実DB/P3認可/I6永続化/全操作完成へ拡張しない |

Pythonへ野球計算を写さない。保存済み旧数学は現hostの全応答再生と一致した場合だけcarry。新出力はV7原観測と閉codec/current因果に一致する必要がある。旧artifactで不足観測を暗黙成功へ流さない。0db3でcurrent RBI入力未供給の得点走者caseは拒否を保ち、後発artifact/ABIの依存をpacketへ分ける。新意味は採用しない。
