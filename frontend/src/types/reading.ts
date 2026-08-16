/**
 * 阅读模块类型定义。
 *
 * 与后端 `/api/v1/reading` 和 `/api/v1/ai` 系列接口一一对应，
 * 字段命名采用 snake_case 以直接映射后端 JSON（后端为 Python），
 * 前端不做额外的 camelCase 转换。
 */

/** 单词掌握程度 */
export type MasteryLevel = 'new' | 'learning' | 'familiar' | 'mastered'

/** 收藏的单词 */
export interface WordCollection {
  id: number
  user_id: number
  word: string
  context: string
  article_id: number | null
  ai_explanation: string | null
  short_meaning: string | null
  mastery_level: MasteryLevel
  study_count: number
  last_studied_at: string | null
  created_at: string
  updated_at: string
  /** 分级词库中的等级（如 ['cet4', 'kaoyan']），后端派生填充 */
  levels: string[]
}

/** 一次背诵方案：有序单词序列 + 背诵建议 + 来源标记 */
export interface VocabularyPlan {
  words: WordCollection[]
  note: string | null
  total: number
  generated_by: 'agent' | 'rule'
}

/** 收藏的句子 */
export interface SentenceCollection {
  id: number
  user_id: number
  sentence: string
  article_id: number | null
  note: string | null
  created_at: string
}

/** 阅读历史记录 */
export interface ReadingHistory {
  id: number
  user_id: number
  article_id: number
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  read_count: number
  created_at: string
}

/** 带文章标题的阅读历史（列表接口返回） */
export interface ReadingHistoryWithArticle extends ReadingHistory {
  article_title: string | null
}

/** AI 问答对话消息 */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
}

/** AI 对话历史记录（后端返回，含 id 和 created_at） */
export interface ConversationMessage {
  id: number
  role: string
  content: string
  created_at: string
}

// ---- SSE 流式请求 payload ----

export interface ExplainWordPayload {
  word: string
  context: string
  article_id: number
  history_id?: number
}

export interface AnalyzeSentencePayload {
  sentence: string
  article_id: number
  history_id?: number
}

export interface ParagraphSummaryPayload {
  paragraph: string
  article_id: number
  history_id?: number
}

export interface ChatPayload {
  message: string
  article_id: number
  history_id?: number
}

// ---- 非流式请求 payload ----

export interface SaveWordPayload {
  word: string
  context: string
  article_id?: number
  ai_explanation?: string
  short_meaning?: string
}

export interface SaveSentencePayload {
  sentence: string
  article_id?: number
  note?: string
}

export interface UpdateWordPayload {
  mastery_level?: MasteryLevel
  study_count?: number
}

export interface UpdateSentencePayload {
  note?: string
}

// ---- 阅读总结 ----

/** 活动统计数据 */
export interface ActivityStats {
  word_count: number
  sentence_count: number
  chat_count: number
  duration_seconds: number | null
}

/** 阅读总结 */
export interface ReadingSummary {
  id: number
  history_id: number
  article_id: number
  content: string
  activity_stats: ActivityStats
  created_at: string
}

// ---- 阅读练习题 ----

/** 练习题题目 */
export interface QuizQuestion {
  id: number
  question: string
  options: string[]
  correct_answer: string
  explanation: string
}

/** 用户答题结果（提交后返回） */
export interface QuizAnswerResult {
  question_id: number
  user_answer: string
  correct_answer: string
  is_correct: boolean
  explanation: string
}

/** 练习题 */
export interface ReadingQuiz {
  id: number
  history_id: number
  article_id: number
  questions: QuizQuestion[]
  user_answers: { question_id: number; user_answer: string; is_correct: boolean }[] | null
  score: number | null
  total: number
  created_at: string
}

/** 提交练习题后的响应 */
export interface QuizSubmitResponse {
  quiz_id: number
  score: number
  total: number
  results: QuizAnswerResult[]
}
