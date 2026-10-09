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
