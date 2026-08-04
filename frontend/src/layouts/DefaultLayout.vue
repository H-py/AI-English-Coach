<script setup lang="ts">
import AppSidebar from './components/AppSidebar.vue'
import AppHeader from './components/AppHeader.vue'

/**
 * 默认布局：侧边栏 + 顶栏 + 内容区。
 * 内容区限制最大宽度并居中，在宽屏下充分利用空间。
 */
</script>

<template>
  <div
    class="flex h-screen w-full overflow-hidden bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100"
  >
    <AppSidebar />

    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <AppHeader />

      <main class="flex-1 overflow-y-auto">
        <div class="mx-auto w-full max-w-7xl px-6 py-8 sm:px-8 lg:px-10">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
</template>
