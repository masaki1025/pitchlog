---
feature: mvp-past-correction-product
status: active
承認: PO委任によるCodex主担当/rootの技術接合着手指示（2026-11-06）。新しい野球意味の採用は含まない
重さ分類: コア領域
branch: feature/mvp-past-correction-product
created: 2026-11-06
計画レビュー周回: 0
確定ゲート周回: 0
---

# 過去投球訂正の製品接合

## 1. 固定点と到達条件

起点 `043591c37ddf833553300f36d04940bb40b452e1`。本ブランチの作者は専用worktreeだけを書き、rootの結合worktree・共有台帳・正式資産には並行して書かない。既US1のP3、P7、FR-007、D06=B、T1唯一artifact、取消・終了/再開・native27の既契約を変更しない。

実画面で保存済みの過去投球1件を選び、旧内容と新内容の差分を確認して、P3として送信する。V10対象参照・V11期待版・D5・本文を固定し、同じ要求の再送では保存済み結果を再掲して再適用しない。T1/T2/T4/T6/T7と後続プレイの真正再計算、成績・終了後の最新公開pointerを同じ確定境界へ結び、再読込で訂正後だけを表示する。挿入・論理削除、過去交代訂正、全操作の下流再計算もFR-007/011の義務として残し、この1件のwitnessで完了と宣言しない。

**現実の不足**: `backend/src/pitchlog/sync/change_path.py`は汎用P3取引を持つが実製品routerはP3を明示閉鎖する。P3専用の実validator/projection/後続再計算、変更後のread、I6結果保持、画面からの正式wire生成・送信が無い。`GameScreenPastCorrection.vue`は表示専用下書きである。既undo末尾取消を過去訂正に流用しない。

## 2. 既契約の境界

- P3はD1なしの変更イベント。③認可→RG1→復旧世代→D5分類→新規だけ進行中V12/対象V11・内容へ進む。既D5同内容はI2固定再掲、異内容はB13。進行中は記録権と未同期キュー空、終了後はオンラインと復旧世代を検査する。tenant不一致は404相当で情報を漏らさない。
- T7で対象確定版と無効化意図を不可分に保存し、配信は冪等。I6は対象参照・V11・D5・確定内容・accepted_atを端末へ永続化してから完了表示する。結果不明の旧要求を新D5へ切り替えない。
- D06=BのO4では全取消を確認できなければD5を未消費と扱わない。権威照会、旧要求終結、耐久後着遮断を経て初めて同D1/同内容/新D5を不可分置換する。**これは過去訂正の改内容P3を許可する規則ではない**。
- 訂正は既唯一TS artifactで保存済み原本を対象位置から後続まで再評価する。Python/SQLに同じ野球計算を写さない。投球以外の先行・後続操作は原本/時点/名簿/責任投手/CPを保持し、未供給操作をskipまたは`unchanged`として成功させない。対象/後続の幻の走者・得点・アウトを拒否する。
- 終了済みでは終了状態・終了宣言の確定版/終了receiptを維持し、訂正後の新stats版・public pointer receiptだけをP3のT6結果に束縛して同TX切替する。旧版は履歴として残す。成績の最新版をUIまたは別集計で作らない。

## 3. ステップ

| # | 実装範囲 | 検査・停止条件 |
| --- | --- | --- |
| 1 | 既P3/訂正UI/読取・CP/成績・native27を突合し、閉じたP3本文・対象版・結果・下流再評価の技術仕様と候補asset差分を固定する | 既契約から導けない意味は具体例をrootへ送る。実Port/DB完成を着手前条件にしない |
| 2 | backendのP3専用実Port・単一artifactによる対象以降の再評価・同TX保存、routerの独立P3応答、必要な私有token/SQL/migration候補を実装する | tenant/権利/拒否順/原子性/後着/故障/同D5再掲。正式schema/認可資産はcache候補packetでroot直列受理へ渡す。未対応下流は閉じる |
| 3 | ページ付き履歴/対象版/read・差分previewとUIのP3送信、同本文再送/I6耐久保持を接続する | queue非空・offline・別tenant・旧版・同D5異内容・応答消失・I6失敗は成功表示しない。画面の保存後readと新stats pointerを照合 |
| 4 | owned PG/browserで作成→複数球→過去1球訂正→再送→再読込→終了後訂正/最新版を実測し、core敵対レビューへ固定差分を渡す | 共通flockを全寿命保持。実画面・DB・receipt/無効化/成績を検証し、候補成功と正式受理を分ける |

ステップごとに対象pathだけコミットする。pytest/Vitestの意味ある対向を伴い、source/typeを先行する。未実装操作・規範未裁定の野球分岐は明示的に閉じ、件数やfixture値だけで成功を作らない。

### 既決D-14-lの有限技術具体化（2026-11-06、主担当委任）

ADR-003 D-14-lは下流状態・帰属の再導出を既(α)の反復、成績再集計を既(α)(β)の合成と確定済みだが、付録Eの改/挿/削入力とD-8帰属比較面には未履行の穴がある。主担当はこれを新しい野球意味の裁定待ちとせず、既契約内の有限入力union・後続再評価ABI・帰属比較面/case候補へ技術具体化するよう指示した。正式contract・正本追補はcacheのin-review packetへ分離し、rootが非作者レビューと正式ゲートを直列管理する。

挿入の経路は既正本 `sync-protocol.md` 5-1〜5-3（特に325、493、520〜570行）が確定済みである。任意位置挿入はP3の新変更種別ではなく毎球入力#1をP2で適用し、D1は生成順の末尾、D2は指定した過去位置、隙間不足時だけO2/T5で局所再採番する。当初の「P3挿入event kind欠落」という推定は原典照合で撤回した。候補unionは操作ごとの既経路（修正/論理削除=P3、挿入=P2）を保持する。既決事項を新PO判断へ戻さない。

対象位置からの既成立操作は保存済み原本を有限ページで読み、元正史の状態連鎖を検証し、唯一artifactで新正史を順に再評価する。最初の有限witnessは通常投球2件の先頭をballからcalled pitchへ変更し、後続ballを同じ観測原本で再導出する。これはFR-007全操作を狭める受入ではない。交代・undo・終端打球等の後続で真正再評価が未供給なら、変更受理の前に明示閉拒否する。投手責任・第3アウト時系列・RBI裁定の欠損を推測補完しない。

### T5保存27指標の実制約追随（2026-11-07、PO委任root）

寄与が変わるP3の前提である通常の三振球が、既0045適用後も`stats_primitive_facts.ck_stats_fact_metric`の26指標制約で`batters_faced`を拒否した。これは採用済み27指標の保存面の追随漏れであり、ステップ2のbackend接合に含めて0045 migrationの第三制約を同じ27閉集合へ揃える。既26指標と未知指標拒否を保持し、実catalogの三制約全値・未知指標負例で検証する。P3の新しい野球意味や新たな指標は追加しない。

### 正規D4と寄与差の候補実証（2026-11-07、ステップ2）

実製品P3のV10 D4は開始時に発行されたowner付きwire文字列を既同期入口と同じcodecでtenant・gameに束縛し、E1 phaseの内部DB世代をCAS・capsule・T5保存へ渡す。ACKには元wire D4をそのまま残す。旧numeric D4での実測は製品経路の証拠から外し、隔離された純coreの旧試験だけに留める。既保存の見逃し三振をballへ改める有限caseは原本を唯一artifactで再評価し、対象が最終球でもT5旧版K・投手K各1と現行版各0を同TXで検証する。元結果としての見逃し三振だけを有限入力へ追加し、置換結果の未対応値や未知値は閉拒否する。この候補成功は通常投球の有限訂正に限り、走者・後続物理変更、25件超、交代、削除、挿入、終了版、画面接合は残件とする。

### 現行版の画面確認（2026-11-07、ステップ3技術追補）

同じD1数のP3では唯一artifactの`PrefixRef.checkpoint.revision`が旧値と同じになる。画面は無関係な増加を要求せず、新checkpoint ID/digest、対象の新PlayRow/source、結果、現afterを確認する。別のtenant read TXで実slotの`confirmed_version=2`、受理D5とchange event/ledger、capsuleの現checkpoint・現T5 pointerを既完全検証関数で結合したP3専用確認応答を読み、同一要求・現GETと全値照合する。旧slot版・別D5・別head・後発変更は成功に写さない。確認APIはtenant/C2の閉操作として登録し、既19 routeの同token期限更新宣言は拡張しない。

ステップ4中間の追加球読取は、P3時点の不変capsuleとその後の真正通常投球を別々に全値照合し、各球の前後文脈・D1/D2・物理行・T5 sourceを順に結合する。SQL/Pythonは後続100件を暫定有限上限として閉じる。これはMVPの件数上限ではなく、ページ化と25件超の対象・複数訂正は残件である。画面保存確認は追加球数を固定しないが、現CP・対象版・同D5/receipt・現T5 pointerを引き続き確認する。R16の真正HTTPS/PGで後続2球は成立した一方、旧Undo/LC/Sub読取は503のまま。終了後P3はLCがcurrent CPを非play形式へ更新するため、旧v3 CPを要求するP3の準備/CASは未到達である。既終了宣言の版/receiptを保ち、非play完全stackと訂正後current/成績を同TXへ結ぶ接合が必要であり、現中間成果を全P3の完了としない。

P3対象の旧投球原本とその元admission/ledger/物理行の証明は保持し、slot確定版2だけをP3 capsule/item・変更event・有効PlayRow・書込印の別資格で照合する。R24のowned実DBではslot/event/有効PlayRow/capsule/item/headとP3書込印のxminが同一、変更D5 ledgerだけ別xminだった。`change_path.py`のD5 INSERTは`idempotency.py`の一意競合再照合用`run_in_savepoint`で行うため、同じ外側の原子取引内でもledger行は子XIDになる。変更ledgerはtenant/D5/accepted/source fingerprint/非退役を厳密に要求し、別xminという新設の過剰条件だけを撤回する。これは既DB全取消の証拠を変更しない。0042/0043の確定関数は改訂せず、後発0048候補でP3版read二関数を再描画し、正式asset採否はrootの直列ゲートに残す。

端末のD1なし原要求は送信前に耐久保存し、I6受理結果を別に保持する。再読込時にI6がある場合も送信せず同要求・現read・成績を確認し、未確認なら明示表示する。今回の画面witnessは同一現D4の通常v3三球・対象版1・25件以内の1訂正であり、複数訂正、25件超、旧世代、終了/再開、後続交代と他操作の有効版接合をステップ4以降の必須残件として保持する。

### LC後のP3旧原本と有効版の接続（2026-11-07、ステップ4技術追補）

R29の真正HTTPS/PGでP3→通常2球→終了、終了T5現行版とreceiptは成立した。R31の再開は、LC後のnonplay CP下で旧投球slot版2をPython読取が版1として扱い503で閉じた。再開を成功扱いするには、同tenant・同TXで現在のnonplay CPとP3 head/capsule/変更event/元保存行/有効physical/T5旧確定版を別kindの歴史anchorとして照合し、既P3唯一検証器を共有する。現在v3 readの資格に歴史anchorを混ぜず、通常slot1の全条件、P3 slot2の同取引・同対象・有効物理行の条件を保持する。元frameのP3対象だけを有効版へ射影し、後続通常frameとLC control bridgeの前後連鎖を照合する。旧K原本と旧T5は監査用に残し、P3版の常時成功・slot2無条件通過を禁止する。0042/0043既確定関数を改訂せず、0048候補の後発read版として隔離し、rootの正式直列受理へ渡す。

R32/R33で非play歴史anchor候補は終了後の再開ACKと現在GET 200まで進んだ。画面は非play CP後に既 `nonplay-prefix-read-v1` の取消・追記パネルへ切り替わるため、再開後の通常ボールは同パネルの真正read/既writerから追加する。R34で再開前の2球目をファウルに変える試行は通常writer POST 503で止まり、P3/LC接合の成功証拠には数えない。再開前は既実証済みの通常ボール1球に絞り、再開後に非playパネルからボール1球を追記して再終了する有限witnessを先に固定する。旧R29の通常2球実証は独立に保持し、ファウル・他操作の未接続を完了扱いしない。

R46の隔離HTTPS/PGでは、正規D4の三球→過去KをballへP3訂正→同D5再掲→通常球→終了→再開→非play画面から通常球→再終了→再読込が1試合で成立した。旧T5版K/投手K各1、現行版各0、対象slot版2、最終current source 5件、二度の終了receiptと最新pointerをDBで照合した。通常球は現行open成績版のrevision/source_countを更新し、P3とLC end/reopenだけが新しい版IDを作る既実装に従い、総版数は5。R44/R45の失敗はそれぞれ再読込後の端末確認欠落とテスト版数の過剰期待として保持する。この実証は「終了後にP3訂正する」経路、複数P3、25件超、旧世代、後続交代/打球/走者、CSV88現在版、P3結果不明復旧、正式0048配備の完了を意味しない。

現artifactに旧nativeUndo fixtureの実行SHAが追随していなかったため、P3と無関係の野球値を変えず、公式Node hostの4要求/応答全値一致とCP digest再導出を確認した固定24 leafのfixture追随候補を本ステップの回帰準備として含める。旧値と差分・検査器由来はcache packetに残す。

### 25件超の同世代v3訂正（2026-11-07、ステップ4技術追補）

25件はMVPの試合長ではなく現候補の一括入力上限である。現画面・Controller・API・routerは対象D1または全履歴が25超なら閉じ、`past_correction_source` は `limit=25` の一ページで `next_cursor=null` を要求する。v3の唯一数学は `deriveLineupPlayPrefixWithContinuation` の反復であり、旧ordinary v1用 `replayPastCorrectionPage` の25件ABIをv3で使用済みとは扱わない。v3のPython tuple/capsule/T5配列、私有SQLの `items<=25`・後続100件・全行 `jsonb_agg`、P3 current readerの全件配列も同時に上限となる。件数条件だけの除去、最初の25件だけの成功、全件RAM読込は不可。

まず同一tenant・game・内部世代・recording right・P3 phase・**同一DB取引とgame lock**内で、現在CP/保存anchor/履歴版/確定水位を固定する。既 `PlayPrefixHistoryPageToken` の最大100を超えず一ページ25件以下の keyset を順に読む。各ページで `d1=前末尾+1`、`d2`単調増加、原event/ledger/history/PlayRow/走者/元計算全値と前後CP連鎖を確認し、実cursorと固定headを次ページへ渡す。最終 `next_cursor=null`、全ページ件数=固定水位、最後の元response=固定current CPを必須とする。ページ欠落/重複/逆順/混在版/途中更新/非playは保存前に閉拒否する。FEは対象を含むページだけ保持し、ページ番号からの推定版や旧headでの送信を許さない。対象offer・送信本文・確認は真正target行と同CP/slot版に再束縛する。

数学は旧/訂正後の直前応答を両方持ち越して、対象以降を既唯一hostへ順に渡す。各ページの保存観測・物理行・唯一T5評価は同じページの元ID/D1/D2に束縛し、原本と有効版の順序付きdigestをページ間で継続する。候補は一括tupleを作らず有界ページ単位で同TX私有保存面へ渡す。SQLはtenant/game/generation/capsule/attempt/phaseに束縛した有界keyset読取とページ保存・最後の全件数/連鎖digest/current CP/T5 source/pointerの不可分確定へ分ける。既確定0042/0043は書換えず、0048のschema・関数・ACL・catalogはcache候補packetでroot唯一writerへ渡す。読取側も `read_p3_current` の全件 `jsonb_agg` を有界header/page読取へ置換し、全ページを同取引で検証しながら要求ページだけを返す。NFR-005の集計はDBのtenant/game/version絞込・索引・GROUP BYを維持し、Pythonの全件集計や別野球計算を置かない。

最小正負対向は26球で対象D1=1/25/26、ページ境界25→26、同D5再掲・別本文、欠落/重複/順序逆転/古いcursor/異なるhead・tenant・世代/途中故障全取消、T5旧新版のsource件数・指標差/現在pointer、GET/reload/次球である。複数P3、旧世代、終了後訂正、後続非通常操作はこの25件超witnessから成功へ推測拡張しないが、MVP残件として引き続き実装する。
