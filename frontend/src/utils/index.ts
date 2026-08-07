/**
 * 通用工具函数与本地存储封装。
 */

const ACCESS_TOKEN_KEY = 'arc_access_token'
const REFRESH_TOKEN_KEY = 'arc_refresh_token'
const USER_KEY = 'arc_user'

// ---- Access Token ----
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function setAccessToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token)
}

// ---- Refresh Token ----
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_TOKEN_KEY, token)
}

// ---- 统一清除 ----
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

/** 清除本地存储的用户信息（与 auth store 的 useStorage key 一致） */
export function clearUserData(): void {
  localStorage.removeItem(USER_KEY)
}

/** 清除全部认证相关数据：token + 用户信息 */
export function clearAllAuthData(): void {
  clearTokens()
  clearUserData()
}

// ---- 兼容别名 ----
// 保留旧的 getToken/setToken/removeToken 作为 access token 的别名，
// 便于尚未完成改造的调用方平滑过渡。
export const getToken = getAccessToken
export const setToken = setAccessToken
export const removeToken = clearTokens

// ---- 通用 ----

/** 简单的 debounce */
export function debounce<T extends (...args: any[]) => void>(fn: T, delay = 300): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delay)
  }) as T
}

/** 类名拼接 */
export function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

/** 判断空值 */
export function isNil<T>(v: T | null | undefined): v is null | undefined {
  return v === null || v === undefined
}
