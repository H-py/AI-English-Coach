<script setup lang="ts">
import { ref } from 'vue'
import { speakWord } from '@/utils/speech'

const props = withDefaults(
  defineProps<{
    /** 要朗读的单词或短语 */
    word: string
    /** 按钮尺寸：small | default */
    size?: 'small' | 'default'
  }>(),
  {
    size: 'default'
  }
)

/** 播放中的短暂高亮反馈 */
const playing = ref(false)

function handleSpeak(): void {
  if (!props.word) return
  speakWord(props.word)
  playing.value = true
  window.setTimeout(() => {
    playing.value = false
  }, 600)
}
</script>

<template>
  <button
    type="button"
    class="speaker-btn"
    :class="[`speaker-btn--${size}`, { 'speaker-btn--active': playing }]"
    :title="`${word} 的发音`"
    :aria-label="`播放 ${word} 的发音`"
    @click.stop="handleSpeak"
  >
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M11 5 6 9H2v6h4l5 4V5z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  </button>
</template>

<style scoped>
.speaker-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: #a1a1aa;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease, transform 0.15s ease;
}

.speaker-btn:hover {
  color: #4b3fe3;
  background: rgba(75, 63, 227, 0.1);
}

.speaker-btn:active {
  transform: scale(0.92);
}

.speaker-btn--active {
  color: #4b3fe3;
}

.speaker-btn--default {
  width: 28px;
  height: 28px;
}

.speaker-btn--default svg {
  width: 16px;
  height: 16px;
}

.speaker-btn--small {
  width: 22px;
  height: 22px;
}

.speaker-btn--small svg {
  width: 13px;
  height: 13px;
}

:global(html.dark) .speaker-btn:hover {
  color: #9b8cff;
  background: rgba(96, 84, 241, 0.18);
}

:global(html.dark) .speaker-btn--active {
  color: #9b8cff;
}
</style>
