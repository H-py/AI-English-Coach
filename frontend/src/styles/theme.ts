import type { GlobalThemeOverrides } from 'naive-ui'

/**
 * Naive UI 主题覆盖（极简风：参考 Apple / Linear / Notion）。
 *
 * 设计取向：
 *  - 主色用接近黑的深灰（#1d1d1f），避免学习软件常见的花哨配色。
 *  - 圆角统一偏大（8~12px），营造柔和现代的观感。
 *  - 字体走系统无衬线栈，行高舒适，强调阅读优先。
 */

const shared: GlobalThemeOverrides = {
  common: {
    primaryColor: '#1d1d1f',
    primaryColorHover: '#3a3a3c',
    primaryColorPressed: '#0a0a0a',
    primaryColorSuppl: '#1d1d1f',
    borderRadius: '8px',
    borderRadiusSmall: '6px',
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
    fontSize: '14px'
  },
  Card: {
    borderRadius: '12px',
    paddingMedium: '20px 24px'
  },
  Button: {
    fontWeight: '500',
    borderRadiusMedium: '8px'
  },
  Input: {
    borderRadius: '8px'
  },
  Menu: {
    itemHeight: '40px',
    borderRadius: '8px'
  }
}

export const lightThemeOverrides: GlobalThemeOverrides = {
  ...shared,
  common: {
    ...shared.common,
    bodyColor: '#ffffff',
    cardColor: '#ffffff',
    textColorBase: '#1d1d1f',
    textColor1: '#1d1d1f',
    textColor2: '#3a3a3c',
    textColor3: '#86868b',
    borderColor: '#ececec',
    dividerColor: '#f0f0f0'
  }
}

export const darkThemeOverrides: GlobalThemeOverrides = {
  ...shared,
  common: {
    ...shared.common,
    bodyColor: '#0a0a0a',
    cardColor: '#161616',
    textColorBase: '#ededed',
    textColor1: '#ededed',
    textColor2: '#c7c7cc',
    textColor3: '#86868b',
    borderColor: '#262626',
    dividerColor: '#1f1f1f'
  }
}
