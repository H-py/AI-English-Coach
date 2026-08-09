import { http } from './request'
import type {
  WordCollection,
  SentenceCollection,
  ReadingHistory,
  ReadingHistoryWithArticle,
  SaveWordPayload,
  SaveSentencePayload,
  UpdateWordPayload,
  UpdateSentencePayload,
  MasteryLevel
} from '@/types/reading'

/**
 * 阅读模块 API。
 *
 * 提供非流式接口（单词收藏 / 句子收藏 / 阅读历史），使用 http 封装，
 * 响应信封已由拦截器自动解包，直接返回业务数据。
 *
 * 所有接口前缀 `/api/v1`（VITE_API_BASE_URL 已包含）。
 */

// ============================================================
//  非流式接口
// ============================================================

export const readingApi = {
  // ---- 单词收藏 ----

  /** 收藏单词到生词本 */
  saveWord(data: SaveWordPayload): Promise<WordCollection> {
    return http.post('/reading/words', data)
  },

  /** 获取生词本列表（分页，可选按掌握度筛选 / 按单词搜索） */
  listWords(params?: {
    page?: number
    page_size?: number
    mastery_level?: MasteryLevel
    search?: string
  }): Promise<{ items: WordCollection[]; total: number }> {
    return http.get('/reading/words', { params })
  },

  /** 更新单词掌握度 / 学习次数 */
  updateWord(id: number, data: UpdateWordPayload): Promise<WordCollection> {
    return http.put(`/reading/words/${id}`, data)
  },

  /** 删除生词本中的单词 */
  deleteWord(id: number): Promise<void> {
    return http.delete(`/reading/words/${id}`)
  },

  // ---- 句子收藏 ----

  /** 收藏句子 */
  saveSentence(data: SaveSentencePayload): Promise<SentenceCollection> {
    return http.post('/reading/sentences', data)
  },

  /** 获取句子收藏列表（分页，可选搜索） */
  listSentences(params?: {
    page?: number
    page_size?: number
    search?: string
  }): Promise<{ items: SentenceCollection[]; total: number }> {
    return http.get('/reading/sentences', { params })
  },

  /** 更新句子笔记 */
  updateSentence(id: number, data: UpdateSentencePayload): Promise<SentenceCollection> {
    return http.put(`/reading/sentences/${id}`, data)
  },

  /** 删除收藏的句子 */
  deleteSentence(id: number): Promise<void> {
    return http.delete(`/reading/sentences/${id}`)
  },

  // ---- 阅读历史 ----

  /** 开始阅读（创建历史记录，返回 historyId） */
  startReading(articleId: number): Promise<ReadingHistory> {
    return http.post('/reading/history', { article_id: articleId })
  },

  /** 结束阅读（更新结束时间与时长） */
  endReading(
    historyId: number,
    data: { ended_at?: string; duration_seconds?: number }
  ): Promise<ReadingHistory> {
    return http.put(`/reading/history/${historyId}`, data)
  },

  /** 获取阅读历史列表（分页，含文章标题） */
  listHistory(params?: {
    page?: number
    page_size?: number
  }): Promise<{ items: ReadingHistoryWithArticle[]; total: number }> {
    return http.get('/reading/history', { params })
  }
}
