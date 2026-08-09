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
  /** 当前阅读会话的 history ID（用于关联活动日志和生成总结） */
  historyId: number | null
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
  saveSentence,
  loadChatHistory,
  // 阅读总结
  summary,
  generatingSummary,
  generateSummary,
  loadSummary,
  // 练习题
  quiz,
  generatingQuiz,
  submittingQuiz,
  quizResults,
  quizAnswers,
  generateQuiz,
  loadLatestQuiz,
  submitQuizAnswers
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

const activeTab = ref<'explain' | 'chat' | 'summary'>('explain')

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
      explainWord(newText, props.selectedContext || newText, props.articleId, props.historyId)
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
    explainWord(props.selectedText, props.selectedContext || props.selectedText, props.articleId, props.historyId)
  } else {
    sentenceSaved.value = false
    translateSentence(props.selectedText, props.articleId, props.historyId)
  }
}

/** 手动触发句子分析 */
function handleAnalyzeSentence(): void {
  if (!props.selectedText) return
  sentenceSaved.value = false
  analyzeSentence(props.selectedText, props.articleId, props.historyId)
}

/** 手动触发段落总结 */
function handleParagraphSummary(): void {
  const paragraph = props.selectedContext || props.selectedText
  if (!paragraph) return
  paragraphSummary(paragraph, props.articleId, props.historyId)
}

// ============================================================
//  chat 模式操作
// ============================================================

/** 发送问答消息 */
async function handleSendChat(): Promise<void> {
  const text = chatInput.value.trim()
  if (!text || streaming.value) return
  chatInput.value = ''
  await sendChat(text, props.articleId, props.historyId)
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

// 首次切换到 chat 标签时加载对话历史（懒加载，避免每次进页面都请求）
watch(activeTab, (newTab) => {
  if (newTab === 'chat' && chatMessages.value.length === 0) {
    loadChatHistory(props.articleId).then(() => scrollToBottom())
  }
  // 首次切换到总结标签时加载已有总结和练习题
  if (newTab === 'summary' && props.historyId) {
    if (summary.value === null) {
      loadSummary(props.historyId)
    }
    if (quiz.value === null) {
      loadLatestQuiz(props.historyId)
    }
  }
})

// ============================================================
//  收藏操作
// ============================================================

/**
 * 将 markdown 文本转为纯文本，去除所有格式标记。
 * **bold** → bold, *italic* → italic, __bold__ → bold, _italic_ → italic,
 * `code` → code, > quote → quote, - list → • list, 1. list → list, # 标题 → 标题
 */
function stripMarkdown(text: string): string {
  return text
    // 加粗: **text** 或 __text__
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    // 斜体: *text* 或 _text_（在加粗处理之后，避免误匹配）
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '$1')
    .replace(/(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/g, '$1')
    // 行内代码: `code`
    .replace(/`([^`]+)`/g, '$1')
    // 标题: # / ## / ### ...
    .replace(/^#{1,6}\s+/gm, '')
    // 引用块标记: > text
    .replace(/^>\s?/gm, '')
    // 无序列表: - / * / + 开头
    .replace(/^\s*[-*+]\s+/gm, '• ')
    // 有序列表: 1. 2. ...
    .replace(/^\s*\d+\.\s+/gm, '')
    // 多余空行压缩
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/**
 * 从单词 AI 解释中提取收藏内容。
 * 保留单词 + 音标 + 释义，去除例句部分和所有 markdown 格式标记。
 */
function extractWordMeaning(content: string): string {
  // 去除"例句"及之后的内容
  const text = content.split(/\n例句[：:]/i)[0]
  return stripMarkdown(text)
}

/**
 * 清理句子笔记：去除开头的引用块（"> 原句"），并去除 markdown 格式标记。
 */
function cleanSentenceNote(content: string): string {
  // aiContent 以 "> 原句\n\n" 开头，去掉这部分只保留 AI 分析内容
  const match = content.match(/^>.*?\n\n([\s\S]*)/)
  const text = match ? match[1] : content
  return stripMarkdown(text)
}

/** 收藏当前解释的单词（保留音标+释义，去除例句和格式标记） */
async function handleSaveWord(): Promise<void> {
  if (!props.selectedText) return
  try {
    await saveWord(
      props.selectedText,
      props.selectedContext || props.selectedText,
      props.articleId,
      extractWordMeaning(aiContent.value)
    )
    wordSaved.value = true
    message.success(t('reading.wordSaved'))
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}

/** 收藏当前分析的句子（保存纯文本笔记，去除 markdown 标记） */
async function handleSaveSentence(): Promise<void> {
  if (!props.selectedText) return
  try {
    await saveSentence(
      props.selectedText,
      props.articleId,
      cleanSentenceNote(aiContent.value)
    )
    sentenceSaved.value = true
    message.success(t('reading.sentenceSaved'))
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}

// ============================================================
//  阅读总结 & 练习题操作
// ============================================================

/** 所有题目是否都已作答 */
const allQuestionsAnswered = computed(() => {
  if (!quiz.value) return false
  return quiz.value.questions.every((q) => quizAnswers.value[q.id])
})

/** 生成阅读总结 */
async function handleGenerateSummary(): Promise<void> {
  if (!props.historyId) return
  await generateSummary(props.historyId)
}

/** 生成练习题 */
async function handleGenerateQuiz(): Promise<void> {
  if (!props.historyId) return
  await generateQuiz(props.articleId, props.historyId)
}

/** 提交练习题答案 */
async function handleSubmitQuiz(): Promise<void> {
  if (!quiz.value) return
  await submitQuizAnswers(quiz.value.id)
  if (quizResults.value) {
    message.success(t('reading.quizSubmitted', { score: quizResults.value.score, total: quizResults.value.total }))
  }
}

/** 根据选项索引获取字母（0→A, 1→B, ...） */
function optionLetter(index: number): string {
  return String.fromCharCode(65 + index)
}

/** 格式化阅读时长 */
function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '0s'
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins === 0) return `${secs}s`
  if (secs === 0) return `${mins}m`
  return `${mins}m${secs}s`
}

/** 从判分结果中获取某道题的正确答案 */
function getCorrectAnswer(questionId: number): string {
  if (!quizResults.value) return ''
  const result = quizResults.value.results.find((r) => r.question_id === questionId)
  return result?.correct_answer ?? ''
}

/** 从判分结果中获取某道题的解析 */
function getExplanation(questionId: number): string {
  if (!quizResults.value) return ''
  const result = quizResults.value.results.find((r) => r.question_id === questionId)
  return result?.explanation ?? ''
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
        <button
          :class="['ai-tab', { 'ai-tab--active': activeTab === 'summary' }]"
          @click="activeTab = 'summary'"
        >
          {{ t('reading.summary') }}
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
      <template v-else-if="activeTab === 'chat'">
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

      <!-- ======================== 总结模式 ======================== -->
      <template v-else>
        <!-- 无 historyId 时提示 -->
        <div v-if="!historyId" class="ai-panel__empty">
          <p class="ai-panel__hint">{{ t('reading.summaryNoHistory') }}</p>
        </div>

        <template v-else>
          <!-- 总结区域 -->
          <!-- 生成中 -->
          <div v-if="generatingSummary" class="ai-panel__thinking">
            <NSpin size="small" />
            <span class="ai-panel__hint">{{ t('reading.generatingSummary') }}</span>
          </div>

          <!-- 无总结：生成按钮 -->
          <div v-else-if="!summary" class="ai-panel__summary-empty">
            <p class="ai-panel__hint">{{ t('reading.summaryHint') }}</p>
            <NButton size="small" type="primary" @click="handleGenerateSummary">
              {{ t('reading.generateSummary') }}
            </NButton>
          </div>

          <!-- 已有总结：展示内容 -->
          <template v-else>
            <!-- 活动统计 -->
            <div class="summary-stats">
              <span class="summary-stat">
                {{ t('reading.statWords', { count: summary.activity_stats?.word_count ?? 0 }) }}
              </span>
              <span class="summary-stat">
                {{ t('reading.statSentences', { count: summary.activity_stats?.sentence_count ?? 0 }) }}
              </span>
              <span class="summary-stat">
                {{ t('reading.statChats', { count: summary.activity_stats?.chat_count ?? 0 }) }}
              </span>
              <span class="summary-stat">
                {{ t('reading.statDuration', { duration: formatDuration(summary.activity_stats?.duration_seconds) }) }}
              </span>
            </div>

            <!-- 总结正文 -->
            <!-- eslint-disable vue/no-v-html -->
            <div class="markdown-body summary-content" v-html="renderMarkdown(summary.content)" />

            <!-- 重新生成按钮 -->
            <div class="summary-actions">
              <NButton size="small" secondary @click="handleGenerateSummary">
                {{ t('reading.regenerateSummary') }}
              </NButton>
            </div>
          </template>

          <!-- 练习题区域 -->
          <div v-if="summary" class="quiz-section">
            <div class="quiz-section__divider" />

            <!-- 生成中 -->
            <div v-if="generatingQuiz" class="ai-panel__thinking">
              <NSpin size="small" />
              <span class="ai-panel__hint">{{ t('reading.generatingQuiz') }}</span>
            </div>

            <!-- 无练习题：生成按钮 -->
            <div v-else-if="!quiz" class="quiz-section__empty">
              <NButton size="small" type="primary" @click="handleGenerateQuiz">
                {{ t('reading.startQuiz') }}
              </NButton>
            </div>

            <!-- 有练习题 -->
            <template v-else>
              <div class="quiz-header">
                <span class="quiz-header__title">{{ t('reading.quizTitle') }}</span>
                <span v-if="quizResults" class="quiz-header__score">
                  {{ t('reading.quizScore', { score: quizResults.score, total: quizResults.total }) }}
                </span>
              </div>

              <!-- 题目列表 -->
              <div
                v-for="(q, qi) in quiz.questions"
                :key="q.id"
                class="quiz-question"
              >
                <p class="quiz-question__text">
                  {{ qi + 1 }}. {{ q.question }}
                </p>
                <div class="quiz-question__options">
                  <label
                    v-for="(opt, oi) in q.options"
                    :key="oi"
                    :class="[
                      'quiz-option',
                      {
                        'quiz-option--selected': quizAnswers[q.id] === optionLetter(oi),
                        'quiz-option--correct': quizResults && optionLetter(oi) === getCorrectAnswer(q.id),
                        'quiz-option--wrong': quizResults && quizAnswers[q.id] === optionLetter(oi) && optionLetter(oi) !== getCorrectAnswer(q.id),
                      }
                    ]"
                  >
                    <input
                      :type="'radio'"
                      :name="`q-${q.id}`"
                      :value="optionLetter(oi)"
                      :checked="quizAnswers[q.id] === optionLetter(oi)"
                      :disabled="!!quizResults"
                      class="quiz-option__radio"
                      @change="quizAnswers[q.id] = optionLetter(oi)"
                    />
                    <span class="quiz-option__text">{{ opt }}</span>
                  </label>
                </div>
                <!-- 解析（仅提交后显示） -->
                <div v-if="quizResults" class="quiz-question__explanation">
                  <p v-if="quizAnswers[q.id] === getCorrectAnswer(q.id)" class="quiz-correct">
                    {{ t('reading.correctAnswer') }}
                  </p>
                  <p v-else class="quiz-wrong">
                    {{ t('reading.wrongAnswer') }}
                    {{ t('reading.correctIs', { answer: getCorrectAnswer(q.id) }) }}
                  </p>
                  <p class="quiz-explanation-text">{{ getExplanation(q.id) }}</p>
                </div>
              </div>

              <!-- 提交按钮 -->
              <div v-if="!quizResults" class="quiz-actions">
                <NButton
                  size="small"
                  type="primary"
                  :disabled="!allQuestionsAnswered"
                  :loading="submittingQuiz"
                  @click="handleSubmitQuiz"
                >
                  {{ t('reading.submitQuiz') }}
                </NButton>
              </div>

              <!-- 重新练习按钮 -->
              <div v-else class="quiz-actions">
                <NButton size="small" secondary @click="handleGenerateQuiz">
                  {{ t('reading.retryQuiz') }}
                </NButton>
              </div>
            </template>
          </div>
        </template>
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

/* ---- 总结模式 ---- */
.ai-panel__summary-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 48px 16px;
  text-align: center;
}

.summary-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.summary-stat {
  font-size: 12px;
  color: #86868b;
  background: #f5f5f5;
  padding: 4px 10px;
  border-radius: 12px;
}

.summary-content {
  margin-bottom: 12px;
}

.summary-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

/* ---- 练习题区域 ---- */
.quiz-section {
  margin-top: 16px;
}

.quiz-section__divider {
  height: 1px;
  background: #f0f0f0;
  margin-bottom: 16px;
}

.quiz-section__empty {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

.quiz-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.quiz-header__title {
  font-size: 14px;
  font-weight: 600;
  color: #1d1d1f;
}

.quiz-header__score {
  font-size: 13px;
  font-weight: 600;
  color: #34c759;
}

.quiz-question {
  margin-bottom: 16px;
}

.quiz-question__text {
  font-size: 14px;
  color: #1d1d1f;
  margin: 0 0 8px;
  line-height: 1.6;
}

.quiz-question__options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quiz-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  cursor: pointer;
  transition: all 0.15s ease;
}

.quiz-option:hover {
  background: #f9f9f9;
}

.quiz-option--selected {
  border-color: #1d1d1f;
  background: #f0f0f0;
}

.quiz-option--correct {
  border-color: #34c759;
  background: rgba(52, 199, 89, 0.08);
}

.quiz-option--wrong {
  border-color: #ff3b30;
  background: rgba(255, 59, 48, 0.08);
}

.quiz-option__radio {
  margin-top: 3px;
  cursor: pointer;
}

.quiz-option__text {
  font-size: 13px;
  color: #1d1d1f;
  line-height: 1.5;
  flex: 1;
}

.quiz-question__explanation {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f9f9f9;
  border-radius: 8px;
}

.quiz-correct {
  font-size: 13px;
  font-weight: 600;
  color: #34c759;
  margin: 0 0 4px;
}

.quiz-wrong {
  font-size: 13px;
  font-weight: 600;
  color: #ff3b30;
  margin: 0 0 4px;
}

.quiz-explanation-text {
  font-size: 13px;
  color: #86868b;
  margin: 0;
  line-height: 1.5;
}

.quiz-actions {
  display: flex;
  justify-content: center;
  margin-top: 16px;
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

/* ---- 总结/练习题暗色模式 ---- */
:global(html.dark) .summary-stat {
  color: #86868b;
  background: #1f1f1f;
}

:global(html.dark) .quiz-section__divider {
  background: #1f1f1f;
}

:global(html.dark) .quiz-header__title {
  color: #ededed;
}

:global(html.dark) .quiz-question__text {
  color: #d4d4d8;
}

:global(html.dark) .quiz-option {
  border-color: #2a2a2a;
}

:global(html.dark) .quiz-option:hover {
  background: #1a1a1a;
}

:global(html.dark) .quiz-option--selected {
  border-color: #d4d4d8;
  background: #262626;
}

:global(html.dark) .quiz-option--correct {
  border-color: #34c759;
  background: rgba(52, 199, 89, 0.12);
}

:global(html.dark) .quiz-option--wrong {
  border-color: #ff453a;
  background: rgba(255, 69, 58, 0.12);
}

:global(html.dark) .quiz-option__text {
  color: #d4d4d8;
}

:global(html.dark) .quiz-question__explanation {
  background: #1a1a1a;
}

:global(html.dark) .quiz-explanation-text {
  color: #86868b;
}
</style>
