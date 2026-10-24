# 開始経路の限定照合（2026-10-24）

## 固定点と調査範囲

実baseは`origin/develop=4b2db6907f329c3dde113c3b7e1c3515600fb915`（PR181通常merge）。主repoの作業HEADは旧developの`1ab398cc`であり、これを最新製品と誤認せず、実baseのGit blobを参照した。正常180 supplier`95d766f5d20234b1d534538b96fc369eda1cc6f1`は実baseの祖先である。旧173/0aaa/f48を輸入しない。

U-G1は別wt固定`67dff5f707dcb2311a35140ae870b44f46e24803`、U-F8入口は別wt`eb83787ca5f9e79f94bc773f99e62d74121778cf`と実baseへ統合された外殻を照合。実画面作成の隔離供給はfirst-path候補の固定点`d2713e9ec377fe7f4e882c7be01d9f42005aefa8`と後発CSV supportだけで、正常mainへ統合されたとはしない。最新台帳/RG1/作成を本branchへ一括mergeしない。

全過去レビュー/監査を読み直さず、UG1の開始側契約・UM2呼出し・UR1単一部品・UF8入口と実baseの該当sourceだけを確認。製品/共有metadata/他作者source/DB/Git履歴の変更なし。P6/封印/.env/運用秘密へアクセスしない。

## 実供給と不足

| 項目 | 現物・場所 | 判定 |
| --- | --- | --- |
| 開始の意味と親承認 | 固定67dffの`docs/features/ug1-game-lifecycle/plan.md` §2/4 step3、同design §初期化と成功境界 | 8ステップ/2026-10-14承認/基本計画2周を保持。両側スタメン・UM2・初期権・started_at/in_progressは単一transaction、commit後のみ成功。開始側の物理/側DDL/全lock順は未受理のまま |
| 開始公開operation/endpoint | 実base`backend/src/pitchlog/api/routers/games.py:47,73`、`api/schemas/games.py:64` | preparing list/detailだけ。開始service/DTO/POST startは存在しない。first-pathの追加POSTはpreparing作成であり開始ではない |
| 初期付与単一部品 | 実base`recording_rights/initial_grant.py:48,62,84,104,116,290` | InitialGrantRecord/InitialGrant、DurableGenerationSource、RecoveryEpochFence、InitialGrantScope、issue_initial_recording_rightが供給済み。InitialGrantScope実classは0、試験内fake scopeの成功を実接合としない |
| 実耐久源とRG1候補 | `c07f508df6bdcec815e311e5a81c25feeba08610`、RG1候補`5ee75156adabdb7a43fbd1393c5b62337e6e770a` | root所有の別候補。実Unix peer/同期PG/witness/fenceは再利用でき、reserve/claimはfresh保持中にも実測済み。fresh/全復元完成を同義にせず、今回編集しない |
| 端末資格/再交付/業務epoch | 実base`db/recording_rights/models.py:187`と全db/migrationの該当識別子検索 | RecordingGenerationはD4/issuance_order/holder_device/D3等だけ。device credential、start_request、proof_digest/暗号配達、business recovery epochの保存先/API/実adapterは存在しない |
| スタメン側 | 実base`db/game_state/models.py:223`以下GameLineup | game_id/team_record_id/entries JSONのみ。side/側ごとのuniqueがなく同一team両側を識別できない。親designは側列/uniqueを7.3対象として既に留保している |
| 名簿/記憶 | 実base`repositories/lineup_memory.py:230,282`と`api/schemas/lineup_memory.py:8` | save_lineup_memoryは同一scope、self team→active players UUID順。player/order/positionを保存、当時背番号はUG1所有。fielding_positionはJsonValueであり、そのまま意味確定済みとはしない。対戦相手/紅白戦/9-DH10の全検証はUG1へ残る |
| 実RecordingRightsPort | 実base`sync/ports.py:65,134` | Protocolと空PORT_IMPLEMENTATIONSだけ。実V12照合class/登録は0。別候補`7c04c964`にはPortWriter.run_function/VerifiedDeviceContext等の契約があるが実Port classなし、正常mainへ未供給で丸ごとmergeしない |
| UI/client | 実base`frontend/src/screens/GameScreenEntryTypes.ts:40`、`GameScreenEntry.vue`、`GameScreenEntryProvider.ts` | StartCandidateはprops外殻、実providerはpreparing read。実start client/trigger/初期名簿formはない。未取得lineup/権利/状態をready/heldへ偽装しない |

## T1を待たずに作る順序と具体的な次patch

今回の1stepは[plan](plan.md)の開始要求transportのみ。名前/背番号/tenant/予約attempt/権利をbodyで受理しない。fielding_positionの既存JsonValue表現を保持しても、DTO通過を確定スタメンと認めず、後段の単一検証なしには開始を接続しない。開始の最初の製品小単位をT1状態計算の完成待ちにはしない。

次の実DBadapter単位は、以下の必要集合をrootが確定・個別所有委任してから実装する。これは未提供リストだけではなく、同一scopeで実装するための物理候補であり、現時点の正式値/既受理契約ではない。

1. **業務物理候補**: `db/recording_rights/models.py`＋新migrationに、tenant/deviceを主キーとする資格digest/失効時刻、tenant/game/start_request/device/current D4/epoch/proof digest/ProofEnvelope(key_id/nonce/ciphertext)の束縛と一意配達、外部epochとの同一値照合先を持たせる。`RecordingGeneration`のD4/issuance_order/holder/D3=0と現世代一意は維持する。端末資格の発行/失効・保護鍵供給・attemptの予約前耐久記録は閉じた実入口が必要で、任意UUID/JSONやチームCookieだけを保持端末証明へ読み替えない。V12Boxを再利用し暗号/発行アルゴリズムをコピーしない。
2. **実scope候補**: 新`repositories/initial_recording_right.py`にexact生存`_TenantTransaction`を包むInitialGrantScope実adapterと固定operationを置く。資格の同一tenant共有lock、同一要求の現権利/配達照合、preparing game FOR UPDATE、現世代→配達の固定順、業務epoch一致、2行insert、既存RG1事前/直前を閉じたtokenだけで実行する。Session/任意SQL/tenant argumentの公開はしない。外部fence→資格→game→世代→配達→RG1をcommitまで保持し、再交付も失効/現権利を実再照合する。UM2を含むチーム/選手の全順は次項と一緒に確定してからstart serviceへ接続する。
3. **開始本体候補**: `db/game_state/models.py`＋新migrationのside/`(tenant_id,game_id,side)`unique、新`repositories/game_start.py`、新`services/game_start.py`。同一scopeで両チーム/現役playersを決定順lock→当時背番号取得→保存snapshotのdhを使う単一の9/10・位置/重複検証→両側lineup保存→UM2（紅白戦は後攻1回）→単一初期権部品→status/started_at→RG1/epoch直前→commit→成功。実際のlock順はinitial部品内部の資格→game順とUM2のteam→player順を合わせて固定し、既存syncのgame→世代順を逆転しない。まだ採用されていない守備値集合やD2初期投影を独断で補完しない。
4. **実Port候補**: 新`recording_rights/port.py`＋既存`sync/ports.py`/`port_guard.py`のexact class登録、既存accepted候補のPortWriter.run_functionを必要差分だけ供給。V12 digest/現D4/現epoch/実deviceを同じwriterのreadで照合し、read_rg1/check_rg1を既存固定2関数へ委譲。外部leaseは業務commitまで保持し、偽/派生/失効writer、旧epoch、別device、revoked、原本欠損を拒否する。開始には初期付与scopeが必要で、同期全Port/T1の完成を開始DTO/adapterの一律前提にはしない。
5. **HTTP/UI候補**: 既存games routerへ`POST /games/{game_id}/start`、tenant_accessのexact operation/C2登録、正規`frontend/src/api/games.ts`と新`GameScreenStarting*.vue/Provider.ts`を接続。新ルート不要で既存record hostから名簿/要求を供給、実commit後だけ開始receiptを採用。正規Pinia/QueryClient/epoch/path/abort/Cookie失効を再利用し、未知計算状態で1球ボタンを開かない。既存read DTOはpreparing専用なのでin_progress再取得を別の閉DTOへ分け、既存readを全状態対応済みにしない。

必要な共有変更はrootへ所有を戻す。具体集合はcoreの新source/test exact登録、`contracts/authz/product/{table-classification,capability-catalog,ddl-elements,exposure-facts,application-steps}.json`の新物理subject/列権限、route-registry/http-route-matrixのstart1件、tenant_boundary base-allowlist/repository-contractと生成物、必要9/8/履歴/snapshot/policyである。無制限contracts編集を許可せず、個々の実sourceからexact行を列挙してから候補化する。新表のRLS/FORCE/ACLと資格/暗号列のアプリ直接読取拒否は実負例を要する。正式7.3/7.7の受理はrootの別ゲート。

実DB検証は正常start後のD3=0/権利/両側名簿/UM2/時刻の全確定と、scope例外の全取消、同一要求再交付、別device/越境/失効、RG1両競合、外部reserve/claim不明・消費後business rollback非再利用、旧epoch/fence喪失を含む。製品の実作成→開始operationを通し、試合/権利の手製INSERTを開始成立証拠に数えない。実HTTP/画面では実login/Cookie/C2から通し、保存snapshotを再resolver計算しない。T1計算/1球はその実source供給後の別検証。

## 見込み・未実施

調査はread-onlyでDB0。新wtは実baseから作成、編集はplan/researchだけ。最初のtransport1stepは楽観30〜45分/通常1〜2時間。実scope/物理接合は契約固定後に3〜4/6〜10時間程度、HTTP/UI/browserは別単位。全開始をT1完成待ちへ戻さず、物理未受理を既採用として隠さない。旧親/UR1正常置換/台帳/UF8各レビュー系列と未完DoDは維持する。

起案検査はdocs-status21文書/違反0、design-propagation/doc-coverage成功、新2文書の全ローカルリンク実在、diff check成功。製品/DB試験は起案範囲外なので未実行。新2文書を固定した後に局所plan-syncを実baseと比較し、独立限定レビュー/PO委任前は製品編集を停止する。
