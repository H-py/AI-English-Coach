import { http } from './request'
import type {
  Article,
  ArticleListResponse,
  ArticleQuery,
} from '@/types/article'

/**
 * 文章模块 API 封装（只读接口，供普通用户使用）。
 *
 * 文章的创建、编辑、删除等管理操作由 adminApi 统一处理，
 * 对应后端 `/api/v1/admin/articles` 系列接口。
 *
 * http 已在响应拦截器中对后端统一信封 { code, message, data } 解包，
 * 因此各方法直接返回业务数据本身。
 */
export const articleApi = {
  /** 获取文章列表（支持按难度 / 标签筛选与分页） */
  list(params?: ArticleQuery): Promise<ArticleListResponse> {
    return http.get('/articles', { params })
  },

  /** 获取全部可用标签（用于标签筛选） */
  getTags(): Promise<string[]> {
    return http.get('/articles/tags')
  },

  /** 获取文章详情（含正文） */
  getDetail(id: number): Promise<Article> {
    return http.get(`/articles/${id}`)
  }
}
