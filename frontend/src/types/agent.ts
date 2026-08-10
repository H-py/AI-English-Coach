/**
 * Agent 智能体模块类型定义。
 *
 * 与后端 `/api/v1/agents/reading-coach/chat` SSE 流式接口一一对应。
 * 后端返回多事件类型（thinking / tool_call / tool_result / content / done / error），
 * 每种事件有不同的字段组合，前端通过 type 字段分发处理。
 */

/** Agent 事件类型 */
export type AgentEventType = 'conversation_started' | 'thinking' | 'tool_call' | 'tool_result' | 'content' | 'done' | 'error'

/**
 * Agent SSE 事件帧。
 *
 * 后端每条帧格式为 `data: {"type": "...", ...}\n\n`，
 * 不同 type 携带的字段不同：
 *  - conversation_started: conversation_id（当前对话 ID，流开始时发送）
 *  - thinking:  content（思考内容文本）
 *  - tool_call: tool（工具名）、arguments（调用参数）
 *  - tool_result: tool（工具名）、content（结果摘要）、data（结构化数据）
 *  - content:   content（最终回复内容片段）
 *  - done:      conversation_id（当前对话 ID）
 *  - error:     message（错误信息）
 */
export interface AgentEvent {
  type: AgentEventType
  content?: string
  tool?: string
  arguments?: Record<string, unknown>
  data?: Record<string, unknown>
  message?: string
  conversation_id?: number
}

/**
 * 思考步骤（UI 展示用）。
 *
 * 将 thinking / tool_call / tool_result 三类事件
 * 统一记录为有序的步骤列表，供 AgentThinkingFlow 组件渲染。
 */
export interface ThinkingStep {
  id: number
  type: 'thinking' | 'tool_call' | 'tool_result'
  content: string
  toolName?: string
  toolArguments?: Record<string, unknown>
  toolResultData?: Record<string, unknown>
  timestamp: string
}

/** Agent 聊天请求 payload */
export interface AgentChatPayload {
  message: string
  article_id?: number | null
  history_id?: number | null
  conversation_id?: number | null
}

/** Agent 会话记录（列表项） */
export interface AgentSession {
  id: number
  agent_type: string
  user_message: string
  final_answer: string | null
  total_steps: number
  status: string
  created_at: string
}

/** Agent 执行步骤记录 */
export interface AgentStep {
  id: number
  step_order: number
  step_type: 'thinking' | 'tool_call' | 'tool_result'
  content: string | null
  tool_name: string | null
  tool_arguments: Record<string, unknown> | null
  tool_result: Record<string, unknown> | null
  created_at: string
}

/** Agent 会话详情（含步骤） */
export interface AgentSessionDetail extends AgentSession {
  steps: AgentStep[]
}

/** 会话列表响应 */
export interface AgentSessionListResponse {
  items: AgentSession[]
  total: number
  page: number
  page_size: number
}

/** Agent 多轮对话（列表项） */
export interface AgentConversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

/** Agent 对话详情（含多轮 session） */
export interface AgentConversationDetail extends AgentConversation {
  sessions: AgentSessionDetail[]
}

/** 对话列表响应 */
export interface AgentConversationListResponse {
  items: AgentConversation[]
  total: number
  page: number
  page_size: number
}
