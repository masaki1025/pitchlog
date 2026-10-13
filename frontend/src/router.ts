import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'
import StrikeZoneCompareHost from './components/zone/StrikeZoneCompareHost.vue'
import HelpScreen from './screens/HelpScreen.vue'

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  return createRouter({
    history,
    routes: [
      { path: '/', name: 'home', component: StrikeZoneCompareHost },
      { path: '/help', name: 'help', component: HelpScreen },
    ],
  })
}

export const router = createAppRouter()
