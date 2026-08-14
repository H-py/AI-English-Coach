/**
 * 管理后台类型定义。
 *
 * 与后端 `/api/v1/admin/*` 系列接口一一对应。
 */

import type { CetType, Difficulty } from './article'
import type { EnglishLevel, UserRole } from './auth'

/** 管理后台文章列表项（含 is_published / view_count / updated_at） */
export interface AdminArticleListItem {
  id: number
  title: string
  summary: string | null
  difficulty: Difficulty
  cet_type: CetType | null
  word_count: number
  reading_time: number | null
  cover_url: string | null
  tags: string[]
  is_published: boolean
  view_count: number
  created_at: string
  updated_at: string
}

/** 管理后台文章列表响应 */
export interface AdminArticleListResponse {
  items: AdminArticleListItem[]
  total: number
  page: number
  page_size: number
}

/** 管理后台文章列表查询参数 */
export interface AdminArticleQuery {
  search?: string
  difficulty?: Difficulty
  cet_type?: CetType
  tag?: string
  is_published?: boolean
  page?: number
  page_size?: number
}

/** 创建文章请求体（含 is_published） */
export interface AdminArticleCreatePayload {
  title: string
  content: string
  difficulty: Difficulty
  cet_type?: CetType | null
  source?: string
  tags?: string[]
  cover_url?: string
  summary?: string
  reading_time?: number
  is_published?: boolean
}

/** 更新文章请求体（所有字段可选） */
export interface AdminArticleUpdatePayload {
  title?: string
  content?: string
  difficulty?: Difficulty
  cet_type?: CetType | null
  source?: string
  tags?: string[]
  cover_url?: string
  summary?: string
  reading_time?: number
  is_published?: boolean
}

/** 管理后台用户信息 */
export interface AdminUser {
  id: number
  email: string
  username: string
  avatar_url: string | null
  english_level: EnglishLevel
  role: UserRole
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

/** 管理后台用户列表响应 */
export interface AdminUserListResponse {
  items: AdminUser[]
  total: number
  page: number
  page_size: number
}

/** 管理后台用户列表查询参数 */
export interface AdminUserQuery {
  search?: string
  role?: UserRole
  is_active?: boolean
  page?: number
  page_size?: number
}

/** 管理后台更新用户请求体 */
export interface AdminUserUpdatePayload {
  username?: string
  role?: UserRole
  is_active?: boolean
  english_level?: EnglishLevel
}

/** 管理后台概览统计 */
export interface AdminDashboard {
  total_users: number
  total_articles: number
  published_articles: number
  total_views: number
}
