# U-R1 新5の隔離候補資産（2026-10-18、正式台帳未反映）

**後続のDDL判断**: [3群判断資料](step5-three-part-approval.md)は、既存世代表のapp表単位ACLを確認した結果、V12 digestと復旧世代を同表へ追加する下記初期案を見直し、専用function_only表へまとめることを推奨する。下記表は隔離候補作成時の履歴であり、正式DDLの承認値ではない。

[物理契約差分](step5-physical-contract-annex.md)に対する**候補**。POが承認したのはV12の同一要求・同一認証端末への暗号化再交付、自己申告端末IDの拒否、復旧世代の毎書込照合と停止範囲、新5の隔離候補作成まで。以下のDDL・認可・凍結基準・実配置・鍵保管先は未受理である。既存DBには適用しない。TSK-550 Bが共有資産を編集中のため、正式JSONは同枝に先行入力せず、統合済みの実基線から再導出する。

## 業務DBの具体差分候補

| 資産 | exact候補と制約 | 未決・登録先 |
| --- | --- | --- |
| `public.recording_generations` | `v12_digest BYTEA`（32 byte）、`recovery_generation BIGINT`（正）。新規normal世代には両値必須。既存行は段階移行中NULLを許すが、NULLなら証明不能として書込拒否。D3/適用prefix=0と現通常世代一意は既存契約を維持 | ORM・migration・manifest・immutable列/trigger・既存行移行。現行authzのapp INSERT許可を拡大せず、新規U-R1限定operationとして別審査 |
| `public.recording_right_deliveries` | PK `(tenant_id,game_id,start_request_id)`、FK `(tenant_id,game_id,generation)`→記録権世代、`device_id UUID`、`key_id TEXT`、`nonce BYTEA`（12 byte）、`ciphertext BYTEA`（48 byte: V12 32 byte+GCM tag）、`revoked_at TIMESTAMPTZ`。RLS FORCE、app直接DMLなし、固定関数だけ。物理DELETEなし | owner/関数identity、SELECT・INSERT・UPDATE列、既存行保管期間と鍵ローテーションの運用責任。再交付関数は現世代・同端末・同要求・未失効をDBで再照合 |
| `public.rg1_restore_gate` | `recovery_generation BIGINT NULL`候補。既存closed seedではNULL、外部現値と一致しない限り開かない。RG1の2読取関数は毎書込の外部現値照合を担う固定operationへ拡張が必要 | 新4の既承認FORCE RLS/単一行権限を広げず、復元制御ownerと同期側の7.6/認可再審査を要する。外部台帳読取と状態行ロックの直列化点は未受理 |
| `authn.trusted_devices`（所有候補） | `tenant_id,device_id,credential_digest,revoked_at`、tenant+device一意。credentialは256-bit乱数、DBにはSHA-256 digestだけ。認証済みtenantとの一致と失効を固定関数で照合。app直接DMLなし、RLS FORCE | 認証/TSK-506側の発行・失効所有と表配置が未受理。自己申告`device_id`だけでは成功しない。U-R1はその固定照合結果を内部直接呼出しでも再検証 |

AES-256-GCMの鍵は業務DB外から`V12Box`へ注入する。鍵原文は業務DB、SQL、ログ、例外へ保存しない。暗号文はtenant・試合・開始要求・端末・D4・復旧世代をAADに含め、入力tenantと実行器の固定tenantを照合する。暗号鍵の実保管先、旧鍵保持、アクセス・復旧担当が決まるまで配備可能とは判定しない。現候補は1 active keyで発行し、明示的に注入された旧鍵が残る間だけ旧暗号文を再交付する。旧鍵を失えば再交付は失敗閉鎖となる。鍵ローテーション時の保管・廃止条件は追加判断を要する。

## 復元外台帳と毎書込の直列化候補

`recovery_epoch(singleton_id=1,current_generation BIGINT)`、**別行**の`d4_counter(singleton_id=1,next_generation BIGINT)`、`d4_reservations(attempt_id UUID PRIMARY KEY,tenant_id UUID,game_id UUID,start_request_id UUID,generation BIGINT UNIQUE,recovery_generation BIGINT,status reserved|claimed,committed_at TIMESTAMPTZ)`を、業務DBの復元範囲外に置く。epoch共有ロックを保持したままD4を予約しても同一行のUPDATEへ昇格しない分離である。予約の成功はprimaryと同期standbyの両方でWAL耐久が確認された後だけ返す。呼出側は予約前にattempt IDを耐久記録し、台帳は同じattempt IDと**同じ所有tuple**の再照会でだけ同じ結果を返す。異なる所有tupleは拒否する。予約応答不明時は同じIDを再照会し、業務DBへ入る直前に台帳で`reserved→claimed`を一度だけ耐久確定する。`claimed`のattemptは二度目の業務投入を拒否する。claim応答が不明ならそのD4を使わず状態を照会し、安全を証明できない限り停止する。業務DB取消後の新しい予約には新IDを使う。取消/応答消失で番号を戻さない。旧primaryフェンス不能・同期先喪失・最後の予約不明では新規D4発行停止。復旧世代はD4とは別系列で単調に増やし、業務DBの古いbackupから採番を戻さない。具体DDL、トランザクション分離・権限・同期複製設定・昇格手順は隔離DB実測と運用担当受理を要する。

毎書込の厳密な候補順は、**外部epoch行の`FOR SHARE`を先に取得し、業務DBの全書込・RG1直前共有ロック・commitを終えるまで外部共有ロックを保持**する。復元開始の最初のtransactionは既受理どおりRG1行だけを排他にしてclosedへ確定し、その後で外部epoch行を排他更新する。書込が外部共有ロックを保持して先に進んだ場合も、復元開始はRG1閉鎖を先に確定し、その書込のRG1直前検査を拒否する。外部更新が先に確定した後の書込はDB現値と不一致で拒否する。外部ロック取得前に試合・世代・U-M2の行ロックを持たない。U-G1/U-S1のscopeを外部leaseで包む方法、接続障害時の解放とロック順は**担当受理・隔離DB競合試験待ち**である。

## コード・凍結のexact候補と未受理境界

- 新規製品候補: `backend/src/pitchlog/recording_rights/initial_grant.py`。暗号化V12と要求/端末束縛、独立D4予約、同一開始の再交付、不明・不一致拒否を持つ。現段階では`InitialGrantScope`/`DurableGenerationSource`はProtocolで、**本物の登録済みoperationと実台帳adapterは未提供**。
- 接続候補: U-R1が`issue_initial_recording_right`を同一tenant scopeへ適合させる固定operation群、U-G1が開始HTTPとcommit成功後の応答を所有、U-S1が検証済み端末値をPortへ渡す。既存`RecordingRightsPort`の欠落署名は未受理。新8の実Port完成とは扱わない。
- 凍結資産: `repository-contract.json`の新しいrecording generation INSERT / delivery read+insert / device verify / epoch check token・capability、`base-allowlist.json`のSQL組立シンボル、`runtime-authz-contract.json`、authz product DDL/manifest・table-classification・oracle/lock・schema-manifest・archiveを候補差分とする。revision/digest/snapshot/7.7受理履歴は**TSK-550 B統合後の実基線から算出**し、承認前に入力しない。
- RG1の毎書込外部照合は、現行2固定関数の値とロックだけでは実現しない。`RecoveryEpochFence`を実外部台帳の共有ロックへ接続し、U-G1/U-S1が業務DBのcommit後まで保持する接続契約・関数/Port差分を受理する必要がある。現在の`assert_write_recovery_generation`は保持証明を要求する候補であり、全経路への実接合済みとは扱わない。

## 隔離試験と停止点

現候補の単体試験は応答消失後の同じV12/追加発行なし、予約応答不明から同じattempt IDの回収、所有tupleの付替え拒否、claim後/業務取消後の同D4再投入拒否、別端末・偽装資格拒否、復旧世代不一致/台帳不明、AAD/鍵不一致、RG1事前閉鎖を確認する。使い捨てPostgreSQLで、epoch共有ロック下での別行D4更新成功と、復元側epoch排他更新の待ちを検証する。実台帳の予約・claim耐久性、同一要求並行、他テナント、現世代一意、試合行→世代行→RG1ロック、commit直前復元、RLS/FORCE、同期standby喪失は別途検証する。単体試験は実台帳・運用上の耐久性証明を代替しない。

**次の一括受理対象**: owner・関数・DDL/JSONのexact差分、鍵保管/旧鍵、端末資格の所有、外部現値照合の直列化点、U-G1/U-S1の署名/全ロック順、TSK-550 B統合後のrevision/digest/snapshotと7.7前後記録。現行の基線を変更せずに候補だけを提示する。共有DB適用・有料資源・運用open・マージは別ゲート。

## 一括判断欄（未受理項目のみ）

| 判断 | 推奨候補 | 承認後に始められる範囲・残る証明 |
| --- | --- | --- |
| D4台帳の配置・運用・費用 | 業務DB復元範囲外の別故障領域primary＋同期standby。既存資源は独立性・同期耐久・旧primaryフェンスを証明できるときだけ利用。満たせなければ新規2資源の見積を取得 | 配置先、運用責任者、初期/継続費、構築日程は根拠未入手。決定後に実台帳adapterと昇格/停止演習。購入は別許可 |
| V12鍵と端末資格の所有 | 32 byte AES鍵を業務DB外の秘密管理境界で保全し、旧鍵を再交付期間中保持。認証担当が端末資格の発行/失効、U-R1が同一scope内の再照合 | 具体保管先・管理者・保持期間、TSK-506/U-G1/U-S1の項目別受理が必要。既存シークレットは調査しない |
| 業務DBと外部台帳のexact資産 | 本文の3候補行と4業務資産、owner限定固定関数、app直接DMLなし。attempt所有tupleと一度限りclaimを必須とする | exact DDL・関数identity・RLS/ACL・JSON・凍結revisionは未承認。TSK-550 B統合後の実基線と所有調整から導出し、7.7前後値を別受理 |
| 開始・同期の接続 | U-G1同一tenant scopeで開始と初期付与、外部epoch共有ロックは業務commit後まで保持。U-S1は検証済み端末をPortへ渡す | 関数署名、返却DTO/失敗写像、試合/チーム/選手/U-M2/世代/delivery/RG1の全順は担当未回答。実Port・HTTP入口・全経路接合は未完成 |

隔離候補だけで開始できるのは暗号化・予約境界・拒否のコードと使い捨てDB試験まで。正式資産の受理前にmigration/登録/凍結台帳へ反映せず、実配置証明前に通常書込を開かない。
