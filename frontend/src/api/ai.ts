import { http } from './request'
import { getAccessToken } from '@/utils'
import type { ConversationMessage, ReadingSummary, ReadingQuiz, QuizSubmitResponse } from '@/types/reading'

/**
 * AI 模块 API。
 *
 * 分为两部分：
 *  1. aiApi —— 非流式接口（对话历史 / 阅读总结 / 练习题），使用 http 封装，
 *     响应信封已由拦截器自动解包，直接返回业务数据。
 *  2. streamAI —— SSE 流式接口（AI 解释 / 分析 / 翻译 / 摘要 / 问答），
 *     返回 text/event-stream，不能用 axios 封装，需用原生 fetch +
 *     ReadableStream 手动解析 `data: ` 前缀的 SSE 帧。
 *
 * 所有接口前缀 `/api/v1`（VITE_API_BASE_URL 已包含）。
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL

// ============================================================
//  非流式接口
// ============================================================

export const aiApi = {
  // ---- AI 对话历史 ----

  /** 获取指定文章的 AI 对话历史（最近 50 条，按时间正序） */
  getConversations(articleId: number): Promise<{ items: ConversationMessage[]; total: number }> {
    return http.get(`/ai/conversations/${articleId}`)
  },

  // ---- 阅读总结 ----

  /** 生成某次阅读会话的 AI 总结 */
  generateSummary(historyId: number): Promise<ReadingSummary> {
    return http.post('/ai/summary', { history_id: historyId })
  },

  /** 获取某次阅读会话的已有总结（无总结时返回 null） */
  getSummary(historyId: number): Promise<ReadingSummary | null> {
    return http.get(`/ai/summary/${historyId}`)
  },

  // ---- 阅读练习题 ----

  /** 基于文章生成练习题 */
  generateQuiz(articleId: number, historyId: number): Promise<ReadingQuiz> {
    return http.post('/ai/quiz', { article_id: articleId, history_id: historyId })
  },

  /** 获取某次阅读会话的最新练习题（无练习题时返回 null） */
  getLatestQuiz(historyId: number): Promise<ReadingQuiz | null> {
    return http.get(`/ai/quiz/${historyId}`)
  },

  /** 提交练习题答案并获取判分结果 */
  submitQuiz(quizId: number, answers: { question_id: number; user_answer: string }[]): Promise<QuizSubmitResponse> {
    return http.post(`/ai/quiz/${quizId}/submit`, { answers })
  }
}

// ============================================================
//  SSE 流式接口
// ============================================================

/**
 * SSE 流式请求通用函数。
 *
 * 后端 5 个 AI 端点（explain-word / analyze-sentence / translate-sentence /
 * paragraph-summary / chat）均返回 `text/event-stream`，
 * 每条帧格式为 `data: {"content": "chunk"}\n\n`，
 * 结束帧为 `data: {"done": true}\n\n`，
 * 错误帧为 `data: {"error": "msg"}\n\n`。
 *
 * 本函数用 fetch + ReadableStream 逐块读取并解析，
 * 通过回调将内容片段、完成、错误事件传递给调用方。
 *
 * @param endpoint  端点名称（不含 /ai/ 前缀），如 'explain-word'
 * @param body      POST 请求体（可包含 history_id 用于活动跟踪）
 * @param callbacks 回调集合：onChunk（内容片段）、onDone（完成）、onError（错误）
 * @param signal    可选的 AbortSignal，用于取消请求（新请求发起时取消旧请求）
 */
export async function streamAI(
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
  const response = await fetch(`${API_BASE}/ai/${endpoint}`, {
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
