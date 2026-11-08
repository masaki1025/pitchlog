---
feature: mvp-p3-batted-followers
status: active
承認: PO委任rootの明示移管・既MVP内実装指示（2026-11-08、起点b9948fa9）
重さ分類: コア領域
branch: feature/mvp-p3-batted-followers-20261108
created: 2026-11-08
計画レビュー周回: 1
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

採用記録: 計画HEAD `1d22c548` をCodex rootが全文確認し、PO委任の既MVP内最小追補として2026-11-08 19:19 JSTに採用。対象4通常球/置換ball-called維持、後続既4安打の唯一host再生・current RBI必須・未知I6閉拒否、既paged/同TX/CAS/二走/保存資格不変更が条件。本人確認/新意味/実PG成功/全P3成立の記録ではない。

## 候補接続と検査結果

- step1: 既4安打を非対象の原本再生へ開き、旧保存はlegacy閉codec、新訂正はcurrent RBI閉codecで別照合する。新候補の因果再束縛を安全に分離できないため、step1本体に同時配置。旧25件＋初期新11件=36 passed / 8.91秒。型/Ruff成功。
- step2: 実called-pitch→ball変更を通し、元観測保持・参加者/名簿/走者全値不一致拒否、欠測RBIのlegacy再生可/新訂正拒否を対向化。既物理mapperによる41列/runner全値再利用、既唯一T5の原/訂正出力全値一致まで純接続。初回T5検査の5失敗は試験が実DTOにない`kind`を参照したためで、実DTOのselected/source_event_id/metricsと原/訂正全値比較へ修正。製品コード/期待を弱めていない。
- step3: `tests/domainrt/test_past_correction_lineup.py`、新 `test_past_correction_batted_followers.py`（21件）、`tests/test_batted_hit_prefix_payload.py` の計81件成功 / 10.94秒。対象Ruff/型成功。旧25件回帰を含み、既paging二走/CAS/資格発行コードは不変更。

現在の新規成功は純候補であり、DB資格/認可/P3保存/実画面/全操作完成ではない。追加共有差分は不要（既pagedは同関数を呼出）。後発artifactの新RBI/凡打等は未接合。得点走者で現current因果が不足する旧観測、参加者/走者が訂正で変わる観測、訂正対象としての打球、4安打以外の後続は閉拒否のまま。状態が変わって元観測を再利用できない場合の結果確定/I6永続化は既呼出側が担う。

次はroot非作者レビュー後、同通常49統合候補へ本3pathを接合し、既P3実HTTPのauthority不明応答を解消した固定環境で「通常球訂正→後続安打→次球→終了/再開→成績/CSV」を検証する。現段階ではその実接続成功を記録しない。SOURCE/数学期待/正式資産の採取直しは行っていない。
