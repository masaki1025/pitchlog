---
feature: mvp-tiebreak-start-product
status: active
branch: feature/mvp-integration-20261109
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# タイブレーク開始から次球・再配置までの製品接続

起点 `7e5bbc8e3039bb574d8c5f6f8987ea11b61f689e`。FR-009・付録E・ADR-003 D-8・同期 D06=B の既決操作へ、2026-11-11 の PO 回答 TB-P1=A / TB-P2=A / TB-P3=A を反映する。

## 採用済み意味

- **TB-P1=A**: 記録者が、適用規則に適合する配置を確認・確定する。任意の選手を自由配置する意味ではない。実選手IDは現在の攻撃側の実出場選手から閉照合し、先頭打者との重複・同一ID・非出場者を拒否する。
- **TB-P2=A**: 配置走者の責任投手は、その半回開始時の実投手で固定する。投手交代後も維持し、失点帰属に使う。自責点計算はMVPへ追加しない（既存どおり対象外）。
- **TB-P3=A**: 発動後は各半回に規則snapshotどおり再配置する。最初の半回だけで終えない。同半回の二重配置は拒否する。

## 実装ステップ

| # | 単位 | 到達条件 |
| --- | --- | --- |
| 1 | 純遷移核 | 規則snapshot・現在半回・実選手ID・半回開始投手を閉じ、P1/P2/P3の状態・走者・participantsを同一artifact候補で返す。不正・二重配置・別半回・非出場者を純対向で拒否 |
| 2 | 契約・保存・同期 | 正式operationRows/case（初回と再配置）、tiebreak frame、P2保存・次球・GET・T5無寄与を接続。認可/RG1/記録権/C2/D5/D06/O4を維持 |
| 3 | 画面・成績・CSV・実証 | 記録者確認画面、断中キュー、次球、成績27項目/CSV、越境/再送/故障全取消、owned DB/実画面E2E。独立レビューと正式資産再導出はrootで実施 |

## 境界

- `contracts/`、正式artifact/pin、共有SQL/registry/catalog/認可/tenant/ledger/migration、台帳の最終編集はrootが一元管理する。
- 走者個人ID・責任投手・再配置をPython/SQLで別計算しない。唯一artifactの同じ遷移核を使う。
- 30秒DB writer bindingを延長しない。timeout・期待値・検査条件を緩和しない。
- 実機・本番TLS・バックアップ復旧・運用公開は別工程。

## 実装前調査（2026-11-11 20:50）

TB-P1/P2/P3=Aは純遷移核まで固定済み。製品接続の前に、次の実測済み制約を解く必要がある。

1. **通常球UIの連続記録が先決**: 初球→通常球の引継ぎは同じ画面で成立したが、三振（打席終了）後の次球で `prepareLineupPrefix` が「初球の正式計算が成立しませんでした」を返し、POST 0件で停止した（`head:2`）。タイブレーク開始後の「配置→次球→投手交代→生還→次半回」はすべてこの連続記録の上に載るため、先にACK/queue/next d1の接続を直す。9回163球の既存E2Eはブラウザ内fetchであり、この経路の証明にならない。
2. **非play frameの保存形式**: `Content` は `additionalProperties:false`。`substitutionFrames` へ混在させると `read_started_nonplay_active_history` の「substitution event数 = substitutionFrames数」と `persist_writer_pitcher_entry` の `eventKind='substitution'` 照合に抵触する。**別配列 `tiebreakFrames` を追加**し、Content schema版上げ、read関数の件数照合へtiebreak分を明示追加、専用receiptを設けるのが最小。
3. **新非play操作の完全集合**: `tiebreak_payload` / `tiebreak_execution` / `tiebreak_projection` / `tiebreak_bridge`、`consume_nonplay_tiebreak` と専用receipt、`nonplay_function_operations` の固定集合、`nonplay_product`・`runtime_contract`・`operation_registry`・ACL/catalog、authz corpus/oracle再封印、`transitionTiebreakStartV1` のartifact公開とpin再導出。
4. **正式契約**: 初回行（`tiebreakActive=false`）に加え、P3再配置行（`tiebreakActive=true`・新半回・`runners=empty`・`outs=0`）を `operationRows` へ追加し、case拡張・凍結corpusを追随する。
5. **画面**: `GameScreenSubstitutions.vue` のdisabledを外し、GET由来の実選手ID・規則配置・半回開始投手を供給する専用providerを追加。自由配置はさせず、次打者・同一ID・非出場者を画面でも選択不可にする。
