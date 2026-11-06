# 候補の調査根拠と未実測

2026-11-04。基線40ce2e312bc46435239f2a6d0ea0f1fb919a5de0。調査・候補文書だけを変更し、製品コード/正本/contracts/refs/commit/DB/秘密/P-6封印は操作していない。

| 再利用物 | 確認した内容 | 本候補への反映 |
|---|---|---|
| `docs/requirements/requirements-pitchlog-2026-07-22.md` FR-031/付録D | 88列全プレイ、新概念別ファイル、世代込み結合、無害化 | 88列固定+サイドカーZIP、実供給/画面DL |
| `docs/design/data-model.md` §12-1/12-2 | 全88列行き先と導出/保持/移行使用の区別 | columns.candidate.jsonのbinding区分。表記に間違いがある旧参照はTSK-271の指摘と照合 |
| `docs/features/legacy-column-mapping/research.md` §2/§3/末尾再判定 | センチネル、球種/score配列の矛盾、互換出力の生値物理保持義務は未確定 | 列名から意味を推測せず、C02で原字面往復の上乗せを避ける |
| `feature-data-model-canonical/docs/features/data-model-canonical/{plan,research}.md` | TSK-250の写像所有、63–71/62/77の互換出力未証明 | 正式機械写像を取得したとは扱わず、step1で個別receiptを受ける |
| 旧`Baseball_Scoring/config.py::COLUMN_NAMES` | 88件。旧HEAD042385188761b3fd1cdcd5aaf7dcde98fb48d04d | AST literalだけを抽出。config全体SHAはcandidate JSONに記録。旧module importなし |
| `backend/src/pitchlog/exports/csv.py` | str/int/Noneのみ、BOM/CRLF/QUOTE_ALL/無害化/行単位遅延 | 小数・日時・JSONは受理済の完成文字列へ。CSV側にfloat/計算追加なし |
| `backend/src/pitchlog/db/game_state/models.py` | Game/PlayRow/PlayRunner/Lineup/Participation、索引 | DB抽出・keyset、同game sourceへの結合。現在名簿の無条件代用なし |
| `backend/src/pitchlog/db/sync_protocol/{models,event_kinds}.py` | 受理event、D1-null変更、置換/退役、C12条件 | events sidecar、target pair、全event kindの機械全数比較 |
| `backend/src/pitchlog/db/writer_binding/ordinary_models.py` | 現在checkpoint/有限history（private） | 全試合CSV原本と同一視しない。参照権限を広げず既producerの公開export投影を受け取る |
| `backend/src/pitchlog/repositories/transaction.py` | public scopeにisolation指定引数なし | step2でtenant/RG1を保つ専用read snapshot最小拡張を計画 |
| `frontend/src/api/client.ts::apiDownload` | Blobとfilenameだけ。stale auth検証あり | 既ガード維持。完成ZIPの長さ/hash metadataだけ最小後方互換拡張 |
| `frontend/src/router.ts` | 実record routeはGameScreenEntryRecordHost | 実hostへexport component接続 |

`columns.candidate.json`のstored_field_existsも出力受理済を意味しない。語彙key→旧文字列、選手ID→履歴名/背番号、正規化座標→旧列値、投影→結果表記など、各変換のsource_receiptは未受理のまま明示した。step1で全件を受理する前にpartial readyを返さない。source_receiptはnull放置をやめ、owner/有限producer/実装stepをsupply-matrixへ固定した。

`sidecars.candidate.json`は列/schema候補であり、まだ正式contractsではない。JSONセルの内部業務schemaは元producerの受理済schemaを参照し、全記録の網羅と秘密不出力を両立させる。未知のevent kind/業務フィールドは黙って削らず契約不足として失敗。C12の全event kindとのexact-set比較をstep1の検査へ入れる。rowsのないsidecarもheader付きで出し、manifestから欠けない。

反映で追加確認: 正式付録B-7/A-1は保存→画面と新規k263正準を既決とする。旧案がB-5取り込みだけを見てC01を新裁定待ちにした点は誤りであり訂正。kx132/ky66→x132/y197が新規正準の例。courseQuantizationは入力形成であり、保存→画面の公開operationは今回の限定検索では未発見。反映1のTS正本/同artifact追加案は方式根拠が足りないため反映2で撤去。出力は現行D-1宣言モデルから生成するtargetへ変更した。

供給の具体欠測: accepted ordinary payloadにrequest/responseはあるが、StateFields/Scoreboardには投手別累計球数/全イニング配列の完成値がない。OperationEvent自体に記録timestamp列はなく、既payloadにもプレイ時刻を確認できない。履歴の表示識別/入力経路/時刻は新規同TX snapshotを追加し、既保存に無い値を遡って捏造しない。具体path/owner/対象fixtureはsupply-matrix G04/G06/G07/G08。

日時の注意: 列75/77の互換値はTSK-271のB-4（TSK-214受取）に既残件がある。旧Tag打刻Won'tを本featureで再導入しない。既時刻保存/互換値receiptを確認し、欠ける新規記録metadataはsupply-matrixで指定した同計画の保存adapterへ追加する。TSK-214全体の完了を待たない。時刻や経過時間を新しく推測生成しない。

現在のcolumn型は旧DLの宣言型でありwriter受入型と別。REALはPython floatをwriterへ渡す意味ではなく、producerの正規十進文字列を必要とする。列78–87のJSONは正規値を別sidecarで保存し、旧形式の配列をCSV側で組み直さない。打球/コースのスケールやscore末尾4を推測しない。

実行した検証は、候補JSON構文/88件/0〜87連続/ヘッダとAST literal一致/相対リンク/本文と5ステップ整合だけ。pytest/DB/実HTTP/画面/実機/独立レビューは未実施。hash一覧はrootへの受渡時にこの6文書の外へ保存し、自己参照hashを文書に埋めない。

非作者第1回P1/P2をまとめて反映。候補追加文書supply-matrix.mdが88列全件と9サイドカー全件を有限実装へ対応する。過去移行の原字面完全復元は新規MVP条件から分離し、未対応移行試合だけ非成功にする。反映後の非作者差分レビューは未実施。


反映2の原典確認: ADR-003 D-1は発効前の型付き宣言モデルを正とし、D-1-dは有限reducerからDB SQLを生成する。D-14-mはT1/T2/座標入力形成だけであり、出力変換の既決意味はD-2方式適用許可と異なる。`backend/domain/model.schema.json`/`backend/src/pitchlog/domaingen/{core,backends/sql}.py`は実在するが、必要windowの製品生成/呼出成功は未実測。G04-Aの追加有限SQL targetを本計画に指定し、不能時は手書き式へ逃げず具体的表現不足を返す。

G04のJS全件累積案はNFR-005に反するため削除した。有限RAM/keysetで全eventを畳むことはDB側集計の代用にならない。改訂では保存T1の参照（G04-R）とDB共通primitive（G04-A）を分離し、後者の唯一入口・owner・同RR選択集合・D2順序・window後のキーセット・訂正取消/世代・query planの検証をsupply-matrix末尾へ固定した。

反映2はこの既存6文書だけを編集。独立schema/ZIP/HTTP/tenant抽出の準備をstep1内で先行できる形を明記し、全計算の方式ゲートを独立準備全体の停止条件にはしない。全88列が真の値で揃うまでは200/完成としない。製品/正本/共有台帳/refs/DB操作なし。
