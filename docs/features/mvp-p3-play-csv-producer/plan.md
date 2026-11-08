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
