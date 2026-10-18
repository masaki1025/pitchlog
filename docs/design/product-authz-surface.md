---
status: approved
---
# 詳細設計: FR-014段階Aの規則解決認可面

## 変更履歴

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-10-15 | TSK-550段階Aの固定制限関数だけを新設正本として起案。**本書で確定する範囲** = 関数1件の到達経路、専用ownerと最小権限、READ COMMITTEDでの親ロック後の割当照会、直接権限を開かない境界、GUC残余脅威。**実装時に確定する範囲** = 関数SQL・認可資産/適用器・カタログ/2接続/故障試験の具体。管理書込関数、段階Bの優先順位、固定function operationの実装、§6-5とF-2値は対象外。**2026-10-16限定追加レビュー反映**: A実行器が検証済みscopeのUUIDを第1引数へ注入するため関数identityを4引数へ訂正し、第1引数とtenant GUCの不一致を非成功に固定。公開requestは3項目のまま。**同日正式確定**: 既定・規則行の`FOR SHARE`と必要な2列`UPDATE`、scope終了までのロック保持、特権migrationの停止・排他条件、通常経路の資格情報隔離・直SQL遮断を§2〜4へ反映。追加限定7.3はP0=0/P1=1/P2=1で2件を採用し、POが最終本文とレビュー後差分を確認して今回の改訂範囲を正式確定。GUC脅威モデルの認可・tenant境界所有側採否と具体ACL・7.7は別ゲート。計画: `../features/ux1-fr014-rule-resolution/plan.md`、審査差分: `../features/ux1-fr014-rule-resolution/step3-formal-gate-submission.md` | approved |

## 射程宣言

本書で確定する範囲は、段階Aの固定制限関数1件の到達経路、専用ownerと最小権限、READ COMMITTEDにおける親ロック後の割当照会、直接権限を開かない境界、GUC残余脅威である。実装時に確定する範囲は、関数SQL、認可資産・適用器、カタログ・2接続・故障試験の具体である。管理書込関数、段階Bの優先順位、固定function operationの実装、§6-5とF-2の値は本書の確定対象外とする。

## 1. 所在と段階Aの入口

製品認可面の既存実装設計は`../features/product-authz-surface/design.md`が持つ。同書は正本ではない。本書はFR-014の段階Aに追加する**固定読取関数1件**の規範だけを持ち、ロール総数と分割は[data-model 3-2節](data-model.md#3-2-ロールを-7-つに分ける論点-3裁定-a-3認証関数所有用は-u-a1規則解決関数所有用は-tsk-550-の候補)、規則データの出所は[同10-5節](data-model.md#10-5-規則セットfr-014付録f)に従う。

認証済みの同一tenant transaction scopeから`public.resolve_stage_a_rule(uuid,text,text,boolean)`だけを呼ぶ。第1引数のtenant UUIDは検証済みscopeから固定実行器が注入する。公開requestは試合区分キー、必須大会キー、上書き有無の3項目とし、任意tenant ID・規則IDを呼出側から受けない。上書き有無がtrueなら段階A対象外として拒否し、全体既定を返さない。候補なし、越境、無効規則、読取失敗から試合INSERTへ進まない。段階A対象外は既受理の`stage_a_unsupported`へ写像し、公開失敗分類を増やさない。越境と候補なしの利用者向け外形は同じにする。具体的な関数公開型・戻りdecoder・固定operationはTSK-550の既受理契約に従い、実装はステップ4以後のゲートで扱う。

## 2. owner・権限・関数本体

`pitchlog_rule_resolution_fn_owner`を専用の`NOSUPERUSER NOLOGIN BYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION`ロールとし、7属性を再適用時にも正規化し、membershipを持たせない。`public`には`USAGE`だけで`CREATE`を与えない。表・列権限は次に限る。

| 表 | 関数ownerの権限 | アプリ用ロールの境界 |
| --- | --- | --- |
| `tenant_vocabularies` | `SELECT(tenant_id,key,category,disabled)`と親行`FOR UPDATE`に必要な`UPDATE(disabled)` | 既存ACL/RLSを維持 |
| `tournament_rule_assignments` | `SELECT(tenant_id,tournament_key)` | 直接SELECT・書込を拒否 |
| `game_type_rule_defaults` | `SELECT(game_type_key,game_type_category,rule_set_id)`と行`FOR SHARE`に必要な`UPDATE(game_type_category)` | 既存`global_read_only`のSELECTを維持、書込を拒否 |
| `rule_sets` | `SELECT(id,regulation_innings,called_game_conditions,extra_innings_limit,tiebreak_rule,uses_dh)`と行`FOR SHARE`に必要な`UPDATE(id)` | 直接SELECT・書込を拒否 |

上記3列の`UPDATE`は行ロック専用ではなく実UPDATE能力でもある。専用ownerのNOLOGIN・非membership、関数本文のDML禁止、appの直UPDATE拒否、付与・再適用・撤去時の列ACLとカタログ照合を一体で維持する。関数は`SECURITY DEFINER`・`VOLATILE`・`SET search_path=pg_catalog,pg_temp`、全表参照をschema修飾し、DML・任意SQL・transaction制御を含めない。関数作成と`PUBLIC`の既定EXECUTE剥奪、`pitchlog_app`だけへのEXECUTE付与は既存認可適用器の同一transactionに収める。取り外しでは専用ownerの3列`UPDATE`を含む全grantと関数`EXECUTE`を残さない。

## 3. 読取境界と出所

関数は`READ COMMITTED`以外で成功しない。大会親行をtenant GUCと照合して`FOR UPDATE`し、その待機が終わってから**別SQL文**で同tenant・大会の割当を照会する。割当があれば全体既定へフォールバックしない。親の`category`が`tournament`以外、`disabled=true`、不存在、tenant不一致のいずれかでも成功しない。対象の既定キーと規則IDは、付録F-2の出所が個別ゲートで承認された固定5組に一致する場合だけ成功候補とする。別IDへの付け替えは値が妥当でも出所不明として拒否する。規則行の5値は単一の相関検証を通してから同一scopeの試合保存へ渡す。

段階Aでは製品の大会割当・規則マスタ書込入口を閉じる。大会親行を`FOR UPDATE`した後、待機後の別SQL文で割当を判定し、対象の既定行と規則行をこの順に`FOR SHARE`する。取得ロックは試合保存とRG1ゲートを含む同一scopeのcommitまたはrollbackまで保持する。将来製品書込入口を開く場合は、親→割当→既定→規則の取得順と2接続の競合試験を別途受理する。特権migrationは試合作成の流入を止め、進行中scopeを排出してから既定表→規則表の順に`ACCESS EXCLUSIVE`を取得し、commitまで保持する。待機timeoutまたは結果不明なら変更と試合作成公開を停止する。

## 4. GUCの残余脅威と検査

関数は`app.tenant_id`の存在・UUID形式、第1引数のscope注入UUIDとの厳密一致、要求大会のtenant一致を検査し、不一致なら非成功とする。ただしアプリDB接続資格情報を取得した主体はGUCを設定できるため、関数内検査だけで偽装を防いだとは扱わない。通常製品経路のtenant真正性は認証済み`TenantContext`の発行、固定function operation、DB接続資格情報の隔離と直SQL遮断の運用境界に依存し、隔離を証明できなければ試合作成を公開しない。接続そのものを奪った主体の残余脅威はこの関数の保証範囲外とし、認可面・tenant境界所有者とPOが明示的に採否する。

実装後は専用DBで、appの直表SELECT/書込拒否、既存既定表SELECT保持、関数のPUBLIC拒否、別tenant・欠損・無効規則・読取故障・割当あり拒否、親ロック待機の前後両順序、権限の再適用と取り外し、カタログexact-setを試験する。実関数2接続/故障注入はステップ3〜6、U-G1の実HTTP・RG1・保存全取消はTSK-395ステップ2の証跡とし、正本承認前の完了条件にしない。
