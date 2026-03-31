<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-shell">
        <header class="app-header">
          <div>
            <h1 class="brand-title">DouyinLiveRecorder 控制台 v2</h1>
            <p class="brand-sub">
              直播录制与看板遵循 3 秒完成驱动轮询，失败按 3s/6s/12s/24s 退避，成功恢复为 3s。
            </p>
          </div>
          <div class="header-actions">
            <n-select
              style="width: 180px"
              :value="platformFilter"
              :options="platformOptions"
              @update:value="onPlatformChange"
            />
            <n-tag :type="pollTagType" size="small">
              {{ pollTagText }}
            </n-tag>
            <n-button ghost @click="manualRefresh">立即刷新</n-button>
            <n-button type="warning" @click="switchToLegacy">切回旧版</n-button>
          </div>
        </header>

        <main class="content-wrap">
          <n-tabs v-model:value="activeTab" type="line" animated>
            <n-tab-pane name="recordings" tab="直播录制">
              <RecordingView
                class="surface"
                :tasks="tasks"
                :loading="loading"
                :board-filter="boardFilter"
                :platform-filter="platformFilter"
                :last-updated-at="lastUpdatedAt"
                :polling-delay-ms="pollingDelayMs"
                :polling-failures="pollingFailures"
                @refresh="manualRefresh"
                @update:platform-filter="onPlatformChange"
                @clear-board-filter="clearBoardFilter"
              />
            </n-tab-pane>

            <n-tab-pane name="dashboard" tab="看板">
              <DashboardView
                class="surface"
                :tasks="tasks"
                :dashboard="dashboard"
                :loading="loading"
                :last-updated-at="lastUpdatedAt"
                @refresh="manualRefresh"
                @jump-to-recordings="jumpToRecordings"
              />
            </n-tab-pane>

            <n-tab-pane name="settings" tab="设置">
              <SettingsView class="surface" :active="activeTab === 'settings'" />
            </n-tab-pane>
          </n-tabs>

          <n-alert v-if="loadError" style="margin-top: 10px" type="error" :show-icon="true">
            {{ loadError }}
          </n-alert>
        </main>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NConfigProvider,
  NMessageProvider,
  NSelect,
  NTabPane,
  NTabs,
  NTag,
} from 'naive-ui'
import RecordingView from './views/RecordingView.vue'
import DashboardView from './views/DashboardView.vue'
import SettingsView from './views/SettingsView.vue'
import { listTasks, getDashboard } from './api/runtime'
import { useCompletionPolling } from './composables/usePolling'
import type { DashboardPayload, TaskItem } from './types'
import type { BoardColumn } from './utils/status'

const SESSION_KEY = 'douyin_live_recorder_ui_version'

const activeTab = ref<'recordings' | 'dashboard' | 'settings'>('recordings')
const platformFilter = ref('')
const boardFilter = ref<BoardColumn | ''>('')
const tasks = ref<TaskItem[]>([])
const dashboard = ref<DashboardPayload | null>(null)
const loading = ref(false)
const loadError = ref('')
const lastUpdatedAt = ref(0)

const themeOverrides = {
  common: {
    fontFamily: 'IBM Plex Sans SC, Microsoft YaHei, sans-serif',
    primaryColor: '#0f9d9a',
    primaryColorHover: '#0b8a88',
    primaryColorPressed: '#087774',
    borderRadius: '10px',
  },
}

const platformOptions = computed(() => {
  const platforms = Array.from(
    new Set<string>(tasks.value.map((item) => String(item.platform || 'other'))),
  ).sort()
  const options = [{ label: '全部平台', value: '' }]
  platforms.forEach((item) => options.push({ label: item, value: item }))
  if (platformFilter.value && !platforms.includes(platformFilter.value)) {
    options.push({ label: platformFilter.value, value: platformFilter.value })
  }
  return options
})

const refreshRuntime = async (signal?: AbortSignal) => {
  if (loading.value) {
    return
  }

  loading.value = true
  try {
    const [tasksPayload, dashboardPayload] = await Promise.all([
      listTasks(platformFilter.value, signal),
      getDashboard(platformFilter.value, signal),
    ])

    tasks.value = Array.isArray(tasksPayload.items) ? tasksPayload.items : []
    dashboard.value = dashboardPayload
    loadError.value = ''
    lastUpdatedAt.value = Date.now()
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === 'AbortError'
    if (!aborted) {
      loadError.value = error instanceof Error ? error.message : String(error)
    }
  } finally {
    loading.value = false
  }
}

const poller = useCompletionPolling(async (signal) => {
  await refreshRuntime(signal)
}, { baseIntervalMs: 3000, maxIntervalMs: 30000 })

const pollTagType = computed(() => {
  if (poller.failureCount.value > 0) {
    return 'error'
  }
  return poller.running.value ? 'success' : 'info'
})

const pollTagText = computed(() => {
  const delayText = `${Math.floor(poller.currentDelay.value / 1000)}s`
  if (poller.failureCount.value > 0) {
    return `轮询退避中 ${delayText} · 连续失败 ${poller.failureCount.value}`
  }
  return poller.running.value ? '轮询请求中' : `轮询间隔 ${delayText}`
})

const pollingDelayMs = computed(() => poller.currentDelay.value)
const pollingFailures = computed(() => poller.failureCount.value)

const shouldRunRuntimePolling = computed(() => activeTab.value !== 'settings')

const ensurePollingState = () => {
  if (document.visibilityState !== 'visible') {
    poller.stop()
    return
  }

  if (shouldRunRuntimePolling.value) {
    poller.start()
  } else {
    poller.stop()
  }
}

const onVisibilityChange = () => {
  ensurePollingState()
}

const manualRefresh = async () => {
  if (shouldRunRuntimePolling.value) {
    await poller.trigger()
    return
  }
  await refreshRuntime()
}

const onPlatformChange = (value: string) => {
  platformFilter.value = value || ''
}

const jumpToRecordings = (column: BoardColumn) => {
  boardFilter.value = column
  activeTab.value = 'recordings'
}

const clearBoardFilter = () => {
  boardFilter.value = ''
}

const switchToLegacy = () => {
  try {
    sessionStorage.setItem(SESSION_KEY, 'v1')
  } catch {
  }
  window.location.href = '/ui/v1?ui=v1'
}

watch(activeTab, () => {
  ensurePollingState()
})

watch(platformFilter, async () => {
  if (shouldRunRuntimePolling.value) {
    await manualRefresh()
  }
})

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  ensurePollingState()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  poller.stop()
})
</script>
