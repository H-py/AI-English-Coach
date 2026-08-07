import { http } from './request'
import type { Article } from '@/types/article'
import type {
  AdminArticleCreatePayload,
  AdminArticleListResponse,
  AdminArticleQuery,
  AdminArticleUpdatePayload,
  AdminDashboard,
  AdminUser,
  AdminUserListResponse,
  AdminUserQuery,
  AdminUserUpdatePayload,
} from '@/types/admin'

/**
 * 管理后台 API 封装。
 *
 * 所有接口对应后端 `/api/v1/admin/*` 路由，需要 admin 角色 token。
 * http 已在响应拦截器中对后端统一信封解包，各方法直接返回业务数据。
 */
export const adminApi = {
  // ---- Dashboard ----

  /** 获取管理后台概览统计 */
  getDashboard(): Promise<AdminDashboard> {
    return http.get('/admin/dashboard')
  },

  // ---- Article management ----

  /** 获取文章列表（含未发布，支持搜索 / 筛选 / 分页） */
  listArticles(params?: AdminArticleQuery): Promise<AdminArticleListResponse> {
    return http.get('/admin/articles', { params })
  },

  /** 获取文章详情（不增加浏览量） */
  getArticle(id: number): Promise<Article> {
    return http.get(`/admin/articles/${id}`)
  },

  /** 创建文章 */
  createArticle(data: AdminArticleCreatePayload): Promise<Article> {
    return http.post('/admin/articles', data)
  },

  /** 更新文章（部分字段） */
  updateArticle(id: number, data: AdminArticleUpdatePayload): Promise<Article> {
    return http.put(`/admin/articles/${id}`, data)
  },

  /** 删除文章 */
  deleteArticle(id: number): Promise<void> {
    return http.delete(`/admin/articles/${id}`)
  },

  // ---- User management ----

  /** 获取用户列表（支持搜索 / 角色筛选 / 分页） */
  listUsers(params?: AdminUserQuery): Promise<AdminUserListResponse> {
    return http.get('/admin/users', { params })
  },

  /** 获取单个用户详情 */
  getUser(id: number): Promise<AdminUser> {
    return http.get(`/admin/users/${id}`)
  },

  /** 更新用户信息（角色 / 状态 / 用户名等） */
  updateUser(id: number, data: AdminUserUpdatePayload): Promise<AdminUser> {
    return http.put(`/admin/users/${id}`, data)
  },

  /** 删除用户（不可删除自己） */
  deleteUser(id: number): Promise<void> {
    return http.delete(`/admin/users/${id}`)
  },
}
