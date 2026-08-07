<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDataTable,
  NInput,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NTag,
  NTooltip,
  useMessage,
  type DataTableColumns
} from 'naive-ui'
import { adminApi } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import type { AdminUser, AdminUserQuery } from '@/types/admin'
import type { UserRole } from '@/types/auth'

/**
 * 用户管理列表页（管理后台）。
 *
 * 功能：
 *  - 按邮箱 / 用户名搜索（输入防抖），按角色筛选（全部 / 普通用户 / 管理员）；
 *  - 表格展示用户信息，行操作支持启用/禁用、切换角色、删除（带二次确认）；
 *  - 删除对当前登录管理员自身禁用（自删保护），并以 NTooltip 提示原因；
 *  - 服务端分页，底部独立分页器。
 *
 * 所有接口错误由 axios 响应拦截器统一提示，组件内仅处理成功后的本地状态同步与轻提示。
 */
const { t } = useI18n()
const message = useMessage()
const authStore = useAuthStore()

// 当前登录用户 ID（用于自删保护）
const currentUserId = computed(() => authStore.user?.id)

// ============================================================
//  列表数据与查询状态
// ============================================================

const users = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(false)

const page = ref(1)
const pageSize = ref(10)

const searchQuery = ref('')
const roleFilter = ref<string>('all')

/** 角色筛选下拉选项：全部 / 普通用户 / 管理员 */
const roleOptions = computed(() => [
  { label: t('admin.user.allRoles'), value: 'all' },
  { label: t('admin.user.roleOptions.user'), value: 'user' },
  { label: t('admin.user.roleOptions.admin'), value: 'admin' }
])

/** 组装查询参数并拉取用户列表 */
async function fetchUsers(): Promise<void> {
  loading.value = true
  try {
    const query: AdminUserQuery = {
      search: searchQuery.value.trim() || undefined,
      role: roleFilter.value !== 'all' ? (roleFilter.value as UserRole) : undefined,
      page: page.value,
      page_size: pageSize.value
    }
    const res = await adminApi.listUsers(query)
    users.value = res.items
    total.value = res.total
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    loading.value = false
  }
}

/** 翻页：更新页码并重新加载 */
function handlePageChange(p: number): void {
  page.value = p
  fetchUsers()
}

// 搜索：输入防抖 300ms，触发后重置到第 1 页
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    fetchUsers()
  }, 300)
})

// 角色筛选变化：立即重置到第 1 页并重新加载
watch(roleFilter, () => {
  page.value = 1
  fetchUsers()
})

// ============================================================
//  行操作
// ============================================================

/** 当前进行中的行操作（用于按钮 loading / 互斥禁用） */
const action = ref<{ id: number; type: 'active' | 'role' | 'delete' } | null>(null)

/** 用接口返回值就地替换列表中对应用户，保证表格重渲染 */
function replaceUser(updated: AdminUser): void {
  users.value = users.value.map((u) => (u.id === updated.id ? updated : u))
}

/** 切换启用 / 禁用状态 */
async function handleToggleActive(row: AdminUser): Promise<void> {
  action.value = { id: row.id, type: 'active' }
  try {
    const updated = await adminApi.updateUser(row.id, { is_active: !row.is_active })
    replaceUser(updated)
    message.success(t('admin.user.updated'))
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    action.value = null
  }
}

/** 切换角色：admin <-> user */
async function handleToggleRole(row: AdminUser): Promise<void> {
  const newRole: UserRole = row.role === 'admin' ? 'user' : 'admin'
  action.value = { id: row.id, type: 'role' }
  try {
    const updated = await adminApi.updateUser(row.id, { role: newRole })
    replaceUser(updated)
    message.success(t('admin.user.updated'))
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    action.value = null
  }
}

/** 删除用户（已在 NPopconfirm 中二次确认） */
async function handleDelete(row: AdminUser): Promise<void> {
  action.value = { id: row.id, type: 'delete' }
  try {
    await adminApi.deleteUser(row.id)
    message.success(t('admin.user.deleted'))
    // 删除后若当前页只剩这一条且非第 1 页，回退一页再拉取
    if (users.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await fetchUsers()
  } catch {
    // 错误由 axios 拦截器统一提示
  } finally {
    action.value = null
  }
}

// ============================================================
//  日期格式化
// ============================================================

/** 格式化 ISO 时间字符串为本地日期 */
function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString()
}

// ============================================================
//  表格列定义（h() 渲染需要定制样式的列）
// ============================================================

/** 行 key */
function rowKey(row: AdminUser): number {
  return row.id
}

const columns = computed<DataTableColumns<AdminUser>>(() => [
  {
    title: t('admin.user.fields.id'),
    key: 'id',
    width: 70
  },
  {
    title: t('admin.user.fields.email'),
    key: 'email',
    minWidth: 200,
    ellipsis: { tooltip: true }
  },
  {
    title: t('admin.user.fields.username'),
    key: 'username',
    width: 140,
    ellipsis: { tooltip: true }
  },
  {
    title: t('admin.user.fields.role'),
    key: 'role',
    width: 110,
    render: (row) =>
      h(
        NTag,
        { type: row.role === 'admin' ? 'info' : 'default', bordered: false },
        { default: () => t('admin.user.roleOptions.' + row.role) }
      )
  },
  {
    title: t('admin.user.fields.englishLevel'),
    key: 'english_level',
    width: 140,
    render: (row) => t('profile.levelOptions.' + row.english_level)
  },
  {
    title: t('admin.user.fields.isActive'),
    key: 'is_active',
    width: 110,
    render: (row) =>
      h(
        NTag,
        { type: row.is_active ? 'success' : 'error', bordered: false },
        { default: () => (row.is_active ? t('admin.user.active') : t('admin.user.disabled')) }
      )
  },
  {
    title: t('admin.user.fields.createdAt'),
    key: 'created_at',
    width: 130,
    render: (row) => formatDate(row.created_at)
  },
  {
    title: t('admin.user.fields.lastLoginAt'),
    key: 'last_login_at',
    width: 140,
    render: (row) => (row.last_login_at ? formatDate(row.last_login_at) : '—')
  },
  {
    title: t('admin.user.actions'),
    key: 'actions',
    width: 340,
    fixed: 'right',
    render: (row) => renderActions(row)
  }
])

/** 渲染行操作按钮：启用/禁用、切换角色、删除（自删保护 + 二次确认） */
function renderActions(row: AdminUser) {
  const isSelf = row.id === currentUserId.value
  const current = action.value
  // 当前行是否有进行中的操作，及其类型
  const activeType =
    current !== null && current.id === row.id ? current.type : null

  // 启用 / 禁用
  const toggleActiveBtn = h(
    NButton,
    {
      size: 'small',
      type: row.is_active ? 'warning' : 'success',
      tertiary: true,
      loading: activeType === 'active',
      disabled: activeType !== null && activeType !== 'active',
      onClick: () => handleToggleActive(row)
    },
    { default: () => (row.is_active ? t('admin.user.disable') : t('admin.user.enable')) }
  )

  // 切换角色
  const toggleRoleBtn = h(
    NButton,
    {
      size: 'small',
      type: 'default',
      tertiary: true,
      loading: activeType === 'role',
      disabled: activeType !== null && activeType !== 'role',
      onClick: () => handleToggleRole(row)
    },
    {
      default: () =>
        row.role === 'admin' ? t('admin.user.setUser') : t('admin.user.setAdmin')
    }
  )

  // 删除按钮：自身禁用并 tooltip 提示；其余走 NPopconfirm 二次确认
  const deleteBtn = h(
    NButton,
    {
      size: 'small',
      type: 'error',
      tertiary: true,
      loading: activeType === 'delete',
      disabled: isSelf || (activeType !== null && activeType !== 'delete')
    },
    { default: () => t('common.delete') }
  )

  const deleteNode = isSelf
    ? h(
        NTooltip,
        {},
        {
          default: () => t('admin.user.cannotDeleteSelf'),
          trigger: () => deleteBtn
        }
      )
    : h(
        NPopconfirm,
        { onPositiveClick: () => handleDelete(row) },
        {
          default: () => t('admin.user.deleteConfirm'),
          trigger: () => deleteBtn
        }
      )

  return h(
    NSpace,
    { size: 'small', wrap: false },
    { default: () => [toggleActiveBtn, toggleRoleBtn, deleteNode] }
  )
}

// ============================================================
//  生命周期
// ============================================================

onMounted(fetchUsers)
</script>

<template>
  <div class="space-y-6">
    <!-- 页头 -->
    <header class="space-y-2">
      <h1
        class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50 sm:text-3xl"
      >
        {{ t('admin.user.title') }}
      </h1>
    </header>

    <!-- 工具栏：搜索 + 角色筛选 -->
    <section
      class="rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
    >
      <NSpace align="center" :size="12">
        <NInput
          v-model:value="searchQuery"
          :placeholder="t('admin.user.searchPlaceholder')"
          clearable
          class="w-full sm:w-72"
        />
        <NSelect
          v-model:value="roleFilter"
          :options="roleOptions"
          class="w-40"
        />
      </NSpace>
    </section>

    <!-- 用户表格 -->
    <section
      class="rounded-xl border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900"
    >
      <NDataTable
        :columns="columns"
        :data="users"
        :loading="loading"
        :pagination="false"
        :bordered="false"
        :row-key="rowKey"
        :scroll-x="1280"
      />
    </section>

    <!-- 分页 -->
    <div v-if="total > 0" class="flex justify-center pt-2">
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
