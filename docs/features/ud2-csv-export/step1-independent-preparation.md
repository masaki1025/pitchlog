# ステップ1 独立準備の実装候補

基線/採用計画HEAD: `261b08b438ef748960e7a8cd95611b5a893367ff`。主担当のステップ1限定指示に従い、製品実装は`backend/src/pitchlog/exports/{play_rows,archive}.py`と対応2試験だけ。rootの計画採用後の実装候補であり、ステップ1全体の完了・正式schema受理・供給接続を意味しない。commitはroot担当。

## 実装した境界

- `SavedCsvRow`にgame UUID/snapshot digest/全列mappingを要求。全88列/9sidecar headersを候補JSONと機械全数照合する。欠測列/余剰列/異試合/異snapshot/不正型を拒否し、明示NULLだけを保持する。行は一行ずつ消費、並べ替え・補完・座標計算・集計・結果再計算はない。
- サイドカーの候補UUID/正準整数文字列/JSON/boolean/JST日時型を検証。JSON重複key/NaN等を拒否する。型検証後も元文字列を保持し、JSON内の式/NULL/空文字/0を失わない。正式業務schemaの全フィールド検査/必要非NULL性/供給receipt認定は未接続であり、このvalidation成功を正式データ受理とは呼ばない。
- 既`stream_csv`を再利用し、BOM/CRLF/引用/無害化をコピー実装しない。完成値はstr/int/Noneだけ。列別の野球値や新規計算を生成しない。
- `prepare_play_archive`は全10CSVを明示的に受け取り、固定ZIP entry名だけを許す。未供給ファイルと明示0行は異なる。日本語自由名をファイル名へ挿入せずgame UUIDの固定形式を使う。
- ディスク`TemporaryFile`へZIP_STOREDで書き、manifest（全CSVのSHA256/bytes/データ行数・snapshot/version digests・供給済JST日時）を追加。CRC/全ZIP SHA/長さが確定してからcontext限定ハンドルを渡す。完成後chunk読出も全消費時にhash/長さを照合する。HTTPはまだ登録していない。
- 正の設定だけを受理。既定上限は各CSV100万行/セル65,536文字/行1,048,576文字/CSV128MiB/展開総量256MiB/ZIP256MiB、chunk64KiB。上限はこのpure部品の可変設定であり製品最大試合数や無制限保証ではない。総展開上限にはmanifestも算入。一時ファイルは成功/失敗/呼出側取消/送出中断でcontext終了時に閉じる。`chunks`をcontext外へ保持して送信しない責務は後続HTTP呼出側にある。

## 検証

backend cwd、共有DSNを外した環境でpure対象のみ実行。

- `uv run pytest tests/test_play_csv_rows.py tests/test_play_export_archive.py tests/test_csv_export.py -q`: **124成功**（既writer54、新規70）、0.39秒。初回108件を保持しMapping境界16件を追加。実DB/HTTPを起動しない。
- 対象4ファイルのRuff format/check: 成功。
- 対象4ファイルの`uv run ty check`: 成功。
- `git diff --check`: 成功（新規未追跡ファイルは対象外なのでRuffも別実行）。

独立ZIP/CSV readerで全88セルの固定goldenと全9sidecar、各file/hash/bytes/行数・全ZIP整合を照合。異試合/版、欠測/余剰、0/NULL、日本語/式/改行/JSON、型境界、行/文字/整数/ファイル/展開/ZIP上限、未知長供給の遅延消費、遅いsource故障、spool確保/書込失敗、CRC失敗、呼出側cancel、完成後改変を確認した。

goldenは`step1-independent-golden.json`。完成値を受け取った後の保存/直列化境界の例であり、T1/T5の独立期待値や正式供給ベクタではない。

## 未成立と次の境界

正式contracts配置/ゲート、全88/9sidecarの実producer receipt、D-1宣言/生成target・共通T5 DB primitive、履歴metadata保存、tenant/RLS/同一RR DB抽出、registry/認可・HTTP route、実画面DL/実機/1試合実供給は**未成立**。fixture成功・型検証・ZIP完成をそれらの成功へ延長しない。現実の供給が欠けると非成功になるので、仮NULL/0を生成してMVPを完成させない。

製品のHTTP応答はまだない。ディスク準備前/中盤で失敗した場合も例外が返り、完成ハンドルは渡らない。通信切断後にZIPを成功保存しない検査は後続HTTP/DLの責任であり未検証。既exported_atはcaller供給のJST文字列で、欠測した記録時刻をここで生成しない。source_versionsもcaller供給のdigestで、DB版/資格を認定しない。

当方のwriterは本候補固定後に停止。source・試験・evidenceのSHAとpacketはcache `stats-csv-next-unit-20261104/ud2-step1-independent-preparation/`へ保全する。独立コードレビュー/主担当採否は未実施。


## 非作者P1-01の最小修復

レビュー`ud2-step1-independent-code-review-20261104/REPORT.md` SHA256 `4a78a71533fb563a19c9140d556d91c3868fe94211c58497483742b9a885c727`（P0=0/P1=1）を採用。`dict(row.values)`/`dict(tables)`がkey検査前に供給Mapping全体を取得する資源境界の穴を修復した。

共通`_bounded_mapping`で任意Mappingのlen/dict/list/frozenset化を行わず、固定schemaの幅+1までキーを順に検査する。未知/重複はその場で、欠測は有限走査終了で拒否。検査通過後だけ既知キーを固定順に一回ずつ取得する。88列は最大89キー/88値、外側10資源は最大11キー/10値。未知キーの値は取得しない。読み出し途中のKeyErrorは供給不足となり、OSError等は元の故障として伝播する。

対向は巨大10000余剰キー、無限iterator-backed Mapping、既知キー重複/余剰、欠測、長さ偽装、正常全88/10のアクセス回数、キー検査後の欠測、外側getter故障（spool前）、内側getter故障/無限Mapping（完成物をyieldせずspool cleanup）。初回の値/版/同game/無害化/順序/全88golden/ZIP/fault意味条件は変更していない。

修復後pure124件、対象Ruff/ty成功。正式供給/DB/HTTP等の未成立は前節のまま。差分再レビュー/主担当採否前、作者writerを再停止する。修復packetはcache `ud2-step1-independent-preparation-repair1/`へ別保存し、初回packetを上書きしない。

## 2026-11-04 主担当の限定採用

PO委任によるCodex主担当/root判断。候補exact6集合SHA256 `66a57ee366451bb8a2bf2fc9060cf8920c37a82e4f972fb5df092241ec700f04`を実ファイルと照合。非作者の初回REPORT `4a78a71533fb563a19c9140d556d91c3868fe94211c58497483742b9a885c727` のMapping事前全materialize P1を採用して修復し、同レビュアーの限定再レビューREPORT `90681f9a50386c152dbdccc31deb99bf8f0d5e876d19d2044b4873f083e971c0` でP0/P1未解消0を確認して、この独立準備のsource/試験を採用・保存する。旧108試験を保持、追加16対向の独立実行成功。本人の逐行確認・正式供給/契約受理やステップ1全体完了ではない。次は正式schema/receipt・共通D-1/T5 primitiveとDB抽出の接合で、欠測を仮値へ変えず、実HTTP/画面DLまで同計画を継続する。
