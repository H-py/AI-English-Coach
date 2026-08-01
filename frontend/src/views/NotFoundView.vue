<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NButton } from 'naive-ui'

/** 404 页面 */
const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <div class="flex min-h-[60vh] flex-col items-center justify-center gap-5 text-center">
    <p class="text-7xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50">
      404
    </p>
    <div class="space-y-2">
      <h1 class="text-xl font-medium text-neutral-800 dark:text-neutral-100">
        {{ t('notFound.title') }}
      </h1>
      <p class="max-w-md text-sm text-neutral-500 dark:text-neutral-400">
        {{ t('notFound.desc') }}
      </p>
    </div>
    <NButton type="primary" @click="router.push('/')">
      {{ t('notFound.backHome') }}
    </NButton>
  </div>
</template>
