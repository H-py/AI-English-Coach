<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSpin } from 'naive-ui'
import { adminApi } from '@/api/admin'
import type { AdminDashboard } from '@/types/admin'

/**
 * 管理后台仪表盘：展示全站概览统计。
 *
 * 在 onMounted 时调用 adminApi.getDashboard() 拉取数据，
 * 展示 4 张统计卡片（用户总数 / 文章总数 / 已发布文章 / 总浏览量）。
 * 错误提示由 axios 响应拦截器统一处理，此处静默恢复。
 */

const { t } = useI18n()

// ============================================================
//  数据状态
// ============================================================

const loading = ref(false)
const dashboard = ref<AdminDashboard | null>(null)

// ============================================================
//  图标（Lucide 风格线性图标，stroke-based，24×24 viewBox）
// ============================================================

const ICONS = {
  users:
    'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
  book:
    'M4 19.5A2.5 2.5 0 0 1 6.5 17H20 M4 19.5A2.5 2.5 0 0 0 6.5 22H20 M4 19.5V5.5A2.5 2.5 0 0 1 6.5 3H20v14',
  checkCircle:
    'M22 11.08V12a10 10 0 1 1-5.93-9.14 M22 4 12 14.01l-3-3',
  eye: 'M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z'
} as const

// ============================================================
//  统计卡片配置
// ============================================================

interface StatCard {
  /** i18n 标签 key */
  labelKey: string
  /** 取值字段，对应 AdminDashboard */
  field: keyof AdminDashboard
  /** 图标 path */
  icon: string
  /** 图标背景色类 */
  iconBgClass: string
  /** 图标前景色类 */
  iconTextClass: string
}

const cards = computed<StatCard[]>(() => [
  {
    labelKey: 'admin.dashboard.totalUsers',
    field: 'total_users',
    icon: ICONS.users,
    iconBgClass: 'bg-blue-50 dark:bg-blue-500/10',
    iconTextClass: 'text-blue-500 dark:text-blue-400'
  },
  {
    labelKey: 'admin.dashboard.totalArticles',
    field: 'total_articles',
    icon: ICONS.book,
    iconBgClass: 'bg-emerald-50 dark:bg-emerald-500/10',
    iconTextClass: 'text-emerald-500 dark:text-emerald-400'
  },
  {
    labelKey: 'admin.dashboard.publishedArticles',
    field: 'published_articles',
    icon: ICONS.checkCircle,
    iconBgClass: 'bg-amber-50 dark:bg-amber-500/10',
    iconTextClass: 'text-amber-500 dark:text-amber-400'
  },
  {
    labelKey: 'admin.dashboard.totalViews',
    field: 'total_views',
    icon: ICONS.eye,
    iconBgClass: 'bg-violet-50 dark:bg-violet-500/10',
    iconTextClass: 'text-violet-500 dark:text-violet-400'
  }
])

// ============================================================
//  数据加载
// ============================================================

async function fetchDashboard(): Promise<void> {
  loading.value = true
  try {
    dashboard.value = await adminApi.getDashboard()
  } finally {
    loading.value = false
  }
}

// ============================================================
//  生命周期
// ============================================================

onMounted(() => {
  fetchDashboard()
})
</script>

<template>
  <div class="space-y-8">
    <!-- 页面标题 -->
    <div>
      <h1
        class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50"
      >
        {{ t('admin.title') }}
      </h1>
    </div>

    <!-- 统计卡片 -->
    <NSpin :show="loading">
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div
          v-for="card in cards"
          :key="card.field"
          class="rounded-xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900"
        >
          <div class="flex items-center gap-4">
            <!-- 图标 -->
            <span
              class="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg"
              :class="card.iconBgClass"
            >
              <svg
                class="h-5 w-5"
                :class="card.iconTextClass"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.75"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path :d="card.icon" />
              </svg>
            </span>

            <!-- 数字 + 标签 -->
            <div class="min-w-0">
              <p
                class="text-3xl font-bold tabular-nums text-neutral-900 dark:text-neutral-50"
              >
                {{ dashboard ? dashboard[card.field] : 0 }}
              </p>
              <p class="text-sm text-neutral-500 dark:text-neutral-400">
                {{ t(card.labelKey) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </NSpin>
  </div>
</template>
