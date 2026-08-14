<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NTag } from 'naive-ui'
import StarRating from '@/components/StarRating.vue'
import { useArticle } from '@/composables/useArticle'
import type { ArticleListItem } from '@/types/article'

/**
 * 文章卡片。
 *
 * 极简风格：白底圆角细边框，hover 微阴影。点击卡片整体跳转详情页。
 * 展示：难度星级（五颗星）、四六级真题标签、标题、摘要（2 行截断）、
 * 词数、阅读时间、标签。
 */
const props = defineProps<{
  article: ArticleListItem
}>()

const router = useRouter()
const { t } = useI18n()
const { cetLabel } = useArticle()

// 难度星级（字符串转数字，供 StarRating 使用）
const difficultyStars = computed(() => Number(props.article.difficulty))

// 标签最多展示 3 个，避免卡片过高
const visibleTags = computed(() => props.article.tags.slice(0, 3))

function goDetail(): void {
  router.push(`/articles/${props.article.id}`)
}
</script>

<template>
  <article
    class="article-card group flex cursor-pointer flex-col rounded-xl border border-neutral-200 bg-white p-5 transition-all duration-200 dark:border-neutral-800 dark:bg-neutral-900"
    @click="goDetail"
  >
    <!-- 难度星级 + 四六级标签 -->
    <div class="mb-3 flex items-center gap-2">
      <StarRating :stars="difficultyStars" />
      <NTag
        v-if="article.cet_type"
        size="tiny"
        :bordered="false"
        type="warning"
      >
        {{ cetLabel(article.cet_type) }}
      </NTag>
    </div>

    <!-- 标题 -->
    <h3
      class="mb-2 line-clamp-2 text-base font-semibold tracking-tight text-neutral-900 transition-colors group-hover:text-neutral-600 dark:text-neutral-50 dark:group-hover:text-neutral-300"
    >
      {{ article.title }}
    </h3>

    <!-- 摘要（2 行截断）；无摘要时用占位撑开高度，保持卡片高度一致 -->
    <p
      v-if="article.summary"
      class="line-clamp-2 flex-1 text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable"
    >
      {{ article.summary }}
    </p>
    <div v-else class="flex-1" aria-hidden="true" />

    <!-- 元信息：词数 / 阅读时间 -->
    <div class="mt-4 flex items-center gap-4 text-xs text-neutral-400 dark:text-neutral-500">
      <span>{{ article.word_count }} {{ t('article.wordCount') }}</span>
      <span v-if="article.reading_time">
        {{ article.reading_time }} {{ t('article.readingTime') }}
      </span>
    </div>

    <!-- 标签 -->
    <div v-if="visibleTags.length" class="mt-3 flex flex-wrap gap-1.5">
      <NTag
        v-for="tag in visibleTags"
        :key="tag"
        size="tiny"
        :bordered="false"
        type="default"
        class="!text-neutral-500 dark:!text-neutral-400"
      >
        {{ tag }}
      </NTag>
    </div>
  </article>
</template>

<style scoped>
.article-card:hover {
  border-color: #d4d4d4;
  box-shadow: 0 4px 16px -4px rgba(0, 0, 0, 0.08);
}
:global(html.dark) .article-card:hover {
  border-color: #404040;
  box-shadow: 0 4px 16px -4px rgba(0, 0, 0, 0.4);
}
</style>
