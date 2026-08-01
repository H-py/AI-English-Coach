import { defineStore } from 'pinia'
import { ref } from 'vue'
import { articleApi } from '@/api/article'
import type {
  Article,
  ArticleListItem,
  ArticleQuery
} from '@/types/article'

/**
 * 文章 store（pinia setup 写法）。
 *
 * 职责：
 *  - 维护文章列表（items + total）、当前详情、可用标签等共享状态；
 *  - 封装列表 / 详情 / 标签的数据拉取动作；
 *  - 不处理路由跳转与 UI 副作用，这些交给 composable / 组件层。
 *
 * 错误提示由 axios 响应拦截器统一弹出，store 内不额外 try/catch 弹错；
 * 调用方可通过 catch 感知失败并恢复 loading。
 */
export const useArticleStore = defineStore('article', () => {
  // 文章列表
  const articles = ref<ArticleListItem[]>([])
  const total = ref(0)

  // 当前查看的文章详情
  const currentArticle = ref<Article | null>(null)

  // 全部可用标签
  const tags = ref<string[]>([])

  // 列表加载状态（供需要感知全局 loading 的场景使用）
  const loading = ref(false)

  /** 拉取文章列表，更新 articles 与 total */
  async function fetchArticles(query?: ArticleQuery): Promise<void> {
    loading.value = true
    try {
      const res = await articleApi.list(query)
      articles.value = res.items
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  /** 拉取文章详情，更新 currentArticle */
  async function fetchArticleDetail(id: number): Promise<void> {
    const res = await articleApi.getDetail(id)
    currentArticle.value = res
  }

  /** 拉取全部可用标签，更新 tags */
  async function fetchTags(): Promise<void> {
    const res = await articleApi.getTags()
    tags.value = res
  }

  /** 清空当前文章详情（离开详情页时调用，避免残留旧数据） */
  function clearCurrent(): void {
    currentArticle.value = null
  }

  return {
    // state
    articles,
    total,
    currentArticle,
    tags,
    loading,
    // actions
    fetchArticles,
    fetchArticleDetail,
    fetchTags,
    clearCurrent
  }
})
