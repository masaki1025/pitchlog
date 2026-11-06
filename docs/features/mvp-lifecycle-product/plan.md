---
feature: mvp-lifecycle-product
status: active
branch: feature/mvp-lifecycle-product-connection
承認: PO委任によるCodex主担当/root判断（2026-11-06、既MVP終了・追記再開の実装接合）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 終了・追記再開の製品接続

単一7.3ゲート98344baaで確定した要件2.20・同期0.13・data-model1.6・ADR003 0.11に従う。基本2回＋限定追加2回を維持し、計画で新しい野球意味やD5/拒否順を再裁定しない。既mvp-lifecycle-product-author-20261106 packet 2f464208ef8ed53e78048ea5370e55204b60584b7397b51272882b1bed91fee8（基点89f0189c、40path）と外部FE6 a36c323bを再利用する。現在の取消修復2b1533aeを通常merge済み。rootを本WT唯一writerとし、作者/非作者はcache-onlyへ分離する。外部UI6は別担当の枝で修復中、同pathを並行編集しない。

1. 既packetの40pathとbootstrap差分を現在の実契約へ再基線し、閉V7 confirmed_checkpoint/confirmed_prefix/queued_predecessor と確定/予約target、先行未処理、唯一artifactの制御計算を実装する。単一核を維持し、未対応prefix操作を飛ばさず成功拒否する。共有FE6/mountの編集はせず接合差分で渡す。対象はpacket記載pathと対応する既prefix/bridge/正式schema・V5/eventKind13/C12・入力契約の必要最小追随。
2. 同TX lifecycle admission/head/checkpoint/games.status/終了版/真正stats receipt/pointerを接続する。0043、制約、ACL/owner、関数body/registryはrootが正式資産へ直列反映する。既ownerの便宜的権限拡大、test-only finalize、成功真偽の外部注入をしない。新生成pin/artifact/D11と正式受理はsource固定後に公式helperで派生し独立確認する。
3. 外部UI6の修復候補を非作者確認後に接合し、実記録画面から終了→再開→記録追加→再終了→再取得/reloadを通す。同本文/D5/attempt再送、通信断/再起動、先行要求待ち、二重tab、終了後ロック、越境拒否、途中故障全rollbackをowned実PGで確認する。性能閾値や正常通信時更新保証を緩めない。
4. 真正終了/再開providerを成績のlatest confirmed/current openへ接続し、訂正/再終了の二重計上なしと成績/CSVを確認する。P3は既担当/契約依存を分離し未実装を成功にしない。実機/運用TLS/復旧は準備・証拠と未実施を区別する。

各stepの候補source/根拠/独立レビュー/検査を固定し、step単位commitする。共有認可・tenant・7.7はroot直列、source未固定の中間pushを避ける。main/develop/共有DB/運用秘密は触らない。全4stepの完了やMVP完成を、step1のfixture成功に置き換えない。
