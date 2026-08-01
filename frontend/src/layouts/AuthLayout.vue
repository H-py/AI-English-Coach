<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppLogo from '@/components/AppLogo.vue'

/**
 * 认证页独立布局（登录 / 注册）。
 * 极简：垂直水平居中，无侧边栏无顶栏。
 * 顶部 Logo + 应用名，中间渲染子路由视图，底部版权小字。
 */
const { t } = useI18n()

const year = new Date().getFullYear()
</script>

<template>
  <div
    class="flex min-h-screen flex-col items-center justify-center bg-neutral-50 px-4 py-10 dark:bg-neutral-950"
  >
    <!-- 顶部：Logo + 应用名 -->
    <div class="mb-8">
      <AppLogo />
    </div>

    <!-- 中间：卡片容器承载子路由视图 -->
    <main
      class="w-full max-w-sm rounded-2xl border border-neutral-200 bg-white p-8 shadow-sm dark:border-neutral-800 dark:bg-neutral-900"
    >
      <RouterView />
    </main>

    <!-- 底部：版权小字 -->
    <footer class="mt-8 text-center text-xs text-neutral-400 dark:text-neutral-600">
      © {{ year }} {{ t('app.name') }}
    </footer>
  </div>
</template>
