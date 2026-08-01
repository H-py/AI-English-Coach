import { http } from './request'
import type {
  Article,
  ArticleListResponse,
  ArticleQuery,
  ArticleCreatePayload,
  ArticleUpdatePayload
} from '@/types/article'

/**
 * 文章模块 API 封装。
 *
 * http 已在响应拦截器中对后端统一信封 { code, message, data } 解包，
 * 因此各方法直接返回业务数据本身。
 * 所有接口前缀 `/api/v1`（axios baseURL 已配好），这里只写相对路径。
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
  },

  /** 创建文章 */
  create(data: ArticleCreatePayload): Promise<Article> {
    return http.post('/articles', data)
  },

  /** 更新文章（部分字段） */
  update(id: number, data: ArticleUpdatePayload): Promise<Article> {
    return http.put(`/articles/${id}`, data)
  },

  /** 删除文章 */
  delete(id: number): Promise<void> {
    return http.delete(`/articles/${id}`)
  }
}
