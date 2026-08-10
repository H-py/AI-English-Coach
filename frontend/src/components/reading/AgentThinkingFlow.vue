<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSpin, NTag } from 'naive-ui'
import MarkdownIt from 'markdown-it'
import type { ThinkingStep } from '@/types/agent'

/**
 * Agent 思考流程展示组件。
 *
 * 将 Agent 的思考步骤（thinking / tool_call / tool_result）
 * 以垂直时间流的形式展示，不同类型步骤有不同的视觉样式：
 *  - thinking：灰色背景，思考内容文本
 *  - tool_call：蓝色背景，工具名 + 参数标签
 *  - tool_result：绿色背景，工具结果（markdown 渲染）
 *
 * 当 streaming 为 true 且尚无步骤时，显示加载动画。
 */

const props = defineProps<{
  /** 思考步骤列表 */
  steps: ThinkingStep[]
  /** 是否正在流式输出 */
  streaming: boolean
}>()

const { t } = useI18n()

// ---- 本地 markdown 实例（仅用于 tool_result 内容渲染） ----
const md = new MarkdownIt({
  html: false,
  linkify: true
})

/** 将 markdown 文本渲染为 HTML */
function renderMarkdown(content: string): string {
  if (!content) return ''
  return md.render(content)
}

// ---- 工具名中文映射 ----

const toolNameMap: Record<string, string> = {
  search_vocabulary: '搜索生词本',
  get_word_detail: '查询单词详情',
  get_reading_history: '获取阅读历史',
  get_article_content: '获取文章内容',
  get_sentence_collection: '获取收藏句子',
  get_user_profile: '获取用户画像',
  get_learning_stats: '获取学习统计',
  search_memories: '搜索相关记忆'
}

/** 获取工具的中文展示名 */
function toolDisplayName(toolName?: string): string {
  if (!toolName) return ''
  return toolNameMap[toolName] || toolName
}

// ---- 工具参数处理 ----

/** 将参数对象转为 [key, value] 数组，用于展示为标签 */
const argumentEntries = (args?: Record<string, unknown>): Array<[string, string]> => {
  if (!args) return []
  return Object.entries(args).map(([key, value]) => [
    key,
    typeof value === 'string' ? value : JSON.stringify(value)
  ])
}

// ---- 是否显示加载状态 ----

const showLoading = computed(() => props.streaming && props.steps.length === 0)
</script>

<template>
  <div class="agent-flow">
    <!-- 加载状态：正在思考但尚无步骤 -->
    <div v-if="showLoading" class="agent-flow__loading">
      <NSpin size="small" />
      <span class="agent-flow__loading-text">{{ t('agent.thinkingLabel') }}</span>
    </div>

    <!-- 步骤列表 -->
    <template v-for="step in steps" :key="step.id">
      <!-- ===== thinking 步骤 ===== -->
      <div
        v-if="step.type === 'thinking'"
        class="flow-step flow-step--thinking"
      >
        <div class="flow-step__header">
          <span class="flow-step__icon">💭</span>
          <span class="flow-step__label">{{ t('agent.thinking') }}</span>
        </div>
        <div class="flow-step__content flow-step__content--text">
          {{ step.content }}
        </div>
      </div>

      <!-- ===== tool_call 步骤 ===== -->
      <div
        v-else-if="step.type === 'tool_call'"
        class="flow-step flow-step--tool-call"
      >
        <div class="flow-step__header">
          <span class="flow-step__icon">🔧</span>
          <span class="flow-step__label">
            {{ t('agent.callingTool') }}: {{ toolDisplayName(step.toolName) }}
          </span>
        </div>
        <div
          v-if="argumentEntries(step.toolArguments).length > 0"
          class="flow-step__content flow-step__content--tags"
        >
          <NTag
            v-for="[key, value] in argumentEntries(step.toolArguments)"
            :key="key"
            size="small"
            :bordered="false"
            type="info"
          >
            {{ key }}: {{ value }}
          </NTag>
        </div>
      </div>

      <!-- ===== tool_result 步骤 ===== -->
      <div
        v-else-if="step.type === 'tool_result'"
        class="flow-step flow-step--tool-result"
      >
        <div class="flow-step__header">
          <span class="flow-step__icon">📊</span>
          <span class="flow-step__label">
            {{ t('agent.toolResult') }}: {{ toolDisplayName(step.toolName) }}
          </span>
        </div>
        <!-- eslint-disable vue/no-v-html -->
        <div
          class="flow-step__content markdown-body"
          v-html="renderMarkdown(step.content)"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ---- 容器 ---- */
.agent-flow {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ---- 加载状态 ---- */
.agent-flow__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
}

.agent-flow__loading-text {
  font-size: 13px;
  color: #86868b;
}

/* ---- 通用步骤卡片 ---- */
.flow-step {
  padding: 10px 12px;
  border-radius: 8px;
  border-left: 3px solid transparent;
}

.flow-step__header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.flow-step__icon {
  font-size: 14px;
  line-height: 1;
}

.flow-step__label {
  font-size: 12px;
  font-weight: 600;
  color: #86868b;
}

.flow-step__content {
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.flow-step__content--text {
  color: #86868b;
}

.flow-step__content--tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* ---- thinking 步骤：灰色 ---- */
.flow-step--thinking {
  background: #f5f5f5;
  border-left-color: #d1d1d6;
}

/* ---- tool_call 步骤：蓝色 ---- */
.flow-step--tool-call {
  background: rgba(0, 122, 255, 0.06);
  border-left-color: #007aff;
}

/* ---- tool_result 步骤：绿色 ---- */
.flow-step--tool-result {
  background: rgba(52, 199, 89, 0.06);
  border-left-color: #34c759;
}

/* ---- tool_result markdown 样式 ---- */
.flow-step__content.markdown-body {
  font-size: 13px;
  color: #1d1d1f;
}

.flow-step__content.markdown-body :deep(p) {
  margin: 0.3em 0;
}

.flow-step__content.markdown-body :deep(ul),
.flow-step__content.markdown-body :deep(ol) {
  padding-left: 1.4em;
  margin: 0.3em 0;
}

.flow-step__content.markdown-body :deep(code) {
  background: #e8e8ed;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 0.88em;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
}

.flow-step__content.markdown-body :deep(pre) {
  background: #e8e8ed;
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.3em 0;
}

.flow-step__content.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

/* ============================================================
   暗色模式
   ============================================================ */
:global(html.dark) .agent-flow__loading-text {
  color: #86868b;
}

:global(html.dark) .flow-step__label {
  color: #86868b;
}

:global(html.dark) .flow-step__content--text {
  color: #86868b;
}

/* thinking 暗色 */
:global(html.dark) .flow-step--thinking {
  background: #1f1f1f;
  border-left-color: #3a3a3c;
}

/* tool_call 暗色 */
:global(html.dark) .flow-step--tool-call {
  background: rgba(10, 132, 255, 0.12);
  border-left-color: #0a84ff;
}

/* tool_result 暗色 */
:global(html.dark) .flow-step--tool-result {
  background: rgba(48, 209, 88, 0.12);
  border-left-color: #30d158;
}

:global(html.dark) .flow-step__content.markdown-body {
  color: #d4d4d8;
}

:global(html.dark) .flow-step__content.markdown-body :deep(code) {
  background: #2a2a2a;
}

:global(html.dark) .flow-step__content.markdown-body :deep(pre) {
  background: #1a1a1a;
}
</style>
