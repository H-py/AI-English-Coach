/**
 * 认证模块相关类型定义。
 */

/** 用户英语水平等级 */
export type EnglishLevel = 'beginner' | 'intermediate' | 'advanced'

/** 用户信息 */
export interface User {
  id: number
  email: string
  username: string
  avatar_url: string | null
  english_level: EnglishLevel
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

/** Token 响应（仅包含令牌信息） */
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** 登录 / 注册响应（令牌 + 用户信息） */
export interface LoginResponse extends TokenResponse {
  user: User
}

/** 注册请求体 */
export interface RegisterPayload {
  email: string
  username: string
  password: string
}

/** 登录请求体 */
export interface LoginPayload {
  email: string
  password: string
}

/** 更新当前用户资料请求体（字段均可选） */
export interface UpdateUserPayload {
  avatar_url?: string
  english_level?: EnglishLevel
}
