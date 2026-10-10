import { QueryClient } from '@tanstack/vue-query'

const queryDefaults = {
  retry: 1,
  refetchOnWindowFocus: false,
  staleTime: 30_000,
}

// アプリ全体で共有するクエリキャッシュ。
// 認証が変わったときのテナント所有データの消去は認証状態側（U-F2）が行う。
export const queryClient = new QueryClient({
  defaultOptions: { queries: queryDefaults },
})
