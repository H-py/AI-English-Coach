import { http } from './request'
import { getAccessToken } from '@/utils'
import type {
  WordCollection,
  SentenceCollection,
  ReadingHistory,
  ReadingHistoryWithArticle,
  ConversationMessage,
  SaveWordPayload,
  SaveSentencePayload,
  UpdateWordPayload,
  UpdateSentencePayload,
  MasteryLevel
} from '@/types/reading'

/**
 * 阅读模块 API。
 *
 * 分为两部分：
 *  1. readingApi —— 非流式接口（收藏 / 历史），使用 http 封装，
 *     响应信封已由拦截器自动解包，直接返回业务数据。
 *  2. streamReading —— SSE 流式接口（AI 解释 / 分析 / 问答），
 *     返回 text/event-stream，不能用 axios 封装，需用原生 fetch +
 *     ReadableStream 手动解析 `data: ` 前缀的 SSE 帧。
 *
 * 所有接口前缀 `/api/v1`（VITE_API_BASE_URL 已包含）。
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL

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
  },

  // ---- AI 对话历史 ----

  /** 获取指定文章的 AI 对话历史（最近 50 条，按时间正序） */
  getConversations(articleId: number): Promise<{ items: ConversationMessage[]; total: number }> {
    return http.get(`/reading/conversations/${articleId}`)
  }
}

// ============================================================
//  SSE 流式接口
// ============================================================

/**
 * SSE 流式请求通用函数。
 *
 * 后端 4 个 AI 端点（explain-word / analyze-sentence /
 * paragraph-summary / chat）均返回 `text/event-stream`，
 * 每条帧格式为 `data: {"content": "chunk"}\n\n`，
 * 结束帧为 `data: {"done": true}\n\n`，
 * 错误帧为 `data: {"error": "msg"}\n\n`。
 *
 * 本函数用 fetch + ReadableStream 逐块读取并解析，
 * 通过回调将内容片段、完成、错误事件传递给调用方。
 *
 * @param endpoint  端点名称（不含 /reading/ 前缀），如 'explain-word'
 * @param body      POST 请求体
 * @param callbacks 回调集合：onChunk（内容片段）、onDone（完成）、onError（错误）
 * @param signal    可选的 AbortSignal，用于取消请求（新请求发起时取消旧请求）
 */
export async function streamReading(
  endpoint: string,
  body: Record<string, unknown>,
  callbacks: {
    onChunk: (content: string) => void
    onDone?: () => void
    onError?: (error: string) => void
  },
  signal?: AbortSignal
): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(`${API_BASE}/reading/${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body),
    signal
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  if (!response.body) {
    throw new Error('Response body is empty')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false

  /** 安全地触发 onDone，保证只调用一次 */
  const finish = (): void => {
    if (!finished) {
      finished = true
      callbacks.onDone?.()
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // 按行分割，最后一段可能不完整，留在 buffer 中等待下次拼接
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue

      const jsonStr = line.slice(6)
      try {
        const data = JSON.parse(jsonStr)
        if (data.content) {
          callbacks.onChunk(data.content)
        } else if (data.done) {
          finish()
        } else if (data.error) {
          callbacks.onError?.(data.error)
        }
      } catch {
        // 跳过无法解析的行（可能是心跳或不完整帧）
      }
    }
  }

  // 流正常结束，确保 onDone 被调用
  finish()
}
