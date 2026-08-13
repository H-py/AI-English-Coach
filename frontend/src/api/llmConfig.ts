import { http } from './request'
import type {
  LlmConfigCreatePayload,
  LlmConfigListResult,
  LlmConfigTestPayload,
  LlmConfigTestResult,
  LlmConfigUpdatePayload,
  UserLlmConfig
} from '@/types/llmConfig'

/**
 * 用户自定义大模型配置 API。
 *
 * 全部接口需要登录（Bearer 令牌由拦截器自动注入）。响应信封已由拦截器
 * 自动解包，直接返回业务数据。
 */

export const llmConfigApi = {
  /** 列出当前用户的全部模型配置及当前激活的配置 id */
  listConfigs(): Promise<LlmConfigListResult> {
    return http.get('/llm-config')
  },

  /** 新增一条模型配置（用户的首个配置会自动激活） */
  createConfig(data: LlmConfigCreatePayload): Promise<UserLlmConfig> {
    return http.post('/llm-config', data)
  },

  /** 更新指定模型配置；api_key 留空表示保留原值 */
  updateConfig(id: number, data: LlmConfigUpdatePayload): Promise<UserLlmConfig> {
    return http.put(`/llm-config/${id}`, data)
  },

  /** 删除指定模型配置 */
  deleteConfig(id: number): Promise<{ ok: boolean }> {
    return http.delete(`/llm-config/${id}`)
  },

  /** 把指定配置设为当前使用中的模型 */
  activateConfig(id: number): Promise<UserLlmConfig> {
    return http.post(`/llm-config/${id}/activate`)
  },

  /** 停用全部配置，恢复使用默认模型 */
  deactivateAll(): Promise<{ ok: boolean }> {
    return http.post('/llm-config/deactivate')
  },

  /** 用指定配置（或内联值）测试连通性 */
  testConfig(data: LlmConfigTestPayload): Promise<LlmConfigTestResult> {
    return http.post('/llm-config/test', data)
  }
}
