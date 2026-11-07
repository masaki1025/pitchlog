# 旧試行照会の閉応答型修復

起点b7c0b64c、計画569014baをrootがPO委任採用。実装step1は2c6d797c。既2値DTOをresponse_modelと実返却へ接合し、JSONResponseの型検査迂回を除去。既B5/B6/B7の401/404/503と新attemptによる照合再送の意味は不変更、ACKを合成しない。新規API/認可/DB処理は増やしていない。

focused24件成功2.57秒。二値serialize/実route response_field・実port Literal一致、他の停止union/認可B値/ACK/余剰/null/型不正拒否、旧error分岐を確認した。真正認証/実DB/復旧耐久性の再実証ではない。対象Ruff/全Ty0。

root追加委任で実登録routeの有限期待を34→38へ追随（既P3 GET2/POST1、recover POST1）。未知route拒否と元downloads-only response_model=None exact集合/全route型検査は保持。全conventionsは74pass/2fail、focusedと合算98pass/2fail2.97秒。元b7c0b64cでも74pass/同2fail3.13秒を再現した。route数/配列は通過し、次の実型欠落を元検査が拒否している。

残る2赤は既P3 sync.pyのgeneration語彙と、既P3 read_sync_change_target/read_sync_change_confirmation/sync_changeの3応答型未宣言。recoverはNone集合から消えた。この修復でP3 DTOへscopeを拡大せず、除外追加/期待削除をせずrootへ引渡す。sync.pyの四つの応答型差分を逆除去すると基線全byteへ一致し、禁止語の件数も不変。cache recovery-response-fix-20261107/baseline-comparison.jsonに固定。

最終非作者レビューは未実施。確認点は、二値と既エラー分岐の不変、schema extra-forbid/strict、JSONResponse迂回解消、conventionsの除外無し、P3既赤と本変更の区別。正式assets/seal/7.7/共有台帳/他WT/運用DBは非編集、PG新起動なし。
