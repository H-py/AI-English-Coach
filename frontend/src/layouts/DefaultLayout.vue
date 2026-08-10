<script setup lang="ts">
import { useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import AppHeader from './components/AppHeader.vue'

/**
 * 默认布局：侧边栏 + 顶栏 + 内容区。
 *
 * 常规页面在内容区限制最大宽度并居中；当路由 meta.fullHeight 为 true 时
 * （如智能学习页面），内容区占满可用空间，不施加 max-width 和 padding，
 * 以支持全屏交互式界面。
 */
const route = useRoute()
</script>

<template>
  <div
    class="flex h-screen w-full overflow-hidden bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100"
  >
    <AppSidebar />

    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <AppHeader />

      <main class="flex-1 overflow-y-auto">
        <!-- 全屏页面：不加 max-width 和 padding -->
        <RouterView v-if="route.meta.fullHeight" />

        <!-- 常规页面：居中限宽 -->
        <div v-else class="mx-auto w-full max-w-7xl px-6 py-8 sm:px-8 lg:px-10">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
</template>
