# ステップ6の入口・ログイン復帰の最小追補候補（未承認・未適用）

## 根拠と変更範囲

承認計画3節はGameScreen*とrouter*を入口の変更範囲にしている。一方、既存App.vueのfinishLoginは/teamに固定し、認証失効時もredirect=/team、homeのヘッダーに試合へのリンクがない。App.vueを編集せずrouterだけで後追い再遷移させる回避は採らず、入口の責任を分かる場所へ置く。

推奨はステップ6の非正本変更範囲へ **frontend/src/App.vueだけを追加**すること。下記の未適用パッチで、試合リンクと認証前後の安全な戻り先をつなぐ。実装時は、既に範囲内のGameScreenEntryNavigation.tsが/team・/games・正規gameIdの/games/:gameId/recordだけを返し、外部URL/二重slash/不正ID/query/hashは/teamへ倒す。既存のauthEpoch/認証再検証/tenant一致を緩めない。Appのその他動作は変えない。

新しい正式API・記録権・状態計算・署名・公開・Draft解除・マージを含まない。未接続の開始/再開/記録は封鎖を維持する。別案はAppの追補を保留し、ステップ6を直接URLからの入口と隔離route試験まで提出して、ログイン後復帰/通常ナビゲーションを未達とすること。

## 未適用パッチ

```diff
--- a/frontend/src/App.vue
+++ b/frontend/src/App.vue
@@ -2,6 +2,7 @@
 import { CircleHelp } from 'lucide-vue-next'
 import { computed, watch } from 'vue'
 import { useAuthStore } from './stores/authStore'
+import { resolveGameEntryReturnPath } from './screens/GameScreenEntryNavigation'
 import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
 
 const route = useRoute()
@@ -15,7 +16,10 @@
   () => [auth.authEpoch, protectedReady.value, route.name],
   () => {
     if (route.meta.requiresAuth === true && !protectedReady.value) {
-      void router.replace({ name: 'login', query: { redirect: '/team' } })
+      void router.replace({
+        name: 'login',
+        query: { redirect: resolveGameEntryReturnPath(route.path) },
+      })
     }
   },
 )
@@ -23,8 +27,8 @@
 async function finishLogin(): Promise<void> {
   auth.syncFromStorage()
   if (!protectedReady.value) return
-  // この縦断で許す戻り先は/teamだけ。外部URLや未完成経路を解釈しない。
-  await router.replace({ name: 'team' })
+  // 登録済みのチーム/試合入口だけに戻し、外部URLは解釈しない。
+  await router.replace(resolveGameEntryReturnPath(route.query.redirect))
 }
 
 async function returnToHome(): Promise<void> {
@@ -36,6 +40,12 @@
   <main>
     <header v-if="route.name === 'home'" class="flex items-center gap-3 p-4">
       <h1 class="text-xl font-extrabold">PitchLog</h1>
+      <RouterLink
+        :to="{ name: 'games' }"
+        class="min-h-12 px-3 py-3 font-bold"
+      >
+        試合
+      </RouterLink>
       <RouterLink
         :to="{ name: 'team' }"
         class="ml-auto min-h-12 px-3 py-3 font-bold"
```

パッチはgit apply --checkの適用可能性だけを確認し、App.vueへ実適用していない。GameScreenEntryNavigationの実装・Appと組み合わせた試験はステップ6で行う。テスト観点は、匿名/未確認のgames遷移→login、再検証済み同一tenantだけが復帰、正規記録routeへの復帰、外部URL/不正ID拒否、認証失効時の画面封鎖と意図保持、既存/teamへの復帰維持。未承認の追補を既承認の実装開始許可へ流用しない。
