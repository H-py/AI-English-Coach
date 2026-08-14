<script setup lang="ts">
/**
 * 星级显示组件。
 *
 * 用五颗星展示难度：前 ``stars`` 颗为黄色实心，其余为灰色空心。
 * 星形使用实心 path + ``fill="currentColor"``，通过文字颜色类切换。
 */
defineProps<{
  /** 亮起的星数（1-5） */
  stars: number
}>()
</script>

<template>
  <span
    class="inline-flex items-center gap-0.5"
    role="img"
    :aria-label="`${stars} / 5 stars`"
  >
    <svg
      v-for="i in 5"
      :key="i"
      viewBox="0 0 24 24"
      class="h-4 w-4"
      :class="i <= stars ? 'text-amber-400' : 'text-neutral-300 dark:text-neutral-600'"
      fill="currentColor"
    >
      <path
        d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.563.563 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.563.563 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5z"
      />
    </svg>
  </span>
</template>
