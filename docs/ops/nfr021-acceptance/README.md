---
status: draft
---
| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 1.0 | 2026-08-19 | 新設(Phase 4-4) | draft |

# NFR-021 受入証跡の運用

## 位置づけと文書分類

このディレクトリは NFR-021 の受入証跡を運用する場所である。正本はこの
`README.md` と、`reservation-template.md`、`evidence-phase4-template.md`、
`evidence-release-template.md` の 4 件だけである。個々の予約レコードと結果証跡は、
変更不可の監査記録であり、正本ではない。

文書分類・証跡の保持・正本の確定手続は、[ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) 10.1「NFR-021 受入ゲート」の
「文書分類」および「保持」を正とする。証跡の必須項目、合格項目、受入プロファイルは
[要件定義書](../../requirements/requirements-pitchlog-2026-07-22.md) の NFR-021 を正とし、
本書では複製しない。失効の意味論と検証器の契約も、ハーネス設計書 10.1 の該当項を
参照する。

## 実務手順

受入は、予約を確定してから実施し、結果証跡で予約を閉じ、排他を解除する順に進める。
開始条件、採番、PR への統合、排他解除の規範は、ハーネス設計書 10.1「NFR-021 受入
ゲート」の「試行の排他と採番」および「実施順序」を参照する。予約が未閉塞の間は、
同一ゲートキーの次の試行を始めない。

## レコード種別の閉じた命名文法

すべて `docs/ops/nfr021-acceptance/` の直下ファイルに限る。サブディレクトリ配下の
`.md` は正規形に一致しないため不正である。

| 種別 | 正規形 | 備考 |
| --- | --- | --- |
| 正本(除外集合) | `README.md` / `reservation-template.md` / `evidence-phase4-template.md` / `evidence-release-template.md` の 4 件のみ(完全一致) | 索引必須。検証器の列挙対象から除外する。 |
| 予約レコード | `YYYY-MM-DDTHHMMSSZ-<gate_kind>-<phase4\|vX.Y.Z>-seq<NNN>-reservation.md` | `<NNN>` は `attempt_seq` の最低 3 桁ゼロ詰め。1000 以降は桁が増える。 |
| 結果証跡 | `YYYY-MM-DDTHHMMSSZ-<gate_kind>-<phase4\|vX.Y.Z>-seq<NNN>-<short_sha>.md` | `<short_sha>` は `tested_commit_sha` の短縮形。`seq<NNN>` により形式として一意にする。 |
| 上記のいずれにも一致しない `.md`(サブディレクトリ配下を含む) | fail-closed | 検証器は無視せず不合格にする。 |

| 要素 | 規則 |
| --- | --- |
| `YYYY-MM-DDTHHMMSSZ` | 秒精度の UTC。区切りは日付部のみハイフン、時刻部は区切りなし、末尾は `Z` 固定。 |
| `<gate_kind>` と第 2 要素の組 | `phase4-phase4` または `release-vX.Y.Z` のみ。その他の組合せは不正。 |
| `vX.Y.Z` | `v` + 数値 3 連のセマンティックバージョン。 |
| `<short_sha>` | 小文字 16 進の短縮 commit OID。 |
| `seq<NNN>` | `seq` + 10 進数字 3 桁以上。 |

ファイル名と frontmatter は対応させる。ファイル名の `<gate_kind>` は frontmatter の
`gate_kind` と一致し、第 2 要素が `phase4` なら `release_version` は不在、`vX.Y.Z` なら
`release_version` と一致する。`seq<NNN>` は `attempt_seq`、`<short_sha>` は
`tested_commit_sha` の短縮形に対応する。この突合は Phase 4-5 の検証器が行う。

## `attempt_id` の生成規則

`attempt_id` は次の合成形式で発行する。

```
<ゲートキー>-<attempt_seq の最低 3 桁ゼロ詰め>-<発行時刻 YYYYMMDDTHHMMSSZ>
```

- ゲートキーは `phase4` または `release-vX.Y.Z` に固定する。予約レコード、結果証跡、
  `attempt_id` のいずれでも別表記を許さない。
- 例は `phase4-001-20260819T101500Z` とする。
- 発行主体は、[要件定義書](../../requirements/requirements-pitchlog-2026-07-22.md) 8 章の
  判定者である。採番主体もハーネス設計書 10.1「NFR-021 受入ゲート」の「試行の排他と
  採番」に従う。

ゲートキーと `attempt_seq` を ID 自身に埋め込むことで、`attempt_id` とレコード本文の
不一致を目視でも検出できる。

## レコード間の一致契約

同一の `attempt_id` を持つ予約レコードと結果証跡では、ゲートキー、`attempt_seq`、
`release` の場合は `release_version` がすべて一致しなければならない。1 つでも
食い違えば fail-closed とし、検証器は対応不能として不合格にする。新しいキーは増やさない。

## 索引の必須・除外集合と監査 PR の受入条件

正本 4 件は `docs/README.md` の正本一覧に載せる。予約レコードと結果証跡は正本ではないため、
索引カバレッジ検査の対象外とする。

除外の実装は `docs/ops/nfr021-acceptance/` 全体の接頭辞単位にしてはならない。直下にあり、
かつ予約レコードまたは結果証跡の正規形に一致するものだけを除外する。正本 4 件、未知の
`.md`、サブディレクトリ配下の `.md` は索引漏れとして fail-closed にする。

この規則を `scripts/check_docs_status.py` へ実装するのは本 PR の責務ではない。予約レコード
監査 PR が実装し、正規形の予約・結果証跡を索引不要とする正例と、正本 4 件・未知の `.md`・
サブディレクトリ配下の `.md` を索引漏れとして拒否する負例の両方を受入条件に含める。

## 改変禁止と append-only

予約レコードと結果証跡は、いずれも削除・改変しない。既存証跡の変更・削除を拒否する
append-only の CI 検査は Phase 4-5 で実装する。

## Phase 4 のブートストラップ手順

Phase 4 の初回受入では、[ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) 10.1「NFR-021 受入ゲート」の
「Phase 4 のブートストラップ」を参照し、次の順に進める。

1. 4-4 の確定ゲートで、この README とテンプレート 3 枚を確定する。
2. 確定した内容に準拠して、初回の予約レコード監査 PR を `develop` へ統合する。この PR では
   ディレクトリの新設と、CI 受理に必要な最小限の索引除外規則およびそのテストを扱う。
3. Phase 4 PR にその統合点を取り込み、予約を含む候補ツリーで受入を実施する。
4. 結果証跡で予約を閉じ、合格時は Phase 4 PR をマージする。失敗時は、実装を含まない
   結果証跡だけの監査 PR で予約を閉じてから次の試行を予約する。
