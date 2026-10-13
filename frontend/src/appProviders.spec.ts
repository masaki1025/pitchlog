import { useQueryClient } from '@tanstack/vue-query'
import { createApp, defineComponent, h } from 'vue'
import { describe, expect, it } from 'vitest'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './stores/authStore'
import { installAppProviders, pinia } from './appProviders'

describe('アプリの共有 provider', () => {
  it('認証ストアとクエリに同じインスタンスを渡す', () => {
    let authStore: ReturnType<typeof useAuthStore> | undefined
    let installedQueryClient: ReturnType<typeof useQueryClient> | undefined
    const Probe = defineComponent({
      setup() {
        authStore = useAuthStore()
        installedQueryClient = useQueryClient()
        return () => h('span', 'ready')
      },
    })
    const app = installAppProviders(createApp(Probe))

    app.mount(document.createElement('div'))

    expect(authStore).toBe(useAuthStore(pinia))
    expect(installedQueryClient).toBe(queryClient)
    app.unmount()
  })
})
