# RG1新4: 認可所有側3項目の代替受理判断資料（2026-10-16）

`data-model.md` v0.11の§3-2限定改訂はPOが最終反映`78c64915`の未再レビュー残余を確認して承認し、`dc969d3e`で`approved`に確定済み。この正本承認自体はTSK-424認可所有側の項目別受理、候補DDL/JSON、7.7正式受理を含まない。TSK-424への照会（Notionコメント`3fb93b75-e687-81d1-9522-001dfdd41c49`）には項目別回答がない。下表の「推奨」は当初のPO判断材料として残す。

**2026-10-16の別裁定**: 本会話のプロダクトオーナーは、下表のexact差分に限り、今回のRG1新4についてTSK-424の項目別回答に代わるPO受理を明示承認した。下表の「推奨」は承認前の判断材料として残す。承認範囲は専用NOLOGIN/NOBYPASSRLS owner、対象1表・単一行のFORCE RLS、owner向けSELECT/UPDATE policy各1件、`SELECT(singleton_id,state)`と`UPDATE(singleton_id)`、appの固定読取2関数EXECUTEとPUBLIC既定EXECUTE剥奪、承認済み§3-2との一致。余剰policy・表全体の権限・復元開始・運用openは対象外。承認者の氏名は今回のメッセージにないため推定しない。本裁定は具体資産の他の範囲、7.7実値の正式受理、本人逐行確認を代替しない。

| 未回答項目 | 代替受理する場合の具体差分 | 根拠・推奨判断 |
| --- | --- | --- |
| 1. 専用owner・RLS・列ACLと既存policy合成 | `pitchlog_rg1_fn_owner`を`NOLOGIN/NOBYPASSRLS/NOINHERIT`で追加し、他roleへGRANTしない。`public.rg1_restore_gate`は`singleton_id=1`の1行、`ENABLE/FORCE RLS`。ownerだけを対象とするSELECTとUPDATEの2 policyを`USING singleton_id=1`、UPDATEは`WITH CHECK singleton_id=1`で追加。列ACLはownerの`SELECT(singleton_id,state)`と`UPDATE(singleton_id)`だけ。表単位権限、appの表権限、他policy、INSERT/DELETE policyは追加しない。適用・取り外し器とcatalog検査はこのexact集合と既存policyとの合成を確認する | 承認済み§3-2と新4の常閉限定契約に一致。候補の専用使い捨てクラスタでは全資産適用・取り外し・migration往復・再適用3件、適用器単体49件が成功し、取り外し時の残存UPDATEを修正済み。**推奨: exact集合に限ってPOが所有側の代替受理を裁定する**。最終候補で既存policy合成や余剰ACLが出れば差分再提示し、裁定対象へ含めない |
| 2. app/PUBLICの関数権限 | `rg1_api`はappに`USAGE`のみ、`CREATE`なし。`SECURITY DEFINER`・固定`search_path=pg_catalog,pg_temp`の`rg1_read_open(uuid)`と`rg1_assert_open_before_commit(uuid)`だけにapp `EXECUTE`を付与。両関数を作成する同じtransactionで`PUBLIC`の既定EXECUTEを剥奪。復元開始関数、運用open、任意SQL、呼出側指定tenantは含めない。引数UUIDは検証済みscope注入、DB側でも`app.tenant_id`一致を確認するがGUCを認証証明と扱わない。製品関数はopen行でもfalseを返す | 旧`authz_private`配置はappがUSAGEを持てず不成立、既存owner再利用は権限過大。独立コードレビューの最終候補はP0/P1/P2=0、固定関数・常閉・直接EXECUTE/ACL負例を対象とした。**推奨: 2関数exact集合だけを代替受理**。直接EXECUTEや例外経路の拡張が見つかれば止め、別審査にする |
| 3. 正本§3-2との一致と確定ゲート担当 | RG1の非テナント`function_only`特例を**この1表だけ**に限定し、製品ロール6・総数7、既存3 ownerの`BYPASSRLS`とRG1 ownerの`NOBYPASSRLS`を別に検査する。候補の`table-classification.json`・`exposure-facts.json`・role/ACL/catalog検査だけを§3-2の確定本文へ照合し、他候補改訂を同梱しない | §3-2の7.3敵対レビューは全文・反映差分の2回でP0=0、P1計7件を全採用。最終反映未再レビューを明示した人間承認も完了し、正本側の7.3担当判断は不要。**推奨: 認可資産への正本写像だけを代替確認**し、正本の再承認や追加版改訂へ戻さない。実候補が承認済み条文から逸脱した場合は新たな正本/資産ゲートを提示する |

**代替受理の範囲**: 上表は認可所有側の無回答3項目だけ。POの別裁定をこの範囲に記録し、最終候補のSQL/JSON完全差分、専用クラスタでの実効ACL・policy合成と負例、独立レビューの識別値を照合する。ローカル候補の既報は[新4候補資料](step4-a-integrated-acceptance-candidate.md)の結果であり、PR最終HEADの全検査成功ではない。`/tmp`容量不足を避けた検査の記録と未受理履歴による赤も同資料に残す。

**7.7とは別**: 2026-10-16時点でC1/#144はDraft・未統合。U-R1/#143の3凍結資産とseed系列のbefore/after・snapshotはC1の受理済み統合HEADを取り込んでから再導出する。現資料のA直後の値を承認値に流用せず、PR最終HEAD、履歴・archive、残る全数検査、必要レビューを一括提示して7.7正式受理を別に求める。本人逐行確認・Draft解除・マージも別ゲート。
