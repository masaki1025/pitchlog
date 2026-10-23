---
feature: mvp-rg1-lifecycle-connection
status: active
承認: 済（PO委任によるCodex判断、まずステップ1/2）
重さ分類: コア領域
branch: feature/mvp-rg1-lifecycle-connection
created: 2026-10-24
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# RG1の安全な成功条件と実作成接続

旧U-R1計画の新7/8のうち、安全な閉鎖・証拠照合・解除を製品へ供給する限定実装単位。全体計画は変更しない。固定baseは正式develop547d199e、作成候補65598dad、台帳の保護witness固定1e4381f8と後続authorityの実提供版を使う。rootが本worktreeの唯一の編集担当となり、台帳package/他担当パスを並行編集しない。

## 意味と最初の到達点

根拠はsync-protocol9-5/11-4、data-model3-2、U-R1 plan新7/8、rg1-preparing-acceptanceのD4分離。preparingではD4/V12/初期権・保持端末を発行しない。必要なのは認可後・INSERT前と同じ取引のcommit直前の実RG1成功だけである。台帳の全昇格/全設備喪失・非0復元・記録開始/T1完成を新規作成成功の前提へ追加しない。

最初は実隔離環境の一度限りのfresh初期化を、復元外の保護されたgenesis・実identity・既発行/不明/回収対象0の証拠から確認し、同じRG1行を正規制限経路で開いて実画面新規作成→HTTP201→DB保存→GET/reloadを通す。単なるDB行0/fixtureのopen/always-trueで成功させない。復元後の対象0とは別で、旧epoch/予約/未確定journal/不明な既設環境をfreshへ読み替えない。

閉鎖はRG1行だけを最初の取引で排他更新し、通常writerの共有lock排出を確認して確定する。close commit後も再open/競合controllerを防ぐ実leaseを保持し、authorityが同business identity/epoch/close範囲/保持主体/未消費proofを専用能力で照合できるようにする。identity専用observerをRG1読取へ拡張しない。呼出者のbool/任意JSON/非空IDを証拠としない。接続・lease喪失/再起動・旧DB復元・commit不明は閉じたまま。

非0復元の全旧世代fence、端末回収/I6退避・閲覧/書出し・未回収0/期限切れ欠落なし、解除と新D4(D3=0)の不可分確定も同じ親MVPの完成対象として残す。未提供中は当該完了遷移を閉じ、fresh成功へ拡張しない。運用公開・運用解除判断・共有DB適用・新秘密/有料資源は含めない。

## 編集scope・core

新sourceは`backend/src/pitchlog/recording_rights/rg1_lifecycle.py`、固定SQL`rg1_lifecycle.sql`、非秘密機械入力`rg1_lifecycle_manifest.json`。試験は既存捕捉内の`backend/tests/test_rg1_lifecycle.py`と`backend/tests/db/test_rg1_lifecycle_connection.py`/専用support。必要な既存RG1関数body/認可生成/実catalog比較・ORM/migration・schema/認可/tenant登録は同じ能力の最小追加だけとし、現行read ownerのUPDATE(state)・app直接表権限・owner membership/汎用EXECUTEを増やさない。新runtime/control subjectを必要最小に分離する。

実装前に全予定pathの実core被覆を検査し、上記新3sourceと新たな意味帰属が必要な既存authz pathsだけをsync/recording/tenantへ先行宣言・試験→別commitのJSON登録で追加。全旧paths/順序/guard_paths/拒否ロジックを保持する。計画外の意味/新公開経路は追加せず必要点だけroot判断へ返す。

正式9資産/外部8・schema/認可manifest/lock/oracle・履歴/snapshotはroot唯一writerが実差分の完全値/旧prefixから導出し非作者確認/PO委任受理後に反映する。data-modelの新subject/解除境界が構造改訂を要する場合は同一単位で最小7.3/7.6を通し、計画承認で正本確定を代替しない。

## 実装ステップ

| # | 単位 | 合格条件 |
| --- | --- | --- |
| 1 | core追加層の先行宣言と試験 | 未登録/片側/共変更の拒否を保持し、製品sourceは未追加 |
| 2 | 別commitでJSON登録 | 完全追加層だけ登録、全旧集合/順序/guardを保持 |
| 3 | 実閉鎖/lease/proofとfresh解除・作成接続の候補実装 | 正規制限関数/実authority照合/最小role/RLS、実201/保存/再取得と途中全取消・閉鎖競合・再起動旧open拒否。台帳全DoD/非0復元へ成功を広げない |
| 4 | 正本最小整合・完全値受理・最終独立/CI・通常統合 | 固定HEAD/diff/実baseで全必要ゲート・必須全件CI成功。親新7/8の未提供範囲を保持 |

PO委任に基づく独立確認・root承認後、指定された1ステップだけ実行する。作業中は局所pytest/Vitest/Ruff/ty、実接合は専用DB/port/tempと既存非秘密認証fixtureを使い資源を直列調整してcleanupする。候補環境成功と正式develop/実機/運用成功を区別する。人間本人の確認/署名を代記しない。


2026-10-23T20:37:51.253623+00:00、Codex主担当/rootはPO4/5/8/10に基づき、対象583735f1/plan6ca62a21116e8afb1de7ed8385ccca37579c6498222f64777e2819eed60cc47eを承認。非作者rights_replacement_reviewの限定第1回0/0/0、標準binarydiffd1ef3fd344aa4113eafaff6e0b875922830fdc535fbcff881988cce0a841aa68を照合した。まずstep1の新3source先行宣言/試験だけを実施し、検査後にstep2の別JSON登録を行う。step3の既存関数body/認可資産/migration/起動接合先はその着手前に同じ局所追補へ具体化して確認する。過去承認の再取得や新しい人間待ちではなく、PO委任による対象版の実装具体化。人間本人の逐行確認/署名、実open/保存成功/正式7.3/7.7を代記しない。
