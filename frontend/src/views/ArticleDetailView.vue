<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NTag, NSpin, NEmpty } from 'naive-ui'
import { useArticle } from '@/composables/useArticle'
import { useReading } from '@/composables/useReading'
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
const { store, loading, loadArticleDetail, difficultyLabel, difficultyColor } = useArticle()
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

// 难度配色
const difficultyStyle = computed(() => {
  if (!article.value) return { color: '', textColor: '', borderColor: '' }
  return difficultyColor(article.value.difficulty)
})

// ============================================================
//  文本选区
// ============================================================

/** 用户选中的文本 */
const selectedText = ref('')
/** 选中文本所在的完整句子（作为 AI 上下文） */
const selectedContext = ref('')
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
    return
  }

  selectedText.value = text
  // 提取选中文本所在的完整句子作为上下文
  if (article.value) {
    selectedContext.value = extractSentence(article.value.content, text)
  }
}

// ============================================================
//  阅读历史
// ============================================================

/** 当前阅读会话的 historyId */
const historyId = ref<number | null>(null)
/** 阅读开始时间戳（毫秒） */
const startTime = ref<number>(0)

// ============================================================
//  生命周期
// ============================================================

onMounted(async () => {
  const id = Number(route.params.id)
  if (Number.isNaN(id)) return

  // 加载文章详情
  await loadArticleDetail(id)

  // 文章加载成功后开始阅读会话
  if (article.value) {
    startTime.value = Date.now()
    try {
      historyId.value = await startReadingSession(id)
    } catch {
      // 阅读历史记录失败不影响阅读体验
    }
  }
})

onUnmounted(async () => {
  // 上报阅读时长（best-effort，不阻塞卸载）
  if (historyId.value !== null && startTime.value > 0) {
    const duration = Math.floor((Date.now() - startTime.value) / 1000)
    try {
      await endReadingSession(historyId.value, duration)
    } catch {
      // 忽略上报失败
    }
  }

  // 清空当前文章详情，避免返回列表时残留
  store.clearCurrent()
})
</script>

<template>
  <div class="flex h-[calc(100vh-7.5rem)] flex-col gap-6">
    <!-- 返回按钮 -->
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

            <!-- 元信息：难度 / 来源 / 词数 / 阅读时间 -->
            <div class="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-neutral-500 dark:text-neutral-400">
              <NTag
                size="small"
                round
                :bordered="true"
                :color="difficultyStyle"
              >
                {{ difficultyLabel(article.difficulty) }}
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

            <!-- 正文内容区：支持文本选择 -->
            <!--
              article.content 是纯文本，用 v-text 渲染在 div 里（安全），
              配合 white-space: pre-wrap 保留换行。
              mouseup 时检测选区并提取上下文句子。
            -->
            <div
              ref="contentRef"
              class="article-content prose-comfortable"
              v-text="article.content"
              @mouseup="handleSelection"
            />
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
  white-space: pre-wrap;
  word-break: break-word;
  cursor: text;
  text-align: justify;
  text-justify: inter-word;
}

.article-content :deep(p) {
  margin-bottom: 1.4em;
}

:global(html.dark) .article-content {
  color: #d4d4d8;
}
</style>
