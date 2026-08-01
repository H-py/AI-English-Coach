import { computed, watch } from 'vue'
import { darkTheme, type GlobalTheme, type GlobalThemeOverrides } from 'naive-ui'
import { useAppStore } from '@/stores/app'
import { lightThemeOverrides, darkThemeOverrides } from '@/styles/theme'

/**
 * 主题切换 composable。
 *
 * 职责：
 * 1. 暴露给 Naive UI ConfigProvider 的 theme / themeOverrides（light/dark）。
 * 2. 同步在 <html> 上增删 `dark` 类，驱动 Tailwind 的 dark mode（class 策略）。
 *
 * 这样 Tailwind 的 `dark:` 变体与 Naive UI 暗色主题始终保持一致。
 */
export function useTheme() {
  const app = useAppStore()

  const naiveTheme = computed<GlobalTheme | null>(() =>
    app.isDark ? darkTheme : null
  )
  const themeOverrides = computed<GlobalThemeOverrides>(() =>
    app.isDark ? darkThemeOverrides : lightThemeOverrides
  )

  // 同步 dark class 到 <html>，驱动 Tailwind dark mode
  watch(
    () => app.isDark,
    (dark) => {
      const root = document.documentElement
      if (dark) root.classList.add('dark')
      else root.classList.remove('dark')
    },
    { immediate: true }
  )

  return {
    naiveTheme,
    themeOverrides,
    isDark: computed(() => app.isDark),
    theme: computed(() => app.theme),
    toggleTheme: app.toggleTheme,
    setTheme: app.setTheme
  }
}
