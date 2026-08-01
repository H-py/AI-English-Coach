/**
 * 统一 API 响应信封。
 * 后端所有接口返回 { code, message, data } 结构：
 *  - code === 0 表示成功，前端拦截器解包后直接返回 data 字段
 *  - code !== 0 表示业务错误，拦截器抛出 message 提示并 reject
 */
export interface ResponseResult<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页响应数据结构（后续模块按需使用） */
export interface PaginatedData<T> {
  list: T[]
  total: number
  page: number
  pageSize: number
}
