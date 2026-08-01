<script setup lang="ts">
import { useI18n } from 'vue-i18n'

/**
 * 应用 Logo 组件。
 * 极简标记：一个翻开的书页图形置于接近黑的圆角方块中。
 * compact 模式下仅显示标记，隐藏文字（用于折叠侧边栏）。
 */
withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })

const { t } = useI18n()
</script>

<template>
  <div class="flex items-center gap-2.5 select-none">
    <span class="logo-mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
        <path
          d="M12 6.5C10.5 5 8 4.5 5 4.75V18c3-.25 5.5.25 7 1.75M12 6.5C13.5 5 16 4.5 19 4.75V18c-3-.25-5.5.25-7 1.75M12 6.5v13.25"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </span>
    <span v-if="!compact" class="logo-text">
      {{ t('app.name') }}
    </span>
  </div>
</template>

<style scoped>
.logo-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background-color: #1d1d1f;
  color: #ffffff;
  flex-shrink: 0;
}
html.dark .logo-mark {
  background-color: #f5f5f7;
  color: #0a0a0a;
}
.logo-mark svg {
  width: 17px;
  height: 17px;
}
.logo-text {
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #1d1d1f;
  white-space: nowrap;
}
html.dark .logo-text {
  color: #ededed;
}
</style>
