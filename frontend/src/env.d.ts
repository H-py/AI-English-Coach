/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API 基地址，通过 .env 的 VITE_API_BASE_URL 注入 */
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
