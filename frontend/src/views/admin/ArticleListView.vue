<script setup lang="ts">
import { h, computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDebounceFn } from '@vueuse/core'
import {
  NDataTable,
  NButton,
  NInput,
  NSelect,
  NTag,
  NPagination,
  NSpace,
  NPopconfirm,
  useMessage
} from 'naive-ui'
import type { DataTableColumns, SelectOption } from 'naive-ui'
import { adminApi } from '@/api/admin'
import StarRating from '@/components/StarRating.vue'
import type { AdminArticleListItem, AdminArticleQuery } from '@/types/admin'
import type { CetType, Difficulty } from '@/types/article'

/**
 * 文章管理列表页（管理后台）。
 *
 * 功能：
 *  - 按标题搜索（防抖 400ms）
 *  - 按难度（1-5 星 / 全部）筛选
 *  - 按四六级真题（全部 / 四级 / 六级）筛选
 *  - 按发布状态（全部 / 已发布 / 草稿）筛选
 *  - 表格列：标题 / 难度(星级) / 四六级 / 标签 / 状态(tag) / 浏览量 / 词数 / 创建时间 / 操作(编辑/删除)
 *  - 新建文章 -> /admin/articles/new
 *  - 编辑 -> /admin/articles/{id}/edit
 *  - 删除：Popconfirm 确认后调用 adminApi.deleteArticle，成功提示并刷新列表
 *  - 底部分页（支持切换每页条数）
 *
 * 错误提示由 axios 响应拦截器统一处理（与项目其他页面一致），
 * 成功提示使用 useMessage。
 */
const { t } = useI18n()
const router = useRouter()
const message = useMessage()

// ============================================================
//  查询状态
// ============================================================

const articles = ref<AdminArticleListItem[]>([])
const total = ref(0)
const loading = ref(false)

const page = ref(1)
const pageSize = ref(10)
const searchQuery = ref('')
// 使用字符串哨兵 'all' 便于 NSelect 绑定，查询时再映射为 undefined
const difficultyFilter = ref<string>('all')
const cetTypeFilter = ref<string>('all')
const statusFilter = ref<string>('all')

const pageSizeOptions = [10, 20, 50]

/** 难度筛选下拉选项（全部 + 1-5 星） */
const difficultyOptions = computed<SelectOption[]>(() => [
  { label: t('article.allDifficulties'), value: 'all' },
  ...(['1', '2', '3', '4', '5'] as Difficulty[]).map((d) => ({
    label: t(`article.difficulty.${d}`),
    value: d
  }))
])

/** 四六级真题筛选下拉选项（全部 / 四级 / 六级） */
const cetTypeOptions = computed<SelectOption[]>(() => [
  { label: t('article.cet.all'), value: 'all' },
  { label: t('article.cet.cet4'), value: 'cet4' },
  { label: t('article.cet.cet6'), value: 'cet6' }
])

/** 发布状态下拉选项（全部 / 已发布 / 草稿） */
const statusOptions = computed<SelectOption[]>(() => [
  { label: t('admin.article.allStatus'), value: 'all' },
  { label: t('admin.article.published'), value: 'published' },
  { label: t('admin.article.draft'), value: 'draft' }
])

/** 查询参数中的 difficulty（'all' 时不传，由后端返回全部） */
const difficultyParam = computed<Difficulty | undefined>(() =>
  difficultyFilter.value === 'all' ? undefined : (difficultyFilter.value as Difficulty)
)

/** 查询参数中的 cet_type（'all' 时不传） */
const cetTypeParam = computed<CetType | undefined>(() =>
  cetTypeFilter.value === 'all' ? undefined : (cetTypeFilter.value as CetType)
)

/** 查询参数中的 is_published（'all' 时不传） */
const isPublishedParam = computed<boolean | undefined>(() => {
  if (statusFilter.value === 'all') return undefined
  return statusFilter.value === 'published'
})

// ============================================================
//  数据拉取
// ============================================================

/** 按当前查询状态拉取文章列表 */
async function fetchArticles(): Promise<void> {
  loading.value = true
  try {
    const params: AdminArticleQuery = {
      page: page.value,
      page_size: pageSize.value,
      search: searchQuery.value.trim() || undefined,
      difficulty: difficultyParam.value,
      cet_type: cetTypeParam.value,
      is_published: isPublishedParam.value
    }
    const res = await adminApi.listArticles(params)
    articles.value = res.items
    total.value = res.total
  } catch {
    // 错误由 axios 响应拦截器统一提示
  } finally {
    loading.value = false
  }
}

/** 搜索防抖：输入停止 400ms 后重置到第 1 页并拉取 */
const debouncedSearch = useDebounceFn(() => {
  page.value = 1
  fetchArticles()
}, 400)

watch(searchQuery, () => debouncedSearch())

/** 难度 / 四六级 / 状态筛选变化：重置到第 1 页并重新加载 */
watch([difficultyFilter, cetTypeFilter, statusFilter], () => {
  page.value = 1
  fetchArticles()
})

/** 翻页 */
function handlePageChange(p: number): void {
  page.value = p
  fetchArticles()
}

/** 切换每页条数：重置到第 1 页并重新加载 */
function handlePageSizeChange(ps: number): void {
  pageSize.value = ps
  page.value = 1
  fetchArticles()
}

/** 难度下拉选中（NSelect 不使用 v-model 以避免 string|number 类型摩擦） */
function handleDifficultyChange(v: string | number | null): void {
  difficultyFilter.value = v == null ? 'all' : String(v)
}

/** 四六级下拉选中 */
function handleCetTypeChange(v: string | number | null): void {
  cetTypeFilter.value = v == null ? 'all' : String(v)
}

/** 状态下拉选中 */
function handleStatusChange(v: string | number | null): void {
  statusFilter.value = v == null ? 'all' : String(v)
}

// ============================================================
//  操作
// ============================================================

/** 跳转新建文章页 */
function handleCreate(): void {
  router.push('/admin/articles/new')
}

/** 跳转编辑文章页 */
function handleEdit(id: number): void {
  router.push(`/admin/articles/${id}/edit`)
}

/** 删除文章（Popconfirm 确认后触发） */
async function handleDelete(id: number): Promise<void> {
  try {
    await adminApi.deleteArticle(id)
    message.success(t('admin.article.deleted'))
    // 当前页删空且非第 1 页：回退一页，避免停留在空白页
    if (articles.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await fetchArticles()
  } catch {
    // 错误由 axios 响应拦截器统一提示
  }
}

/** 格式化 ISO 日期为本地日期字符串 */
function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString()
}

/** 表格行 key */
function rowKey(row: AdminArticleListItem): number {
  return row.id
}

// ============================================================
//  表格列定义（标签 / 操作使用 h() 渲染）
// ============================================================

const columns = computed<DataTableColumns<AdminArticleListItem>>(() => [
  {
    title: t('admin.article.fields.title'),
    key: 'title',
    minWidth: 220,
    ellipsis: { tooltip: true },
    render: (row) =>
      h(
        'span',
        { class: 'font-medium text-neutral-900 dark:text-neutral-100' },
        row.title
      )
  },
  {
    title: t('admin.article.fields.difficulty'),
    key: 'difficulty',
    width: 130,
    render: (row) => h(StarRating, { stars: Number(row.difficulty) })
  },
  {
    title: t('admin.article.fields.cetType'),
    key: 'cet_type',
    width: 100,
    render: (row) =>
      row.cet_type
        ? h(
            NTag,
            { size: 'small', bordered: false, type: 'warning' },
            { default: () => t(`article.cet.${row.cet_type}`) }
          )
        : h('span', { class: 'text-neutral-400 dark:text-neutral-600' }, '—')
  },
  {
    title: t('admin.article.fields.tags'),
    key: 'tags',
    minWidth: 160,
    maxWidth: 220,
    render: (row) => {
      if (row.tags.length === 0) {
        return h('span', { class: 'text-neutral-400 dark:text-neutral-600' }, '—')
      }
      // 最多展示 2 个标签，超出以 +N 折叠，避免溢出到相邻列
      const visible = row.tags.slice(0, 2)
      const rest = row.tags.length - visible.length
      const tags = visible.map((tag) =>
        h(
          NTag,
          { size: 'small', bordered: false, round: true },
          { default: () => tag }
        )
      )
      if (rest > 0) {
        tags.push(
          h(
            NTag,
            { size: 'small', bordered: false, round: true },
            { default: () => `+${rest}` }
          )
        )
      }
      return h(NSpace, { size: 4, wrap: true }, () => tags)
    }
  },
  {
    title: t('admin.article.status'),
    key: 'is_published',
    width: 120,
    render: (row) =>
      h(
        NTag,
        {
          type: row.is_published ? 'success' : 'default',
          size: 'small',
          bordered: false,
          round: true
        },
        {
          default: () =>
            row.is_published ? t('admin.article.published') : t('admin.article.draft')
        }
      )
  },
  {
    title: t('admin.article.views'),
    key: 'view_count',
    width: 100,
    align: 'right',
    render: (row) =>
      h(
        'span',
        { class: 'tabular-nums text-neutral-500 dark:text-neutral-400' },
        String(row.view_count)
      )
  },
  {
    title: t('admin.article.fields.wordCount'),
    key: 'word_count',
    width: 110,
    align: 'right',
    render: (row) =>
      h(
        'span',
        { class: 'tabular-nums text-neutral-500 dark:text-neutral-400' },
        String(row.word_count)
      )
  },
  {
    title: t('admin.article.createdAt'),
    key: 'created_at',
    width: 130,
    render: (row) =>
      h(
        'span',
        { class: 'text-neutral-500 dark:text-neutral-400' },
        formatDate(row.created_at)
      )
  },
  {
    title: t('admin.article.actions'),
    key: 'actions',
    width: 170,
    fixed: 'right',
    render: (row) =>
      h(NSpace, { size: 8, wrap: false }, () => [
        h(
          NButton,
          { size: 'small', secondary: true, onClick: () => handleEdit(row.id) },
          { default: () => t('admin.article.edit') }
        ),
        h(
          NPopconfirm,
          {
            positiveText: t('common.delete'),
            negativeText: t('common.cancel'),
            onPositiveClick: () => handleDelete(row.id)
          },
          {
            trigger: () =>
              h(
                NButton,
                { size: 'small', quaternary: true, type: 'error' },
                { default: () => t('admin.article.delete') }
              ),
            default: () => t('admin.article.deleteConfirm')
          }
        )
      ])
  }
])

onMounted(fetchArticles)
</script>

<template>
  <div class="space-y-6">
    <!-- 页头 -->
    <header class="space-y-1">
      <h1 class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl">
        {{ t('admin.article.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400">
        {{ t('common.total', { count: total }) }}
      </p>
    </header>

    <!-- 工具栏：搜索 + 筛选 + 新建 -->
    <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <NSpace :size="12" align="center" :wrap="true">
        <NInput
          v-model:value="searchQuery"
          :placeholder="t('admin.article.searchPlaceholder')"
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

        <NSelect
          :value="difficultyFilter"
          :options="difficultyOptions"
          class="w-44"
          @update:value="handleDifficultyChange"
        />

        <NSelect
          :value="cetTypeFilter"
          :options="cetTypeOptions"
          class="w-32"
          @update:value="handleCetTypeChange"
        />

        <NSelect
          :value="statusFilter"
          :options="statusOptions"
          class="w-36"
          @update:value="handleStatusChange"
        />
      </NSpace>

      <NButton type="primary" @click="handleCreate">
        <template #icon>
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14" stroke-linecap="round" />
          </svg>
        </template>
        {{ t('admin.article.create') }}
      </NButton>
    </div>

    <!-- 表格 -->
    <div class="overflow-hidden rounded-xl border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <NDataTable
        :columns="columns"
        :data="articles"
        :loading="loading"
        :pagination="false"
        :bordered="false"
        :row-key="rowKey"
        :scroll-x="1180"
      >
        <template #empty>
          <div class="py-16 text-center text-sm text-neutral-400 dark:text-neutral-500">
            {{ t('common.noData') }}
          </div>
        </template>
      </NDataTable>
    </div>

    <!-- 分页 -->
    <div
      v-if="total > 0"
      class="flex justify-center pt-1"
    >
      <NPagination
        :page="page"
        :page-size="pageSize"
        :item-count="total"
        :page-sizes="pageSizeOptions"
        show-size-picker
        show-quick-jumper
        @update:page="handlePageChange"
        @update:page-size="handlePageSizeChange"
      />
    </div>
  </div>
</template>
