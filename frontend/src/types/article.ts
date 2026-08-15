/**
 * 文章模块类型定义。
 *
 * 与后端 `/api/v1/articles` 系列接口一一对应，
 * 字段命名采用 snake_case 以直接映射后端 JSON（后端为 Python），
 * 前端不做额外的 camelCase 转换。
 */

/** 难度星级（1-5 星） */
export type Difficulty = '1' | '2' | '3' | '4' | '5'

/** 四六级真题类型 */
export type CetType = 'cet4' | 'cet6'

/** 文章完整对象（详情接口返回） */
export interface Article {
  id: number
  title: string
  content: string
  summary: string | null
  source: string | null
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

/** 文章列表项（列表接口返回，不含正文） */
export interface ArticleListItem {
  id: number
  title: string
  summary: string | null
  difficulty: Difficulty
  cet_type: CetType | null
  word_count: number
  reading_time: number | null
  cover_url: string | null
  tags: string[]
  created_at: string
}

/** 文章列表响应（分页信封解包后的业务数据） */
export interface ArticleListResponse {
  items: ArticleListItem[]
  total: number
  page: number
  page_size: number
}

/** 单个推荐档位（文章列表 + 可选理由） */
export interface RecommendationTier {
  items: ArticleListItem[]
  reason: string | null
}

/** 个性化推荐文章响应（三档 + 来源标记） */
export interface ArticleRecommendations {
  easy: RecommendationTier
  matched: RecommendationTier
  challenging: RecommendationTier
  generated_by: 'agent' | 'rule'
  generated_at: string
}

/** 文章列表查询参数 */
export interface ArticleQuery {
  difficulty?: Difficulty
  cet_type?: CetType
  tag?: string
  page?: number
  page_size?: number
}

/** 相邻文章的轻量引用（id + 标题） */
export interface ArticleNeighbor {
  id: number
  title: string
}

/** 当前文章的上一篇 / 下一篇（按列表顺序循环） */
export interface ArticleNeighbors {
  prev: ArticleNeighbor | null
  next: ArticleNeighbor | null
}

/** 创建文章的请求体 */
export interface ArticleCreatePayload {
  title: string
  content: string
  difficulty: Difficulty
  cet_type?: CetType | null
  source?: string
  tags?: string[]
  cover_url?: string
  summary?: string
  reading_time?: number
}

/** 更新文章的请求体（所有字段可选） */
export interface ArticleUpdatePayload {
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
