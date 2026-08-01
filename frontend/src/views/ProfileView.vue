<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NSelect, NButton, NSpin, useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { readingApi } from '@/api/reading'
import { useAuth } from '@/composables/useAuth'
import type { EnglishLevel } from '@/types/auth'

/**
 * 个人中心 / 设置页。
 *
 * 展示当前登录用户的基本信息（用户名、邮箱、头像、注册时间、最近登录时间）
 * 与学习概览统计（与首页一致的 4 项指标），并支持切换英语水平等级。
 *
 * 数据在 onMounted 时并行拉取：
 *  - 用户信息来自 auth store（登录后已持久化）；
 *  - 统计通过 readingApi 并行获取，使用 Promise.allSettled 保证单项失败不影响其余展示。
 * 切换英语水平调用 authApi.updateMe 并同步更新 auth store；登出复用 useAuth.logout。
 */

const { t } = useI18n()
const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()
const { logout } = useAuth()

// ============================================================
//  用户信息
// ============================================================

const user = computed(() => authStore.user)

/** 头像回退：无 avatar_url 时取用户名首字母大写 */
const userInitial = computed(() => user.value?.username?.charAt(0).toUpperCase() ?? '?')

// ============================================================
//  时间格式化
// ============================================================

/** 格式化 ISO 时间字符串为本地可读时间 */
function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// ============================================================
//  英语水平选择
// ============================================================

const levelOptions = computed(() => [
  { label: t('profile.levelOptions.beginner'), value: 'beginner' },
  { label: t('profile.levelOptions.intermediate'), value: 'intermediate' },
  { label: t('profile.levelOptions.advanced'), value: 'advanced' }
])

const selectedLevel = ref<EnglishLevel>(user.value?.english_level ?? 'beginner')
const levelUpdating = ref(false)

/**
 * 切换英语水平：
 *  乐观更新选中值 -> 调用 authApi.updateMe -> 同步 auth store；
 *  失败时回退到 store 中的当前水平，错误提示由 axios 拦截器统一处理。
 */
async function handleLevelChange(value: string | number): Promise<void> {
  const level = value as EnglishLevel
  selectedLevel.value = level
  levelUpdating.value = true
  try {
    const updated = await authApi.updateMe({ english_level: level })
    authStore.setUser(updated)
    selectedLevel.value = updated.english_level
    message.success(t('profile.levelUpdated'))
  } catch {
    // 错误由 axios 拦截器统一提示；回退选中值
    selectedLevel.value = user.value?.english_level ?? 'beginner'
  } finally {
    levelUpdating.value = false
  }
}

// ============================================================
//  学习概览统计
// ============================================================

interface StatItem {
  /** i18n 标签 key */
  labelKey: string
  value: number
  /** 图标 path（Lucide 风格，stroke-based，单 path 多子路径） */
  icon: string
  /** 图标背景色类 */
  iconBgClass: string
  /** 图标前景色类 */
  iconTextClass: string
}

/** Lucide 风格线性图标 path（24×24 viewBox，stroke-based） */
const ICONS = {
  bookmark: 'm19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z',
  messageSquare: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  history:
    'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2',
  bookOpen:
    'M12 7v14 M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z'
} as const

const statsLoading = ref(false)
const stats = ref<StatItem[]>([
  {
    labelKey: 'profile.wordsCollected',
    value: 0,
    icon: ICONS.bookmark,
    iconBgClass: 'bg-blue-50 dark:bg-blue-500/10',
    iconTextClass: 'text-blue-500 dark:text-blue-400'
  },
  {
    labelKey: 'profile.sentencesCollected',
    value: 0,
    icon: ICONS.messageSquare,
    iconBgClass: 'bg-emerald-50 dark:bg-emerald-500/10',
    iconTextClass: 'text-emerald-500 dark:text-emerald-400'
  },
  {
    labelKey: 'profile.readingSessions',
    value: 0,
    icon: ICONS.history,
    iconBgClass: 'bg-amber-50 dark:bg-amber-500/10',
    iconTextClass: 'text-amber-500 dark:text-amber-400'
  },
  {
    labelKey: 'profile.articlesRead',
    value: 0,
    icon: ICONS.bookOpen,
    iconBgClass: 'bg-violet-50 dark:bg-violet-500/10',
    iconTextClass: 'text-violet-500 dark:text-violet-400'
  }
])

/**
 * 并行拉取统计数据。
 *
 * 使用 Promise.allSettled 保证单项失败时其余统计仍能正常展示；
 * 错误提示由 axios 响应拦截器统一处理，此处静默恢复。
 *
 * listHistory 取 page_size=100 以同时获取：
 *  - total → 阅读次数
 *  - items 中不同 article_id 的数量 → 已读文章数
 */
async function fetchStats(): Promise<void> {
  statsLoading.value = true
  try {
    const [wordsRes, sentencesRes, historyRes] = await Promise.allSettled([
      readingApi.listWords({ page: 1, page_size: 1 }),
      readingApi.listSentences({ page: 1, page_size: 1 }),
      readingApi.listHistory({ page: 1, page_size: 100 })
    ])

    if (wordsRes.status === 'fulfilled') {
      stats.value[0].value = wordsRes.value.total
    }
    if (sentencesRes.status === 'fulfilled') {
      stats.value[1].value = sentencesRes.value.total
    }
    if (historyRes.status === 'fulfilled') {
      stats.value[2].value = historyRes.value.total
      // 已读文章数 = 历史记录中不同 article_id 的数量
      const articleIds = new Set(historyRes.value.items.map((h) => h.article_id))
      stats.value[3].value = articleIds.size
    }
  } finally {
    statsLoading.value = false
  }
}

// ============================================================
//  登出
// ============================================================

/** 登出：复用 useAuth.logout（清除认证态并跳转登录页） */
async function handleLogout(): Promise<void> {
  await logout()
}

// ============================================================
//  生命周期
// ============================================================

onMounted(() => {
  // 防御性自检：若用户信息缺失（如会话异常），回登录页，避免渲染残缺的个人页
  if (!authStore.user) {
    router.push('/login')
    return
  }
  fetchStats()
})
</script>

<template>
  <div class="space-y-8">
    <!-- 页头 -->
    <header class="space-y-2">
      <h1
        class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl"
      >
        {{ t('profile.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('profile.subtitle') }}
      </p>
    </header>

    <!-- 用户信息卡片 -->
    <section
      v-if="user"
      class="rounded-xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900"
    >
      <!-- 头像 + 用户名 -->
      <div class="flex items-center gap-4">
        <img
          v-if="user.avatar_url"
          :src="user.avatar_url"
          :alt="t('profile.avatar')"
          class="h-16 w-16 flex-shrink-0 rounded-full object-cover"
        />
        <div
          v-else
          class="h-16 w-16 flex-shrink-0 rounded-full bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center text-xl font-bold text-blue-600 dark:text-blue-400"
        >
          {{ userInitial }}
        </div>
        <h2 class="text-2xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50">
          {{ user.username }}
        </h2>
      </div>

      <!-- 信息行 -->
      <div class="mt-6 space-y-3 border-t border-neutral-100 pt-6 dark:border-neutral-800">
        <div class="flex items-center justify-between gap-4">
          <span class="text-sm text-neutral-400">{{ t('profile.email') }}</span>
          <span class="text-sm text-neutral-900 dark:text-neutral-100">{{ user.email }}</span>
        </div>
        <div class="flex items-center justify-between gap-4">
          <span class="text-sm text-neutral-400">{{ t('profile.memberSince') }}</span>
          <span class="text-sm text-neutral-900 dark:text-neutral-100">
            {{ formatDateTime(user.created_at) }}
          </span>
        </div>
        <div class="flex items-center justify-between gap-4">
          <span class="text-sm text-neutral-400">{{ t('profile.lastLogin') }}</span>
          <span
            v-if="user.last_login_at"
            class="text-sm text-neutral-900 dark:text-neutral-100"
          >
            {{ formatDateTime(user.last_login_at) }}
          </span>
          <span v-else class="text-sm text-neutral-400">—</span>
        </div>
      </div>

      <!-- 英语水平选择 -->
      <div class="mt-6 border-t border-neutral-100 pt-6 dark:border-neutral-800">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span class="text-sm text-neutral-400">{{ t('profile.englishLevel') }}</span>
          <NSelect
            :value="selectedLevel"
            :options="levelOptions"
            :loading="levelUpdating"
            class="w-full sm:w-48"
            @update:value="handleLevelChange"
          />
        </div>
      </div>
    </section>

    <!-- 学习概览统计 -->
    <section class="space-y-4">
      <h2 class="text-sm font-medium uppercase tracking-wider text-neutral-400">
        {{ t('profile.statsTitle') }}
      </h2>

      <NSpin :show="statsLoading">
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div
            v-for="stat in stats"
            :key="stat.labelKey"
            class="stat-card rounded-xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900"
          >
            <div class="flex items-center gap-4">
              <!-- 图标 -->
              <span
                class="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg"
                :class="stat.iconBgClass"
              >
                <svg
                  class="h-5 w-5"
                  :class="stat.iconTextClass"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path :d="stat.icon" />
                </svg>
              </span>

              <!-- 数字 + 标签 -->
              <div class="min-w-0">
                <p
                  class="text-3xl font-bold tabular-nums text-neutral-900 dark:text-neutral-50"
                >
                  {{ stat.value }}
                </p>
                <p class="truncate text-sm text-neutral-500 dark:text-neutral-400">
                  {{ t(stat.labelKey) }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </NSpin>
    </section>

    <!-- 登出 -->
    <div class="pt-2">
      <NButton size="large" type="error" tertiary @click="handleLogout">
        {{ t('auth.logout') }}
      </NButton>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.stat-card:hover {
  transform: translateY(-2px);
  border-color: #d4d4d4;
  box-shadow: 0 4px 16px -4px rgba(0, 0, 0, 0.08);
}
:global(html.dark) .stat-card:hover {
  border-color: #404040;
  box-shadow: 0 4px 16px -4px rgba(0, 0, 0, 0.4);
}
</style>
