import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useStorage } from '@vueuse/core'
import { authApi } from '@/api/auth'
import {
  setAccessToken,
  setRefreshToken,
  clearTokens
} from '@/utils'
import type { User, LoginResponse } from '@/types/auth'

/**
 * 认证 store（pinia setup 写法）。
 *
 * 职责：
 *  - 维护当前登录用户信息，并通过 useStorage 持久化到 localStorage，
 *    使得刷新页面后仍能保持登录态（key 为 'arc_user'）。
 *  - 暴露 isAuthenticated 派生状态供路由守卫与组件使用。
 *  - 封装 setAuth / clearAuth / fetchUser / logout 等动作。
 *
 * 注意：access/refresh token 由 utils 的 setAccessToken/setRefreshToken 管理，
 * 与 user 信息分离存储；HTTP 401 时由 axios 拦截器统一清除并跳转登录页。
 */
export const useAuthStore = defineStore('auth', () => {
  // 用户信息，初始值为 null；useStorage 存对象需显式给 null 作为初值
  const user = useStorage<User | null>('arc_user', null)

  // 是否已认证：基于 user 是否存在判断
  const isAuthenticated = computed(() => user.value !== null)

  // 是否为管理员：基于 user.role === 'admin' 判断
  const isAdmin = computed(() => user.value?.role === 'admin')

  /** 写入登录态：保存 token 与用户信息 */
  function setAuth(data: LoginResponse): void {
    setAccessToken(data.access_token)
    setRefreshToken(data.refresh_token)
    user.value = data.user
  }

  /** 仅更新用户信息（如 fetchUser / updateMe 后） */
  function setUser(u: User): void {
    user.value = u
  }

  /** 清除全部认证状态：token + 用户信息 */
  function clearAuth(): void {
    clearTokens()
    user.value = null
  }

  /** 拉取当前用户信息并更新本地状态 */
  async function fetchUser(): Promise<User> {
    const result = await authApi.getMe()
    setUser(result)
    return result
  }

  /**
   * 登出：通知服务端使令牌失效，无论成功与否都清除本地认证状态。
   */
  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } finally {
      clearAuth()
    }
  }

  return {
    // state
    user,
    // getters
    isAuthenticated,
    isAdmin,
    // actions
    setAuth,
    setUser,
    clearAuth,
    fetchUser,
    logout
  }
})
