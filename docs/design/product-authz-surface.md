---
status: in-review
---
# 詳細設計: FR-014段階Aの規則解決認可面

## 変更履歴

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 0.1 | 2026-10-15 | TSK-550段階Aの固定制限関数だけを新設正本として起案。**本書で確定する範囲** = 関数1件の到達経路、専用ownerと最小権限、READ COMMITTEDでの親ロック後の割当照会、直接権限を開かない境界、GUC残余脅威。**実装時に確定する範囲** = 関数SQL・認可資産/適用器・カタログ/2接続/故障試験の具体。管理書込関数、段階Bの優先順位、固定function operationの実装、§6-5とF-2値は対象外。計画: `../features/ux1-fr014-rule-resolution/plan.md`、審査差分: `../features/ux1-fr014-rule-resolution/step3-formal-gate-submission.md` | in-review |

## 射程宣言

本書で確定する範囲は、段階Aの固定制限関数1件の到達経路、専用ownerと最小権限、READ COMMITTEDにおける親ロック後の割当照会、直接権限を開かない境界、GUC残余脅威である。実装時に確定する範囲は、関数SQL、認可資産・適用器、カタログ・2接続・故障試験の具体である。管理書込関数、段階Bの優先順位、固定function operationの実装、§6-5とF-2の値は本書の確定対象外とする。

## 1. 所在と段階Aの入口

製品認可面の既存実装設計は`../features/product-authz-surface/design.md`が持つ。同書は正本ではない。本書はFR-014の段階Aに追加する**固定読取関数1件**の規範だけを持ち、ロール総数と分割は[data-model 3-2節](data-model.md#3-2-ロールを-7-つに分ける論点-3裁定-a-3認証関数所有用は-u-a1規則解決関数所有用は-tsk-550-の候補)、規則データの出所は[同10-5節](data-model.md#10-5-規則セットfr-014付録f)に従う。

認証済みの同一tenant transaction scopeから`public.resolve_stage_a_rule(text,text,boolean)`だけを呼ぶ。入力は試合区分キー、必須大会キー、上書き有無とし、任意tenant ID・規則IDを呼出側から受けない。上書き有無がtrueなら段階A対象外として拒否し、全体既定を返さない。候補なし、越境、無効規則、読取失敗から試合INSERTへ進まない。段階A対象外は既受理の`stage_a_unsupported`へ写像し、公開失敗分類を増やさない。越境と候補なしの利用者向け外形は同じにする。具体的な関数公開型・戻りdecoder・固定operationはTSK-550の既受理契約に従い、実装はステップ4以後のゲートで扱う。

## 2. owner・権限・関数本体

`pitchlog_rule_resolution_fn_owner`を専用の`NOSUPERUSER NOLOGIN BYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION`ロールとし、7属性を再適用時にも正規化し、membershipを持たせない。`public`には`USAGE`だけで`CREATE`を与えない。表・列権限は次に限る。

| 表 | 関数ownerの権限 | アプリ用ロールの境界 |
| --- | --- | --- |
| `tenant_vocabularies` | `SELECT(tenant_id,key,category,disabled)`と親行`FOR UPDATE`に必要な`UPDATE(disabled)` | 既存ACL/RLSを維持 |
| `tournament_rule_assignments` | `SELECT(tenant_id,tournament_key)` | 直接SELECT・書込を拒否 |
| `game_type_rule_defaults` | `SELECT(game_type_key,game_type_category,rule_set_id)` | 既存`global_read_only`のSELECTを維持、書込を拒否 |
| `rule_sets` | `SELECT(id,regulation_innings,called_game_conditions,extra_innings_limit,tiebreak_rule,uses_dh)` | 直接SELECT・書込を拒否 |

親の列`UPDATE(disabled)`は実UPDATE能力でもあるため、NOLOGIN・membership無し・関数本文のDML禁止・カタログ検査を一体で維持する。関数は`SECURITY DEFINER`・`VOLATILE`・`SET search_path=pg_catalog,pg_temp`、全表参照をschema修飾し、DML・任意SQL・transaction制御を含めない。関数作成と`PUBLIC`の既定EXECUTE剥奪、`pitchlog_app`だけへのEXECUTE付与は既存認可適用器の同一transactionに収める。再適用と取り外しでも、専用ownerの全列grant、とくに`UPDATE(disabled)`を残さない。

## 3. 読取境界と出所

関数は`READ COMMITTED`以外で成功しない。大会親行をtenant GUCと照合して`FOR UPDATE`し、その待機が終わってから**別SQL文**で同tenant・大会の割当を照会する。割当があれば全体既定へフォールバックしない。親の`category`が`tournament`以外、`disabled=true`、不存在、tenant不一致のいずれかでも成功しない。対象の既定キーと規則IDは、付録F-2の出所が個別ゲートで承認された固定5組に一致する場合だけ成功候補とする。別IDへの付け替えは値が妥当でも出所不明として拒否する。規則行の5値は単一の相関検証を通してから同一scopeの試合保存へ渡す。

段階Aでは製品の大会割当・規則マスタ書込入口を閉じる。保守停止中の特権migration以外から既定・規則行を変えないことを前提として、この2行は通常SELECTとする。将来書込入口を開くときは、親・割当・既定・規則のロック順と保持期間を別契約として改訂し、2接続で実測する。

## 4. GUCの残余脅威と検査

関数は`app.tenant_id`の存在・UUID形式・要求大会のtenant一致を検査する。ただしアプリDB接続資格情報を取得した主体はGUCを設定できるため、関数内検査だけで偽装を防いだとは扱わない。通常製品経路のtenant真正性は認証済み`TenantContext`の発行、固定function operation、DB接続資格情報の保護と直SQL不可の運用境界に依存する。接続そのものを奪った主体の残余脅威を、認可面・tenant境界所有者とPOが明示的に採否する。

実装後は専用DBで、appの直表SELECT/書込拒否、既存既定表SELECT保持、関数のPUBLIC拒否、別tenant・欠損・無効規則・読取故障・割当あり拒否、親ロック待機の前後両順序、権限の再適用と取り外し、カタログexact-setを試験する。実関数2接続/故障注入はステップ3〜6、U-G1の実HTTP・RG1・保存全取消はTSK-395ステップ2の証跡とし、正本承認前の完了条件にしない。
