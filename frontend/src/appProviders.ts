import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import type { App } from 'vue'
import { queryClient } from './lib/queryClient'

// 認証状態とクエリキャッシュを全画面で同じインスタンスに保つ。
export const pinia = createPinia()

export function installAppProviders(app: App): App {
  return app.use(pinia).use(VueQueryPlugin, { queryClient })
}
