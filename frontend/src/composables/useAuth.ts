import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import type { LoginPayload, RegisterPayload } from '@/types/auth'

/**
 * 认证逻辑 composable。
 *
 * 在 auth store 之上封装页面层常用的登录 / 注册 / 登出 / 守卫动作，
 * 统一处理「成功后跳转」的副作用。错误由 axios 响应拦截器统一弹出 message，
 * 这里不额外 try/catch 弹错；若调用方需感知失败可自行捕获。
 */
export function useAuth() {
  const store = useAuthStore()
  const router = useRouter()

  /** 登录：成功后写入认证态并根据角色跳转 */
  async function login(payload: LoginPayload): Promise<void> {
    const data = await authApi.login(payload)
    store.setAuth(data)
    await router.push(data.user.role === 'admin' ? '/admin' : '/')
  }

  /** 注册：成功后写入认证态并跳转首页 */
  async function register(payload: RegisterPayload): Promise<void> {
    const data = await authApi.register(payload)
    store.setAuth(data)
    await router.push('/')
  }

  /** 登出：清除认证态并跳转登录页 */
  async function logout(): Promise<void> {
    await store.logout()
    await router.push('/login')
  }

  /**
   * 确保当前已认证：
   *  - 已认证直接返回；
   *  - 未认证时尝试拉取用户信息（token 可能仍有效）；
   *  - 拉取失败则跳转登录页。
   */
  async function ensureAuthenticated(): Promise<void> {
    if (store.isAuthenticated) return
    try {
      await store.fetchUser()
    } catch {
      await router.push('/login')
    }
  }

  return {
    login,
    register,
    logout,
    ensureAuthenticated
  }
}
