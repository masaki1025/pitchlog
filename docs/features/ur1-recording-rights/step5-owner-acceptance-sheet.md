# 新5の担当別受理シート（候補、2026-10-18）

対象は[接続契約の固定候補](step5-connection-fixed-candidate.md)の未受理部分だけ。既受理の「初期権は試合開始時」「同一業務scope」「試合行→世代行」「RG1の事前/直前ゲート」は維持する。U-R1の隔離候補 `7b031b3e` は本物の外部台帳adapter・端末資格・製品 `RecordingRightsPort` を提供していない。回答欄は現時点で**全て未受理**。

## 1. 公開署名、DTO、失敗結果、全ロック順

| 項目・推奨候補 | 必要な所有側受理 | 受理後に実装できる範囲 |
| --- | --- | --- |
| U-G1の開始: `start_game(scope, game_id: UUID, start_request_id: UUID, verified_device: VerifiedDeviceContext) -> StartGameResult`。U-R1へ同じscopeの`issue_initial_recording_right(...)`を呼ぶ。`StartGameResult`は`game_id, game_status, generation(D4), recovery_generation, holder_device_id, recording_right_proof(V12)`を持ち、V12は業務DB commit成功後に同じ認証済み端末へだけ返す。`issuance_order`初期値は担当決定待ちでDTOへ仮値を置かない | U-G1: 実関数名・HTTP DTO/状態・`start_request_id`再送契約・初回発行順・二重開始の結果。TSK-506/認証: `VerifiedDeviceContext`を発行する実入口と、他端末へのV12非漏洩 | U-G1が開始transactionへ付与operationを接続し、応答消失の同端末再交付を実入口で試験する。U-R1は固定operationの登録候補を担当する |
| 同期Port: 既存`is_recovery_generation_current(game_id, supplied, writer)`と`holds_recording_right(game_id, d4, v12, writer)`へ検証済み端末文脈を渡す候補。`PortWriter`は同じscopeの固定tokenだけを実行し、任意SQL/Sessionや呼出側指定tenantを増やさない。P3終了後はV12を省略し復旧世代・RG1は照合 | U-S1: 署名・P1/P2/P4/P3の呼出位置、P3終了後の引数の扱い、Port登録、B4/B9/B10の経路別写像。TSK-506: HTTPからの端末文脈注入 | U-R1が本物Portの限定実装を新8で登録し、U-S1が実経路に接続してD5未消費・全取消を結合試験する。受理だけでPort完成にはならない |
| 全順: 認証/非ロックRG1確認 → 外部epoch共有fence → 業務DBの有効端末資格行`FOR SHARE` → D4 counter/予約/一度限りclaim（外部別行） → 試合行`FOR UPDATE` → U-G1のチーム行UUID順・選手行UUID順・U-M2記憶行 → 世代行 → 配達行 → RG1行`FOR SHARE NOWAIT` → 業務DB commit → 外部fence解放。復元開始の最初の取引はRG1行だけを閉じて確定する | U-G1: 実際のチーム/選手/U-M2と世代/配達の相対順、commit/fence所有。U-S1: 同期の試合→世代→RG1、外部fence保持。認証担当: 資格失効のロック順。U-M2の既存順は変更しない | 各経路の直列化・deadlock負例と、RG1移行時の全取消を本物のscopeで検査する |

**失敗の所有**: U-R1の`InitialGrantUnavailable`は状態不明・RG1閉鎖・鍵/台帳/資格不明で業務scope全取消、`InitialGrantConflict`は別端末/別owner/既存権利不一致で全取消。U-G1がHTTPのstatus・再試行可否を受理する。U-S1はRG1の検査位置に関係なく、P1/P2/P4をB7、P3をB10に写像し、D5未消費を保証する。復旧世代不一致のP3は既存B9契約に従う。U-R1はB結果を独自に新設しない。

## 2. 端末資格の失効と書込みの競合

| 推奨する直列化・拒否 | 必要な所有側受理 | 受理後に実装できる範囲 |
| --- | --- | --- |
| tenant認証で束縛された`device_id`と資格を内部で検証し、U-R1の同一業務scopeが資格行を`FOR SHARE`で取得してcommitまで保持する。失効は同一行の`UPDATE`で、資格行の排他ロックを取ってから確定する。失効が先なら開始/再交付は資格不在として拒否。書込み側が先なら失効は書込みcommitまで待ち、以後の要求を拒否。資格行欠損・不明・読取失敗はfail-closed | 認証担当/TSK-506: 発行・照合・失効の表/関数所有、認証sessionへの束縛、失効側が資格行保持中に試合/世代/RG1を逆順に取らないこと。U-G1/U-S1: 実入口から同じ資格文脈を渡すこと | 専用固定operationと認可、失効先行/書込先行・内部token直接呼出し・別tenant/別端末の実DB競合試験。今の使い捨てDB試験は行ロックの機構確認のみ |

V12再交付は、現世代・現復旧世代・同一開始要求・有効な同一端末と未失効の配達行をロック下で再照合する。資格の共有ロックが取れない間はV12を復号・返却しない。HTTP応答はcommit成功の確認後にだけ出す。資格失効後の過去応答を回収できるとは主張しない。

## 3. 予約attempt、途中失敗、不明commit

| 推奨する耐久契約・停止条件 | 必要な所有側受理 | 受理後に実装できる範囲 |
| --- | --- | --- |
| `start_request_id`は端末が送信前に保持する同一要求ID。外部台帳の`d4_reservations`を`attempt_id, tenant_id, game_id, start_request_id, generation, recovery_generation, status`の耐久記録とし、counter更新と予約INSERTを**同一外部transaction**で確定する。`(tenant,game,start_request)`には高々1件の`reserved`を許す候補。予約応答消失時はowner tupleでその行を再照会し、同じattempt/D4だけを返す。台帳が権威ある不在を証明できなければ新予約を禁止 | U-R1: 外部台帳の一意制約・予約/claim固定関数と隔離adapter。U-G1: 開始要求IDの保存・再送と、再照会したattemptを同一開始へ渡す境界 | 応答消失・並行予約・他owner再利用を隔離DBで検査し、実台帳の同期耐久接続は実配置後の別証明とする |
| claimは`attempt_id`だけでなくowner tuple全項目を条件に`reserved→claimed`へ**一度だけ**遷移し、業務DBへ投入する前に外部同期耐久を確認する。claim応答不明では同D4の再投入をしない。業務DB rollback後もclaimed D4を戻さない。新attemptが必要なら、業務DBの同一開始が未確定であることを権威ある読取で証明し、旧attemptを二度使わず別D4を予約する。旧開始transactionが進行中か否かを判定できなければ停止する | U-G1/U-R1: 不明commitの判定に使う試合行/開始要求のロック・一意制約、進行中transactionの待機、旧claimと新attemptの切替時点。ロック順の例外が要る場合は計画追補とレビュー | rollback、commit応答消失、旧transaction競合、新attemptの非再利用を実DBで検査する。現在の隔離代役だけでcommit結果不明の解決実装が完成したとは扱わない |

## V12鍵の独立管理と寿命

**推奨**: 認証HMAC署名鍵とは別のAES-256-GCM鍵束を使う。配達行に`key_id`を置き、現行鍵は暗号化/復号、旧鍵は既存暗号文の復号専用とする。新鍵への切替後も未失効の暗号文に対応する旧鍵を保持し、同一V12の暗号文を新鍵で安全に再暗号化・検証した後、または該当する全権利の失効を確認した後だけ旧鍵を廃止する。再暗号化は新V12や新D4を発行しない。鍵欠損・不明ID・復号失敗では同権利へ別V12を作らず再交付停止。資格/配達/世代の失効時は再交付を拒否し、不要になった旧鍵の廃止を監査する。鍵値・V12平文はDBやログへ書かない。

既存`authz/signing_key_config.py`の**設定形式と起動時検査の方式だけ**を参考にできる。`docs/ops/key-rotation.md`の署名鍵破棄手順は旧鍵を保持しないため、V12鍵へ流用しない。鍵保管/配布先、鍵束の寿命、再暗号化の実施責任と運用手順、端末内資格/証明の保管責任は**担当未指定・別受理**。これらが決まるまで製品の鍵接続・本番再交付成功を主張しない。
