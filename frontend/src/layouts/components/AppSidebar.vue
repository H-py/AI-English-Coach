<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import AppLogo from '@/components/AppLogo.vue'

interface NavItem {
  name: string
  to: string
  icon: string
}

// Lucide 风格的极简线性图标 path（stroke-based）
const icons: Record<string, string> = {
  home: 'M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  smartLearning: 'M12 3l2 7 7 2-7 2-2 7-2-7-7-2 7-2 2-7z',
  reading: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z M4 19.5A2.5 2.5 0 0 0 6.5 22H20',
  vocabulary: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z M8 7h8 M8 11h6',
  sentences: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  history: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2',
  modelConfig: 'M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6',
  profile: 'M20 21a8 8 0 0 0-16 0 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z'
}

const app = useAppStore()
const { sidebarCollapsed } = storeToRefs(app)
const route = useRoute()
const { t } = useI18n()

const navItems = computed<NavItem[]>(() => [
  { name: 'home', to: '/', icon: 'home' },
  { name: 'smartLearning', to: '/smart-learning', icon: 'smartLearning' },
  { name: 'articles', to: '/articles', icon: 'reading' },
  { name: 'vocabulary', to: '/vocabulary', icon: 'vocabulary' },
  { name: 'sentences', to: '/sentences', icon: 'sentences' },
  { name: 'history', to: '/history', icon: 'history' },
  { name: 'modelConfig', to: '/model-config', icon: 'modelConfig' },
  { name: 'profile', to: '/profile', icon: 'profile' }
])

function isActive(to: string): boolean {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}
</script>

<template>
  <aside
    class="flex h-screen flex-shrink-0 flex-col border-r border-neutral-200 bg-white transition-[width] duration-200 ease-in-out dark:border-neutral-800 dark:bg-neutral-900"
    :class="sidebarCollapsed ? 'w-16' : 'w-60'"
  >
    <!-- Logo 区 -->
    <div
      class="flex h-16 items-center border-b border-neutral-100 px-4 dark:border-neutral-800"
      :class="{ 'justify-center px-0': sidebarCollapsed }"
    >
      <AppLogo :compact="sidebarCollapsed" />
    </div>

    <!-- 导航 -->
    <nav class="flex-1 space-y-1 px-2 py-4">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.to"
        class="nav-link"
        :class="{ active: isActive(item.to) }"
        :title="t(`nav.${item.name}`)"
      >
        <svg
          class="nav-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path :d="icons[item.icon]" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span v-if="!sidebarCollapsed" class="nav-label">{{ t(`nav.${item.name}`) }}</span>
      </RouterLink>
    </nav>

    <!-- 底部留白占位（后续可放用户/设置入口） -->
    <div class="h-2" />
  </aside>
</template>

<style scoped>
.nav-link {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  color: #525252;
  transition: background-color 0.15s ease, color 0.15s ease;
}
:global(html.dark) .nav-link {
  color: #a3a3a3;
}
.nav-link:hover {
  background-color: #f5f5f5;
  color: #171717;
}
:global(html.dark) .nav-link:hover {
  background-color: #262626;
  color: #f5f5f5;
}
.nav-link.active {
  background-color: #f4f4f5;
  color: #171717;
  font-weight: 500;
}
:global(html.dark) .nav-link.active {
  background-color: #262626;
  color: #f5f5f5;
}
.nav-icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}
.nav-label {
  white-space: nowrap;
}
</style>
