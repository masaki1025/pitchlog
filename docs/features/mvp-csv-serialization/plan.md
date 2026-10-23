---
feature: mvp-csv-serialization
status: in-review
承認: 済(2026-10-23・PO委任によるCodex判断)
重さ分類: 通常
worktree: ../../..
notion: https://chatgpt.com/space/page_711a9b1ac7d88191a6b0bc313a60db01
branch: feature/mvp-csv-serialization
created: 2026-10-23
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 毎球・成績CSVで共有する安全な直列化

## 1. 背景・目的

MVP-FR-016/017とMVP-NFR-012、FR-031/NFR-023へ向け、両CSV資源で同じ直列化部品を使う。既存DeepSeek候補Unit1AのBOM/CRLF/NULL/無害化/ストリーミング案を再利用する。既存実装検索で共通CSV writerは見つからなかった。

## 2. スコープ

backend/src/pitchlog/exports/csv.py（必要な__init__.py）とbackend/tests/test_csv_export.py、本feature文書のみ。HTTP/router/DB/認可・列順や27指標の正式契約・T5/T6計算・固定ベクタ・他featureは変更しない。これだけでCSV資源を提供済みとはしない。

## 3. 影響する正本

反映なし。既存要件の無害化を実装部品化し、正式列契約/資源接続は後続単位。source選択根拠: https://community.owasp.org/attacks/CSV_Injection （2026-10-23参照）。別アプリでの再保存後も普遍的に安全とは断言せず、受入対象の実ソフトでの検証は残る。

## 4. 実装方針

公開関数stream_csv(headers, rows, chunk_size=65536)はIterator[bytes]を返す。ヘッダとchunk_sizeは呼出時に検証し、行は必要時だけ読む。セルはstr/int/Noneだけ（bool/float/不正型は拒否）。整数を文字列化し、率や表示値は供給済み文字列として受け取る。計算・丸め・年度導出・集計は行わない。

UTF8 BOMを先頭1回だけ付け、標準csv.writerのQUOTE_ALL/CRLF/二重引用符エスケープで全セルを囲む。Noneは空文字。自由テキスト/ヘッダは先頭の=,+,-,@,TAB,CR,LF、先行空白/BOMを除いた同記号、全角記号のNFKC検出に対してU+0027を先頭へ足す。元テキスト自体のトリム/正規化はしない。整数-1は数値として保持する。保存値にこの前置文字を戻さない。

NUL、TAB/CR/LF以外のC0/DEL、不正なUnicodeは例外とし、列数不一致・不正row型・不正cellを黙殺しない。無害化を引用の前に適用する。出力chunk長は上限以下、全行list化なし、メモリは最大1行とchunk単位。行失敗は送出例外で伝播し、後続HTTPは部分CSVを成功保存しない責任を持つ（本単位はHTTP未実装）。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 共通writerとセキュリティ/遅延消費pytest | 日本語/BOM/CRLF/quote/改行/NULL/整数、6種記号・LF/全角/空白前置注入、invalid型/制御文字/行幅を検証。1万行でも先頭取得時に全行を消費せず、chunk上限を守る。backend Ruff format/check、ty、対象pytest成功 |

## 5. DoD

- [x] 独立計画レビュー後、PO委任によるCodex判断で対象SHAを承認。
- [x] 単一writerを実装し、意味計算のコピーや入力全行読込がない。
- [x] 対象試験/型/静的検査が成功し、独立コードレビューを受ける。
- [x] 資源接続/実Excel等/成績一致は未完として記録し、helper成功をMVP完成へ拡張しない。

## 6. テスト計画

backend pytestで実csv.readerへのround tripと正確なバイト列を確認。注入境界・UTF8・行幅/型拒否、生成器の消費数とchunk長を検証。pytest対象、backend Ruff format/check・tyを実施し、正式資産/計算コード/既存DeepSeek6文書の差分0を確認する。

## 計画レビューと承認

第1回全文独立レビュー: `/root/csv_review`、候補作者/root、対象SHA256 `cf7e0812cfb52b91d9a27770ca2c40a44dcbf1199ebe5e707a4df58bbc57a62b`、可決P0=0/P1=0/P2=0。作成・編集非関与、読取のみ。

PO委任によるCodex判断: 2026-10-23T12:50:23.651294+00:00、判断者/root Codex主担当。2026-10-23のMVP内計画・CSV形式具体化の委任と上記レビューに基づき、記載1ステップだけを承認する。山田正輝の個別実値確認・署名とは扱わない。

最終対象54件成功、Ruff/ty成功。実装レビュー第1回0件、独立再実行54件成功。詳細はresearch.md。台帳への追記なし: 一般ハーネスの評価変更はなく、既存NFR-023に従う製品出力部品である。最終HEAD確認/必須CI/通常統合は後続。
