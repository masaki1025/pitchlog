# U-R1新4: data-model v0.11最終承認・認可境界の判断資料（2026-10-16）

## 判断の対象と固定値

- 承認前の正本候補は`docs/design/data-model.md` v0.11、`status: in-review`、候補HEADは`78c649150b085074476cbfe85f963dd96ec5a335`、本文SHA-256は`fe8251678c9f29c9d03d1a5239d5780204b77995a31d2f3a0ead65c67954f759`。直前approvedを収録するコミット`239d391d`からの本文差分SHA-256は`945062b09036ca3b2132e2269792a564b787dfa9167df24c889958460e447ad0`。最終の`反映2周目`本文差分SHA-256は`ed9d04b769f3f9bcc49fa06027eae54800d83a6515f4df13bd09d0a3114e9b98`。これらはレビュー対象の識別値で、承認記録だけを追記した後の本文SHAとは区別する。
- 本文は§3-2のロール表・RG1物理資源段落、共通関数所有者契約のRG1への適用、旧ロール数4参照、v0.11変更履歴で構成する。**2026-10-16の本会話でPOが最終候補と未再レビュー残余を確認し、この改訂範囲を明示承認した**。正本・索引は`approved`へ確定する。氏名は本承認メッセージにないので推定しない。
- 共有資産の順序は**C1／PR #144を正式受理・統合→U-R1／PR #143が実developを基線に再導出**でPO固定。C1担当Codex Dが[#143のコメント](https://github.com/masaki1025/pitchlog/pull/143#issuecomment-6209084415)で受領・阻害差分なしと回答し、C1の`docs/worklog/2026-10-14-uf13-team-route-acceptance.md`に記録した。C1の正式7.7受理・統合は未完了。

## 正本本文の確定候補

§3-2の候補は、RG1全体共通の`singleton_id=1`単一状態行を`closed`で初期化し、専用`pitchlog_rg1_fn_owner`を`NOLOGIN/NOBYPASSRLS`かつ**誰にもGRANTしない**ロールとして定める。ownerは`SELECT(singleton_id,state)`と行ロック用`UPDATE(singleton_id)`だけを持ち、RG1表に`FORCE RLS`と同owner向けID=1のSELECT/UPDATE policyを置く。RG1だけを非テナント`function_only`のpolicy例外とし、アプリの表直接権限は与えない。

アプリは`rg1_api`のUSAGEと、`SECURITY DEFINER`固定読取2関数`rg1_read_open(uuid)`・`rg1_assert_open_before_commit(uuid)`のEXECUTEだけを持つ。PUBLICのEXECUTEは剥奪し、関数は固定`search_path`と修飾名を使う。UUID引数は検証済みscopeから注入し、DBの`app.tenant_id`一致は文脈整合の確認であり**認可証明ではない**。コミット直前の再照合は`FOR SHARE NOWAIT`、競合・欠損・不明・読取失敗はfail-closedとする。新4の製品関数はopen行でも常閉を返し、復元開始・運用openは後続ゲートに残す。

既存の共有・管理・認証の3関数ownerだけが`BYPASSRLS`を持つ。RG1 ownerは`NOBYPASSRLS`で、非付与・関数ACL・名前解決の共通検査を受ける。製品ロール数は6、期間限定の移行バッチ用を含む総数は7。D4発行、運用open、U-S1/U-G1実経路結合は本改訂の射程外。

## 7.3レビューと採否

| 周 | 対象と判定 | 採否・反映 |
| --- | --- | --- |
| 第1回 | `b34c350a`の正本全文。否決 P0=0/P1=5/P2=0 | 全5件採用。`function_only`例外、ownerの非付与と`SECURITY DEFINER`/固定`search_path`、GUCの非認証性、ロール数、列権限の誤記を`01ec08aa`（`反映1周目`）で修正。不採用0、(B)送り0 |
| 第2回 | `01ec08aa`の反映差分と影響節。否決 P0=0/P1=2/P2=0 | 全2件採用。既存3 ownerとRG1 ownerの属性検査を分離し、旧ロール数4参照を`78c64915`（`反映2周目`）で修正。不採用0、(B)送り0 |

2回の基本枠を終了した。7.3-8により**最終反映差分は未再レビュー**だったが、POはその残余を確認して正本v0.11の今回の改訂範囲を承認した。採否の項目別典拠は`docs/worklog/2026-10-15-ur1-recording-rights.md`末尾に固定した。第1回・第2回とも正本確定ゲートの様式を満たし、P0は0件だった。

## 新4候補の認可差分と限界

| 対象 | 最小追加 | 拡大しない境界 |
| --- | --- | --- |
| ロール・schema | `pitchlog_rg1_fn_owner`を`NOLOGIN/NOBYPASSRLS/NOINHERIT`で追加。`rg1_api`はappにUSAGEのみ | ownerを他ロールへGRANTしない。app/PUBLICにschema CREATEを付与しない |
| 表・RLS | `public.rg1_restore_gate`単一行、ENABLE/FORCE RLS、ownerだけのSELECT/UPDATE policy。`USING`とUPDATEの`WITH CHECK`は`singleton_id=1` | appへの表SELECT/INSERT/UPDATE/DELETEなし。INSERT/DELETE policy、余剰policy、表単位UPDATEなし |
| 列ACL | ownerに`SELECT(singleton_id,state)`と`UPDATE(singleton_id)`のみ | `UPDATE(state)`、他表・他列・他owner・他関数のUPDATEを許さない。unapplyで両列ACLを剥奪 |
| 関数ACL | `(uuid)`読取2関数だけにapp EXECUTE。作成と同一transactionでPUBLIC EXECUTEを剥奪 | 復元開始関数、任意SQL、任意tenant引数、運用openを加えない。DBのGUC一致を認証根拠にしない |
| seed | migration 0032の`(singleton_id=1,state='closed')`完全一致1行 | 他ID・open・不明状態・追加行・既存行上書きを拒否。既存seed系列は維持 |

認可資産所有側TSK-424へは、実効権限と既存policy合成、2関数のEXECUTEとPUBLIC剥奪、正本§3-2の修正点・7.3担当に絞り、Notionコメント`3fb93b75-e687-81d1-9522-001dfdd41c49`で回答を求めた。**項目別回答はまだ確認できない**。回答不能の場合に必要な代替判断は、POが上表のexact境界と専用使い捨てクラスタの適用/取り外し試験・独立コードレビューP0/P1/P2=0を根拠に、TSK-424担当回答を代替してこの認可候補を個別受理するかどうかである。無回答を受理と扱わず、PO判断を正本承認や7.7正式受理と混同しない。

**後続の別裁定**: 同日、POは[代替受理判断資料](rg1-authz-alternative-acceptance.md)のexact差分に限り、RG1新4のTSK-424項目別回答に代わる受理を明示承認した。上段の「代替判断が必要」はその裁定前の状態として残す。7.7実値の正式受理・本人逐行確認は引き続き別ゲート。

## 検査と後続ゲート

- 公開中のDraft PR #143準備HEADは`cd03ddcb`。そのCIはharness・mutation・tenant-boundary-bypass等が成功し、core guardだけが本人逐行確認欄未チェックで失敗。backend/frontendは未push新4候補を含まないためskipping。
- ローカル未push新4候補は、専用使い捨てクラスタで製品認可の適用・取り外し・migration往復・再適用3件が成功。既報のRG1/認可/migration関連266件、repository/capability200件等の対象検査成功を維持。正本最終反映後の`check_authz_catalog.py`は1414件相当の照合で成功、`check_docs_status.py`は20文書・違反0、docs status試験は専用`--basetemp`で72件成功。最初の通常tmp実行は`/tmp`容量不足（8 KiBしか空きなし）で失敗し、別のローカルtmp領域で再実行した。未受理履歴/seedによる全件検査の赤と、root認可変異全数未完はそのまま残る。
- C1統合まではA直後の暫定7.7値を正式値へ昇格しない。#144が正式受理・統合されたら実統合SHAを含む最新`origin/develop`をmergeし、受理済み履歴を保持して3凍結資産のrevision/digest、全snapshot、RG1 seedの記録案、archiveを再導出し、最終検査と正式7.7受理資料を別提示する。
- **data-model v0.11最終本文の承認は完了**。TSK-424回答不能時のRG1新4 exact認可差分は、後続の別PO裁定で限定代替受理済み。7.7正式受理、本人逐行確認、Draft解除、マージは別ゲート。D4方式・運用open・新8実経路結合も別ゲート。
