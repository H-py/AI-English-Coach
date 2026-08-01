<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NTag, NPagination, NSpin, NEmpty } from 'naive-ui'
import { readingApi } from '@/api/reading'
import type { ReadingHistoryWithArticle } from '@/types/reading'

/**
 * Reading history page.
 *
 * Features:
 *  - Card list of reading sessions: article title (clickable -> detail),
 *    article ID badge when title is missing, reading duration, start/end
 *    time, and a status tag (completed / in progress).
 *  - "Read again" affordance per card to jump back into the article.
 *  - Empty state (NEmpty), loading state (NSpin), pagination (NPagination).
 *
 * Data is fetched directly via readingApi (not a store); the page manages
 * its own list state, mirroring the VocabularyView pattern.
 */

const { t } = useI18n()
const router = useRouter()

// ============================================================
//  Helpers
// ============================================================

/** Format an ISO datetime string into a locale-aware readable string. */
function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/** Format a number of seconds into "Xm Ys" or just "Xs". */
function formatDuration(seconds: number | null): string {
  if (seconds == null || seconds < 0) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

/** Navigate to the article detail page. */
function goToArticle(articleId: number): void {
  router.push(`/articles/${articleId}`)
}

// ============================================================
//  List state
// ============================================================

const history = ref<ReadingHistoryWithArticle[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

// ============================================================
//  Data fetching
// ============================================================

/** Fetch the reading history list for the current page. */
async function fetchHistory(): Promise<void> {
  loading.value = true
  try {
    const res = await readingApi.listHistory({
      page: page.value,
      page_size: pageSize.value
    })
    history.value = res.items
    total.value = res.total
  } catch {
    // Errors are surfaced by the axios interceptor.
  } finally {
    loading.value = false
  }
}

/** Handle pagination change. */
function handlePageChange(p: number): void {
  page.value = p
  fetchHistory()
}

onMounted(fetchHistory)
</script>

<template>
  <div class="space-y-6">
    <!-- Page header -->
    <header class="space-y-2">
      <h1 class="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50">
        {{ t('history.title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 prose-comfortable">
        {{ t('history.subtitle') }}
      </p>
    </header>

    <!-- Session count -->
    <div class="flex items-center justify-end">
      <span class="whitespace-nowrap text-xs text-neutral-400 dark:text-neutral-500">
        {{ t('history.totalSessions', { count: total }) }}
      </span>
    </div>

    <!-- History list / empty state -->
    <div class="min-h-[300px]">
      <NSpin :show="loading">
        <!-- Empty state -->
        <NEmpty
          v-if="!loading && history.length === 0"
          :description="t('history.empty')"
          class="py-20"
        >
          <template #extra>
            <p class="text-sm text-neutral-400 dark:text-neutral-500">
              {{ t('history.emptyHint') }}
            </p>
          </template>
        </NEmpty>

        <!-- Card list -->
        <div v-else class="space-y-4">
          <article
            v-for="item in history"
            :key="item.id"
            class="rounded-xl border border-neutral-200 bg-white p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-neutral-800 dark:bg-neutral-900 sm:p-6"
          >
            <!-- Top: article title (clickable) / ID badge + status tag -->
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0 flex-1">
                <!-- Article title: clickable -->
                <h2
                  v-if="item.article_title"
                  class="cursor-pointer text-lg font-semibold tracking-tight text-neutral-900 transition-colors hover:text-blue-500 dark:text-neutral-50 dark:hover:text-blue-400"
                  @click="goToArticle(item.article_id)"
                >
                  {{ item.article_title }}
                </h2>

                <!-- Missing title: show article ID badge + fallback label -->
                <div v-else class="flex items-center gap-2">
                  <NTag
                    size="small"
                    round
                    :bordered="false"
                    class="cursor-pointer"
                    @click="goToArticle(item.article_id)"
                  >
                    #{{ item.article_id }}
                  </NTag>
                  <span class="text-sm text-neutral-400 dark:text-neutral-500">
                    {{ t('history.noTitle') }}
                  </span>
                </div>
              </div>

              <!-- Status: completed (ended_at present) vs in progress -->
              <NTag
                :type="item.ended_at ? 'success' : 'info'"
                size="small"
                round
                :bordered="false"
              >
                {{ item.ended_at ? t('history.completed') : t('history.inProgress') }}
              </NTag>
            </div>

            <!-- Footer: duration + times + read again -->
            <div class="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100 pt-4 dark:border-neutral-800">
              <!-- Duration / start / end -->
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-400 dark:text-neutral-500">
                <!-- Duration -->
                <span class="inline-flex items-center gap-1">
                  <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M12 7v5l3 2" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <span>{{ t('history.duration') }}: {{ formatDuration(item.duration_seconds) }}</span>
                </span>

                <span class="text-neutral-300 dark:text-neutral-600">·</span>

                <!-- Started at -->
                <span class="inline-flex items-center gap-1">
                  <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" />
                    <path d="M3 9h18M8 2v4M16 2v4" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <span>{{ t('history.startedAt') }}: {{ formatDateTime(item.started_at) }}</span>
                </span>

                <!-- Ended at (only when completed) -->
                <template v-if="item.ended_at">
                  <span class="text-neutral-300 dark:text-neutral-600">·</span>
                  <span>{{ t('history.endedAt') }}: {{ formatDateTime(item.ended_at) }}</span>
                </template>
              </div>

              <!-- Read again -->
              <button
                type="button"
                class="read-again inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-blue-500 transition-colors hover:bg-blue-50 hover:text-blue-600 dark:text-blue-400 dark:hover:bg-blue-500/10"
                @click="goToArticle(item.article_id)"
              >
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 12a9 9 0 1 0 3-6.7M3 4v4h4" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
                {{ t('history.readAgain') }}
              </button>
            </div>
          </article>
        </div>
      </NSpin>
    </div>

    <!-- Pagination -->
    <div
      v-if="total > pageSize"
      class="flex justify-center pt-2"
    >
      <NPagination
        :page="page"
        :page-size="pageSize"
        :item-count="total"
        show-quick-jumper
        @update:page="handlePageChange"
      />
    </div>
  </div>
</template>

<style scoped>
/* Read-again button: tighten focus ring for keyboard navigation */
.read-again:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 2px;
}

/* ============================================================
   Dark mode
   ============================================================ */
:global(html.dark) .read-again:focus-visible {
  outline-color: #60a5fa;
}
</style>
