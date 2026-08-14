<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSwitch,
  NButton,
  NDynamicTags,
  NInputNumber,
  NSpin,
  useMessage,
  type FormInst,
  type FormRules
} from 'naive-ui'
import { adminApi } from '@/api/admin'
import type { AdminArticleCreatePayload, AdminArticleUpdatePayload } from '@/types/admin'
import type { Article, CetType, Difficulty } from '@/types/article'

/**
 * 文章编辑 / 创建页（管理后台）。
 *
 * - 路由 `/admin/articles/new`      -> 创建模式；
 * - 路由 `/admin/articles/:id/edit` -> 编辑模式，挂载时拉取文章详情回填表单。
 *
 * 表单校验仅强制 title / content 必填，其余字段可选。
 * 保存成功后弹出提示并跳回文章列表 `/admin/articles`。
 */

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const message = useMessage()

// ============================================================
//  模式判定
// ============================================================

/** 从路由参数解析文章 ID，无法解析则为 null（即创建模式） */
const articleId = computed<number | null>(() => {
  const id = Number(route.params.id)
  return Number.isNaN(id) ? null : id
})

/** 是否为编辑模式 */
const isEdit = computed(() => articleId.value !== null)

/** 页面标题：随模式与语言切换响应式更新 */
const pageTitle = computed(() =>
  isEdit.value ? t('admin.article.editTitle') : t('admin.article.createTitle')
)

// ============================================================
//  表单模型
// ============================================================

interface ArticleFormModel {
  title: string
  content: string
  summary: string
  source: string
  difficulty: Difficulty
  cet_type: string
  tags: string[]
  reading_time: number | null
  cover_url: string
  is_published: boolean
}

const model = reactive<ArticleFormModel>({
  title: '',
  content: '',
  summary: '',
  source: '',
  difficulty: '3',
  cet_type: '',
  tags: [],
  reading_time: null,
  cover_url: '',
  is_published: false
})

const formRef = ref<FormInst | null>(null)
/** 保存按钮 loading */
const saving = ref(false)
/** 编辑模式下初次拉取文章 loading */
const fetching = ref(false)

/** 难度选项：1-5 星，文案随语言切换 */
const difficultyOptions = computed<Array<{ label: string; value: Difficulty }>>(() => [
  { label: t('article.difficulty.1'), value: '1' },
  { label: t('article.difficulty.2'), value: '2' },
  { label: t('article.difficulty.3'), value: '3' },
  { label: t('article.difficulty.4'), value: '4' },
  { label: t('article.difficulty.5'), value: '5' }
])

/** 四六级真题选项：空 = 非真题 */
const cetTypeOptions = computed<Array<{ label: string; value: string }>>(() => [
  { label: t('article.cet.none'), value: '' },
  { label: t('article.cet.cet4'), value: 'cet4' },
  { label: t('article.cet.cet6'), value: 'cet6' }
])

/** 正文词数：按空白拆分自动统计 */
const wordCount = computed(() => {
  const text = model.content.trim()
  if (!text) return 0
  return text.split(/\s+/).filter(Boolean).length
})

/** 校验规则：仅 title / content 必填，文案随语言响应式更新 */
const rules = computed<FormRules>(() => ({
  title: [
    {
      required: true,
      message: t('admin.article.validation.titleRequired'),
      trigger: ['blur', 'input']
    }
  ],
  content: [
    {
      required: true,
      message: t('admin.article.validation.contentRequired'),
      trigger: ['blur', 'input']
    }
  ]
}))

// ============================================================
//  数据加载（编辑模式）
// ============================================================

/** 编辑模式下拉取文章详情并回填表单 */
async function fetchArticle(): Promise<void> {
  const id = articleId.value
  if (id === null) return
  fetching.value = true
  try {
    const article: Article = await adminApi.getArticle(id)
    model.title = article.title
    model.content = article.content
    model.summary = article.summary ?? ''
    model.source = article.source ?? ''
    model.difficulty = article.difficulty
    model.cet_type = article.cet_type ?? ''
    model.tags = article.tags ?? []
    model.reading_time = article.reading_time
    model.cover_url = article.cover_url ?? ''
    model.is_published = article.is_published
  } catch {
    // 错误由 axios 响应拦截器统一提示，此处静默恢复
  } finally {
    fetching.value = false
  }
}

// ============================================================
//  保存
// ============================================================

/**
 * 组装请求体。
 * 空字符串 / 空数组 / null 转为 undefined，避免向后端写入无意义空值。
 */
function buildPayload(): AdminArticleCreatePayload {
  return {
    title: model.title,
    content: model.content,
    difficulty: model.difficulty,
    cet_type: model.cet_type === '' ? null : (model.cet_type as CetType),
    summary: model.summary || undefined,
    source: model.source || undefined,
    tags: model.tags.length ? model.tags : undefined,
    cover_url: model.cover_url || undefined,
    reading_time: model.reading_time ?? undefined,
    is_published: model.is_published
  }
}

/** 提交：先做表单校验，通过后按模式调用创建 / 更新接口 */
async function handleSubmit(): Promise<void> {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const data = buildPayload()
    if (isEdit.value && articleId.value !== null) {
      // AdminArticleCreatePayload 字段是 AdminArticleUpdatePayload 的超集，可直接赋值
      const updateData: AdminArticleUpdatePayload = data
      await adminApi.updateArticle(articleId.value, updateData)
      message.success(t('admin.article.updated'))
    } else {
      await adminApi.createArticle(data)
      message.success(t('admin.article.created'))
    }
    router.push('/admin/articles')
  } catch {
    // 错误由拦截器统一提示，此处仅恢复 loading
  } finally {
    saving.value = false
  }
}

/** 取消：返回文章列表 */
function handleCancel(): void {
  router.push('/admin/articles')
}

// ============================================================
//  生命周期
// ============================================================

onMounted(() => {
  if (isEdit.value) fetchArticle()
})
</script>

<template>
  <div class="space-y-8">
    <!-- 页头 -->
    <header class="space-y-2">
      <h1
        class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl"
      >
        {{ pageTitle }}
      </h1>
    </header>

    <!-- 表单区（左侧，最大宽度 max-w-3xl） -->
    <div class="max-w-3xl">
      <NSpin :show="fetching">
        <NForm
          ref="formRef"
          :model="model"
          :rules="rules"
          label-placement="top"
          :show-require-mark="false"
        >
          <!-- 标题 -->
          <NFormItem :label="t('admin.article.fields.title')" path="title">
            <NInput
              v-model:value="model.title"
              clearable
            />
          </NFormItem>

          <!-- 正文 -->
          <NFormItem :label="t('admin.article.fields.content')" path="content">
            <NInput
              v-model:value="model.content"
              type="textarea"
              :rows="15"
            />
          </NFormItem>

          <!-- 词数提示（基于正文自动统计） -->
          <div class="-mt-2 mb-6 flex items-center justify-between px-1">
            <span class="text-xs text-neutral-400 dark:text-neutral-500">
              {{ t('admin.article.autoWordCount') }}
            </span>
            <span
              class="text-xs font-medium tabular-nums text-neutral-500 dark:text-neutral-400"
            >
              {{ wordCount }} {{ t('article.wordCount') }}
            </span>
          </div>

          <!-- 摘要 -->
          <NFormItem :label="t('admin.article.fields.summary')" path="summary">
            <NInput
              v-model:value="model.summary"
              type="textarea"
              :rows="3"
            />
          </NFormItem>

          <!-- 难度 + 四六级 + 阅读时长（三列） -->
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <NFormItem :label="t('admin.article.fields.difficulty')" path="difficulty">
              <NSelect
                v-model:value="model.difficulty"
                :options="difficultyOptions"
              />
            </NFormItem>
            <NFormItem :label="t('admin.article.fields.cetType')" path="cet_type">
              <NSelect
                v-model:value="model.cet_type"
                :options="cetTypeOptions"
              />
            </NFormItem>
            <NFormItem :label="t('admin.article.fields.readingTime')" path="reading_time">
              <NInputNumber
                v-model:value="model.reading_time"
                :min="0"
                class="w-full"
              />
            </NFormItem>
          </div>

          <!-- 来源 -->
          <NFormItem :label="t('admin.article.fields.source')" path="source">
            <NInput
              v-model:value="model.source"
              clearable
            />
          </NFormItem>

          <!-- 封面图 URL -->
          <NFormItem :label="t('admin.article.fields.coverUrl')" path="cover_url">
            <NInput
              v-model:value="model.cover_url"
              clearable
            />
          </NFormItem>

          <!-- 标签 -->
          <NFormItem :label="t('admin.article.fields.tags')" path="tags">
            <NDynamicTags v-model:value="model.tags" />
          </NFormItem>

          <!-- 发布状态 -->
          <NFormItem :label="t('admin.article.fields.isPublished')" path="is_published">
            <NSwitch v-model:value="model.is_published" />
          </NFormItem>

          <!-- 操作区 -->
          <div class="flex gap-3 pt-2">
            <NButton
              type="primary"
              :loading="saving"
              @click="handleSubmit"
            >
              {{ t('admin.article.save') }}
            </NButton>
            <NButton @click="handleCancel">
              {{ t('admin.article.cancel') }}
            </NButton>
          </div>
        </NForm>
      </NSpin>
    </div>
  </div>
</template>
