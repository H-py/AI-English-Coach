import { ref } from 'vue'
import { readingApi, streamReading } from '@/api/reading'
import type { ChatMessage } from '@/types/reading'

/**
 * 阅读页 AI 交互 composable。
 *
 * 封装阅读页右侧 AI 助手所需的全部状态与动作：
 *  - 流式 AI 交互（单词解释 / 句子分析 / 段落总结 / 自由问答）
 *  - 收藏（单词 / 句子）
 *  - 阅读历史（开始 / 结束会话）
 *
 * 状态设计：
 *  - aiContent / aiMode 用于 explain / sentence / paragraph 三种"解释类"模式，
 *    它们共享同一个内容区，新请求会先清空再流式填充。
 *  - chatMessages 用于 chat 模式，独立维护对话气泡列表，
 *    流式内容追加到最后一条 assistant 消息。
 *
 * 并发控制：
 *  - 使用 requestCounter + AbortController 保证只有最新请求的回调会更新状态，
 *    旧请求被 abort 后其回调自动失效，避免内容串扰。
 *
 * 错误提示由 axios 响应拦截器统一弹出（非流式接口）；
 * 流式接口的错误通过 onError 回调或 catch 块内联追加到内容中。
 */
export function useReading() {
  // ---- 响应式状态 ----

  /** 是否正在流式输出 */
  const streaming = ref(false)

  /** 当前 AI 输出内容（解释类模式，流式累积） */
  const aiContent = ref('')

  /** 当前 AI 面板模式 */
  const aiMode = ref<'explain' | 'sentence' | 'translate' | 'paragraph' | 'chat'>('explain')

  /** 问答对话历史（chat 模式独立维护） */
  const chatMessages = ref<ChatMessage[]>([])

  // ---- 并发控制（非响应式） ----

  /** 请求计数器，用于判断回调是否属于当前最新请求 */
  let requestCounter = 0

  /** 当前流式请求的 AbortController */
  let abortController: AbortController | null = null

  /** 取消正在进行的流式请求 */
  function abortOngoing(): void {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
  }

  // ============================================================
  //  流式 AI 交互
  // ============================================================

  /**
   * 解释单词。
   * 调用前清空 aiContent、设 streaming=true、设 aiMode='explain'。
   */
  async function explainWord(
    word: string,
    context: string,
    articleId: number
  ): Promise<void> {
    const requestId = ++requestCounter
    abortOngoing()
    const controller = new AbortController()
    abortController = controller

    const isCurrent = (): boolean => requestId === requestCounter

    aiContent.value = ''
    aiMode.value = 'explain'
    streaming.value = true

    try {
      await streamReading(
        'explain-word',
        { word, context, article_id: articleId },
        {
          onChunk: (content) => {
            if (isCurrent()) aiContent.value += content
          },
          onDone: () => {
            if (isCurrent()) streaming.value = false
          },
          onError: (error) => {
            if (isCurrent()) {
              aiContent.value += `\n\n> Error: ${error}`
              streaming.value = false
            }
          }
        },
        controller.signal
      )
    } catch (e) {
      if (isCurrent()) {
        // AbortError 是主动取消，不显示错误
        if ((e as Error).name !== 'AbortError') {
          aiContent.value += `\n\n> Error: ${(e as Error).message}`
        }
        streaming.value = false
      }
    } finally {
      if (isCurrent()) abortController = null
    }
  }

  /**
   * 分析句子。
   * 调用前先显示选中的句子原文（blockquote），再流式追加分析内容。
   * 设 streaming=true、aiMode='sentence'。
   */
  async function analyzeSentence(
    sentence: string,
    articleId: number
  ): Promise<void> {
    const requestId = ++requestCounter
    abortOngoing()
    const controller = new AbortController()
    abortController = controller

    const isCurrent = (): boolean => requestId === requestCounter

    // 先显示选中的句子原文，后续流式内容追加在后面
    aiContent.value = `> ${sentence}\n\n`
    aiMode.value = 'sentence'
    streaming.value = true

    try {
      await streamReading(
        'analyze-sentence',
        { sentence, article_id: articleId },
        {
          onChunk: (content) => {
            if (isCurrent()) aiContent.value += content
          },
          onDone: () => {
            if (isCurrent()) streaming.value = false
          },
          onError: (error) => {
            if (isCurrent()) {
              aiContent.value += `\n\n> Error: ${error}`
              streaming.value = false
            }
          }
        },
        controller.signal
      )
    } catch (e) {
      if (isCurrent()) {
        if ((e as Error).name !== 'AbortError') {
          aiContent.value += `\n\n> Error: ${(e as Error).message}`
        }
        streaming.value = false
      }
    } finally {
      if (isCurrent()) abortController = null
    }
  }

  /**
   * 翻译句子。
   * 调用前先显示选中的句子原文（blockquote），再流式追加翻译内容。
   * 设 streaming=true、aiMode='translate'。
   */
  async function translateSentence(
    sentence: string,
    articleId: number
  ): Promise<void> {
    const requestId = ++requestCounter
    abortOngoing()
    const controller = new AbortController()
    abortController = controller

    const isCurrent = (): boolean => requestId === requestCounter

    // 先显示选中的句子原文，后续流式内容追加在后面
    aiContent.value = `> ${sentence}\n\n`
    aiMode.value = 'translate'
    streaming.value = true

    try {
      await streamReading(
        'translate-sentence',
        { sentence, article_id: articleId },
        {
          onChunk: (content) => {
            if (isCurrent()) aiContent.value += content
          },
          onDone: () => {
            if (isCurrent()) streaming.value = false
          },
          onError: (error) => {
            if (isCurrent()) {
              aiContent.value += `\n\n> Error: ${error}`
              streaming.value = false
            }
          }
        },
        controller.signal
      )
    } catch (e) {
      if (isCurrent()) {
        if ((e as Error).name !== 'AbortError') {
          aiContent.value += `\n\n> Error: ${(e as Error).message}`
        }
        streaming.value = false
      }
    } finally {
      if (isCurrent()) abortController = null
    }
  }

  /**
   * 段落总结。
   * 调用前清空 aiContent、设 streaming=true、设 aiMode='paragraph'。
   */
  async function paragraphSummary(
    paragraph: string,
    articleId: number
  ): Promise<void> {
    const requestId = ++requestCounter
    abortOngoing()
    const controller = new AbortController()
    abortController = controller

    const isCurrent = (): boolean => requestId === requestCounter

    aiContent.value = ''
    aiMode.value = 'paragraph'
    streaming.value = true

    try {
      await streamReading(
        'paragraph-summary',
        { paragraph, article_id: articleId },
        {
          onChunk: (content) => {
            if (isCurrent()) aiContent.value += content
          },
          onDone: () => {
            if (isCurrent()) streaming.value = false
          },
          onError: (error) => {
            if (isCurrent()) {
              aiContent.value += `\n\n> Error: ${error}`
              streaming.value = false
            }
          }
        },
        controller.signal
      )
    } catch (e) {
      if (isCurrent()) {
        if ((e as Error).name !== 'AbortError') {
          aiContent.value += `\n\n> Error: ${(e as Error).message}`
        }
        streaming.value = false
      }
    } finally {
      if (isCurrent()) abortController = null
    }
  }

  /**
   * 发送问答消息。
   * 调用前先 push user 消息到 chatMessages，再 push 空 assistant 消息，
   * 流式内容追加到最后一条 assistant 消息的 content。
   */
  async function sendChat(message: string, articleId: number): Promise<void> {
    const requestId = ++requestCounter
    abortOngoing()
    const controller = new AbortController()
    abortController = controller

    const isCurrent = (): boolean => requestId === requestCounter

    aiMode.value = 'chat'
    streaming.value = true

    // 先 push 用户消息，再 push 空的 assistant 占位消息
    chatMessages.value.push({
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    })
    chatMessages.value.push({
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString()
    })

    try {
      await streamReading(
        'chat',
        { message, article_id: articleId },
        {
          onChunk: (content) => {
            if (!isCurrent()) return
            const last = chatMessages.value[chatMessages.value.length - 1]
            if (last && last.role === 'assistant') {
              last.content += content
            }
          },
          onDone: () => {
            if (isCurrent()) streaming.value = false
          },
          onError: (error) => {
            if (!isCurrent()) return
            const last = chatMessages.value[chatMessages.value.length - 1]
            if (last && last.role === 'assistant') {
              last.content += `\n\n> Error: ${error}`
            }
            streaming.value = false
          }
        },
        controller.signal
      )
    } catch (e) {
      if (isCurrent()) {
        if ((e as Error).name !== 'AbortError') {
          const last = chatMessages.value[chatMessages.value.length - 1]
          if (last && last.role === 'assistant') {
            last.content += `\n\n> Error: ${(e as Error).message}`
          }
        }
        streaming.value = false
      }
    } finally {
      if (isCurrent()) abortController = null
    }
  }

  // ============================================================
  //  收藏
  // ============================================================

  /** 收藏单词到生词本 */
  async function saveWord(
    word: string,
    context: string,
    articleId: number,
    explanation?: string
  ): Promise<void> {
    await readingApi.saveWord({
      word,
      context,
      article_id: articleId,
      ai_explanation: explanation
    })
  }

  /** 收藏句子 */
  async function saveSentence(
    sentence: string,
    articleId: number,
    note?: string
  ): Promise<void> {
    await readingApi.saveSentence({
      sentence,
      article_id: articleId,
      note
    })
  }

  // ============================================================
  //  面板清理
  // ============================================================

  /** 清空 AI 面板内容（aiContent + chatMessages） */
  function clearAiPanel(): void {
    aiContent.value = ''
    chatMessages.value = []
  }

  // ============================================================
  //  对话历史
  // ============================================================

  /**
   * 加载指定文章的 AI 对话历史。
   *
   * 从后端拉取最近 50 条对话记录并填充到 chatMessages，使前端
   * 在页面刷新或重新进入后仍能恢复之前的对话上下文。仅在
   * chatMessages 为空时调用（首次切换到 chat 标签）。
   */
  async function loadChatHistory(articleId: number): Promise<void> {
    try {
      const res = await readingApi.getConversations(articleId)
      chatMessages.value = res.items.map((msg) => ({
        role: msg.role as 'user' | 'assistant',
        content: msg.content,
        timestamp: msg.created_at
      }))
    } catch {
      // Errors are surfaced by the axios interceptor.
    }
  }

  // ============================================================
  //  阅读历史
  // ============================================================

  /** 开始阅读会话，返回 historyId */
  async function startReadingSession(articleId: number): Promise<number> {
    const history = await readingApi.startReading(articleId)
    return history.id
  }

  /** 结束阅读会话，上报阅读时长（秒） */
  async function endReadingSession(
    historyId: number,
    durationSeconds: number
  ): Promise<void> {
    await readingApi.endReading(historyId, {
      ended_at: new Date().toISOString(),
      duration_seconds: durationSeconds
    })
  }

  return {
    // 状态
    streaming,
    aiContent,
    aiMode,
    chatMessages,
    // 流式 AI 交互
    explainWord,
    analyzeSentence,
    translateSentence,
    paragraphSummary,
    sendChat,
    // 收藏
    saveWord,
    saveSentence,
    // 面板清理
    clearAiPanel,
    // 对话历史
    loadChatHistory,
    // 阅读历史
    startReadingSession,
    endReadingSession
  }
}
