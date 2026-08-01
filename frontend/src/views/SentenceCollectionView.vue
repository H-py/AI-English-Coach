<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NInput,
  NPopconfirm,
  NButton,
  NPagination,
  NSpin,
  NEmpty,
  useMessage
} from 'naive-ui'
import { useDebounceFn } from '@vueuse/core'
import { readingApi } from '@/api/reading'
import type { SentenceCollection } from '@/types/reading'

/**
 * 句子收藏页面。
 *
 * 功能：
 *  - 按句子文本搜索（防抖 300ms）
 *  - 卡片列表展示：句子文本（英文）、用户笔记（可内联编辑）、创建时间
 *  - 操作：内联编辑笔记（保存 / 取消）、Popconfirm 确认删除
 *  - 分页、空状态、加载状态
 *
 * 数据通过 readingApi 直接获取（非 store），本页自管理列表状态。
 */

const { t } = useI18n()
const message = useMessage()

// ============================================================
//  工具函数
// ============================================================

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

const searchQuery = ref('')
const sentences = ref<SentenceCollection[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

/** 是否展示分页器：总数超过单页时显示 */
const showPagination = computed(() => total.value > pageSize.value)

// ============================================================
//  笔记内联编辑状态
// ============================================================

/** 当前正在编辑笔记的句子 id（null 表示无编辑态） */
const editingId = ref<number | null>(null)
/** 编辑中的笔记内容（临时缓冲，保存前不写入列表） */
const editingNote = ref('')
/** 正在保存笔记的句子 id，用于按钮 loading 与防重复提交 */
const savingId = ref<number | null>(null)

// ============================================================
//  数据拉取
// ============================================================

/** 组装查询参数并拉取句子收藏列表 */
async function fetchSentences(): Promise<void> {
  loading.value = true
  try {
    const res = await readingApi.listSentences({
      page: page.value,
      page_size: pageSize.value,
      search: searchQuery.value.trim() || undefined
    })
    sentences.value = res.items
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
  fetchSentences()
}, 300)

watch(searchQuery, () => debouncedSearch())

/** 翻页 */
function handlePageChange(p: number): void {
  page.value = p
  fetchSentences()
}

// ============================================================
//  笔记编辑
// ============================================================

/** 进入编辑态：记录当前句子 id 与笔记初始值 */
function startEdit(sentence: SentenceCollection): void {
  editingId.value = sentence.id
  editingNote.value = sentence.note ?? ''
}

/** 取消编辑：清空编辑态 */
function cancelEdit(): void {
  editingId.value = null
  editingNote.value = ''
}

/** 保存笔记：调用更新接口，成功后同步本地列表并退出编辑态 */
async function saveEdit(sentence: SentenceCollection): Promise<void> {
  if (editingId.value === null) return
  savingId.value = sentence.id
  try {
    const updated = await readingApi.updateSentence(editingId.value, {
      note: editingNote.value
    })
    const idx = sentences.value.findIndex((s) => s.id === sentence.id)
    if (idx !== -1) sentences.value[idx] = updated
    message.success(t('sentences.noteUpdated'))
    editingId.value = null
    editingNote.value = ''
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    savingId.value = null
  }
}

// ============================================================
//  删除
// ============================================================

/** 删除句子（Popconfirm 确认后触发） */
async function handleDelete(sentence: SentenceCollection): Promise<void> {
  try {
    await readingApi.deleteSentence(sentence.id)
    sentences.value = sentences.value.filter((s) => s.id !== sentence.id)
    total.value = Math.max(0, total.value - 1)
    message.success(t('sentences.sentenceDeleted'))
    // 当前页删空且非第 1 页：回退一页重新拉取，避免停留在空白页
    if (sentences.value.length === 0 && page.value > 1) {
      page.value -= 1
      fetchSentences()
    }
  } catch {
    // 错误由 axios 拦截器统一提示
  }
}

onMounted(fetchSentences)
</script>

<template>
  <div class="space-y-6">
    <!-- 页头 -->
    <header class="space-y-2">
      <h1 class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl">
        {{ t('sentences.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('sentences.subtitle') }}
      </p>
    </header>

    <!-- 工具栏：总数 + 搜索 -->
    <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <span class="text-xs text-neutral-400 dark:text-neutral-500">
        {{ t('sentences.totalSentences', { count: total }) }}
      </span>

      <div class="flex items-center gap-3">
        <NInput
          v-model:value="searchQuery"
          :placeholder="t('sentences.searchPlaceholder')"
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

    <!-- 句子列表 / 空状态 -->
    <div class="min-h-[300px]">
      <NSpin :show="loading">
        <!-- 空状态 -->
        <NEmpty
          v-if="!loading && sentences.length === 0"
          :description="t('sentences.empty')"
          class="py-20"
        >
          <template #extra>
            <p class="text-sm text-neutral-400 dark:text-neutral-500">
              {{ t('sentences.emptyHint') }}
            </p>
          </template>
        </NEmpty>

        <!-- 卡片列表 -->
        <div v-else class="space-y-4">
          <article
            v-for="sentence in sentences"
            :key="sentence.id"
            class="sentence-card rounded-xl border border-neutral-200 bg-white p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-neutral-800 dark:bg-neutral-900 sm:p-6"
          >
            <!-- 句子文本 -->
            <p class="text-lg font-medium leading-relaxed text-neutral-900 dark:text-neutral-50">
              {{ sentence.sentence }}
            </p>

            <!-- 笔记 -->
            <div class="mt-4">
              <div class="flex items-center justify-between">
                <span class="text-[11px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                  {{ t('sentences.note') }}
                </span>
                <!-- 编辑 / 添加按钮（非编辑态显示） -->
                <NButton
                  v-if="editingId !== sentence.id"
                  size="tiny"
                  quaternary
                  @click="startEdit(sentence)"
                >
                  {{ sentence.note ? t('sentences.editNote') : t('sentences.addNote') }}
                </NButton>
              </div>

              <!-- 编辑态：内联 textarea -->
              <div v-if="editingId === sentence.id" class="mt-2">
                <NInput
                  v-model:value="editingNote"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  :placeholder="t('sentences.addNote')"
                />
                <div class="mt-2 flex justify-end gap-2">
                  <NButton size="small" @click="cancelEdit">
                    {{ t('sentences.cancel') }}
                  </NButton>
                  <NButton
                    size="small"
                    type="primary"
                    :loading="savingId === sentence.id"
                    @click="saveEdit(sentence)"
                  >
                    {{ t('sentences.save') }}
                  </NButton>
                </div>
              </div>

              <!-- 展示态：已有笔记 -->
              <p
                v-else-if="sentence.note"
                class="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-neutral-600 dark:text-neutral-300"
              >
                {{ sentence.note }}
              </p>

              <!-- 展示态：无笔记 -->
              <p v-else class="mt-1 text-sm text-neutral-400 dark:text-neutral-500">
                {{ t('sentences.noNote') }}
              </p>
            </div>

            <!-- 底部：创建时间 + 删除 -->
            <div class="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100 pt-4 dark:border-neutral-800">
              <div class="flex items-center gap-2 text-xs text-neutral-400 dark:text-neutral-500">
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" />
                  <path d="M16 2v4M8 2v4M3 10h18" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
                <span>{{ formatDateTime(sentence.created_at) }}</span>
              </div>

              <NPopconfirm
                :positive-text="t('common.delete')"
                :negative-text="t('common.cancel')"
                @positive-click="handleDelete(sentence)"
              >
                <template #trigger>
                  <NButton size="small" quaternary type="error">
                    {{ t('common.delete') }}
                  </NButton>
                </template>
                {{ t('sentences.deleteConfirm') }}
              </NPopconfirm>
            </div>
          </article>
        </div>
      </NSpin>
    </div>

    <!-- 分页 -->
    <div
      v-if="showPagination"
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
/* 句子卡片：悬停过渡平滑（配合 Tailwind hover 类） */
.sentence-card {
  will-change: transform;
}

/* ============================================================
   暗色模式
   ============================================================ */
:global(html.dark) .sentence-card {
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

:global(html.dark) .sentence-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
</style>
