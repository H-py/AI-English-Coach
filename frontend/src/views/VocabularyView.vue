<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NTabs,
  NTab,
  NInput,
  NTag,
  NDropdown,
  NPopconfirm,
  NButton,
  NPagination,
  NSpin,
  NEmpty,
  useMessage
} from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import { useDebounceFn } from '@vueuse/core'
import MarkdownIt from 'markdown-it'
import { readingApi } from '@/api/reading'
import type { WordCollection, MasteryLevel } from '@/types/reading'

/**
 * 生词本页面。
 *
 * 功能：
 *  - 按掌握度筛选（全部 / 新词 / 学习中 / 熟悉 / 已掌握）
 *  - 按单词搜索（防抖 300ms）
 *  - 卡片列表展示：单词、掌握度标签、上下文、AI 解释（markdown 渲染）、学习次数与时间
 *  - 操作：下拉切换掌握度、Popconfirm 确认删除
 *  - 分页、空状态、加载状态
 *
 * 数据通过 readingApi 直接获取（非 store），本页自管理列表状态。
 */

const { t } = useI18n()
const message = useMessage()

// ============================================================
//  Markdown 渲染器
// ============================================================

/** 渲染 AI 解释：禁用原始 HTML 保证安全，开启链接识别与换行 */
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

/** 将 markdown 文本渲染为 HTML */
function renderMarkdown(content: string): string {
  if (!content) return ''
  return md.render(content)
}

// ============================================================
//  掌握度配置
// ============================================================

/** 标签页 key：'all' 或具体掌握度 */
type TabKey = 'all' | MasteryLevel

/**
 * 掌握度 -> NTag type 映射。
 * new=灰色(default) / learning=蓝色(info) / familiar=琥珀色(warning) / mastered=绿色(success)
 */
const masteryTagType: Record<MasteryLevel, 'default' | 'info' | 'warning' | 'success'> = {
  new: 'default',
  learning: 'info',
  familiar: 'warning',
  mastered: 'success'
}

/** 掌握度 -> 国际化文案（key 与类型字面量一一对应） */
function masteryLabel(level: MasteryLevel): string {
  return t(`vocabulary.${level}`)
}

/** 标记为下拉菜单选项（禁用当前掌握度，避免重复操作） */
function masteryOptions(word: WordCollection): DropdownOption[] {
  const levels: MasteryLevel[] = ['new', 'learning', 'familiar', 'mastered']
  return levels.map((level) => ({
    label: masteryLabel(level),
    key: level,
    disabled: level === word.mastery_level
  }))
}

/** 格式化 ISO 时间字符串为本地可读时间 */
function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// ============================================================
//  列表状态
// ============================================================

const activeTab = ref<TabKey>('all')
const searchQuery = ref('')
const words = ref<WordCollection[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

/** 当前筛选的掌握度（'all' 时不传该参数，后端返回全部） */
const masteryFilter = computed<MasteryLevel | undefined>(() =>
  activeTab.value === 'all' ? undefined : activeTab.value
)

// ============================================================
//  数据拉取
// ============================================================

/** 组装查询参数并拉取生词列表 */
async function fetchWords(): Promise<void> {
  loading.value = true
  try {
    const res = await readingApi.listWords({
      page: page.value,
      page_size: pageSize.value,
      mastery_level: masteryFilter.value,
      search: searchQuery.value.trim() || undefined
    })
    words.value = res.items
    total.value = res.total
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    loading.value = false
  }
}

/** 搜索防抖：输入停止 300ms 后重置到第 1 页并拉取 */
const debouncedSearch = useDebounceFn(() => {
  page.value = 1
  fetchWords()
}, 300)

watch(searchQuery, () => debouncedSearch())

/** 掌握度标签切换：重置到第 1 页并重新加载 */
watch(activeTab, () => {
  page.value = 1
  fetchWords()
})

/** 翻页 */
function handlePageChange(p: number): void {
  page.value = p
  fetchWords()
}

// ============================================================
//  操作
// ============================================================

/** 切换单词掌握度（下拉菜单选中） */
async function handleMasterySelect(word: WordCollection, key: string | number): Promise<void> {
  const level = key as MasteryLevel
  try {
    const updated = await readingApi.updateWord(word.id, { mastery_level: level })
    const idx = words.value.findIndex((w) => w.id === word.id)
    if (idx !== -1) words.value[idx] = updated
    message.success(t('vocabulary.masteryUpdated'))
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}

/** 删除单词（Popconfirm 确认后触发） */
async function handleDelete(word: WordCollection): Promise<void> {
  try {
    await readingApi.deleteWord(word.id)
    words.value = words.value.filter((w) => w.id !== word.id)
    total.value = Math.max(0, total.value - 1)
    message.success(t('vocabulary.wordDeleted'))
    // 当前页删空且非第 1 页：回退一页重新拉取，避免停留在空白页
    if (words.value.length === 0 && page.value > 1) {
      page.value -= 1
      fetchWords()
    }
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}

onMounted(fetchWords)
</script>

<template>
  <div class="space-y-6">
    <!-- 页头 -->
    <header class="space-y-2">
      <h1 class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl">
        {{ t('vocabulary.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('vocabulary.subtitle') }}
      </p>
    </header>

    <!-- 工具栏：掌握度筛选 Tabs + 搜索 -->
    <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <NTabs
        v-model:value="activeTab"
        type="line"
        animated
        class="vocab-tabs"
      >
        <NTab name="all">{{ t('vocabulary.all') }}</NTab>
        <NTab name="new">{{ t('vocabulary.new') }}</NTab>
        <NTab name="learning">{{ t('vocabulary.learning') }}</NTab>
        <NTab name="familiar">{{ t('vocabulary.familiar') }}</NTab>
        <NTab name="mastered">{{ t('vocabulary.mastered') }}</NTab>
      </NTabs>

      <div class="flex items-center gap-3">
        <span class="hidden whitespace-nowrap text-xs text-neutral-400 dark:text-neutral-500 sm:inline">
          {{ t('vocabulary.totalWords', { count: total }) }}
        </span>
        <NInput
          v-model:value="searchQuery"
          :placeholder="t('vocabulary.searchPlaceholder')"
          clearable
          class="w-full sm:w-64"
        >
          <template #prefix>
            <svg class="h-4 w-4 text-neutral-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" stroke-linecap="round" />
            </svg>
          </template>
        </NInput>
      </div>
    </div>

    <!-- 单词列表 / 空状态 -->
    <div class="min-h-[300px]">
      <NSpin :show="loading">
        <!-- 空状态 -->
        <NEmpty
          v-if="!loading && words.length === 0"
          :description="t('vocabulary.empty')"
          class="py-20"
        >
          <template #extra>
            <p class="text-sm text-neutral-400 dark:text-neutral-500">
              {{ t('vocabulary.emptyHint') }}
            </p>
          </template>
        </NEmpty>

        <!-- 卡片列表 -->
        <div v-else class="space-y-4">
          <article
            v-for="word in words"
            :key="word.id"
            class="vocab-card rounded-xl border border-neutral-200 bg-white p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-neutral-300 hover:shadow-md dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700 sm:p-6"
          >
            <!-- 顶部：单词 + 掌握度标签 -->
            <div class="flex items-start justify-between gap-4">
              <h2 class="text-xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-2xl">
                {{ word.word }}
              </h2>
              <NTag
                :type="masteryTagType[word.mastery_level]"
                size="small"
                round
                :bordered="false"
              >
                {{ masteryLabel(word.mastery_level) }}
              </NTag>
            </div>

            <!-- 上下文 -->
            <div v-if="word.context" class="mt-4">
              <span class="text-[11px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                {{ t('vocabulary.context') }}
              </span>
              <p class="mt-1 line-clamp-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">
                {{ word.context }}
              </p>
            </div>

            <!-- AI 解释 -->
            <div class="mt-4">
              <span class="text-[11px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                {{ t('vocabulary.explanation') }}
              </span>
              <!-- eslint-disable vue/no-v-html -->
              <div
                v-if="word.ai_explanation"
                class="markdown-body mt-1"
                v-html="renderMarkdown(word.ai_explanation)"
              />
              <p v-else class="mt-1 text-sm text-neutral-400 dark:text-neutral-500">
                {{ t('vocabulary.noExplanation') }}
              </p>
            </div>

            <!-- 底部：学习信息 + 操作区 -->
            <div class="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100 pt-4 dark:border-neutral-800">
              <!-- 学习次数 / 上次学习时间 -->
              <div class="flex items-center gap-2 text-xs text-neutral-400 dark:text-neutral-500">
                <span>{{ t('vocabulary.studyCount', { count: word.study_count }) }}</span>
                <span class="text-neutral-300 dark:text-neutral-600">·</span>
                <span v-if="word.last_studied_at">
                  {{ t('vocabulary.lastStudied', { time: formatDateTime(word.last_studied_at) }) }}
                </span>
                <span v-else>{{ t('vocabulary.never') }}</span>
              </div>

              <!-- 操作：标记为下拉 + 删除确认 -->
              <div class="flex items-center gap-2">
                <NDropdown
                  :options="masteryOptions(word)"
                  trigger="click"
                  placement="bottom-end"
                  @select="(key) => handleMasterySelect(word, key)"
                >
                  <NButton size="small" secondary>
                    <div class="flex items-center gap-1">
                      <span>{{ t('vocabulary.markAs') }}</span>
                      <svg class="h-3.5 w-3.5 opacity-60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </div>
                  </NButton>
                </NDropdown>

                <NPopconfirm
                  :positive-text="t('common.delete')"
                  :negative-text="t('common.cancel')"
                  @positive-click="handleDelete(word)"
                >
                  <template #trigger>
                    <NButton size="small" quaternary type="error">
                      {{ t('common.delete') }}
                    </NButton>
                  </template>
                  {{ t('vocabulary.deleteConfirm') }}
                </NPopconfirm>
              </div>
            </div>
          </article>
        </div>
      </NSpin>
    </div>

    <!-- 分页 -->
    <div
      v-if="total > pageSize"
      class="flex justify-center pt-2"
    >
      <NPagination
        :page="page"
        :page-size="pageSize"
        :item-count="total"
        show-quick-jumper
        @update:page="handlePageChange"
      />
    </div>
  </div>
</template>

<style scoped>
/* NTabs：去除默认底部多余间距，与工具栏对齐 */
.vocab-tabs {
  --n-tab-padding: 6px 14px;
}

/* ---- Markdown 渲染（AI 解释，v-html 内容需 :deep 穿透） ---- */
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: #3f3f46;
  word-break: break-word;
}

.markdown-body :deep(p) {
  margin: 0.4em 0;
}

.markdown-body :deep(p:first-child) {
  margin-top: 0;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.4em;
  margin: 0.4em 0;
}

.markdown-body :deep(li) {
  margin: 0.2em 0;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}

.markdown-body :deep(code) {
  background: #f4f4f5;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
}

.markdown-body :deep(pre) {
  background: #f4f4f5;
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
  border-left: 3px solid #d4d4d8;
  padding-left: 12px;
  margin: 0.4em 0;
  color: #71717a;
}

.markdown-body :deep(a) {
  color: #2563eb;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  font-weight: 600;
  margin: 0.6em 0 0.3em;
  line-height: 1.3;
}

.markdown-body :deep(h1) { font-size: 1.2em; }
.markdown-body :deep(h2) { font-size: 1.1em; }
.markdown-body :deep(h3) { font-size: 1em; }

.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.5em 0;
  width: 100%;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e4e4e7;
  padding: 6px 10px;
  text-align: left;
}

/* ============================================================
   暗色模式
   ============================================================ */
:global(html.dark) .markdown-body {
  color: #d4d4d8;
}

:global(html.dark) .markdown-body :deep(code) {
  background: #27272a;
}

:global(html.dark) .markdown-body :deep(pre) {
  background: #18181b;
}

:global(html.dark) .markdown-body :deep(blockquote) {
  border-color: #3f3f46;
  color: #a1a1aa;
}

:global(html.dark) .markdown-body :deep(a) {
  color: #60a5fa;
}

:global(html.dark) .markdown-body :deep(th),
:global(html.dark) .markdown-body :deep(td) {
  border-color: #3f3f46;
}
</style>
