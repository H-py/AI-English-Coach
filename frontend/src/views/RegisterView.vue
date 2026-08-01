<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  NForm,
  NFormItem,
  NInput,
  NButton,
  type FormInst,
  type FormItemRule,
  type FormRules
} from 'naive-ui'
import { useAuth } from '@/composables/useAuth'
import type { RegisterPayload } from '@/types/auth'

/**
 * 注册页。
 * 极简卡片式表单：用户名 + 邮箱 + 密码 + 确认密码，提交后调用 useAuth().register。
 * 错误提示由 axios 响应拦截器统一处理，这里仅负责表单校验与 loading 状态。
 */
const { t } = useI18n()
const router = useRouter()
const { register } = useAuth()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)

interface RegisterFormModel extends RegisterPayload {
  confirmPassword: string
}

const model = reactive<RegisterFormModel>({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

// 校验规则：文案随语言切换响应式更新
const rules = computed<FormRules>(() => {
  // 确认密码自定义校验：必须与密码一致
  const confirmPasswordValidator: FormItemRule['validator'] = (_rule, value) => {
    if (!value) {
      return new Error(t('auth.validation.confirmPasswordRequired'))
    }
    if (value !== model.password) {
      return new Error(t('auth.validation.passwordMismatch'))
    }
    return true
  }

  return {
    username: [
      {
        required: true,
        message: t('auth.validation.usernameRequired'),
        trigger: ['blur', 'input']
      },
      {
        min: 2,
        max: 50,
        message: t('auth.validation.usernameLength'),
        trigger: ['blur', 'input']
      }
    ],
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
      },
      {
        min: 6,
        max: 128,
        message: t('auth.validation.passwordLength'),
        trigger: ['blur', 'input']
      }
    ],
    confirmPassword: [
      {
        required: true,
        validator: confirmPasswordValidator,
        trigger: ['blur', 'input']
      }
    ]
  }
})

// 同时作为按钮 click（MouseEvent）与回车 keyup（KeyboardEvent）的处理器，
// 故取公共基类 Event（二者均支持 preventDefault）。
async function handleSubmit(e: Event): Promise<void> {
  e.preventDefault()
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    // 仅提交后端需要的字段，不含 confirmPassword
    const { username, email, password } = model
    await register({ username, email, password })
  } catch {
    // 错误已由拦截器统一提示，此处仅恢复 loading
  } finally {
    loading.value = false
  }
}

function goLogin(): void {
  router.push('/login')
}
</script>

<template>
  <div class="space-y-6">
    <!-- 标题区 -->
    <div class="space-y-1 text-center">
      <h1 class="text-xl font-semibold text-neutral-900 dark:text-neutral-50">
        {{ t('auth.createAccount') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400">
        {{ t('auth.registerSubtitle') }}
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
      <NFormItem :label="t('auth.username')" path="username">
        <NInput
          v-model:value="model.username"
          :placeholder="t('auth.usernamePlaceholder')"
          :input-props="{ autocomplete: 'username' }"
          clearable
        />
      </NFormItem>

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
          :input-props="{ autocomplete: 'new-password' }"
        />
      </NFormItem>

      <NFormItem :label="t('auth.confirmPassword')" path="confirmPassword">
        <NInput
          v-model:value="model.confirmPassword"
          type="password"
          show-password-on="click"
          :placeholder="t('auth.confirmPasswordPlaceholder')"
          :input-props="{ autocomplete: 'new-password' }"
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
        {{ t('auth.registerBtn') }}
      </NButton>
    </NForm>

    <!-- 底部跳转登录 -->
    <p class="text-center text-sm text-neutral-500 dark:text-neutral-400">
      {{ t('auth.hasAccount') }}
      <button
        type="button"
        class="font-medium text-neutral-900 transition-colors hover:text-neutral-600 dark:text-neutral-100 dark:hover:text-neutral-300"
        @click="goLogin"
      >
        {{ t('auth.goLogin') }}
      </button>
    </p>
  </div>
</template>
