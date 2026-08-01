<script setup lang="ts">
/**
 * 通用卡片容器。
 * 极简风：白底、细边框、柔和圆角、充足内边距，适合阅读优先的内容排版。
 */
withDefaults(
  defineProps<{
    title?: string
    /** 去掉默认内边距，交由调用方自行控制 */
    flush?: boolean
  }>(),
  { title: undefined, flush: false }
)
</script>

<template>
  <section
    class="rounded-2xl border border-neutral-200 bg-white transition-colors dark:border-neutral-800 dark:bg-neutral-900"
  >
    <header
      v-if="title || $slots.header"
      class="flex items-center justify-between border-b border-neutral-100 px-6 py-4 dark:border-neutral-800"
    >
      <slot name="header">
        <h3 class="text-sm font-medium text-neutral-500 dark:text-neutral-400">{{ title }}</h3>
      </slot>
    </header>
    <div :class="flush ? '' : 'p-6'">
      <slot />
    </div>
  </section>
</template>
