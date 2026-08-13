/**
 * 用户自定义大模型配置的类型定义。
 */

/** 一条用户模型配置（API Key 始终为掩码形式，绝不含明文）。 */
export interface UserLlmConfig {
  id: number
  user_id: number
  provider_name: string
  base_url: string
  model: string
  masked_api_key: string
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 用户的全部模型配置列表及当前激活的配置 id（未激活任何配置时为 null）。 */
export interface LlmConfigListResult {
  items: UserLlmConfig[]
  active_id: number | null
}

/** 创建模型配置的载荷。 */
export interface LlmConfigCreatePayload {
  provider_name: string
  base_url: string
  model: string
  api_key: string
}

/** 模型配置的部分更新载荷；api_key 为空/省略表示保留已保存的密钥。 */
export interface LlmConfigUpdatePayload {
  provider_name?: string
  base_url?: string
  model?: string
  api_key?: string
}

/** 连接测试载荷：可指定已存配置，或提供内联覆盖值（测试尚未保存的值）。 */
export interface LlmConfigTestPayload {
  config_id?: number
  base_url?: string
  model?: string
  api_key?: string
}

/** 连接测试结果。 */
export interface LlmConfigTestResult {
  ok: boolean
  model: string
}

/** 模型服务提供方预设（用于快速填充服务商名称 / Base URL / 模型名）。 */
export interface LlmProviderPreset {
  key: 'deepseek' | 'openai' | 'ollama' | 'custom'
  name: string
  baseUrl: string
  model: string
}
