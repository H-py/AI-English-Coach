<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NButton, NText } from 'naive-ui'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import { useAuth } from '@/composables/useAuth'
import { i18n } from '@/locales'

/**
 * 顶栏：左侧折叠按钮，右侧语言切换 + 主题切换 + 用户区域。
 * 极简、毛玻璃背景，强调留白。
 * 用户区域：已登录显示头像 + 用户名 + 登出，未登录显示登录入口。
 */
const app = useAppStore()
const auth = useAuthStore()
const { sidebarCollapsed } = storeToRefs(app)
const { isAuthenticated, user } = storeToRefs(auth)
const { toggleTheme, isDark } = useTheme()
const { logout } = useAuth()
const router = useRouter()
const { t } = useI18n()

/** 头像回退：无 avatar_url 时取用户名首字母大写 */
const userInitial = computed(() => user.value?.username?.charAt(0).toUpperCase() ?? '?')

function toggleLocale(): void {
  const next = app.locale === 'zh' ? 'en' : 'zh'
  app.setLocale(next)
  i18n.global.locale.value = next
}

function goLogin(): void {
  router.push('/login')
}
</script>

<template>
  <header
    class="flex h-16 flex-shrink-0 items-center justify-between border-b border-neutral-200 bg-white/80 px-4 backdrop-blur-md dark:border-neutral-800 dark:bg-neutral-900/80 sm:px-6"
  >
    <!-- 左：折叠按钮 -->
    <button
      class="header-btn"
      :title="t('common.toggleSidebar')"
      @click="app.toggleSidebar()"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
        <path
          :d="sidebarCollapsed
            ? 'M4 6h16M4 12h16M4 18h16'
            : 'M4 6h10M4 12h16M4 18h10'"
          stroke-linecap="round"
        />
      </svg>
    </button>

    <!-- 右：语言 + 主题 -->
    <div class="flex items-center gap-1.5">
      <button class="header-btn lang" :title="t('common.language')" @click="toggleLocale">
        {{ app.locale === 'zh' ? '中' : 'EN' }}
      </button>

      <button
        class="header-btn"
        :title="t('common.toggleTheme')"
        @click="toggleTheme()"
      >
        <!-- 月亮（暗色时显示，点击切到亮色） -->
        <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <circle cx="12" cy="12" r="4" />
          <path
            d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
            stroke-linecap="round"
          />
        </svg>
        <!-- 月亮（亮色时显示，点击切到暗色） -->
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <path
            d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      <!-- 分隔线 -->
      <span class="mx-1 h-5 w-px bg-neutral-200 dark:bg-neutral-700" />

      <!-- 用户区域 -->
      <template v-if="isAuthenticated">
        <div class="flex items-center gap-2">
          <!-- 头像：有 avatar_url 显示图片，否则显示用户名首字母 -->
          <img
            v-if="user?.avatar_url"
            :src="user.avatar_url"
            :alt="user?.username ?? ''"
            class="h-8 w-8 flex-shrink-0 rounded-full object-cover"
          />
          <div
            v-else
            class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-600 dark:bg-blue-500/20 dark:text-blue-400"
          >
            {{ userInitial }}
          </div>
          <NText class="user-name" depth="2">{{ user?.username }}</NText>
        </div>
        <NButton quaternary size="small" @click="logout">
          {{ t('auth.logout') }}
        </NButton>
      </template>
      <NButton v-else quaternary size="small" @click="goLogin">
        {{ t('auth.login') }}
      </NButton>
    </div>
  </header>
</template>

<style scoped>
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
.header-btn.lang {
  width: 2.25rem;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.user-name {
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  max-width: 8rem;
  overflow: hidden;
  text-overflow: ellipsis;
}
:global(html.dark) .header-btn {
  color: #a3a3a3;
}
:global(html.dark) .header-btn:hover {
  background-color: #262626;
  color: #f5f5f5;
}
</style>
