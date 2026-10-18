# 新5接続契約の固定候補（2026-10-18、担当受理待ち）

比較元は `origin/develop=156dd139a893845428a1ecab69632143f7694e0b`、候補コードは `081b52a0b14bcb5b6ea69ed751aed5287c729490`。本書は U-G1 と U-S1 が項目別に受理するための候補であり、製品Portの登録や外部台帳の耐久性を証明しない。RG1 新4の受理済み契約と、試合行→記録権世代行の既受理ロック順は維持する。

## U-G1: 開始と同一scopeの付与

U-G1所有の開始処理は、認証境界から渡された `VerifiedDeviceContext(tenant_id: UUID, device_id: UUID, credential: str)`、サーバー側で永続化した `start_request_id: UUID` と `reservation_attempt_id: UUID` を受ける候補とする。自己申告の端末IDだけでは呼べない。`tenant_transaction_scope` 内で以下の U-R1 operation を一度呼び、開始状態・スタメンとともに**業務DBを一括確定**する。`scope` は同じ業務DB transactionに束縛される。

```python
issue_initial_recording_right(
    scope: InitialGrantScope, *, tenant_id: UUID, game_id: UUID,
    device_id: UUID, device_credential: str, start_request_id: UUID,
    reservation_attempt_id: UUID, source: DurableGenerationSource,
    fence: RecoveryEpochFence, box: V12Box,
) -> InitialGrant

InitialGrant(game_id: UUID, generation: int, recovery_generation: str,
             holder_device_id: UUID, recording_right_proof: str)
```

`InitialGrant` は**commit成功後だけ**同じ認証済み端末へ返す。現在の候補は `device_credential` をscopeで再照合し、試合行と現権利をロック後に再照合する。公開HTTP DTOと失敗のHTTP写像は U-G1/TSK-506 の所有で未受理。`issuance_order` の初期値も U-G1/U-R1 の受理待ちで、仮値を置かない。

| 内部結果 | 意味・必須処理 | 公開写像 |
| --- | --- | --- |
| `InitialGrant` | 現権利と同一要求・同一端末の再交付、または新規付与。commit成功の証拠ではない | commit後にだけ成功応答。U-G1受理待ち |
| `InitialGrantUnavailable` | RG1閉鎖/競合/欠損、外部epoch・鍵・資格の不明/不一致、予約/claim結果不明。業務DBを全取消。新たな発行を推測しない | U-G1受理待ち。B7/B10の区別は呼出位置に従う |
| `InitialGrantConflict` | 同一要求の端末・現権利・台帳予約owner不一致。全取消・再交付しない | U-G1受理待ち |
| 業務DB commit結果不明 | HTTP成功を返さず、同じ認証済み端末・`start_request_id`で保存済み結果を照会する。存在と現権利を証明できなければ新attemptで再発行しない | U-G1受理待ち |

## U-S1: 本物のPortへ渡す候補

現 `RecordingRightsPort.is_recovery_generation_current(game_id, supplied, writer)` と `holds_recording_right(game_id, d4, v12, writer)` には検証済み端末文脈がない。変更候補は `verified_device: VerifiedDeviceContext` を両方へ加え、同じ `PortWriter` 内で U-R1 の固定operationが **(tenant, game, device, D4, V12 digest, 復旧世代)** を再照合する形とする。`verified_device` の発行とPortへの渡し位置は TSK-506/U-S1 の受理待ち。`PortWriter` に任意SQL、Session、テナント入力を足さない。P3終了後は正本どおりV12照合を省くが、復旧世代とRG1の直前ゲートは省かない。

| U-S1分岐 | 候補結果と責任境界 |
| --- | --- |
| ③-a でRG1停止 | U-R1は既存の非ロック読取を提供。U-S1はD5を消費せず、P1/P2/P4はB7、P3はB10へ写像 |
| V12/D4/端末/復旧世代不一致 | U-R1 Portが偽・不明をfail-closedで返す。U-S1が既定のB4/B9/B10へ写像し、D5と適用範囲を管理する。経路別写像は担当受理待ち |
| ⑧ のRG1停止・外部epoch不一致 | U-R1がFOR SHARE NOWAITと外部epoch共有fenceで拒否。U-S1がscope全体を取消し、D5を未消費にする。P1/P2/P4はB7、P3はB10 |
| 応答消失後の再送 | U-S1のD5台帳で保存済み結果を再掲。U-R1は再送のために新D4/V12を発行しない |

## DBをまたぐ順序と途中失敗

1. 認証済みtenantと端末資格を確認し、同じ要求/attemptの識別子を耐久保存する。RG1を非ロックで事前照合する。業務scope内では有効な資格行を `FOR SHARE` でロックし、業務DB commitまで保持する。資格失効はこの行の `UPDATE` と直列化する。資格失効側が資格行を保持したまま試合・世代行を取る経路を作らないことは認証担当の受理待ち。
2. 復元外台帳の `recovery_epoch` 1行を `FOR SHARE` で取り、業務DB commit終了まで保持する。counterは別行で原子的にD4を予約する。同じ `attempt_id` の応答不明は**同じowner tuple**でのみ再照会する。別ownerは拒否する。
3. 台帳に `reserved→claimed` を一度だけ耐久確定し、その後に業務DBの試合行 `FOR UPDATE` → U-G1のチーム行/選手行（既存順）→ U-M2記憶行（既存順）→ 記録権世代行 → V12配達行 → RG1状態行 `FOR SHARE NOWAIT` の順でロック/照合する。U-S1同期は既受理の試合行→世代行→RG1行を維持する。配達行・チーム/選手/記憶との相対順は U-G1/U-S1 の実経路照合待ち。
4. 業務DBをcommitし、結果が確定してから外部epoch共有ロックを解放する。外部の予約/claimは業務DB rollbackで戻さず、D4を飛び番として消費する。業務DB commit後・HTTP応答前の消失は同じ開始要求と端末の保存済み権利を照会し、同じV12を再交付する。

**失敗閉鎖**: 予約応答不明は新attemptを作らず元attemptを再照会。claim応答不明は二度目のclaim/業務DB投入をせず、台帳結果の確証を得るまで停止する。業務DB commit結果不明は保存済み結果の有無・現権利が確定するまで新D4を予約しない。epochのロック喪失・復旧世代不一致・RG1停止・端末失効・暗号鍵不明は業務DB全取消。外部台帳でclaim済みのD4は戻さない。復元開始の最初のtransactionはRG1状態行だけを閉じて確定し、試合行/世代行へ触れない。その後の外部epoch排他更新は既存共有fenceの終了を待つ。安全性を証明できない期間は既存世代を含め書込み停止。

**未受理項目**: U-G1の公開DTO/HTTP写像、初回発行順、要求・attemptの耐久保存点、両DB transaction/fenceの所有・commit不明解決方法、U-M2を含む実ロック全順。U-S1のPort追加引数/呼出位置/経路別B4・B9・B10写像、TSK-506の端末資格発行・注入、認証担当の資格失効ロック順。担当無回答を合意として扱わない。

## 認証・秘密管理基盤との照合

| 既存資産 | 再利用できる部分 | 足りない契約・担当候補 |
| --- | --- | --- |
| `authz/signing_key_config.py` と `.env.example` の `PITCHLOG_TOKEN_SIGNING_KEY_B64` | 起動時に必須値・Base64正規形・長さを検査する構成方式 | V12用には別の暗号鍵ID/鍵束/起動時検査が必要。鍵の保管・配布・廃止の運用担当は未指定 |
| `docs/ops/key-rotation.md` v1.0 | 配備先の実行系を漏れなく照合し、切替失敗を閉鎖する手順の考え方 | 署名鍵は旧鍵を破棄する契約。V12再交付には旧暗号鍵を必要期間だけ保持するため、同じ鍵や同じローテーション手順を流用しない。V12鍵寿命・旧鍵廃止・事故時対応は別受理 |
| `authz/team_login.py`、`verified_tenant.py`、`api/tenant_access.py` | チーム認証と有効なtenantの確定 | 現 `TenantContext` はtenant IDのみ。認証済み端末資格の発行・検証・失効、認証sessionへの束縛は未提供。認証担当とTSK-506/U-G1の所有受理が必要 |

リポジトリの `.env` 実値や秘密は参照していない。既存環境の鍵保管先や端末内保管方法はコードから証明できず、担当と保管先を仮決めしない。U-R1は暗号化・再交付・固定operationと内部再照合の提供候補、認証担当は端末資格の発行/失効、TSK-506はHTTP入口の資格注入、U-G1は開始応答の所有候補であり、**担当確定は各所有者の回答待ち**。
