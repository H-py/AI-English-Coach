<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NButton, NSpin, NEmpty } from 'naive-ui'
import ArticleCard from '@/components/ArticleCard.vue'
import { readingApi } from '@/api/reading'
import { articleApi } from '@/api/article'
import { useAuthStore } from '@/stores/auth'
import type { ArticleListItem } from '@/types/article'

/**
 * 首页：登录后落地页。
 *
 * 展示问候语、学习概览统计（收藏单词 / 句子、阅读次数、已读文章）、
 * 快速入口与推荐文章，引导用户继续学习。
 *
 * 数据在 onMounted 时并行拉取，统计与文章互不阻塞；
 * 统计内部使用 Promise.allSettled 保证单项失败不影响其余展示。
 */

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

// ============================================================
//  问候语
// ============================================================

const username = computed(() => authStore.user?.username ?? '')

/** 根据当前时段返回对应问候语 i18n key（6-12 早上 / 12-18 下午 / 其余晚上） */
const greetingKey = computed(() => {
  const hour = new Date().getHours()
  if (hour >= 6 && hour < 12) return 'home.morningGreeting'
  if (hour >= 12 && hour < 18) return 'home.afternoonGreeting'
  return 'home.eveningGreeting'
})

// ============================================================
//  统计数据
// ============================================================

interface StatItem {
  /** i18n 标签 key */
  labelKey: string
  value: number
  /** 图标 path（Lucide 风格，stroke-based，单 path 多子路径） */
  icon: string
  /** 左侧装饰条颜色类 */
  barClass: string
  /** 图标背景色类 */
  iconBgClass: string
  /** 图标前景色类 */
  iconTextClass: string
  /** 点击跳转路由 */
  route: string
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
    labelKey: 'home.wordsCollected',
    value: 0,
    icon: ICONS.bookmark,
    barClass: 'bg-blue-400',
    iconBgClass: 'bg-blue-50 dark:bg-blue-500/10',
    iconTextClass: 'text-blue-500 dark:text-blue-400',
    route: '/vocabulary'
  },
  {
    labelKey: 'home.sentencesCollected',
    value: 0,
    icon: ICONS.messageSquare,
    barClass: 'bg-emerald-400',
    iconBgClass: 'bg-emerald-50 dark:bg-emerald-500/10',
    iconTextClass: 'text-emerald-500 dark:text-emerald-400',
    route: '/sentences'
  },
  {
    labelKey: 'home.readingSessions',
    value: 0,
    icon: ICONS.history,
    barClass: 'bg-amber-400',
    iconBgClass: 'bg-amber-50 dark:bg-amber-500/10',
    iconTextClass: 'text-amber-500 dark:text-amber-400',
    route: '/history'
  },
  {
    labelKey: 'home.articlesRead',
    value: 0,
    icon: ICONS.bookOpen,
    barClass: 'bg-violet-400',
    iconBgClass: 'bg-violet-50 dark:bg-violet-500/10',
    iconTextClass: 'text-violet-500 dark:text-violet-400',
    route: '/articles'
  }
])

// ============================================================
//  推荐文章
// ============================================================

const articlesLoading = ref(false)
const articles = ref<ArticleListItem[]>([])

// ============================================================
//  数据加载
// ============================================================

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

/** 拉取推荐文章（最新发布的 6 篇） */
async function fetchArticles(): Promise<void> {
  articlesLoading.value = true
  try {
    const res = await articleApi.list({ page: 1, page_size: 6 })
    articles.value = res.items
  } finally {
    articlesLoading.value = false
  }
}

// ============================================================
//  路由跳转
// ============================================================

function goToArticles(): void {
  router.push('/articles')
}

function goToVocabulary(): void {
  router.push('/vocabulary')
}

// ============================================================
//  生命周期
// ============================================================

onMounted(() => {
  fetchStats()
  fetchArticles()
})
</script>

<template>
  <div class="space-y-10">
    <!-- 问候区 -->
    <section class="space-y-2">
      <h1
        class="text-3xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-4xl"
      >
        {{ t(greetingKey, { name: username }) }}
      </h1>
      <p class="text-base text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('home.subtitle') }}
      </p>
    </section>

    <!-- 学习概览统计 -->
    <section class="space-y-4">
      <h2 class="text-sm font-medium uppercase tracking-wider text-neutral-400">
        {{ t('home.statsTitle') }}
      </h2>

      <NSpin :show="statsLoading">
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div
            v-for="stat in stats"
            :key="stat.labelKey"
            class="stat-card group relative cursor-pointer overflow-hidden rounded-xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900"
            @click="router.push(stat.route)"
          >
            <!-- 左侧彩色装饰条 -->
            <span
              class="absolute left-0 top-0 h-full w-1"
              :class="stat.barClass"
            />

            <div class="flex items-center gap-4 pl-2">
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

    <!-- 快速入口 -->
    <section class="flex flex-wrap gap-3">
      <NButton size="large" type="primary" @click="goToArticles">
        {{ t('home.goToArticles') }}
      </NButton>
      <NButton size="large" @click="goToVocabulary">
        {{ t('home.goToVocabulary') }}
      </NButton>
    </section>

    <!-- 推荐文章 -->
    <section class="space-y-5">
      <div class="space-y-1">
        <h2
          class="text-xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50"
        >
          {{ t('home.recommendedTitle') }}
        </h2>
        <p class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ t('home.recommendedSubtitle') }}
        </p>
      </div>

      <div class="min-h-[200px]">
        <NSpin :show="articlesLoading">
          <NEmpty
            v-if="!articlesLoading && articles.length === 0"
            :description="t('home.noRecommendations')"
            class="py-16"
          />
          <div
            v-else
            class="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3"
          >
            <ArticleCard
              v-for="article in articles"
              :key="article.id"
              :article="article"
            />
          </div>
        </NSpin>
      </div>
    </section>
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
