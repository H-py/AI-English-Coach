<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NSpin } from 'naive-ui'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github.css'
import { useAgent } from '@/composables/useAgent'
import { getAgentConversations, getAgentConversationDetail, deleteAgentConversation } from '@/api/agent'
import type { AgentConversation, ThinkingStep } from '@/types/agent'
import AgentThinkingFlow from '@/components/reading/AgentThinkingFlow.vue'
import SpeakerButton from '@/components/SpeakerButton.vue'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('json', json)

/**
 * 智能学习页面（ChatGPT 风格）。
 *
 * 左侧：对话历史列表 + 新对话按钮
 * 右侧：消息区（用户气泡 + AI 回复 + 思考流程）+ 底部输入框
 *
 * 支持多轮对话：每次 sendToAgent 会将消息追加到当前 conversation，
 * 后端通过 done 事件返回 conversation_id 供后续轮次使用。
 * 点击左侧对话可加载完整历史（含多轮 session 及步骤）。
 */

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  thinkingSteps?: ThinkingStep[]
  isStreaming?: boolean
  showThinking?: boolean
}

const { t } = useI18n()

const {
  agentStreaming,
  thinkingSteps,
  agentAnswer,
  agentError,
  currentConversationId,
  sendToAgent,
  clearAgent
} = useAgent()

// ---- 本地状态 ----

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const conversations = ref<AgentConversation[]>([])
const loadingConversations = ref(false)
const loadingDetail = ref(false)
const scrollRef = ref<HTMLElement | null>(null)
let messageIdCounter = 0

// ---- 示例提示 ----

const examplePrompts = [
  'Review my recent reading progress',
  'What words should I review today?',
  'Create a study plan for me',
  'Explain my common mistakes'
]

// ---- markdown 渲染 ----

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`
      } catch {
        // fall through
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  }
})

function renderMarkdown(content: string): string {
  if (!content) return ''
  return md.render(content)
}

/**
 * 从 Agent 回复中提取可发音的单词。
 * Agent 查词结果通常以 "**word** /IPA/" 开头，识别该模式供发音按钮使用。
 * 返回 { word, phonetic }；无匹配时返回 null。
 */
function extractSpeakable(content: string): { word: string; phonetic: string } | null {
  if (!content) return null
  const m = content.match(/\*\*(.+?)\*\*\s*(\/[^/\n]+\/)?/)
  if (!m || !m[1]) return null
  return { word: m[1].trim(), phonetic: m[2] || '' }
}

// ---- 时间格式化 ----

function formatTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMs / 3600000)
  const diffDay = Math.floor(diffMs / 86400000)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  if (diffHour < 24) return `${diffHour} 小时前`
  if (diffDay < 7) return `${diffDay} 天前`
  return date.toLocaleDateString()
}

// ---- 对话列表 ----

async function loadConversations(): Promise<void> {
  loadingConversations.value = true
  try {
    const res = await getAgentConversations(1, 30)
    conversations.value = res.items
  } catch {
    // 错误由拦截器处理
  } finally {
    loadingConversations.value = false
  }
}

// ---- 加载历史对话 ----

async function loadConversation(conversationId: number): Promise<void> {
  if (agentStreaming.value) return
  loadingDetail.value = true
  clearAgent()
  currentConversationId.value = conversationId
  messages.value = []

  try {
    const detail = await getAgentConversationDetail(conversationId)

    // 将每个 session 转换为一对 user + assistant 消息
    for (const session of detail.sessions || []) {
      // 用户消息
      messages.value.push({
        id: ++messageIdCounter,
        role: 'user',
        content: session.user_message
      })

      // 将后端 steps 转换为前端 ThinkingStep
      const steps: ThinkingStep[] = (session.steps || []).map((s) => ({
        id: s.id,
        type: s.step_type,
        content: s.content || '',
        toolName: s.tool_name || undefined,
        toolArguments: s.tool_arguments || undefined,
        toolResultData: s.tool_result || undefined,
        timestamp: s.created_at
      }))

      // AI 回复
      messages.value.push({
        id: ++messageIdCounter,
        role: 'assistant',
        content: session.final_answer || '',
        thinkingSteps: steps,
        isStreaming: false,
        showThinking: false
      })
    }
  } catch {
    // 错误由拦截器处理
  } finally {
    loadingDetail.value = false
  }

  nextTick(() => scrollToBottom())
}

// ---- 新建对话 ----

function startNewChat(): void {
  if (agentStreaming.value) return
  clearAgent()
  messages.value = []
}

// ---- 发送消息 ----

async function handleSend(): Promise<void> {
  const text = inputText.value.trim()
  if (!text || agentStreaming.value) return

  // 终结上一个进行中的消息
  finalizeStreamingMessage()

  inputText.value = ''

  // 添加用户消息
  messages.value.push({
    id: ++messageIdCounter,
    role: 'user',
    content: text
  })

  // 添加 AI 占位消息
  messages.value.push({
    id: ++messageIdCounter,
    role: 'assistant',
    content: '',
    thinkingSteps: [],
    isStreaming: true,
    showThinking: false
  })

  scrollToBottom()

  // 发送给 Agent，传入当前对话 ID 以支持多轮对话
  await sendToAgent(text, undefined, undefined, currentConversationId.value)
}

/** 从示例提示发送 */
function sendExample(prompt: string): void {
  inputText.value = prompt
  handleSend()
}

// ---- 辅助函数 ----

/** 终结当前正在流式输出的消息 */
function finalizeStreamingMessage(): void {
  const streamingMsg = messages.value.find(
    (m) => m.role === 'assistant' && m.isStreaming
  )
  if (streamingMsg) {
    streamingMsg.isStreaming = false
  }
}

/** 滚动到底部 */
function scrollToBottom(): void {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}

/** 删除对话 */
async function handleDeleteConversation(conversationId: number): Promise<void> {
  try {
    await deleteAgentConversation(conversationId)
    // 如果删除的是当前对话，清空消息区
    if (currentConversationId.value === conversationId) {
      clearAgent()
      messages.value = []
    }
    await loadConversations()
  } catch {
    // 错误由拦截器处理
  }
}

// ---- Watchers：同步 Agent 状态到当前流式消息 ----

watch(
  thinkingSteps,
  (steps) => {
    const streamingMsg = messages.value.find(
      (m) => m.role === 'assistant' && m.isStreaming
    )
    if (streamingMsg) {
      streamingMsg.thinkingSteps = [...steps]
    }
    scrollToBottom()
  },
  { deep: true }
)

watch(agentAnswer, (content) => {
  const streamingMsg = messages.value.find(
    (m) => m.role === 'assistant' && m.isStreaming
  )
  if (streamingMsg) {
    streamingMsg.content = content
  }
  scrollToBottom()
})

watch(agentStreaming, (streaming, prev) => {
  if (!streaming && prev) {
    const streamingMsg = messages.value.find(
      (m) => m.role === 'assistant' && m.isStreaming
    )
    if (streamingMsg) {
      streamingMsg.isStreaming = false
      if (agentError.value) {
        streamingMsg.content = `> ⚠️ ${agentError.value}`
      }
    }
  }
})

// 监听 currentConversationId 变化，刷新对话列表（新对话创建或切换时触发）
watch(currentConversationId, (val) => {
  if (val != null) {
    loadConversations()
  }
})

// ---- 生命周期 ----

onMounted(() => {
  loadConversations()
})
</script>

<template>
  <div class="sl">
    <!-- ============ 左侧：会话历史 ============ -->
    <aside class="sl-sidebar">
      <button class="sl-new-chat" @click="startNewChat">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="sl-new-chat__icon">
          <path d="M12 5v14M5 12h14" stroke-linecap="round" />
        </svg>
        <span>{{ t('agent.newChat') }}</span>
      </button>

      <div class="sl-sessions">
        <p class="sl-sessions__title">{{ t('agent.historyTitle') }}</p>

        <div v-if="loadingConversations && conversations.length === 0" class="sl-sessions__loading">
          <NSpin size="small" />
        </div>

        <p v-else-if="conversations.length === 0" class="sl-sessions__empty">
          {{ t('agent.emptyHistory') }}
        </p>

        <div
          v-for="conversation in conversations"
          :key="conversation.id"
          :class="['sl-session', { 'sl-session--active': currentConversationId === conversation.id }]"
          @click="loadConversation(conversation.id)"
        >
          <span class="sl-session__text">{{ conversation.title }}</span>
          <span class="sl-session__time">{{ formatTime(conversation.updated_at) }}</span>
          <button
            class="sl-session__delete"
            title="Delete"
            @click.stop="handleDeleteConversation(conversation.id)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" style="width:14px;height:14px">
              <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m-9 0v14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </aside>

    <!-- ============ 右侧：对话区 ============ -->
    <div class="sl-main">
      <!-- 加载遮罩 -->
      <div v-if="loadingDetail" class="sl-main__loading">
        <NSpin size="medium" />
      </div>

      <!-- 消息列表 -->
      <div ref="scrollRef" class="sl-messages">
        <!-- 空状态 -->
        <div v-if="messages.length === 0" class="sl-empty">
          <div class="sl-empty__icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" class="sl-empty__icon-svg">
              <path d="M12 3l2 7 7 2-7 2-2 7-2-7-7-2 7-2 2-7z" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </div>
          <h2 class="sl-empty__greeting">{{ t('agent.greeting') }}</h2>
          <p class="sl-empty__subtitle">{{ t('agent.subtitle') }}</p>

          <div class="sl-empty__prompts">
            <button
              v-for="prompt in examplePrompts"
              :key="prompt"
              class="sl-empty__prompt"
              @click="sendExample(prompt)"
            >
              {{ prompt }}
            </button>
          </div>
        </div>

        <!-- 消息列表 -->
        <div class="sl-messages__inner">
          <template v-for="msg in messages" :key="msg.id">
            <!-- 用户消息 -->
            <div v-if="msg.role === 'user'" class="sl-msg sl-msg--user">
              <div class="sl-msg__bubble sl-msg__bubble--user">{{ msg.content }}</div>
            </div>

            <!-- AI 消息 -->
            <div v-else class="sl-msg sl-msg--assistant">
              <!-- 思考流程（可折叠） -->
              <div
                v-if="msg.thinkingSteps && msg.thinkingSteps.length > 0"
                class="sl-thinking"
              >
                <button
                  class="sl-thinking__toggle"
                  @click="msg.showThinking = !msg.showThinking"
                >
                  <svg
                    class="sl-thinking__chevron"
                    :class="{ 'sl-thinking__chevron--open': msg.showThinking }"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M9 18l6-6-6-6" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <span>{{ t('agent.thinkingProcess') }}</span>
                  <span class="sl-thinking__count">{{ msg.thinkingSteps.length }}</span>
                </button>
                <div v-if="msg.showThinking" class="sl-thinking__body">
                  <AgentThinkingFlow
                    :steps="msg.thinkingSteps"
                    :streaming="msg.isStreaming || false"
                  />
                </div>
              </div>

              <!-- 加载指示器（无内容且无思考步骤时） -->
              <div
                v-if="msg.isStreaming && !msg.content && (!msg.thinkingSteps || msg.thinkingSteps.length === 0)"
                class="sl-msg__loading"
              >
                <NSpin size="small" />
                <span class="sl-msg__loading-text">{{ t('agent.thinkingLabel') }}</span>
              </div>

              <!-- 回复内容 -->
              <template v-if="msg.content">
                <!-- 单词发音工具条（Agent 查词结果） -->
                <div
                  v-if="extractSpeakable(msg.content)"
                  class="sl-msg__speak-row"
                >
                  <span class="sl-msg__speak-word">{{ extractSpeakable(msg.content)!.word }}</span>
                  <span v-if="extractSpeakable(msg.content)!.phonetic" class="sl-msg__speak-phonetic">
                    {{ extractSpeakable(msg.content)!.phonetic }}
                  </span>
                  <SpeakerButton :word="extractSpeakable(msg.content)!.word" size="small" />
                </div>
                <div
                  class="sl-msg__content markdown-body"
                  v-html="renderMarkdown(msg.content)"
                />
              </template>
              <span v-if="msg.isStreaming && msg.content" class="typing-cursor" />
            </div>
          </template>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="sl-input">
        <div class="sl-input__inner">
          <NInput
            v-model:value="inputText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            :placeholder="t('agent.agentPlaceholder')"
            :disabled="agentStreaming"
            @keydown.enter.exact.prevent="handleSend"
          />
          <NButton
            type="primary"
            :loading="agentStreaming"
            :disabled="!inputText.trim()"
            @click="handleSend"
          >
            <template #icon>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </template>
          </NButton>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
   布局容器
   ============================================================ */
.sl {
  display: flex;
  height: 100%;
  width: 100%;
  overflow: hidden;
  background: #ffffff;
}

/* ============================================================
   左侧侧边栏
   ============================================================ */
.sl-sidebar {
  display: flex;
  flex-direction: column;
  width: 260px;
  flex-shrink: 0;
  border-right: 1px solid #ececec;
  background: #f7f7f8;
  overflow: hidden;
}

.sl-new-chat {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px;
  padding: 10px 14px;
  border: 1px solid #d8d8e0;
  border-radius: 8px;
  background: #ffffff;
  font-size: 14px;
  font-weight: 500;
  color: #1d1d1f;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.sl-new-chat:hover {
  background: #f0f0f5;
  border-color: #c0c0c8;
}

.sl-new-chat__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.sl-sessions {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}

.sl-sessions__title {
  font-size: 12px;
  font-weight: 600;
  color: #86868b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 8px 8px 6px;
}

.sl-sessions__loading {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.sl-sessions__empty {
  font-size: 13px;
  color: #aeaeb2;
  padding: 12px 8px;
  text-align: center;
}

.sl-session {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
  margin-bottom: 2px;
}

.sl-session:hover {
  background: rgba(0, 0, 0, 0.04);
}

.sl-session--active {
  background: rgba(0, 0, 0, 0.06);
}

.sl-session__text {
  font-size: 13px;
  color: #3a3a3c;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 20px;
}

.sl-session__time {
  font-size: 11px;
  color: #aeaeb2;
}

.sl-session__delete {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #86868b;
  cursor: pointer;
  opacity: 0;
  transition: all 0.12s ease;
}

.sl-session:hover .sl-session__delete {
  opacity: 1;
}

.sl-session__delete:hover {
  background: rgba(0, 0, 0, 0.1);
  color: #ff3b30;
}

/* ============================================================
   右侧主区域
   ============================================================ */
.sl-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
  overflow: hidden;
}

.sl-main__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.6);
  z-index: 10;
}

/* ============================================================
   消息列表
   ============================================================ */
.sl-messages {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.sl-messages__inner {
  max-width: 760px;
  margin: 0 auto;
  padding: 24px 24px 12px;
}

/* ============================================================
   空状态
   ============================================================ */
.sl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
  padding: 40px 24px;
  text-align: center;
}

.sl-empty__icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #007aff, #5856d6);
  border-radius: 16px;
  margin-bottom: 20px;
}

.sl-empty__icon-svg {
  width: 30px;
  height: 30px;
  color: #ffffff;
}

.sl-empty__greeting {
  font-size: 24px;
  font-weight: 600;
  color: #1d1d1f;
  margin: 0 0 8px;
}

.sl-empty__subtitle {
  font-size: 14px;
  color: #86868b;
  line-height: 1.6;
  margin: 0 0 28px;
  max-width: 420px;
}

.sl-empty__prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 520px;
}

.sl-empty__prompt {
  padding: 8px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  background: #ffffff;
  font-size: 13px;
  color: #5a5a5e;
  cursor: pointer;
  transition: all 0.15s ease;
}

.sl-empty__prompt:hover {
  border-color: #007aff;
  color: #007aff;
  background: rgba(0, 122, 255, 0.04);
}

/* ============================================================
   消息气泡
   ============================================================ */
.sl-msg {
  margin-bottom: 24px;
}

.sl-msg--user {
  display: flex;
  justify-content: flex-end;
}

.sl-msg__bubble--user {
  max-width: 70%;
  padding: 10px 16px;
  background: #1d1d1f;
  color: #ffffff;
  border-radius: 18px 18px 4px 18px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.sl-msg--assistant {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 单词发音工具条（Agent 查词结果） */
.sl-msg__speak-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  padding: 6px 10px;
  border: 1px solid #e4e4e7;
  border-radius: 8px;
  background: #fafafa;
}

.sl-msg__speak-word {
  font-size: 14px;
  font-weight: 600;
  color: #171717;
}

.sl-msg__speak-phonetic {
  font-size: 13px;
  color: #71717a;
}

:global(html.dark) .sl-msg__speak-row {
  border-color: #3f3f46;
  background: #18181b;
}

:global(html.dark) .sl-msg__speak-word {
  color: #e5e5e5;
}

:global(html.dark) .sl-msg__speak-phonetic {
  color: #a1a1aa;
}

.sl-msg__content {
  font-size: 14px;
  line-height: 1.7;
  color: #1d1d1f;
  word-break: break-word;
}

.sl-msg__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.sl-msg__loading-text {
  font-size: 13px;
  color: #86868b;
}

/* ============================================================
   思考流程（可折叠）
   ============================================================ */
.sl-thinking {
  border: 1px solid #ececec;
  border-radius: 10px;
  overflow: hidden;
}

.sl-thinking__toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: #f7f7f8;
  font-size: 13px;
  font-weight: 500;
  color: #5a5a5e;
  cursor: pointer;
  transition: background 0.12s ease;
}

.sl-thinking__toggle:hover {
  background: #f0f0f5;
}

.sl-thinking__chevron {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform 0.2s ease;
  transform: rotate(0deg);
}

.sl-thinking__chevron--open {
  transform: rotate(90deg);
}

.sl-thinking__count {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: #86868b;
  background: #e0e0e5;
  border-radius: 10px;
  padding: 1px 7px;
}

.sl-thinking__body {
  padding: 10px 12px;
  border-top: 1px solid #ececec;
}

/* ============================================================
   Markdown 渲染样式
   ============================================================ */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  font-weight: 600;
  margin: 0.8em 0 0.4em;
  line-height: 1.3;
}

.markdown-body :deep(h1) { font-size: 1.3em; }
.markdown-body :deep(h2) { font-size: 1.2em; }
.markdown-body :deep(h3) { font-size: 1.1em; }

.markdown-body :deep(p) {
  margin: 0.5em 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.4em;
  margin: 0.5em 0;
}

.markdown-body :deep(li) {
  margin: 0.2em 0;
}

.markdown-body :deep(code) {
  background: #f5f5f5;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
}

.markdown-body :deep(pre) {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0.5em 0;
}

.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid #d1d1d6;
  padding-left: 12px;
  margin: 0.5em 0;
  color: #86868b;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}

.markdown-body :deep(a) {
  color: #007aff;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.5em 0;
  width: 100%;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e0e0e0;
  padding: 6px 10px;
  text-align: left;
}

/* ============================================================
   打字光标
   ============================================================ */
.typing-cursor {
  display: inline-block;
  width: 7px;
  height: 1em;
  background: #1d1d1f;
  margin-left: 2px;
  vertical-align: text-bottom;
  border-radius: 1px;
  animation: blink 1s steps(2) infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* ============================================================
   输入区
   ============================================================ */
.sl-input {
  flex-shrink: 0;
  border-top: 1px solid #ececec;
  padding: 16px 24px 20px;
  background: #ffffff;
}

.sl-input__inner {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.sl-input__inner :deep(.n-input) {
  flex: 1;
}

/* ============================================================
   暗色模式
   ============================================================ */
:global(html.dark) .sl {
  background: #0a0a0a;
}

/* 侧边栏暗色 */
:global(html.dark) .sl-sidebar {
  border-color: #1f1f1f;
  background: #131313;
}

:global(html.dark) .sl-new-chat {
  background: #1c1c1c;
  border-color: #2a2a2a;
  color: #ededed;
}

:global(html.dark) .sl-new-chat:hover {
  background: #262626;
  border-color: #3a3a3a;
}

:global(html.dark) .sl-sessions__title {
  color: #6e6e76;
}

:global(html.dark) .sl-sessions__empty {
  color: #6e6e76;
}

:global(html.dark) .sl-session:hover {
  background: rgba(255, 255, 255, 0.05);
}

:global(html.dark) .sl-session--active {
  background: rgba(255, 255, 255, 0.08);
}

:global(html.dark) .sl-session__text {
  color: #d4d4d8;
}

:global(html.dark) .sl-session__time {
  color: #6e6e76;
}

:global(html.dark) .sl-session__delete {
  color: #6e6e76;
}

:global(html.dark) .sl-session__delete:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ff453a;
}

/* 主区域暗色 */
:global(html.dark) .sl-main__loading {
  background: rgba(10, 10, 10, 0.6);
}

/* 消息暗色 */
:global(html.dark) .sl-msg__bubble--user {
  background: #2a2a2a;
  color: #ededed;
}

:global(html.dark) .sl-msg__content {
  color: #d4d4d8;
}

:global(html.dark) .sl-msg__loading-text {
  color: #6e6e76;
}

/* 思考流程暗色 */
:global(html.dark) .sl-thinking {
  border-color: #1f1f1f;
}

:global(html.dark) .sl-thinking__toggle {
  background: #1a1a1a;
  color: #a3a3a3;
}

:global(html.dark) .sl-thinking__toggle:hover {
  background: #262626;
}

:global(html.dark) .sl-thinking__count {
  background: #2a2a2a;
  color: #6e6e76;
}

:global(html.dark) .sl-thinking__body {
  border-color: #1f1f1f;
}

/* Markdown 暗色 */
:global(html.dark) .markdown-body :deep(code) {
  background: #262626;
}

:global(html.dark) .markdown-body :deep(pre) {
  background: #1a1a1a;
}

:global(html.dark) .markdown-body :deep(blockquote) {
  border-color: #3a3a3c;
  color: #86868b;
}

:global(html.dark) .markdown-body :deep(a) {
  color: #0a84ff;
}

:global(html.dark) .markdown-body :deep(th),
:global(html.dark) .markdown-body :deep(td) {
  border-color: #2a2a2a;
}

:global(html.dark) .typing-cursor {
  background: #d4d4d8;
}

/* 输入区暗色 */
:global(html.dark) .sl-input {
  border-color: #1f1f1f;
  background: #0a0a0a;
}

/* 空状态暗色 */
:global(html.dark) .sl-empty__greeting {
  color: #ededed;
}

:global(html.dark) .sl-empty__subtitle {
  color: #6e6e76;
}

:global(html.dark) .sl-empty__prompt {
  background: #1c1c1c;
  border-color: #2a2a2a;
  color: #a3a3a3;
}

:global(html.dark) .sl-empty__prompt:hover {
  border-color: #0a84ff;
  color: #0a84ff;
  background: rgba(10, 132, 255, 0.08);
}
</style>
