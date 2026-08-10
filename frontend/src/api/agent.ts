import { getAccessToken } from '@/utils'
import { http } from './request'
import type {
  AgentEvent,
  AgentSessionListResponse,
  AgentSessionDetail,
  AgentConversationListResponse,
  AgentConversationDetail
} from '@/types/agent'

/**
 * Agent 智能体模块 API。
 *
 * 与 `streamAI` 的关键区别：
 *  - 端点前缀为 `/agents/`（而非 `/ai/`）。
 *  - SSE 帧携带 `type` 字段，支持多事件类型：
 *      thinking / tool_call / tool_result / content / done / error。
 *  - 回调为 `onEvent`（接收完整的 AgentEvent 对象），而非 `onChunk`。
 *
 * 所有接口前缀 `/api/v1`（VITE_API_BASE_URL 已包含）。
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL

/**
 * Agent SSE 流式请求通用函数。
 *
 * 后端端点 `POST /api/v1/agents/{endpoint}` 返回 `text/event-stream`，
 * 每条帧格式为 `data: {"type": "thinking|tool_call|tool_result|content|done|error", ...}\n\n`。
 *
 * 本函数用 fetch + ReadableStream 逐块读取并解析，
 * 通过回调将事件、完成、错误传递给调用方。
 *
 * @param endpoint  端点路径（不含 /agents/ 前缀），如 'reading-coach/chat'
 * @param body      POST 请求体
 * @param callbacks 回调集合：onEvent（事件）、onDone（完成）、onError（错误）
 * @param signal    可选的 AbortSignal，用于取消请求
 */
export async function streamAgent(
  endpoint: string,
  body: Record<string, unknown>,
  callbacks: {
    onEvent: (event: AgentEvent) => void
    onDone?: () => void
    onError?: (error: string) => void
  },
  signal?: AbortSignal
): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(`${API_BASE}/agents/${endpoint}`, {
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
        const event = JSON.parse(jsonStr) as AgentEvent

        // 优先通过 onEvent 回调分发所有事件（含 thinking / tool_call / tool_result / content）
        callbacks.onEvent(event)

        // done / error 事件额外触发对应回调
        if (event.type === 'done') {
          finish()
        } else if (event.type === 'error') {
          callbacks.onError?.(event.message || 'Unknown error')
        }
      } catch {
        // 跳过无法解析的行（可能是心跳或不完整帧）
      }
    }
  }

  // 流正常结束，确保 onDone 被调用
  finish()
}

// ============================================================
//  会话历史接口（非流式）
// ============================================================

/**
 * 获取当前用户的 Agent 会话列表（分页）。
 *
 * 结果按创建时间倒序排列，供"智能学习"页面左侧历史栏使用。
 */
export async function getAgentSessions(
  page: number = 1,
  pageSize: number = 20
): Promise<AgentSessionListResponse> {
  return http.get('/agents/sessions', {
    params: { page, page_size: pageSize }
  })
}

/**
 * 获取指定 Agent 会话的详情（含执行步骤）。
 *
 * 供点击历史记录后加载完整会话内容。
 */
export async function getAgentSessionDetail(
  sessionId: number
): Promise<AgentSessionDetail> {
  return http.get(`/agents/sessions/${sessionId}`)
}

// ============================================================
//  多轮对话接口（非流式）
// ============================================================

/**
 * 获取当前用户的 Agent 对话列表（分页）。
 *
 * 每个对话包含多轮 session，结果按更新时间倒序排列，
 * 供"智能学习"页面左侧历史栏使用。
 */
export async function getAgentConversations(
  page: number = 1,
  pageSize: number = 20
): Promise<AgentConversationListResponse> {
  return http.get('/agents/conversations', {
    params: { page, page_size: pageSize }
  })
}

/**
 * 获取指定 Agent 对话的详情（含多轮 session 及其执行步骤）。
 *
 * 供点击历史对话后加载完整多轮对话内容。
 */
export async function getAgentConversationDetail(
  conversationId: number
): Promise<AgentConversationDetail> {
  return http.get(`/agents/conversations/${conversationId}`)
}

/**
 * 删除指定 Agent 对话。
 */
export async function deleteAgentConversation(
  conversationId: number
): Promise<void> {
  return http.delete(`/agents/conversations/${conversationId}`)
}
