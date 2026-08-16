<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NTabs,
  NTab,
  NInput,
  NInputNumber,
  NSelect,
  NTag,
  NModal,
  NButton,
  NPopconfirm,
  NPagination,
  NSpin,
  NEmpty,
  useMessage
} from 'naive-ui'
import { useDebounceFn } from '@vueuse/core'
import MarkdownIt from 'markdown-it'
import { readingApi } from '@/api/reading'
import SpeakerButton from '@/components/SpeakerButton.vue'
import type { WordCollection, MasteryLevel } from '@/types/reading'

/**
 * 生词本页面。
 *
 * 功能：
 *  - 按掌握度筛选（全部 / 新词 / 学习中 / 熟悉 / 已掌握）
 *  - 按单词搜索（防抖 300ms）
 *  - 响应式网格卡片：单词 + 音标 + 主要意思（简略展示）
 *  - 卡片底部四枚快速标记按钮（新词/学习中/熟悉/掌握），点击即切换
 *  - 点击卡片打开居中弹窗，展示完整信息（AI 解释全文、上下文、学习统计）
 *  - 弹窗内可切换掌握度、删除单词
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

/** 全部掌握度（用于快速标记按钮遍历） */
const masteryLevels: MasteryLevel[] = ['new', 'learning', 'familiar', 'mastered']

/** 掌握度 -> NTag type 映射（标签展示） */
const masteryTagType: Record<MasteryLevel, 'default' | 'info' | 'warning' | 'success'> = {
  new: 'default',
  learning: 'info',
  familiar: 'warning',
  mastered: 'success'
}

/** 掌握度 -> 国际化文案 */
function masteryLabel(level: MasteryLevel): string {
  return t(`vocabulary.${level}`)
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
const pageSize = ref(20)

/** 详情弹窗状态 */
const showDetail = ref(false)
const activeWord = ref<WordCollection | null>(null)

/** 正在执行掌握度切换的单词 id（防止重复点击） */
const updatingId = ref<number | null>(null)

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

/**
 * 切换单词掌握度（卡片快速标记按钮 / 详情弹窗共用）。
 * 点击当前已选中的掌握度时忽略，避免无意义请求。
 */
async function handleMasteryChange(word: WordCollection, level: MasteryLevel): Promise<void> {
  if (word.mastery_level === level || updatingId.value === word.id) return
  updatingId.value = word.id
  try {
    const updated = await readingApi.updateWord(word.id, { mastery_level: level })
    const idx = words.value.findIndex((w) => w.id === word.id)
    if (idx !== -1) words.value[idx] = updated
    if (activeWord.value?.id === word.id) activeWord.value = updated
    message.success(t('vocabulary.masteryUpdated'))
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    updatingId.value = null
  }
}

/** 打开详情弹窗 */
function openDetail(word: WordCollection): void {
  activeWord.value = word
  showDetail.value = true
}

/** 关闭详情弹窗 */
function closeDetail(): void {
  showDetail.value = false
  activeWord.value = null
}

/** 删除单词（详情弹窗内确认后触发） */
async function handleDelete(word: WordCollection): Promise<void> {
  try {
    await readingApi.deleteWord(word.id)
    words.value = words.value.filter((w) => w.id !== word.id)
    total.value = Math.max(0, total.value - 1)
    message.success(t('vocabulary.wordDeleted'))
    closeDetail()
    // 当前页删空且非第 1 页：回退一页重新拉取，避免停留在空白页
    if (words.value.length === 0 && page.value > 1) {
      page.value -= 1
      fetchWords()
    }
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}

// ============================================================
//  AI 辅助背诵
// ============================================================

/** 背诵设置弹窗 / 背诵弹窗显示状态 */
const showReciteSetup = ref(false)
const showRecite = ref(false)

/** 本次要背诵的单词数量（默认 10，1-50） */
const reciteCount = ref(10)
/** 快捷数量选项 */
const reciteOptions = [
  { label: '5', value: 5 },
  { label: '10', value: 10 },
  { label: '15', value: 15 },
  { label: '20', value: 20 }
]
/** 按分级词库等级过滤（'' 表示全部） */
const reciteLevel = ref('')
/** 等级筛选选项 */
const reciteLevelOptions = computed(() => [
  { label: t('wordLevel.all'), value: '' },
  { label: t('wordLevel.cet4'), value: 'cet4' },
  { label: t('wordLevel.cet6'), value: 'cet6' },
  { label: t('wordLevel.kaoyan'), value: 'kaoyan' }
])
/** 生成方案中（loading） */
const planGenerating = ref(false)

/** 背诵队列（AI 生成的有序单词）与当前进度 */
const reciteQueue = ref<WordCollection[]>([])
const reciteIndex = ref(0)
const reciteNote = ref<string | null>(null)
/** 正在标记"记住了"的单词 id */
const studyingId = ref<number | null>(null)

/** 当前展示的单词卡片 */
const currentWord = computed(() => reciteQueue.value[reciteIndex.value] ?? null)

/** 打开背诵设置弹窗 */
function openReciteSetup(): void {
  reciteCount.value = 10
  reciteLevel.value = ''
  showReciteSetup.value = true
}

/** 确认数量并生成背诵方案 */
async function startRecite(): Promise<void> {
  planGenerating.value = true
  try {
    const plan = await readingApi.getStudyPlan(
      reciteCount.value,
      reciteLevel.value || undefined
    )
    if (!plan.words.length) {
      message.info(t('vocabulary.reciteEmpty'))
      showReciteSetup.value = false
      return
    }
    reciteQueue.value = [...plan.words]
    reciteNote.value = plan.note
    reciteIndex.value = 0
    showReciteSetup.value = false
    showRecite.value = true
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    planGenerating.value = false
  }
}

/** 记住当前单词：先做双向召回检验，通过后才更新学习信息 */
async function handleRemembered(): Promise<void> {
  const word = currentWord.value
  if (!word || studyingId.value !== null) return
  // 有中文释义才能检验；缺失时直接通过（老数据兜底）
  if (word.short_meaning) {
    openVerify(word)
    return
  }
  await doRemember(word)
}

/** 检验通过后真正标记学习：服务端递增次数 + 掌握度，进入下一个 */
async function doRemember(word: WordCollection): Promise<void> {
  if (studyingId.value !== null) return
  studyingId.value = word.id
  try {
    const updated = await readingApi.markWordStudied(word.id)
    // 同步生词本列表（学习次数变化）
    const idx = words.value.findIndex((w) => w.id === word.id)
    if (idx !== -1) words.value[idx] = updated
    if (activeWord.value?.id === word.id) activeWord.value = updated
    reciteIndex.value += 1
    if (reciteIndex.value >= reciteQueue.value.length) {
      finishRecite()
    }
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    studyingId.value = null
  }
}

/** 没记住当前单词：掌握度重置为新词，重新排到队列末尾复习（不计学习次数） */
async function handleForgot(): Promise<void> {
  const word = currentWord.value
  if (!word || studyingId.value !== null) return
  await resetMasteryAndRequeue(word)
}

/** 把指定单词的掌握度重置为新词（服务端），并重新排到队列末尾复习 */
async function resetMasteryAndRequeue(word: WordCollection): Promise<void> {
  // 立即本地重排，不等待网络
  requeueWord(word)
  // 已是新词则无需请求
  if (word.mastery_level !== 'new') {
    try {
      const updated = await readingApi.updateWord(word.id, { mastery_level: 'new' })
      const idx = words.value.findIndex((w) => w.id === word.id)
      if (idx !== -1) words.value[idx] = updated
      if (activeWord.value?.id === word.id) activeWord.value = updated
    } catch {
      // 错误由 axios 拦截器统一提示；掌握度未更新仍照常复习
    }
  }
}

/** 把指定单词重新排到队列末尾复习 */
function requeueWord(word: WordCollection): void {
  reciteQueue.value.splice(reciteIndex.value, 1)
  reciteQueue.value.push(word)
  if (reciteIndex.value >= reciteQueue.value.length) {
    reciteIndex.value = 0
  }
}

/** 切换到上一个单词（纯翻页，不标记学习） */
function handlePrevWord(): void {
  if (reciteIndex.value > 0) reciteIndex.value -= 1
}

/** 切换到下一个单词（纯翻页，不标记学习） */
function handleNextWord(): void {
  if (reciteIndex.value < reciteQueue.value.length - 1) {
    reciteIndex.value += 1
  }
}

/** 背诵完成：关闭弹窗并刷新列表（学习次数已更新） */
function finishRecite(): void {
  showRecite.value = false
  reciteQueue.value = []
  message.success(t('vocabulary.reciteDone'))
  fetchWords()
}

// ============================================================
//  记住前召回检验
// ============================================================

/** 检验弹窗状态 */
const showVerify = ref(false)
const verifyWord = ref<WordCollection | null>(null)
/** 当前检验步骤：1=看英文写中文，2=看中文写英文 */
const verifyStep = ref<1 | 2>(1)
const verifyInput = ref('')
/** 最近一次提交答错：展示正确答案与重试/没记住 */
const verifyFailed = ref(false)

/** 打开检验弹窗（从"记住了"进入） */
function openVerify(word: WordCollection): void {
  verifyWord.value = word
  verifyStep.value = 1
  verifyInput.value = ''
  verifyFailed.value = false
  showVerify.value = true
}

function closeVerify(): void {
  showVerify.value = false
  verifyWord.value = null
  verifyInput.value = ''
  verifyFailed.value = false
}

/** 提交当前检验步骤的答案，通过则推进/标记，答错则进入失败态 */
function submitVerify(): void {
  const word = verifyWord.value
  if (!word || !verifyInput.value.trim() || verifyFailed.value) return
  const input = verifyInput.value
  if (verifyStep.value === 1) {
    const ok = gradeMeaning(input, word.short_meaning ?? '')
    if (ok) {
      verifyInput.value = ''
      verifyStep.value = 2
    } else {
      verifyFailed.value = true
    }
  } else {
    const ok = gradeWord(input, word.word)
    if (ok) {
      const done = verifyWord.value
      closeVerify()
      if (done) void doRemember(done)
    } else {
      verifyFailed.value = true
    }
  }
}

/** 答错后重试：清空输入回到该检验步骤 */
function retryVerify(): void {
  verifyInput.value = ''
  verifyFailed.value = false
}

/** 答错后选择没记住：关闭检验弹窗，掌握度重置为新词并重新入队 */
async function forgetFromVerify(): Promise<void> {
  const word = verifyWord.value
  closeVerify()
  if (word) await resetMasteryAndRequeue(word)
}

/** 检验步骤指示 chip 样式：已完成绿色、当前蓝色、未到灰色 */
function stepChipClass(step: 1 | 2): string {
  if (verifyFailed.value) {
    return 'bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500'
  }
  if (step < verifyStep.value) {
    return 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400'
  }
  if (step === verifyStep.value) {
    return 'bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400'
  }
  return 'bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500'
}

// ---- 召回检验判分 ----

/** 规范化答案：小写、去空白、去标点（保留字母/数字/撇号/连字符） */
function normalizeAnswer(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[^\p{L}\p{N}'-]/gu, '')
}

/** 编辑距离（Levenshtein） */
function levenshtein(a: string, b: string): number {
  const m = a.length
  const n = b.length
  if (m === 0) return n
  if (n === 0) return m
  let prev = Array.from({ length: n + 1 }, (_, j) => j)
  for (let i = 1; i <= m; i++) {
    const curr = [i, ...new Array<number>(n).fill(0)]
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
    }
    prev = curr
  }
  return prev[n]
}

/** 相似度 0-1（基于编辑距离） */
function similarity(a: string, b: string): number {
  const maxLen = Math.max(a.length, b.length)
  if (maxLen === 0) return 1
  return 1 - levenshtein(a, b) / maxLen
}

/** 英文拼写判分（看中文→写英文）：必须完全一致，只允许大小写与首尾空白差异 */
function gradeWord(input: string, correct: string): boolean {
  return input.trim().toLowerCase() === correct.trim().toLowerCase()
}

/** 中文释义判分（看英文→写中文）：容差清单式释义（"主管、高管" 答 "主管" 即可） */
function gradeMeaning(input: string, correct: string): boolean {
  const a = normalizeAnswer(input)
  const c = normalizeAnswer(correct)
  if (!a || !c) return false
  if (a === c) return true
  // 中文释义常为"含义A、含义B"清单，答出任一完整词条即通过
  const tokens = correct
    .split(/[、，,;；/\\\s]+/)
    .map(normalizeAnswer)
    .filter(Boolean)
  if (tokens.some((tk) => tk === a)) return true
  // 无分隔符的短释义：整体包含判定，避免单个字符（如"主"答"主管"）误放行
  if (a.length >= 2 && c.includes(a)) return true
  if (a.includes(c)) return true
  return similarity(a, c) >= 0.75
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
        <!-- 宽度放在普通 div 上（naive-ui 的 NInput 根元素写死 width:100%，
             会覆盖 Tailwind 的 w-* 类，所以用包装层控制宽度） -->
        <div class="w-80 sm:w-[16rem]">
          <NInput
            v-model:value="searchQuery"
            :placeholder="t('vocabulary.searchPlaceholder')"
            clearable
          >
            <template #prefix>
              <svg class="h-4 w-4 text-neutral-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-4.3-4.3" stroke-linecap="round" />
              </svg>
            </template>
          </NInput>
        </div>

        <!-- AI 辅助背诵 -->
        <NButton type="primary" ghost @click="openReciteSetup">
          <template #icon>
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 18h6 M10 22h4 M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.2 1 2h6c0-.8.4-1.5 1-2A7 7 0 0 0 12 2z" />
            </svg>
          </template>
          {{ t('vocabulary.aiRecite') }}
        </NButton>
      </div>
    </div>

    <!-- 单词网格 / 空状态 -->
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

        <!-- 卡片网格 -->
        <div
          v-else
          class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
        >
          <article
            v-for="word in words"
            :key="word.id"
            class="vocab-card flex flex-col rounded-xl border border-neutral-200 bg-white p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-neutral-300 hover:shadow-md dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
            @click="openDetail(word)"
          >
            <!-- 顶部：单词 + 发音 + 掌握度标签 -->
            <div class="flex items-start justify-between gap-3">
              <div class="flex min-w-0 items-center gap-1.5">
                <h2 class="truncate text-xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50">
                  {{ word.word }}
                </h2>
                <SpeakerButton :word="word.word" size="small" />
              </div>
              <NTag
                :type="masteryTagType[word.mastery_level]"
                size="small"
                round
                :bordered="false"
                class="shrink-0"
              >
                {{ masteryLabel(word.mastery_level) }}
              </NTag>
            </div>

            <!-- 主要意思（简短释义，直接读库字段） -->
            <div class="mt-2 flex-1">
              <p class="line-clamp-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">
                {{ word.short_meaning || t('vocabulary.noExplanation') }}
              </p>
            </div>

            <!-- 词汇等级徽标（来自分级词库） -->
            <div v-if="word.levels?.length" class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="lv in word.levels"
                :key="lv"
                class="rounded bg-blue-50 px-1.5 py-0.5 text-[11px] font-medium text-blue-600 dark:bg-blue-500/10 dark:text-blue-400"
              >
                {{ t(`wordLevel.${lv}`) }}
              </span>
            </div>

            <!-- 底部：快速标记按钮 -->
            <div class="mt-4 flex gap-1.5" @click.stop>
              <button
                v-for="level in masteryLevels"
                :key="level"
                class="vocab-mark"
                :class="[`vocab-mark--${level}`, { 'vocab-mark--active': word.mastery_level === level }]"
                :disabled="updatingId === word.id"
                :title="masteryLabel(level)"
                @click.stop="handleMasteryChange(word, level)"
              >
                {{ masteryLabel(level) }}
              </button>
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

    <!-- 详情弹窗 -->
    <NModal
      :show="showDetail"
      preset="card"
      class="vocab-modal"
      :title="activeWord?.word"
      :style="{ '--n-width': '440px', maxWidth: '90vw' }"
      :content-style="{ maxHeight: '60vh', overflowY: 'auto' }"
      @update:show="(v: boolean) => (v ? undefined : closeDetail())"
    >
      <template v-if="activeWord">
        <!-- 简短释义 + 发音 + 掌握度标签 -->
        <div class="flex flex-wrap items-center gap-3">
          <span v-if="activeWord.short_meaning" class="text-base text-neutral-600 dark:text-neutral-300">
            {{ activeWord.short_meaning }}
          </span>
          <SpeakerButton :word="activeWord.word" />
          <NTag
            :type="masteryTagType[activeWord.mastery_level]"
            size="small"
            round
            :bordered="false"
          >
            {{ masteryLabel(activeWord.mastery_level) }}
          </NTag>
        </div>

        <!-- 词汇等级徽标（来自分级词库） -->
        <div v-if="activeWord.levels?.length" class="mt-3 flex flex-wrap gap-1.5">
          <span
            v-for="lv in activeWord.levels"
            :key="lv"
            class="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600 dark:bg-blue-500/10 dark:text-blue-400"
          >
            {{ t(`wordLevel.${lv}`) }}
          </span>
        </div>

        <!-- 掌握度快速切换 -->
        <div class="mt-4 flex gap-2">
          <button
            v-for="level in masteryLevels"
            :key="level"
            class="vocab-mark vocab-mark--lg"
            :class="[`vocab-mark--${level}`, { 'vocab-mark--active': activeWord.mastery_level === level }]"
            :disabled="updatingId === activeWord.id"
            @click="handleMasteryChange(activeWord, level)"
          >
            {{ masteryLabel(level) }}
          </button>
        </div>

        <!-- AI 解释全文 -->
        <div class="mt-5">
          <span class="text-[11px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            {{ t('vocabulary.explanation') }}
          </span>
          <!-- eslint-disable vue/no-v-html -->
          <div
            v-if="activeWord.ai_explanation"
            class="markdown-body mt-1"
            v-html="renderMarkdown(activeWord.ai_explanation)"
          />
          <p v-else class="mt-1 text-sm text-neutral-400 dark:text-neutral-500">
            {{ t('vocabulary.noExplanation') }}
          </p>
        </div>

        <!-- 上下文 -->
        <div v-if="activeWord.context" class="mt-5">
          <span class="text-[11px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            {{ t('vocabulary.context') }}
          </span>
          <p class="mt-1 rounded-lg bg-neutral-50 p-3 text-sm leading-relaxed text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
            {{ activeWord.context }}
          </p>
        </div>

        <!-- 学习信息 -->
        <div class="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-neutral-100 pt-4 text-xs text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
          <span>{{ t('vocabulary.studyCount', { count: activeWord.study_count }) }}</span>
          <span v-if="activeWord.last_studied_at">
            {{ t('vocabulary.lastStudied', { time: formatDateTime(activeWord.last_studied_at) }) }}
          </span>
          <span v-else>{{ t('vocabulary.never') }}</span>
          <span>{{ t('vocabulary.collectedAt', { time: formatDateTime(activeWord.created_at) }) }}</span>
        </div>

        <!-- 底部操作：删除 -->
        <div class="mt-5 flex justify-end border-t border-neutral-100 pt-4 dark:border-neutral-800">
          <NPopconfirm
            :positive-text="t('common.delete')"
            :negative-text="t('common.cancel')"
            @positive-click="handleDelete(activeWord)"
          >
            <template #trigger>
              <NButton size="small" quaternary type="error">
                {{ t('common.delete') }}
              </NButton>
            </template>
            {{ t('vocabulary.deleteConfirm') }}
          </NPopconfirm>
        </div>
      </template>
    </NModal>

    <!-- AI 背诵：设置数量弹窗 -->
    <NModal
      v-model:show="showReciteSetup"
      preset="card"
      :title="t('vocabulary.reciteTitle')"
      style="width: 400px; max-width: 92vw"
    >
      <div class="py-2">
        <p class="mb-2 text-sm text-neutral-500 dark:text-neutral-400">
          {{ t('vocabulary.reciteCountLabel') }}
        </p>
        <NInputNumber
          v-model:value="reciteCount"
          :min="1"
          :max="50"
          class="w-full"
        />
        <div class="mt-3 flex gap-2">
          <NButton
            v-for="opt in reciteOptions"
            :key="opt.value"
            size="small"
            :type="reciteCount === opt.value ? 'primary' : 'default'"
            @click="reciteCount = opt.value"
          >
            {{ opt.label }}
          </NButton>
        </div>

        <!-- 词汇等级筛选（可选） -->
        <p class="mb-2 mt-5 text-sm text-neutral-500 dark:text-neutral-400">
          {{ t('vocabulary.reciteLevelLabel') }}
        </p>
        <NSelect v-model:value="reciteLevel" :options="reciteLevelOptions" class="w-full" />
      </div>

      <!-- 生成方案中的友好提示 -->
      <div
        v-if="planGenerating"
        class="flex items-center gap-2 rounded-lg bg-neutral-50 px-3 py-2.5 text-sm text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400"
      >
        <NSpin :size="16" />
        {{ t('vocabulary.reciteGenerating') }}
      </div>

      <template #footer>
        <div class="flex justify-end">
          <NButton type="primary" :loading="planGenerating" @click="startRecite">
            {{ t('vocabulary.reciteStart') }}
          </NButton>
        </div>
      </template>
    </NModal>

    <!-- AI 背诵：逐词背诵弹窗 -->
    <NModal
      v-model:show="showRecite"
      preset="card"
      :title="t('vocabulary.reciteTitle')"
      style="width: 480px; max-width: 92vw"
    >
      <div class="mb-4 flex items-center justify-between">
        <span class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ t('vocabulary.reciteProgress', { cur: reciteIndex + 1, total: reciteQueue.length }) }}
        </span>
        <span class="text-xs text-neutral-400">{{ t('vocabulary.reciteHint') }}</span>
      </div>

      <p v-if="reciteNote" class="mb-4 rounded-lg bg-neutral-50 px-3 py-2 text-xs text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
        {{ t('vocabulary.reciteNote') }}：{{ reciteNote }}
      </p>

      <!-- 当前单词卡片 -->
      <div
        v-if="currentWord"
        class="rounded-xl border border-neutral-200 bg-neutral-50 p-6 dark:border-neutral-800 dark:bg-neutral-800/40"
      >
        <div class="flex items-center justify-between">
          <h2 class="text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50">
            {{ currentWord.word }}
          </h2>
          <SpeakerButton :word="currentWord.word" size="small" />
        </div>

        <p class="mt-2 text-base text-neutral-600 dark:text-neutral-300">
          {{ currentWord.short_meaning || t('vocabulary.noExplanation') }}
        </p>

        <div
          v-if="currentWord.ai_explanation"
          class="mt-4 border-t border-neutral-200 pt-3 text-sm text-neutral-500 dark:border-neutral-800 dark:text-neutral-400 prose-comfortable"
          v-html="renderMarkdown(currentWord.ai_explanation)"
        />

        <p v-if="currentWord.context" class="mt-3 text-xs text-neutral-400 dark:text-neutral-500">
          {{ t('vocabulary.context') }}：{{ currentWord.context }}
        </p>
      </div>

      <template #footer>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <!-- 翻页：上一个 / 下一个（纯切换，不标记） -->
          <div class="flex gap-2">
            <NButton
              :disabled="reciteIndex === 0 || studyingId !== null"
              @click="handlePrevWord"
            >
              <template #icon>
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m15 18-6-6 6-6" />
                </svg>
              </template>
              {{ t('vocabulary.prevWord') }}
            </NButton>
            <NButton
              :disabled="reciteIndex >= reciteQueue.length - 1 || studyingId !== null"
              @click="handleNextWord"
            >
              {{ t('vocabulary.nextWord') }}
              <template #icon>
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </template>
            </NButton>
          </div>

          <!-- 标记：没记住 / 记住了 -->
          <div class="flex gap-2">
            <NButton type="error" tertiary :disabled="studyingId !== null" @click="handleForgot">
              {{ t('vocabulary.forgot') }}
            </NButton>
            <NButton type="primary" :loading="studyingId !== null" @click="handleRemembered">
              {{ t('vocabulary.remembered') }}
            </NButton>
          </div>
        </div>
      </template>
    </NModal>

    <!-- 记住前召回检验弹窗 -->
    <NModal
      v-model:show="showVerify"
      preset="card"
      :title="t('vocabulary.reciteVerifyTitle')"
      style="width: 440px; max-width: 92vw"
    >
      <template v-if="verifyWord">
        <div class="mb-4 flex items-center justify-between">
          <span class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ t('vocabulary.reciteProgress', { cur: reciteIndex + 1, total: reciteQueue.length }) }}
          </span>
          <div class="flex items-center gap-1.5">
            <span class="rounded-full px-2 py-0.5 text-xs" :class="stepChipClass(1)">
              ① {{ t('vocabulary.reciteVerifyStep1') }}
            </span>
            <span class="rounded-full px-2 py-0.5 text-xs" :class="stepChipClass(2)">
              ② {{ t('vocabulary.reciteVerifyStep2') }}
            </span>
          </div>
        </div>

        <!-- 答题区 -->
        <template v-if="!verifyFailed">
          <div
            class="rounded-xl border border-neutral-200 bg-neutral-50 p-6 text-center dark:border-neutral-800 dark:bg-neutral-800/40"
          >
            <p class="text-xs uppercase tracking-wider text-neutral-400">
              {{ verifyStep === 1 ? t('vocabulary.reciteVerifyStep1') : t('vocabulary.reciteVerifyStep2') }}
            </p>
            <p class="mt-3 text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50">
              {{ verifyStep === 1 ? verifyWord.word : verifyWord.short_meaning }}
            </p>
            <p class="mt-2 text-xs text-neutral-400">
              {{
                verifyStep === 1
                  ? t('vocabulary.reciteVerifyEnglishHint')
                  : t('vocabulary.reciteVerifyMeaningHint')
              }}
            </p>
          </div>

          <NInput
            v-model:value="verifyInput"
            class="mt-4"
            :placeholder="
              verifyStep === 1
                ? t('vocabulary.reciteVerifyMeaningPlaceholder')
                : t('vocabulary.reciteVerifyWordPlaceholder')
            "
            @keydown.enter.prevent="submitVerify"
          />

          <div class="mt-4 flex justify-end">
            <NButton type="primary" :disabled="!verifyInput.trim()" @click="submitVerify">
              {{ t('vocabulary.reciteVerifySubmit') }}
            </NButton>
          </div>
        </template>

        <!-- 答错：展示正确答案 -->
        <div
          v-else
          class="rounded-xl border border-red-200 bg-red-50 p-4 dark:border-red-500/30 dark:bg-red-500/10"
        >
          <p class="text-sm font-semibold text-red-600 dark:text-red-400">
            {{ t('vocabulary.reciteVerifyWrong') }}
          </p>
          <p class="mt-3 text-lg font-semibold text-neutral-900 dark:text-neutral-50">
            {{ verifyWord.word }}
            <span
              v-if="verifyWord.short_meaning"
              class="ml-2 text-base font-normal text-neutral-500 dark:text-neutral-400"
            >
              {{ verifyWord.short_meaning }}
            </span>
          </p>
          <p class="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {{ t('vocabulary.reciteVerifyYourAnswer') }}：{{ verifyInput }}
          </p>
        </div>
      </template>

      <template #footer>
        <div v-if="verifyWord && verifyFailed" class="flex justify-end gap-2">
          <NButton @click="retryVerify">
            {{ t('vocabulary.reciteVerifyRetry') }}
          </NButton>
          <NButton type="error" tertiary @click="forgetFromVerify">
            {{ t('vocabulary.forgot') }}
          </NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
/* NTabs：去除默认底部多余间距，与工具栏对齐 */
.vocab-tabs {
  --n-tab-padding: 6px 14px;
}

/* ============================================================
   快速标记按钮
   ============================================================ */
.vocab-mark {
  flex: 1;
  min-width: 0;
  padding: 4px 0;
  border: 1px solid var(--border, #e4e4e7);
  border-radius: 6px;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
  color: #71717a;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vocab-mark:disabled {
  cursor: default;
  opacity: 0.6;
}

.vocab-mark--lg {
  flex: none;
  padding: 6px 14px;
  font-size: 13px;
}

/* 各等级默认色（边框 + 文字） */
.vocab-mark--new { color: #71717a; border-color: #d4d4d8; }
.vocab-mark--learning { color: #2563eb; border-color: #bfdbfe; }
.vocab-mark--familiar { color: #d97706; border-color: #fde68a; }
.vocab-mark--mastered { color: #16a34a; border-color: #bbf7d0; }

.vocab-mark:not(:disabled):hover {
  transform: translateY(-1px);
}

.vocab-mark--new:not(:disabled):hover { background: #f4f4f5; }
.vocab-mark--learning:not(:disabled):hover { background: #eff6ff; }
.vocab-mark--familiar:not(:disabled):hover { background: #fffbeb; }
.vocab-mark--mastered:not(:disabled):hover { background: #f0fdf4; }

/* 当前选中态：实心填充 */
.vocab-mark--active,
.vocab-mark--active:disabled {
  color: #ffffff;
  border-color: transparent;
  opacity: 1;
}
.vocab-mark--new.vocab-mark--active { background: #71717a; }
.vocab-mark--learning.vocab-mark--active { background: #2563eb; }
.vocab-mark--familiar.vocab-mark--active { background: #d97706; }
.vocab-mark--mastered.vocab-mark--active { background: #16a34a; }

/* ============================================================
   Markdown 渲染（AI 解释，v-html 内容需 :deep 穿透）
   ============================================================ */
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
:global(html.dark) .vocab-mark {
  border-color: #3f3f46;
  color: #a1a1aa;
}

:global(html.dark) .vocab-mark--learning { color: #93c5fd; border-color: #1e40af; }
:global(html.dark) .vocab-mark--familiar { color: #fcd34d; border-color: #92400e; }
:global(html.dark) .vocab-mark--mastered { color: #86efac; border-color: #166534; }

:global(html.dark) .vocab-mark--new:not(:disabled):hover { background: #27272a; }
:global(html.dark) .vocab-mark--learning:not(:disabled):hover { background: #172554; }
:global(html.dark) .vocab-mark--familiar:not(:disabled):hover { background: #451a03; }
:global(html.dark) .vocab-mark--mastered:not(:disabled):hover { background: #052e16; }

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
