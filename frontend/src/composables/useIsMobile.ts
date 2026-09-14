import { useMediaQuery } from '@vueuse/core'

/**
 * 移动 / 窄屏检测。
 *
 * 以 Tailwind lg 断点（1024px）为界：小于 lg 视为移动端布局，
 * 侧边栏与 AI 面板等以抽屉形式呈现；lg 及以上保持桌面布局。
 */
export function useIsMobile() {
  return useMediaQuery('(max-width: 1023px)')
}
