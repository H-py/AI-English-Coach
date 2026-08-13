/**
 * 浏览器原生 TTS 发音工具（Web Speech API）。
 *
 * 零依赖：使用浏览器内置的 speechSynthesis 朗读英文单词，
 * 无需网络请求与第三方服务。语音由操作系统提供（Windows / macOS 自带
 * 英文语音），音质清晰可懂，适合单词发音场景。
 *
 * 稳定性处理（Chrome/Edge 已知 bug）：
 *  - speechSynthesis 在连续朗读若干次后会进入"挂起"状态，后续 speak
 *    不再发声。业界通用 workaround：每次朗读前 cancel + resume 重置引擎；
 *  - utterance 结束/出错时主动 cancel，推动队列前进（Chrome 需要）；
 *  - 兜底定时器：若 utterance 长时间未触发 end（引擎卡死），强制重置。
 */

/** 缓存的英文语音（speechSynthesis 的语音列表可能异步加载） */
let cachedVoice: SpeechSynthesisVoice | null = null

/** 选择可用的英文语音（优先美音，其次英音，最后任意英文） */
function pickEnglishVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis?.getVoices() ?? []
  if (voices.length === 0) return null
  return (
    voices.find((v) => /^en[-_]US/i.test(v.lang)) ||
    voices.find((v) => /^en[-_]GB/i.test(v.lang)) ||
    voices.find((v) => /^en/i.test(v.lang)) ||
    null
  )
}

/** 重置语音引擎状态（Chrome 卡死 bug 的核心 workaround） */
function resetSynth(synth: SpeechSynthesis): void {
  try {
    synth.cancel()
    synth.resume()
  } catch {
    // 引擎异常时忽略，兜底定时器会再次尝试
  }
}

/**
 * 创建配置好的英文朗读 utterance。
 * 供单词发音与文章朗读共用，统一语音选择逻辑。
 */
export function createUtterance(text: string, rate = 0.9): SpeechSynthesisUtterance {
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = rate

  if (!cachedVoice) cachedVoice = pickEnglishVoice()
  if (cachedVoice) utterance.voice = cachedVoice

  return utterance
}

/** 朗读英文单词或短语 */
export function speakWord(word: string): void {
  if (!isSpeechSupported() || !word.trim()) return

  const synth = window.speechSynthesis
  const text = word.trim()

  // Chrome 卡死修复：每次朗读前重置引擎（cancel + resume）
  resetSynth(synth)

  const utterance = createUtterance(text, 0.9)

  // 兜底定时器：若引擎卡死（长时间未触发 end），强制重置
  let stuckTimer: number | null = null
  const clearStuckTimer = (): void => {
    if (stuckTimer !== null) {
      window.clearTimeout(stuckTimer)
      stuckTimer = null
    }
  }
  utterance.onend = () => {
    // Chrome bug：结束后主动 cancel 推动队列前进
    synth.cancel()
    clearStuckTimer()
  }
  utterance.onerror = clearStuckTimer

  synth.speak(utterance)

  // 超时未结束视为卡死，重置引擎以便下次朗读
  stuckTimer = window.setTimeout(() => {
    resetSynth(synth)
    clearStuckTimer()
  }, 10000)
}

/** 浏览器是否支持语音合成 */
export function isSpeechSupported(): boolean {
  return (
    typeof window !== 'undefined' && 'speechSynthesis' in window
  )
}

// 模块加载时预取英文语音；语音列表异步就绪后刷新缓存
if (isSpeechSupported()) {
  const refreshVoice = (): void => {
    cachedVoice = pickEnglishVoice()
  }
  refreshVoice()
  window.speechSynthesis.onvoiceschanged = refreshVoice
}
