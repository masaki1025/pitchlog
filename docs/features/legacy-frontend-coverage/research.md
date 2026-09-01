---
feature: legacy-frontend-coverage
type: research
date: 2026-09-02
---

# 調査メモ: 旧 frontend が要件書 v2.0(全面踏襲)をどこまで満たすか

## 問い

**旧システムの React SPA(`frontend/`)を逐語移植すれば、要件書 v2.0 の FR を満たすのか。** 満たさないなら、(a) 移植では埋まらない要件(= 新規実装)はどれか、(b) 旧にあるが要件書に無い機能(= 踏襲/破棄の PO 判断が要るもの)はどれか。

**この問いの出所**: `docs/worklog/2026-08-16-frontend-skeleton.md:91-92` の申し送り —「旧 `frontend/` が要件書 v2.0(全面踏襲)をどこまで満たしているか — **未調査**。移植前に画面ごとの差分を取る必要がある」。TSK-226 はこれを起票したもの。

**この調査は受入判定ではない**。「打席入力画面の逐語移植の受入判定」は別タスク(未起票)であり、TSK-226 とは明文で切り分けられている(`docs/features/course-coordinate-contract/plan.md:110`)。

## 結論(要約)

1. **旧 SPA は要件書 v2.0 を満たさない。** 42 FR の確定判定(§3-0 の基準 = 受入基準の条項単位の充足)は **○ 1 / △ 33 / × 8**。**受入基準の全条項を照合できたのは FR-008(試合の再開)だけ**であり、× 8 件は受入条件を満たす実装が無いか旧実装が要件と正反対(逆実装)。一次判定(○ 11 / △ 23 / × 8)は条項単位の照合で 10 件が △ へ降格した(§3-2)。
2. **欠落の中心はコア領域**。**FR-012(通信断中の記録継続)と FR-013(記録権)は、要件の受入条件を満たす実装が旧 SPA に無い**。旧 SPA はオフラインで記録を続けられず、**未送信が 1 件でもあると次の入力を全面ブロックする**設計であり、要件の前提と正反対(部品〔SW・IndexedDB・耐久キュー・べき等キー〕は在る — §2-4)。記録権は意味要素(付与・世代・引き継ぎ・読み取り専用化)のいずれにも対応する実装が見つからない(§2-4 の検索記録)。
3. **旧を逐語移植すると要件違反になる箇所が実在する**。物理削除(FR-019・絶対規則違反)、テナント分離の 403/404 混在(FR-034 違反)、球種のハードコード、状態の直接上書き(FR-040 が改善対象と明記)。
4. **「全面踏襲」と「完全に同じもの(機械的な逐語移植)」は別系統の PO 決定であり、両立しない箇所がある**。要件書・改善台帳は複数箇所で「旧を改善する」側を既決にしている。この矛盾の解消は PO 判断。
5. **要件書側にも受入判定できない穴が 20 件**ある。特に **H/E/K/B の定義が要件書のどこにも無い**のに NFR-019 がそれを一致検証の比較面に指定しており、比較面が確定しない。

---

## 0. 典拠の所在と健全性

**旧システムの実体**: `masaki1025/Baseball_Scoring-archive`(private・要件書 v2.0 の典拠保全先)を **コミット `dd03160044aa5932d3b5a025870c9a5a56d979ef`** で取得して実査した。本メモで `LEGACY:<path>:<line>` と書いたものは、このコミットの作業ツリー内のパスと行を指す。

| 確認項目 | 結果 | 確認方法(2026-09-02 実行) |
| --- | --- | --- |
| tag `pitchlog-req-v2.0-evidence` が指すコミット | `dd03160044aa5932d3b5a025870c9a5a56d979ef` | tag からの解決 |
| 実査した作業ツリーの HEAD | 同上(一致) | HEAD の解決 |
| 88 列契約(`config.py` の `COLUMN_NAMES`)の実在 | 実在(2 箇所) | 当該コミットの `config.py` を検索 |

**なぜ `dd03160` を基準にするか**: `dd03160` は **v2.0 差分の証拠固定点**である — v2.0 の全面踏襲の射程は「アーカイブ固定点 `ed6a20f` から `dd03160` までの 30 コミットで追加された機能」と決定され(`docs/worklog/2026-08-13-req-v2-legacy-parity.md:11,16`)、tag `pitchlog-req-v2.0-evidence` がこのコミットを固定している。基準を新しくすると、要件書がまだ知らない機能まで「旧にある」と数えることになる。

**版固定アーカイブとの関係**: `docs/legacy/research/` の 9 本は **`ed6a20f`(2026-07-24)時点 = Streamlit 単一アプリ**のスナップショットで、React SPA の記述を含まない(`docs/legacy/research/README.md:3`・`docs/features/req-v2-1-nfr018-single-impl/research.md:98`)。**旧 SPA に関する事実はすべて `dd03160` の実物が典拠**。版固定資料と矛盾した場合は `dd03160` を正とした(相違点は §7)。

**調査対象の規模**:

| 対象 | 規模 |
| --- | --- |
| 旧 SPA `frontend/src/` の TS/TSX | 105 ファイル・35,479 行 |
| うち画面(`src/screens/`) | 13 画面・12,695 行(最大 `GameScreen.tsx` 3,327 行 / `TeamScreen.tsx` 2,364 行 / `LineupScreen.tsx` 2,179 行) |
| 要件側 | FR 42 件 + 付録 A〜F |

### 0-1. 基準時点の腐り(申し送り)

**上流 `shogo0303/Baseball_Scoring` は `dd03160` から 68 コミット先行している**(2026-09-02 時点で `3a05296`・2026-08-26)。うち `frontend/` の差分は **95 ファイル・+5,930 行 / −318 行**。新規追加ファイルには pitchlog のコア領域に直撃するものがある:

| 上流の新規追加(dd03160 以降) | pitchlog 側の関係 |
| --- | --- |
| `components/sync/SyncCoordinator.tsx`・`syncScheduler.ts`・`activeTabSession.ts`・`ActiveTabGate.tsx` | **FR-012 の E3(非所有タブでは記録できない)・FR-013 記録権**に相当しうる |
| `lib/instantPitchFeedback.ts`・`observationCorrection.ts`・`gameCreationIdempotency.ts` | 即時フィードバック・観測補正・試合作成のべき等化 |
| `components/settings/PitchTypeSettings*`・`game/OtherPitchTypeSheet.tsx` | 球種のチーム別設定(要件書が改善対象にした領域 — `REQ:168`) |
| `scoreboard/LandscapeBaseballScoreboard.tsx`・`team/TeamKarteThemeSheet.tsx` | カルテ配色テーマは pitchlog では **Won't**(`REQ:96`) |

**この差分の追跡は本タスクの射程に入れない。** 既存の記録が理由を述べている —「**『旧に追いつく』を要件のゴールに据えると終端がない。v2.2 のカットオーバー日の確定がこの追いかけを終わらせる唯一の手段**」(`docs/worklog/2026-08-13-req-v2-legacy-parity.md:70-74`)。カットオーバー日は要件書 v2.2 送りの未決。

なお、上流の実体は 2026-09-02 に `~/projects/Baseball_Scoring` へ clone 済み(`origin/develop` = `3a05296`)。差分調査が必要になればローカルで読める。

---

## 1. 要件側 — 画面に何が要求されているか

### 1-1. 要件書は旧を「継承」で書いている

ブロック 1(FR-001〜010)は柱書きで**旧要件書 v0.2 の受入基準を包括継承**し、変更点のみ上書きする建付け(`REQ:180`)。FR 単位でも 16 件が「(旧FR-xxx継承+以下を上書き)」形式(FR-001〜010・016・018・020〜023)。**要件書だけを読んでも画面要求は完結せず、旧の受入基準が実質的に仕様の一部**になっている。

一方 **「全面踏襲」の語は変更履歴 v2.0 行の PO 決定にしかなく、FR-001〜024 の本文には無い**(`REQ:22`)。v2.0 で新設・改訂されたのは FR-041・FR-042・付録 A-5・FR-034・9 章 R-11〜13。

### 1-2. 要件書が「踏襲しない」と名指しした箇所

逐語移植の対象から明示的に外れている。旧を写すと要件違反になる。

| 対象 | 要件書の扱い | 典拠 |
| --- | --- | --- |
| 分析コードへの球種ハードコード(「スラ系=スライダー・カット・カーブ」の焼き込み) | 追加球種が集計から漏れる構造 → **ハードコード禁止** | `REQ:168` |
| ツーシーム・シュートの分類 | 旧版分析コードは落ち系に誤分類 → **継承しない** | `REQ:1214` |
| 状態の直接上書き | 旧の「履歴に残らない直接上書き」を **FR-040 が改善** | `REQ:337` |
| `frontend/src/lib/scoringReview.ts` の判定表 | **踏襲しない**(NFR-018 違反・P0) | `docs/features/req-v2-legacy-parity/design.md:400-408` |
| 公式記録の判定・改訂ワークフロー | 自責点・防御率 Won't 維持に伴い**踏襲対象外** | `docs/worklog/2026-08-13-req-v2-legacy-parity.md:21-22` |

### 1-3. 要件書側の穴(画面の受入判定ができない箇所)

20 件を検出。10 章(未決事項)と突合した結果、**10 章に載っているのは 2 件だけ**で、残り 18 件は未検出の穴。重いもの:

| # | 内容 | 典拠 | 10 章 |
| --- | --- | --- | --- |
| G-15 | **スコアボードの H/E/K/B の定義が要件書のどこにも無い**。出現は `REQ:416`(ユーザーストーリー)と `REQ:917`(NFR-019 の比較面指定)の 2 箇所のみで、算出定義は付録 A にも無い。**NFR-019 はこれをクライアント/サーバー一致の比較面に指定しており、比較面が確定しない** | `REQ:416`・`REQ:917`・付録A `REQ:1078-1131` | 無 |
| G-6 | undo の空履歴時の提示が「**構造化値であり文言は表示規則が解決する**」とされる一方、**その表示規則自体が要件書に存在しない** | `REQ:234`・`REQ:917` | 無 |
| G-7 | **「差分プレビュー」の表示項目・粒度の定義が無い**。FR-007(3 箇所)・FR-013・FR-040 が同じ語を受入条件に使う | `REQ:241,245,246,318,339` | 無 |
| G-4 | 「打球情報」「作戦」の**値集合が本文に無い**(付録 D-4 は球種 10 種のみ列挙し、他は「同様にシードデータで固定する」に留まる) | `REQ:212`・`REQ:1219` | 無 |
| — | FR-033 のレート制限(閾値・ロック時間) | `REQ:587` | **有**(セキュリティ詳細) |
| — | `プロフィール` 共有粒度・分布の最小集団数 | `REQ:505` | **有** |
| G-1〜G-20 の残り | 構えの入力 UI / 入力補助の対象キー・略号 / 走者手動変更の操作形態 / 終了宣言の促し方 / 9 ポジション警告の形態 / 未送信件数の表示位置 / 「編集して再送」の編集 UI / 通常引き継ぎの導線 / 規則設定画面の所在と担い手 / 「明示操作」の形態 / 断中注記の基準時刻 / 次打者の範囲 / カルテ一式の範囲 / 類似名の判定基準 / 補正入力の形態 / コース分布の表現形式が二択 / 共有画面のレイアウト / グループ終了通知の手段 / FR-038 の人手介入 UI | 各 FR 受入基準 | 無 |

---

## 2. 旧 SPA 側 — 実際に何があるか(概観)

### 2-1. 構成

- **ルーティング**: `react-router` の `BrowserRouter`。Route 16 件(実画面 15 + catch-all)。ガードは `RequireAuth`(token 無しは `/login`)と `RequireTeamAdmin`(`role !== 'admin'` はホーム)の 2 種のみ(`LEGACY:frontend/src/App.tsx:25-35,55-165`)。
- **認証**: チーム単位が基本、個人アカウント(入力者)も存在する 2 系統。JWT Bearer・Cookie 不使用・`TOKEN_DAYS=30`、`password_version` によるトークン失効(`LEGACY:auth.py:11,34-62`・`LEGACY:api/main.py:54-55`)。
- **チャートライブラリを一切使っていない**。図表はすべて手書き SVG / CSS div(`LEGACY:frontend/package.json:13-20` の dependencies は react / react-dom / react-router / zustand / @tanstack/react-query / lucide-react のみ)。
- **指標計算はほぼ全てサーバー側**。API は Streamlit 時代の `charts/` 純粋関数をそのまま再利用しており、`analytics/`(Streamlit UI 層)は `api/` から一切 import されていない(`LEGACY:api/analysis_summary.py:16-17`・`LEGACY:api/karte_service.py:16-24`)。

### 2-2. 1 球入力フロー(FR-002 の中心)

- 横持ちは 3 カラム固定(`lg:grid-cols-[264px_368px_360px]` — `LEGACY:frontend/src/screens/GameScreen.tsx:2742`)。中央ペインが `centerMode` で **zone ⇄ field** を切り替える(`:2839`)。
- **順序は強制されていない**。Streamlit のような段階開示ではなく、zone モードで構え・コース・球種・球速が同時に見えていて任意順に入力できる。順序性は「結果を選んだ瞬間に field へ切り替わる」ことだけで担保(`:1873-1987`)。
- **座標は 0〜263 の正方形・原点左上**。唯一の幾何定義は `shared/display_geometry_263_v1.json`(ゾーン矩形 left80/right183/top68/bottom180)。タップ座標は 0.1〜262.9 にクランプ。**保存座標は常に捕手側視点**で、投手後方視点は画面 X を `263 - x` で反転して保存値へ戻す(`LEGACY:frontend/src/lib/courseInputView.ts:11-27`)。送信ペイロードに `pitch_coordinate_system: 'catcher_view_263'` を明示(`LEGACY:frontend/src/lib/captureMetadata.ts:39-42`)。
- **操作回数**(実装から逐語に計数): ボール/見逃し/空振り = **5 操作で確定ボタンなし即登録** / ファール = 7(自動確定) / インプレー = 8 / 申告敬遠・ピッチクロック違反 = **2**(無投球で即登録) / 投手牽制 = 3。
- **球速は既定「下 2 桁クイック」**。00〜69 は先頭に 1 を補完(35→135)、70〜99 はそのまま(`LEGACY:frontend/src/lib/speedInput.ts:3,46-50`)。
- **キーボードショートカット完備**(`b`/`s`/`w`/`f` = ボール/見逃し/空振り/ファール、`q e r t y u a d g` = 球種、`0-9` 球速、`Enter` 確定、`Esc` 段階的キャンセル、`Ctrl+Z` undo)。再割当可、数字キーは再割当不可(`LEGACY:frontend/src/lib/shortcuts.ts:22-85,120-122`)。
- **必須未入力はクライアントで事前チェックしない**。`buildPlayInput` は未入力を `0`/`false` に落として送り、**サーバー 422 の `detail.code` を受けて初めて**該当ペインへ自動切替してハイライトする(`:998-1051,1160-1179,1201-1207`)。クライアント事前ブロックは球速の下 1 桁未入力のみ(`:1822-1828`)。**修正モードだけは事前検証がある**(`:244-290`)。

### 2-3. undo・修正・遡及編集(FR-006/007 の中心)

- **undo は最後の 1 プレイのみ。多段 undo は無い**(`DELETE /games/{id}/plays/last` — `LEGACY:frontend/src/api/endpoints.ts:630-635`)。GameScreen からは確認なしで即実行、PlaysScreen では 2 段階確認。
- **過去修正は 2 段階**: `POST /plays/{id}/edit-preview` → `PlayEditImpactSheet` で影響提示 → `preview_hash` + `confirm_recalculation: true` を添えて `PATCH /plays/{id}`。**`blocking_issues` が 1 件でもあれば確定不可**(`LEGACY:frontend/src/screens/GameScreen.tsx:1760-1794`・`LEGACY:frontend/src/components/game/PlayEditImpactSheet.tsx:201`)。
- **差分プレビューの中身**(要件 G-7 が未定義としている部分の、旧の実装): 更新対象行数/状況変化行数のバッジ、変更内容の before→after 表、修正前/修正後の試合状況カード(回表裏・スコア・BSO・打者・走者)、後続プレイの再計算差分の折りたたみ、警告と保存不可理由(`PlayEditImpactSheet.tsx:80-206`)。
- **交代の遡及修正**は打順枠 1 つ単位。終了境界とその理由(次の別選手への交代 / 現在スタメン維持 / 後任が既に記録済み / 選手 ID 不明)まで提示する(`LEGACY:frontend/src/components/game/HistoricalSubstitutionSheet.tsx:94-112,456-491`)。
- **死んだ実装がある**: `HistoricalEditPreviewSheet` と `previewHistoricalPlayEdit`/`commitHistoricalPlayEdit`(サーバー側 `POST /plays/{id}/edit/preview`・`/edit/commit`)は SPA から一度も呼ばれない。**過去修正の API が 2 系統あり片方だけが使われている**。移行仕様の決定に効く事実。

### 2-4. オフライン・同期・記録権(FR-012/013 の中心)— ここが最大の欠落

**部品はある**:

| 部品 | 実装 | 典拠 |
| --- | --- | --- |
| Service Worker | 本番ビルドのみ登録。`/api/*` は常に network-only。**`skipWaiting` を敢えて呼ばない**(未送信 outbox を持つ記録画面を強制更新しないため) | `LEGACY:frontend/public/sw.js:69-71,91-95` |
| IndexedDB | DB `baseball-system-offline-v1`。localStorage をバイト単位ミラーとして併用 | `LEGACY:frontend/src/lib/indexedDbStorage.ts:3-6,120-134` |
| 送信キュー | zustand persist の耐久 outbox。状態 5 種、スキーマ v5、移行不能な旧データは削除せず `quarantined` へ隔離 | `LEGACY:frontend/src/stores/syncStore.ts:15-21,129-254` |
| べき等キー | `client_event_id`(UUID)+ `device_id` + `captured_at` を全送信に自動付与 | `LEGACY:frontend/src/lib/captureMetadata.ts:18-44` |
| タブ間排他 | Web Locks `bb-sync:{teamId}:{gameId}` | `LEGACY:frontend/src/screens/GameScreen.tsx:1318-1328` |
| バックオフ | 2 秒→最大 60 秒の指数+ジッタ、429 は `Retry-After` 尊重、401 は自動再試行停止 | `LEGACY:frontend/src/lib/syncPolicy.ts:4-53` |

**しかしオフラインで記録を続けることはできない**(実物で確認済み):

- キューへ入るのは**確定 POST が失敗したときだけ**(`LEGACY:frontend/src/lib/syncPolicy.ts:64-72`)。
- **当該試合に未同期が 1 件でもある間、次の入力は一切できない**。`doConfirm` が中断して「未同期プレイの送信完了後に次の入力を行ってください」を出す(`LEGACY:frontend/src/screens/GameScreen.tsx:1833-1846`)。入力グリッド全体が `pointer-events-none`、キーボードも Tab 以外を preventDefault。
- つまり **SPA がオフラインで保持できるのは「送信に失敗した最後の 1 球」だけ**。ロック解除は「同期成功」か「未同期センターで明示破棄」の 2 つのみ。
- 同様に、未同期がある間は **1 球戻す・直前修正・過去修正・状況変更・タイブレーク・入力終了・交代も全てブロック**される。
- `revision_conflict` は**自動解決しない**。「安全のため更新番号だけを書き換える自動再送は行いません」と告げて手動再入力を求める(`:3229-3278`)。

**記録権は存在しない**(実物で確認済み):

- 入力ロックの判定材料は `syncHydrated` / `pendingForCurrentGame` / `editBusy` / `gameFinished` / `historicalEditActive` の **5 つとも端末内の状態**で、他端末を一切見ない(`LEGACY:frontend/src/lib/gameInputLock.ts:16-29`)。
- 検索式 `grep -rniE '記録権|input_lock|recording_right|lock_holder|write_lock|scorer_lock|owner_device'`(対象: リポジトリ全体の .ts/.tsx/.py)のヒットは**名簿更新の DB ロック 3 件のみ**(`LEGACY:db/team_management_repo.py:105,332,441` の `_begin_roster_write_locked` — 記録権とは無関係)。
- **記録権の意味要素ごとの不在**: ①**付与**(試合×端末に記録権を与える API・状態)= 対応実装なし ②**世代/フェンシング**(旧世代のイベントを拒む仕組み)= なし(在るのは `write_revision` の楽観ロック後勝ち 409 のみ) ③**引き継ぎ**(通常/緊急の移譲操作)= なし ④**読み取り専用化**(権を失った端末の閲覧専用化)= なし(入力ロックは全て端末内状態由来 — `LEGACY:frontend/src/lib/gameInputLock.ts:16-29`)。
- あるのは ① サーバーの楽観ロック(`write_revision` 不一致で 409「別の端末で試合データが更新されました。」)② 端末ローカルの入力盤ロック ③ タブ間の送信排他 の 3 つだけで、いずれも記録権ではない。**同一チームの複数端末が同じ試合を同時に開いて交互に書き込むことは機構上ブロックされない**(先に書いた方が勝ち、後は 409)。

### 2-5. 分析・カルテ・出力

- **図表 15 種を実装**(すべて手書き SVG / CSS)。3×3 コース別打率ヒートマップ、37×37 ガウシアン密度の投球位置ヒートマップ(インライン SVG・`feGaussianBlur`)、打球位置スプレー図、球速分布の分位点バー(min〜max / p10〜p90 / 中央値)、カウント別球種構成、状況別配球 3×3 など。
- **WHIP・FIP・防御率・自責点は旧 SPA にも旧 API にも存在しない**(実物で確認済み): `frontend/src` のヒット 13 件はすべて `scoringReview.ts` 系の自責点まわりで WHIP/FIP は 0、`api/` **0 件**、`charts/` **0 件**。実装があるのは Streamlit 専用の `LEGACY:analytics/cal_stats.py:101-110` のみで、**`api/` は `analytics/` を import していない**。
- **カルテ所見**は楽観ロック付き(409 `karte_note_conflict` 時は下書き保持 +「最新を読み込む」)。テキスト 4 種(各最大 20 行・1 行 500 文字)+ 投手の球種メモ最大 20 件(`LEGACY:frontend/src/screens/KarteScreen.tsx:129-219`)。
- **出力は充実**: 投手/打者分析 PDF・PPTX、チーム攻撃分析 PDF、試合用カルテ PDF/HTML(**headless Chrome の `--print-to-pdf`**)、一括レポート(PDF 20 名 / PPTX 8 名上限、同時実行は 429)、スコア表 PDF、88 列 CSV(1 試合 / 最大 100 試合 ZIP)。分析系の出力エンドポイントは**すべて管理者限定**。CSV は数式インジェクション対策済み(先頭 `= + - @` をクォート・BOM + CRLF)。
- **`scoringReview.ts` の裁定**: 打点・自責点の判定表をフロントで独自再実装しているのは**コードとして事実**(NFR-018 相当の二重実装)。ただし呼び出し元は `LEGACY:frontend/src/api/mock.ts` の 3 箇所のみで、**MOCK モード専用のシャドー実装**。実運用経路では GameScreen がサーバーの `scoring_review` を表示するだけ(`LEGACY:frontend/src/screens/GameScreen.tsx:1247-1250`)。→ 先行記録(`docs/features/req-v2-legacy-parity/research.md:218`)は事実だが、「本番の状況計算がフロントで動いている」という含意までは成立しない。**ただし `LEGACY:frontend/src/lib/playRules.ts` の `assessScoringRules` は実運用経路(`GameScreen`・`ResultPad`)から呼ばれており、こちらが NFR-018 の実質的な論点**。

### 2-6. 管理・削除・移送

- **試合削除は物理削除**(実物で確認済み): `DELETE FROM play_player_link` / `play_data` / `game` を 1 トランザクションで実行し、`data/game_{id}.json` も削除(`LEGACY:db/game_repo.py:2750-2781`)。確認シートの文言は「**この操作は取り消せません**」で、確定に文字列「削除」の入力が必要。**論理削除フラグ・ゴミ箱・復元 API はリポジトリ全体でヒット 0 件**。
- **選手の削除 API は存在しない**(`LEGACY:api/routers/teams.py` に DELETE ルート 0 本)。`player_repo.delete_player` は Streamlit 管理画面からのみ呼ばれ、実装は `active=0` 化。
- **管理コンソールは SPA に無い**。Streamlit `LEGACY:app/pages/admin.py` にのみ存在し、`DB_ADMIN_PASSWORD` による**チームログインと独立した別建て認証**。しかも**所有者スコープを一切かけない**(任意チームの名簿閲覧・選手削除・他チームのユーザー削除・テーマ設定)。`api/` の `DB_ADMIN_PASSWORD` 参照は **0 件**。
- **88 列 CSV の取り込みは実装済み**: 契約名 `play_data-v1-88`、`system` モードは**順序まで含めて厳密一致**要求、`legacy` モードは列名エイリアス 15 件で変換。10MB / 20,000 行 / 1 セル 250,000 文字の上限、文字コード自動判定(`utf-8-sig`→`utf-8`→`cp932`)、owner + SHA-256 レシートによる重複防止、preview→commit 間の改変検出(409)。取り込み単位は**必ず新しい試合**。

---

### 2-7. 画面 × FR 対応表(13 画面)

母集団は **`LEGACY:frontend/src/screens/` の 13 コンポーネント**(実測 13 ファイル)。ルート定義は 16 件(catch-all 1 を除く実画面 15)で、KarteScreen と LineupScreen が各 2 ルートを持つ(`LEGACY:frontend/src/App.tsx:55-165`)。シート類(交代・状況変更・設定など)は宿主画面の行に含めた。

| # | 画面 | 実装がある関係 FR | 本来この画面が宿主だが旧に実装が無い FR |
| --- | --- | --- | --- |
| 1 | LoginScreen | FR-033 | — |
| 2 | StartScreen(+ SettingsSheet) | FR-008(再開導線)・FR-019(削除導線 — 逆実装)・FR-036 | — |
| 3 | LineupScreen(2 ルート: new / change) | FR-001・FR-011・FR-016・FR-039 | FR-015(その場登録) |
| 4 | GameScreen(+ 各シート) | FR-002・FR-003・FR-004・FR-005・FR-006・FR-007・FR-009・FR-010・FR-020・FR-021・FR-022・FR-023・FR-040 | FR-012(オフライン記録継続)・FR-013(記録権)・FR-024(プリフェッチ) |
| 5 | PlaysScreen | FR-007(過去修正の入口)・FR-031(単一試合 CSV) | — |
| 6 | GameListScreen | FR-008・FR-019(逆実装)・FR-031(一括 CSV) | — |
| 7 | ScoreCardScreen | FR-030 | — |
| 8 | AnalysisScreen | FR-025・FR-026・FR-027・FR-032・FR-042(概要 KPI 4 項目) | — |
| 9 | KarteScreen(2 ルート: pitcher / batter) | FR-025・FR-026(個人分析)・FR-028・FR-029 | — |
| 10 | ComparisonWorkspacesScreen | FR-041・FR-042(共有側) | — |
| 11 | TeamScreen | FR-015(通常登録)・FR-017・FR-039 | FR-018(セルフ削除) |
| 12 | CsvImportScreen | FR-038(88 列取り込み — 要件の全件移行とは範囲が違う) | — |
| 13 | HelpScreen | (対応 FR なし — 静的ガイド) | — |

**画面表面を持たない / 旧 SPA に画面が存在しない FR**: FR-014(規則設定画面が旧に無い — 終了規則は domain 焼き込み)/ FR-034(API の認可契約 — 全画面横断)/ FR-035・FR-037(旧 SPA に管理画面なし)。以上で **42 FR すべて**が「いずれかの画面」または「画面表面なし」に割り当てられている。

---

## 3. 突合 — FR × 旧 SPA 充足度

### 3-0. 判定基準(2026-09-02 確定 — 本節の全行に適用)

**部品の有無ではなくユーザーストーリー(受入基準)の充足で判定する。**

| 判定 | 定義 |
| --- | --- |
| **○** | 当該 FR の受入基準の**全条項**が旧実装で照合できた |
| **△** | 対応する実装は在るが、**照合できない条項**または**要件と食い違う挙動**が残る |
| **×** | FR が要求する能力に対応する実装が無い、**または**旧実装が要件と正反対で流用の起点にならない(例: FR-019 の物理削除) |

- 優先度 **Should** の FR(FR-018・032・040 等)は**その Should の受入基準**で照合する(Must 条項を持たない FR に Must 充足を求めない)
- 受入基準内の **(Could)** 条項は照合結果を記録するが**降格の根拠にしない**
- ○ 判定行の条項単位の照合記録は **§3-2**(台帳 H-59 の照合規律 — 照合した条項を列挙してから合否を述べる)

| FR | 旧 SPA の対応物 | 判定 | 差分の要点 |
| --- | --- | --- | --- |
| FR-001 試合の開始 | `LineupScreen` mode=new | △ | スタメン・試合情報入力は在る。**オフライン専用の挙動は無い**: オフライン検知は frontend 全体でヒット 0 件(検索式: `grep -rn 'navigator.onLine\|offline' frontend/src` = 0)。作成失敗は汎用トースト「試合作成に失敗しました」のみ(`LEGACY:frontend/src/screens/LineupScreen.tsx:274-275`)。作成はキュー対象外(キュー投入は確定 POST の失敗時のみ — `LEGACY:frontend/src/lib/syncPolicy.ts:64-72`)で SW も /api/* は network-only のため、**結果としてオフラインでは作成できないが「オンライン必須」の明示は無い** |
| FR-002 毎球の投球情報入力 | `StrikeZone`(263)・`StanceGrid`・`PitchTypeChips`・`SpeedPad` | △ | 入力面は充実。ただし**必須未入力の明示がサーバー 422 依存**で、要件の「不足項目を明示して確定不可」はクライアント事前検証を要求。**球速の妥当範囲(60〜170)警告は無い**: クライアントは補完のみで範囲検証なし(検索式: `grep -n '170\|範囲' frontend/src/lib/speedInput.ts frontend/src/components/pads/SpeedPad.tsx` = 0)、サーバーは `pitch_speed: Field(0, ge=0, le=999)` の 0〜999 のみ(`LEGACY:api/schemas/models.py:653,748`)。警告+確認で確定可のフローは存在しない |
| FR-003 打撃結果と状況の自動更新 | `ResultPad` + `BaseDiamond` の進塁サジェスト・手動上書き | △ | 手動値優先は照合済み(`LEGACY:frontend/src/components/diamond/BaseDiamond.tsx:238-289`)。**「付録 E どおり」とゴールデンケース全一致は照合不能**(ベクタ未整備 — `REQ:910`)→ △(§3-2) |
| FR-004 走者・特殊プレイ | `PickoffSheet`・`StrategySheet`・`FieldDiagram`・プレス | △ | 捕球選手の座標自動推定 + 修正まで実装済み(`LEGACY:frontend/src/lib/fielder.ts:1-34`)。**特殊プレイの状態効果の付録 E 検証は照合不能**(同上)→ △(§3-2) |
| FR-005 スコア・アウト・イニング自動計算 | `MiniScoreboard`・`CountDisplay` | △ | **断中のクライアント計算による画面更新は不可**(§2-4)。**「X」表記は無い**(検索式: `grep -rn '"X"' frontend/src api services reports domain/scoreboard.py` のスコア文脈ヒット 0)。**終了時の入力ロックは在る**(client: `LEGACY:frontend/src/screens/GameScreen.tsx:944` / server: 400「試合終了後に新しいプレイは追加できません。訂正する場合は1球戻してください」`LEGACY:api/routers/plays.py:298`)。**終了宣言の促しも在る**(バナー「試合終了 — 入力は無効です(メニュー→入力終了 で回収・終了)」`LEGACY:frontend/src/screens/GameScreen.tsx:2332-2334` + トースト `:1255`)。ただし**終了条件成立で game_status は自動的に「試合終了」へ遷移する**(`LEGACY:domain/game_end_rules.py:4-20` の `should_finish_game` → `LEGACY:api/routers/plays.py:283`)— 宣言(`finish_game` = `LEGACY:api/routers/games.py:643`)はライフサイクル終了として別に存在する |
| FR-006 undo | `DELETE /plays/last`(1 段) | △ | **未同期があると undo 不可**。要件の「常に取消イベントがキューに積まれる」(`REQ:226`)と設計が逆。**空履歴時の提示は在る**: サーバーが `no_plays`「取り消すプレイがありません」を返し(`LEGACY:api/routers/plays.py:406,418`)、クライアントは detail.message をトースト表示・状態は変えない(`LEGACY:frontend/src/screens/GameScreen.tsx:1367-1371`) |
| FR-007 記録済みプレイの修正 | 直前修正 + 過去修正 + `PlayEditImpactSheet` | △ | 差分プレビューの中身は要件 G-7 が未定義な部分まで具体化(実装先行 — `LEGACY:frontend/src/components/game/PlayEditImpactSheet.tsx:80-206`)。**しかし 7 条項中 4 条項が不成立**: 任意位置への挿入なし・任意行の削除なし・記録権前提が成立しない・「進行中に戻す」操作なし(§3-2)→ △ |
| FR-008 試合の再開 | `resumeGame` | ○ | スコア・走者・打順・カウントの 4 項目とも state で復元される(`LEGACY:api/routers/games.py:513-522`・`LEGACY:api/schemas/play_row.py:366-395` — §3-2 で条項照合済み) |
| FR-009 タイブレークの開始 | `TiebreakSheet`(10〜15 回・走者配置・先頭打者・開始アウト — `LEGACY:frontend/src/components/game/TiebreakSheet.tsx:189-384`) | △ | **断中の操作(キューに積む)は不可**(§2-4) |
| FR-010 試合の終了 | `finishGame`(未同期回収を伴う — `LEGACY:frontend/src/screens/GameScreen.tsx:1500-1509`) | △ | **断中の終了宣言・指定文言の警告・試合一覧の未送信バッジは無い** |
| FR-011 選手交代 | `LineupScreen` change + `SubstitutionSheet`(臨時代走) + `HistoricalSubstitutionSheet` | △ | 遡及修正まで実装済み。**9 ポジション検証は在るが要件と逆方向**: 試合作成時はサーバーが 422 `invalid_lineup_positions`「守備2〜9とDHまたは投手を重複なく1人ずつ設定してください」で**ブロック**(`LEGACY:api/routers/games.py:131-158`。全欄空なら素通し `:134-136`)。交代時はクライアントが**重複のみ**検出して確定ボタンを無効化(`LEGACY:frontend/src/screens/LineupScreen.tsx:927-934,1430`)— **不足の検出は無い**。要件の「警告(ブロックしない)」形はどちらにも無い。**未登録選手のその場登録も無い**: 「名簿にない背番号は氏名なしで保存されます」の警告で登録せず素通し(`LEGACY:frontend/src/screens/LineupScreen.tsx:1481-1486`) |
| **FR-012 通信断中の記録継続と自動同期** | 部品(SW・IndexedDB・キュー・べき等キー)はあるが用途が違う | **×** | **受入条件「オフラインで記録を続けられる」を満たす実装が無い**(存在する部品: SW `LEGACY:frontend/public/sw.js:69-95` / IndexedDB `LEGACY:frontend/src/lib/indexedDbStorage.ts:3-6` / 耐久キュー `LEGACY:frontend/src/stores/syncStore.ts:15-21` / べき等キー `LEGACY:frontend/src/lib/captureMetadata.ts:18-44`)。未送信 1 件で全入力ブロック(`LEGACY:frontend/src/screens/GameScreen.tsx:1833-1846`)。未送信件数の常時表示・送信内容の通知・(a)編集して再送/(b)破棄の 2 択・閾値 350 の警告・E3(非所有タブ)・永続ストレージ拒否の警告 — **いずれも無い** |
| **FR-013 記録権(入力ロック)** | 無し | **×** | **意味要素(付与・世代・引き継ぎ・読み取り専用化)のいずれにも対応実装が無い**(検索式と要素別の不在根拠は §2-4。ヒットは名簿ロック 3 件のみ = `LEGACY:db/team_management_repo.py:105,332,441`)。通常引き継ぎ・緊急引き継ぎ・退避イベントの取り込み — 全て新規 |
| **FR-014 試合規則の設定と適用** | `GameKindSettingsContent`(localStorage の候補名のみ — `LEGACY:frontend/src/components/settings/GameKindSettingsContent.tsx:12-52`) | **×** | **規則セット(規定イニング・コールド・延長上限・DH 制)の設定は無い**(検索式: `grep -rn 'コールド\|延長上限\|規定イニング' frontend/src api` = 0)。終了規則は domain 関数への焼き込み(`LEGACY:domain/game_end_rules.py:12-25`)で、大会名ごとの規則セット・試合単位上書き・適用規則のスナップショット保存は無い |
| FR-040 状態補正イベント | `StateOverrideSheet`(`LEGACY:frontend/src/components/game/StateOverrideSheet.tsx:334-519`) | △ | 上書き UI は在るが、要件は**現行の「履歴に残らない直接上書き」を改善**すると明記(`REQ:337`)。イベント化・差分履歴・undo 対象化は新規 |
| FR-015 選手の登録 | `TeamScreen`(1 名 / 一括 / 編集 / プロフィール / 測定履歴) | △ | 充実。**試合中のその場登録は無い**: GameScreen・交代シート・LineupScreen に選手登録の導線 0(検索式: `grep -rn 'addPlayer\|選手を登録\|選手を追加' frontend/src/screens/GameScreen.tsx frontend/src/components/game/ frontend/src/screens/LineupScreen.tsx` = 0。`addPlayer` の呼び出し元は TeamScreen のみ = 登録フォームの実体は `LEGACY:frontend/src/screens/TeamScreen.tsx:1280-1368` にしか無い)。断中の一時 ID 生成は同期機構が無いため成立しない |
| FR-016 スタメンの記憶・復元 | `getStamem` による自動復元(保存はサーバー側の暗黙処理) | △ | 復元は在るが**背番号ベース**: stamem の実体は poses/names/nums/lrs の配列(`LEGACY:api/schemas/models.py:463-467`・`LEGACY:db/game_repo.py:916-934`)で、要件の**選手 ID ベースではない**(改名・背番号変更に追従しない)。**非現役枠の提示も無い**: 名簿一覧 API は active のみ返す(`LEGACY:db/player_repo.py:1196` 以下が active 条件)ため非現役の背番号は「未登録」と同じ見え方になり、**「差し替えが必要」という専用の提示は存在しない**(復元処理に区分チェック無し — `LEGACY:frontend/src/screens/LineupScreen.tsx:1633-1662`) |
| FR-017 在籍ステータス管理 | `bulk-deactivate`(プレビュー→確定)/ `bulk-reactivate`(`LEGACY:api/routers/team_management.py:143-234`) | △ | プレビュー→確認→実行は実装済み。ただし**旧は active/inactive の 2 値**で、要件の 3 区分(現役/その他/OB)ではない |
| **FR-018 誤登録選手のセルフ削除** | 無し | **×** | SPA に導線も API も無い(検索式: `grep -n '@router' api/routers/teams.py` に DELETE ルート 0 本。`player_repo.delete_player` の呼び出し元は Streamlit 管理画面のみ `LEGACY:app/pages/admin.py:364`) |
| **FR-019 試合の削除とゴミ箱** | 物理削除のみ | **×** | **× の根拠は「逆実装」**(§3-0: 旧実装が要件と正反対で流用の起点にならない): 削除は `DELETE FROM play_player_link/play_data/game` の物理削除(`LEGACY:db/game_repo.py:2750-2781`)で、論理削除・ゴミ箱・復元の痕跡 0(検索式: `grep -rniE 'deleted_at|is_deleted|soft.?delete|restore_game'` = 0)。**絶対規則「物理削除しない」に正面から違反**。ゴミ箱・30 日復元・期限日付の明示は全て新規 |
| FR-039 対戦相手チームレコード | `TeamScreen` 対戦相手タブ + `team_catalog` | △ | 登録・編集は在る。**試合作成中のその場登録は形を変えて在る**: 作成画面の「手入力」トグルで自由入力チーム名を許し(`LEGACY:frontend/src/screens/LineupScreen.tsx:1883-1893`)、サーバーが `ensure_team` で名前一意のチームを作成/再利用する(`LEGACY:api/schemas/play_row.py:131`・`LEGACY:db/player_repo.py` の `ensure_team` = INSERT OR IGNORE。コメントに「one-off free-text opponent flow」`LEGACY:api/routers/games.py:252-254`)。**ただし team_catalog への相手登録は伴わない**(catalog 紐付けは POST /teams/opponents のみ)ため次回の「登録済みの相手」には出ない。**類似名警告は無い**(検索式: `grep -n '類似\|similar' api/routers/teams.py` = 0。duplicate 検出は背番号のみ `:136,199`)。**リネーム誘導も無い**(チーム削除 API 自体が SPA/API に存在せず、「削除不可→リネームへ誘導」の UI は無い。検索式: `grep -rn 'リネーム\|rename' frontend/src api` の該当 0) |
| FR-020 スコアボード表示 | `MiniScoreboard`(イニング別 + R/H/E) | △ | **要件は H/E/K/B**。旧の**画面表示**は R/H/E で K/B が無いが、**state は H/E/K/BB を持つ**(score リストの 12〜15 番目 — `LEGACY:api/schemas/play_row.py:379-390`。三振 = `STRIKEOUT_RESULTS`・四死球 = `WALK_RESULTS` — `LEGACY:domain/scoreboard.py:7-8`)。**要件書に無い H/E/K/B の定義(G-15)の事実上の正が旧実装に存在する** — 後続タスク B の材料。最終反映時刻・断中の追従表示は無い |
| FR-021 投手成績のリアルタイム表示 | `LiveInputBar` 投手カード(`LEGACY:frontend/src/components/game/LiveInputBar.tsx:161-199`) | △ | 当日成績・被打率・対左右・直球平均・球種割合は在る。**WHIP・FIP が無い**(検索式: `grep -rniE 'whip|\bfip\b' frontend/src api charts` = 0 — 実装は Streamlit 専用の `LEGACY:analytics/cal_stats.py:101-110` のみで API から未接続)。FIP 注記・期間ラベル・断中注記も無い |
| FR-022 打者成績のリアルタイム表示 | `LiveInputBar` 打者カード(現打者・次打者) | △ | **当日打席結果は表示名の羅列のみ**: サーバーは `results: string[]`(打席結果の表示名。0/空を除外した一次元配列)しか返さず(`LEGACY:api/routers/stats.py:947-955`)、UI も `today.results.join('・')` の 1 行テキスト(`LEGACY:frontend/src/components/game/LiveInputBar.tsx:90`)。**v2.2 が確定した 7 列構造(打席番号 / イニング / 結果表示名 / 打数算入 / 安打種別 / 打点 / 出塁の別)は存在しない** |
| FR-023 球種分布の表示 | `LiveInputBar` の今季球種割合ドーナツ | △ | **割合のみで球数併記なし**(凡例は `{label} {percentage}%` — `LEGACY:frontend/src/components/game/LiveInputBar.tsx:182,192`)。**断中のクライアント追従も不可**(§2-4)→ △(§3-2) |
| **FR-024 試合開始時のプリフェッチ** | 無し(react-query のキャッシュのみ) | **×** | 断中参照を前提とした先読みは無い(検索式: `grep -rn 'prefetch\|先読み\|preload' frontend/src` = 0) |
| FR-025 投手分析 | `AnalysisScreen` 投手タブ + カルテ | △ | 5 図表すべて相当物あり。ただし**形態が違う**(コース分布は 3×3 と 37×37 密度で、旧 Streamlit の等高線でも要件の二択でもない)。**母数併記は在る**(各カードに n= バッジ `LEGACY:frontend/src/components/analysis/player/PlayerAnalysisPanels.tsx:63,71,80` / 球種別・カウント別・球速帯別も対象数併記 `:153,162,191`)。**集計範囲ラベルも在る**(表示区分バー: シーズン・対戦相手・期間〔既定「全期間」〕 `LEGACY:frontend/src/screens/KarteScreen.tsx:299,309`) |
| FR-026 打者分析 | `ZoneHeatmap`(3×3)+ `BattedBallSpray`(`LEGACY:frontend/src/components/analysis/player/PlayerAnalysisPanels.tsx:247-271,618-647`) | △ | **打率マップは 3×3 のみ**(Streamlit の 13 分割は SPA に無い)。**打球方向は散布のみで、要件の「等角 5 分割」集計が無い** |
| FR-027 作戦分析 | `StrategyDashboard`(状況別 / 盗塁 / バント) | △ | 母数(件数一覧)併記あり。内部集計は 11 分類のイベント件数のみ(`LEGACY:charts/batting/analyse_strategy.py:47-112,132-159`)。**しかしカテゴリが frozenset で固定**(`LEGACY:api/strategy_service.py:24-27`)のため**チーム追加の作戦は集計対象にならず**、成否の付録 A-4 定義との一致も照合不能(§3-2)→ △ |
| FR-041 共同分析グループ | `ComparisonWorkspaces` + `LEGACY:api/analysis_workspace_service.py` | △ | 骨格は在る(招待コード 160bit・ハッシュ保存・72h・1 回消費、既定すべて非共有、最後の admin は退出不可、TOCTOU 対策、非参加は 404)。**ただし粒度が 4 フラグ**(`share_profile` / `share_performance` / `share_identified` / `allow_export`)で要件は 3 粒度。**同時比較上限・比較対象の選択・共有集計エクスポートが無い**(`allow_export` はフラグだけで未行使)。共有分析は**全期間固定でフィルタを持たない** |
| FR-042 チーム単位の分析 | `performance_summary`(W/L/D・得失点・打撃・投球) | △ | **イニング別得点・失点が無い**。**付録 A-5 の 7 項目との照合結果**: 自チーム分析の overview が持つのは 試合数・得点・失点・得失点差 の 4 項目のみ(`LEGACY:api/analysis_summary.py:506-512`)。**勝・敗・分の通算値は無く**、試合別の 勝/敗/分 ラベル(`:447`)が直近 12 件の trends に付くだけ。通算 W/L/D の集計は共有側 `_performance_summary` にのみ存在する(`LEGACY:api/analysis_workspace_service.py:419-434`) |
| FR-028 カルテの閲覧・所見編集 | `KarteScreen` + `NotesEditor`(楽観ロック — `LEGACY:frontend/src/screens/KarteScreen.tsx:129-219`) | △ | 競合検出・母数・範囲ラベル・既定全期間は照合済み(`:299,309`)。**A-3b の指標セットを満たさない**(打者カルテ必須の**打球方向〔等角 5 分割〕が旧に無い** — FR-026 行)→ △(§3-2) |
| FR-029 カルテ PDF の出力 | `/stats/karte-reports/{kind}`(headless Chrome) | △ | 一括出力は在る。**進捗表示は無い**: 一括生成は同期 1 リクエスト(GET → Response — `LEGACY:api/routers/stats.py:303-350`)でクライアントは fetch 待ちのみ(検索式: `grep -n '進捗\|progress\|スキップ\|skip' frontend/src/components/analysis/AnalysisExportSheet.tsx` = 0)。**「◯名はデータなしのためスキップ」通知も無い**: `min_pa` 未満は黙って対象外になるだけ(`LEGACY:api/karte_service.py:1308,1386`)。**在籍区分オプションも無い**: 対象は名簿の在籍区分ではなく**プレイ記録行から役割別に抽出**(`LEGACY:api/karte_service.py:158` の `_role_rows`。UI に現役/全区分の選択なし)。**NFR-023 の限定条項(PDF レンダラの外部リソース・ローカル参照の無効化)**: 生成 HTML は自己完結で外部参照 0(検索式: `grep -n 'http\|cdn\|<link\|<script' reports/pitcher_karte_html_pdf.py` の外部 URL 0 件)、入力は file:// のローカル一時ファイル(`LEGACY:reports/pitcher_karte_html_pdf.py:1354,1366-1369,1390`)。Chrome 起動フラグは `--disable-background-networking` 等(`:1357-1403`)だが**ページ自身の外部取得やローカルファイル参照を遮断する明示的フラグは無く**、無害性は生成 HTML が外部参照を含まないことに依存する |
| FR-030 スコアカード | `ScoreCardScreen` + `/scorecard.pdf` | △ | 表示・PDF・着色は在る。**選手交代の経過は出力されない**(検索式: `grep -n '交代\|substitution' api/scorecard_service.py` = 0)、**「X」表記も無い**(ステップ 1)→ △(§3-2)。一次調査の「交代経過まで実装済み」は誤りだったため訂正 |
| FR-031 毎球データの CSV 出力 | `/exports/plays-csv`・`/games/{id}/plays.csv` | △ | 88 列・BOM 付き UTF-8 は照合済み。**88 列 CSV に数式インジェクション無害化は無い**(serialize は正規化+BOM のみ — `LEGACY:api/play_csv_export_service.py:52-89`。一次調査の「対策済み」は**フロント生成の分析 CSV**〔`LEGACY:frontend/src/lib/analysisCsv.ts:103-115`〕との取り違えで誤り)。**交代履歴等の別ファイル方式も無い** → △(§3-2) |
| FR-032 分析資料の PDF 出力 | `/stats/analysis-reports/*` | △ | **集計は画面と同一のサービス層を共用**: 打者分析 PDF は `api.karte_service.build_karte_detail` を、投手分析 PDF も `api.karte_service` を経由してデータを得る(`LEGACY:api/batter_analysis_report_service.py:10`・`LEGACY:api/analysis_report_service.py:10`)。**描画は reportlab の別実装**(`LEGACY:reports/batter_analysis_pdf.py:9-11`)であり、「同一定義」は集計層の共用で担保され描画層では担保されない。**チャート単位の母数併記の全数照合は未実施のため Should 基準でも照合不能条項が残る**(§3-2)→ △ |
| FR-033 チームログイン | `LoginScreen` | △ | **レート制限は無い**(検索式: `grep -rn 'rate\|attempt\|lockout\|試行\|連続' api/routers/auth.py` = 0・`grep -rn 'slowapi\|limiter\|RateLimit' api/main.py api/deps.py` = 0)。要件側も閾値・ロック時間は 10 章の未決 |
| FR-034 データ所有権制御 | 404 / 403 の使い分け | △ | **要件違反**。試合は一律 404(存在秘匿のコメントあり)だが、**チーム/選手系は 404 `team_not_found` と 403 `forbidden_team` を使い分けており、チーム ID の存在有無が外部から判別できる**。要件は存在秘匿(単一リソース名指しは 404・理由コードを返さない — `REQ:594-595`)で統一(判定の典拠: `LEGACY:api/main.py:61-77`〔試合は一律 404〕・`LEGACY:api/routers/teams.py:84-93`〔チームは 404/403 を使い分け〕) |
| **FR-035 システム管理者機能** | SPA に無し(Streamlit のみ) | **×** | SPA/API に管理画面なし(検索式: `grep -rn 'DB_ADMIN_PASSWORD' api/` = 0。実在は `LEGACY:app/pages/admin.py:76-449` のみ)。Streamlit 版は所有者スコープ無し。選手統合・分割・操作ログ・退避イベントは概念ごと無い |
| FR-036 チームパスワードの変更 | `SettingsSheet` アカウントタブ | △ | 現行 PW 必須・トークン全経路失効は照合済み。**変更日時の記録なし**(検索式: `grep -n 'changed_at\|日時' api/routers/auth.py` = 0)、**ポリシーは長さのみで「英字と数字を必ず含む」が無い**(`LEGACY:api/schemas/models.py:127-134`)、**管理者リセットの復旧経路なし**(管理者機能自体が無い — §2-6)→ △(§3-2) |
| **FR-037 管理コンソール** | SPA に無し | **×** | ルート表(16 件)に管理系パスが無く(`LEGACY:frontend/src/App.tsx:55-165`)、`api/` に管理者認証の参照 0(検索式: `grep -rn 'DB_ADMIN_PASSWORD' api/` = 0)。要件の一覧・語彙マスタ・設定値・操作ログ・制御資源表示に対応する画面が存在しない |
| FR-038 既存データの一括移行 | `CsvImportScreen`(88 列契約 — `LEGACY:frontend/src/screens/CsvImportScreen.tsx:35-46`・`LEGACY:services/csv_import.py:30-33,187`) | △ | 取り込み機構は堅牢。ただし要件の移行は**旧 DB 全件移行**で、CSV 取り込みは範囲が違う。名寄せの人手介入 UI は要件側も未定義(§1-3) |

### 3-1. 集計

**確定値(2026-09-02・§3-0 の基準による再判定後)**:

| 判定 | 件数 | FR |
| --- | --- | --- |
| ○ 受入基準の全条項を照合できた | **1** | FR-008 |
| △ 実装は在るが、照合できない条項または要件と食い違う挙動が残る | **33** | FR-001〜007・009〜011・015〜017・020〜023・025〜034・036・038〜042 |
| × 受入条件を満たす実装が無い、または逆実装 | **8** | FR-012・013・014・018・019・024・035・037 |

一次判定は ○ 11 / △ 23 / × 8 だった。条項単位の照合(§3-2)で 10 件が △ へ降格した。

> 集計は §3-0 の基準による再判定後の値(確定はステップ 4)。要件書側が受入条件を持たない項目(§1-3 の 20 件)は判定を確定できないため △ に寄せている。

### 3-2. ○ 判定行の条項単位照合(2026-09-02・台帳 H-59 の照合規律)

一次判定 ○ の 11 行について、受入基準を条項単位で照合した(ステップ 1〜2 の実査で ○ 候補へ昇格した行は無い)。**合** = 旧実装で照合できた / **否** = 不成立 / **照合不能** = 検証手段が無い・本調査で突合未実施。

**FR-003(Must)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 付録 E どおりの自動設定 | 照合不能 | 実装は在る(サーバー状況計算 + 進塁サジェスト `LEGACY:frontend/src/components/diamond/BaseDiamond.tsx:57-83`)が、付録 E ゴールデンベクタが未整備(`REQ:910`)で本調査でも全数突合未実施 |
| 手動値優先 | 合 | 走者ポップオーバーの上書き +「自動提案に戻す」(`LEGACY:frontend/src/components/diamond/BaseDiamond.tsx:238-289`) |
| ゴールデンケース全一致 | 照合不能 | 同上(ベクタ未整備) |

**FR-004(Must)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 盗塁成功 → 塁更新・集計対象 | 合 | `LEGACY:frontend/src/components/game/StrategySheet.tsx:50-181`・集計 `LEGACY:api/strategy_service.py:61-65` |
| 打球位置座標 + 捕球選手の自動推定・修正可 | 合 | `LEGACY:frontend/src/lib/fielder.ts:1-34`・`LEGACY:frontend/src/components/field/FieldDiagram.tsx:43-49,156-178` |
| 特殊プレイの状態効果 = 付録 E 対象・テーブル駆動検証 | 照合不能 | ベクタ未整備(`REQ:910`) |

**FR-007(Must)→ △ 降格(7 条項中 4 条項が不成立)**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 幻の得点/アウトを生まない | 照合不能 | 下流再計算 + `blocking_issues` は在る(`LEGACY:frontend/src/components/game/PlayEditImpactSheet.tsx:181-194`)が保証の検証手段なし |
| 交代イベント時点の保持 | 照合不能 | 本調査で個別検証未実施 |
| 終了済み試合の修正 + 自動再集計 | 部分合 | 終了後も過去修正可(`LEGACY:frontend/src/lib/gameInputLock.ts:16-29` の historicalEditActive)。事前集計テーブル相当は旧に無い |
| **任意位置への挿入** | **否** | 挿入ルート無し(検索式: `grep -n '@router\.' api/routers/plays.py` に insert 系 0。DELETE は `/plays/last` のみ) |
| **プレイ行の削除(論理削除)** | **否** | 任意行の削除ルート無し。undo は末尾 1 行の物理 DELETE(`LEGACY:db/game_repo.py:2646-2650`) |
| **記録権保持端末のみ + キュー空前提** | **否** | 記録権が存在しない(§2-4)。キュー空前提のみ実装(未同期時の全ブロック)されているが要件の形ではない |
| **再開が終了ロックを解除** | **否** | resume はセッション復元のみ(`LEGACY:api/routers/games.py:513-522`)。「進行中に戻す」操作は無い(検索式: `grep -rn '進行中に戻す\|reopen' frontend/src api` = 0) |

**FR-008(Must)→ ○ 維持**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 試合一覧から再開 → スコア・走者・打順・カウントが最終プレイの状態で復元 | 合 | `POST /games/{id}/resume` → `row_to_game_state` が score(イニング別 + H/E/K/BB 含む)・outs/strikes/balls・inning/half・batter.order・走者を返す(`LEGACY:api/routers/games.py:513-522`・`LEGACY:api/schemas/play_row.py:366-395`)。生きたセッションを DB スナップショットで巻き戻さない規律つき |

**FR-023(Must)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 割合 + 球数の併記 | **否** | 凡例は `{label} {percentage}%` のみ(`LEGACY:frontend/src/components/game/LiveInputBar.tsx:182,192`) |
| 断中のクライアント計算で追従 | **否** | 未送信 1 件で入力・表示更新の前提が崩れる(§2-4)。当日集計はサーバー取得 |

**FR-027(Must)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 走者状況別の傾向と結果(成否は付録 A-4)を母数併記で集計 | 部分合 | 件数一覧の常時併記は在る。**成否の付録 A-4 定義との一致は照合不能**(旧の判定表 `LEGACY:charts/batting/analyse_strategy.py:47-112` と A-4 の突合未実施) |
| チーム追加の作戦が傾向集計の対象になる | **否** | カテゴリが frozenset で固定(`LEGACY:api/strategy_service.py:24-27`・`LEGACY:charts/batting/analyse_strategy.py:20-26`)。追加語彙は集計に現れない |

**FR-028(Must)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 統計サマリー = 付録 A-3b・母数併記・集計範囲ラベル必須・既定全期間・同一フィルタ | **否** | 母数(n=)・範囲ラベル・既定「全期間」・同一フィルタは合(`LEGACY:frontend/src/screens/KarteScreen.tsx:299,309`)。**A-3b が打者カルテに必須とする打球方向(等角 5 分割)が旧に無い**(`REQ:1129-1130`・§3 FR-026 行)ため指標セット不一致 |
| 楽観ロック(先発の内容が黙って消えない) | 合 | 409 `karte_note_conflict` + 下書き保持(`LEGACY:frontend/src/screens/KarteScreen.tsx:129-219`) |
| (Could)所見履歴 10 世代 | 照合不能 | 旧に履歴機構の確認未実施(Could のため降格根拠にしない) |

**FR-030(Must)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| イニング別経過・打席結果・投手成績 + **選手交代の経過** | **否** | 前 3 者は在る(`LEGACY:api/scorecard_service.py:150-195`)が**交代の経過は出力されない**(検索式: `grep -n '交代\|substitution' api/scorecard_service.py` = 0) |
| 終了の形の表記(裏なしは「X」) | **否** | X 表記なし(ステップ 1 の検索式) |
| 紅白戦の出力 | 照合不能 | 未実施 |
| 移行試合の交代「不明」許容 | 対象外 | 旧に移行概念なし |
| (Could)勝敗投手・セーブの手動指定 | 否(Could) | 該当 UI なし |

**FR-031(Must)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 88 列互換の全プレイ行 | 合 | `LEGACY:api/play_csv_export_service.py:81-89` |
| 数式インジェクション無害化 | **否** | serialize は列正規化 + BOM のみ(`:52-89`)。無害化実装は**フロント生成の分析 CSV**(`LEGACY:frontend/src/lib/analysisCsv.ts:103-115`)にしか無い |
| BOM 付き UTF-8 | 合 | `utf-8-sig`(`:89`) |
| (補足=本質要件)交代履歴等の別ファイル方式 | **否** | サイドカー出力なし |

**FR-032(Should)→ △ 降格**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 分析画面と同一定義のチャート(範囲ラベル・母数入り)の PDF | 部分合 | 集計はサービス層共用(`LEGACY:api/batter_analysis_report_service.py:10`)・「全期間」ラベルあり(`LEGACY:reports/batter_analysis_pdf.py:185`)。**チャート単位の母数併記の全数照合は未実施** |

**FR-036(Must)→ △ 降格(4 条項中 2.5 条項が不成立)**
| 条項 | 合否 | 根拠 |
| --- | --- | --- |
| 現行 PW 必須 + **変更日時の記録** | 部分否 | 現行 PW 必須は合(`LEGACY:api/routers/auth.py:122-159`)。**変更日時の記録は無い**(検索式: `grep -n 'changed_at\|日時' api/routers/auth.py` = 0) |
| 旧トークンの全経路失効 | 合 | `password_version`(`LEGACY:auth.py:34-36`・`LEGACY:api/deps.py:131-159`) |
| ポリシー = 8 文字以上 + **英字と数字を必ず含む** | **否** | 長さ(8 以上・72 バイト)のみで文字種要件なし(`LEGACY:api/schemas/models.py:127-134`) |
| 管理者リセットの復旧経路 | **否** | SPA/API に管理者機能自体が無い(§2-6) |


---

## 4. 旧に無い要件(= 逐語移植では満たせない範囲)

**優先度順**。① と ② はコア領域(設計書 6.3)。**本表は実装単位の一覧で FR と 1:1 にならない**。突合規則(検査条件): (a) 突合表で **× の FR 全件**が本表のいずれかの項目に現れる (b) 本表に現れる FR は突合表で **× または △(未充足条項あり — 優先度は問わない)**。

| # | 要件 | 関係 FR | 旧の状況 | 重さ |
| --- | --- | --- | --- | --- |
| ① | **通信断中の記録継続と自動同期** | FR-012(×) | オフライン記録継続が無い。未送信 1 件で全入力ブロック | **コア領域**。同期プロトコル(同期設計正本)は設計済みで、旧に移植元が無い |
| ② | **記録権(入力ロック)** | FR-013(×) | 意味要素のいずれにも対応実装が無い。楽観ロックによる後勝ち 409 のみ | **コア領域**。人間の逐行確認必須 |
| ③ | **試合の削除とゴミ箱** | FR-019(×) | 物理削除の**逆実装**。**絶対規則違反** | 論理削除への設計変更はデータモデルに波及 |
| ④ | **システム管理者機能・管理コンソール** | FR-035(×)・FR-037(×) | SPA に無し。Streamlit 版は所有者スコープ無し | 新規設計。選手統合/分割・操作ログ・退避イベント閲覧を含む |
| ⑤ | **試合規則の設定と適用** | FR-014(×) | 試合種別の候補名(localStorage)のみ。終了規則は domain 焼き込み | 付録 F の規則スキーマ + スナップショット保存が新規 |
| ⑥ | **誤登録選手のセルフ削除** | FR-018(×) | 無し | |
| ⑦ | **試合開始時のプリフェッチ** | FR-024(×) | 無し | ① に従属(断中参照が前提) |
| ⑧ | **状態補正の履歴化** | FR-040(△) | 直接上書きのみ | 要件が明示的に「改善」と位置づけ |
| ⑨ | **WHIP・FIP** | FR-021(△)・FR-041(△) | **旧 SPA / 旧 API に実装ゼロ**。Streamlit の `analytics/` にのみ存在し、そこは API から未接続 | 「全面踏襲」の踏襲元が存在しない Must 要件 |
| ⑩ | **打球方向の等角 5 分割集計** | FR-026(△)・FR-028(△ — A-3b 経由) | 散布図のみ。方向分類・割合表が無い | |
| ⑪ | **共有集計エクスポート・同時比較上限・比較対象選択** | FR-041(△) | `allow_export` フラグは定義済みだが未行使。上限も選択も無い | |
| ⑫ | **イニング別得点・失点** | FR-042(△) | 無し | |
| ⑬ | **任意位置へのプレイ挿入・プレイ行の論理削除・「進行中に戻す」** | FR-007(△) | 挿入/任意行削除/再開解除のいずれも無し(§3-2) | 下流再計算の設計に波及 |
| ⑭ | **当日打席結果の 7 列構造** | FR-022(△) | 表示名の羅列のみ | v2.2 で列定義が確定済み |
| ⑮ | **通算 W/L/D と A-5 完全形のチーム分析** | FR-042(△) | overview は 4 項目のみ | |

検査: × 8 件(FR-012・013・014・018・019・024・035・037)は ①〜⑦ に全件現れる。本表に現れる FR は × 8 種 + △ 7 種(FR-007・021・022・026・028・040〜042)でいずれも突合規則 (b) を満たす。

### 4-1. 「旧に無い」ではなく「旧が要件と逆」の箇所(より危険)

移植すると要件違反になる。**気づかずに写すと静かに壊れる**類。

| 箇所(関係 FR) | 旧の実装 | 要件 |
| --- | --- | --- |
| 試合削除(FR-019) | 物理削除(`DELETE FROM game`) | 論理削除(絶対規則・要件書 4.0-2) |
| テナント分離の応答(FR-034) | チーム/選手系は 403 `forbidden_team` と 404 `team_not_found` を使い分け → **存在が判別できる** | 存在秘匿 — 単一リソース名指しは 404・理由コードなし(`REQ:594-595`) |
| 未同期時の挙動(FR-012) | 入力を全面ブロック | 記録を続けさせる。未送信件数を常時表示(`REQ:290`) |
| undo(FR-006) | 未同期があると実行不可 | 常に取消イベントがキューに積まれる(`REQ:226`) |
| 状態補正(FR-040) | 履歴に残らない直接上書き | イベントとして履歴に残す(`REQ:337`) |
| 球種の系統(4.0-3・FR-027 の作戦語彙も同型) | 分析コードにハードコード | ハードコード禁止(`REQ:168`) |
| ツーシーム・シュート(付録 D-4) | 落ち系に誤分類 | 直球系(`REQ:1214`) |

---

## 5. 旧にあるが要件書に無いもの(= 踏襲/破棄の PO 判断が要る)

| # | 旧 SPA の機能 | 典拠 | 論点 |
| --- | --- | --- | --- |
| 1 | **個人アカウント(入力者)ログイン** — チーム単位とは別に `user_account` で `role='scorer'` としてログインできる | `LEGACY:api/routers/auth.py:78-114`・`LEGACY:frontend/src/screens/LoginScreen.tsx:126-149` | 要件書は「**個人アカウント・入力者の識別を持たない**」を Won't にしている(`REQ:88`)。**旧は既に実装済み**。全面踏襲の射程に入るか PO 判断 |
| 2 | **臨時代走**(塁選択 → サーバー判定済み候補 → プレビュー → **審判承認チェック必須** → 開始/終了) | `LEGACY:frontend/src/components/game/SubstitutionSheet.tsx:62-403` | FR-011 に該当条項なし |
| 3 | **公式記録レビュー**(責任投手・打点・自責の仮判定 + 86 種の理由コード) | `LEGACY:frontend/src/components/game/OfficialScoringReviewSheet.tsx:19-90` | 自責点・防御率は **Won't 維持**が既決。ただし「**稼働中の読み取り専用レビュー表示の扱いは PO 裁定事項として未決**」と記録あり(`docs/features/req-v2-legacy-parity/research.md:22`)。**この未決が本調査で再度顕在化した** |
| 4 | **ショートカットの録画式再割当**(結果/球種/画面操作。衝突検出・数字キー拒否) | `LEGACY:frontend/src/components/game/ShortcutSettingsSheet.tsx:29-70` | FR-002 の Could が「キーボードショートカット」を例示止まりにしている(G-2)。旧は完全実装 |
| 5 | **コース入力の視点切替**(捕手側 / 投手後方。保存値は常に捕手側へ変換) | `LEGACY:frontend/src/lib/courseInputView.ts:11-27` | 要件書に記載なし。**ただしこのファイルは既に逐語移植済みで NFR-018 (c) 例外表の唯一の対象**(`REQ:904-906`) |
| 6 | **球速の下 2 桁クイック入力**(35→135 の補完) | `LEGACY:frontend/src/lib/speedInput.ts:46-50` | 要件書に記載なし |
| 7 | **入力用途トグル**(動画確認 / 試合中 — 表示情報だけを切替) | `LEGACY:frontend/src/components/settings/InputWorkflowModeToggle.tsx:17-67` | 要件書に記載なし |
| 8 | **試合中のカルテ追記**(`QuickKarteNoteSheet`) | `LEGACY:frontend/src/components/game/QuickKarteNoteSheet.tsx:56-80` | FR-028 は分析画面からの編集のみ |
| 9 | **旧名簿の自チーム claim**(legacy-unclaimed / legacy-claim・背番号衝突検出付き) | `LEGACY:api/routers/team_management.py:236-285` | FR-038 の移行と関係するが要件書に条項なし |
| 10 | **選手の比較用プロフィール・測定履歴**(生年・野球開始年・測定日・出典・品質 valid/estimated/suspect) | `LEGACY:frontend/src/screens/TeamScreen.tsx:191-349` | FR-041 の `プロフィール` 共有粒度は **10 章で未決**(`REQ:505`) |
| 11 | **カルテ配色テーマ**(チーム単位・パレット選択) | `LEGACY:api/routers/team_management.py:89-121` | 要件書は **Won't**(`REQ:96`)。ただし上流ではさらに `TeamKarteThemeSheet.tsx` が追加されている |
| 12 | **一括レポート**(表紙 → チームスタッツ → 作戦分析 → 投手 → 打者 の PDF マージ、PPTX 化) | `LEGACY:api/combined_analysis_report_service.py:28,36` | PPTX は **暫定 Won't**(`REQ:94`) |
| 13 | **PPTX 出力**(投手分析) | `LEGACY:api/routers/stats.py:353-405` | 同上 |
| 14 | **CSV 取り込み**(`legacy` / `system` の 2 モード) | `LEGACY:frontend/src/screens/CsvImportScreen.tsx:35-46` | FR-038 は DB 全件移行で、CSV 取り込みは別機能 |
| 15 | **AI 分析タブ**(「準備中」のプレースホルダのみ。外部送信しない旨を明記) | `LEGACY:frontend/src/screens/AnalysisScreen.tsx:355-383` | 機能実体なし。踏襲不要と思われるが記録として残す |

### 5-1. Streamlit にあって SPA に無いもの(参考 — 踏襲対象の切り分け)

「旧」を Streamlit まで含めると SPA に無い機能が多数ある。**移植元は SPA なので自動的に対象外**だが、要件充足の判断で「旧にはあった」と誤って数えないために記録する。

WHIP / FIP(`LEGACY:analytics/cal_stats.py`)/ コース別打率 13 分割ゾーン図 / 球速分布の scipy KDE / コース分布の plotnine 等高線 / 打球方向図(ゴロ=破線・フライ=弧・ファール表示)/ 球種割合パイチャート / 過去修正の「この 1 行だけ更新」/ メンバー表のチーム丸ごと遡及反映 / 入力画面内のスコアブックタブ・データ一覧タブ / 手動「DB に同期」ボタン / 試合日時の更新 / 経過時間の Tag 打刻 / DB 管理コンソール一式。

---

## 6. 既決事項との整合

### 6-1. 「全面踏襲」と「逐語移植」は別系統の決定

| 系統 | 決定 | 射程 | 典拠 |
| --- | --- | --- | --- |
| A | **旧システム新機能の全面踏襲**(2026-08-13 PO 決定) | 旧リポ 30 コミット分の**機能** → FR-041/042 新設・Won't 撤回 2 件 | `docs/worklog/2026-08-13-req-v2-legacy-parity.md:16-22`・`REQ:22` |
| B | **Vue へ移植。目標は「完全に同じもの」= 機械的な逐語移植**(2026-08-16 PO 裁定) | 画面の見た目・挙動 | `docs/features/frontend-skeleton/plan.md:24-33` |

TSK-226 はこの 2 系統の交点にあり、**その交点が「未調査」として申し送られていた**(`docs/worklog/2026-08-16-frontend-skeleton.md:91-92`)。

### 6-2. 本調査の結論が抵触する既決事項

| 既決 | 内容 | 本調査との関係 |
| --- | --- | --- |
| **PO 裁定「完全に同じもの」** | 「似せる」のではなく機械的な逐語移植 | **§4-1 の 7 箇所で成立しない**。旧を写すと要件違反になる |
| **ADR-002** | 旧 React コードは**参照資料としてのみ扱い、コード再利用はしない** | 本調査の「新規実装が必要」という結論は ADR-002 と**整合する** |
| **要件書 NFR-018 (c) 例外表** | 逐語移植の除外枠は**閉じた表 1 行**(`courseInputView.ts` の `COURSE_COORDINATE_SIZE`)。追加・削除・失効はいずれも**要件書の改訂を要する** | 「この画面も逐語移植対象」と結論しても、**改訂ゲートを通さない限り例外は成立しない** |
| **ADR-003 の導入順序** | NFR-018 対象計算に触れる実装は**検査基盤 + ベクタの先行確定が着手条件**。「検査基盤の未整備を理由に対象計算のコードを先に追加することはできない」 | **打席入力画面は座標変換を含む**ため、着手前提が既にある |
| **設計書 v1.13** | 製品機能の実装は Phase の対象外。**6.1 の実装計画書ゲート**で進む。順序・群・段階は定めない | 画面移植の順序は各実装計画書の判断 |
| **改善台帳 I-15/I-16/I-17/I-18** | リアルタイム成績・分析画面・座標系・カルテは「**旧を改善する**」側で決着済み(「現行にない新挙動」を含む) | **「旧 SPA で足りている」と結論すると台帳と衝突**。逆に「不足」として新たに数えると二重計上になる |
| **D-9** | 新機能追加は初回リリース後に回す(スコープ肥大防止) | §4 の 12 件が「新機能」に当たるかは PO 判断 |
| **v2.0 design §5** | `scoringReview.ts` は踏襲しない(P0) | §2-5 の裁定により、**論点は `playRules.ts` へ移る** |

### 6-3. 既に決まっているのに未実施の前提条件

本調査の後続作業がここに依存する。

1. **「打席入力画面の逐語移植の受入判定」タスクが未起票** — 要件書 NFR-018 (c) 例外表の「終了証跡」欄が要求(`REQ:906`)。TSK-275(卒業タスク)の着手前提。
2. **NFR-018 (c) 例外表が「有効化待ち」のまま** — 形式上は NFR-018 違反状態が継続(実リスクは TSK-233 のテストで解消済み)。
3. **付録 B-3/B-4 座標変換ベクタが未整備**(TSK-238)。
4. **付録 E ゴールデンケース全表・付録 A 固定ベクタが未整備** — 完成前に NFR-019(a) を合格と判定してはならない。
5. **Playwright(E2E)と visual regression が未導入** — 時期は「**最初の画面移植と同時または直前**」と申し送られている(TSK-225)。
6. **旧 `frontend/` の参照資料としての置き場が未決**(`docs/legacy/` は変更禁止)。
7. **公式記録の読み取り専用レビュー表示の扱いが未決**(v2.1 送り)。

---

## 7. 版固定資料との相違(報告)

`docs/legacy/research/` は `ed6a20f` 時点で **React SPA を扱っていない**ため、多くは「矛盾」ではなく「未収載」。ただし以下は現状に照らして訂正・陳腐化している。

| 資料 | 記述 | `dd03160` の実際 |
| --- | --- | --- |
| `services-shell.md:107` | `user_account` は存在するが「**ログインには使われていない**」 | **個人アカウントログインは実装済み**(`LEGACY:api/routers/auth.py:78-105`) |
| `services-shell.md:20` | `data/game_{id}.json` を Streamlit 固有として説明 | **`LEGACY:db/game_repo.py` のリポジトリ層の副作用**で、API 経由の書き込みでも走る |
| `analytics-reports.md:171,176,177` | カウント別打者成績は PDF 限定 / 対話的可視化はほぼ静的 PNG / 球速帯別成績は画面に無い | **SPA で画面化済み**(`CountPitchMatrix`・`SituationPitchingCard`・`VelocityPerformance`) |
| `input-screen.md` 全体 | Streamlit `game_input.py` のみが対象 | 未同期センター・Service Worker・過去修正プレビュー・臨時代走・公式記録レビューが丸ごと未収載 |

**旧コード内部の矛盾**(移行時に踏みうる): Streamlit の使い方ガイドは「`ST=シンカー` / `SK=シュート`」と書くが、実コードは `ST → シュート` / `SK → シンカー`。**SPA は実コード側と一致**しており、ヘルプ文が誤り(`LEGACY:app/main.py:532` vs `LEGACY:app/pages/game_input.py:840-849` vs `LEGACY:frontend/src/lib/vocab.ts:10,14`)。

**旧 SPA 内部の二重定義**: `LEGACY:frontend/src/lib/displayGeometry.ts`(契約 JSON 由来・入力が使用)と `LEGACY:frontend/src/components/field/fieldGeometry.ts:16-22`(分析が使用)が同じ座標定数を別々に持つ。現状は値が一致しているが正本が 2 つある。

---

## 未解決・申し送り

**本調査の残余はすべて後続タスクへ送った(2026-09-02 起票・重複検索済み。URL は worklog に記録)**:

| 後続タスク | 送った内容 | 本メモの参照節 |
| --- | --- | --- |
| **TSK-305** 上流 68 コミット(dd03160→3a05296)の差分調査 | 基準時点の腐り。sync/記録権相当の上流実装の判定・カットオーバー日の議論材料 | §0-1 |
| **TSK-306** 要件書 10 章への穴 18 件の反映 | 画面の受入判定ができない穴(G-15 の H/E/K/B 定義不在を含む)。確定ゲート案件 | §1-3 |
| **TSK-307** 打席入力画面の逐語移植の受入判定 | NFR-018 (c) 例外表の終了証跡欄が求める受入判定(判定 PR の URL は TSK-275 へ引き渡す)。既存の申し送り(course-coordinate-contract/plan.md:110)の消化 | §6-3 |
| **TSK-308** PO 判断シートの裁定と正本化 | [decision-sheet.md](decision-sheet.md) の群 A(未決 12 件 — WHIP・FIP / 参照資料の置き場を含む)・群 B(既決と衝突 9 件 — 「完全に同じもの」裁定 × 要件の改善既決 7 件・個人アカウント・公式記録レビュー表示)の裁定と、裁定結果の正本化 | §4-1・§5・decision-sheet |
| **TSK-309** 充足度調査成果の正本化 | 確定した突合表(42 行)と画面 × FR 対応表(13 画面)の正本化(または成立条件つきの恒久化不要裁定) | §3・§2-7 |

### 本調査で確定できなかったもの(要件側の穴に起因)

§1-3 の 20 件(→ TSK-306)。特に **G-15(H/E/K/B の定義不在)は NFR-019 の比較面を確定不能にしており、要件書の改訂を要する可能性がある**。本調査は事実の指摘に留め、要件違反に当たるかの判定は行わない(なお旧実装に事実上の定義がある — §3 FR-020 行)。

### 実査の消化記録

- 2026-09-02 のステップ 1〜2 実査で、当初本節に挙がっていた全項目(記録・試合運営系 8 FR / 表示・分析・出力・認証系 7 FR + NFR-023 限定条項 + `analyse_strategy.py` 内部集計 + PDF 生成器のデータ経路)を §3 の該当行へ事実として反映し、ステップ 3 の条項単位照合(§3-2)で判定を確定した。

