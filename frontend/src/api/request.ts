import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig
} from 'axios'
import { createDiscreteApi } from 'naive-ui'
import type { ResponseResult } from '@/types/api'
import { getAccessToken, clearAllAuthData } from '@/utils'

/**
 * Naive UI 的 message 等离散 API 需要在 Provider 树内使用，
 * 而 axios 拦截器运行在组件树之外。这里用 createDiscreteApi
 * 创建独立实例，使其可在拦截器中安全调用。
 */
const { message } = createDiscreteApi(['message'])

/** 认证错误码（与后端 CODE_AUTH_ERROR 一致） */
const CODE_AUTH_ERROR = 20000

/** 是否已触发登录态失效跳转，避免并发请求重复处理 */
let sessionExpiredHandled = false

/** 是否正停留在登录页（正在尝试登录，401 应视为账号密码错误而非会话过期） */
function isOnLoginPage(): boolean {
  return window.location.pathname.replace(/\/+$/, '') === '/login'
}

/** 登录态失效：清除本地认证数据并跳转登录页，附带过期提示参数 */
function handleSessionExpired(): void {
  if (sessionExpiredHandled) return
  sessionExpiredHandled = true
  clearAllAuthData()
  window.location.replace('/login?session_expired=1')
}

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 15000
})

// ---- 请求拦截器：注入 Bearer token ----
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ---- 响应拦截器：解包信封 + 401 处理 ----
request.interceptors.response.use(
  (response) => {
    // 约定后端统一返回 ResponseResult<T>
    const res = response.data as ResponseResult<unknown>

    // code === 0 成功：只把真实业务数据 data 返回给调用方
    if (res.code === 0) {
      return res.data as any
    }

    // 业务错误：用 message 提示并 reject
    message.error(res.message || '请求失败')
    return Promise.reject(new Error(res.message || '请求失败'))
  },
  (error) => {
    const status = error?.response?.status
    const envelope = error?.response?.data as Partial<ResponseResult> | undefined

    // 登录态失效：HTTP 401 或信封携带认证错误码（token 过期/无效）。
    // 已停留在登录页时不做跳转，走下方统一提示（避免把"邮箱或密码错误"误判为会话过期）。
    if ((status === 401 || envelope?.code === CODE_AUTH_ERROR) && !isOnLoginPage()) {
      handleSessionExpired()
      return Promise.reject(error)
    }

    // 优先使用后端信封里的 message，其次 axios 错误信息
    const msg =
      envelope?.message || error?.message || '网络异常，请稍后重试'
    message.error(msg)
    return Promise.reject(error)
  }
)

/**
 * 类型友好的 HTTP 封装。
 *
 * 由于响应拦截器已对信封解包，调用方拿到的就是业务数据本身。
 * 通过 `as unknown as Promise<T>` 让 TS 推断为解包后的类型，
 * 使用方式：`http.get<User>('/users/1')` => Promise<User>
 */
export const http = {
  get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return request.get(url, config) as unknown as Promise<T>
  },
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.post(url, data, config) as unknown as Promise<T>
  },
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.put(url, data, config) as unknown as Promise<T>
  },
  patch<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.patch(url, data, config) as unknown as Promise<T>
  },
  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return request.delete(url, config) as unknown as Promise<T>
  }
}

export default request
