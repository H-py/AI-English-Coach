import { ref } from 'vue'
import { createUtterance, isSpeechSupported } from '@/utils/speech'

/**
 * 文章朗读 composable：分块朗读 + 播放控制 + 高亮范围。
 *
 * 设计要点：
 *  - 按句子切分正文，但以"朗读块"为单位朗读（同一段落内相邻句子合并，
 *    约 120 字符 / 2-3 句），块内由 TTS 在句号处自然停顿，明显减少
 *    逐句切换 utterance 造成的句间停顿；
 *  - 段落之间不跨块合并，保留段落的自然停顿；
 *  - 块间通过 onend 串联推进，每块朗读前 cancel + resume 重置引擎
 *    （规避 speechSynthesis 连续朗读后挂起的已知 bug）；
 *  - 单个朗读块控制在 120 字符内，规避 Chrome 对长文本约 15 秒后
 *    自动暂停的已知 bug；
 *  - 暂停 = 取消当前块并记录索引，恢复 = 从当前块重新朗读；
 *  - 句子切分时保护小数中的小数点（如 4.6、5.6%），避免被误判为句号。
 */

/** 朗读块最大字符数 */
const MAX_BLOCK_CHARS = 120
/** 小数点保护占位符（私有区字符，正文不会出现） */
const DOT_PLACEHOLDER = '\uE000'

/** 按句子切分一行文本（句号/感叹号/问号为边界，忽略数字间的小数点） */
function splitLine(line: string): string[] {
  const trimmed = line.trim()
  if (!trimmed) return []
  // 保护小数/百分号中的小数点（如 4.6、5.6%），避免被误判为句号
  const protectedText = trimmed.replace(
    /(\d)\.(\d)/g,
    `$1${DOT_PLACEHOLDER}$2`
  )
  const parts = protectedText.match(/[^.!?。！？]+[.!?。！？]*/g) ?? [protectedText]
  return parts
    .map((s) => s.replace(new RegExp(DOT_PLACEHOLDER, 'g'), '.').trim())
    .filter((s) => s.length > 0)
}

/** 一段文本 -> 行数组，每行是带全局索引的句子数组 */
export interface SentenceRef {
  text: string
  globalIndex: number
}

/**
 * 按段落拆分文章正文，供 UI 逐句渲染（高亮）与朗读共用。
 * 全局索引即朗读顺序（与 splitSentences 保持一致）。
 */
export function splitContent(content: string): SentenceRef[][] {
  if (!content) return []
  let gi = 0
  return content
    .split('\n')
    .map((line) =>
      splitLine(line).map((text) => ({ text, globalIndex: gi++ }))
    )
    .filter((line) => line.length > 0)
}

/** 文章正文 -> 句子列表（朗读顺序与 splitContent 的 globalIndex 一致） */
export function splitSentences(content: string): string[] {
  return splitContent(content)
    .flat()
    .map((s) => s.text)
}

/** 朗读块：段落内若干连续句子合并为一个 utterance */
export interface SpeechBlock {
  text: string
  from: number
  to: number
}

/** 构建朗读块：段落内合并相邻句子，超过字符上限则切分；段落间不跨块 */
function buildBlocks(lines: SentenceRef[][]): SpeechBlock[] {
  const blocks: SpeechBlock[] = []
  let cur: SpeechBlock | null = null
  let chars = 0

  for (const line of lines) {
    for (const s of line) {
      if (!cur) {
        cur = { text: s.text, from: s.globalIndex, to: s.globalIndex }
        chars = s.text.length
        continue
      }
      if (chars + s.text.length + 1 > MAX_BLOCK_CHARS) {
        blocks.push(cur)
        cur = { text: s.text, from: s.globalIndex, to: s.globalIndex }
        chars = s.text.length
      } else {
        cur.text += ' ' + s.text
        cur.to = s.globalIndex
        chars += s.text.length + 1
      }
    }
    // 段落结束：封口当前块（保持段间停顿）
    if (cur) {
      blocks.push(cur)
      cur = null
      chars = 0
    }
  }
  if (cur) blocks.push(cur)

  return blocks
}

export function useArticleSpeech() {
  /** 是否处于朗读会话中（含暂停态） */
  const isPlaying = ref(false)
  /** 是否暂停 */
  const isPaused = ref(false)
  /** 当前朗读块的句子范围（含边界），用于 UI 高亮 */
  const currentRange = ref<{ from: number; to: number } | null>(null)
  /** 当前朗读块索引（0-based），用于进度条 */
  const currentBlockIndex = ref(0)
  /** 朗读块总数，用于进度条 */
  const totalBlocks = ref(0)
  /** 语速（0.75 / 1 / 1.25） */
  const rate = ref(1)

  /** 可调节的语速选项 */
  const rateOptions = [0.75, 1, 1.25]

  let blocks: SpeechBlock[] = []
  let stuckTimer: number | null = null
  /**
   * 会话代际：每次 start / pause / seek / setRate / stop 都会递增。
   * speakBlock 创建 utterance 时捕获当时的代际；回调触发时若代际已
   * 变化（说明该 utterance 已被暂停/跳转/停止取代），直接失效。
   * 这解决了 speechSynthesis.cancel() 异步生效、旧 utterance 的
   * onend 仍会触发，导致"暂停了还在朗读 / 进度条乱跳"的问题。
   */
  let generation = 0

  function clearStuckTimer(): void {
    if (stuckTimer !== null) {
      window.clearTimeout(stuckTimer)
      stuckTimer = null
    }
  }

  function resetSynth(): void {
    if (!isSpeechSupported()) return
    try {
      window.speechSynthesis.cancel()
      window.speechSynthesis.resume()
    } catch {
      // 忽略
    }
  }

  /** 朗读指定索引的块；越界则结束会话 */
  function speakBlock(index: number): void {
    if (index < 0 || index >= blocks.length) {
      stop()
      return
    }

    // 清理可能悬空的兜底定时器（seek / resume 等打断场景）
    clearStuckTimer()

    const gen = generation
    currentBlockIndex.value = index
    const block = blocks[index]
    currentRange.value = { from: block.from, to: block.to }
    resetSynth()

    const utterance = createUtterance(block.text, rate.value)
    utterance.onend = () => {
      clearStuckTimer()
      // 该 utterance 已被取代（暂停/跳转/停止），不再继续推进
      if (gen !== generation) return
      speakBlock(index + 1)
    }
    utterance.onerror = () => {
      clearStuckTimer()
      if (gen !== generation) return
      // 单块失败跳过，继续下一块
      speakBlock(index + 1)
    }

    window.speechSynthesis.speak(utterance)

    // 兜底：引擎卡死（长时间未触发 end）时重置并安全退出
    stuckTimer = window.setTimeout(() => {
      if (gen !== generation) return
      resetSynth()
      stop()
    }, 20000)
  }

  /** 开始朗读整篇文章 */
  function start(content: string): void {
    stop()
    const lines = splitContent(content)
    if (lines.length === 0 || !isSpeechSupported()) return
    blocks = buildBlocks(lines)
    totalBlocks.value = blocks.length
    isPlaying.value = true
    isPaused.value = false
    speakBlock(0)
  }

  /** 暂停：取消当前块并使其回调失效，恢复时从当前块重读 */
  function pause(): void {
    if (!isPlaying.value || isPaused.value) return
    isPaused.value = true
    generation++
    clearStuckTimer()
    if (isSpeechSupported()) window.speechSynthesis.cancel()
  }

  /** 恢复朗读（从当前块重读） */
  function resume(): void {
    if (!isPlaying.value || !isPaused.value) return
    isPaused.value = false
    speakBlock(currentBlockIndex.value)
  }

  /** 跳转到指定朗读块并开始朗读（进度条拖拽） */
  function seekTo(index: number): void {
    if (!isPlaying.value || index < 0 || index >= blocks.length) return
    isPaused.value = false
    generation++
    speakBlock(index)
  }

  /** 停止朗读并重置所有状态 */
  function stop(): void {
    generation++
    if (isSpeechSupported()) window.speechSynthesis.cancel()
    clearStuckTimer()
    blocks = []
    isPlaying.value = false
    isPaused.value = false
    currentRange.value = null
    currentBlockIndex.value = 0
    totalBlocks.value = 0
  }

  /** 切换语速；播放中切换则重读当前块 */
  function setRate(r: number): void {
    rate.value = r
    if (isPlaying.value && !isPaused.value && blocks.length > 0) {
      generation++
      speakBlock(currentBlockIndex.value)
    }
  }

  return {
    // state
    isPlaying,
    isPaused,
    currentRange,
    currentBlockIndex,
    totalBlocks,
    rate,
    rateOptions,
    // helpers
    splitContent,
    splitSentences,
    // actions
    start,
    pause,
    resume,
    seekTo,
    stop,
    setRate
  }
}
