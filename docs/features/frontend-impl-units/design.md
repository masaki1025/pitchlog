---
feature: frontend-impl-units
type: design
date: 2026-10-09
---

# 詳細設計: 移植元 frontend の面の棚卸し

## 1. 判定の材料と方法

移植元の固定コミットは dd03160044aa5932d3b5a025870c9a5a56d979ef（略記 dd03160）。タグ pitchlog-req-v2.0-evidence が指すコミットである。ローカルの保全リポジトリで同コミットの frontend/src/ を git ls-tree -r で列挙し、130 blob を確認した。下表の各行はそのコミットに実在するパスを典拠とする。13 画面、ストア実体 7 件と試験 2 件、API 7 件、共有部品 50 件、lib 45 件、起動・静的資産 6 件で合計 130 件。

①は現行の [core-areas.json](../../../.claude/core-areas.json) の areas[].paths に対応先パスを fnmatchcase で実際に当てた結果。対応先は frontend/src/ の相対位置を保ち、React コンポーネントの .tsx は .vue、main.tsx は既存の main.ts に対応させた。旧版の .test.mjs は勝手に .spec.ts とみなさず、そのまま照合した。②は [開発ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) の「6.3 レビュー体制」「コア領域の境界定義」の「含む」に、旧ファイルの実際の処理を当てた結果。各列の判定は独立である。

②の記号と根拠となる条文は次のとおり。

- S（同期プロトコル）: 「断中記録・墓標/改訂の適用・再送」「べき等キー」「複数タブの単一書き手競合」。耐久キュー、再送、入力抑止、重複判定を含めた。
- G（状況計算）: 「スコア・アウト・走者・打順・終了判定」「イベント単位の状態遷移・成績帰属」「状態補正イベント(FR-040)」「下流再計算/リプレイ」「座標変換・捕球選手推定」。表示だけのスコア表は含めず、入力値を変換・判定する処理を含めた。
- R（記録権）: 「記録権の付与・世代更新とフェンシング(旧世代拒否)」「通常引き継ぎの原子性」「緊急引き継ぎの競合拒否」。旧版の端末内入力ロックを記録権の付与と取り違えないため、この棚卸しでの②該当は 0 件。
- T（テナント分離）: 「テナント境界の認可判定すべて」「FR-041 の共有操作」「全出力経路の越境」。認証主体、チーム別キャッシュ、共有許可、管理・出力経路を含めた。
- D（データ移行）: 「FR-038 の全体」「FR-031/付録D の 88 列互換出力・サイドカー・直列化契約」。88 列の取込・出力面を含め、分析用 CSV の書式化とは分けた。

②に複数の記号があるファイルは、6.3 の「領域コードと非コアコードの混在ファイルはファイル全体を含める」「領域間の paths 重複を許す」に従う。最終列は①と②の和集合であり、食い違いは「判定に迷うコードは含む側に倒す」に従う。これは変更時のレビュー境界の導出であり、旧実装が現行要件を満たすという判定ではない。同期キューの旧版からのスキーマ移行は FR-038 の 88 列データ移行と区別した。

旧 route の件数は 15 本と catch-all。面の数は route 数から導かず、画面ファイル 13 件で数えた。route 一覧の正は [React → Vue 移植規則](../frontend-skeleton/porting-rules.md) の「router / query / store」。

## 2. 全件棚卸し

### 2.1 画面（13 件）

| dd03160 の実測パス | ① paths | ② 6.3 意味 | 採用 | 判定理由 |
| --- | --- | --- | --- | --- |
| dd03160:frontend/src/screens/AnalysisScreen.tsx | 不一致 | 該当（テナント） | コア | 保護対象の分析取得・出力 |
| dd03160:frontend/src/screens/ComparisonWorkspacesScreen.tsx | 不一致 | 該当（テナント） | コア | 共有許可とチーム別の取得・更新 |
| dd03160:frontend/src/screens/CsvImportScreen.tsx | 不一致 | 該当（テナント、データ移行） | コア | 88列 CSV の検証・確定と取込先 |
| dd03160:frontend/src/screens/GameListScreen.tsx | 不一致 | 該当（同期、テナント、データ移行） | コア | チーム別一覧・未送信キュー削除・88列出力 |
| dd03160:frontend/src/screens/GameScreen.tsx | 不一致 | 該当（同期、状況、テナント、データ移行） | コア | 再送・状態補正・チーム別キュー・88列出力 |
| dd03160:frontend/src/screens/HelpScreen.tsx | 不一致 | 非該当 | 非コア | 静的ガイド |
| dd03160:frontend/src/screens/KarteScreen.tsx | 不一致 | 該当（テナント） | コア | 選手別保護データの取得・更新・出力 |
| dd03160:frontend/src/screens/LineupScreen.tsx | 不一致 | 該当（状況、テナント） | コア | 打順変更とチーム別選手の取得 |
| dd03160:frontend/src/screens/LoginScreen.tsx | 不一致 | 該当（テナント） | コア | チーム認証と認可源の設定 |
| dd03160:frontend/src/screens/PlaysScreen.tsx | 不一致 | 該当（同期、状況、テナント、データ移行） | コア | 未同期抑止・過去修正・チーム別キュー・88列出力 |
| dd03160:frontend/src/screens/ScoreCardScreen.tsx | 不一致 | 該当（テナント） | コア | チームのスコア表と PDF 出力 |
| dd03160:frontend/src/screens/StartScreen.tsx | 不一致 | 該当（同期、テナント） | コア | チーム別キャッシュと未送信キュー削除 |
| dd03160:frontend/src/screens/TeamScreen.tsx | 不一致 | 該当（テナント） | コア | チーム管理・選手管理の境界 |

### 2.2 ストア（実体 7 件・試験 2 件）

| dd03160 の実測パス | ① paths | ② 6.3 意味 | 採用 | 判定理由 |
| --- | --- | --- | --- | --- |
| dd03160:frontend/src/stores/authStore.ts | 不一致 | 該当（テナント） | コア | 認証主体・チーム ID・役割の保持 |
| dd03160:frontend/src/stores/gameKindSettingsStore.ts | 不一致 | 該当（テナント） | コア | チーム別のローカル設定保持 |
| dd03160:frontend/src/stores/inputSettingsStore.ts | 不一致 | 非該当 | 非コア | 端末の入力表示設定のみ |
| dd03160:frontend/src/stores/pitchDraft.test.mjs | 不一致 | 該当（状況） | コア | 走者補正・打球入力下書きの試験 |
| dd03160:frontend/src/stores/pitchDraft.ts | 不一致 | 該当（状況） | コア | 走者補正・打球座標の下書き |
| dd03160:frontend/src/stores/shortcutStore.ts | 不一致 | 非該当 | 非コア | 端末のキー割当のみ |
| dd03160:frontend/src/stores/syncQueueMigration.test.mjs | 不一致 | 該当（同期、テナント） | コア | 旧耐久キューと所有チーム検証の試験 |
| dd03160:frontend/src/stores/syncQueueMigration.ts | 不一致 | 該当（同期、テナント） | コア | 旧耐久キューの復元・隔離・所有チーム検証 |
| dd03160:frontend/src/stores/syncStore.ts | 不一致 | 該当（同期、テナント） | コア | 耐久キューと所有チーム別の再送 |

### 2.3 API（7 件）

| dd03160 の実測パス | ① paths | ② 6.3 意味 | 採用 | 判定理由 |
| --- | --- | --- | --- | --- |
| dd03160:frontend/src/api/client.ts | 不一致 | 該当（同期、テナント） | コア | 再送対象判定と認証トークンの送信 |
| dd03160:frontend/src/api/combinedReports.ts | 不一致 | 該当（テナント） | コア | 保護対象の複合レポート出力 |
| dd03160:frontend/src/api/endpoints.ts | 不一致 | 該当（同期、状況、テナント、データ移行） | コア | 確定・補正・共有・88列入出力の契約が同居 |
| dd03160:frontend/src/api/liveInput.ts | 不一致 | 非該当 | 非コア | ライブ集計を取得する単純な GET |
| dd03160:frontend/src/api/mock.ts | 不一致 | 該当（同期、状況、テナント、データ移行） | コア | 重複送信判定・状態再計算・共有認可・88列出力 |
| dd03160:frontend/src/api/teamManagement.ts | 不一致 | 該当（テナント） | コア | チーム管理の API 契約 |
| dd03160:frontend/src/api/types.ts | 不一致 | 該当（同期、状況、テナント、データ移行） | コア | イベント・状態・共有許可・CSV の型契約 |

### 2.4 共有部品（50 件）

| dd03160 の実測パス | ① paths | ② 6.3 意味 | 採用 | 判定理由 |
| --- | --- | --- | --- | --- |
| dd03160:frontend/src/components/ComparisonWorkspaceAnalysis.tsx | 不一致 | 該当（テナント） | コア | チームを含む共有分析の取得キー |
| dd03160:frontend/src/components/analysis/AnalysisExportSheet.tsx | 不一致 | 該当（テナント） | コア | 保護対象の分析出力操作 |
| dd03160:frontend/src/components/analysis/StrategyDashboard.tsx | 不一致 | 非該当 | 非コア | 取得済み集計の表示 |
| dd03160:frontend/src/components/analysis/player/PlayerAnalysisPanels.tsx | 不一致 | 該当（状況） | コア | 保存座標からゾーン・分布を導く処理 |
| dd03160:frontend/src/components/analysis/player/battedBallFilter.test.mjs | 不一致 | 非該当 | 非コア | 表示用打球フィルタの試験 |
| dd03160:frontend/src/components/analysis/player/battedBallFilter.ts | 不一致 | 非該当 | 非コア | 表示用打球フィルタ |
| dd03160:frontend/src/components/analysis/player/pitchHeatmap.test.mjs | 不一致 | 非該当 | 非コア | ヒートマップ配色の試験 |
| dd03160:frontend/src/components/analysis/player/pitchHeatmap.ts | 不一致 | 非該当 | 非コア | ヒートマップの配色 |
| dd03160:frontend/src/components/data-transfer/DataTransferSheet.tsx | 不一致 | 該当（データ移行） | コア | 88列 CSV の入出力入口 |
| dd03160:frontend/src/components/diamond/BaseDiamond.tsx | 不一致 | 該当（状況） | コア | 走者状態の上書き入力 |
| dd03160:frontend/src/components/field/FieldDiagram.tsx | 不一致 | 該当（状況） | コア | 画面タップから保存座標への変換 |
| dd03160:frontend/src/components/field/FieldGeometrySvg.tsx | 不一致 | 該当（状況） | コア | 保存座標と同一のフィールド座標配置 |
| dd03160:frontend/src/components/field/fieldGeometry.test.mjs | 不一致 | 該当（状況） | コア | フィールド座標の契約試験 |
| dd03160:frontend/src/components/field/fieldGeometry.ts | 不一致 | 該当（状況） | コア | フィールド座標定数と幾何計算 |
| dd03160:frontend/src/components/game/BottomBar.tsx | 不一致 | 該当（同期、状況） | コア | 未同期時の入力・履歴修正の操作可否 |
| dd03160:frontend/src/components/game/CheatSheet.tsx | 不一致 | 非該当 | 非コア | 入力ガイドの表示 |
| dd03160:frontend/src/components/game/GameDeleteSheet.tsx | 不一致 | 該当（同期） | コア | 未送信キューを残す試合削除の抑止 |
| dd03160:frontend/src/components/game/GameListCard.tsx | 不一致 | 非該当 | 非コア | 試合情報と操作入口の表示 |
| dd03160:frontend/src/components/game/HeaderPlayerInfoPopover.tsx | 不一致 | 非該当 | 非コア | 取得済み選手情報の表示 |
| dd03160:frontend/src/components/game/HistoricalEditPreviewSheet.tsx | 不一致 | 非該当 | 非コア | サーバーの修正プレビュー表示 |
| dd03160:frontend/src/components/game/HistoricalSubstitutionSheet.tsx | 不一致 | 該当（状況） | コア | 過去交代の打順・守備位置を構成 |
| dd03160:frontend/src/components/game/LiveInputBar.tsx | 不一致 | 該当（同期） | コア | 未送信状態と手動再送操作 |
| dd03160:frontend/src/components/game/MenuSheet.tsx | 不一致 | 該当（同期、状況） | コア | 未同期時の状況補正・試合操作の抑止 |
| dd03160:frontend/src/components/game/OfficialScoringReviewSheet.tsx | 不一致 | 非該当 | 非コア | サーバーの成績帰属レビュー表示 |
| dd03160:frontend/src/components/game/PickoffSheet.tsx | 不一致 | 該当（状況） | コア | 在塁に応じた牽制結果の入力 |
| dd03160:frontend/src/components/game/PlayEditImpactSheet.tsx | 不一致 | 非該当 | 非コア | サーバーの修正影響の表示 |
| dd03160:frontend/src/components/game/QuickKarteNoteSheet.tsx | 不一致 | 非該当 | 非コア | 所見の編集フォーム |
| dd03160:frontend/src/components/game/ShortcutSettingsSheet.tsx | 不一致 | 非該当 | 非コア | キー割当の編集フォーム |
| dd03160:frontend/src/components/game/StateOverrideSheet.tsx | 不一致 | 該当（状況） | コア | 得点・アウト・走者の補正値を構成 |
| dd03160:frontend/src/components/game/StrategySheet.tsx | 不一致 | 非該当 | 非コア | 作戦値の選択フォーム |
| dd03160:frontend/src/components/game/SubstitutionSheet.tsx | 不一致 | 該当（状況） | コア | 交代・臨時代走の入力と改訂照合 |
| dd03160:frontend/src/components/game/SyncCenterSheet.tsx | 不一致 | 該当（同期） | コア | キューの再送・競合解決・破棄操作 |
| dd03160:frontend/src/components/game/TiebreakSheet.tsx | 不一致 | 該当（状況） | コア | タイブレークの走者配置を計算 |
| dd03160:frontend/src/components/pads/PitchTypeChips.tsx | 不一致 | 非該当 | 非コア | 球種選択の表示 |
| dd03160:frontend/src/components/pads/ResultPad.tsx | 不一致 | 該当（状況） | コア | 打撃結果と得点規則の判定 |
| dd03160:frontend/src/components/pads/SpeedPad.tsx | 不一致 | 非該当 | 非コア | 球速入力の表示と補完 |
| dd03160:frontend/src/components/scoreboard/BatterPitcherCard.tsx | 不一致 | 非該当 | 非コア | 取得済み投打情報の表示 |
| dd03160:frontend/src/components/scoreboard/CountDisplay.tsx | 不一致 | 非該当 | 非コア | 取得済みカウントの表示 |
| dd03160:frontend/src/components/scoreboard/MiniScoreboard.tsx | 不一致 | 非該当 | 非コア | 取得済み得点の表示 |
| dd03160:frontend/src/components/settings/GameKindSettingsContent.tsx | 不一致 | 該当（テナント） | コア | チーム別設定の選択・保存 |
| dd03160:frontend/src/components/settings/InputSettingsContent.tsx | 不一致 | 非該当 | 非コア | 視点・球速方式の設定表示 |
| dd03160:frontend/src/components/settings/InputSettingsSheet.tsx | 不一致 | 非該当 | 非コア | 入力設定の容器 |
| dd03160:frontend/src/components/settings/InputWorkflowModeToggle.tsx | 不一致 | 非該当 | 非コア | 入力用途の表示切替 |
| dd03160:frontend/src/components/settings/SettingsSheet.tsx | 不一致 | 該当（テナント） | コア | アカウントの変更と認証状態の操作 |
| dd03160:frontend/src/components/settings/TeamMembersContent.tsx | 不一致 | 該当（テナント） | コア | チーム内利用者の管理経路 |
| dd03160:frontend/src/components/ui/Button.tsx | 不一致 | 非該当 | 非コア | 汎用ボタン |
| dd03160:frontend/src/components/ui/Sheet.tsx | 不一致 | 非該当 | 非コア | 汎用ダイアログ |
| dd03160:frontend/src/components/ui/Toast.tsx | 不一致 | 非該当 | 非コア | 汎用通知 |
| dd03160:frontend/src/components/zone/StanceGrid.tsx | 不一致 | 該当（状況） | コア | 視点に応じた構え番号の保存値変換 |
| dd03160:frontend/src/components/zone/StrikeZone.tsx | 一致（状況） | 該当（状況） | コア | 画面タップから保存コース座標への変換 |

### 2.5 補助ロジック（45 件）

| dd03160 の実測パス | ① paths | ② 6.3 意味 | 採用 | 判定理由 |
| --- | --- | --- | --- | --- |
| dd03160:frontend/src/lib/analysisCsv.test.mjs | 不一致 | 非該当 | 非コア | 分析 CSV の書式・無害化試験 |
| dd03160:frontend/src/lib/analysisCsv.ts | 不一致 | 非該当 | 非コア | 集計済み分析値の CSV 書式化 |
| dd03160:frontend/src/lib/captureMetadata.ts | 不一致 | 該当（同期、状況） | コア | べき等キーと保存座標系の契約付与 |
| dd03160:frontend/src/lib/comparisonWorkspace.test.mjs | 不一致 | 該当（テナント） | コア | 共有範囲とチーム別キーの試験 |
| dd03160:frontend/src/lib/comparisonWorkspace.ts | 不一致 | 該当（テナント） | コア | 共有許可とチーム別キャッシュキー |
| dd03160:frontend/src/lib/count.ts | 不一致 | 該当（状況） | コア | 投球後のカウント仮更新 |
| dd03160:frontend/src/lib/courseInputView.test.mjs | 不一致 | 該当（状況） | コア | 保存座標と視点変換の試験 |
| dd03160:frontend/src/lib/courseInputView.ts | 一致（状況） | 該当（状況） | コア | 保存座標と表示座標の相互変換 |
| dd03160:frontend/src/lib/displayGeometry.ts | 一致（状況） | 該当（状況） | コア | 保存座標に対応する幾何定数 |
| dd03160:frontend/src/lib/fielder.ts | 不一致 | 該当（状況） | コア | 打球座標から捕球選手を推定 |
| dd03160:frontend/src/lib/format.ts | 一致（データ移行） | 非該当 | コア | 日付表示と CSS クラス結合のみ |
| dd03160:frontend/src/lib/gameInputLock.test.mjs | 不一致 | 該当（同期） | コア | 未同期時の入力ロックの試験 |
| dd03160:frontend/src/lib/gameInputLock.ts | 不一致 | 該当（同期） | コア | 未同期時の入力ロック判定 |
| dd03160:frontend/src/lib/gameKindSettings.test.mjs | 不一致 | 該当（テナント） | コア | チーム別設定の隔離試験 |
| dd03160:frontend/src/lib/gameKindSettings.ts | 不一致 | 該当（テナント） | コア | チーム ID 別の設定分離 |
| dd03160:frontend/src/lib/indexedDbStorage.test.mjs | 不一致 | 該当（同期） | コア | 耐久キューの保存・復元試験 |
| dd03160:frontend/src/lib/indexedDbStorage.ts | 不一致 | 該当（同期） | コア | 耐久キューの IndexedDB 保存・復元 |
| dd03160:frontend/src/lib/lineupEditor.test.mjs | 不一致 | 該当（状況） | コア | 打順・DH 変換の試験 |
| dd03160:frontend/src/lib/lineupEditor.ts | 不一致 | 該当（状況） | コア | 打順・DH と守備位置の変換 |
| dd03160:frontend/src/lib/liveInput.test.mjs | 不一致 | 非該当 | 非コア | 表示用途の入力モードの試験 |
| dd03160:frontend/src/lib/liveInput.ts | 不一致 | 非該当 | 非コア | 表示モードと取得結果の型定義 |
| dd03160:frontend/src/lib/mockRules.ts | 不一致 | 該当（同期、状況） | コア | 模擬環境の重複記録と走者・プレイ計算 |
| dd03160:frontend/src/lib/mockTeamManagement.test.mjs | 不一致 | 該当（テナント） | コア | 模擬環境の認証・チーム管理試験 |
| dd03160:frontend/src/lib/mockTeamManagement.ts | 不一致 | 該当（テナント） | コア | 模擬環境の認証主体判定 |
| dd03160:frontend/src/lib/playRules.ts | 不一致 | 該当（状況） | コア | アウト・得点の結果規則 |
| dd03160:frontend/src/lib/playerAnalysisProfile.test.mjs | 不一致 | 非該当 | 非コア | 選手分析プロフィールの入力検証試験 |
| dd03160:frontend/src/lib/playerAnalysisProfile.ts | 不一致 | 非該当 | 非コア | 選手分析プロフィールの入力検証 |
| dd03160:frontend/src/lib/playerMeasurement.test.mjs | 不一致 | 非該当 | 非コア | 選手測定値の模擬データ操作試験 |
| dd03160:frontend/src/lib/playerMeasurement.ts | 不一致 | 非該当 | 非コア | 選手測定値の模擬データ操作 |
| dd03160:frontend/src/lib/playerProfile.test.mjs | 不一致 | 非該当 | 非コア | 選手プロフィールの入力検証試験 |
| dd03160:frontend/src/lib/playerProfile.ts | 不一致 | 非該当 | 非コア | 選手プロフィールの入力検証 |
| dd03160:frontend/src/lib/queryClient.ts | 不一致 | 非該当 | 非コア | 汎用取得キャッシュ設定 |
| dd03160:frontend/src/lib/registerServiceWorker.ts | 不一致 | 非該当 | 非コア | 静的資産用 Service Worker の登録 |
| dd03160:frontend/src/lib/scoringReview.ts | 不一致 | 該当（状況） | コア | 得点・自責の暫定帰属計算 |
| dd03160:frontend/src/lib/shortcuts.test.mjs | 不一致 | 非該当 | 非コア | キー割当の試験 |
| dd03160:frontend/src/lib/shortcuts.ts | 不一致 | 非該当 | 非コア | キー割当と表示 |
| dd03160:frontend/src/lib/spatialInput.ts | 一致（状況） | 該当（状況） | コア | 座標の移動・保存範囲への制限 |
| dd03160:frontend/src/lib/speedInput.test.mjs | 不一致 | 非該当 | 非コア | 球速入力補完の試験 |
| dd03160:frontend/src/lib/speedInput.ts | 不一致 | 非該当 | 非コア | 球速入力補完 |
| dd03160:frontend/src/lib/syncPolicy.ts | 不一致 | 該当（同期） | コア | 失敗分類・再送時刻の算定 |
| dd03160:frontend/src/lib/teamSearch.test.mjs | 不一致 | 非該当 | 非コア | チーム名検索表示の試験 |
| dd03160:frontend/src/lib/teamSearch.ts | 不一致 | 非該当 | 非コア | チーム名の検索表示 |
| dd03160:frontend/src/lib/useKeydown.ts | 不一致 | 非該当 | 非コア | 汎用キーイベント登録 |
| dd03160:frontend/src/lib/vocab.test.mjs | 不一致 | 該当（状況） | コア | プレイ結果・走者状態コードの試験 |
| dd03160:frontend/src/lib/vocab.ts | 不一致 | 該当（状況） | コア | プレイ結果・走者状態の入力コード表 |

### 2.6 起動・静的資産（6 件）

| dd03160 の実測パス | ① paths | ② 6.3 意味 | 採用 | 判定理由 |
| --- | --- | --- | --- | --- |
| dd03160:frontend/src/App.tsx | 不一致 | 該当（テナント） | コア | 認証・管理者ガードの判定 |
| dd03160:frontend/src/assets/batter-silhouette-front.png | 不一致 | 非該当 | 非コア | 表示用の静的画像 |
| dd03160:frontend/src/assets/batter-silhouette-right.png | 不一致 | 非該当 | 非コア | 表示用の静的画像 |
| dd03160:frontend/src/assets/pitcher-silhouette-back.png | 不一致 | 非該当 | 非コア | 表示用の静的画像 |
| dd03160:frontend/src/index.css | 不一致 | 非該当 | 非コア | 全体の表示スタイル |
| dd03160:frontend/src/main.tsx | 不一致 | 非該当 | 非コア | アプリ起動処理 |

## 3. ①と②の食い違い（全件）

次の表は食い違った面を省略せず再掲する。いずれも 6.3 の fail-closed 規則によりコアに含める。②に複数領域があるときも、①との差はファイル単位で 1 件と数える。

| dd03160 の実測パス | ① paths | ② 6.3 意味 | 食い違いの理由 |
| --- | --- | --- | --- |
| dd03160:frontend/src/App.tsx | 不一致 | 該当（テナント） | 認証・管理者ガードの判定 |
| dd03160:frontend/src/api/client.ts | 不一致 | 該当（同期、テナント） | 再送対象判定と認証トークンの送信 |
| dd03160:frontend/src/api/combinedReports.ts | 不一致 | 該当（テナント） | 保護対象の複合レポート出力 |
| dd03160:frontend/src/api/endpoints.ts | 不一致 | 該当（同期、状況、テナント、データ移行） | 確定・補正・共有・88列入出力の契約が同居 |
| dd03160:frontend/src/api/mock.ts | 不一致 | 該当（同期、状況、テナント、データ移行） | 重複送信判定・状態再計算・共有認可・88列出力 |
| dd03160:frontend/src/api/teamManagement.ts | 不一致 | 該当（テナント） | チーム管理の API 契約 |
| dd03160:frontend/src/api/types.ts | 不一致 | 該当（同期、状況、テナント、データ移行） | イベント・状態・共有許可・CSV の型契約 |
| dd03160:frontend/src/components/ComparisonWorkspaceAnalysis.tsx | 不一致 | 該当（テナント） | チームを含む共有分析の取得キー |
| dd03160:frontend/src/components/analysis/AnalysisExportSheet.tsx | 不一致 | 該当（テナント） | 保護対象の分析出力操作 |
| dd03160:frontend/src/components/analysis/player/PlayerAnalysisPanels.tsx | 不一致 | 該当（状況） | 保存座標からゾーン・分布を導く処理 |
| dd03160:frontend/src/components/data-transfer/DataTransferSheet.tsx | 不一致 | 該当（データ移行） | 88列 CSV の入出力入口 |
| dd03160:frontend/src/components/diamond/BaseDiamond.tsx | 不一致 | 該当（状況） | 走者状態の上書き入力 |
| dd03160:frontend/src/components/field/FieldDiagram.tsx | 不一致 | 該当（状況） | 画面タップから保存座標への変換 |
| dd03160:frontend/src/components/field/FieldGeometrySvg.tsx | 不一致 | 該当（状況） | 保存座標と同一のフィールド座標配置 |
| dd03160:frontend/src/components/field/fieldGeometry.test.mjs | 不一致 | 該当（状況） | フィールド座標の契約試験 |
| dd03160:frontend/src/components/field/fieldGeometry.ts | 不一致 | 該当（状況） | フィールド座標定数と幾何計算 |
| dd03160:frontend/src/components/game/BottomBar.tsx | 不一致 | 該当（同期、状況） | 未同期時の入力・履歴修正の操作可否 |
| dd03160:frontend/src/components/game/GameDeleteSheet.tsx | 不一致 | 該当（同期） | 未送信キューを残す試合削除の抑止 |
| dd03160:frontend/src/components/game/HistoricalSubstitutionSheet.tsx | 不一致 | 該当（状況） | 過去交代の打順・守備位置を構成 |
| dd03160:frontend/src/components/game/LiveInputBar.tsx | 不一致 | 該当（同期） | 未送信状態と手動再送操作 |
| dd03160:frontend/src/components/game/MenuSheet.tsx | 不一致 | 該当（同期、状況） | 未同期時の状況補正・試合操作の抑止 |
| dd03160:frontend/src/components/game/PickoffSheet.tsx | 不一致 | 該当（状況） | 在塁に応じた牽制結果の入力 |
| dd03160:frontend/src/components/game/StateOverrideSheet.tsx | 不一致 | 該当（状況） | 得点・アウト・走者の補正値を構成 |
| dd03160:frontend/src/components/game/SubstitutionSheet.tsx | 不一致 | 該当（状況） | 交代・臨時代走の入力と改訂照合 |
| dd03160:frontend/src/components/game/SyncCenterSheet.tsx | 不一致 | 該当（同期） | キューの再送・競合解決・破棄操作 |
| dd03160:frontend/src/components/game/TiebreakSheet.tsx | 不一致 | 該当（状況） | タイブレークの走者配置を計算 |
| dd03160:frontend/src/components/pads/ResultPad.tsx | 不一致 | 該当（状況） | 打撃結果と得点規則の判定 |
| dd03160:frontend/src/components/settings/GameKindSettingsContent.tsx | 不一致 | 該当（テナント） | チーム別設定の選択・保存 |
| dd03160:frontend/src/components/settings/SettingsSheet.tsx | 不一致 | 該当（テナント） | アカウントの変更と認証状態の操作 |
| dd03160:frontend/src/components/settings/TeamMembersContent.tsx | 不一致 | 該当（テナント） | チーム内利用者の管理経路 |
| dd03160:frontend/src/components/zone/StanceGrid.tsx | 不一致 | 該当（状況） | 視点に応じた構え番号の保存値変換 |
| dd03160:frontend/src/lib/captureMetadata.ts | 不一致 | 該当（同期、状況） | べき等キーと保存座標系の契約付与 |
| dd03160:frontend/src/lib/comparisonWorkspace.test.mjs | 不一致 | 該当（テナント） | 共有範囲とチーム別キーの試験 |
| dd03160:frontend/src/lib/comparisonWorkspace.ts | 不一致 | 該当（テナント） | 共有許可とチーム別キャッシュキー |
| dd03160:frontend/src/lib/count.ts | 不一致 | 該当（状況） | 投球後のカウント仮更新 |
| dd03160:frontend/src/lib/courseInputView.test.mjs | 不一致 | 該当（状況） | 保存座標と視点変換の試験 |
| dd03160:frontend/src/lib/fielder.ts | 不一致 | 該当（状況） | 打球座標から捕球選手を推定 |
| dd03160:frontend/src/lib/format.ts | 一致（データ移行） | 非該当 | 日付表示と CSS クラス結合のみ |
| dd03160:frontend/src/lib/gameInputLock.test.mjs | 不一致 | 該当（同期） | 未同期時の入力ロックの試験 |
| dd03160:frontend/src/lib/gameInputLock.ts | 不一致 | 該当（同期） | 未同期時の入力ロック判定 |
| dd03160:frontend/src/lib/gameKindSettings.test.mjs | 不一致 | 該当（テナント） | チーム別設定の隔離試験 |
| dd03160:frontend/src/lib/gameKindSettings.ts | 不一致 | 該当（テナント） | チーム ID 別の設定分離 |
| dd03160:frontend/src/lib/indexedDbStorage.test.mjs | 不一致 | 該当（同期） | 耐久キューの保存・復元試験 |
| dd03160:frontend/src/lib/indexedDbStorage.ts | 不一致 | 該当（同期） | 耐久キューの IndexedDB 保存・復元 |
| dd03160:frontend/src/lib/lineupEditor.test.mjs | 不一致 | 該当（状況） | 打順・DH 変換の試験 |
| dd03160:frontend/src/lib/lineupEditor.ts | 不一致 | 該当（状況） | 打順・DH と守備位置の変換 |
| dd03160:frontend/src/lib/mockRules.ts | 不一致 | 該当（同期、状況） | 模擬環境の重複記録と走者・プレイ計算 |
| dd03160:frontend/src/lib/mockTeamManagement.test.mjs | 不一致 | 該当（テナント） | 模擬環境の認証・チーム管理試験 |
| dd03160:frontend/src/lib/mockTeamManagement.ts | 不一致 | 該当（テナント） | 模擬環境の認証主体判定 |
| dd03160:frontend/src/lib/playRules.ts | 不一致 | 該当（状況） | アウト・得点の結果規則 |
| dd03160:frontend/src/lib/scoringReview.ts | 不一致 | 該当（状況） | 得点・自責の暫定帰属計算 |
| dd03160:frontend/src/lib/syncPolicy.ts | 不一致 | 該当（同期） | 失敗分類・再送時刻の算定 |
| dd03160:frontend/src/lib/vocab.test.mjs | 不一致 | 該当（状況） | プレイ結果・走者状態コードの試験 |
| dd03160:frontend/src/lib/vocab.ts | 不一致 | 該当（状況） | プレイ結果・走者状態の入力コード表 |
| dd03160:frontend/src/screens/AnalysisScreen.tsx | 不一致 | 該当（テナント） | 保護対象の分析取得・出力 |
| dd03160:frontend/src/screens/ComparisonWorkspacesScreen.tsx | 不一致 | 該当（テナント） | 共有許可とチーム別の取得・更新 |
| dd03160:frontend/src/screens/CsvImportScreen.tsx | 不一致 | 該当（テナント、データ移行） | 88列 CSV の検証・確定と取込先 |
| dd03160:frontend/src/screens/GameListScreen.tsx | 不一致 | 該当（同期、テナント、データ移行） | チーム別一覧・未送信キュー削除・88列出力 |
| dd03160:frontend/src/screens/GameScreen.tsx | 不一致 | 該当（同期、状況、テナント、データ移行） | 再送・状態補正・チーム別キュー・88列出力 |
| dd03160:frontend/src/screens/KarteScreen.tsx | 不一致 | 該当（テナント） | 選手別保護データの取得・更新・出力 |
| dd03160:frontend/src/screens/LineupScreen.tsx | 不一致 | 該当（状況、テナント） | 打順変更とチーム別選手の取得 |
| dd03160:frontend/src/screens/LoginScreen.tsx | 不一致 | 該当（テナント） | チーム認証と認可源の設定 |
| dd03160:frontend/src/screens/PlaysScreen.tsx | 不一致 | 該当（同期、状況、テナント、データ移行） | 未同期抑止・過去修正・チーム別キュー・88列出力 |
| dd03160:frontend/src/screens/ScoreCardScreen.tsx | 不一致 | 該当（テナント） | チームのスコア表と PDF 出力 |
| dd03160:frontend/src/screens/StartScreen.tsx | 不一致 | 該当（同期、テナント） | チーム別キャッシュと未送信キュー削除 |
| dd03160:frontend/src/screens/TeamScreen.tsx | 不一致 | 該当（テナント） | チーム管理・選手管理の境界 |
| dd03160:frontend/src/stores/authStore.ts | 不一致 | 該当（テナント） | 認証主体・チーム ID・役割の保持 |
| dd03160:frontend/src/stores/gameKindSettingsStore.ts | 不一致 | 該当（テナント） | チーム別のローカル設定保持 |
| dd03160:frontend/src/stores/pitchDraft.test.mjs | 不一致 | 該当（状況） | 走者補正・打球入力下書きの試験 |
| dd03160:frontend/src/stores/pitchDraft.ts | 不一致 | 該当（状況） | 走者補正・打球座標の下書き |
| dd03160:frontend/src/stores/syncQueueMigration.test.mjs | 不一致 | 該当（同期、テナント） | 旧耐久キューと所有チーム検証の試験 |
| dd03160:frontend/src/stores/syncQueueMigration.ts | 不一致 | 該当（同期、テナント） | 旧耐久キューの復元・隔離・所有チーム検証 |
| dd03160:frontend/src/stores/syncStore.ts | 不一致 | 該当（同期、テナント） | 耐久キューと所有チーム別の再送 |

## 4. 検算

- 2.1 画面（13 件）: 13 件
- 2.2 ストア（実体 7 件・試験 2 件）: 9 件
- 2.3 API（7 件）: 7 件
- 2.4 共有部品（50 件）: 50 件
- 2.5 補助ロジック（45 件）: 45 件
- 2.6 起動・静的資産（6 件）: 6 件
- 合計: 130 件。①一致 5 件、②該当 76 件、採用コア 77 件、非コア 53 件。
- 食い違い: ①のみ 1 件、②のみ 72 件、合計 73 件。上の別表の行数と一致。
- ①のみの format.ts は日付表示と CSS クラス結合だけで、6.3 の 88 列変換・直列化に当たらない。現行 paths に一致する事実は残し、採用はコアとした。
- 旧版には R（記録権）の付与・フェンシング・引き継ぎを実装する面を確認できないため、②の R 該当は 0 件。これは現行製品でその面が不要という判断を含まない。

## 5. frontend 実装単位の候補と境界

### 5.1. 候補の読み方

以下は 2 節の実測面と現行要件に必要な増分面から導いた**単位の候補**であり、FR の主所有や分担表の確定ではない。候補 ID は既存の `U-A1`〜`U-X5` と衝突しない `U-F1`〜`U-F14` とする。`F` は frontend を表す識別用の接頭辞であり、正本に存在しない採番規則を設けるものではない。既存の主所有は [製品実装単位の設計](../product-impl-unit-split/design.md) の「4-1. 主所有(FR ごとにちょうど 1 単位)」にある 42 FR のままとする。下表の「FR の面」は frontend が担う**名前つきの候補面**であり、各 FR の成立全体を引き受ける意味ではない。FR 別の分担行と被覆検算はこの節では確定しない。

`S`＝同期プロトコル、`G`＝状況計算、`R`＝記録権、`T`＝テナント分離、`D`＝データ移行。判定は [開発ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) の「6.3 レビュー体制」「コア領域の境界定義」の**各「含む」欄**を、候補が変更し得る面に当てたもの。2 節の旧ファイル判定を変更せず、現行要件で加わる面も候補単位の判定へ含める。依存先がコアであるだけでは自単位をコアにしないが、混在する契約や意味上の強制点を自単位が変更し得る場合は含める。依存は実装・連携に必要な境界を示し、着手順や PR 分割を定めない。

### 5.2. 境界を引く実測

| 実測した関係 | 候補への帰結 |
| --- | --- |
| `dd03160:frontend/src/screens/LineupScreen.tsx` は二つの既存 route で共用される。`GameScreen.tsx`・`LineupScreen.tsx`・`PlaysScreen.tsx` は相互に遷移し、試合状態キャッシュを書き換え合う。過去修正の入口は Plays、確定は Game にある。 | Lineup の二つの入口を分けず、Game・Lineup・Plays を `U-F8` にまとめる。Start と GameList も同じ試合再開・削除・状態キャッシュの面として含める。 |
| `dd03160:frontend/src/screens/KarteScreen.tsx` は投手・打者の二つの既存 route で共用される。 | Karte を途中で分けず、分析・個人カルテの `U-F10` に含める。 |
| `LoginScreen.tsx`・`HelpScreen.tsx`・`TeamScreen.tsx` は独立度が高い。Team と他画面の接点は `['players', teamId]` キャッシュである。 | それぞれ `U-F3`・`U-F4`・`U-F5` に分け、Team と試合面の接点はキャッシュ契約として扱う。 |
| 全画面共通の部品は `dd03160:frontend/src/components/ui/` の Button・Sheet・Toast で、全画面をまたぐストアは `stores/authStore.ts` だけである。`zone/`・`field/`・`diamond/`・`pads/`・`scoreboard/` の利用者は GameScreen とその配下に限る。 | 共通表示 `U-F1` と認証状態 `U-F2` を分ける。試合専用の部品群は `U-F8` に置き、全画面共通とは扱わない。 |
| 移植元 130 件で現行 `areas[].paths` に一致したのは 5 件。一方、pitchlog 側 `frontend/src/lib/sync/` の 61 ファイルは移植元 `dd03160` に存在しない現行資産である。`components/zone/` とともに現行の機械的なコア境界に当たる。 | `src/lib/sync/` に接続する耐久キュー・記録権の面を `U-F7`、`components/zone/` に触れる記録・座標入力の面を `U-F8` とする。61 ファイルを移植対象に数えない。他候補はこの二つのパスを直接の変更面に含めず、それぞれの**意味**に従って 5 領域を判定する。 |

2.1 の旧画面 13 件にシステム管理者の管理コンソールはない。[要件書](../../requirements/requirements-pitchlog-2026-07-22.md) の「FR-035: システム管理者機能」「FR-037: 管理コンソール」はチーム管理より広い管理・出力経路を要求する。旧 TeamScreen と混同せず、対応する旧パスのない増分面を `U-F14` に置く。

### 5.3. 候補一覧

下表のパスは `dd03160:frontend/src/` を起点とする。`**` は 2 節に列挙済みの当該配下の面と試験を指す。`U-F7` の現行 `frontend/src/lib/sync/` は依存先であって移植元の面ではない。`U-F14` は対応する旧パスがない現行要件の増分面である。

| 候補 | ① 含む面 | ② 担う FR の面（候補） | ④ 依存する面・既存単位 |
| --- | --- | --- | --- |
| **U-F1 共通表示** | `components/ui/**`、`index.css`、`lib/queryClient.ts`・`registerServiceWorker.ts`・`teamSearch*`。汎用の表示・取得補助。 | FR-002 の入力操作、FR-020〜023 の表示に共通する UI 器具。個別の記録・集計の成立判定は利用画面側。 | 現行 frontend の起動基盤。ほかの候補への実装依存はない。 |
| **U-F2 認証状態** | `stores/authStore.ts`。全画面に渡す認証主体・チーム・役割の境界。 | FR-033 のセッション保持、FR-034 のクライアント側認可源。 | 認証・テナント契約 `U-A1`・`U-T1`。 |
| **U-F3 ログイン** | `screens/LoginScreen.tsx`。 | FR-033 のログイン入力・失敗表示面。 | `U-F1`・`U-F2`・`U-F6`、認証契約 `U-A1`。 |
| **U-F4 利用ガイド** | `screens/HelpScreen.tsx`。 | FR-002 の入力操作と FR-012 の断中操作を利用者へ説明する補助面。要件書「8. 完了条件・リリース判定基準」の利用ガイドにも接する。 | `U-F1`・`U-F2`。記録・同期の実装には依存しない。 |
| **U-F5 チーム・選手** | `screens/TeamScreen.tsx`、`api/teamManagement.ts`、`components/settings/TeamMembersContent.tsx`、`lib/playerProfile*`・`playerAnalysisProfile*`・`playerMeasurement*`。 | FR-015・017・018・039 の選手・チーム管理面、FR-034 のチーム管理画面越境防止面、FR-038 の旧データ名寄せに接し得る選手確認面。 | `U-F1`・`U-F2`・`U-F6`、選手・取込契約 `U-M1`・`U-X5`。`U-F8` とは `['players', teamId]` キャッシュ契約のみを共有する。 |
| **U-F6 共通 API・形式契約** | `api/client.ts`・`endpoints.ts`・`types.ts`・`mock.ts`、`lib/mockRules.ts`・`mockTeamManagement*`・`format.ts`。領域別の API 3 ファイルは各利用候補へ置く。 | FR-012・013 の送信・世代情報、FR-003・007・040 のイベント・補正、FR-031・038 の 88 列入出力、FR-034・041 の認可・共有に共通する通信・型の面。 | `U-F2`、既存 `U-S1`・`U-R1`・`U-X1`・`U-D2`・`U-X5`・`U-C1` の契約。模擬計算は独立した正解実装にしない。 |
| **U-F7 耐久キュー・記録権接続** | `stores/syncStore.ts`・`syncQueueMigration*`、`lib/indexedDbStorage*`・`syncPolicy.ts`・`gameInputLock*`・`captureMetadata.ts`。現行 `frontend/src/lib/sync/` との接続境界。 | FR-012 の耐久キュー・再送・単一書き手、FR-013 の世代・連番・引き継ぎをクライアントで扱う面。 | `U-F2`・`U-F6`、現行 `frontend/src/lib/sync/` と `U-S1`・`U-R1` のプロトコル。 |
| **U-F8 試合記録・再開・修正** | `screens/{Start,GameList,Lineup,Game,Plays}Screen.tsx`、`components/{game,zone,field,diamond,pads,scoreboard}/**`、`components/settings/` の TeamMembersContent 以外、`stores/{pitchDraft,gameKindSettingsStore,inputSettingsStore,shortcutStore}*`、`api/liveInput.ts`、`lib/{count,courseInputView,displayGeometry,fielder,gameKindSettings,lineupEditor,liveInput,playRules,scoringReview,shortcuts,spatialInput,speedInput,useKeydown,vocab}*`、`assets/`。 | FR-001〜011・014・016・019・024・040 の開始、入力、交代、補正、再開、削除、事前取得の画面面。FR-012・013 の同期・記録権の操作面。FR-020〜023 の**記録中の表示面**、FR-031 の試合からの出力入口、FR-036 のパスワード変更フォーム面。 | `U-F1`・`U-F2`・`U-F5`（選手キャッシュ）・`U-F6`・`U-F7`・`U-F9`（入出力入口）。既存 `U-G1`・`U-G2`・`U-X1`・`U-S1`・`U-R1`・`U-D1`・`U-P1`・`U-D2`・`U-A1` の契約。 |
| **U-F9 88 列データ受渡し** | `screens/CsvImportScreen.tsx`、`components/data-transfer/DataTransferSheet.tsx`。 | FR-031 の互換 CSV 出力入口、FR-038 の取込・検証結果・警告・確認の画面面。 | `U-F1`・`U-F2`・`U-F6`、既存 `U-D2`・`U-X5`・`U-T1` の入出力・越境防止契約。 |
| **U-F10 分析・個人カルテ** | `screens/{Analysis,Karte}Screen.tsx`、`components/analysis/**`、`api/combinedReports.ts`、`lib/analysisCsv*`。 | FR-025〜029・032・042 の保護対象分析・個人カルテ・分析出力の面。Karte の二つの既存入口を同一候補に置く。 | `U-F1`・`U-F2`・`U-F6`、既存 `U-X2`・`U-X4`・`U-T1` の集計・出力・認可契約。 |
| **U-F11 共同分析** | `screens/ComparisonWorkspacesScreen.tsx`、`components/ComparisonWorkspaceAnalysis.tsx`、`lib/comparisonWorkspace*`。 | FR-041 の共有操作・共有分析の保護表示面。 | `U-F1`・`U-F2`・`U-F6`、既存 `U-C1`・`U-C2`・`U-C3`・`U-X2` の共有認可・集計契約。 |
| **U-F12 スコアカード** | `screens/ScoreCardScreen.tsx`。 | FR-030 のスコアカード表示・PDF 出力面。 | `U-F1`・`U-F2`・`U-F6`、`U-F8` の試合下書き解除境界、既存 `U-X3` の出力契約。 |
| **U-F13 起動・アクセス入口** | `App.tsx`・`main.tsx`。画面へのアクセスを組み立てる境界。 | FR-033 の認証状態による入口、FR-034 のクライアント側アクセス表示面。サーバー認可の代替にはしない。 | `U-F2`・`U-F3`・`U-F4`・`U-F5`・`U-F8`〜`U-F12`・`U-F14` の画面候補、[React → Vue 移植規則](../frontend-skeleton/porting-rules.md) の「router / query / store」。 |
| **U-F14 システム管理** | 旧 130 件に対応ファイルはない。要件書「FR-035: システム管理者機能」「FR-037: 管理コンソール」「FR-038: 既存データの一括移行」が要求する管理・移行・出力の画面面。形はここで決めない。 | FR-035・037 の管理者認証・管理操作・一覧・退避イベント確認、FR-038 の一括移行の実行確認・結果確認、FR-013 の退避イベント対応、FR-031 の管理者 CSV 出力面。 | `U-F1`・`U-F2`・`U-F6`・`U-F7`、既存 `U-A2`・`U-R1`・`U-S1`・`U-X5`・`U-D2`・`U-C1` の管理・記録権・移行契約。 |

### 5.4. 5 領域すべてへの判定

各セルは**その候補が変更し得る面**の判定である。「非該当」は依存先の領域を否定しない。特に `U-F1`・`U-F4` は非コアの表示面として閉じる候補であり、`U-F7`・`U-F8` はそれぞれ `src/lib/sync/`・`components/zone/` の境界に触れる。その他の候補も 6.3 の意味範囲へ当たればコアとする。

| 候補 | S 同期 | G 状況 | R 記録権 | T テナント | D 移行 |
| --- | --- | --- | --- | --- | --- |
| U-F1 共通表示 | 非該当 | 非該当 | 非該当 | 非該当 | 非該当 |
| U-F2 認証状態 | 非該当 | 非該当 | 非該当 | 該当 | 非該当 |
| U-F3 ログイン | 非該当 | 非該当 | 非該当 | 該当 | 非該当 |
| U-F4 利用ガイド | 非該当 | 非該当 | 非該当 | 非該当 | 非該当 |
| U-F5 チーム・選手 | 非該当 | 非該当 | 非該当 | 該当 | 該当 |
| U-F6 共通 API・形式契約 | 該当 | 該当 | 該当 | 該当 | 該当 |
| U-F7 耐久キュー・記録権接続 | 該当 | 該当 | 該当 | 該当 | 非該当 |
| U-F8 試合記録・再開・修正 | 該当 | 該当 | 該当 | 該当 | 該当 |
| U-F9 88 列データ受渡し | 非該当 | 非該当 | 非該当 | 該当 | 該当 |
| U-F10 分析・個人カルテ | 非該当 | 該当 | 非該当 | 該当 | 非該当 |
| U-F11 共同分析 | 非該当 | 非該当 | 非該当 | 該当 | 非該当 |
| U-F12 スコアカード | 非該当 | 非該当 | 非該当 | 該当 | 非該当 |
| U-F13 起動・アクセス入口 | 非該当 | 非該当 | 非該当 | 該当 | 非該当 |
| U-F14 システム管理 | 該当 | 非該当 | 該当 | 該当 | 該当 |

複数領域に帰属する候補は次の **7 件を全件列挙**する。各根拠は 6.3「コア領域の境界定義」の「含む」欄の文言に当てたもので、機械的な paths の一致数ではない。

| 候補 | 重複帰属 | 「含む」欄への当てはめ・含む側に倒した点 |
| --- | --- | --- |
| U-F5 | T・D | チーム内管理の経路は「テナント境界の認可判定すべて」。旧選手データの請求・確認が FR-038 の「名寄せ」や「確認ガード」に接する可能性があるため、旧 TeamScreen 単体の 2 節判定は変えず、候補単位では D も含める。 |
| U-F6 | S・G・R・T・D | `endpoints.ts`・`types.ts`・`mock.ts` は、6.3 の「再送・べき等キー」「イベント単位の状態遷移・成績帰属」「テナント境界の認可判定すべて」「88 列互換出力・直列化契約」が混在する。現行 FR-013 の世代・フェンシング契約も共通の送信型を通り得るため R を含める。`format.ts` は旧意味判定では D 非該当でも、現行 paths に一致するのでコア採用を維持する。 |
| U-F7 | S・G・R・T | 耐久キューは「断中記録・再送」「複数タブの単一書き手競合」、捕捉メタデータは「座標変換」、世代・連番は「記録権の付与・世代更新とフェンシング」と重複し得る。所有チーム別の復元・隔離は「テナント境界の認可判定すべて」に当たる。旧キューのスキーマ更新は FR-038 の 88 列移行ではないため D は含めない。 |
| U-F8 | S・G・R・T・D | 入力と再送は「断中記録・再送」、打順・走者・座標は「イベント単位の状態遷移」「座標変換」、チーム別一覧・キャッシュと CSV は「全出力経路の越境」、88 列出力は「FR-031/付録D の 88 列互換出力」に当たる。旧版に R 実装が無くても、現行 FR-013 の世代・引き継ぎに関わる記録可否を画面から扱うため R を含める。 |
| U-F9 | T・D | 取込先と CSV 出力は「全出力経路の越境」。取込・隔離・警告・確認は「FR-038 の全体」、出力は「FR-031/付録D の 88 列互換出力」に当たる。 |
| U-F10 | G・T | `components/analysis/player/PlayerAnalysisPanels.tsx` の保存座標からの分布導出は「座標変換」に接する。後段集計も 6.3 の条件付き除外の発効前は含む。分析・カルテ・PDF は「FR-042 の保護対象集計」「全出力経路の越境」に当たる。 |
| U-F14 | S・R・T・D | 管理者の退避イベント取込は「墓標/改訂の適用・再送」と「退避経路」に接する。管理・共有操作と横断一覧は「認可源・管理経路」「全出力経路の越境」、一括移行は「FR-038 の全体」、管理者 CSV は「FR-031/付録D の 88 列互換出力」に当たる。取込時の状態再計算は既存のサーバー契約に依存し、この候補で G の強制点を変更する面は置かない。 |

単一領域の候補も条文へ当てた。`U-F2`・`U-F3`・`U-F13` は FR-033 の「認可源・管理経路」、`U-F11` は「FR-041 の共有操作」、`U-F12` は「全出力経路の越境」により T に該当する。`U-F1` の汎用部品と `U-F4` の静的ガイドは、6.3 の 5 領域の強制点を変更しないためすべて非該当とした。記録権を伴わない単純な表示制御は 6.3 の R「含めない」欄に従うが、`U-F7`・`U-F8` の世代・引き継ぎ境界をその表示に狭めて除外しない。

### 5.5. 計算と主所有の境界

リハーサル最小集合の 26 FR には FR-020・021・022・023 が含まれ、いずれも記録中の画面に表示面がある。4 件の**主所有は既存 `U-X1`**のまま、`U-F8` はスコアボード・投手成績・打者成績・球種分布の**表示面の候補**とする。断中にも表示するためクライアントで状況を算出する場合、その計算は `NFR-018` の単一実装に従う。`contracts/` のゴールデンベクタをクライアント・サーバー一致の正として照合し、旧 `lib/count.ts`・`playRules.ts`・`mockRules.ts` や分析側の座標計算をコピー実装として独立させない。実現方式そのものは要件書 `NFR-018` の申し送りと ADR の判断に従う。

## 6. 主所有の突合と frontend 分担

### 6.1. 突合の基準

主所有の正は [製品実装単位の設計](../product-impl-unit-split/design.md) の「4-1. 主所有(FR ごとにちょうど 1 単位)」、既存の分担の正は同書の「4-2. 分担(面の名前つき)」。下表の `FR` は番号 `001`＝`FR-001` のように読む。4-1 の最後の行は単位と FR を**同じ順番**で対応させた。`U-F1`〜`U-F14` は下表の主所有列には入れず、6.3 の分担列にだけ置く。

対象 41 件は [調査メモ](research.md) の「1. FR の帰属 — 主所有は満杯、分担だけが空いている」に従い、FR-001〜042 から**画面責務が要件だけでは判定不能な FR-031 を除いたもの**。FR-031 についても旧 `dd03160` に出力の操作入口が実在するため分担行を記録するが、41 件の被覆率の分母には入れない。6.2 の第 3 列は 6.3 の `(FR, U-F 単位)` 行を指す索引であり、同じ FR に複数の面があればすべて示す。経路の予約から主所有は導かない。

### 6.2. `(FR, 主所有単位)` の 42 ペアと frontend 行の索引

| FR | 主所有（既存 4-1 と突合） | 6.3 の frontend 分担行 |
| --- | --- | --- |
| 001 | `U-G1` | `U-F8` |
| 002 | `U-X1` | `U-F1`・`U-F4`・`U-F8` |
| 003 | `U-X1` | `U-F8` |
| 004 | `U-X1` | `U-F8` |
| 005 | `U-X1` | `U-F8` |
| 006 | `U-X1` | `U-F8` |
| 007 | `U-G2` | `U-F8` |
| 008 | `U-G1` | `U-F8` |
| 009 | `U-X1` | `U-F8` |
| 010 | `U-X1` | `U-F8` |
| 011 | `U-G2` | `U-F8` |
| 012 | `U-S1` | `U-F4`・`U-F6`・`U-F7`・`U-F8` |
| 013 | `U-R1` | `U-F6`・`U-F7`・`U-F8`・`U-F14` |
| 014 | `U-X1` | `U-F8` |
| 015 | `U-M1` | `U-F5`・`U-F8` |
| 016 | `U-M2` | `U-F8` |
| 017 | `U-M1` | `U-F5` |
| 018 | `U-M1` | `U-F5` |
| 019 | `U-D1` | `U-F8` |
| 020 | `U-X1` | `U-F8` |
| 021 | `U-X1` | `U-F8` |
| 022 | `U-X1` | `U-F8` |
| 023 | `U-X1` | `U-F8` |
| 024 | `U-P1` | `U-F8` |
| 025 | `U-X2` | `U-F10` |
| 026 | `U-X2` | `U-F10` |
| 027 | `U-X2` | `U-F10` |
| 028 | `U-X2` | `U-F10` |
| 029 | `U-X2` | `U-F10` |
| 030 | `U-X3` | `U-F12` |
| 031 | `U-D2` | `U-F8`・`U-F9`・`U-F14`（41 件の対象外） |
| 032 | `U-X4` | `U-F10` |
| 033 | `U-A1` | `U-F2`・`U-F3` |
| 034 | `U-T1` | `U-F2`・`U-F13` |
| 035 | `U-A2` | `U-F14` |
| 036 | `U-A1` | `U-F8` |
| 037 | `U-A2` | `U-F14` |
| 038 | `U-X5` | `U-F9`・`U-F14` |
| 039 | `U-M1` | `U-F5` |
| 040 | `U-X1` | `U-F8` |
| 041 | `U-C1` | `U-F11`・`U-F14` |
| 042 | `U-X2` | `U-F10` |

### 6.3. 分担表（既存 5 行と frontend の追加行）

先頭の 5 行は既存 4-2 の分担を**そのまま再掲**する。その下の `U-F*` 行だけが本書で確定する frontend の分担である。各行の「面」は動作または表示する内容を名前で示し、主所有の付け替えや経路の所有宣言にはしない。

| FR | 主所有 | 分担 | 面 |
| --- | --- | --- | --- |
| 007 | `U-G2` | `U-X1` | 下流再計算 |
| 010 | `U-X1` | `U-G1` | 終了の記録・確定の永続化 |
| 011 | `U-G2` | `U-X1` | 下流再計算 |
| 019 | `U-D1` | `U-T1` | キャッシュ無効化契約 |
| 041 | `U-C1` | `U-C2` / `U-C3` / **`U-X2`** | 制御読み取り 4 経路 / 共有出力の**認可面** 12 経路 / **共有集計の計算面**(`NFR-018` (β)・**凍結中**) |
| 001 | `U-G1` | `U-F8` | 対戦相手・先後攻・試合区分を選んで開始する操作面 |
| 002 | `U-X1` | `U-F1` | 1 球入力に使う選択ボタンと操作通知の共通部品面 |
| 002 | `U-X1` | `U-F4` | 構え・コース・球種・球速・結果を選ぶ操作手順のガイド面 |
| 002 | `U-X1` | `U-F8` | 構え・コース・球種・球速・結果の入力と 1 球確定の操作面 |
| 003 | `U-X1` | `U-F8` | 打撃結果入力後の走者・アウト・打順の即時更新表示面 |
| 004 | `U-X1` | `U-F8` | 盗塁・牽制・暴投等の入力と打球座標・捕球選手修正面 |
| 005 | `U-X1` | `U-F8` | スコア・アウト・回表裏の断中更新と終了条件の案内面 |
| 006 | `U-X1` | `U-F8` | 直前操作の取消、対象なし表示と画面状態の即時復元面 |
| 007 | `U-G2` | `U-F8` | 過去プレイの選択、修正差分の確認と確定操作面 |
| 008 | `U-G1` | `U-F8` | 進行中試合の選択と最終スコア・走者・打順・カウントの復元面 |
| 009 | `U-X1` | `U-F8` | タイブレーク開始時の走者配置・先頭打者指定面 |
| 010 | `U-X1` | `U-F8` | 終了宣言、未送信理由の表示と試合一覧の未送信バッジ面 |
| 011 | `U-G2` | `U-F8` | 投手・代打・代走・守備交代の入力と過去交代の訂正面 |
| 012 | `U-S1` | `U-F4` | 未同期キューの保持・再送を利用者に説明するガイド面 |
| 012 | `U-S1` | `U-F6` | 操作イベントのべき等キー・連番・送信拒否理由の通信契約面 |
| 012 | `U-S1` | `U-F7` | 耐久キューへの採番と不可分な追記、自動再送・単一書き手面 |
| 012 | `U-S1` | `U-F8` | 未送信件数、停止箇所と改訂・墓標・再送の操作表示面 |
| 013 | `U-R1` | `U-F6` | 記録権世代・連番と旧世代拒否理由の送受信型契約面 |
| 013 | `U-R1` | `U-F7` | 記録権世代・連番の保持と旧世代の送信抑止面 |
| 013 | `U-R1` | `U-F8` | 別端末の記録権警告と通常・緊急引き継ぎの操作面 |
| 013 | `U-R1` | `U-F14` | 退避イベントの閲覧・書き出しと条件付き取込の管理面 |
| 014 | `U-X1` | `U-F8` | 大会・試合区分の規則選択、試合別上書きと適用規則の確認面 |
| 015 | `U-M1` | `U-F5` | 選手名・投打・背番号の登録と同番号の警告面 |
| 015 | `U-M1` | `U-F8` | 交代中に画面を離れず未登録選手を追加する操作面 |
| 016 | `U-M2` | `U-F8` | 前回スタメンの選手 ID 復元と非現役枠の差し替え案内面 |
| 017 | `U-M1` | `U-F5` | 在籍区分の変更・一括変更プレビューと候補表示面 |
| 018 | `U-M1` | `U-F5` | 誤登録選手の削除確認、削除不可理由と OB 化への誘導面 |
| 019 | `U-D1` | `U-F8` | 試合削除の確認、ゴミ箱の期限表示と自己復元の操作面 |
| 020 | `U-X1` | `U-F8` | イニング別得点・H/E/K/B と X 表記のスコアボード表示面 |
| 021 | `U-X1` | `U-F8` | 登板投手の当日・シーズン成績、断中の最終取得時刻と未取得表示面 |
| 022 | `U-X1` | `U-F8` | 現打者・次打者の 7 列打席履歴・シーズン成績と代打直後の切替表示面 |
| 023 | `U-X1` | `U-F8` | 登板投手の球種割合・球数と断中の追従表示面 |
| 024 | `U-P1` | `U-F8` | 両チーム選手の成績・規則スナップショットの先読みと未取得案内面 |
| 025 | `U-X2` | `U-F10` | 投手・期間・区分等の絞り込みとコース・球種・球速・被打球チャート面 |
| 026 | `U-X2` | `U-F10` | 打者のゾーン別打率・打球方向・対左右成績と母数の表示面 |
| 027 | `U-X2` | `U-F10` | 走者状況別の作戦傾向・結果と母数の表示面 |
| 028 | `U-X2` | `U-F10` | 投手・打者カルテの統計・所見閲覧と競合を示す編集面 |
| 029 | `U-X2` | `U-F10` | 個人・チーム一括カルテ PDF の条件指定、進捗とスキップ通知面 |
| 030 | `U-X3` | `U-F12` | イニング経過・打席・投手・交代のスコアカード閲覧と PDF 出力面 |
| 031 | `U-D2` | `U-F8` | 試合・プレイ一覧からの毎球 CSV 出力操作入口面 |
| 031 | `U-D2` | `U-F9` | 88 列互換 CSV とサイドカーの試合単位ダウンロード操作面 |
| 031 | `U-D2` | `U-F14` | 管理者の試合横断一覧からの試合単位 CSV 保存面 |
| 032 | `U-X4` | `U-F10` | 対象・条件指定と範囲ラベル・母数付き分析 PDF の出力面 |
| 033 | `U-A1` | `U-F2` | 認証主体・トークンのセッション保持と失効反映面 |
| 033 | `U-A1` | `U-F3` | チーム名・パスワード入力と拒否時の情報を漏らさないエラー表示面 |
| 034 | `U-T1` | `U-F2` | チーム ID・役割を保持して画面と通信へ渡す認可源面 |
| 034 | `U-T1` | `U-F13` | 認証状態・役割によるアクセス入口の制御面 |
| 035 | `U-A2` | `U-F14` | 管理者認証、チーム登録・無効化と選手統合の影響確認面 |
| 036 | `U-A1` | `U-F8` | 現行パスワードを伴う変更と旧トークン失効後の再ログイン案内面 |
| 037 | `U-A2` | `U-F14` | チーム・選手・スタメン・試合の横断一覧、操作ログとシステム設定の管理面 |
| 038 | `U-X5` | `U-F9` | 88 列取込ファイルの検証結果・警告・確定を示す操作面 |
| 038 | `U-X5` | `U-F14` | 全データ一括移行の確認、件数突合・名寄せ・隔離レポート表示面 |
| 039 | `U-M1` | `U-F5` | 対戦相手チームの登録・類似名警告と自テナント内ロスター管理面 |
| 040 | `U-X1` | `U-F8` | 得点・アウト・走者・打順の補正入力と差分履歴表示面 |
| 041 | `U-C1` | `U-F11` | 共同分析グループの付与・比較対象選択と許可範囲の集計表示面 |
| 041 | `U-C1` | `U-F14` | 管理者による招待発行・失効、参加・離脱、付与・役割変更と終了の操作面 |
| 042 | `U-X2` | `U-F10` | チーム打率・出塁率・長打率・イニング別得失点と母数の表示面 |

FR-020〜023 の分担は**記録中の具体的な表示**に限る。4 件の主所有は 6.2 のとおり `U-X1` に固定し、断中に必要なクライアント計算は 5.5 の `NFR-018` 境界に従う。FR-038 の `U-F9` は 88 列ファイルの取込操作、`U-F14` はシステム管理者の全データ一括移行・検証の操作であり、両者を同じ完成条件とは扱わない。

### 6.4. 多重集合と対象 41 FR の被覆検算

4-1 の主所有表から得た `(FR, 主所有単位)` の多重集合と、6.2 の第 1・2 列から得た多重集合を**ペア単位**で突合した。4-1 の最終行は列内の順序で 11 ペアに展開した。結果は **4-1 にだけあるペア 0 件／6.2 にだけあるペア 0 件**で、42 ペアが 1 件残らず一致した。FR ごとの件数も多重集合で数え、**延べ 42／一意 42／多重度 max 1**。件数だけでは主所有者の入れ替えを見逃すため、ペアの差分が空であることを判定に使った。

6.2 の第 3 列と 6.3 の frontend 行を `(FR, U-F 単位)` で突合し、**索引にだけある行 0 件／分担表にだけある行 0 件**を確認した。対象 41 FR はそれぞれ第 3 列に少なくとも 1 つの `U-F` 行を持ち、**被覆 41/41 件**。frontend の面が 1 つもない対象 FR は**0 件（該当なし）**。FR-031 は分母から除外したが、6.3 に 3 件の具体的な出力操作面を記録した。frontend 分担行は **57 件**で、「面」空欄は **0 件**である。
