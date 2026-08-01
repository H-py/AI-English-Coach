import { createI18n } from 'vue-i18n'
import en from './en.json'
import zh from './zh.json'

export type AppLocale = 'zh' | 'en'

/**
 * vue-i18n 配置（Composition API 模式）。
 * 默认语言为中文，回退到英文；语言偏好由 app store 持久化并在 main.ts 中同步。
 */
export const i18n = createI18n({
  legacy: false,
  locale: 'zh',
  fallbackLocale: 'en',
  messages: {
    zh,
    en
  }
})

export default i18n
