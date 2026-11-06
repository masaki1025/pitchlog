import { getActivePinia } from 'pinia'
import { watch } from 'vue'
import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'
import { ensureSessionVerified } from './api/auth'
import { pinia } from './appProviders'
import StrikeZoneCompareHost from './components/zone/StrikeZoneCompareHost.vue'
import HelpScreen from './screens/HelpScreen.vue'
import LoginScreen from './screens/LoginScreen.vue'
import TeamScreen from './screens/TeamScreen.vue'
import GameScreenEntryHost from './screens/GameScreenEntryHost.vue'
import GameScreenRecordModeHost from './screens/GameScreenRecordModeHost.vue'
import {
  LocalRecordingSession,
  recordingBackendReachability,
} from './lib/localRecordingSession'
import { resolveGameEntryReturnPath } from './screens/GameScreenEntryNavigation'
import { useAuthStore } from './stores/authStore'

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  let localEntry: { path: string; session: LocalRecordingSession } | null = null
  const router = createRouter({
    history,
    routes: [
      { path: '/', name: 'home', component: StrikeZoneCompareHost },
      { path: '/help', name: 'help', component: HelpScreen },
      {
        path: '/login',
        name: 'login',
        component: LoginScreen,
      },
      {
        path: '/team',
        name: 'team',
        component: TeamScreen,
        meta: { requiresAuth: true },
      },
      {
        path: '/games',
        name: 'games',
        component: GameScreenEntryHost,
        meta: { requiresAuth: true },
      },
      {
        path: '/games/:gameId/record',
        name: 'game-record',
        component: GameScreenRecordModeHost,
        props: (route) => ({
          localSession:
            localEntry?.path === route.fullPath
              ? localEntry.session
              : undefined,
        }),
        meta: { requiresAuth: true },
      },
    ],
  })
  router.beforeEach(async (to) => {
    localEntry?.session.dispose()
    localEntry = null
    if (to.meta.requiresAuth !== true) return true
    const loginRoute = {
      name: 'login',
      query: { redirect: resolveGameEntryReturnPath(to.fullPath) },
      replace: true,
    }
    if (getActivePinia() !== pinia) return loginRoute
    const auth = useAuthStore(pinia)
    if (!auth.hasHydrated) {
      await new Promise<void>((resolve) => {
        const stop = watch(
          () => auth.hasHydrated,
          (hydrated) => {
            if (hydrated) {
              stop()
              resolve()
            }
          },
        )
      })
    }
    try {
      if (getActivePinia() !== pinia) return loginRoute
      // HTTP認証を成功扱いにせず、真正保存原本のある記録入口だけを端末内へ戻す。
      if (to.name === 'game-record' && typeof to.params.gameId === 'string') {
        const saved = await LocalRecordingSession.restore(
          to.params.gameId,
        ).catch(() => null)
        if (saved) {
          const reachability = await recordingBackendReachability()
          if (reachability === 'unavailable' && saved.current) {
            localEntry = { path: to.fullPath, session: saved }
            return true
          }
          saved.dispose()
        }
      }
      const result = await ensureSessionVerified()
      auth.syncFromStorage()
      if (
        result.status === 'authenticated' &&
        result.authEpoch === auth.authEpoch &&
        auth.isAuthenticated &&
        auth.teamId !== null &&
        auth.teamId === result.tenantId
      )
        return true
    } catch {
      // 未確認や進行中の認証操作から保護画面を開始しない。
    }
    return loginRoute
  })
  return router
}

export const router = createAppRouter()
