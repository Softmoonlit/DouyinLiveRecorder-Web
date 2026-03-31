import { onBeforeUnmount, ref } from 'vue'

interface PollingOptions {
  baseIntervalMs?: number
  maxIntervalMs?: number
}

type PollingTask = (signal: AbortSignal) => Promise<void>

export function useCompletionPolling(task: PollingTask, options: PollingOptions = {}) {
  const baseIntervalMs = options.baseIntervalMs ?? 3000
  const maxIntervalMs = options.maxIntervalMs ?? 30000

  const active = ref(false)
  const running = ref(false)
  const failureCount = ref(0)
  const currentDelay = ref(baseIntervalMs)

  let timer: number | null = null
  let controller: AbortController | null = null

  const clearTimer = () => {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  const calculateDelay = (failures: number) => {
    if (failures <= 0) {
      return baseIntervalMs
    }
    const next = baseIntervalMs * 2 ** (failures - 1)
    return Math.min(next, maxIntervalMs)
  }

  const scheduleNext = () => {
    if (!active.value) {
      return
    }
    const delay = calculateDelay(failureCount.value)
    currentDelay.value = delay
    clearTimer()
    timer = window.setTimeout(() => {
      void run()
    }, delay)
  }

  const run = async () => {
    if (!active.value || running.value) {
      return
    }

    running.value = true
    controller = new AbortController()
    try {
      await task(controller.signal)
      failureCount.value = 0
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === 'AbortError'
      if (!aborted) {
        failureCount.value += 1
      }
    } finally {
      running.value = false
      controller = null
      scheduleNext()
    }
  }

  const start = () => {
    clearTimer()
    if (!active.value) {
      active.value = true
    }
    failureCount.value = 0
    currentDelay.value = baseIntervalMs
    void run()
  }

  const stop = () => {
    active.value = false
    clearTimer()
    if (controller) {
      controller.abort()
      controller = null
    }
  }

  const trigger = async () => {
    if (!active.value) {
      return
    }
    clearTimer()
    await run()
  }

  onBeforeUnmount(() => {
    stop()
  })

  return {
    active,
    running,
    failureCount,
    currentDelay,
    start,
    stop,
    trigger,
  }
}
