---
feature: mvp-p3-play-csv-producer
status: active
branch: feature/mvp-p3-play-csv-producer-20261108
承認: PO委任Codex主担当/root判断（2026-11-08 22:55 JST）
計画レビュー周回: 1
確定ゲート周回: 0
---

# P3の真正effective原本を毎球CSVへ接合する

起点 `6c52fd2b3b665b825d9c4aaf4aabc5d3ab03c732`。既 `mvp-csv-effective-product-connection` / `mvp-play-csv-delivery` / `mvp-past-correction-product` の未完接合のみ。正本の意味・数学・CSV列仕様を変更しない。新59play九回の実通過はP3/この計画の完成ではない。P3実画面とauthority診断はRecovery所有・次PGslot優先、本担当はPG無しで先行する。

## 確認した実際の停止と再利用点

- `exports/play_export_csv.py:_missing_snapshot` は `play_change` が1件でもあれば88列未供給とする。後続のsource_version/source_identities一対一、全audit行とsnapshot全対応、88列閉集合、tenant/game/event/世代/D2/play版/物理原本の全照合も必須で、先頭guardだけを削除しない。
- `tests/test_play_export_p3_selection.py` と `fixtures/play_export_p3_selector_v2.json` は唯一 `_verified_candidate_inputs(..., p3_selector_profile=v2)` を再利用し、score/read/writer各候補へ同じSと `capsule_items.payload` を有効identity全値で束縛する。独自replay/別S/現在名簿による再集計は不要かつ禁止。
- 既writer `authz/play_export_writer_product.py:candidate_function_body` はスコア側だけP3を生成できるが、`candidate_save_body` は **同TXのplay_input/event.xmin + 新規physical.xmin** を要求する。P3対象eventはplay_change、後続physicalは元IDを保持し得るため、この通常writerを自由引数で使い回しては成立しない。
- `sync/past_correction_capsule.py:build_p3_current_item` はtargetからeffective payload/history/physicalを固定する。targetだけ新play_row ID、後続は旧play_row IDを保持する。旧 `play_export_snapshots` のPKは `(tenant_id,play_row_id)`・append-onlyなので、同じphysical IDの訂正後88列を上書きできない。
- P3共有保存点は `authz/p3_projection_sql.py` / `p3_projection_paged_sql.py`（root/Recovery所有）。CSVはここへ同TXの有限hook packetを渡す。`stats/facts.py` / `ordinary_pitch_operations.py` / `past_correction_paged.py` の直接編集はしない。

## 推奨する最小供給境界（root技術採用対象）

既通常88列/監査snapshotは不変とし、**P3 capsuleに束縛したappend-only完成88列overlay**を別に保持する。identityはtenant/game/internal_generation/capsule_id/D1/effective_event_id/effective_play_row_id/physical版とitem digest、Sのfact version/revision/digestへ全値束縛。既PKを緩めず、二度目P3/旧capsule失効でも旧監査証拠を保持する。DDL/model/slot番号/認可はrootが正式割当て・配置、本担当はcacheの候補に限定する。

producerは既真正P3 frame/itemsの封印後・同TX最終head公開前へ置く。自由JSONやsuccess boolは受けず、実P3保存原本/消費済み同writer/同xidを読んで閉照合する。記録時の表示・選手・背番号・入力時刻等の不変列は元88列snapshotへ束縛し、変化する状態/物理/集計列はcorrected payload＋既唯一projector/唯一SQL生成器の出力だけを使う。原本が足りなければ未供給を返す（0/NULL/現roster補完なし）。列ごとの原典出所を先に固定し、不変と保証できない値をコピーしない。sidecarのrunner/history/effective physicalも同capsule由来へ束縛する。

読取は既同RR/RO scope、500keyset、唯一Sを維持。現在有効88列はS所属＋current capsuleのoverlayを選び、通常部分は既snapshotを選ぶ。監査原本の全coverageは通常snapshotと歴代P3 overlayを区別して検証し、`auditrows!=snapshots` の安全条件を削除せず、同じ対象集合への明示的完全照合に拡張する。extra/欠落/旧capsule差替え/異S/未知profileは409。真正scope/権限/DB異常の503を未供給へ混同しない。

## 実装ステップ（採用後）

| ステップ | 範囲 | 検査と受渡し |
|---|---|---|
| 1 | CSV専用typed proof/overlay選択・全coverage検査・列出所を具体化 | 正負pure（target/後続/未変更先行/二度目/未知版/原snapshot欠落/旧context/余剰）・新math無し。必要producer境界をrootへ固定 |
| 2 | 既唯一CSV score/read/writer生成のP3 profileを再利用、同TX producer候補とroot共有hook/DDL差分をcache化 | source同値/同TX/xmin/nonce全保持・途中fault全取消の候補対向、source原本不在は409維持。正式asset手編集なし |
| 3 | root接合後に既P3実経路からZIP同版/88列/sidecar/成績S照合 | root調整のowned1回・source固定/DSN unset/commonlock/cleanup。fixture完成値投入で200にしない。正式受理/全MVP/実機は別 |

作者編集の提案scopeは `exports/play_export_csv.py` と新CSV専用proof/projector、`repositories/play_export.py` とCSV専用reader/codec、CSV専用authz生成器（既writer/read含む）、`sync/play_export_producer.py` と新P3専用producer、専用tests/docs。共有核・モデル/DDL・正式contracts/catalog/seal/7.7・台帳・他WTはroot専有。新source/実保存契約への最小差分はcache packetにし、scope採用前の製品編集やPG実行はしない。

採用対象は7949877c9b214bc15f4ce8665729ce270c2007bd / plan SHA cadc7ecb5d1cb3bf051e1c82afe3a60a4486f486008428d4342f19028a3e5dcd。rootが全文確認し旧snapshot保持/append-only overlay/真正capsule・S・同TX・全coverageを技術採用。正式受理/実PG/全MVP成立を含まない。step1→2は本scopeで継続可、root共有核・DDL/認可は候補packetのみ。

step1値境界: `exports/p3_snapshot.py` に単独では資格を持たないtyped identity/完成値/500件以下の同RR頁検査を追加。tenant/game/gen/capsule/D1/旧play/effectiveevent/play/version/itemdigest/capsuledigest/stats版を全値照合し、88列閉集合と型を検査。新SQL/producerの真正性をこのデータclassの生成だけで成立させない。既_missing_snapshot/製品routeは未変更でP3未供給409を維持。28正負pure（別tenant/capsule/旧版/別TX/余剰欠落/NaN/bool/二度目訂正/重複/逆順）0.15秒、限定Ruff/Ty0。step2で同TX producerと真正DBreaderを接合しない限り製品提供ではない。

root技術判断（2026-11-08 23:04 JST）: target列45の新closed置換key1件（ball/called-strike）の表示名を既tenant/active語彙境界・同TX正式lookupで取得し、append-only訂正時参照へ保存することを採用。元記録時参照だったと記録せず、capsule/event/ref/timeを全束縛する。旧name/uniform/不変列を保持し、固定ラベル辞書/現在roster/他game原本の流用はしない。lookup/token不足はroot共有packet、欠落/無権限は閉拒否。

step2直接列候補: `exports/p3_projection.py` は旧88列原本と同digestのcapsule itemを照合し、先行/後続の物理・観測・参加者不変、targetのclosed ball/called-strike置換だけを認める。before/完了/打席表示は既唯一helper、集計3列は除外して既S生成SQLへ委ねる。旧氏名/番号/時刻は保持、新列45は訂正時refへ束縛。列72は通常版を変えず有限P3版（effective event/capsule/item/実artifact/旧origin）へ写し、未知形式/key/UUID/SHAを拒否。新3suiteは60passed2.18秒/限定Ty・Ruff0。既P3 selection default試験は、今正式readbodyがv2なのに旧connection defaultがv1を要求する基線差で1fail（今回両原典/正式asset未編集）。producer/正式reader/同TX共有hook未供給のため、既P3未供給409は変更していない。

step2同TX候補追補（rootの保存前後anchor・全D1carry技術採用）:

- `authz/play_export_p3_product.py` に新append-only17列/5FK/9CHECK/列ACLの宣言と3私有関数候補を追加。番号/正式配置はroot割当。保存前のcurrent S/native/CP/headをreadし、保存後は旧nativeの実失効/同xminとcapsuleのprior CPを照合する。先行nativeとprior P3 head版を単純同一視しない。自由成功bool/任意source selector/最新時刻検索を加えない。
- `sync/play_export_p3_producer.py` は既実P3 execution getter・同scope/event/writer/lease/nonce/transactionを再確認し、自由生成不能かつ1回限りのbefore receiptへ前版を固定する。pagedでも既25件の同版頁を辿り、ゲーム長を500件に制限しない。
- 不変prefixは25件keysetの `INSERT SELECT` で旧88列/full inningsをDB内carryし、Pythonへ全ゲームJSONを読み出さない。必要suffixだけ既直接列helper/唯一Sと既唯一生成scoreを使用する。頁欠落/余剰・receipt不一致・最終watermark対応不足は同TX非成功。旧監査snapshot/歴代overlayは不変。
- 直接列85は自由資格ではなく実private reader原本から生成。target列45は同TXのdisabled=false/category閉語彙の参照、列72は最初の通常origin＋今回effective capsule/item/artifactの有限版。前版P3 JSON自体は旧overlay監査として残し、再帰入れ子で増大させない。訂正時ref/timeと元時刻を区別する。
- SourceCodec原典へ整合: snapshotのtransaction_idはpg_snapshot文字列、D2はsigned64、fingerprintは既wire-v1接頭辞も許可。writer内部の取引照合はこれと混同せず、実bound identityのown xidを使う。

この段階はSQL生成/私有producerの候補。正式reader/export全audit coverageへの接合、source/token登録、migration/ACL/guard、root共有before/after hook、実PGcompile/原子性は未成立。既 `_missing_snapshot` のP3未供給409は削除せず、自由fixtureで200を作らない。root共有hookはbefore SHA付きcache patchに限定する。計画採用を正式7.7受理・人間確認・実P3成功へ読み替えない。

step2読取/coverage接合候補:

- rootがmigration slot `0050_play_export_p3_snapshots`（down_revision `0049_pitcher_entry_sources`）を予約。17列宣言は9710f6ab版と同一。本担当はmigration/正式資産を編集しない。
- 新 `authz/play_export_p3_read_product.py` / `repositories/play_export_p3_read.py` は既ReadPlayExportSources ABIを変更せず、同RR/RO・gameと(generation,capsule,D1)・単頁500だけの1関数を追加候補とする。唯一S/header/同pg_snapshot、実capsule watermark合計、全item所属/hash/17列/訂正時ref/current headを照合する。readerはscope保持/全頁件数を検査し、任意executor/汎用decoder/未登録の実行を拒否する。source_fingerprintはledger原本、item digestはcapsule原本として別々に扱う。
- 新 `exports/p3_coverage.py` はnormal＋歴代P3を全audit physicalへ完全対応させ、旧normal原本も失わない。cap内D1連続/全watermark/全group metadata・current head一意を確認し、現在Sだけから現在88列/full inningsを選ぶ。歴代と現在を同じ全件dictへせず、APIの既ExportRowStore/ディスク索引を使用する。新sidecar種別 `plays_csv_p3_v1` は同88列にcapsule/item/native/ref由来を添える（既9sidecarの列は不変）。
- `repositories/play_export.py` はP3 eventがある場合のみ専用readerを同RRで完全消費する候補。`exports/play_export_csv.py` は旧normal guardを保持し、P3は全監査coverageと現在完成原本が両方成立した場合だけ閉拒否を解除する。未供給/未登録/原本不一致を空集合の成功へしない。root正式helper/token未配置なのでこの候補のP3 HTTP/ZIP成功は未成立。
- 二度目同値followersの正例は、旧/新capsuleが同じfollower物理・観測・計算/hashを保持していても実current headとSだけで選べることを確認する。列72の今回capsule由来は変わり、旧版監査は保存される。旧head詐称、mixed head、欠落/余剰/別tenant/別source/現在JSON差替えは未供給。pure fixtureを実DB/実認可/実P3成功へ読み替えない。
- 共有3path（function_operations/operation_registry/transaction）の新read1型有限family/真正同RR dispatcherはbefore/after SHA付きcache patchのみ。本担当のWTでは共有sourceを一切変更しない。cache import overlayで実登録1＋8改変拒否＋汎用decode拒否の10対向を実行（DB呼出し/認可成功を模擬しない）。この段階で見つかったimport循環はleafの表示helper/hash importを値検査時に遅延して解消。

非作者rootのP1（9710f6ab対象）と後発92eeb229: 公開 `_TenantTransaction` に `.session` がない点を是正。実registryから既 `_capture_scope(handle,writer)` が発行する `_WriterScope` をbefore receiptへ保持し、全SQL前後で既 `_assert_scope` と元P3 execution/context/source.bound/nonceを両方検証する。公開handleへraw Sessionを追加せず、cursorは上限+1（2/26件）でcloseする。実型handle/Sessionと同registryのcapture・別runtime/別Session/fake窓口拒否20件4.88秒/RuffTy0。これは無DBの私有窓口型/拒否証拠であり、実P3権限/SQL成功ではない。元9710をP1解消済みと書き換えない。

root追加委任（2026-11-09、既step2技術scope）: `authz/play_export_p3_product.py:candidate_declarations()` を既factory同型で追加。新table1/5関数（writer3/read1/監査guard1）/3policy/27列ACL/36body。writer3/read1はapp EXECUTE、guardはowner-onlyでapp/actor/PUBLIC EXECUTE無し。全関数owner/search_path/REVOKEは固定し、未知ABI/構造/role/tenant式をmetadata pinで拒否する。監査guardはUPDATE/DELETEの全行とTRUNCATE全命令を無条件42501、`guard_trigger_sql()` 2本は正式関数適用後にrootが配置する。0050に未配置関数依存を混ぜない。

列ACLは新17（INSERT16/SELECT17）と、既通常snapshot9のINSERTを保持してSELECTを足した完全row差分、vocab display_nameのSELECT新1だけ。既vocab key/category/disabled SELECT3は原典を検査して再描画しない。旧app policy/通常INSERT policyを削らずnormal owner SELECTを別policyで追加する。未使用の初期overlay read草案関数を削除し、唯一の新RR readerへ揃えた。factory/既生成源/reader/coverage/private scopeの76pure13.95秒/RuffTy0。実SQLcompile/通常50/実CSV/正式受理は依然root接合後の未達。
