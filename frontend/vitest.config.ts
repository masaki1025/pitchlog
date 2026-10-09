import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // 外部検査器を起動する閉域 spec と他ファイルを競合させず、検査内容は維持する。
      fileParallelism: false,
    },
  }),
)
