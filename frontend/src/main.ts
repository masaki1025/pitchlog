import { createApp } from 'vue'
import './index.css'
import App from './App.vue'
import { installAppProviders } from './appProviders'
import { router } from './router'
import { registerServiceWorker } from './lib/registerServiceWorker'

installAppProviders(createApp(App)).use(router).mount('#app')
void registerServiceWorker().catch(() => {
  // 静的 bundle を確定保存できない場合、認証・記録資格を補完しない。
})
