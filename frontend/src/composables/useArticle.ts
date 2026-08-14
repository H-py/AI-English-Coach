import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useArticleStore } from '@/stores/article'
import type { ArticleQuery, CetType, Difficulty } from '@/types/article'

/**
 * 文章模块通用 composable。
 *
 * 在 article store 之上封装页面层常用操作：
 *  - 带本地 loading 状态的数据加载（列表 / 详情 / 标签）；
 *  - 难度星级与四六级真题的本地化标签，供筛选器等复用。
 *
 * 错误提示由 axios 响应拦截器统一处理；加载失败时 loading 会恢复，
 * 调用方可自行 catch 以做额外的 UI 处理。
 */
export function useArticle() {
  const store = useArticleStore()
  const { t } = useI18n()

  // 页面级 loading：列表 / 详情共用，避免在 store 中堆积多个 loading 状态
  const loading = ref(false)

  /** 加载文章列表（带本地 loading） */
  async function loadArticles(query?: ArticleQuery): Promise<void> {
    loading.value = true
    try {
      await store.fetchArticles(query)
    } finally {
      loading.value = false
    }
  }

  /** 加载文章详情（带本地 loading） */
  async function loadArticleDetail(id: number): Promise<void> {
    loading.value = true
    try {
      await store.fetchArticleDetail(id)
    } finally {
      loading.value = false
    }
  }

  /** 加载全部可用标签 */
  async function loadTags(): Promise<void> {
    await store.fetchTags()
  }

  /** 返回难度星级的本地化标签，如 "1星" */
  function difficultyLabel(d: Difficulty): string {
    return t(`article.difficulty.${d}`)
  }

  /** 返回四六级真题类型的本地化标签，如 "四级" */
  function cetLabel(c: CetType): string {
    return t(`article.cet.${c}`)
  }

  return {
    // state（来自 store，保持响应式引用）
    store,
    // 本地 loading
    loading,
    // actions
    loadArticles,
    loadArticleDetail,
    loadTags,
    // helpers
    difficultyLabel,
    cetLabel
  }
}
