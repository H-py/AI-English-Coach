<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NSelect,
  NSpin,
  NTag,
  useMessage,
  type FormInst,
  type FormRules
} from 'naive-ui'
import { llmConfigApi } from '@/api/llmConfig'
import type {
  LlmConfigCreatePayload,
  LlmConfigTestPayload,
  LlmConfigUpdatePayload,
  LlmProviderPreset,
  UserLlmConfig
} from '@/types/llmConfig'

/**
 * 模型配置页（多模型管理）。
 *
 * 允许用户配置多个 OpenAI 兼容大模型服务，并选择其中一个作为当前使用的
 * 模型；未激活任何配置时使用默认模型。每个模型可独立测试连通性、编辑、
 * 删除。若配置有问题（API Key 无效、Base URL 不可达、模型名错误），后端
 * 会返回指明具体原因的友好错误，页面透出，绝不静默回退到默认模型。
 */

const { t } = useI18n()
const message = useMessage()

const loading = ref(false)
const configs = ref<UserLlmConfig[]>([])
const activeId = ref<number | null>(null)

// ============================================================
//  服务商预设
// ============================================================

const PRESETS: Record<string, LlmProviderPreset> = {
  deepseek: { key: 'deepseek', name: 'DeepSeek', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  openai: { key: 'openai', name: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  ollama: { key: 'ollama', name: 'Ollama', baseUrl: 'http://localhost:11434/v1', model: 'llama3' },
  custom: { key: 'custom', name: '', baseUrl: '', model: '' }
}

const providerOptions = computed(() => [
  { label: t('modelConfig.deepseek'), value: 'deepseek' },
  { label: t('modelConfig.openai'), value: 'openai' },
  { label: t('modelConfig.ollama'), value: 'ollama' },
  { label: t('modelConfig.custom'), value: 'custom' }
])

/** 选择预设时填充服务商名称、Base URL 与模型名（均仍可手动修改） */
function handlePresetChange(value: string | number | null): void {
  const key = String(value ?? 'custom') as LlmProviderPreset['key']
  selectedProvider.value = key
  const preset = PRESETS[key]
  if (preset && key !== 'custom') {
    form.provider_name = preset.name
    form.base_url = preset.baseUrl
    form.model = preset.model
  }
}

/** 根据已存的 Base URL + 模型名识别对应预设，未匹配则视为自定义 */
function detectPreset(baseUrl: string, modelName: string): LlmProviderPreset['key'] {
  const hit = Object.entries(PRESETS).find(
    ([key, p]) => key !== 'custom' && p.baseUrl === baseUrl && p.model === modelName
  )
  return (hit?.[0] as LlmProviderPreset['key']) ?? 'custom'
}

// ============================================================
//  新增 / 编辑弹窗
// ============================================================

const showModal = ref(false)
const editingId = ref<number | null>(null)
const editingMaskedKey = ref('')
const saving = ref(false)
const testing = ref(false)
const formRef = ref<FormInst | null>(null)
const form = reactive({
  provider_name: '',
  base_url: '',
  model: '',
  api_key: ''
})
const selectedProvider = ref<LlmProviderPreset['key']>('custom')

function openCreate(): void {
  editingId.value = null
  editingMaskedKey.value = ''
  form.provider_name = ''
  form.base_url = ''
  form.model = ''
  form.api_key = ''
  selectedProvider.value = 'custom'
  showModal.value = true
}

function openEdit(config: UserLlmConfig): void {
  editingId.value = config.id
  editingMaskedKey.value = config.masked_api_key
  form.provider_name = config.provider_name
  form.base_url = config.base_url
  form.model = config.model
  form.api_key = ''
  selectedProvider.value = detectPreset(config.base_url, config.model)
  showModal.value = true
}

const rules = computed<FormRules>(() => ({
  provider_name: [
    {
      validator: (_rule, value: string) => {
        if (selectedProvider.value === 'custom' && !(value ?? '').trim()) {
          return new Error(t('modelConfig.validation.providerNameRequired'))
        }
        return true
      },
      trigger: ['blur', 'input']
    }
  ],
  base_url: [
    {
      validator: (_rule, value: string) => {
        const v = (value ?? '').trim()
        if (!v) return new Error(t('modelConfig.validation.baseUrlRequired'))
        if (!/^https?:\/\//.test(v)) {
          return new Error(t('modelConfig.validation.baseUrlInvalid'))
        }
        return true
      },
      trigger: ['blur', 'input']
    }
  ],
  model: [
    {
      required: true,
      message: t('modelConfig.validation.modelRequired'),
      trigger: ['blur', 'input']
    }
  ],
  api_key: [
    {
      validator: (_rule, value: string) => {
        // 新增时必须填写 API Key；编辑时留空表示保留原值
        if (editingId.value === null && !(value ?? '').trim()) {
          return new Error(t('modelConfig.validation.apiKeyRequired'))
        }
        return true
      },
      trigger: ['blur', 'input']
    }
  ]
}))

async function handleSave(): Promise<void> {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    if (editingId.value === null) {
      const payload: LlmConfigCreatePayload = {
        provider_name: form.provider_name.trim(),
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        api_key: form.api_key.trim()
      }
      await llmConfigApi.createConfig(payload)
      message.success(t('modelConfig.created'))
    } else {
      const payload: LlmConfigUpdatePayload = {
        provider_name: form.provider_name.trim(),
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        api_key: form.api_key.trim() || undefined
      }
      await llmConfigApi.updateConfig(editingId.value, payload)
      message.success(t('modelConfig.saved'))
    }
    showModal.value = false
    await fetchConfigs()
  } catch {
    // 错误由拦截器统一提示
  } finally {
    saving.value = false
  }
}

/** 弹窗内测试尚未保存的表单值 */
async function handleModalTest(): Promise<void> {
  testing.value = true
  const payload: LlmConfigTestPayload = {
    base_url: form.base_url.trim() || undefined,
    model: form.model.trim() || undefined,
    api_key: form.api_key.trim() || undefined
  }
  try {
    await llmConfigApi.testConfig(payload)
    message.success(t('modelConfig.testSuccess'))
  } catch {
    // 错误由拦截器统一提示
  } finally {
    testing.value = false
  }
}

// ============================================================
//  列表操作
// ============================================================

const testingId = ref<number | null>(null)

async function handleActivate(config: UserLlmConfig): Promise<void> {
  await llmConfigApi.activateConfig(config.id)
  message.success(t('modelConfig.activated'))
  await fetchConfigs()
}

async function handleDeactivate(): Promise<void> {
  await llmConfigApi.deactivateAll()
  message.success(t('modelConfig.deactivated'))
  await fetchConfigs()
}

async function handleTest(config: UserLlmConfig): Promise<void> {
  testingId.value = config.id
  try {
    await llmConfigApi.testConfig({ config_id: config.id })
    message.success(t('modelConfig.testSuccess'))
  } catch {
    // 错误由拦截器统一提示
  } finally {
    testingId.value = null
  }
}

async function handleDelete(config: UserLlmConfig): Promise<void> {
  await llmConfigApi.deleteConfig(config.id)
  message.success(t('modelConfig.deleted'))
  await fetchConfigs()
}

// ============================================================
//  状态提示
// ============================================================

const statusText = computed(() => {
  if (activeId.value === null) return t('modelConfig.statusUsingDefault')
  const active = configs.value.find((c) => c.id === activeId.value)
  const name = active?.provider_name?.trim() || t('modelConfig.custom')
  return t('modelConfig.statusUsingModel', { name })
})

// ============================================================
//  数据加载
// ============================================================

async function fetchConfigs(): Promise<void> {
  loading.value = true
  try {
    const res = await llmConfigApi.listConfigs()
    configs.value = res.items
    activeId.value = res.active_id
  } catch {
    // 错误由 axios 拦截器统一提示，此处静默恢复
  } finally {
    loading.value = false
  }
}

onMounted(fetchConfigs)
</script>

<template>
  <div class="space-y-8">
    <!-- 页头 -->
    <header class="space-y-2">
      <h1
        class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl"
      >
        {{ t('modelConfig.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('modelConfig.subtitle') }}
      </p>
    </header>

    <!-- 状态提示 -->
    <section
      class="rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
    >
      <p class="text-sm text-neutral-600 dark:text-neutral-300">
        {{ t('modelConfig.currentStatus', { status: statusText }) }}
      </p>
      <p v-if="!configs.length" class="mt-1 text-xs text-neutral-400">
        {{ t('modelConfig.noConfig') }}
      </p>
    </section>

    <NSpin :show="loading">
      <!-- 工具栏：标题 + 新增按钮 -->
      <div class="mb-4 flex items-center justify-between">
        <h2
          class="text-sm font-medium uppercase tracking-wider text-neutral-400"
        >
          {{ t('modelConfig.modelsTitle') }}
        </h2>
        <NButton type="primary" @click="openCreate">
          <template #icon>
            <svg
              class="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M12 5v14 M5 12h14" />
            </svg>
          </template>
          {{ t('modelConfig.addModel') }}
        </NButton>
      </div>

      <!-- 空列表 -->
      <div
        v-if="!configs.length && !loading"
        class="rounded-xl border border-dashed border-neutral-300 py-16 text-center dark:border-neutral-700"
      >
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ t('modelConfig.emptyList') }}</p>
        <p class="mt-1 text-xs text-neutral-400">{{ t('modelConfig.emptyListHint') }}</p>
      </div>

      <!-- 模型列表 -->
      <div v-else class="space-y-4">
        <section
          v-for="config in configs"
          :key="config.id"
          class="rounded-xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900"
        >
          <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <h3
                  class="truncate text-base font-semibold text-neutral-900 dark:text-neutral-50"
                >
                  {{ config.provider_name || t('modelConfig.custom') }}
                </h3>
                <NTag v-if="config.id === activeId" size="small" type="success" :bordered="false">
                  {{ t('modelConfig.activeBadge') }}
                </NTag>
              </div>
              <dl class="mt-2 space-y-1 text-xs text-neutral-500 dark:text-neutral-400">
                <div class="flex gap-2">
                  <dt class="w-20 flex-shrink-0 text-neutral-400">{{ t('modelConfig.baseUrl') }}</dt>
                  <dd class="min-w-0 break-all">{{ config.base_url }}</dd>
                </div>
                <div class="flex gap-2">
                  <dt class="w-20 flex-shrink-0 text-neutral-400">{{ t('modelConfig.model') }}</dt>
                  <dd>{{ config.model }}</dd>
                </div>
                <div class="flex gap-2">
                  <dt class="w-20 flex-shrink-0 text-neutral-400">{{ t('modelConfig.apiKey') }}</dt>
                  <dd>{{ config.masked_api_key || '—' }}</dd>
                </div>
              </dl>
            </div>

            <!-- 操作 -->
            <div class="flex flex-shrink-0 flex-wrap items-center gap-2">
              <template v-if="config.id === activeId">
                <NPopconfirm @positive-click="handleDeactivate">
                  <template #trigger>
                    <NButton size="small" tertiary>{{ t('modelConfig.stopUsing') }}</NButton>
                  </template>
                  {{ t('modelConfig.stopUsingConfirm') }}
                </NPopconfirm>
              </template>
              <NButton
                v-else
                size="small"
                type="primary"
                ghost
                @click="handleActivate(config)"
              >
                {{ t('modelConfig.useThis') }}
              </NButton>
              <NButton size="small" :loading="testingId === config.id" @click="handleTest(config)">
                {{ t('modelConfig.test') }}
              </NButton>
              <NButton size="small" @click="openEdit(config)">
                {{ t('modelConfig.edit') }}
              </NButton>
              <NPopconfirm @positive-click="handleDelete(config)">
                <template #trigger>
                  <NButton size="small" type="error" tertiary>{{ t('modelConfig.delete') }}</NButton>
                </template>
                {{ t('modelConfig.deleteConfirm') }}
              </NPopconfirm>
            </div>
          </div>
        </section>
      </div>
    </NSpin>

    <!-- 新增 / 编辑弹窗 -->
    <NModal
      v-model:show="showModal"
      preset="card"
      :title="editingId === null ? t('modelConfig.addTitle') : t('modelConfig.editTitle')"
      style="width: 560px; max-width: 92vw"
    >
      <NForm
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        :show-require-mark="false"
      >
        <NFormItem :label="t('modelConfig.provider')" path="provider">
          <NSelect
            :value="selectedProvider"
            :options="providerOptions"
            :placeholder="t('modelConfig.providerPlaceholder')"
            @update:value="handlePresetChange"
          />
        </NFormItem>
        <NFormItem :label="t('modelConfig.providerName')" path="provider_name">
          <NInput
            v-model:value="form.provider_name"
            :placeholder="t('modelConfig.providerNamePlaceholder')"
            clearable
          />
        </NFormItem>
        <NFormItem :label="t('modelConfig.baseUrl')" path="base_url">
          <NInput
            v-model:value="form.base_url"
            :placeholder="t('modelConfig.baseUrlPlaceholder')"
            clearable
          />
        </NFormItem>
        <NFormItem :label="t('modelConfig.model')" path="model">
          <NInput
            v-model:value="form.model"
            :placeholder="t('modelConfig.modelPlaceholder')"
            clearable
          />
        </NFormItem>
        <NFormItem :label="t('modelConfig.apiKey')" path="api_key">
          <NInput
            v-model:value="form.api_key"
            type="password"
            show-password-on="click"
            :placeholder="editingId !== null && editingMaskedKey ? editingMaskedKey : t('modelConfig.apiKeyPlaceholder')"
          />
        </NFormItem>
      </NForm>

      <template #footer>
        <div class="flex items-center justify-between">
          <NButton :loading="testing" @click="handleModalTest">
            {{ testing ? t('modelConfig.testing') : t('modelConfig.test') }}
          </NButton>
          <div class="flex gap-2">
            <NButton @click="showModal = false">{{ t('common.cancel') }}</NButton>
            <NButton type="primary" :loading="saving" @click="handleSave">
              {{ t('modelConfig.save') }}
            </NButton>
          </div>
        </div>
      </template>
    </NModal>
  </div>
</template>
