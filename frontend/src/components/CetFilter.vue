<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { CetType } from '@/types/article'

/**
 * 四六级真题筛选器。
 *
 * 用按钮组展示「全部」+ 四级 + 六级，选中态高亮。
 * 通过 v-model（modelValue / update:modelValue）与父级双向绑定。
 * 样式与 DifficultyFilter 保持一致（filter-btn）。
 */
const props = defineProps<{
  modelValue: CetType | undefined
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: CetType | undefined): void
}>()

const { t } = useI18n()

// 四六级类型，固定顺序
const cetTypes: CetType[] = ['cet4', 'cet6']

/** 点击「全部」：清空筛选 */
function selectAll(): void {
  emit('update:modelValue', undefined)
}

/** 点击具体类型 */
function selectCet(c: CetType): void {
  emit('update:modelValue', c)
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <!-- 全部 -->
    <button
      type="button"
      class="filter-btn"
      :class="{ active: modelValue === undefined }"
      @click="selectAll"
    >
      {{ t('article.cet.all') }}
    </button>

    <!-- 四级 / 六级 -->
    <button
      v-for="c in cetTypes"
      :key="c"
      type="button"
      class="filter-btn"
      :class="{ active: modelValue === c }"
      @click="selectCet(c)"
    >
      {{ t(`article.cet.${c}`) }}
    </button>
  </div>
</template>

<style scoped>
.filter-btn {
  padding: 0.375rem 0.875rem;
  border-radius: 9999px;
  border: 1px solid #e5e5e5;
  background: transparent;
  font-size: 0.8125rem;
  color: #525252;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}
.filter-btn:hover {
  border-color: #d4d4d4;
  color: #171717;
}
.filter-btn.active {
  background-color: #1d1d1f;
  border-color: #1d1d1f;
  color: #ffffff;
}

:global(html.dark) .filter-btn {
  border-color: #2a2a2a;
  color: #a3a3a3;
}
:global(html.dark) .filter-btn:hover {
  border-color: #404040;
  color: #f5f5f5;
}
:global(html.dark) .filter-btn.active {
  background-color: #ededed;
  border-color: #ededed;
  color: #0a0a0a;
}
</style>
