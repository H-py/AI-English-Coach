<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, type FormInst, type FormRules } from 'naive-ui'
import { useAuth } from '@/composables/useAuth'
import type { LoginPayload } from '@/types/auth'

/**
 * 登录页。
 * 极简卡片式表单：邮箱 + 密码，提交后调用 useAuth().login。
 * 错误提示由 axios 响应拦截器统一处理，这里仅负责表单校验与 loading 状态。
 */
const { t } = useI18n()
const router = useRouter()
const { login } = useAuth()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)

const model = reactive<LoginPayload>({
  email: '',
  password: ''
})

// 校验规则：文案随语言切换响应式更新
const rules = computed<FormRules>(() => ({
  email: [
    {
      required: true,
      message: t('auth.validation.emailRequired'),
      trigger: ['blur', 'input']
    },
    {
      type: 'email',
      message: t('auth.validation.emailInvalid'),
      trigger: ['blur', 'input']
    }
  ],
  password: [
    {
      required: true,
      message: t('auth.validation.passwordRequired'),
      trigger: ['blur', 'input']
    }
  ]
}))

// 同时作为按钮 click（MouseEvent）与回车 keyup（KeyboardEvent）的处理器，
// 故取公共基类 Event（二者均支持 preventDefault）。
async function handleSubmit(e: Event): Promise<void> {
  e.preventDefault()
  // 先做表单校验，失败则不发起请求
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await login({ ...model })
  } catch {
    // 错误已由拦截器统一提示，此处仅恢复 loading
  } finally {
    loading.value = false
  }
}

function goRegister(): void {
  router.push('/register')
}
</script>

<template>
  <div class="space-y-6">
    <!-- 标题区 -->
    <div class="space-y-1 text-center">
      <h1 class="text-xl font-semibold text-neutral-900 dark:text-neutral-50">
        {{ t('auth.welcomeBack') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400">
        {{ t('auth.loginSubtitle') }}
      </p>
    </div>

    <!-- 表单 -->
    <NForm
      ref="formRef"
      :model="model"
      :rules="rules"
      label-placement="top"
      size="large"
      :show-require-mark="false"
    >
      <NFormItem :label="t('auth.email')" path="email">
        <NInput
          v-model:value="model.email"
          :placeholder="t('auth.emailPlaceholder')"
          :input-props="{ autocomplete: 'email', type: 'email' }"
          clearable
        />
      </NFormItem>

      <NFormItem :label="t('auth.password')" path="password">
        <NInput
          v-model:value="model.password"
          type="password"
          show-password-on="click"
          :placeholder="t('auth.passwordPlaceholder')"
          :input-props="{ autocomplete: 'current-password' }"
          @keyup.enter="handleSubmit"
        />
      </NFormItem>

      <NButton
        type="primary"
        block
        attr-type="submit"
        :loading="loading"
        @click="handleSubmit"
      >
        {{ t('auth.loginBtn') }}
      </NButton>
    </NForm>

    <!-- 底部跳转注册 -->
    <p class="text-center text-sm text-neutral-500 dark:text-neutral-400">
      {{ t('auth.noAccount') }}
      <button
        type="button"
        class="font-medium text-neutral-900 transition-colors hover:text-neutral-600 dark:text-neutral-100 dark:hover:text-neutral-300"
        @click="goRegister"
      >
        {{ t('auth.goRegister') }}
      </button>
    </p>
  </div>
</template>
