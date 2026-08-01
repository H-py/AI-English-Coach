<script setup lang="ts">
import { computed } from 'vue'
import {
  NConfigProvider,
  NLoadingBarProvider,
  NMessageProvider,
  NDialogProvider,
  NNotificationProvider,
  zhCN,
  dateZhCN,
  enUS,
  dateEnUS
} from 'naive-ui'
import { useTheme } from '@/composables/useTheme'
import { useAppStore } from '@/stores/app'

/**
 * 根组件：在最顶层包裹 Naive UI 全局 Provider 链。
 * 顺序：ConfigProvider -> LoadingBar -> Message -> Dialog -> Notification -> RouterView
 * 这样任意子组件 / api 拦截器都能安全调用对应的离散 API。
 */
const { naiveTheme, themeOverrides } = useTheme()
const app = useAppStore()

const naiveLocale = computed(() => (app.locale === 'zh' ? zhCN : enUS))
const naiveDateLocale = computed(() => (app.locale === 'zh' ? dateZhCN : dateEnUS))
</script>

<template>
  <NConfigProvider
    :theme="naiveTheme"
    :theme-overrides="themeOverrides"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
  >
    <NLoadingBarProvider>
      <NMessageProvider>
        <NDialogProvider>
          <NNotificationProvider>
            <RouterView />
          </NNotificationProvider>
        </NDialogProvider>
      </NMessageProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>
