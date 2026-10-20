# U-R1 / TSK-392: 新4統合確認と新5の着手準備（2026-10-18）

## 新4の完了判定

- PR [#143](https://github.com/masaki1025/pitchlog/pull/143) の最終headは `b06971deceeb86711f73859592357ff0482e2f51`。実統合SHAは `156dd139a893845428a1ecab69632143f7694e0b`。`git merge-base --is-ancestor` で最終headが最新取得済み `origin/develop=156dd139` に含まれることを確認した。後続専用worktree `feature/ur1-initial-rights` はこの基線から作成した。
- 最終headのPR CIは12ジョブすべて成功。新4のPR差分（merge第1親 `493342be37d4383ca572f8d1c826a3f184a4d213` と第2親）で `backend/tests/conftest.py` は0行差分。過去の失敗・取消runを最終headの結果と混同しない。
- 承認済み新4表との照合: 非ロック事前読取と同一scopeの `FOR SHARE NOWAIT` 直前再読、常閉単一状態行、RG1固定2関数/登録、限定owner・RLS・ACL・closed一行seed、欠損/不明/失敗・競合・取消のDB/認可試験、凍結契約/7.7履歴・archiveをPR #143で統合済み。隔離DBの行ロック正常系と製品関数常閉試験は分離して実施した。コア独立レビューの記録と、後続の限定試験是正に独立再レビューがない残余はPRの資料に保持する。PRの逐行確認チェックは人間の記録であり、ここで代行しない。
- **完了範囲は新4のみ**。製品open成功・復元開始関数は新7、U-G1/U-S1の実経路接合と本物の`RecordingRightsPort`登録は新8、D4初期付与は新5。FR-013の引継ぎ・旧世代フェンス・退避を含むU-R1全体のDoDは未達。

## TSK-550 Bへの統合後引渡し

前回の[パス別引渡し](2026-10-15-ur1-recording-rights.md#tsk-550-b向けパス別引渡し本記録を編集解除回答とする)を維持する。guard 3ファイル、認可生成元/派生物、repository登録、正本、migration/closed seed、凍結台帳の**新4分の編集所有は解除済み**。これらの確定先行差分はPR #143の統合 `156dd139` にある。TSK-550 Bは未統合のU-R1枝を比較元にせず、自己の最新developから既存受理履歴・RG1の2登録/限定権限・0032 migrationを保持してB固有差分と7.7値を再導出する。新5は別PR・別受理単位であり、Bが現在編集中の共有資産には触れない。今後の新5で共有ファイルが必要になれば、Bの実統合状態と編集所有を改めて照合する。

読取照合時点でTSK-550 Bの`feature/ux1-fr014-rule-resolution`作業木には認可生成元・`runtime-authz-contract.json`・正本などの未コミット差分がある。U-R1の新5作業木にはそれらの編集を作らず、Bの作業木も変更していない。U-G1の作業木は`origin/develop`より古い専用枝であり、こちらも変更していない。

## 新5の物理契約と所有

既存の[D4裁定案](../features/ur1-recording-rights/d4-decision-proposal.md)と[接続依存表](../features/ur1-recording-rights/port-connection-dependency.md)を引き継ぐ。方式調査を重複開始しない。別担当のTSK-250は永続化写像の正本、TSK-411は復元運用の後続担当で、D4生成アルゴリズム/物理出所の製品実装はU-R1。U-G1は試合開始transaction、U-S1は同期核。これらの担当worktreeを変更しない。

追加の所有照合: NotionのD4非再利用調査検索ではTSK-411の復元手順カード以外に、採用済みの物理発行方式・専用実装担当の記録を確認できなかった。ローカル`probe/beta-d4`枝は2026-10-05の凍結受理ドライランで、D4発行源の調査枝ではない。別担当の未公開調査が存在する可能性は否定せず、新5着手時には提示された調査・裁定を先行資料として照合する。

| 要素 | 既承認の意味・既存の器 | 新5着手前に必要な未承認の物理契約 |
| --- | --- | --- |
| D4 | `bigint`、rollback・過去backup復元後も再利用禁止。試合内`issuance_order`は別の単調列。現通常世代は試合内高々1件。`recording_generations.generation`/`issuance_order`は既存 | 復元外の予約源と永続化成功境界、応答不明時の識別・再照会、配置/障害時の停止、schema/API/認可/凍結資産。二台同期PostgreSQLは**推奨案で未採用** |
| V12 | 現D4・現復旧世代・保持端末への結合、wireは不透明な文字列。終了後P3には不要 | 発行・検証方式、秘密値の保存/失効・寿命、保持端末への安全な返却と端末内格納。仮値・仮秘密を置かない |
| 保持端末 | 同一試合の記録権保持端末は1台。`holder_device`列は存在 | 認証済み端末IDの信頼できる取得元、U-G1の開始入力/応答DTO、端末交換時の境界。任意文字列を信頼済みIDとして扱わない |
| 復旧世代 | 復元前後で再利用禁止、同期では旧世代を拒否。wireの要求境界は既存 | 永続化場所・復元外保全・発行/照合API・型とDB写像。RG1閉状態行だけでは復旧世代の出所にならない |

### D4方式の一括判断候補

**推奨**は既存裁定案の「業務DBの復元範囲外にある専用PostgreSQL primaryと別故障領域の同期standbyで、予約を両側へ耐久記録してからD4を返す」。予約後の業務transaction取消でもD4を戻さない。最後の成功予約を証明できない障害・応答不明・値域枯渇・旧primaryのフェンス不能では新規発行を止める。通常書込とRG1を台帳の毎要求照合へ結合するかは別の可用性判断で、ここでは採用しない。

採用判断と同時に、(1) 業務DBと独立した2配置先・ストレージ/バックアップ境界、(2) クラスタ/資格情報/監視/フェイルオーバー/復旧演習の運用責任者と昇格権限、(3) 初期構築・継続費の見積取得者とMVP日程、(4) 同期standby喪失時と両保全先喪失時の発行停止を確認する必要がある。現時点で配置・担当・単価は未指定なので金額や日程を仮決めしない。台帳単独障害では**試合開始・引継ぎ・復元後の新世代開始が停止**する。RG1が別途健全なら`preparing`作成と既存世代の記録/同期はD4予約の障害だけでは止めない。RG1不明ならそれらもfail-closed。運用open、既存DB/共有環境への適用、有料資源の利用は別判断。

## U-G1開始接続と実Portへの依存

- U-G1の`tenant_transaction_scope`が試合開始・両側スタメン/記憶・U-R1初期付与・`in_progress`遷移を**同一成功境界**で管理する。U-R1 operationは同じ検証済みscopeを受け、D4を耐久予約した後に通常世代を1件作りD3/適用prefixを0とする。業務DB失敗時は試合/スタメン/記憶/世代の全変更を取り消すが、予約D4は再利用しない。二重開始・越境は拒否する。試合行→記録権世代行の順はU-S1 R-16と一致させ、U-M2のチーム/選手行を含む**全ロック順はU-G1/U-S1受理待ち**。
- 公開する内部operationの正確な関数・型、保持端末の信頼済み入力元、V12/復旧世代の返却DTOと失敗結果は未確定。既存の`connection-contract.md`にある`grant_initial_recording_right(scope, *, game_id, holder_device)`形は案で、物理出所・全ロック順の受理前に製品APIとして確定しない。HTTP入口はU-G1所有で、U-R1は独自の公開書込APIを足さない。
- RG1新4の提供物は`repositories/rg1.py`の固定読取2operation。`sync/ports.py`の`PORT_IMPLEMENTATIONS`は空で、本物の`RecordingRightsPort`実装クラス・登録・利用可能コミットは**未提供**。新5の初期付与だけでもPort全体の完成とはしない。新8の実接合・T8までの提供予定日は、D4/V12/端末/復旧世代の物理契約と個別資産受理がないため確定不能。

## 先行できる試験準備と停止点

物理値を仮作成せず、隔離DBでの受け入れ表を準備する: 正常な初期1件とD3=0/現世代一意、同一試合二重開始、他テナント/欠損試合、開始transaction取消時の全未確定と予約D4非再利用、台帳応答不明/standby喪失時の発行停止、試合行→世代行とU-M2を含むロック順、開始直前のRG1閉鎖、旧D4/復旧世代/V12/端末不一致。初期付与の実DB試験とU-G1実入口結合試験は区別する。予約源・V12・復旧世代を偽装した製品正常系でDoDを閉じない。

**新5製品実装の停止点**: D4方式/配置・運用、V12/端末/復旧世代の物理契約、U-G1/U-S1の開始契約と全ロック順、必要な正本/DDL/認可/凍結資産の個別承認。承認前に新5製品コード・正式台帳・運用openへ進まない。承認後も新5だけを別ステップ/PRで実装し、独立レビューと人間逐行確認を区別する。

## 2026-10-18: POの方針と新5一枚判断資料

POは新4の完了・`156dd139`統合を受領し、承認待ちへ戻さないよう指示。D4は業務DBの復元範囲外にある同期保全の専用PostgreSQL 2台を**推奨方式**として具体化し、耐久性を証明できない障害時の新規発行停止を維持する。配置/費用/運用担当や有料資源作成は未承認。既存2資源が安全条件を実証できる場合と新規2資源が必要な場合、V12/端末/復旧世代、開始関数/DTO/失敗・全ロック順、承認後の新5範囲を[一枚判断資料](../features/ur1-recording-rights/step5-decision-sheet.md)に整理した。現行開発composeの2サービスは同期standbyではなく、実配備先も未測定。チーム認証はtenantだけを返し、端末IDを証明しない。`recording_generations`にV12照合値と復旧世代の列はなく、これらを実装済みと扱わない。実装後の試験証跡を新5着手前条件に繰り上げない。

U-G1カードへの項目別照会コメント`3fd93b75-e687-8187-8d3f-001d93090937`は関数・DTO/応答消失・全順/D4予約位置・失敗写像を、U-S1カードへのコメント`3fd93b75-e687-813a-bebc-001d41bdd290`は同期Port型・逆順/失敗分類・復旧世代の停止境界を対象にした。**返信は未確認で、担当受理済みにはしていない**。既受理のRG1二段階Portや試合行→世代行の順は再照会していない。

## 2026-10-18: D4設計方針採用後の物理契約差分

POはD4について「業務DBの復元範囲外・別故障領域の専用PostgreSQL primary＋同期standby、旧primaryのフェンス、耐久性を証明できないとき新規発行停止」を**設計方針として採用**した。上の「推奨案で未採用」はこの日時以前の記録で、配置・運用責任・費用・有料資源・物理DDLの承認には変わっていない。V12・端末・復旧世代と開始/同期接続の[差分案](../features/ur1-recording-rights/step5-physical-contract-annex.md)を追加し、[一枚資料](../features/ur1-recording-rights/step5-decision-sheet.md)から参照した。計画には**未承認の最小追補候補**を記載した。新5製品コード・既存DB・正式凍結台帳は変更していない。

読取調査: 最新`origin/develop=156dd139a893845428a1ecab69632143f7694e0b`。開発`docker-compose.yml`の2 DBは同期複製ペアではなく、`docs/ops/deployment.md`は実配置先未測定。ローカルDocker contextに見える隔離試験コンテナから転用可能な別故障領域2配置先は証明できない。接続資格情報は読んでいない。現認証`verify_tenant_id`はtenant/期限だけ、`TenantContext`はtenantだけ。`RecordingGeneration`にV12 digest/復旧世代はなく、`RecordingRightsPort.holds_recording_right`にも端末引数がない。よって端末真正性は新5の内部operationと新8の実Port双方の接続契約が必要。

今回の推奨差分: V12のdigest照合と暗号化した同一開始要求への再交付、認証と結合した端末資格、外部D4台帳の別復旧世代系列、U-G1同一scopeの開始要求ID/DTO/失敗型、U-S1への検証済み端末入力。復旧世代を毎書込で外部照合する案は、台帳障害時に既存世代の書込も止めるため、従来のD4障害時停止範囲と異なる**PO判断事項**。外部照合だけでepoch切替との原子性を主張せず、復元制御の先行閉鎖とフェンスを前提にする。代案は管理された復元/起動時照合だが、稼働中復元禁止の運用証明を要する。鍵の保管先、端末資格の所有、具体HTTP結果、全ロック順、実配置/費用/日程は未決。

U-G1カードへ追加の具体差分照会`3fd93b75-e687-813c-b168-001d47dfc624`、U-S1カードへPort署名・呼出位置/復旧世代停止範囲の照会`3fd93b75-e687-8130-a431-001d1e2d5d1e`を送った。いずれも**回答待ちで未受理**。既受理のRG1③-a/⑧とゲーム行→世代行順は再審査しない。TSK-506のHTTP端末資格導出は担当接続待ち。ステップ表は変えず、新5の隔離実装だけを実配置前に先行できる最小追補を人間判断へ出す。新7の運用open/復元開始、新8の本物Port結合は別ゲートを維持する。

## 2026-10-18: 新5隔離候補と既定レビュー

依頼者は、V12の同一要求・同一認証済み端末への暗号化再交付、端末資格と認証の結合、復旧世代の毎書込照合と不明/不一致時の既存世代を含む停止を採用し、新5の**隔離候補**実装・試験・既定レビューを承認した。最小追補を計画へ反映した。exact DDL/JSON・7.7正式受理、実配置/費用/運用担当、共有DB適用、購入、運用open、マージは含まれない。

候補は`recording_rights/initial_grant.py`のAES-256-GCM V12再交付、固定tenant・現端末資格・現世代再照合、D4外部予約/claim境界、外部復旧世代共有ロック保持をProtocolとして実装した。実台帳adapter、登録済み固定operation、U-G1/U-S1の本物Portは未提供。`step5-candidate-assets.md`に業務DB/外部台帳/認可候補と停止点を記録した。TSK-550 Bの共有凍結資産・他担当worktreeは変更していない。U-G1/U-S1へ外部epoch lockを業務commit後まで保持する未受理接続案を照会（それぞれNotion `3fd93b75-e687-81c4-b9cf-001d6bb68af2`、`3fd93b75-e687-81f1-8790-001d47be8102`）。回答は未確認で合意扱いしない。

独立候補レビューは、再交付時のロック下再照合、tenantの暗号AAD束縛、外部epoch読取だけでは足りない直列化、予約応答不明の同一attempt再照会、epochとD4 counter同一行によるロック競合を指摘し、候補へ反映した。さらにP0として、attempt IDを別要求に再利用するとD4が重複し得る点、業務rollback後に同IDを再投入できる点を検出した。予約行へtenant/game/start_request所有tupleを束縛し、`reserved→claimed`を業務DBへ入る前に一度だけ耐久確定する候補へ修正した。予約応答不明はclaim前に同ID照会、claim後の不明はD4を再投入せず閉鎖する。この時点では最終修正の独立再確認前だった。終端結果は末尾に記録した。

Ruff check、ty check、候補単体とRG1関連25件は成功。使い捨てPostgreSQLでepoch行`FOR SHARE`保持中に別行D4 counterを更新でき、復元側epoch UPDATEがcommitまで待つことを実測した。これは同期standbyの耐久性、実台帳のRLS/ACL、U-G1/U-S1実経路の成功証拠ではない。新5のDoDは未達。次の一括判断は候補DDL/owner/関数/JSON・鍵保管/端末資格所有・復元外台帳の実配置/運用/費用、担当間署名/全ロック順、実基線から導出する7.7前後値である。正式受理前に共有資産へ入力しない。

### レビュー終端と最終限定差分

独立レビュアによる限定再確認は候補のP0/P1が0件。P2として、再交付のロック済み行について試合ID・開始要求IDを関数自身でも照合する防御を提案されたため採用し、誤った行を返すadapterの拒否試験を加えた。この**P2反映差分は独立再レビュー未実施**であり、将来の本人逐行確認対象に含める。P2反映後、claim応答不明の再投入拒否も加えた候補単体15件・Ruff check・ty checkは成功。最終候補で候補単体・RG1関連の計27件が成功。全backend試験・全ハーネスの成功や実台帳の耐久性証明とは扱わない。

依頼者の2026-10-18指示に従い、この承認済み隔離候補を**ローカル保全コミット**へ固定する。これは新5の9ステップ表にいう完了コミットではないため、完全トークン`(ステップ 5/9)`を件名へ付けない。実Port・実台帳・exact認可/凍結資産と7.7受理、担当間接合、全DoDが揃うまで新5完了と記録しない。push・PR・mergeは行わない。

**P2反映後の識別**: 独立限定レビュー時の`initial_grant.py` SHA-256先頭`90a7b33aad2c`、試験SHA-256先頭`03eb3219050b`から、関数内へ`locked.game_id != game_id`と`locked.start_request_id != start_request_id`を追加し、誤束縛adapterの拒否試験とclaim応答不明の負例を追加した。最終ファイルSHA-256は関数`8119c9ebcd80327c64e15074e0221e3f8dc5f8d4d3b6c800aa7002eeeda1d178`、試験`d34c57207115ade86d9ce7b1b8e66bc4d872b40efda354962b6335a23ea16688`。この差分は未再レビュー。

## 2026-10-18: 候補保全後の3群判断資料

依頼者の指示で隔離候補と試験・記録をローカル`68c085852bb57c2f65e30e08a39cd49689bc1d19`へ固定した。pushなし。最新取得済み`origin/develop`は`156dd139a893845428a1ecab69632143f7694e0b`のまま。既存世代表のapp表単位SELECT/INSERT/UPDATEを確認し、前候補の同表へV12 digestを足すと直接参照・更新面が増える問題を発見した。秘密材は新規function_only配達表へ分け、既存世代表のACLは拡大しない推奨変更を[3群判断資料](../features/ur1-recording-rights/step5-three-part-approval.md)へ記録した。これは**新しい具体DDL判断の候補**で、正式migration・認可・凍結資産への反映はしていない。

隔離PostgreSQLで所有tuple不一致と2回目の`reserved→claimed`がSQL条件で拒否される負例を追加した。候補単体・DBの16件、Ruff、tyが成功。実台帳adapterの同期standby耐久、資格発行/失効、U-G1/U-S1実経路や本物Portの合格とは扱わない。U-G1の実作業木に開始側の新受理は見当たらず、U-S1のPort署名も現時点で端末引数なし。両担当の未回答は[判断資料](../features/ur1-recording-rights/step5-three-part-approval.md)の接続表へ残した。TSK-550 B・両担当の作業木は読取のみで編集していない。

最終候補`ba75705e`でbackend Ruff全対象とtyが成功し、候補・RG1関連の使い捨てDB込み28件が成功した。全backend pytest、同期standby耐久・旧primaryフェンス、製品Port/HTTPの検査は未実施。新5の完了判定には用いない。

## 2026-10-18: 群1採用後の固定接続候補と事前レビュー

依頼者は群1を**隔離候補の範囲**として採用した。世代表のapp ACLは拡大せず、V12情報を新しい`function_only`表に分離し、外部`recovery_epoch`と`d4_counter`を別行にする。`claim`候補に予約時と同じtenant/game/start_requestの所有tupleを渡し、使い捨てPostgreSQLで他owner・二重claim・競合を拒否する試験を追加した。[U-G1/U-S1固定候補](../features/ur1-recording-rights/step5-connection-fixed-candidate.md)に署名・DTO・失敗結果・両DBの途中失敗/不明commit時の停止を記載した。認証基盤調査では`TenantContext`はtenant IDだけ、端末資格の製品実装は未提供。既存署名鍵は旧鍵破棄の契約を持ち、V12暗号鍵へ共用できない。鍵保管先・担当は未指定。

[data-model 7.3候補](../features/ur1-recording-rights/step5-data-model-73-candidate.md)は正本へ**未反映**。v0.11 approvedを維持する。現sync-protocol 9-5の作成時初期付与との衝突はU-S1 R-17の作成/開始分割を別正本ゲートで先に確定する必要がある。正本本文が `in-review` になっていないため、今回の独立確認は**正式7.3の1周目に算入しない**。

独立したCodex CLI セッション`01a14ee9-cf12-7120-aaa6-b322c1c90fa7`（gpt-6.1-sol、read-only）は候補全体を事前確認し、**P0 0 / P1 1 / P2 2**。P1=端末資格の最後の照合後に失効するとV12再交付を通せる（実際に候補を呼び再現）。P2=RG1のB7/B10を検査位置ではなくP1/P2/P4対P3で写像すること、現sync-protocolの作成行を開始行へ分割する正本変更を明示すること。**3件全採用**。資格行をscope内で`FOR SHARE`し業務DB commitまで保持する候補へ変え、失効UPDATEが待つ隔離DB試験を追加した。資格失効側の逆順ロックがないことは認証担当の受理待ち。B7/B10と正本改訂範囲を文書へ反映した。この**反映後差分は独立再レビュー未実施**。前回のP2反映差分は今回のレビュー対象に入れた。新5候補の独立レビューは前段の全文/限定再確認2回と今回の事前確認1回の計3回。6.3の追加周を自動開始しない。正式7.3は未使用。

正式資産・7.7・実台帳・製品Port・共有DBは変更していない。後続は、U-S1 R-17正本追随、資格失効側ロック順/公開PortとU-G1の公開結果・全順の項目別受理、正本の正式7.3、exact DDL/JSON・個別受理、7.7実値の順。実配置・鍵管理責任・端末資格責任・有料資源は未決のまま。TSK-550 B/U-G1/U-S1/TSK-506の作業木は編集していない。

反映後の限定検査はbackend `ruff check .`、`ty check`、候補+RG1関連pytest **29件成功**（使い捨てPostgreSQLの資格失効・claim競合を含む）。root `check_docs_status.py` は20文書/違反0。全backend・全ハーネス、同期standby/旧primary/製品Portは未検証。反映後SHA-256は`initial_grant.py=c20d596ba80a7c9e792a472ddde295a261b0dee2977627e7f0391765bdca59c3`、候補試験=`e643efd043775b6f51706661f9a1f7211b69a2047e9c6cd38340a5252cbad0e0`。この識別値の差分は独立再レビュー未実施。

接続候補の文言を追確認し、`start_request_id`を「サーバーが既に永続化済み」と断定した箇所を訂正した。端末が送信前に保持する既存案を参照し、`reservation_attempt_id`の発行者・耐久保存先・rollback後の切替を担当受理待ちへ明示した。応答不明時に同じattemptを再照会できる実装がない状態を安全な再試行済みとは扱わない。この文書のみの最終修正も独立再レビュー未実施。

## 2026-10-18: R-17正式7.3起案と担当別受理単位

依頼者は`7b031b3e`までを受領し、承認済み「初期付与は試合開始時」にsync-protocol 9-5を合わせる限定正本改訂と正式7.3を指示した。U-S1の既承認R-17を根拠に、最新`origin/develop=156dd139`から別worktree`feature/tsk547-start-grant-canonical`でv0.9 `in-review`を起案コミット`5ad64e10`へ固定した。U-S1の作業木は変更していない。正式7.3の全文第1回はP0=1/P1=2/P2=0、3件全採用。復元された`preparing`を新D4の復元完了対象から除き、開始取消にスタメン記憶を含め、作成/開始のRG1コミット競合を11-4へ足す反映コミット`85f4b565`を作成した。差分・影響節の正式第2回は進行中。候補の事前レビュー3回および最後の修正差分未再レビューとは**別集計**であり、正式7.3やコード再レビューとして重複計上しない。正本の人間承認は未了。

U-G1/U-S1/認証担当の未受理を[担当別受理シート](../features/ur1-recording-rights/step5-owner-acceptance-sheet.md)へ分けた。公開署名/DTO/失敗と全ロック順、資格失効対書込みの直列化、外部予約attemptの耐久保存と予約応答消失・業務rollback・commit結果不明の各停止/再照合、独立V12鍵束の寿命が対象。**担当の無回答は合意ではない**。実台帳、実端末資格、製品Portは未提供で、隔離候補の成功と区別する。

既存[固定接続候補](../features/ur1-recording-rights/step5-connection-fixed-candidate.md)の列挙では端末資格行と外部epoch行の取得順が逆に読めたため、候補関数と担当別シートに合わせて**外部epoch共有→資格行共有**へ整えた。これは未受理の全順候補の内部整合であり、認証担当/U-G1/U-S1の受理を代記しない。

担当別シートへ、開始commit後・HTTP送信前の資格失効競合は応答側の直列化契約が未受理であること、V12旧鍵を稼働DBだけでなく許容する復元世代の旧暗号文が消えるまで保持することを追記した。署名鍵の旧鍵破棄手順を暗号鍵へ流用しない。鍵保管・配布先と運用担当は未指定のまま。

独立した使い捨てPostgreSQL試験に、D4 counterと予約行の同一外部transaction確定後の応答消失を模し、所有tupleによる同一attempt/D4再照会、別tenant拒否、claimed D4の非再利用を追加した。これは実台帳adapter・同期standby耐久・不明業務commitの解決を証明しない。backend `ruff format`後、`ruff check`、`ty check`、候補+RG1関連pytest **30件成功**。全backend/全ハーネス、製品Port実経路は未検証。正式資産/7.7、実配置/費用、運用open、共有DB適用、push/PR/mergeは変更していない。

## 2026-10-18: #148未統合中の新5隔離試験

TSK-547の限定正本v0.9はPO承認・Draft PR #148のHEAD `d643da6e`へ固定されたが、未統合である。この枝を新5の`develop`基線へ取り込まず、新5は引き続き`origin/develop=156dd139`を比較元とする。統合後に実基線を取得し、正本・共有資産を再照合する。

確定した意味「初期付与は開始時、作成時と復元調整解除時の`preparing`には付与しない」に対応し、隔離候補の復元試験を追加した。業務DBだけを`preparing`のバックアップへ戻し、外部D4発行元と復旧世代を維持する。解除前の旧世代書込みは拒否され、解除後に業務DB復旧世代が外部現値へ一致して初めて開始候補がD4を発行する。旧D4は再利用しない。試験は隔離代役の状態遷移であり、製品の復元解除、同期standbyの耐久性、旧V12の実Port拒否を証明しない。backend Ruff、ty、候補/RG1関連pytest **31件成功**。初回の試験fixtureは業務DB復旧世代の更新を欠き1件失敗したため、解除後の一致状態を明示して再実行した。

未決の管理単位は分ける。**担当別契約未受理**は[担当別受理シート](../features/ur1-recording-rights/step5-owner-acceptance-sheet.md)のU-G1開始署名・DTO・結果/不明commit・全ロック順、U-S1実Port署名・呼出位置、認証/TSK-506の資格発行・失効/応答競合である。**物理・運用未確定**は外部D4台帳の実配置・耐久性/旧primaryフェンス・費用/運用担当と、独立V12暗号鍵束の保管・配布・復元可能期間・運用担当である。前者の未回答を後者の承認と混同せず、隔離候補の成功も両者の受理に数えない。#148の`f69c6b3d`はpush済みだが未統合であり、新5基線は引き続き`origin/develop=156dd139`とする。

## 2026-10-18: #148統合後の実基線と新5再照合

PR #148は最終HEAD`f69c6b3d`を`5bb1ff89306712c1de61c3a0152141c8f771b3a0`でdevelopへ統合。新5作業ブランチは最新`origin/develop`をmergeコミット`958122dd`で取り込み、競合なし。これより前の「#148未統合」は履歴上の事実として残し、**現在の新5停止理由からは外す**。計画・接続契約・data-model候補の現在地をsync-protocol v0.9 approvedへ追随した。

意味と検査の対応: (a) 初期付与は開始時、作成時と復元調整解除時の`preparing`には付与しない—候補の`lock_preparing_game`と復元`preparing`試験で開始前の権利行なしを照合。(b) 既存D4対象0件でRG1解除時の発行0件—統合済み正本9-5とroot設計伝播試験で検出する。**製品解除関数は新7で未実装**のため新5候補の製品合格とはしない。(c) 復元後の初回開始のD4非再利用—復元外台帳代役の発行済みD4を維持した隔離試験で再照合する。実台帳の同期耐久/旧primaryフェンスは未検証。backendの候補・RG1関連33件、root設計伝播215件、backend Ruff・ty、docs-status（20文書/違反0）、明示plan指定の`check_plan_docs_sync.py`が成功。plan指定なしの同検査は枝名`ur1-initial-rights`から存在しないplanパスを導出して失敗したため、正規の`docs/features/ur1-recording-rights/plan.md`を明示して再実行した。

## 2026-10-18: 新5の正式審査準備と未回答の絞り込み

既承認の方式と#148統合を維持し、[data-model 6-1限定候補](../features/ur1-recording-rights/step5-data-model-73-candidate.md)へ本文案と影響節を固定した。現時点でU-S1の`feature/us1-sync-port-surface`が同じ`docs/design/data-model.md`をTSK-562向けに未コミット編集（49行追加・4行変更）しているため、U-R1は同正本を並行編集しない。正本の版・統合順が決まるまで`in-review`起案と**正式7.3全文第1回は未開始**であり、候補資料の確認を正式周回と呼ばない。U-S1側の編集・受理済み事項は改変しない。

[3群判断資料](../features/ur1-recording-rights/step5-three-part-approval.md)には専用owner、対象表のFORCE RLSと列ACL、既存世代表のapp ACL不変、RG1追加列の読取限定、固定関数のPUBLIC剥奪という審査候補を明示した。具体的な関数identity/本文、外部claimの信頼済み束縛、端末資格の真正性は未受理なので登録済み製品関数・正式DDL/JSONは追加していない。外部予約DDLに同一要求の`reserved`高々1件を強制する部分一意索引が漏れていたため、隔離DB試験と一致させて追記した。`claimed`後・業務DB commit結果不明時の新attemptは索引だけでは守れず、耐久attempt照会とU-G1/U-R1契約受理まで停止する。

[担当別受理シート](../features/ur1-recording-rights/step5-owner-acceptance-sheet.md)にU-G1、U-S1、認証/鍵、D4運用の未回答だけを整理した。既照会の③-a/⑧、試合行→世代行、開始時付与は再審査しない。U-G1/U-S1の新しい項目別受理、認証済み端末資格の所有・失効順、V12鍵の保管/運用者、外部台帳の配置・責任・費用は未確認。実Port・同期保全台帳は未接続で、新5のDoDと7.7正式受理は未達。正式資産、共有DB、運用open、push・マージは行わない。

## 2026-10-19: U-S1からの編集枠引き渡しとdata-model 7.3起案

U-S1後任との直接照合で、先行順を**U-R1 §6-1 → U-S1墓標**と確定した。U-S1は受領した墓標候補3ファイルの差分SHA-256`89093116acff4ee9465090f1650884ce636bb92a6a449ffc7fb55d734ee9286a`を保全し、コミット`d9c6bd86`後に`data-model.md`・`docs/README.md`の編集停止とU-R1への所有解除を明示した。U-R1は§6-1と対応履歴・索引を現approved v0.11からv0.12候補として先行起案し、U-S1はその実統合後のdevelopから墓標の版を再導出する。U-S1後続案を本ゲートに混ぜない。U-S1の所有記録は同枝の`docs/worklog/2026-10-19-us1-ownership-and-connection.md`にある。

data-model v0.12候補を`in-review`として起案し、変更履歴行へ7.3-7の「本改訂で確定する範囲／実装時に確定する範囲／対象外」を記入した。**7.3-1の暫定適用版は開発規約v1.19、条文コミットSHAはこのin-review化コミットの第一親`00c57bb9e3f22b9839ce163e768a4e1f21cb2d79`**（その状態でv1.19がapproved）。初回敵対レビュー直前に最新版と条文SHAを再確認し、異なれば記録を更新してから実行する。正式レビューは本起案コミット後に第1回全文として行う。新5の確定ゲート周回は0から開始し、過去の新4の2回と混同しない。U-G1/U-S1接続、認証/鍵、実D4配置の既存未回答一覧は維持し、受理を代記しない。

### data-model v0.12 正式7.3第1回（全文）

起案コミット`a6318656f9ebf3e942a020b93c3b83696d688c3b`を固定し、適用版v1.19・条文コミット`00c57bb9e3f22b9839ce163e768a4e1f21cb2d79`に変更がないことを確認して、`.claude/scripts/codex_run.py review adversarial`で独立したread-only全文レビューを実施した（Codexセッション`01a15077-6e7b-7ce0-9e5e-3e6eff93f4a4`）。結果は**否決 P0=1 P1=5 P2=0**。6件はすべて起因、全件採用・不採用0、(B)送り0。採用反映1周として計画frontmatterを`確定ゲート周回: 1`へ更新する。

| 指摘・所在（典拠確認） | 分類 | 採否と反映 |
| --- | --- | --- |
| 外部復旧世代の読取だけでは復元側の更新と業務DB commitが競合する（data-model§6-1、sync-protocol§9-5、step5-physical-contract-annex） | P0・起因・(A) | 採用。外部epoch行の共有fenceを同じ行の復元側排他更新と衝突させ、業務DBのcommit/rollback結果確定まで保持する不変条件を§6-1へ追加。実Port接合・台帳耐久の実証は後続に残す |
| 開始一括取消の列挙からスタメン記憶が漏れる（data-model§6-1、sync-protocol§9-5） | P1・起因・(-) | 採用。§6-1の一括確定・取消へ記憶更新を追加 |
| `function_only`配達行の到達経路が既存7ロールで未定義（data-model§3-2・§6-1） | P1・起因・(A) | 採用。初期記録権専用のNOLOGIN/NOBYPASSRLS関数owner区分を3-2へ追加し、RG1/認証/共有/管理ownerと分離。具体名・SQLは実装時に残す |
| 配達行の1世代/1開始要求の一意性が全数表に無い（data-model§3-4・§6-1） | P1・起因・(-) | 採用。3-4の実装待ち表へテナント内の2件を追加し、migration・manifestと同時に主表へ移す |
| 同一認証済み端末と資格・開始時保持端末の結合が不足（data-model§6-1・§8-3） | P1・起因・(-) | 採用。§6-1へ認証済みセッション、資格、配達行のtenant/device一致を明記。発行・失効の物理方式は担当受理待ち |
| 5-4/12-8の「D4の列まで・機構はTSK-250」という旧申し送りが新6-1と矛盾（data-model§5-4・§12-8） | P1・起因・(-) | 採用。論理境界は§6-1、実発行/台帳はU-R1新5、RG1解除は新7、I6は既存TSK-250へ整理 |

専用owner区分・配達行の一意性・fenceは初回の`function_only`配達行／復元外D4という宣言を成立させるための直接影響であり、新しい製品機能や運用openを追加しない。変更履歴の射程文言へ影響節を明記した。第2回はこの反映差分と影響節だけを対象とし、結果が出るまで正式7.3の収束とは記録しない。

**別の未成立条件**: U-G1/U-S1/認証・TSK-506の署名・結果・全ロック順・端末失効競合の項目別受理、独立V12鍵の保管/運用、D4外部台帳の実配置/耐久証明・費用/運用担当、data-model側7.3と具体資産/7.7。#148統合や隔離試験成功をこれらの受理、運用open、製品Portの完成へ読み替えない。

### data-model v0.12 正式7.3第2回（反映差分と影響節）

反映1周目コミット`35382c1f8bcdd6749c5a32e3f80042fc6782782c`を固定し、`a6318656..35382c1f`の差分と直接影響節を独立read-onlyレビューした（Codexセッション`01a1507e-1239-72a3-bf09-a70c15fe20b8`）。結果は**否決 P0=1 P1=1 P2=0**。2件とも起因で採用・不採用0、(B)送り0。反映2周目として以下を是正し、第3回は規約6.3の2回目P0残存時の自動追加枠による**P0限定差分1回**とする。

| 指摘・所在（典拠確認） | 分類 | 採否と反映 |
| --- | --- | --- |
| 外部epochを先に照合し、復元側が更新した後で共有fenceを取ると古い値でcommitできる（data-model§6-1、物理契約案の全順） | P0・起因・(A) | 採用。外部共有fence取得を現値読取・照合より前に置き、ロック下の値だけで最終判定する。業務DBのcommit/rollback結果確定まで保持し、事前読取を最終判定に使わない。物理契約案の全順へ追随 |
| 実台帳配置・耐久/旧primaryフェンスの証明を新5へ置く申し送りが承認済み計画の新7と衝突（data-model§5-4・§12-8） | P1・起因・(-) | 採用。新5は隔離候補のoperation/adapter/試験、新7は別判断の実配置・耐久/フェンス証明とRG1安全解除へ修正。計画のステップ表は変更しない |

U-S1の墓標改訂とは並行編集せず、正本・索引の編集所有は引き渡し済みの先行U-R1だけが保持する。U-S1後続の版はU-R1の実統合後のdevelopで再導出し、v0.13を予約確定しない。U-G1/U-S1/認証・鍵・D4運用の未回答は既存一覧を維持し、今回の7.3採用から受理を推定しない。

### data-model v0.12 正式7.3第3回（P0限定）と承認待ち

反映2周目コミット`983039c58918fdb282be67e21091040515200a9b`を固定し、`35382c1f..983039c5`のP0是正差分と直接影響箇所だけを独立read-onlyレビューした（Codexセッション`01a15083-3587-7c31-ad7f-7092151b70a7`）。規約6.3の自動追加枠1回を使用した結果は**可決 P0=0 P1=0 P2=0**で、P1/P2は審査範囲外。新規指摘0、採否・反映0、追加の反映周コミットなし。正式7.3の審査3回、採用8件（P0 2/P1 6）、不採用0、反映2周。第2回のP1担当境界修正と本段落の記録は独立再レビュー対象ではなく、最終差分の人間確認へ残す。

**次の判断**: `data-model.md` v0.12の§6-1と直接影響する§3-2・§3-4・§5-4・§12-8、変更履歴、索引、および未再レビューの反映2周目差分を一括で確認し、7.3-8の正本承認可否を判断する。承認前に`approved`へ変えない。具体DDL/認可・7.7、U-G1/U-S1接続、実配置・鍵・運用はそれぞれ既存の別ゲートを維持する。U-S1後続の墓標改訂との並行編集は行わない。

### 2026-10-19 data-model v0.12の人間承認と正本確定

山田正輝が本会話で、固定HEAD`8f18b61f3b93ac997df1d0e594450818301cfedb`のdata-model v0.12候補につき、§6-1・審査で対象とした直接影響節（§3-2・§3-4・§5-4・§12-8）・変更履歴を**2026-10-19に承認**した。審査は第1回全文P0=1/P1=5、第2回反映差分と影響節P0=1/P1=1、第3回P0限定P0=0。8件全採用・不採用0、反映2周。**第2回の担当境界P1反映差分は独立再レビュー未実施**のまま承認対象として確認された。本人逐行確認の実施記録はない。これを根拠に同正本を`approved`へ変更し、索引・計画・本ログを同期する。

U-S1の墓標改訂は後続とし、U-R1統合後の実developから版番号を決める。今回の正本承認は具体DDL/認可・凍結資産、接続契約の担当受理、P-6、実D4台帳の耐久性、鍵・端末資格の提供、運用openには及ばない。認可・凍結資産への影響は別途照合し、7.7の実値が必要なら正式受理資料として独立提示する。

### 2026-10-19 PR #156の正本参照・ORM・TB002切り分け

最新`origin/develop=015dfa9d`をローカルmerge `8a2f3326`で取り込んだ。公開中のDraft HEADは`836232d6`であり、ローカルの未push候補とは区別する。依頼者は`shared-preconditions.json`と`schema-manifest.json`の**正本参照だけ**の候補作成・検証を許可した。前後の完全値、ORMシートの新規2行、TB002の47箇所/21シンボルと条件2登録の必要差分、7.7の影響8資産と条件付試算、#156の提出範囲を[閉鎖判断資料](../features/ur1-recording-rights/step5-pr156-closure-gates.md)へ固定した。正式認可台帳、凍結履歴、snapshotは未編集であり、条件付試算を受理値とはしない。

ORMシートは既存363行の判定・理由を全件一致で維持し、N3/N7各1新規行の判定欄を空欄にした。関連試験21件成功、未判定検出試験1件はこの2行の人間判定待ちとして赤。`check_shared_preconditions.py`、schema manifest試験14件、関連authz2件、TB002条件2既存試験32件、変更試験のRuffとroot ty、凍結invariantsは成功。現TB002実走査は47件で赤。読取専用の限定所有パス試算では、allowlistとsync-protocolコア登録の片方だけでは47件のまま、双方を同じファイルへ限定すると0件で、隣接ファイルのTB002と同ファイルのTB001は残る。これは製品認可の正式変更や7.7受理を代替しない。

U-S1主担当`01a14f9e-f825-7441-b7e1-1179a938254f`へ4項目を直接回答した。検証済み端末文脈、False/照合不能例外、FunctionWriter固定関数口、fenceのcommit結果確定までの保持・不明時隔離は**接続方針として受理**。後者の耐久相関、実台帳、隔離解除と権威あるcommit結果照会はU-R1候補で未提供として明記した。契約受理を実Port提供や耐久性合格へ読み替えない。U-S1の受領をもって認証・U-G1の未回答を受理済みにしない。本人逐行確認・Draft解除・マージは未実施。

### 2026-10-19: #156 正本参照の正式差分承認と TB002 限定候補

POは`shared-preconditions.json`のdata-model Git blob `21a85f5e794baaa05376b06aec7185cada6c33c8→b1dc01f4f263fb31e1d257b2f1e937dc45a99dc0`、`schema-manifest.json`の同書SHA-256 `a4504bbb2cf3fcbec13ea4fbb0ccd7d8ab2b9b66dafec3fc01f763ed06b16bfc→1f25908d029887ddfcbad213cf66ee9fdb1311b7e7cf8a62e47c1396f36dfdc3`を承認。実ファイルと一致を再確認した。意味行・権限・既存履歴は変更しない。ORMの既存363判定は保持、新N3/N7の判定は空欄。U-S1主担当の項目別契約待ちは解消済みだが、実Port・実台帳の未提供は別条件。

前節の「条件2のowner pathへファイル1本を追加する」試算・値は今回のPO指定により**不採用・失効**。TB002の47件を型/DTO 14、検証/直列化10、再交付7、復旧世代再照合9、予約/claim/保存7へ分類し、実ソースSHAと47組の行番号・シンボルに固定した限定登録候補へ置換した。`condition_2_owner_paths`とSQL API許可は不変。同ファイルだけをcore3領域へ加える候補も用意した。候補ソースの変更、隣接ファイル、別条件を拒否する試験を追加。詳細は[閉鎖判断資料](../features/ur1-recording-rights/step5-pr156-closure-gates.md)。認可/凍結契約と7.7は正式受理前で、履歴・承認者/日付は未入力。

限定候補のcore guard全262件、TB002対象の負例6件、ORM/正本参照の既判定21件、root Ruff/tyが成功。TB002検査器の全372件中371件は成功、残り`test_repository_is_green`は8凍結資産のrevision/履歴未受理で予定どおり赤。ORM完了検査はN3/N7の人間未判定2件で赤。隔離候補の初期付与20件は成功。8資産の候補revision・射影・snapshot名とcorpus digestは[受理payload案](../features/ur1-recording-rights/step5-pr156-7.7-payload-proposal.json)へ比較元`origin/develop=015dfa9d`から再導出した。正式履歴・snapshot・manifestは未変更。新5隔離候補の独立レビューは前段3回を使用済みで、今回の認可検査器・core guard差分の独立レビューは未実施。6.3追加1回のPO裁定と、ORM N3/N7の人間判定を依頼済み。どちらも回答前に実施・記入しない。#156はDraftを維持し、push/merge/本人逐行確認を代行しない。

固定候補の識別: ローカルHEAD`8a2f332626a57762cab90d6957a56624a5e8e650`、比較元`origin/develop=015dfa9db0b7b8740369911a9cb5195dd59a62ea`、限定契約候補のbase-allowlist SHA-256`34fcac4d81af1b78389c263363709eaf04eaff00a0bc8846ed233a557cf3f338`と検査器SHA-256`3b7b90f8476b30c0596439b33ce75db1c23c6c930b359e03804f00df280e0e7e`、未追跡7.7 payload案SHA-256`34915e053e6804df9c9385f98d8702b7595505a1276b595e65baac0e46e33e3c`。レビュー・ORM回答で差分が変われば識別を再計算する。8資産の候補after射影とsnapshot名、archive corpus候補digest`1535ff098defae52a7cdd653e54032d9244f118f62c6801f8fc4fc3c1f085085`を閉鎖判断資料へ記載した。後者は既存corpus関数を隔離コピーへ適用して再確認済み。正式7.7受理値として台帳に転記していない。

### 2026-10-19: #156 追加独立レビュー第4回のPO裁定・対象固定

POは既存新5候補レビュー3回を保持し、今回の認可検査器・core-guard限定差分、TB002 47箇所の許可条件と負例、直接影響する7.7候補に対する**独立レビュー追加1回**を規約6.3で承認した。対象tracked diffは`.claude/core-areas.json`、`contracts/tenant_boundary/base-allowlist.json`、`scripts/check_tenant_boundary_bypass.py`、`scripts/core_guard.py`、`tests/test_check_tenant_boundary_bypass.py`、`tests/test_core_guard.py`のHEADとの差分で、SHA-256は`d054e2397564c314505a808bb099e55f593576d2740840915bd3a9939cf75d27`。直接影響の受理payload案SHA-256は`34915e053e6804df9c9385f98d8702b7595505a1276b595e65baac0e46e33e3c`、47件分類・資料SHA-256は`e882c5fc1af002f052ed603e15c396a8f982c56c1b4f3e3f7df6dfcd6a75d5a6`、固定対象の製品候補ソースSHA-256は`c20d596ba80a7c9e792a472ddde295a261b0dee2977627e7f0391765bdca59c3`。比較元`origin/develop=015dfa9db0b7b8740369911a9cb5195dd59a62ea`、ローカルHEAD`8a2f332626a57762cab90d6957a56624a5e8e650`。レビューではP0/P1/P2を判定し、シンボル・操作・経路限定、別操作・別経路・任意DB APIの拒否、7.7 before/after・snapshot・corpusの算定を確認する。レビュー後の追加変更は元SHAとの差分を記録して候補を再固定し、自動で次の独立レビューは行わない。

同日POはORM新規N3出現106・N7候補038をそれぞれ「対象外」と判定した。理由はN3がプロトコル・担当境界で列更新禁止ではないこと、N7が外部fence保持期間で必須列・NULL性・defaultではないこと。両シートの新規行へ人間の判定と典拠を転記し、既存363行の判定・理由は維持。D4非再利用とfence保持の実検証は U-R1 新5・新7とU-S1の契約・試験に残す。ORMシート試験13件は成功。今回の裁定は7.7 payload`34915e05…`の正式受理ではなく、正式台帳とsnapshotは未変更。

ORM判定転記後、生成器の`parse_sheet_rows`で4シートをHEADと比較し、`(正本側,実装側,判定,理由)`のmultisetで旧363行の欠落・変更0、新規N3/N7各1行だけの追加を確認した。`uv run pytest -q -n 0 tests/test_orm_acceptance_sheets.py`は13件成功。新行の「対象外」はD4/fenceの別経路検証を消さない。

### 2026-10-19: #156 限定差分の追加独立レビュー結果と7.7記録案

上記のPO裁定による追加1回を、候補作成に関与していないread-only Codex CLIの独立セッション`01a150ad-9b1c-73c2-b1fc-495b60eebebc`で実施した。対象は上記tracked diff SHA-256`d054e2397564c314505a808bb099e55f593576d2740840915bd3a9939cf75d27`、7.7 payload SHA-256`34915e053e6804df9c9385f98d8702b7595505a1276b595e65baac0e46e33e3c`、閉鎖判断資料SHA-256`e882c5fc1af002f052ed603e15c396a8f982c56c1b4f3e3f7df6dfcd6a75d5a6`、固定製品候補ソースSHA-256`c20d596ba80a7c9e792a472ddde295a261b0dee2977627e7f0391765bdca59c3`。先行3回の履歴は保持し、本件は第4回として別計上する。

結果は**可決 P0=0/P1=0/P2=0、指摘0、採否・反映なし**。検査器の許可をソース実測47行・シンボルとの完全一致で確認し、別経路・別行・別シンボル、TB001、任意の`Session.execute`と生SQL `text`の拒否も確認した。core登録は既存基線からの追加1経路に限定される。9資産のbefore/after、うち8資産のrevision・射影、外部検査器digestと候補corpus digestを再計算して一致した。レビュー用read-only環境では`uv`のcache lockを作れずpytest実行はできなかったため、試験成功の根拠は作業環境での別実行に限定する。レビュー対象のコード・契約差分はレビュー後に変更していない。追加レビュー枠は消費済みで、自動追加周回はしない。

7.7の単一履歴権威`contracts/tenant_boundary/base-allowlist.json`へ後で入力する**受理待ちの記録案**を[別JSON](../features/ur1-recording-rights/step5-pr156-7.7-record-proposal.json)に切り出した。これはレビュー済みpayloadの`acceptance_id`、前後識別子、change、movement_fact、reasonから機械的に導出した提案で、SHA-256は`c13ef970c4d24a73549f9d5b3ec9befdbc44b90a882aa2e0db13c027e31cf7ed`。記録案には承認者・日付を入れず、正式台帳・snapshot・archiveは未変更。レビュー後の追加はこの派生資料と本作業ログだけで、固定候補の再レビューを要するコード変更はない。現payload`34915e05…`はPOの正式7.7受理待ちであり、受理済みとは扱わない。

### 2026-10-19: #156 7.7受理後の反映検査で検出した連動digest漏れ

山田正輝は2026-10-19に、比較元`015dfa9d`・ローカルHEAD`8a2f3326`、限定差分`d054e239…`、payload`34915e05…`、単一記録案`c13ef970…`、照合表`e882c5fc…`、corpus候補`1535ff09…`を指定して7.7を正式受理した。宣言コミット`f43d749e`、JSON登録コミット`a94a220c`をこの順で作成した。どちらも新5完了コミットではなく、通常pushは未実施。

正式反映の診断中、`test_check_tenant_boundary_bypass.py::test_generated_provenance_corpus_never_weakens_develop`が`base-allowlist.inventory.sha256`の不一致を検出した。`db-api-inventory.json`のrevision 15→16で実ファイルSHA-256は`b103a48b6190e6e18cb45e456c75ec26321571c10fafc5d2c2152011f0bed8d3→522b6351474f200da48451edd511ba944c05d5159142b675f9ccec095d76b636`となる。さらに、revision追随した4資産の`source_digest`も更新が必要である。診断用の連動修正後、TB002検査は371件目まで進み、残る`test_repository_is_green`は旧候補base snapshotが新規孤児として残ったために失敗。旧候補snapshotを除いた診断用状態では同試験が成功し、archive関連36件も成功した。

**受理対象値が変わるため、旧受理を改訂案へ流用しない。** 必要な追加差分は[改訂判断資料](../features/ur1-recording-rights/step5-pr156-7.7-amendment-brief.md)へ固定し、元payload・元記録案は保持した。改訂payload SHA-256`8559617ed7714bc85a8dfa51f6bfad866aa43d40eaf39d266eeba4a2a90e96dd`、改訂単一記録案SHA-256`550d5c78aa77597c52459514f017205580b23ab03c3026432519c41fb6d41025`、base after snapshot`8e7f41fcf9d1edca4e4bac871bebc6094fec37763b65659f246bb80379030f9e`、corpus after`51264ae66762fc42e5e789ecf3e7c4067528e2869c36939394b91ed6af95bdf1`。正式台帳・資産revision・snapshot・archiveへ加えた診断用の未コミット変更はすべて戻し、受理済み履歴とbeforeは保持。新受理まで再反映・製品コード追加・push・CI・PR本文変更を停止する。追加の独立レビューは行っておらず、従来0/0/0は旧固定差分の結果として維持する。

### 2026-10-19: 改訂7.7の正式受理・反映と移動したdevelop

山田正輝は本会話で改訂payload SHA-256`8559617ed7714bc85a8dfa51f6bfad866aa43d40eaf39d266eeba4a2a90e96dd`と改訂単一記録案SHA-256`550d5c78aa77597c52459514f017205580b23ab03c3026432519c41fb6d41025`を**2026-10-19に正式受理**した。元payload`34915e05…`・元記録案`c13ef970…`・元照合表`e882c5fc…`は修正せず保持する。旧案のinventory参照と4件の自己封印digest漏れが訂正理由であり、元レビュー0/0/0は訂正差分の独立レビューを意味しない。

正式集約台帳の履歴末尾は受理前に#143で、#156は0件だった。承認済み改訂記録を承認者`山田正輝`・承認日`2026-10-19`として**1件だけ追記**し、既存23件とbeforeを保持した。8資産のrevision・5依存digest、9資産のafter射影、必要な新snapshot、corpusを実ファイルから再生成し、改訂payloadの全after値と一致した。`frozen-inputs`の識別値・snapshotは不変。現在の変更はまだローカルで、共有DBや運用openへ適用していない。

反映時点で`origin/develop`は承認比較元`015dfa9d`から`ba339cf8`へ進んでいた。9資産と凍結外部検査器は同一だが、`.claude/core-areas.json`と`scripts/core_guard.py`には別PRのLoginScreen/router/App登録が追加された。受理記録のbeforeと比較元SHAは承認時の`015dfa9d`を維持する。新developを取り込むまでの関連pytestは**782件成功・core guard7件失敗**で、7件ともtenant-isolationの追加パス順が新しいdevelop基線と不一致である。これは7.7値や製品試験の失敗と分ける。最新develop統合後に共有パスの順序を保持して再検査し、統合差分を元の独立レビュー済み範囲と混同しない。

`origin/develop=ba339cf8`のmerge競合は`.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py`の3ファイルに限定された。U-F13のLoginScreen/router/App登録済み基線をそのまま保持し、`initial_grant.py`をsync-protocol・recording-rights・tenant-isolation各領域の末尾へ1パスずつ加えた。追加層の宣言はその1パスだけとし、U-F13登録とRG1旧層を消さない。双方の回帰試験を保持した解決でcore guard **266件成功**。この3ファイルの統合時差分は元の独立レビュー0/0/0の対象外であり、本人逐行確認へ含める。凍結9資産と外部検査器には統合差分がないので、改訂7.7のrevision・digest・snapshot・corpusは不変として実ファイルから再照合する。

### 2026-10-19: 改訂反映後の全件検査で見つかった追随先

承認済み`runtime-authz-contract` revision 18の実`source_digest=fa4bd7776c1e16bf4ddf5aa96601dc87e6788da7d52c636d56ed6bacc7c92b83`に対し、生成済み`backend/src/pitchlog/authz/runtime_contract.py`が旧revision 17・旧digestのままだった。既存generatorのrenderによる候補差分はこの定数2行だけで、認可条件やAPIは変わらない。対象の認可catalog試験は候補上で成功した。この生成差分は旧独立レビューの対象外であり、未コミット候補として識別する。

root全件検査は約42%・12,571件成功/2件skipの時点で2件失敗を検出し、`--maxfail=1`で停止したため**全件完走ではない**。1件は上記生成漏れで解消した。残る`test_checker_census_matches_declared_anchor`は`unadjudicated_removed_tb002_remains_in_current_census`が`initial_grant.py:397`等の承認済み限定所見を、広域のowner pathに含まれないという理由で拒否する。検査器本体はファイルSHA・行・シンボルの完全一致で47箇所だけ許すが、凍結対象のcensus試験はその限定条件をまだ解釈しない。対応案は既存の限定条件と完全一致する所見だけを減分検査から除き、他パス・他行・他シンボル・SHA不一致の拒否を負例で維持すること。`tests/test_census_baseline_check.py`はcensus凍結射影の外部ファイルなので、変更にはrevision 15→16、snapshot・corpus・#156単一未マージ記録after側の再導出、別の7.7実値受理が必要。広域owner追加や検査削除は行わない。現時点ではこの追加差分を編集せず、候補作成の人間判断待ちとする。元レビューP0/P1/P2=0/0/0はこの追随差分を含まない。

DB必須検査の環境診断では、最初の使い捨てPostgreSQLが`en_US.utf8`で起動し、凍結期待値`C.UTF-8`と不一致で149件成功後に停止した。localeを指定した別の使い捨てクラスタでは環境検査3件が成功したが、次のバックエンド全件試行はfrontend依存`typescript`未導入で152件成功後に停止した。`pnpm install --frozen-lockfile`後、該当DB試験4件は成功した。rootの別試行での`test_actual_measurement_is_generated_and_passes_both_budgets`失敗は、SQL変異の実PostgreSQL DSN未指定に起因し、専用使い捨てDBのDSNを渡した単独再試験は成功した。これらの診断・単独成功は全件成功と区別する。共有DB・共有/tmpは変更していない。

適切な隔離DBのDSNを付け、既知のcensus本体1件だけをdeselectしたroot再試行でも、`test_measured_suppression_accepts_develop_without_growth`が同じ`unadjudicated_removed_tb002_remains_in_current_census`のため失敗した。13,386件成功・2件skipの時点で停止し、全件完走ではない。必要な修正は個別テスト名の除外ではなく、共有述語の限定47箇所を正しく扱うこと。検査を弱めない負例と凍結改訂の別承認を維持する。

### 2026-10-19: 旧担当の停止確認・所有受諾と実HEADの再照合

- 作業開始時点の対象worktreeは`feature-ur1-initial-rights`、実HEAD`e2a9ce82`、未コミット差分0件、上流`origin/feature/ur1-initial-rights`に対して113先行・0遅れ。公開Draft PR #156のheadRefOidは`836232d6`、レビュー0件、Draftのまま。ローカル成果は未pushで、PR側の記録は古い。
- 旧Codex担当は、前節末尾の「現時点ではこの追加差分を編集せず、候補作成の人間判断待ちとする」で停止し、以後の成果をローカルコミットとして保全していた。停止・所有解除の独立文書はリポジトリ・Notionセッション検索・PRコメントには無い。本会話の引継ぎ指示を所有移管として受諾し、既存成果・旧資料・before・先行履歴を削除・改変しない。新5全体・実Port・実台帳の完成とは扱わない。
- 承認記録は[改訂payload](../features/ur1-recording-rights/step5-pr156-7.7-amendment-payload-proposal.json)と[改訂単一記録案](../features/ur1-recording-rights/step5-pr156-7.7-amendment-record-proposal.json)にあり、実ファイルSHA-256は指定の`8559617ed7714bc85a8dfa51f6bfad866aa43d40eaf39d266eeba4a2a90e96dd`・`550d5c78aa77597c52459514f017205580b23ab03c3026432519c41fb6d41025`と一致した。

### 2026-10-19: 改訂7.7の実ファイル照合（再反映なし）

- 反映前の`origin/develop`とPR head`836232d6`はbase-allowlist revision 33・履歴23件・`#156`0件。旧payload`34915e05…`・旧記録案`c13ef970…`は保持し、旧記録は正式履歴へ一度も入っていない。`git log --all -S 'masaki1025/pitchlog#156'`が示す追加は`629b2b11`だけである。
- 現HEADはrevision 34・履歴24件・`#156`1件。その1件は改訂記録案の`record`と`approved_by=山田正輝`・`approved_on=2026-10-19`を除いて完全一致し、履歴末尾にある。旧#156ドラフトに固有のbase snapshot`7c62db13…`は履歴に存在しない（`inventory_revision:15`自体は既存履歴のprevious識別子にも現れるため、単独の識別子にしない）。既存記録の削除・差替えは行っていない。
- 9資産の識別子、9資産のafter射影と`history-snapshots`、8外部snapshot、archive corpus`51264ae66762fc42e5e789ecf3e7c4067528e2869c36939394b91ed6af95bdf1`を実ファイルから再計算し、改訂payloadの全after値と一致した。`census-baseline` revision 15と`frozen-inputs` revision 4は不変。
- 反映は既存コミット`629b2b11`で完了しており、今回の作業では7.7履歴を再追記していない。改訂payload・記録案自体も変更していない。

### 2026-10-19: 最新develop（#158）統合とcore登録の回転

- `origin/develop=7c1afeba`（#158 TSK-550段階A起動入口のコア領域登録）を通常mergeで取り込み、`73f90cf8`。競合は`.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py`の3ファイルだけ。
- develop基線に登録済みの`stage_a_startup.py`は追加層から回転し、U-R1の`initial_grant.py`だけをsync-protocol・recording-rights・tenant-isolationの追加層に残した。tenant-isolationのJSON末尾は`stage_a_startup.py`→`initial_grant.py`の順で両方を保持し、game-stateはdevelopの登録をそのまま保持した。#158の登録試験は、回転後の実態に合わせて宣言試験1件を改名・追随し、合成登録試験3か所へ明示の追加層を渡した。他の試験は変更していない。
- `uv run pytest tests/test_core_guard.py -q`は269件成功、rootの`uv run ruff check .`と`uv run ty check`は成功。凍結9資産・外部検査器・corpusに統合差分は無く、改訂7.7のrevision・digest・snapshot・corpusは不変。
- この3ファイルの解決差分は既存の独立レビュー0/0/0の対象外であり、本人逐行確認へ送る。旧レビューをこの差分へ延長しない。

### 2026-10-19: TSK-372が引き取れる共有パスと条件

- #156が現在編集所有する共有パスは、`contracts/db/schema-manifest.json`（data-model v0.12のcanonical sha256）、`docs/features/orm-schema-migration/acceptance-sheets/`のN3・N7・README、`tests/test_orm_acceptance_sheets.py`の固定件数、`contracts/authz/shared-preconditions.json`（data-model blob）、`.claude/core-areas.json`・`scripts/core_guard.py`・`tests/test_core_guard.py`（`initial_grant.py`登録）、`backend/src/pitchlog/authz/runtime_contract.py`（revision 18生成定数）、`contracts/tenant_boundary/`の凍結9資産・snapshot・corpus。
- TSK-372が引き取れる範囲はmanifestとORM受理シート（N1/N3/N4/N7・README・固定件数）。条件は、#156が実developへ統合された後の実developを基線に再導出すること、PR head`836232d6`や本枝の未統合値を比較元にしないこと、data-model v0.12のcanonical sha256と#156の受理履歴・7.7値を保持すること、共有パスの単一編集者として並行編集しないこと、TSK-372側の正本版は#156統合後のdevelopから版番号を再導出すること、manifest/shared-preconditionsの新実値にはTSK-372側の7.7受理を取ること。
- #156が引き渡さない範囲は、`contracts/tenant_boundary/`の凍結9資産・単一#156履歴・検査器、`initial_grant.py`とその試験、`runtime_contract.py`の生成定数、core登録3ファイルのU-R1分。TSK-372はこれらを削除・上書きしない。この引取りは新5全体・実Port・実台帳・運用openの完了を意味しない。

### 2026-10-19: 全件検査の結果と新しい実値変更の一括判断送り

- root `uv run pytest tests/ -q`（既定の`-n auto`）は**29,669件成功・2件skip・10件失敗**（598.90秒）。失敗の内訳は、census基線8件とDB必須2件。
- census基線8件（`test_checker_census_matches_declared_anchor`、`test_measured_suppression_accepts_develop_without_growth`、`test_removed_tb002_accepts_prefix_related_current_symbol`、`test_independent_added_predicate_rejects_candidate_checker_omission`、`test_declaration_to_implementation_rejects_unused_field_and_recovers`、`test_implementation_to_declaration_rejects_undeclared_input_and_recovers`、`test_each_declared_census_predicate_rejects_its_input_mutation[added_equals...]`、同`[unadjudicated...]`）は同じ原因。参照側検査器が`initial_grant.py`の47箇所をTB002として検出し、現行検査器は`condition_2_scoped_findings`のSHA・パス・行・シンボル完全一致で除外するため、census差分の`removed`に47件が残り、同時に`added_equals_independently_derived_condition_2_candidates`では47件が`missing`になる。凍結census試験は`condition_2_scoped_findings`を解釈しない。負例試験の一部は、この既存不一致が先に発生して期待メッセージへ到達しない。
- DB必須2件（`test_actual_measurement_is_generated_and_passes_both_budgets`、`test_each_language_mutants_are_actually_killed[sql]`）は、設定済みDSNの`127.0.0.1:5432`にサーバーが無く`connection refused`。コード原因ではない。CIのDBサービスで再確認する。ローカルには`127.0.0.1:55432`の別クラスタがあるが、共有・他担当の実行と混同しないため、今回の判定に流用しない。
- 8件の修正は、`tests/test_census_baseline_check.py`（census凍結射影の外部ファイル）で`condition_2_scoped_findings`の完全一致所見を`removed`の判定から除外し、`added_equals_independently_derived_condition_2_candidates`の独立導出候補からも同じ所見を除外し、他パス・他行・他シンボル・SHA不一致を拒否する負例を維持する形。これはcensus-baseline revision 15→16、censusの新snapshot、#156単一記録の`new_baseline_identifiers`と`asset_snapshots`（censusとbase自身）、base-allowlistの新snapshot、corpusとmanifest digestの再導出を伴う。
- 上記は既存の#156記録の差替えになるため、本人確認・別7.7受理なしには適用しない。今回は修正せず、影響範囲だけを一括判断へ提示する。広域`owner_paths`追加・検査削除・個別テスト名の除外は行わない。
- backendの限定検査は`test_initial_recording_right_candidate.py`・`test_authz_runtime_contract_generator.py`・`test_authz_connection_guard.py`の114件成功。backend Ruff format/check・ty成功。frontendは本差分に変更が無いため個別実行せず、CIに委ねる。

### 2026-10-19: 未レビュー差分・本人確認対象・残ゲート

- 未レビュー差分: `73f90cf8`のcore3ファイル解決、`629b2b11`の改訂7.7反映（値は受理済み、差分の独立レビューなし）、`9aec9a72`の生成モジュール2ファイル追随、`14b0a4fa`の`runtime_contract.py`生成定数2行、data-model v0.12第2回P1反映、manifest/shared-preconditions/ORM N3・N7行（PO判定済み、独立コードレビューなし）。旧レビューP0/P1/P2=0/0/0をこれらへ延長しない。
- 本人逐行確認: core3ファイルの解決差分、`repository_contract.py`・`tenant_context_contract.py`の資産追随、data-model v0.12の承認範囲、ORM N3/N7新規2行。
- 未成立: census限定47箇所の凍結census試験対応と別7.7受理、U-G1/U-S1の項目別受理、実台帳・鍵・端末資格、P-6/実入口結合、最終HEAD CI。
- 未実施: 本人確認・署名の代記、Draft解除・マージ、共有DB適用、運用open。

### 2026-10-19: CI回収（HEAD 3519de0b → 2851b87d）と生成モジュールの追随

- `3519de0b` のCI（run 39270975096）は docs-lint・consistency・secrets・nfr021-append-only・tenant-boundary-bypass・frontend-changes・mutation・frontend が成功。harness は census の最初の未裁定removed所見（`unadjudicated_removed_tb002_remains_in_current_census`。ローカルpytestでは同原因8件）で失敗し、core-guard は本人逐行確認行の未記入、backend は生成モジュール2件の不整合で失敗した。
- backend の失敗は、改訂7.7で `contracts/tenant_boundary/repository-contract.json`（revision 22）と `contracts/tenant_boundary/tenant-context-allowlist.json`（revision 17）の資産値だけを更新し、`backend/src/pitchlog/repositories/repository_contract.py`（21）と `tenant_context_contract.py`（16）の `CONTRACT_REVISION`・`SOURCE_DIGEST` を追随させていなかったため。資産値は受理済みで、新しい実値変更ではない。生成モジュールを資産へ追随させ、対象2ファイル70件の試験とbackend Ruff/tyを成功させた。
- core-guard の失敗は `- [x] コア領域/検査経路の変更: 人間による逐行確認を実施した` の未記入であり、コード不一致ではない。本人確認の代記は行わない。
- 生成モジュール追随後の最終HEAD `2851b87d`（run 39276114028）で再回収した。backend は**3,059件成功・4件skip**、docs-lint・consistency・secrets・nfr021-append-only・tenant-boundary-bypass・mutation・frontend・frontend-changes・backend-changes は成功。harness と core-guard だけが上記の既知の残ゲートで失敗し、いずれもコード不一致ではない。
