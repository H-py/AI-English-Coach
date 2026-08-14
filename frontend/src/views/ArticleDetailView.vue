<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NTag, NSpin, NEmpty } from 'naive-ui'
import StarRating from '@/components/StarRating.vue'
import { articleApi } from '@/api/article'
import type { ArticleNeighbors } from '@/types/article'
import { useArticle } from '@/composables/useArticle'
import { useReading } from '@/composables/useReading'
import { useArticleSpeech } from '@/composables/useArticleSpeech'
import AiPanel from '@/components/reading/AiPanel.vue'

/**
 * 文章详情 / 交互式阅读页（Phase 3）。
 *
 * 布局：双栏 —— 左侧文章阅读区 + 右侧 AI 助手面板。
 *
 * 左侧（文章区）：
 *  - 标题、元信息、标签（保持 Phase 2 样式）
 *  - 正文内容区：用户可以选中文本
 *  - 监听 mouseup，获取 window.getSelection() 选中文本
 *  - 提取选中文本所在的句子作为 context，传给右侧 AiPanel
 *
 * 右侧（AI 面板）：
 *  - 固定宽度，不随页面滚动（文章列独立 overflow-y-auto 滚动）
 *  - 嵌入 AiPanel 组件，接收 selectedText / selectedContext props
 *
 * 阅读历史：
 *  - onMounted：startReadingSession 记录开始时间
 *  - onUnmounted：计算 duration，endReadingSession 上报
 */

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { store, loading, loadArticleDetail, cetLabel } = useArticle()
const { startReadingSession, endReadingSession } = useReading()

/** 返回上一页，若无历史则回文章库 */
function goBack(): void {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/articles')
  }
}

const article = computed(() => store.currentArticle)

// ============================================================
//  文章朗读（逐句朗读 + 高亮 + 完整控制）
// ============================================================

const {
  isPlaying: readingPlaying,
  isPaused: readingPaused,
  currentRange: readingRange,
  currentBlockIndex: readingBlock,
  totalBlocks: readingTotal,
  rate: readingRate,
  rateOptions,
  splitContent,
  start: startReading,
  pause: pauseReading,
  resume: resumeReading,
  seekTo: seekReading,
  stop: stopReading,
  setRate: setReadingRate
} = useArticleSpeech()

/** 判断句子是否处于当前朗读块内（用于高亮） */
function isSentenceReading(index: number): boolean {
  return (
    readingPlaying.value &&
    readingRange.value !== null &&
    index >= readingRange.value.from &&
    index <= readingRange.value.to
  )
}

/** 朗读进度条滑块值（1-based 块号，仅用于显示，拖拽中不打断朗读） */
const readingSlider = ref(1)

/** 朗读块推进时同步进度条 */
watch(readingBlock, (v) => {
  readingSlider.value = v + 1
})

/** 进度条拖拽中：只更新显示值，不打断当前朗读 */
function handleSliderInput(e: Event): void {
  const target = e.target as HTMLInputElement
  readingSlider.value = Number(target.value)
}

/** 进度条松开：跳转到对应块朗读 */
function handleSliderChange(): void {
  seekReading(readingSlider.value - 1)
}

/** 进度条填充样式（已读部分着色） */
function sliderFillStyle(): Record<string, string> {
  const max = readingTotal.value
  if (max <= 1) return {}
  const pct = ((readingSlider.value - 1) / (max - 1)) * 100
  return {
    background: `linear-gradient(to right, #4b3fe3 ${pct}%, var(--progress-track, #e4e4e7) ${pct}%)`
  }
}

/** 文章正文按段落 + 句子拆分（供逐句渲染与朗读高亮） */
const contentLines = computed(() => splitContent(article.value?.content ?? ''))

// ============================================================
//  文本选区
// ============================================================

/** 用户选中的文本 */
const selectedText = ref('')
/** 选中文本所在的完整句子（作为 AI 上下文） */
const selectedContext = ref('')
/** 选中内容是否为单词的一部分（截断选择，如选了单词的前半截） */
const selectionPartial = ref(false)
/** 正文内容区 DOM 引用（用于判断选区是否在正文内） */
const contentRef = ref<HTMLElement | null>(null)

/**
 * 从文章正文中提取包含选中文本的句子。
 * 按句号 / 感叹号 / 问号 / 换行作为句子边界，
 * 向前向后扫描，截取完整的句子。
 */
function extractSentence(content: string, selection: string): string {
  const idx = content.indexOf(selection)
  if (idx === -1) return selection

  // 向前扫描句子起点
  let start = 0
  for (let i = idx - 1; i >= 0; i--) {
    const ch = content[i]
    if (ch === '\n') {
      start = i + 1
      break
    }
    // 句末标点 + 空白 = 句子边界
    if (
      (ch === '.' || ch === '!' || ch === '?') &&
      i + 1 < content.length &&
      /\s/.test(content[i + 1])
    ) {
      start = i + 2
      break
    }
  }

  // 向后扫描句子终点
  const selEnd = idx + selection.length
  let end = content.length
  for (let i = selEnd; i < content.length; i++) {
    const ch = content[i]
    if (ch === '\n') {
      end = i
      break
    }
    if (
      (ch === '.' || ch === '!' || ch === '?') &&
      (i + 1 >= content.length || /\s/.test(content[i + 1]))
    ) {
      end = i + 1
      break
    }
  }

  return content.slice(start, end).trim()
}

/** 单词字符集：字母、数字、连字符、撇号 */
const WORD_CHAR = /[A-Za-z0-9'-]/

/** 获取选区起点前一个可见字符 */
function charBeforeSelection(range: Range): string {
  const container = range.startContainer
  const offset = range.startOffset

  if (container.nodeType === Node.TEXT_NODE) {
    const text = container.textContent || ''
    if (offset > 0) return text[offset - 1]
    // offset 为 0：向前找兄弟节点
    let node = container.previousSibling
    while (node) {
      const t = node.textContent || ''
      if (t) return t[t.length - 1]
      node = node.previousSibling
    }
    return ''
  }

  // 元素节点：offset 为子节点索引
  if (offset > 0) {
    const t = container.childNodes[offset - 1]?.textContent || ''
    return t ? t[t.length - 1] : ''
  }
  return ''
}

/** 获取选区终点后一个可见字符 */
function charAfterSelection(range: Range): string {
  const container = range.endContainer
  const offset = range.endOffset

  if (container.nodeType === Node.TEXT_NODE) {
    const text = container.textContent || ''
    if (offset < text.length) return text[offset]
    // offset 已到末尾：向后找兄弟节点
    let node = container.nextSibling
    while (node) {
      const t = node.textContent || ''
      if (t) return t[0]
      node = node.nextSibling
    }
    return ''
  }

  // 元素节点：offset 为子节点索引
  if (offset < container.childNodes.length) {
    return container.childNodes[offset]?.textContent?.[0] || ''
  }
  return ''
}

/**
 * 判断选区是否截断了单词（只选中了单词的一部分）。
 *
 * 规则：选中文本是单个字母串（不含空格）且选区边界紧邻单词字符
 * （起点前或终点后仍是字母/数字/连字符），说明选中内容只是完整单词
 * 的一部分。多词选择（短语/句子）不视为截断。
 *
 * 注意：双击或拖拽时选区首尾可能包含多余空白（如 " executive"），
 * 判断前先跳过首尾空白，避免把前导/尾随空格误判为单词截断。
 */
function isPartialWordSelection(range: Range, text: string): boolean {
  // 多词选择（含空格）是合法的短语选择，不拦截
  if (/\s/.test(text)) return false
  // 非字母开头的选择（数字、标点）不拦截
  if (!/^[A-Za-z]/.test(text)) return false

  // 选区首尾多余空白的数量
  const raw = range.toString()
  const leadingWs = (raw.match(/^\s*/)?.[0] ?? '').length
  const trailingWs = (raw.match(/\s*$/)?.[0] ?? '').length

  // 跳过前导空白后，检查有效起点前一个字符
  let before = ''
  const sc = range.startContainer
  if (sc.nodeType === Node.TEXT_NODE) {
    const t = sc.textContent || ''
    const pos = range.startOffset + leadingWs
    if (pos > 0 && pos <= t.length) before = t[pos - 1]
  } else if (range.startOffset + leadingWs > 0) {
    before = charBeforeSelection(range)
  }

  // 跳过尾部空白后，检查有效终点后一个字符
  let after = ''
  const ec = range.endContainer
  if (ec.nodeType === Node.TEXT_NODE) {
    const t = ec.textContent || ''
    const pos = range.endOffset - trailingWs
    if (pos >= 0 && pos < t.length) after = t[pos]
  } else if (range.endOffset - trailingWs < ec.childNodes.length) {
    after = charAfterSelection(range)
  }

  return (
    (before.length > 0 && WORD_CHAR.test(before)) ||
    (after.length > 0 && WORD_CHAR.test(after))
  )
}

/**
 * mouseup 事件处理：检测正文本本选区。
 * 仅当选区位于正文内容区内时才更新 selectedText。
 */
function handleSelection(): void {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return

  // 确认选区在正文内容区内
  const range = selection.getRangeAt(0)
  if (!contentRef.value || !contentRef.value.contains(range.commonAncestorContainer)) {
    return
  }

  const text = selection.toString().trim()
  if (!text || text.length < 1) {
    // 选区为空：清除
    selectedText.value = ''
    selectedContext.value = ''
    selectionPartial.value = false
    return
  }

  // 检测是否为单词的部分截断选择
  selectionPartial.value = isPartialWordSelection(range, text)

  selectedText.value = text
  // 提取选中文本所在的完整句子作为上下文
  if (article.value) {
    selectedContext.value = extractSentence(article.value.content, text)
  }
}

// ---- selectionchange：跨平台选区检测（移动端主力方案） ----

/** selectionchange 防抖计时器 */
let selectionTimer: ReturnType<typeof setTimeout> | null = null

/**
 * document 级 selectionchange 事件处理。
 *
 * 移动端用户拖拽选区手柄时，touchend 不会在内容区 div 上触发，
 * 但 selectionchange 会在文档级持续触发。使用 300ms 防抖等待选区
 * 稳定后再检测，避免拖拽过程中频繁触发。空选区立即清除，不等待。
 *
 * 桌面端仍由 @mouseup 提供即时响应，此处作为兜底。
 */
function handleSelectionChange(): void {
  const selection = window.getSelection()
  const text = selection?.toString().trim() ?? ''

  // 空选区：立即清除，不等待防抖
  if (!text) {
    if (selectionTimer) {
      clearTimeout(selectionTimer)
      selectionTimer = null
    }
    selectedText.value = ''
    selectedContext.value = ''
    selectionPartial.value = false
    return
  }

  // 非空选区：防抖等待选区稳定后交给 handleSelection 检测
  if (selectionTimer) clearTimeout(selectionTimer)
  selectionTimer = setTimeout(() => {
    handleSelection()
    selectionTimer = null
  }, 300)
}

// ============================================================
//  阅读历史
// ============================================================

/** 当前阅读会话的 historyId */
const historyId = ref<number | null>(null)
/** 阅读开始时间戳（毫秒） */
const startTime = ref<number>(0)

// ============================================================
//  上一篇 / 下一篇（循环导航）
// ============================================================

/** 相邻文章：prev / next 各为 { id, title } 或 null */
const neighbors = ref<ArticleNeighbors>({ prev: null, next: null })

/** 结束当前阅读会话并上报时长（best-effort） */
async function endCurrentSession(): Promise<void> {
  if (historyId.value !== null && startTime.value > 0) {
    const duration = Math.floor((Date.now() - startTime.value) / 1000)
    try {
      await endReadingSession(historyId.value, duration)
    } catch {
      // 忽略上报失败
    }
    historyId.value = null
    startTime.value = 0
  }
}

/**
 * 加载文章详情与相邻文章，并开始新的阅读会话。
 * 在切换文章（上一篇/下一篇）时同样调用，保证状态完整重置。
 */
async function loadArticle(id: number): Promise<void> {
  // 切换文章前先结束上一个阅读会话
  await endCurrentSession()

  // 停止上一篇文章的朗读
  stopReading()

  // 清空上一篇文章的选区状态与已加载内容
  selectedText.value = ''
  selectedContext.value = ''
  selectionPartial.value = false
  store.clearCurrent()

  // 并行加载详情与相邻文章
  await loadArticleDetail(id)
  try {
    neighbors.value = await articleApi.getNeighbors(id)
  } catch {
    neighbors.value = { prev: null, next: null }
  }

  // 文章加载成功后开始阅读会话
  if (article.value) {
    startTime.value = Date.now()
    try {
      historyId.value = await startReadingSession(id)
    } catch {
      // 阅读历史记录失败不影响阅读体验
    }
  }
}

/** 跳转到相邻文章（循环导航：首尾相接） */
function goToArticle(id: number): void {
  router.push(`/articles/${id}`)
}

// ============================================================
//  生命周期
// ============================================================

/**
 * 监听路由参数变化。
 * 上一篇/下一篇跳转时 Vue Router 复用同一组件实例（onMounted 不会
 * 重新触发），因此需要手动重新加载新文章并重置状态。
 */
watch(
  () => route.params.id,
  (newId) => {
    const id = Number(newId)
    if (Number.isNaN(id)) return
    loadArticle(id)
  }
)

onMounted(async () => {
  // 注册文档级选区变化监听（移动端选区检测主力方案）
  document.addEventListener('selectionchange', handleSelectionChange)

  const id = Number(route.params.id)
  if (Number.isNaN(id)) return

  await loadArticle(id)
})

onUnmounted(async () => {
  // 停止文章朗读
  stopReading()

  // 移除选区变化监听
  document.removeEventListener('selectionchange', handleSelectionChange)
  if (selectionTimer) clearTimeout(selectionTimer)

  // 上报阅读时长（best-effort，不阻塞卸载）
  await endCurrentSession()

  // 清空当前文章详情，避免返回列表时残留
  store.clearCurrent()
})
</script>

<template>
  <div class="flex h-[calc(100vh-7.5rem)] flex-col gap-6">
    <!-- 顶部操作栏：返回 + 上一篇 / 下一篇 -->
    <div class="flex items-center justify-between gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-neutral-500 transition-colors hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
        @click="goBack"
      >
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M19 12H5M12 19l-7-7 7-7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        {{ t('article.back') }}
      </button>

      <!-- 上一篇 / 下一篇（循环导航） -->
      <div v-if="article" class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-lg border border-neutral-200 px-2.5 py-1.5 text-xs text-neutral-600 transition-colors hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-neutral-600 dark:hover:bg-neutral-800"
          :title="neighbors.prev?.title"
          :disabled="!neighbors.prev"
          @click="neighbors.prev && goToArticle(neighbors.prev.id)"
        >
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          {{ t('article.prev') }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-lg border border-neutral-200 px-2.5 py-1.5 text-xs text-neutral-600 transition-colors hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-neutral-600 dark:hover:bg-neutral-800"
          :title="neighbors.next?.title"
          :disabled="!neighbors.next"
          @click="neighbors.next && goToArticle(neighbors.next.id)"
        >
          {{ t('article.next') }}
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14M12 5l7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 加载失败 / 无数据 -->
    <div v-if="!loading && !article" class="flex flex-1 items-center justify-center">
      <NEmpty :description="t('article.empty')" />
    </div>

    <!-- 双栏布局：左文章 + 右 AI 面板 -->
    <!--
      整体高度固定为 calc(100vh - 7.5rem)（顶栏 4rem + 内容区 py-8 共 3.5rem），
      使 <main> 不产生页面级滚动。左侧文章列 overflow-y-auto 独立滚动，
      右侧 AI 面板作为 flex item 拉伸填满高度，永不随滚动移动。
    -->
    <div v-else-if="article || loading" class="flex min-h-0 flex-1 gap-8">
      <!-- ======================== 左侧：文章阅读区（独立滚动） ======================== -->
      <article class="min-w-0 flex-1 overflow-y-auto pr-2">
        <NSpin :show="loading">
          <div v-if="loading && !article" class="py-20" />
          <div v-if="article">
            <!-- 标题 -->
            <h1 class="mb-4 text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-4xl">
              {{ article.title }}
            </h1>

            <!-- 朗读工具栏：播放 / 暂停 / 停止 / 语速 -->
            <div class="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-2.5 dark:border-neutral-800 dark:bg-neutral-900">
              <template v-if="!readingPlaying">
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white"
                  @click="startReading(article.content)"
                >
                  <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                  {{ t('article.listen') }}
                </button>
              </template>
              <template v-else>
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-lg bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white"
                  @click="readingPaused ? resumeReading() : pauseReading()"
                >
                  <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                    <path v-if="readingPaused" d="M8 5v14l11-7z" />
                    <path v-else d="M6 5h4v14H6zM14 5h4v14h-4z" />
                  </svg>
                  {{ readingPaused ? t('article.resume') : t('article.pause') }}
                </button>
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-lg border border-neutral-200 px-3 py-1.5 text-xs text-neutral-600 transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                  @click="stopReading"
                >
                  <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M6 6h12v12H6z" />
                  </svg>
                  {{ t('article.stop') }}
                </button>
              </template>

              <!-- 语速调节 -->
              <div class="ml-auto flex items-center gap-1">
                <span class="mr-1 text-xs text-neutral-400 dark:text-neutral-500">{{ t('article.speed') }}</span>
                <button
                  v-for="r in rateOptions"
                  :key="r"
                  type="button"
                  class="rounded-md px-2 py-1 text-xs font-medium transition-colors"
                  :class="readingRate === r
                    ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900'
                    : 'text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800'"
                  @click="setReadingRate(r)"
                >
                  {{ r }}x
                </button>
              </div>

              <!-- 朗读进度条（拖拽跳转到对应位置） -->
              <div
                v-if="readingPlaying && readingTotal > 0"
                class="flex w-full items-center gap-3"
              >
                <input
                  type="range"
                  class="reading-progress"
                  min="1"
                  :max="readingTotal"
                  :value="readingSlider"
                  :style="sliderFillStyle()"
                  :aria-label="t('article.progress')"
                  @input="handleSliderInput"
                  @change="handleSliderChange"
                />
                <span class="shrink-0 text-xs tabular-nums text-neutral-400 dark:text-neutral-500">
                  {{ readingSlider }} / {{ readingTotal }}
                </span>
              </div>
            </div>

            <!-- 元信息：难度星级 / 四六级 / 来源 / 词数 / 阅读时间 -->
            <div class="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-neutral-500 dark:text-neutral-400">
              <StarRating :stars="Number(article.difficulty)" />

              <NTag
                v-if="article.cet_type"
                size="small"
                :bordered="false"
                type="warning"
              >
                {{ cetLabel(article.cet_type) }}
              </NTag>

              <span v-if="article.source">
                {{ t('article.source') }}：{{ article.source }}
              </span>
              <span>{{ article.word_count }} {{ t('article.wordCount') }}</span>
              <span v-if="article.reading_time">
                {{ article.reading_time }} {{ t('article.readingTime') }}
              </span>
            </div>

            <!-- 标签 -->
            <div v-if="article.tags.length" class="mb-8 flex flex-wrap gap-2">
              <NTag
                v-for="tag in article.tags"
                :key="tag"
                size="small"
                :bordered="false"
                type="default"
                class="!text-neutral-500 dark:!text-neutral-400"
              >
                {{ tag }}
              </NTag>
            </div>

            <!-- 正文内容区：支持文本选择 + 逐句渲染（朗读高亮） -->
            <!--
              article.content 是纯文本，按段落/句子拆分渲染为 span（安全），
              当前朗读句加高亮 class。mouseup 时检测选区并提取上下文句子。
            -->
            <div
              ref="contentRef"
              class="article-content prose-comfortable"
              @mouseup="handleSelection"
            >
              <p
                v-for="(line, li) in contentLines"
                :key="li"
                class="article-line"
              >
                <span
                  v-for="sentence in line"
                  :key="sentence.globalIndex"
                  class="article-sentence"
                  :class="{ 'article-sentence--active': isSentenceReading(sentence.globalIndex) }"
                >{{ sentence.text }} </span>
              </p>
            </div>

            <!-- 底部导航：上一篇 / 下一篇（循环） -->
            <nav
              v-if="neighbors.prev || neighbors.next"
              class="mt-10 border-t border-neutral-100 pt-6 dark:border-neutral-800"
            >
              <div class="grid gap-3 sm:grid-cols-2">
                <button
                  v-if="neighbors.prev"
                  type="button"
                  class="group rounded-xl border border-neutral-200 p-4 text-left transition-all hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-800 dark:hover:border-neutral-700 dark:hover:bg-neutral-900"
                  @click="goToArticle(neighbors.prev.id)"
                >
                  <span class="flex items-center gap-1 text-xs text-neutral-400 transition-colors group-hover:text-neutral-600 dark:text-neutral-500 dark:group-hover:text-neutral-300">
                    <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M19 12H5M12 19l-7-7 7-7" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    {{ t('article.prevArticle') }}
                  </span>
                  <span class="mt-1.5 line-clamp-2 block text-sm font-medium text-neutral-800 transition-colors group-hover:text-neutral-900 dark:text-neutral-200 dark:group-hover:text-neutral-100">
                    {{ neighbors.prev.title }}
                  </span>
                </button>

                <button
                  v-if="neighbors.next"
                  type="button"
                  class="group rounded-xl border border-neutral-200 p-4 text-right transition-all hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-800 dark:hover:border-neutral-700 dark:hover:bg-neutral-900"
                  @click="goToArticle(neighbors.next.id)"
                >
                  <span class="flex items-center justify-end gap-1 text-xs text-neutral-400 transition-colors group-hover:text-neutral-600 dark:text-neutral-500 dark:group-hover:text-neutral-300">
                    {{ t('article.nextArticle') }}
                    <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M5 12h14M12 5l7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                  </span>
                  <span class="mt-1.5 line-clamp-2 block text-sm font-medium text-neutral-800 transition-colors group-hover:text-neutral-900 dark:text-neutral-200 dark:group-hover:text-neutral-100">
                    {{ neighbors.next.title }}
                  </span>
                </button>
              </div>
            </nav>
          </div>
        </NSpin>
      </article>

      <!-- ======================== 右侧：AI 助手面板（固定不滚动） ======================== -->
      <!--
        aside 作为 flex item 拉伸到与文章列等高（align-items: stretch），
        内部 AiPanel height:100% 填满 aside，自带 overflow-y-auto 处理内容溢出。
        不需要 sticky / fixed —— 因为文章列独立滚动，aside 根本不参与滚动。
      -->
      <aside v-if="article" class="hidden w-[420px] shrink-0 overflow-hidden lg:block">
        <AiPanel
          :article-id="article.id"
          :history-id="historyId"
          :selected-text="selectedText"
          :selected-context="selectedContext"
          :selected-partial="selectionPartial"
        />
      </aside>
    </div>
  </div>
</template>

<style scoped>
/* 正文 prose 风格：阅读优先，不依赖 typography 插件 */
.article-content {
  font-size: 18px;
  line-height: 1.8;
  color: #1d1d1f;
  word-break: break-word;
  cursor: text;
  text-align: justify;
  text-justify: inter-word;
}

.article-content :deep(p) {
  margin-bottom: 1.4em;
}

/* 正文句子（朗读高亮单元） */
.article-sentence {
  border-radius: 2px;
  transition: background-color 0.3s ease;
}

/* 当前朗读句高亮 */
.article-sentence--active {
  background: #fef08a;
}

:global(html.dark) .article-content {
  color: #d4d4d8;
}

:global(html.dark) .article-sentence--active {
  background: #713f12;
}

/* ---- 朗读进度条 ---- */
.reading-progress {
  flex: 1;
  height: 4px;
  -webkit-appearance: none;
  appearance: none;
  border-radius: 999px;
  --progress-track: #e4e4e7;
  outline: none;
  cursor: pointer;
}

.reading-progress::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #3f3f46;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.25);
  transition: transform 0.15s ease;
}

.reading-progress::-webkit-slider-thumb:hover {
  transform: scale(1.15);
}

.reading-progress::-moz-range-thumb {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #3f3f46;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.25);
}

:global(html.dark) .reading-progress {
  --progress-track: #3f3f46;
}

:global(html.dark) .reading-progress::-webkit-slider-thumb {
  background: #e4e4e7;
  border-color: #27272a;
}

:global(html.dark) .reading-progress::-moz-range-thumb {
  background: #e4e4e7;
  border-color: #27272a;
}
</style>
