import { getActivePinia } from 'pinia'
import { shallowRef, watch, type ShallowRef } from 'vue'
import {
  createRouter,
  createWebHistory,
  type RouterHistory,
  type Router,
} from 'vue-router'
import { ensureSessionVerified } from './api/auth'
import { pinia } from './appProviders'
import StrikeZoneCompareHost from './components/zone/StrikeZoneCompareHost.vue'
import HelpScreen from './screens/HelpScreen.vue'
import LoginScreen from './screens/LoginScreen.vue'
import TeamScreen from './screens/TeamScreen.vue'
import GameScreenEntryHost from './screens/GameScreenEntryHost.vue'
import GameArchiveScreen from './screens/GameArchiveScreen.vue'
import StartScreen from './screens/StartScreen.vue'
import GameStatsScreen from './screens/GameStatsScreen.vue'
import SeasonStats from './screens/SeasonStats.vue'
import GameScreenRecordModeHost from './screens/GameScreenRecordModeHost.vue'
import GameScreenRecordingRightHandover from './screens/GameScreenRecordingRightHandover.vue'
import GameLineupChangeScreen from './screens/GameLineupChangeScreen.vue'
import {
  LocalRecordingSession,
  isLocalRecordingSession,
  recordingBackendReachability,
} from './lib/localRecordingSession'
import GameExportScreen from './screens/GameExportScreen.vue'
import GameScreenViewerLive from './screens/GameScreenViewerLive.vue'
import { resolveGameEntryReturnPath } from './screens/GameScreenEntryNavigation'
import { useAuthStore } from './stores/authStore'

type LocalEntry = { path: string; session: LocalRecordingSession }
const localGates = new WeakMap<
  Router,
  { entry: ShallowRef<LocalEntry | null>; transitioning: ShallowRef<boolean> }
>()

/** routerが実際に受け入れた同じ記録入口だけの表示資格。HTTP認証とは別。 */
export function currentLocalRecordingSession(
  router: Router,
): LocalRecordingSession | null {
  const entry = localGates.get(router)?.entry.value
  return entry &&
    router.currentRoute.value.name === 'game-record' &&
    entry.path === router.currentRoute.value.fullPath &&
    isLocalRecordingSession(entry.session) &&
    entry.session.current
    ? entry.session
    : null
}
/** 同じ端末内記録から再接続中は保護内容を隠してguardの結論を待つ。 */
export function localRecordingTransition(router: Router): boolean {
  return (
    router.currentRoute.value.name === 'game-record' &&
    localGates.get(router)?.transitioning.value === true
  )
}

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const localEntry = shallowRef<LocalEntry | null>(null)
  const transitioning = shallowRef(false)
  const router = createRouter({
    history,
    routes: [
      {
        path: '/',
        name: 'home',
        component: StartScreen,
        meta: { requiresAuth: true },
      },
      {
        path: '/design/strike-zone',
        name: 'design-strike-zone',
        component: StrikeZoneCompareHost,
      },
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
        path: '/games/archive',
        name: 'games-archive',
        component: GameArchiveScreen,
        meta: { requiresAuth: true },
      },
      {
        path: '/games/:gameId/export',
        name: 'game-export',
        component: GameExportScreen,
        meta: { requiresAuth: true },
      },
      {
        path: '/games/:gameId/view',
        name: 'game-viewer',
        component: GameScreenViewerLive,
        meta: { requiresAuth: true },
      },
      {
        path: '/games/:gameId/lineup',
        name: 'game-lineup',
        component: GameLineupChangeScreen,
        meta: { requiresAuth: true },
      },
      {
        path: '/games/:gameId/record',
        name: 'game-record',
        component: GameScreenRecordModeHost,
        props: (route) => ({
          localSession:
            localEntry.value?.path === route.fullPath
              ? localEntry.value.session
              : undefined,
        }),
        meta: { requiresAuth: true },
      },
      {
        path: '/games/:gameId/handover',
        name: 'game-handover',
        component: GameScreenRecordingRightHandover,
        meta: { requiresAuth: true },
      },
      {
        path: '/games/:gameId/stats',
        name: 'game-stats',
        component: GameStatsScreen,
        meta: { requiresAuth: true },
      },
      {
        path: '/stats/season',
        name: 'season-stats',
        component: SeasonStats,
        meta: { requiresAuth: true },
      },
    ],
  })
  localGates.set(router, { entry: localEntry, transitioning })
  router.afterEach(() => {
    transitioning.value = false
  })
  router.onError(() => {
    transitioning.value = false
  })
  router.beforeEach(async (to) => {
    const previous = localEntry.value
    transitioning.value =
      previous !== null &&
      previous.session.current &&
      router.currentRoute.value.name === 'game-record'
    previous?.session.dispose()
    localEntry.value = null
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
          if (
            reachability === 'unavailable' &&
            saved.current &&
            getActivePinia() === pinia
          ) {
            localEntry.value = { path: to.fullPath, session: saved }
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
