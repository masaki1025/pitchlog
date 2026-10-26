---
feature: mvp-game-start-browser-persistence
status: active
承認: 済（PO委任によるCodex判断・有限ブラウザ保存部品）
重さ分類: コア領域
branch: feature/mvp-game-start-browser-persistence
created: 2026-10-26
計画レビュー周回: 1
確定ゲート周回: 0
反映周コミット: 適用
実行方式: 通常
---

# 開始要求と端末資格のブラウザ保存

## 1. 対象と依存

実起点は正式develop30f67cbc。開始plan（候補ab2253cfのdocs/features/mvp-game-start-connection/plan.md）§11/12/13とU-F8 step6/8の、開始送信前の端末資格/要求耐久保存を有限具体化する。全MVP/既レビュー回数は変更しない。現3WTに完成部品はなく、Q1 durableQueueはイベント/D1/I6専用のため開始payloadを流用しない。backendの実enroll/worker/HTTPとは編集を分離し、待ち時間に独立実装する。

契約入力は開始候補86f876eaのbackend/src/pitchlog/api/schemas/game_start.py（SHAは着手前固定）。既exact5要求/各side exact3行、9又は10枠、UUID/StrictInt又はnull/JsonValueを保持する。名簿意味やT1計算は再実装しない。enroll応答3field、開始応答10fieldと期待tenant/game/request/deviceを照合する。D4/V12はopaque、復旧世代は正bigint十進文字列のまま、JS numberへ変換しない。

## 2. 編集範囲とcore先行登録

製品はfrontend/src/api/gameStart.ts、frontend/src/lib/gameStartPersistence.ts。試験は各々同名.spec.tsだけ。Git/本plan/.claude/core-areas.jsonはroot唯一writer。core先行宣言とその拒否試験だけscripts/core_guard.pyとtests/test_core_guard.pyも許す。他source/既Q1 DB/HTTP/router/UI/backend/正式契約JSONへ書かない。

実装前に本planとcore_guard.pyのAREA_PATH_ADDITIONSへ4pathを先行宣言し、その後の別commitでsync-protocol/recording-rights/tenant-isolationへ当該exact4pathを追記する（既paths/拒否/検出範囲は保持）。非作者の6.3⑤確認とPO委任によるroot受理後だけsourceを作る。core例外を広げない。既に正式基線へ登録済みの旧ledger追加層は履歴検査へ保持し、現追加層は新exact4だけとする。旧path・全拒否・既レビューを保持し、旧段階の検査は明示された旧追加集合で継続する。新層の欠落/部分追加/他area/余分path/同commit改変を拒否する負例を既core試験へ追加する。

## 3. 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | core追加層のコード宣言と拒否試験（coreの2path） | JSONは変更せず新exact4/3areaを宣言し、旧履歴と拒否を保持 |
| 2 | 別commitでcore JSONへ登録 | 全3areaへexact4だけ追加、旧全path/順序/対象集合不変、前段宣言との先行関係を検査 |
| 3 | 既要求/応答のclient型とstrict外形/owner照合（apiの2path） | 未知field/型/非finite/欠落/別owner/不正世代/空資格を拒否、資格を例外へ含めない。既DTOと一致し新D4形式や計算を作らない |
| 4 | 専用IndexedDBでpair/pending/受領grantの不可分保存（libの2path） | transaction完了前に成功を返さず、保存拒否/abort/reload/別owner/同ID別payload/複数tab競合を検査。既Q1不変 |

各stepを対象検査・固定/非作者確認・step単位commitし、rootが既委任に基づく次step着手を記録する。HTTP未接続を常成功で埋めず、ここに送信関数/公開URL/成功handlerを作らない。開始button封鎖の解除は後続実接合まで行わない。

## 4. 保存と結果不明の保証

専用DBのtenant別端末pairとtenant/game別要求を閉じる。pairは初回のみ登録、既異なるpairへの上書きは非対応として拒否する。送信前に同request ID/両side全payload/ownerを保存し、そのIDB commit後だけ送信準備完了を返す。同ID別payloadや別device/tenantの混在、未解決要求を新IDで置換する操作は拒否。データは防御的にcopyし、呼出し側の後発変更を保存/照合へ混入させない。

pendingの結果不明は元要求を保持してunknownへ移すだけで、成功/rollback/未使用扱い/新ID生成/自動再送は行わない。受領grantはpendingの期待owner全4fieldと照合し、元要求を残して同じIDB transactionで保存状態を更新する。IDB完了後でもこれは受領応答のローカル保存であり、T1初期state/Ready/全記録権の安全性・サーバーcommitの独立証明ではない。サーバー再交付で同ownerの同応答を受けた場合だけ冪等に保持し、矛盾する上書きを拒否する。既receivedの遅延timeout通知はreceivedを保持しunknownへ降格しない。同owner同grantの再保存はno-op、矛盾grantは既保存値を保持して拒否する。

IDB readwrite transactionの範囲をpair/要求storeへ閉じ、別tabの競合でも異なる要求が同gameへ上書きされない。記録の削除APIは作らず、pending/unknown/received状態を保持する。期限推定による破棄や原資格/元payloadの再生をしない。HTTPS/secure contextと実IDB利用可能性を確認し、失敗時は操作を進めない。既保存の資格/原V12/要求をlog/例外/画面へ出さない。

## 5. 検証と未提供範囲

Vitestとfake-indexeddbによる実API互換のtransaction/reopen検査、対象Prettier/ESLint/vue-tsc、既frontend回帰を使う。fake IDB/reopenを実機Safari/ブラウザ再起動済みへ読み替えない。意味ある故障/改変/競合負例を含め、ただ保存して読んだ同値だけで受入としない。source固定後、候補作者以外へ最終差分を渡す。

実認証/Origin/C2/enroll/worker/start/resolve/実UI/初球保存と担当交代/全MVPは後続必須。正式backend提供前に本client外形を独立契約の成立や製品開始成功と扱わず、統合時に正式版のDTOへ再照合する。運用公開/有料/共有DB/秘密発行はしない。


2026-10-26T05:37:45.382471+00:00、PO委任によるCodex /root判断で本計画を承認。対象plan SHA b67f76d7808107f5335223c997345909f494f2c841ccaa9021046388941bfde5、非作者最終review889bff54624835c182e790af69dc66c95b0c04c9e22675d15844862517be24a6/evidence829b798bcd95bc29760ccd3cdd70f68563f6d487648d28e564119ebba7e8186d。初回0/1/2→反映1の残0/0/0を保持。DTO source5459b62cc6f7de422e011fc4dbfa382639a3499a536d3eed198c4c9ead012ed1の実byte/開始応答10fieldを確認した。step1のみ先行着手し、非作者source確認後にrootがstep2/core JSON登録へ進む。新4path/3area以外の検出・拒否・既pathは変更禁止。Git/plan/JSON/台帳はrootのみ、step1 core source2の作者はrg1_final_review_oct26、製品frontend4pathの作者はroot。rootと異なる作者が最終実装をレビューし、各unitの作者資格を分離する。本人の直接実値確認/署名/実機成功を代記しない。


step1受理（PO委任によるCodex /root判断）：作者evidence3c389f4ce05b158f6c76e9a872c87f873e0f96947160c71d1baef798689734de、非作者REVIEW5945c3251e16ce1fc79d1ec9a2ac5d0a9ec5d75208e0ca47310a7aaf32fb0e03/checksa90eb81685d8fd8c52b52b908e637a23ad7fb87275e70b873e7a1bae982d7ef9、残0/0/0を実照合。旧guard29関数AST/旧133test関数decorator/旧ledger定数と歴史を保持。作者全443成功21.89s・独立対象60成功10.68sは別実行、Ruff/ty/diff成功。片側areaの拒否は試験stage helperの保証であり、prod一般guardのarea別任意段階predicateは不変。JSON/製品sourceはこの時点で未変更。rootは別commitのstep2で実JSON3areaへexact4を追記し、実Git先行関係と旧全fieldを照合してからstep3へ進む。
