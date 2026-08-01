<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NSpin, useMessage } from 'naive-ui'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github.css'
import { useReading } from '@/composables/useReading'

// 注册常用语言（按需加载，避免全量引入 highlight.js）
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('json', json)

/**
 * AI 助手面板（阅读页右侧）。
 *
 * 职责：
 *  - 接收父组件传递的选中文本 selectedText 及其上下文 selectedContext，
 *    自动判断单词 / 句子并触发对应 AI 流式交互。
 *  - 提供两个标签页：解释（explain / sentence / paragraph）与问答（chat）。
 *  - 解释类模式共享 aiContent 内容区；chat 模式独立维护 chatMessages 对话气泡。
 *  - AI 回复完成后提供"收藏单词"/"收藏句子"按钮。
 *  - 使用 markdown-it 渲染 AI 回复，支持 highlight.js 代码高亮。
 *
 * 组件自包含：通过 props 接收选中信息，内部自动触发 AI 交互。
 */

const props = defineProps<{
  /** 当前文章 ID */
  articleId: number
  /** 用户选中的文本 */
  selectedText: string
  /** 选中文本所在的完整句子（作为 AI 上下文） */
  selectedContext: string
}>()

const { t } = useI18n()
const message = useMessage()

const {
  streaming,
  aiContent,
  aiMode,
  chatMessages,
  explainWord,
  analyzeSentence,
  translateSentence,
  paragraphSummary,
  sendChat,
  saveWord,
  saveSentence
} = useReading()

// ---- markdown 渲染器 ----

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`
      } catch {
        // fall through to escape
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  }
})

/** 将 markdown 文本渲染为 HTML */
function renderMarkdown(content: string): string {
  if (!content) return ''
  return md.render(content)
}

/** 解释类模式的渲染内容（computed，随 aiContent 变化自动更新） */
const renderedContent = computed(() => renderMarkdown(aiContent.value))

// ---- 标签页 ----

const activeTab = ref<'explain' | 'chat'>('explain')

// ---- 选中文本判断 ----

/** 选中文本的词数（按空白分割） */
const wordCount = computed(() => {
  if (!props.selectedText) return 0
  return props.selectedText.trim().split(/\s+/).filter(Boolean).length
})

/** 是否为单词（少于 3 个词视为单词 / 短语） */
const isWord = computed(() => wordCount.value > 0 && wordCount.value < 3)

// ---- 收藏状态 ----

const wordSaved = ref(false)
const sentenceSaved = ref(false)

// ---- chat 输入 ----

const chatInput = ref('')
const chatScrollRef = ref<HTMLElement | null>(null)

// ---- 辅助 computed ----

/** chat 模式最后一条 assistant 消息的内容（用于判断是否还在"思考中"） */
const lastAssistantContent = computed(() => {
  const last = chatMessages.value[chatMessages.value.length - 1]
  return last && last.role === 'assistant' ? last.content : ''
})

// ============================================================
//  选中文本变化时自动触发 AI 交互
// ============================================================

watch(
  () => props.selectedText,
  (newText) => {
    if (!newText) return

    // 选中文本时自动切换到解释标签
    activeTab.value = 'explain'
    wordSaved.value = false
    sentenceSaved.value = false

    if (isWord.value) {
      // 单词 / 短语：自动触发解释
      explainWord(newText, props.selectedContext || newText, props.articleId)
    }
    // 长句（>= 3 词）：不自动触发，显示选项按钮让用户选择
  }
)

// ============================================================
//  解释类模式操作
// ============================================================

/**
 * 手动触发解释。
 * 单词/短语：调用 explainWord 进行单词释义；
 * 句子（>= 3 词）：调用 translateSentence 进行整句翻译。
 */
function handleExplain(): void {
  if (!props.selectedText) return
  if (isWord.value) {
    wordSaved.value = false
    explainWord(props.selectedText, props.selectedContext || props.selectedText, props.articleId)
  } else {
    sentenceSaved.value = false
    translateSentence(props.selectedText, props.articleId)
  }
}

/** 手动触发句子分析 */
function handleAnalyzeSentence(): void {
  if (!props.selectedText) return
  sentenceSaved.value = false
  analyzeSentence(props.selectedText, props.articleId)
}

/** 手动触发段落总结 */
function handleParagraphSummary(): void {
  const paragraph = props.selectedContext || props.selectedText
  if (!paragraph) return
  paragraphSummary(paragraph, props.articleId)
}

// ============================================================
//  chat 模式操作
// ============================================================

/** 发送问答消息 */
async function handleSendChat(): Promise<void> {
  const text = chatInput.value.trim()
  if (!text || streaming.value) return
  chatInput.value = ''
  await sendChat(text, props.articleId)
  scrollToBottom()
}

/** 滚动聊天区到底部 */
function scrollToBottom(): void {
  nextTick(() => {
    if (chatScrollRef.value) {
      chatScrollRef.value.scrollTop = chatScrollRef.value.scrollHeight
    }
  })
}

// chatMessages 数量变化时自动滚动
watch(() => chatMessages.value.length, () => scrollToBottom())
// 流式结束后滚动
watch(streaming, (val) => {
  if (!val) scrollToBottom()
})

// ============================================================
//  收藏操作
// ============================================================

/** 收藏当前解释的单词 */
async function handleSaveWord(): Promise<void> {
  if (!props.selectedText) return
  try {
    await saveWord(
      props.selectedText,
      props.selectedContext || props.selectedText,
      props.articleId,
      aiContent.value
    )
    wordSaved.value = true
    message.success(t('reading.wordSaved'))
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}

/** 收藏当前分析的句子 */
async function handleSaveSentence(): Promise<void> {
  if (!props.selectedText) return
  try {
    await saveSentence(props.selectedText, props.articleId, aiContent.value)
    sentenceSaved.value = true
    message.success(t('reading.sentenceSaved'))
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}
</script>

<template>
  <div class="ai-panel">
    <!-- 顶部：标题 + 标签栏 -->
    <div class="ai-panel__header">
      <span class="ai-panel__title">{{ t('reading.aiAssistant') }}</span>
      <div class="ai-panel__tabs">
        <button
          :class="['ai-tab', { 'ai-tab--active': activeTab === 'explain' }]"
          @click="activeTab = 'explain'"
        >
          {{ t('reading.explain') }}
        </button>
        <button
          :class="['ai-tab', { 'ai-tab--active': activeTab === 'chat' }]"
          @click="activeTab = 'chat'"
        >
          {{ t('reading.chat') }}
        </button>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="ai-panel__body">
      <!-- ======================== 解释模式 ======================== -->
      <template v-if="activeTab === 'explain'">
        <!-- 长句选中时的操作选项 -->
        <div
          v-if="selectedText && !isWord && !streaming"
          class="ai-panel__options"
        >
          <p class="ai-panel__hint">{{ t('reading.selectPrompt') }}</p>
          <div class="ai-panel__option-btns">
            <NButton size="small" secondary @click="handleExplain">
              {{ isWord ? t('reading.explain') : t('reading.translate') }}
            </NButton>
            <NButton size="small" secondary @click="handleAnalyzeSentence">
              {{ t('reading.sentenceAnalysis') }}
            </NButton>
            <NButton size="small" secondary @click="handleParagraphSummary">
              {{ t('reading.paragraphSummary') }}
            </NButton>
          </div>
        </div>

        <!-- 思考中（streaming 已开始但尚未收到内容） -->
        <div v-if="streaming && !aiContent" class="ai-panel__thinking">
          <NSpin size="small" />
          <span class="ai-panel__hint">{{ t('reading.thinking') }}</span>
        </div>

        <!-- AI 内容（markdown 渲染） -->
        <div v-if="aiContent" class="ai-panel__content">
          <!-- eslint-disable vue/no-v-html -->
          <div class="markdown-body" v-html="renderedContent" />
          <span v-if="streaming" class="typing-cursor" />
        </div>

        <!-- 收藏按钮 -->
        <div v-if="!streaming && aiContent" class="ai-panel__actions">
          <NButton
            v-if="aiMode === 'explain'"
            size="small"
            :disabled="wordSaved"
            @click="handleSaveWord"
          >
            {{ wordSaved ? t('reading.saved') : t('reading.saveWord') }}
          </NButton>
          <NButton
            v-if="aiMode === 'sentence' || aiMode === 'translate'"
            size="small"
            :disabled="sentenceSaved"
            @click="handleSaveSentence"
          >
            {{ sentenceSaved ? t('reading.saved') : t('reading.saveSentence') }}
          </NButton>
        </div>

        <!-- 空状态（无选中文本且无内容） -->
        <div
          v-if="!selectedText && !aiContent && !streaming"
          class="ai-panel__empty"
        >
          <p class="ai-panel__hint">{{ t('reading.noSelection') }}</p>
        </div>
      </template>

      <!-- ======================== 问答模式 ======================== -->
      <template v-else>
        <div ref="chatScrollRef" class="ai-panel__chat">
          <!-- 空状态 -->
          <div v-if="chatMessages.length === 0" class="ai-panel__empty">
            <p class="ai-panel__hint">{{ t('reading.chatPrompt') }}</p>
          </div>

          <!-- 对话气泡列表 -->
          <template v-for="(msg, i) in chatMessages" :key="i">
            <div
              v-if="!(msg.role === 'assistant' && !msg.content && streaming && i === chatMessages.length - 1)"
              :class="['chat-bubble', `chat-bubble--${msg.role}`]"
            >
              <!-- eslint-disable vue/no-v-html -->
              <div
                v-if="msg.role === 'assistant'"
                class="markdown-body"
                v-html="renderMarkdown(msg.content)"
              />
              <template v-else>{{ msg.content }}</template>
              <span
                v-if="msg.role === 'assistant' && streaming && i === chatMessages.length - 1 && msg.content"
                class="typing-cursor"
              />
            </div>
          </template>

          <!-- 思考中指示器 -->
          <div v-if="streaming && !lastAssistantContent" class="ai-panel__thinking">
            <NSpin size="small" />
            <span class="ai-panel__hint">{{ t('reading.thinking') }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- 底部输入区（仅 chat 模式） -->
    <div v-if="activeTab === 'chat'" class="ai-panel__footer">
      <NInput
        v-model:value="chatInput"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 4 }"
        :placeholder="t('reading.askPlaceholder')"
        @keydown.enter.exact.prevent="handleSendChat"
      />
      <NButton
        type="primary"
        :loading="streaming"
        :disabled="!chatInput.trim()"
        @click="handleSendChat"
      >
        {{ t('reading.send') }}
      </NButton>
    </div>
  </div>
</template>

<style scoped>
/* ---- 面板容器 ---- */
.ai-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border: 1px solid #ececec;
  border-radius: 12px;
  overflow: hidden;
}

/* ---- 顶部 ---- */
.ai-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.ai-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: #1d1d1f;
}

.ai-panel__tabs {
  display: flex;
  gap: 4px;
}

.ai-tab {
  padding: 4px 12px;
  font-size: 13px;
  color: #86868b;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ai-tab:hover {
  color: #1d1d1f;
  background: #f5f5f5;
}

.ai-tab--active {
  color: #1d1d1f;
  background: #f0f0f0;
  font-weight: 500;
}

/* ---- 内容区 ---- */
.ai-panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* ---- 选项区 ---- */
.ai-panel__options {
  padding: 12px;
  background: #f9f9f9;
  border-radius: 8px;
  margin-bottom: 12px;
}

.ai-panel__option-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

/* ---- 提示文字 ---- */
.ai-panel__hint {
  font-size: 13px;
  color: #86868b;
  margin: 0;
}

/* ---- 思考中指示器 ---- */
.ai-panel__thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

/* ---- AI 内容区 ---- */
.ai-panel__content {
  min-height: 40px;
}

/* ---- 收藏按钮区 ---- */
.ai-panel__actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

/* ---- 空状态 ---- */
.ai-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  text-align: center;
}

/* ---- chat 区 ---- */
.ai-panel__chat {
  display: flex;
  flex-direction: column;
}

/* ---- markdown 渲染样式（:deep 穿透 v-html 内容） ---- */
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: #1d1d1f;
  word-break: break-word;
}

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
  color: #1d1d1f;
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

/* ---- 聊天气泡 ---- */
.chat-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  margin-bottom: 10px;
  max-width: 88%;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.chat-bubble--user {
  background: #1d1d1f;
  color: #ffffff;
  margin-left: auto;
  border-bottom-right-radius: 4px;
}

.chat-bubble--assistant {
  background: #f5f5f5;
  color: #1d1d1f;
  border-bottom-left-radius: 4px;
}

/* ---- 打字光标 ---- */
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

/* ---- 底部输入区 ---- */
.ai-panel__footer {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
  align-items: flex-end;
}

.ai-panel__footer :deep(.n-input) {
  flex: 1;
}

/* ============================================================
   暗色模式
   ============================================================ */
:global(html.dark) .ai-panel {
  background: #161616;
  border-color: #262626;
}

:global(html.dark) .ai-panel__header {
  border-color: #1f1f1f;
}

:global(html.dark) .ai-panel__title {
  color: #ededed;
}

:global(html.dark) .ai-tab {
  color: #86868b;
}

:global(html.dark) .ai-tab:hover {
  color: #ededed;
  background: #1f1f1f;
}

:global(html.dark) .ai-tab--active {
  color: #ededed;
  background: #262626;
}

:global(html.dark) .ai-panel__options {
  background: #1a1a1a;
}

:global(html.dark) .ai-panel__actions {
  border-color: #1f1f1f;
}

:global(html.dark) .ai-panel__footer {
  border-color: #1f1f1f;
}

:global(html.dark) .markdown-body {
  color: #d4d4d8;
}

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
  color: #ededed;
}

:global(html.dark) .markdown-body :deep(th),
:global(html.dark) .markdown-body :deep(td) {
  border-color: #2a2a2a;
}

:global(html.dark) .chat-bubble--user {
  background: #ededed;
  color: #0a0a0a;
}

:global(html.dark) .chat-bubble--assistant {
  background: #1f1f1f;
  color: #d4d4d8;
}

:global(html.dark) .typing-cursor {
  background: #d4d4d8;
}
</style>
