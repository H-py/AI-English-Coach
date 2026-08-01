import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useStorage } from '@vueuse/core'

export type ThemeMode = 'light' | 'dark'
export type AppLocale = 'zh' | 'en'

/**
 * 全局应用 store（pinia setup 写法）。
 * 持久化：主题、侧边栏折叠状态、语言偏好均通过 useStorage 写入 localStorage。
 */
export const useAppStore = defineStore('app', () => {
  // ---- 主题 ----
  const theme = useStorage<ThemeMode>('arc:theme', 'light')
  const isDark = computed(() => theme.value === 'dark')
  function setTheme(mode: ThemeMode): void {
    theme.value = mode
  }
  function toggleTheme(): void {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  // ---- 侧边栏折叠 ----
  const sidebarCollapsed = useStorage<boolean>('arc:sidebar-collapsed', false)
  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }
  function setSidebarCollapsed(collapsed: boolean): void {
    sidebarCollapsed.value = collapsed
  }

  // ---- 语言 ----
  const locale = useStorage<AppLocale>('arc:locale', 'zh')
  function setLocale(l: AppLocale): void {
    locale.value = l
  }

  return {
    // state
    theme,
    sidebarCollapsed,
    locale,
    // getters
    isDark,
    // actions
    setTheme,
    toggleTheme,
    toggleSidebar,
    setSidebarCollapsed,
    setLocale
  }
})
