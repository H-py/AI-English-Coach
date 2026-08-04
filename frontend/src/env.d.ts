/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API 基地址，通过 .env 的 VITE_API_BASE_URL 注入 */
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/**
 * 显式声明 .vue 模块类型。
 *
 * 虽然 `vite/client` 自带此声明，但在使用 `@/` 路径别名 + 动态 import 时，
 * TypeScript 语言服务器有时无法正确解析 .vue 文件类型，导致 IDE 报红。
 * 显式声明可确保所有 .vue 导入（包括通过别名导入的）都有正确的类型。
 */
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}
