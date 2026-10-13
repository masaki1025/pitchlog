import { createApp } from 'vue'
import './index.css'
import App from './App.vue'
import { installAppProviders } from './appProviders'
import { router } from './router'

installAppProviders(createApp(App)).use(router).mount('#app')
