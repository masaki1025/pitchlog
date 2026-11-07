# 通常49 writer故障対向の現在地

最新: 下記「通常投球1caseの限定再実走」まで完了。交代/通常投球の修正後故障対向は各1成功。製品変更なし、root非作者確認で限定候補採用、正式統合はroot。

- 起点: `fc09310484c44c63d9d0590a4451f4ca6b8beaa8`。実装固定: `196bdbe6fbedb7cb464fa34889094bd6c2fa0f95`。
- 利用者の新操作: 本単位は試験のみで、製品の操作は増やしていない。
- step1: 新tests2pathを固定。通常9球目の第3アウト後のnative/D03/CSV完了、0球投手交代のconsume/D03/CP完了に限り、原関数呼出後・同runtime/session/top/lifetimeで試験例外を投げる。製品/SQL/catalog/権限変更なし。純15件1.93秒、Ruff/Ty成功。
- 初回owned実行 `1ad7a4eb`: 2failed / 300.00秒。両caseともobserverに到達し、原関数完了・同TX資格・非成功・host前後観測まで通った。比較差分は両方 `sync_fence.writer_bindings` だけで、他game所属業務全表の全行値は一致した。別actorの正規監査永続を全取消対象へ混ぜた試験期待が誤りであり、製品不具合として直していない。
- 初回の限界: 新binding行のclosed/close_id/FPは未検査。全snapshotのcache保存がassert後にあり未保存。したがって2passedや終結監査成立と記録しない。source2867ファイル前後一致、pytest/worker終了、通常teardown。
- 後発 `196bdbe6`: writer_bindingsだけ旧全行のbyte不変、新1行の実D5/attempt/game/要求FP/eventFP/closed/close_id、全行closedを検査。FPは既単一wire部品を使用する。業務admissionを含む他全表の完全一致は維持。全snapshotをassert前に保存。誤った旧監査行/新open/close_id欠落/異D5/attempt/FP/余剰/欠落は純負例で拒否。
- 次: root主経路first2を優先し、通知後にsubstitution1caseを共通lockで再実行する。nativeの初回部分証拠と監査を含む完全成功は分ける。故障なしの通常49実HTTP/CSV成功をこの故障対向の成功へ読み替えない。
- 再開入口: `~/.cache/pitchlog/d03-normal49-faults-child-20261107/{run1.log,run1-manifest.json,run1-source-before.json,run1-source-after.json,current-checks.json,current-source.patch}`。
- 未実施: 修正後owned再検査、非作者確認、PR/統合。実機/P3/全試合0球/全MVPの成立を含まない。

## 交代1caseの限定再実走

rootの候補採用後、同 `dc2f6230` / code `196bdbe6` でsubstitutionだけを再実行し、**1passed / 98.26秒**。source2867ファイル前後一致、共有DSN unset、fixture全寿命lock、pytest/worker終了・通常teardownを確認。

実新規HTTP試合の2球後、新D5の投手交代が実consume/D03/CP保存を返した直後、同runtime/top/lifetimeで試験例外に到達しACKなしとなった。33業務表の全行全列がbaselineと一致し、部分保存はなかった。旧binding監査の全byte不変、新監査1行の実D5/attempt/game/要求FP/eventFP一致、closedとclose_id、全行closed（開いたbindingなし）を実値で確認した。raw全snapshotはassert前にcacheへ保存した。

証拠: cache同ディレクトリ `sub-run2-{source-before,source-after,result,manifest}.json` と `sub-run2.log`。最終result manifestのSHAは `4b7dcaf943a8533bcd5aba7ac017d6a54a7b1b587368d4150cc6ef904f16b0b8`（実SHAはcache正本と照合）。初回2failedは保全。本caseはASGI例外でありブラウザ500の実測ではない。native9球の修正後再検査は未実行・この回に含めていない。次の実走はroot調整に従う。

## 通常投球1caseの限定再実走

run10の終端/cleanup後、root許可に従い同code `196bdbe6`、docs後発込み `a0bdeda4` 固定でnativeのみ実行し、**1passed /202.99秒**。共有DSN unset、共通lock全fixture寿命、source2867前後完全一致、pytest3559655/worker終了と正常teardownを確認した。交代sub-run2とruntime全sourceは同一。

8球baseline後、第9球の第3アウトを実artifactで入力し、実normal Save/D03/native/CSVの原処理が返った直後、同runtime/top/lifetimeのobserverから例外へ到達しACKは無い。33業務表の全行全列がbaselineと完全一致した。旧binding全byte不変、新監査1件の実D5/attempt/game/既単一FP一致、closed/close_id、全行closedを実値で確認した。監査行を削除したり業務TXへのrollback期待を置いていない。全snapshotはassert前にcacheへ保存。

証拠: `native-run3-{source-before,source-after,result,manifest}.json` と `native-run3.log`。manifest SHA `1472f6432eafa7b3eb8705a4d5a9d60a24227bb3e6d61fd481166e57e0ae332a`。初回2failedは不変保全。ブラウザ500/全MVP/P3/正式統合CIへ成功を広げない。rootが故障tests/docs4pathを非作者確認し、PO委任によるCodex/root判断で限定候補採用を通知（2026-11-07）。rootはこの4pathだけ接合し、実source dc2f・code196bdとdocs後発を区別する。
