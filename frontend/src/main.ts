import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { i18n } from './locales'

// 全局样式（Tailwind 三件套 + 基础重置）
import './styles/index.css'

const app = createApp(App)

// 状态管理
const pinia = createPinia()
app.use(pinia)

// 用持久化的语言偏好初始化 i18n（store 依赖 pinia，需在 pinia 安装后读取）
import { useAppStore } from '@/stores/app'
const appStore = useAppStore()
i18n.global.locale.value = appStore.locale

// 路由 & 国际化
app.use(router)
app.use(i18n)

// Naive UI 的 message / dialog / notification provider 统一在 App.vue 顶层包裹，
// 此处仅挂载全局插件，保证 provider 树完整后再渲染 RouterView。
app.mount('#app')
