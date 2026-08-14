<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NPagination, NSpin, NEmpty } from 'naive-ui'
import ArticleCard from '@/components/ArticleCard.vue'
import DifficultyFilter from '@/components/DifficultyFilter.vue'
import CetFilter from '@/components/CetFilter.vue'
import { useArticle } from '@/composables/useArticle'
import type { CetType, Difficulty } from '@/types/article'

/**
 * 文章列表页。
 *
 * 结构：页面标题 + 难度星级筛选 + 四六级真题筛选 -> 文章卡片网格（响应式
 * 1-2-3 列） -> 分页。筛选（星级 / 四六级）变化时重置到第 1 页并重新加载。
 * loading 用 NSpin，空数据用 NEmpty。
 */
const { t } = useI18n()
const { store, loading, loadArticles } = useArticle()

// 筛选与分页状态
const difficulty = ref<Difficulty | undefined>(undefined)
const cetType = ref<CetType | undefined>(undefined)
const page = ref(1)
const pageSize = ref(12)

// 当前页文章列表与总数（来自 store）
const articles = computed(() => store.articles)
const total = computed(() => store.total)

/** 组装查询参数并拉取列表 */
async function fetchList(): Promise<void> {
  await loadArticles({
    difficulty: difficulty.value,
    cet_type: cetType.value,
    page: page.value,
    page_size: pageSize.value
  })
}

/** 星级 / 四六级变化：重置到第 1 页并重新加载 */
watch([difficulty, cetType], () => {
  page.value = 1
  fetchList()
})

/** 翻页：更新页码并重新加载 */
function handlePageChange(p: number): void {
  page.value = p
  fetchList()
}

onMounted(fetchList)
</script>

<template>
  <div class="space-y-8">
    <!-- 标题区 -->
    <header class="space-y-2">
      <h1 class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl">
        {{ t('article.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('article.subtitle') }}
      </p>
    </header>

    <!-- 筛选：难度星级 + 四六级真题 -->
    <div class="space-y-3">
      <DifficultyFilter v-model="difficulty" />
      <CetFilter v-model="cetType" />
    </div>

    <!-- 列表区 -->
    <div class="min-h-[300px]">
      <NSpin :show="loading">
        <!-- 空状态 -->
        <NEmpty
          v-if="!loading && articles.length === 0"
          :description="t('article.empty')"
          class="py-20"
        />

        <!-- 卡片网格：响应式 1-2-3 列 -->
        <div
          v-else
          class="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3"
        >
          <ArticleCard
            v-for="article in articles"
            :key="article.id"
            :article="article"
          />
        </div>
      </NSpin>
    </div>

    <!-- 分页 -->
    <div
      v-if="total > pageSize"
      class="flex justify-center pt-2"
    >
      <NPagination
        :page="page"
        :page-size="pageSize"
        :item-count="total"
        show-quick-jumper
        @update:page="handlePageChange"
      />
    </div>
  </div>
</template>
