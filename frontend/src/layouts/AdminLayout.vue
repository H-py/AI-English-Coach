<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import { useAuth } from '@/composables/useAuth'
import AppLogo from '@/components/AppLogo.vue'

/**
 * 管理后台布局：侧边栏 + 顶栏 + 内容区。
 * 与 DefaultLayout 独立，使用 admin 专属导航项，
 * 底部提供「返回前台」入口。
 */

interface NavItem {
  name: string
  to: string
  icon: string
}

const icons: Record<string, string> = {
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  articles: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z M4 19.5A2.5 2.5 0 0 0 6.5 22H20',
  users: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
  back: 'M19 12H5 M12 19l-7-7 7-7'
}

const auth = useAuthStore()
const { toggleTheme, isDark } = useTheme()
const { logout } = useAuth()
const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const navItems = computed<NavItem[]>(() => [
  { name: 'dashboard', to: '/admin', icon: 'dashboard' },
  { name: 'articles', to: '/admin/articles', icon: 'articles' },
  { name: 'users', to: '/admin/users', icon: 'users' }
])

function isActive(to: string): boolean {
  if (to === '/admin') return route.path === '/admin'
  return route.path.startsWith(to)
}

function goBackToSite(): void {
  router.push('/')
}
</script>

<template>
  <div
    class="flex h-screen w-full overflow-hidden bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100"
  >
    <!-- 侧边栏 -->
    <aside
      class="flex h-screen w-60 flex-shrink-0 flex-col border-r border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900"
    >
      <!-- Logo 区 -->
      <div class="flex h-16 items-center border-b border-neutral-100 px-4 dark:border-neutral-800">
        <AppLogo />
      </div>

      <!-- 管理后台标识 -->
      <div class="px-4 py-3">
        <span class="text-xs font-medium uppercase tracking-wider text-neutral-400 dark:text-neutral-600">
          {{ t('admin.title') }}
        </span>
      </div>

      <!-- 导航 -->
      <nav class="flex-1 space-y-1 px-2">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="item.to"
          class="nav-link"
          :class="{ active: isActive(item.to) }"
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
          <span class="nav-label">{{ t(`admin.nav.${item.name}`) }}</span>
        </RouterLink>
      </nav>

      <!-- 底部：返回前台 + 登出 -->
      <div class="space-y-1 border-t border-neutral-100 px-2 py-3 dark:border-neutral-800">
        <button class="nav-link w-full" @click="goBackToSite">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path :d="icons.back" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span class="nav-label">{{ t('admin.nav.backToSite') }}</span>
        </button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <!-- 顶栏 -->
      <header
        class="flex h-16 flex-shrink-0 items-center justify-between border-b border-neutral-200 bg-white/80 px-6 backdrop-blur-md dark:border-neutral-800 dark:bg-neutral-900/80"
      >
        <span class="text-sm font-medium text-neutral-500 dark:text-neutral-400">
          {{ auth.user?.username }} · {{ t('admin.title') }}
        </span>

        <div class="flex items-center gap-2">
          <button
            class="header-btn"
            :title="t('common.toggleTheme')"
            @click="toggleTheme()"
          >
            <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
              <circle cx="12" cy="12" r="4" />
              <path
                d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
                stroke-linecap="round"
              />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
              <path
                d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>

          <NButton quaternary size="small" @click="logout">
            {{ t('auth.logout') }}
          </NButton>
        </div>
      </header>

      <!-- 内容 -->
      <main class="flex-1 overflow-y-auto">
        <div class="mx-auto w-full max-w-7xl px-6 py-8 sm:px-8 lg:px-10">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
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
  cursor: pointer;
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
.header-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.5rem;
  color: #525252;
  transition: background-color 0.15s ease, color 0.15s ease;
}
.header-btn:hover {
  background-color: #f5f5f5;
  color: #171717;
}
.header-btn svg {
  width: 1.15rem;
  height: 1.15rem;
}
:global(html.dark) .header-btn {
  color: #a3a3a3;
}
:global(html.dark) .header-btn:hover {
  background-color: #262626;
  color: #f5f5f5;
}
</style>
