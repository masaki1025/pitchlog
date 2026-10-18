# U-R1 新5: 隔離候補後の一括判断（2026-10-18）

**比較元**: `origin/develop=156dd139a893845428a1ecab69632143f7694e0b`。隔離候補のローカル保全コミットは`68c085852bb57c2f65e30e08a39cd49689bc1d19`。正式資産・7.7履歴・共有DBは変更していない。以下は**承認を求める候補の範囲**であり、実revision/digestやDDL適用の承認を先取りしない。TSK-550 Bの共有資産は同担当が編集中で、実値はその統合後の比較元から再導出する。

## 1. 今判断できるDDL・認可／凍結の範囲

### 既存契約との衝突と推奨する最小差分

現`recording_generations`は`pitchlog_app`へ**表単位**の`SELECT/INSERT/UPDATE`を付与している。前の[候補資産](step5-candidate-assets.md)のまま同表へ`v12_digest`と`recovery_generation`を追加すると、新列も直接SELECT/UPDATEの対象となる。これは暗号化再交付と最小権限の狙いに合わないため、**世代表の既存ACLを変更せず、V12 digest・暗号文・復旧世代を新規function_only表へまとめる案**を推奨する。世代との結合は複合FKで強制する。これは候補DDLの変更判断であり、既承認のV12再交付方針を変更しない。

候補business schemaの追加・変更を以下に固定して審査する。記載SQLは**資料上の候補**でありmigrationへ未入力。

```sql
ALTER TABLE public.rg1_restore_gate
  ADD COLUMN recovery_generation bigint
  CHECK (recovery_generation > 0);
-- 既存closed seedはNULLのまま。NULL/open不一致は書込み拒否。

CREATE TABLE public.recording_right_deliveries (
  tenant_id uuid NOT NULL,
  game_id uuid NOT NULL,
  generation bigint NOT NULL CHECK (generation > 0),
  start_request_id uuid NOT NULL,
  device_id uuid NOT NULL,
  recovery_generation bigint NOT NULL CHECK (recovery_generation > 0),
  proof_digest bytea NOT NULL CHECK (octet_length(proof_digest) = 32),
  key_id text NOT NULL CHECK (length(key_id) > 0),
  nonce bytea NOT NULL CHECK (octet_length(nonce) = 12),
  ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) = 48),
  revoked_at timestamptz,
  CONSTRAINT pk_recording_right_deliveries
    PRIMARY KEY (tenant_id, game_id, generation),
  CONSTRAINT uq_recording_right_deliveries_start
    UNIQUE (tenant_id, game_id, start_request_id),
  CONSTRAINT fk_recording_right_deliveries_generation
    FOREIGN KEY (tenant_id, game_id, generation)
    REFERENCES public.recording_generations (tenant_id, game_id, generation)
    MATCH FULL ON DELETE NO ACTION
);
ALTER TABLE public.recording_right_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recording_right_deliveries FORCE ROW LEVEL SECURITY;
```

既存`recording_generations.holder_device`は`text`である。候補の`device_id UUID`は同列へ小文字の標準UUID文字列として写し、再読時はUUIDへ厳密に戻して一致させる案とする。世代表の型変更は今回含めない。初回`issuance_order`の値は正本・担当合意待ちなのでDDLで仮決めしない。論理失効は`revoked_at`で表し、物理DELETE権限を作らない。

復元外の**別DB**に置く候補は、epoch行とD4 counter行を分離する。両DBをまたぐ外部FKは作らない。予約/claimはprimaryと同期standbyの双方への耐久記録後にのみ成功扱いとする。

```sql
CREATE TABLE recovery_epoch (
  singleton_id smallint PRIMARY KEY CHECK (singleton_id = 1),
  current_generation bigint NOT NULL CHECK (current_generation > 0)
);
CREATE TABLE d4_counter (
  singleton_id smallint PRIMARY KEY CHECK (singleton_id = 1),
  next_generation bigint NOT NULL CHECK (next_generation > 0)
);
CREATE TABLE d4_reservations (
  attempt_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  game_id uuid NOT NULL,
  start_request_id uuid NOT NULL,
  generation bigint NOT NULL UNIQUE CHECK (generation > 0),
  recovery_generation bigint NOT NULL CHECK (recovery_generation > 0),
  status text NOT NULL CHECK (status IN ('reserved', 'claimed')),
  committed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- claimの条件はattempt_id・所有tuple・status='reserved'の完全一致。
-- claimed→reserved、counterの減算、予約行のDELETEを許さない。
```

**認可の承認候補**: `recording_right_deliveries`は専用NOLOGIN/NOBYPASSRLS関数ownerだけに、テナント条件付き`SELECT/INSERT`を許し、`UPDATE`は後続の失効操作を個別承認するまで与えない。app/PUBLICに表DMLを与えず、FORCE RLSを保つ。世代表の既存app権限は**増やさない**。初期付与の専用関数ownerには、世代表の必要列の`SELECT/INSERT`とテナント条件付き専用policyを追加する。RG1 ownerには新列の`SELECT`のみを追加し、open/復元開始や表全体UPDATEは含めない。appへはテナントをscopeから注入する固定関数だけの`EXECUTE`を付与し、PUBLIC既定EXECUTEを剥奪する。端末資格表の書込ownerは認証担当の回答待ちで、今回U-R1が決めない。

**凍結資産の承認候補範囲**: `contracts/authz/product/ddl-elements.json`とその表・policy・関数body、`table-classification.json`（新表は`function_only`）、`contracts/db/schema-manifest.json`、`contracts/tenant_boundary/repository-contract.json`の固定operation/token/capability、`runtime-authz-contract.json`の保護対象、必要な`base-allowlist.json`の新シンボル**のみ**。各派生lock・oracle・archive・7.7の単一未マージ受理記録は実入力から追随する。現比較元はrepository revision 21、base-allowlist revision 33、runtime revision 17だが、**これをafter revisionとして予約しない**。固定関数実行器は入力`UUID/int/str/bool`のみ許すため、暗号材は関数引数・戻りを安全な文字列表現へ変換しDB側で長さ・復号・tenantを再検証する必要がある。任意SQL/Session/汎用bytes bindの公開や既存許可の拡大は承認候補に入れない。

**拒否条件**: app/PUBLICから新表を直接DMLできる、越境・不明tenantで行の内容/存在が漏れる、V12原文・鍵がDB/ログへ残る、別要求/別tenantのattemptで同D4を使える、claim後に同D4を再投入できる、復旧世代の不一致/不明でも書込む、既存appの世代表権限が新しい秘密列へ届く、FORCE RLSが外れる、余剰policy・DELETE・表全体UPDATEが増える、のいずれかがあれば不受理。

この表の正確なowner名・固定関数identity/本文、端末表の配置、migration番号、実JSON、7.7前後値は**まだ確定不可**。従って今回の判断単位は上記の**DDL形・権限上限・拒否条件**までとし、正式資産承認は担当所有と共有資産基線の確定後に別に提示する。

## 2. 鍵・端末資格の管理

| 責任 | 推奨方式 | 未指定の担当・判断 |
| --- | --- | --- |
| V12の生成・暗号化・復号・同要求再交付 | U-R1が256-bit乱数とAES-256-GCMを使用。AADにtenant/試合/開始要求/端末/D4/復旧世代を含め、世代表の現権利と資格をロック下で再照合。アプリはcommit成功後にのみV12を返す | 鍵管理サービス/場所、鍵の作成・ローテーション・旧鍵保持/廃止・事故時対応の運用責任者は未指定。既存秘密を読み取らない |
| 端末資格の発行・認証への束縛・失効 | 認証担当がtenant認証と端末資格を同時照合し、資格のdigestだけをfunction_only表へ保存。U-R1は内部直接呼出しでも同一scopeの有効資格をDBで再照合 | TSK-506/認証担当の所有範囲、資格の配布・端末内保管、紛失/変更/失効手順、表ownerは未受理。裸のdevice_idは受理しない |
| HTTP・同期への伝達 | U-G1が開始応答をcommit後の同端末へ、TSK-506が同期入口の検証済み端末文脈をU-S1へ渡す | 公開DTO/失敗写像、Port署名/呼出位置は各担当回答待ち |

鍵保管先や運用者を仮置きせず、鍵が読めないときは再交付を閉鎖する。端末資格を複製できる環境への追加耐性を要求するかは別の仕様判断とし、今回の自己申告拒否の合格証拠へ混ぜない。

## 3. D4実配置と、配置前に進める範囲

| 案 | 必要資源・運用責任 | 費用/日程の判断材料 |
| --- | --- | --- |
| 既存資源転用を先に調査 | 業務DBと独立した復元/障害領域に既存primary・別故障領域の同期standby、同期WAL耐久、旧primaryフェンス、監視・昇格権限・復旧演習。運用責任者の記名が必要 | 新規計算機費を回避できる可能性はあるが、容量/通信/監視/当番工数は残る。該当2資源・単価・担当・開始日は未提示で金額/暦日は未算定 |
| 新規2資源 | 上と同じ安全条件を満たす2配置先・永続ストレージ・同期接続・監視・資格情報。購入/配備は別許可 | 提供者・region・サイズ・保全/通信/運用単価と構築担当・演習窓の提示後に見積可能。現時点で費用と完了日は算定できない |

**配置前に進める作業**: 使い捨てPostgreSQLで予約→同一owner再照会→一度限りclaim、別owner/二重claim拒否、epoch共有ロックとcounter別行の競合、応答消失/rollback、端末失効・鍵欠損・越境の負例、DDL/ACLの拒否系と正本7.6照合。実台帳adapter、同期standby喪失、旧primaryフェンス、バックアップ復元後の非再利用は実構成での証明を残す。実台帳に接続していない候補試験を耐久性・本物の`RecordingRightsPort`の合格と数えない。

## U-G1/U-S1へ残す接続差分

| 項目 | 現候補と既存入口との差 | 必要な担当回答 |
| --- | --- | --- |
| U-G1開始の署名/結果 | 旧案`issue_initial_recording_right(scope, game_id, holder_device: str)`に対し隔離候補は`tenant_id, game_id, device_id: UUID, device_credential, start_request_id, reservation_attempt_id, source, fence, box`を要求し、戻りは`game_id,D4,recovery_generation,holder_device_id,V12`。既存scopeは固定tokenの`run/run_function`だけで候補Protocolを実装しない | U-G1が渡す検証済み端末値と要求ID、attempt IDの耐久記録位置、外部fenceをcommit後まで保持する所有、初回`issuance_order`、HTTP再交付/失敗写像、結果へV12を出す時点 |
| U-S1同期Port | 現`holds_recording_right(game_id,d4,v12,writer)`に端末値がなく、復旧世代の外部fenceもない。RG1の③-a/⑧の既受理は維持 | 検証済み端末・復旧世代をPortへ渡す署名/呼出位置、B4/B9/B10とD5未消費の写像、終了後P3のV12例外、全書込経路の外部fence保持 |
| 全ロック順 | 候補は**外部epoch共有→D4予約/claim（別行・業務行ロック前）→試合行→チーム/選手/U-M2→世代/配達→RG1共有→業務commit→外部epoch解放**。復元開始の最初の取引はRG1行だけを閉じて確定後に外部epoch排他更新 | U-G1/U-S1が試合/チーム/選手/記憶/世代/配達の全順、二重開始、外部2DBの待ちと取消境界を項目別に受理する。既受理の試合行→世代行を再審査しない |

U-G1/U-S1の無回答を合意に置換しない。U-M2は既存のチーム→選手UUID順を維持する。新5の本物のoperationと新8のPort全体はそれぞれの担当・後続ゲートに残す。
