import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useArticleStore } from '@/stores/article'
import type { ArticleQuery, Difficulty } from '@/types/article'

/**
 * 文章模块通用 composable。
 *
 * 在 article store 之上封装页面层常用操作：
 *  - 带本地 loading 状态的数据加载（列表 / 详情 / 标签）；
 *  - 难度等级的本地化标签与配色映射，供卡片、筛选器等复用。
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

  /** 返回难度等级的本地化标签，如 "A1 入门" */
  function difficultyLabel(d: Difficulty): string {
    return t(`article.difficulty.${d}`)
  }

  /**
   * 返回难度等级对应的 NTag 配色（低饱和度，符合极简风格）。
   * a1/a2 绿色系、b1/b2 蓝色系、c1/c2 紫色系。
   *
   * 返回结构直接适配 Naive UI NTag 的 color prop：
   *  - color：柔和浅色背景
   *  - textColor：主色调文字
   *  - borderColor：浅色描边
   */
  function difficultyColor(
    d: Difficulty
  ): { color: string; textColor: string; borderColor: string } {
    const palette: Record<
      Difficulty,
      { color: string; textColor: string; borderColor: string }
    > = {
      a1: { color: '#f0fdf4', textColor: '#15803d', borderColor: '#bbf7d0' },
      a2: { color: '#f0fdf4', textColor: '#166534', borderColor: '#bbf7d0' },
      b1: { color: '#eff6ff', textColor: '#1d4ed8', borderColor: '#bfdbfe' },
      b2: { color: '#eff6ff', textColor: '#1e40af', borderColor: '#bfdbfe' },
      c1: { color: '#f5f3ff', textColor: '#6d28d9', borderColor: '#ddd6fe' },
      c2: { color: '#f5f3ff', textColor: '#5b21b6', borderColor: '#ddd6fe' }
    }
    return palette[d]
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
    difficultyColor
  }
}
