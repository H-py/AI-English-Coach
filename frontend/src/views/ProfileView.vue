<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  useMessage,
  type FormInst,
  type FormRules
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { readingApi } from '@/api/reading'
import { useAuth } from '@/composables/useAuth'
import type { EnglishLevel } from '@/types/auth'

/**
 * 个人中心 / 设置页。
 *
 * 展示当前登录用户的基本信息（用户名、邮箱、头像、注册时间、最近登录时间）
 * 与学习概览统计，并支持切换英语水平。头像 / 用户名 / 密码的修改收拢在
 * 「修改个人信息」弹窗中，以三个页签分别编辑：
 *  - 头像：选择图片上传到 MinIO；
 *  - 用户名：修改显示名（唯一性由后端校验）；
 *  - 密码：需验证旧密码。
 *
 * 数据在 onMounted 时并行拉取；错误提示由 axios 响应拦截器统一处理。
 */

const { t } = useI18n()
const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()
const { logout } = useAuth()

// ============================================================
//  用户信息
// ============================================================

const user = computed(() => authStore.user)

/** 头像回退：无 avatar_url 时取用户名首字母大写 */
const userInitial = computed(() => user.value?.username?.charAt(0).toUpperCase() ?? '?')

// ============================================================
//  时间格式化
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
//  修改个人信息弹窗
// ============================================================

const showEditModal = ref(false)
const activeTab = ref('avatar')

/** 打开弹窗：回填用户名、清空密码表单 */
function openEditModal(): void {
  username.value = user.value?.username ?? ''
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
  activeTab.value = 'avatar'
  showEditModal.value = true
}

// ============================================================
//  头像上传（弹窗内）
// ============================================================

const avatarUploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

/** 点击「选择图片」：触发隐藏的 file input */
function triggerAvatarUpload(): void {
  fileInputRef.value?.click()
}

/** 选择文件后上传头像 */
async function handleAvatarChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  avatarUploading.value = true
  try {
    const updated = await authApi.uploadAvatar(file)
    authStore.setUser(updated)
    message.success(t('profile.avatarUpdated'))
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    avatarUploading.value = false
    // 清空 input，允许连续选择同一文件
    input.value = ''
  }
}

// ============================================================
//  用户名编辑（弹窗内）
// ============================================================

const username = ref('')
const usernameSaving = ref(false)

/** 保存用户名 */
async function handleSaveUsername(): Promise<void> {
  const value = username.value.trim()
  if (!value) {
    message.error(t('auth.validation.usernameRequired'))
    return
  }
  if (value === user.value?.username) {
    message.success(t('profile.usernameUpdated'))
    return
  }
  usernameSaving.value = true
  try {
    const updated = await authApi.updateMe({ username: value })
    authStore.setUser(updated)
    username.value = updated.username
    message.success(t('profile.usernameUpdated'))
  } catch {
    // 错误由 axios 拦截器统一提示（如用户名已被占用）
  } finally {
    usernameSaving.value = false
  }
}

// ============================================================
//  英语水平选择
// ============================================================

const levelOptions = computed(() => [
  { label: t('profile.levelOptions.beginner'), value: 'beginner' },
  { label: t('profile.levelOptions.intermediate'), value: 'intermediate' },
  { label: t('profile.levelOptions.advanced'), value: 'advanced' }
])

const selectedLevel = ref<EnglishLevel>(user.value?.english_level ?? 'beginner')
const levelUpdating = ref(false)

/**
 * 切换英语水平：
 *  乐观更新选中值 -> 调用 authApi.updateMe -> 同步 auth store；
 *  失败时回退到 store 中的当前水平。
 */
async function handleLevelChange(value: string | number): Promise<void> {
  const level = value as EnglishLevel
  selectedLevel.value = level
  levelUpdating.value = true
  try {
    const updated = await authApi.updateMe({ english_level: level })
    authStore.setUser(updated)
    selectedLevel.value = updated.english_level
    message.success(t('profile.levelUpdated'))
  } catch {
    selectedLevel.value = user.value?.english_level ?? 'beginner'
  } finally {
    levelUpdating.value = false
  }
}

// ============================================================
//  修改密码（弹窗内）
// ============================================================

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})
const passwordSubmitting = ref(false)
const passwordFormRef = ref<FormInst | null>(null)

const passwordRules = computed<FormRules>(() => ({
  old_password: [
    { required: true, message: t('profile.validation.oldPasswordRequired'), trigger: ['blur', 'input'] }
  ],
  new_password: [
    { required: true, message: t('profile.validation.newPasswordRequired'), trigger: ['blur', 'input'] },
    {
      validator: (_rule, value: string) => {
        if (!value) return true
        if (value.length < 6 || value.length > 128) {
          return new Error(t('profile.validation.newPasswordLength'))
        }
        return true
      },
      trigger: ['blur', 'input']
    }
  ],
  confirm_password: [
    { required: true, message: t('profile.validation.confirmPasswordRequired'), trigger: ['blur', 'input'] },
    {
      validator: (_rule, value: string) => {
        if (value && value !== passwordForm.new_password) {
          return new Error(t('profile.validation.passwordMismatch'))
        }
        return true
      },
      trigger: ['blur', 'input']
    }
  ]
}))

/** 提交修改密码 */
async function handleChangePassword(): Promise<void> {
  try {
    await passwordFormRef.value?.validate()
  } catch {
    return
  }
  passwordSubmitting.value = true
  try {
    await authApi.updatePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password
    })
    message.success(t('profile.passwordUpdated'))
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
  } catch {
    // 错误由 axios 拦截器统一提示（如旧密码错误）
  } finally {
    passwordSubmitting.value = false
  }
}

// ============================================================
//  学习概览统计
// ============================================================

interface StatItem {
  labelKey: string
  value: number
  icon: string
  iconBgClass: string
  iconTextClass: string
  route: string
}

const ICONS = {
  bookmark: 'm19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z',
  messageSquare: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  history:
    'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2',
  bookOpen:
    'M12 7v14 M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z'
} as const

const statsLoading = ref(false)
const stats = ref<StatItem[]>([
  {
    labelKey: 'profile.wordsCollected',
    value: 0,
    icon: ICONS.bookmark,
    iconBgClass: 'bg-blue-50 dark:bg-blue-500/10',
    iconTextClass: 'text-blue-500 dark:text-blue-400',
    route: '/vocabulary'
  },
  {
    labelKey: 'profile.sentencesCollected',
    value: 0,
    icon: ICONS.messageSquare,
    iconBgClass: 'bg-emerald-50 dark:bg-emerald-500/10',
    iconTextClass: 'text-emerald-500 dark:text-emerald-400',
    route: '/sentences'
  },
  {
    labelKey: 'profile.readingSessions',
    value: 0,
    icon: ICONS.history,
    iconBgClass: 'bg-amber-50 dark:bg-amber-500/10',
    iconTextClass: 'text-amber-500 dark:text-amber-400',
    route: '/history'
  },
  {
    labelKey: 'profile.articlesRead',
    value: 0,
    icon: ICONS.bookOpen,
    iconBgClass: 'bg-violet-50 dark:bg-violet-500/10',
    iconTextClass: 'text-violet-500 dark:text-violet-400',
    route: '/articles'
  }
])

/** 并行拉取统计数据，单项失败不影响其余展示 */
async function fetchStats(): Promise<void> {
  statsLoading.value = true
  try {
    const [wordsRes, sentencesRes, historyRes] = await Promise.allSettled([
      readingApi.listWords({ page: 1, page_size: 1 }),
      readingApi.listSentences({ page: 1, page_size: 1 }),
      readingApi.listHistory({ page: 1, page_size: 100 })
    ])

    if (wordsRes.status === 'fulfilled') {
      stats.value[0].value = wordsRes.value.total
    }
    if (sentencesRes.status === 'fulfilled') {
      stats.value[1].value = sentencesRes.value.total
    }
    if (historyRes.status === 'fulfilled') {
      stats.value[2].value = historyRes.value.total
      const articleIds = new Set(historyRes.value.items.map((h) => h.article_id))
      stats.value[3].value = articleIds.size
    }
  } finally {
    statsLoading.value = false
  }
}

// ============================================================
//  登出
// ============================================================

async function handleLogout(): Promise<void> {
  await logout()
}

// ============================================================
//  生命周期
// ============================================================

onMounted(() => {
  // 防御性自检：若用户信息缺失（如会话异常），回登录页
  if (!authStore.user) {
    router.push('/login')
    return
  }
  username.value = authStore.user.username
  selectedLevel.value = authStore.user.english_level
  fetchStats()
})
</script>

<template>
  <div class="space-y-8">
    <!-- 页头 -->
    <header class="space-y-2">
      <h1
        class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl"
      >
        {{ t('profile.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('profile.subtitle') }}
      </p>
    </header>

    <!-- 用户信息卡片 -->
    <section
      v-if="user"
      class="rounded-xl border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900"
    >
      <!-- 头像 + 用户名 + 修改按钮 -->
      <div class="flex items-center gap-4">
        <!-- 头像（仅展示） -->
        <img
          v-if="user.avatar_url"
          :src="user.avatar_url"
          :alt="t('profile.avatar')"
          class="h-16 w-16 flex-shrink-0 rounded-full object-cover"
        />
        <div
          v-else
          class="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-full bg-blue-100 text-xl font-bold text-blue-600 dark:bg-blue-500/20 dark:text-blue-400"
        >
          {{ userInitial }}
        </div>

        <!-- 用户名 -->
        <div class="min-w-0 flex-1">
          <h2
            class="truncate text-2xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50"
          >
            {{ user.username }}
          </h2>
          <p class="mt-0.5 text-sm text-neutral-400">{{ user.email }}</p>
        </div>

        <!-- 修改个人信息按钮 -->
        <NButton type="primary" ghost @click="openEditModal">
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
              <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
              <path d="m15 5 4 4" />
            </svg>
          </template>
          {{ t('profile.editInfo') }}
        </NButton>
      </div>

      <!-- 信息行 -->
      <div class="mt-6 space-y-3 border-t border-neutral-100 pt-6 dark:border-neutral-800">
        <div class="flex items-center justify-between gap-4">
          <span class="text-sm text-neutral-400">{{ t('profile.memberSince') }}</span>
          <span class="text-sm text-neutral-900 dark:text-neutral-100">
            {{ formatDateTime(user.created_at) }}
          </span>
        </div>
        <div class="flex items-center justify-between gap-4">
          <span class="text-sm text-neutral-400">{{ t('profile.lastLogin') }}</span>
          <span
            v-if="user.last_login_at"
            class="text-sm text-neutral-900 dark:text-neutral-100"
          >
            {{ formatDateTime(user.last_login_at) }}
          </span>
          <span v-else class="text-sm text-neutral-400">—</span>
        </div>
      </div>

      <!-- 英语水平选择 -->
      <div class="mt-6 border-t border-neutral-100 pt-6 dark:border-neutral-800">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span class="text-sm text-neutral-400">{{ t('profile.englishLevel') }}</span>
          <NSelect
            :value="selectedLevel"
            :options="levelOptions"
            :loading="levelUpdating"
            class="w-full sm:w-48"
            @update:value="handleLevelChange"
          />
        </div>
      </div>
    </section>

    <!-- 学习概览统计 -->
    <section class="space-y-4">
      <h2 class="text-sm font-medium uppercase tracking-wider text-neutral-400">
        {{ t('profile.statsTitle') }}
      </h2>

      <NSpin :show="statsLoading">
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div
            v-for="stat in stats"
            :key="stat.labelKey"
            class="stat-card cursor-pointer rounded-xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900"
            @click="router.push(stat.route)"
          >
            <div class="flex items-center gap-4">
              <span
                class="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg"
                :class="stat.iconBgClass"
              >
                <svg
                  class="h-5 w-5"
                  :class="stat.iconTextClass"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path :d="stat.icon" />
                </svg>
              </span>
              <div class="min-w-0">
                <p
                  class="text-3xl font-bold tabular-nums text-neutral-900 dark:text-neutral-50"
                >
                  {{ stat.value }}
                </p>
                <p class="truncate text-sm text-neutral-500 dark:text-neutral-400">
                  {{ t(stat.labelKey) }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </NSpin>
    </section>

    <!-- 登出 -->
    <div class="pt-2">
      <NButton size="large" type="error" tertiary @click="handleLogout">
        {{ t('auth.logout') }}
      </NButton>
    </div>

    <!-- 修改个人信息弹窗 -->
    <NModal
      v-model:show="showEditModal"
      preset="card"
      :title="t('profile.editInfo')"
      style="width: 480px; max-width: 92vw"
    >
      <NTabs v-model:value="activeTab" type="line" animated>
        <!-- 头像 -->
        <NTabPane name="avatar" :tab="t('profile.tabAvatar')">
          <div class="flex flex-col items-center gap-4 py-4">
            <div class="relative">
              <img
                v-if="user?.avatar_url"
                :src="user.avatar_url"
                :alt="t('profile.avatar')"
                class="h-24 w-24 rounded-full object-cover"
              />
              <div
                v-else
                class="flex h-24 w-24 items-center justify-center rounded-full bg-blue-100 text-3xl font-bold text-blue-600 dark:bg-blue-500/20 dark:text-blue-400"
              >
                {{ userInitial }}
              </div>
            </div>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              class="hidden"
              @change="handleAvatarChange"
            />
            <NButton :loading="avatarUploading" @click="triggerAvatarUpload">
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
                  <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
                  <path d="m18 8-1-1a2.828 2.828 0 1 0-4 4" />
                  <circle cx="9" cy="8" r="2" />
                  <path d="M3 3h18v18H3z" />
                </svg>
              </template>
              {{ t('profile.chooseImage') }}
            </NButton>
            <p class="text-xs text-neutral-400">{{ t('profile.avatarHint') }}</p>
          </div>
        </NTabPane>

        <!-- 用户名 -->
        <NTabPane name="username" :tab="t('profile.tabUsername')">
          <div class="space-y-4 py-4">
            <NFormItem :label="t('profile.username')" path="username">
              <NInput
                v-model:value="username"
                :maxlength="50"
                :placeholder="t('profile.usernamePlaceholder')"
              />
            </NFormItem>
            <NButton
              type="primary"
              :loading="usernameSaving"
              @click="handleSaveUsername"
            >
              {{ t('profile.save') }}
            </NButton>
          </div>
        </NTabPane>

        <!-- 密码 -->
        <NTabPane name="password" :tab="t('profile.tabPassword')">
          <NForm
            ref="passwordFormRef"
            :model="passwordForm"
            :rules="passwordRules"
            label-placement="top"
            :show-require-mark="false"
            class="py-4"
          >
            <NFormItem :label="t('profile.oldPassword')" path="old_password">
              <NInput
                v-model:value="passwordForm.old_password"
                type="password"
                show-password-on="click"
                :placeholder="t('profile.oldPasswordPlaceholder')"
              />
            </NFormItem>
            <NFormItem :label="t('profile.newPassword')" path="new_password">
              <NInput
                v-model:value="passwordForm.new_password"
                type="password"
                show-password-on="click"
                :placeholder="t('profile.newPasswordPlaceholder')"
              />
            </NFormItem>
            <NFormItem :label="t('auth.confirmPassword')" path="confirm_password">
              <NInput
                v-model:value="passwordForm.confirm_password"
                type="password"
                show-password-on="click"
                :placeholder="t('auth.confirmPasswordPlaceholder')"
              />
            </NFormItem>
            <NButton
              type="primary"
              :loading="passwordSubmitting"
              @click="handleChangePassword"
            >
              {{ t('profile.save') }}
            </NButton>
          </NForm>
        </NTabPane>
      </NTabs>
    </NModal>
  </div>
</template>

<style scoped>
.stat-card {
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.stat-card:hover {
  transform: translateY(-2px);
  border-color: #d4d4d4;
  box-shadow: 0 4px 16px -4px rgba(0, 0, 0, 0.08);
}
:global(html.dark) .stat-card:hover {
  border-color: #404040;
  box-shadow: 0 4px 16px -4px rgba(0, 0, 0, 0.4);
}
</style>
