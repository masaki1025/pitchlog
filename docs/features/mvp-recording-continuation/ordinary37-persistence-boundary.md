# 通常37の真正prefix・独立保存資格境界候補

状態: 非作者の限定反映後P0/P1/P2=0を確認し、主担当がPO委任でstep3開始を受理。全TX・実保存は実装後の実証対象。機械形と44対向設計は `contracts/state-transition/ordinary37_persistence_boundary_candidate_v1.json`。旧20数学case・既計画は変更しない。D5消費、先行拒否、取消・訂正の共有意味は既sync-protocol/owner契約のまま。

## 1. 同TXで証明する値

内部型はJSON候補の閉schemaが正。すべてのkeyを必須にし、未知keyは拒否する。UUIDは正準小文字、整数は正準十進文字列（実DB bigintへは範囲検査後に写す）、digestは小文字64桁。既同期wireの型を変更する宣言ではない。schema importは旧20caseファイルの`/schema`と全文SHAを固定する。元schemaの参照やT2を独自に再定義しない。

- `Checkpoint`: id/revision/history_version、数学prefix_ref、wire D4/internal generation/recovery、confirmed/applied watermark、最終source、history depth、実after/rules/T2、名簿digest、artifact SHA、content digest、current/invalidated。数学のlengthは通常投球prefixの長さであり、D1/D2/一般履歴深さを置換しない。
- `WriterIdentity`: 実writerのauthority/control/business/restore/issuer/version/lease/device/tenant/game/世代/回復/codec/phase/attempt/nonce、request/event fingerprint、DB instance/backend/完全txid8/期限を全一致させる。GUCや呼出者のtrueだけでは発行しない。
- `FrameBinding`: opaque frame identity、前checkpoint id/revision/digest/ref、実source ID、request/response/artifact/newHistoryEntry digest。これらの文字列を持つことは資格ではない。実runtimeの非公開registryでhandle/writer/source event/phase/nonceに束縛された実評価frameを確認し、一回だけ消費する。
- `Admission`: 独立`ordinary37`、上記writer/checkpoint/source/frame、最終PlayRow ID、evaluated/consumed/invalid。初球印を名前だけ変えたり、初球frame/固定ball intentで兼用しない。

sourceは実accepted native operation原本とcurrent世代・D1/D2/D5・全指紋を照合する。raw eventから既source_fingerprint/operation_fingerprintを用い、独自の指紋・D2採番・カウント計算を増やさない。checkpoint content digestは自身のdigest欄のみ除く全値を既正規化に通す。T2の内部一致成功をDB由来の証拠にしない。

DB整数上限は既bigintと同じ2^63−1、txid8は既2^64−1。文字列の最大桁数だけで範囲成立とはしない。backend日時は既timestamptz実値と比較し、文字列の辞書順で期限を判定しない。nonce/credential生値をcheckpoint・新ログへ保存しない。

## 2. 初期化とn→n+1

実既核と同じgame→current generationのロック順を守り、D5再掲/内容拒否/連番/権利の既先行順を維持する。D5保存済み再掲ではframe評価や再INSERTを行わない。

prefix0は実開始readerのvalidated原本から導入する。旧first-ball prefix1は既recorded readerが原本event/slot/全PlayRow/実再評価をexact比較した場合だけ同TXで導入する。DBに都合のよいafterを事前投入したものを成功として扱わない。

通常の継続では同TXのcurrent checkpointをpoint-lockし、実水位/版/世代/原本関連を照合→共通artifactで実観測を評価→実frame保持→独立admission発行/消費→operation/slot/ledger/PlayRow/newHistoryEntry/checkpoint改訂/水位/無効化意図を不可分に確定する。毎球full履歴を取得しない。checkpoint revision・ordinary lengthは各1前進、history深さは既履歴規約から導出する。2S通常ファウルでカウント差分が空でも履歴1件とprefix前進を保つ。

保存行には実観測と実artifact出力を投影する。before/after/flag/得点/在塁/回/打順を初球定数へ固定しない。SQLでT1/T2を再実装しない。checkpointの旧版をcurrentとして書き戻すUPDATEや、未確認client afterによる補修を許さない。

## 3. DB印とnative INSERTの排他

新private ordinary admission表は実writerへの外部キー、tenant複合参照、独立PK/状態制約、default-deny/強制RLSを備える。owner/SECURITY DEFINER/search_path/ACL/installer/再適用検査は既原則を維持する。自由引数のafterや成功boolを受ける発行関数をappへ公開しない。

現在の初球admit triggerは全native INSERTへ初球印を要求する。そのためordinary triggerを単に追加すると両資格必須になり動かない。既lock guardは維持し、admit側を**実sourceの閉payload種別による排他的dispatch**にする。first-ballなら元guard条件を完全維持、ordinaryなら新資格を完全確認する。どちらもない・同eventの両資格・未知種別・別eventの印は拒否する。import/legacy/他tenantの迂回路を追加しない。

同writer/currentD4/authority世代/完全txid8・backend instance/nonce・前prefix水位/checkpoint版・source event/D1/D5・実frame/PlayRowの一致を消費時にも確認する。別TX、savepoint由来、別接続、二重消費、失効後の消費を拒否する。低32bitのxmin一致だけでtxid8同一と認めない。

## 4. 有限ページと失効

ページは版付きcheckpointに固定した、tenant/game/世代/回復/水位のWHEREと`(d1,d2,id)`keyset、SQL `limit+1`（利用者limit 1..100）で取得する。返した最後のkeyから次cursorを作り、余分1行がある場合だけnextを出す。cursorは権限ではなく、実checkpointと全軸を再照合する。cursor内の数値とDB型の写像はlosslessとし、全件読込やoffset走査へ戻さない。

訂正・取消・終了/再開・権利世代/回復・名簿/規則・正史が変わり原典関係が一致しなければcheckpointを失効させ、ownerが既採用規則で再構築するまでこの単位の継続保存を閉じる。後続実装へ新しい終了意味や取消範囲を押し付けない。未実装の操作は既501等の閉拒否を維持し、MVPから削除しない。有限tailをfull historyと表示しない。

## 5. 拒否と検証の射程

44caseの`kernelDecision`は内部の試験分類であり、新wire結果や理由コードではない。既D5同一/異内容・認可・順序・状態拒否とO4の優先は既owner関数を使う。整合破損/資格欠落/実評価失敗は保存成功を返さず、既kernelの全取消・停止・結果不明処理へ渡す。全取消を実証できない場合はD5未消費や新要求へ置換可能と扱わない。結果照会・旧要求終結/後着遮断等の既条件を変えない。

`ExecutionEvidence`は比較例のowner観測であり、製品APIへ渡して資格を作る入力ではない。DB層では実別TX/接続/故障/失効/同要求再送を起こして確認する。schema検査・比較例・実DB結果を分ける。44caseを全て実行する検査と、元初球/既同期順序/冪等/認可/全取消回帰を付ける。現時点は設計候補であり、その実行成功はまだない。

## 6. 次に実装する順序と閉パス

1. 本候補の非作者確認→既委任で採用。新POの野球意味判断は不要。実writer/数学/SQL完成を契約候補開始の条件へ戻さない。
2. `repositories/ordinary_prefix.py`・`ordinary_prefix_operations.py`で真正checkpoint point-read/有限pageを供給。`sync/ordinary_pitch_payload.py`・`ordinary_pitch_execution.py`で既ordinary domainrt callerを一回使い新frameを保持する。初球readerはprefix0/旧1の検証だけ再利用する。
3. 新migration/privateモデル・`authz/ordinary_pitch_write_stamp.py`・既初球排他guard接合と、`ordinary_pitch_tokens.py`・`ordinary_pitch_projection.py`・`ordinary_pitch_ports.py`を同原子境界へ接続。既`apply.py`/`prefix_path.py`/`transaction.py`は型付き有限dispatchだけ追加し、D5/連番/ledger/水位核を再利用する。
4. 正式operation/Port/installer/RLS/ACL/token/capabilityの追補はrootが共有登録を直列化し、7.7/oracle封印を別確認する。ownedPGで多数n→n+1、旧初球、再送、故障系を検証してstep4のAPI/画面へ接続する。

主台帳・既共有計画・初球安定WT・正本は本候補作成の編集対象外。候補作成だけで実保存や正式受理、P6/P7/T1/MVP完成を主張しない。

### 非作者反映1（2026-10-30）

P1: JSON Schemaの`$`は末尾LF直前にも一致するため、UUID/digest/整数patternを既20ABIと同じ`(?![\s\S])`の完全終端へ統一した。PlayRow ID・writer request fingerprint・source D1それぞれにLF/CRLFを付けた6対向を追加し、補修/stripせずschemaで拒否する。44caseは保存source/実DBの成功とは区別する。

### 実codecへの型整合（2026-10-30）

実E1の `wire_fingerprint.py` は既source_fingerprintに `wire-v1:` を付けた原値を返す。requestは既 `wire_request_fingerprint()` の `wire-request-v1:`、eventは `wire-v1:` を区別する。WriterIdentity.request_fingerprintだけ `(?:wire-request-v1:)?[a-f0-9]{64}`、他3用途（WriterIdentity.event_fingerprint/Source.source_fingerprint/Source.event_fingerprint）は既初球validatorとも整合する `(?:wire-v1:)?[a-f0-9]{64}` の完全終端型へ具体化する。原値をstrip/再ハッシュしない。artifact/content/request-response/nonce等の64桁digest型は不変。これは既codecの技術整合でありD5同一性・指紋算法・資格発行条件を変更しない。
