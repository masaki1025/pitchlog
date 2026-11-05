# 共通成績primitive計画の限定照合

読取日: 2026-11-04。製品/正本/正式assetは変更していない。基線は40ce2e312bc46435239f2a6d0ea0f1fb919a5de0。本調査は既T5/T6候補とCSV G04-Aの接合に限定し、新しい全体監査を行わない。

## 再利用する固定点

| 原典 | 確認と今回の選択 |
| --- | --- |
| `8f67bbb25f0f5aaad84706bd42e0afa63ab15152:docs/features/mvp-basic-stats-calculation/{plan,method-addendum,research}.md` | 27項目/十分統計量/T5α・T6β③/冪等な版/未決4件の整理を再利用。3文書候補の保全だけが承認済み。TS正本/同一artifact/TS→SQLの方法候補を製品許可へ上げない |
| `40ce:docs/adr/ADR-003-domain-calc-method.md` D-1/D-1-d/D-14-f/m | 成績はD-1のまま。有限型付きDSL→αのPython/TSとβ③のsql/typed-receiver/formatter。同JS artifactの例外対象へT5/T6を足さない |
| `261b08b438ef748960e7a8cd95611b5a893367ff:docs/features/ud2-csv-export/{plan,decisions,supply-matrix}.md` G04-A | 共通root供給 `ReadPlayExportPrimitives`、唯一model `play-export.model.json`、実表WHERE/GROUP BY/window/500後の累計が採用済み計画。CSV作者のpure ZIP/保存値参照はこのproducerの完成とは別。本planのstatsモデルは共通ID参照だけにする |
| lead `725c6ba2085246768ef260fdc8effab0fd06abe3:docs/features/mvp-integration-lead/decision-sheet.md` | 更新2026-10-30。成績D02=区分写像、D03=登板単位、D04=BF帰属、D05=OPSが未回答。記録lock D02=AやCSV文書の表示区分採用とは別。当時の4未決を記録。現時点は末尾の1879 PO採用追補を正とする |
| `40ce:docs/requirements/requirements-pitchlog-2026-07-22.md` FR-021/022/A-1〜A-3 | PA全7列、当日集計は同PA行から、断中当日更新/season最終値・未取得表示、投手/打者の交代即時反映を保持。4/1年度文言は残存するが、JST暦年既採用方針を戻さず最小正式整合へ |

旧候補3文書は別WT `feature-mvp-basic-stats-calculation` に存在し、40ceツリーの承認済み実装planではない。本planをrootが採用することで今回の具体ステップ/範囲を与える。未回答の採用や正式asset受理を代記しない。

## 実装可能性の差と有限補完

- `backend/domain/model.schema.json` はinteger/bool/enum、比較/四則/min/max/half-up、finite reducer/sourceRef/maximumItemsを宣言できる。ただしtyped item/accumulatorの結合と共通model参照は完成した製品機能ではない。
- `backend/src/pitchlog/domaingen/core.py` は宣言/manifestをIRとhashへ運ぶ。`pregen_checks.py::_reference_types` はinput/state/event/outputだけで、`_expression_kind` はitem/accumulatorをnumeric固定とする。型付き共通参照/有限collection/整数加算の厳格な検査を補う。
- `backends/python.py`/`typescript.py` はdeclarationの計算でなくcalculationId/contextを返す骨格、`backends/sql.py` β1-5は固定 `COALESCE(SUM(:pitchlog_value),0)`。実式/実列binding・COUNT/SUM/window・typed receiverを生成する必要がある。手書きの同じ野球式を2言語に置かない。
- `formatter.py` の宣言/binding基盤は再利用する。TS経路のNumber/通常除算を巨大整数へ無検証で適用しない。最初は整数表示、後続は同じ宣言の正確な分子分母/half-up/混合分数/母数と0分母nullを生成する。
- `frontend/scripts/domain-sql/generate.mjs` はTSの閉式検査の試験資産だが、rows全件JSON→jsonb_array_elements、count/sum固定2出力で、実表WHERE/GROUP BY供給はない。D-1成績をこの未承認TS方式へ移さず、拒否/型/方言試験の考え方だけ利用する。

first implementationは、型付きS/source/全flagと独立期待を固定→同じ共通primitive参照から実0/1/count/addコード・実表SQLを生成→ReadPlayExportPrimitivesと直接target/3層を接合する。投球数だけを試作して終えず、既確定PA/安打/BB/HBP/K/HR/outsの群を同じengineで扱う。上流未実装variantは非成功として明示し、そのvariantの完成を無関係な型/生成器準備の開始条件にしない。

## 正式sourceと不足の区別

23flagの完全集合は、投球回算入アウト・投球数・奪三振・与四球・与死球・被安打・被本塁打・失点・失策・打席・打数・安打・本塁打・塁打・犠打・犠飛・四球・死球・三振・打撃妨害出塁・走塁妨害出塁・得点・打点。subsetだけを受理して未知をfalse補完しない。

- 23flagだけでは走者別得点/RBI数、盗塁成功、投手帰属、打席参照/完了、第三out前の実out数量、二/三塁打の正式種別を全て表せない。実T1 before/after/outEffect/runner/PA/参加者と既規範の型付き結果bindingをcanonical入力へ束縛する。最終到達塁や表示名から再判定しない。
- `db/game_state/models.py` はGame.scheduled_at/status、PlayRow source_event_id/participants/version、PlayRunnerの実責任、ParticipationIntervalの出場区間を持つが、成績版/公開pointer/計算完了metric集合は未提供。source封筒のT1計算応答を実event/ledger/slotと結ぶ供給・同TX保存を実装する。
- G04-Aの球数/各回scoreは共通modelとSQLだけ。前者はwindow後にページ抽出、後者は完了0点/未消化を保存到達状態で区別する。T5/T6は同producerの有効source relation/版を使用し、アプリでページを全件集めて累積しない。
- 当日/provisionalと公式終了確定最新版は別scope。再開はseason/公式CSVの母集団から外し、再終了で新版1件だけにする。毎球CSVの進行中DLまで終了確定限定へ狭めない。
- 生5区分キー/出場・PA記録は先行できる。初稿時点では登板/BF/OPS/名前付き区分集計は未回答をstateで示した。1879採用後は意味待ちを解除するが供給不足は別に示し、残りの実供給を継続する。全27/2CSV/実画面の完成までDoDを保つ。

## 所有・残る正式追随

共通式とReadPlayExportPrimitivesの最終writerはroot。CSV側の同file座標宣言/生成器変更は採用SHAと差分を照合してrootが直列統合し、stats側でコピー式を増やさない。CSV writer/ZIP作者は完成値のconsumerであり、T5 producer式を増やさない。

暦年正式整合は既PO方針の伝播ゲート。D-1の射程内の型/生成機能補完は今回の対象追加で扱い、表現不能が具体入力で判明した場合だけ、その1対象の必要最小正式変更を返す。新D2方式や新しい全体承認待ちを開始前提へ増設しない。正式資産のrevision/history/hash/CI受理はrootが対象別に最後に導出する。

今回はplan/research exact2のみ。source/正式asset/共有台帳/refs/DBを編集せず、P6blindの封印物/期待値を読んでいない。実装・実DB・画面成功はこのdocs成果から主張しない。


## PO実回答D02〜D05の限定伝播草案（2026-11-05）

原典はlead `1879aa469f23ef7d1f8fb93ec1b9adf6b9d2c309:docs/features/mvp-integration-lead/decision-sheet.md`。4件すべてAをPO実採用済みで、旧未回答記述は初稿の履歴に限る。契約55caseの全値は保ち、`primitive-cases.candidate.json#/po_adoption_followup`へ別layerの期待を追加した。製品出力/生成器を期待源に使わない。候補の独立review/正式受理/生成実装/実供給は未成立で、意味待ち解消をavailable/0へ変換しない。

- D02: seed実キー `game_official`,`game_semi_official` を公式、`game_open`,`game_intrasquad`,`game_other` を練習、合算を全5キーとする。同じ集合を画面/DB集計/成績CSVへ渡し、表示名で再分類しない。既scope/終了確定/非表示・ゴミ箱除外は維持する。G-1の毎球記録率が「その他」を除く規則やFR-041共有集合とは別。
- D03: 真正な実投手出場の `{game_id,player_id}` を1件。0球/IBBのみ/再登板を含め、予定登録/名簿/野手出場だけを投手出場へ昇格しない。実出場source/API不足はsource_unavailableであり0ではない。
- D04: A-2の5count(2-0,2-1,3-0,3-1,3-2)×BB/IBBは前任BF1、他7countのBB/IBBと四球以外は救援BF1。実投球数は実際の投手へ残す。複数交代でも真正な既walk_pitcher_idがあればBFへ対応する。真正保存値の無いA→B(2-0)→C(3-1)四球、およびA→B(2-0)→C(2-2)四球だけを具体gapとして抽出した。A-2の単一「前任」から先勝ち/後勝ちを発明せず、この空白を全D04/他指標の開始阻止へ拡張しない。既55caseの当時のD04 pending注記は歴史情報であり現在のPO状態ではない。
- D05: OBPとSLGを正確な分子分母で加え最終1回だけhalf-up。3打数1単打は2/3→0.667で、0.333+0.333=0.666を拒否。どちらかの分母0では値null、未定義項を0へ補わない。構造値はOBP/SLGそれぞれの分子・分母を別保持し、合算分母を作らない。技術表示候補はA-1既定leading0/scale3/half-up/U+2212と両分母合成（例 `0.667(出塁率分母3打席・長打率分母3打数)`）。画面/CSVは同一宣言のformatterを使う。共有OPSの新許可は含まない。

要件の実統合基線はこのWTのv2.18で、lead1879の先頭v2.15/旧暦年候補4517の仮v2.16を採番へ流用しない。今回v2.19案をdraftとして要件/READMEに限定提示する。既PO採用のJST暦年1/1〜12/31、`{年}年通算`を現行規範4箇所へ整合し、過去年度裁定の履歴は保存する。正式版番号/本文確定はrootが統合衝突を照合し7.3等を処理して決める。A-3へのOPS定義追加でA-5の非共有理由が古くなるため、既共有除外集合を維持して理由だけ整合した。

次のD02選択集合とD05式/formatterは同一D-1宣言・生成target/typedSQLへrootが接続する。本草案は新コード/正式model/contract/生成物を作らず、D03/D04のsource不足をD02/D05開始の前提へ増設しない。
