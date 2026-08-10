import { ref } from 'vue'
import { streamAgent } from '@/api/agent'
import type { ThinkingStep } from '@/types/agent'

/**
 * Agent 智能体交互 composable。
 *
 * 封装与后端 reading-coach Agent 的流式交互状态：
 *  - agentStreaming：是否正在流式输出
 *  - thinkingSteps：思考步骤列表（thinking / tool_call / tool_result）
 *  - agentAnswer：最终回复内容（content 事件累积）
 *  - agentError：错误信息
 *
 * 并发控制：
 *  - 使用 AbortController 保证每次只有一个活跃请求，
 *    新请求发起时自动取消旧请求。
 *  - AbortError 会被静默忽略（用户主动取消）。
 */
export function useAgent() {
  /** 是否正在流式输出 */
  const agentStreaming = ref(false)

  /** 思考步骤列表 */
  const thinkingSteps = ref<ThinkingStep[]>([])

  /** Agent 最终回复内容（content 事件累积） */
  const agentAnswer = ref('')

  /** 错误信息 */
  const agentError = ref('')

  /** 当前对话 ID（done 事件返回，用于多轮对话） */
  const currentConversationId = ref<number | null>(null)

  /** 当前流式请求的 AbortController */
  let abortController: AbortController | null = null

  /** 自增 ID，用于 ThinkingStep 的唯一标识 */
  let stepIdCounter = 0

  /**
   * 发送消息给 Agent 并流式接收响应。
   *
   * @param message   用户输入的消息
   * @param articleId 当前文章 ID（可选，智能学习页面不绑定文章时省略）
   * @param historyId 当前阅读会话的 history ID（可选）
   * @param conversationId 当前对话 ID（可选，用于多轮对话）
   */
  async function sendToAgent(
    message: string,
    articleId?: number | null,
    historyId?: number | null,
    conversationId?: number | null
  ): Promise<void> {
    // 取消正在进行的请求
    if (abortController) {
      abortController.abort()
      abortController = null
    }

    // 重置状态
    const controller = new AbortController()
    abortController = controller
    stepIdCounter = 0

    agentStreaming.value = true
    thinkingSteps.value = []
    agentAnswer.value = ''
    agentError.value = ''

    await streamAgent(
      'reading-coach/chat',
      {
        message,
        ...(articleId ? { article_id: articleId } : {}),
        ...(historyId ? { history_id: historyId } : {}),
        ...(conversationId ? { conversation_id: conversationId } : {})
      },
      {
        onEvent(event) {
          switch (event.type) {
            case 'conversation_started':
              // 流开始时立即捕获 conversation_id，确保即使后续
              // Agent 执行出错，前端也能用于后续多轮对话。
              if (event.conversation_id != null) {
                currentConversationId.value = event.conversation_id
              }
              break

            case 'thinking':
              thinkingSteps.value.push({
                id: ++stepIdCounter,
                type: 'thinking',
                content: event.content || '',
                timestamp: new Date().toISOString()
              })
              break

            case 'tool_call':
              thinkingSteps.value.push({
                id: ++stepIdCounter,
                type: 'tool_call',
                content: '',
                toolName: event.tool,
                toolArguments: event.arguments,
                timestamp: new Date().toISOString()
              })
              break

            case 'tool_result':
              thinkingSteps.value.push({
                id: ++stepIdCounter,
                type: 'tool_result',
                content: event.content || '',
                toolName: event.tool,
                toolResultData: event.data,
                timestamp: new Date().toISOString()
              })
              break

            case 'content':
              agentAnswer.value += event.content || ''
              break

            case 'error':
              agentError.value = event.message || 'Unknown error'
              break

            case 'done':
              // 从 done 事件中提取 conversation_id，用于多轮对话
              if (event.conversation_id != null) {
                currentConversationId.value = event.conversation_id
              }
              break
          }
        },
        onDone() {
          agentStreaming.value = false
        },
        onError(error) {
          agentError.value = error
          agentStreaming.value = false
        }
      },
      controller.signal
    ).catch((err: unknown) => {
      // 忽略用户主动取消导致的 AbortError
      if (err instanceof DOMException && err.name === 'AbortError') {
        return
      }
      agentError.value = err instanceof Error ? err.message : String(err)
      agentStreaming.value = false
    })
  }

  /** 清空 Agent 状态（取消请求并重置） */
  function clearAgent(): void {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    agentStreaming.value = false
    thinkingSteps.value = []
    agentAnswer.value = ''
    agentError.value = ''
    currentConversationId.value = null
  }

  return {
    agentStreaming,
    thinkingSteps,
    agentAnswer,
    agentError,
    currentConversationId,
    sendToAgent,
    clearAgent
  }
}
