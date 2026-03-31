<template>
  <section>
    <div class="surface-header">
      <div>
        <h2 class="surface-title">运行看板</h2>
        <p class="surface-sub">高密度展示运行状态与指标，支持三列联动跳转录制页。</p>
      </div>
      <div class="toolbar-row">
        <n-tag :type="loading ? 'warning' : 'success'">
          {{ loading ? '加载中' : `最近刷新 ${lastUpdatedText}` }}
        </n-tag>
        <n-button ghost @click="$emit('refresh')">刷新看板</n-button>
      </div>
    </div>

    <div class="block">
      <div class="kpi-grid">
        <article v-for="card in summaryCards" :key="card.label" class="kpi-card">
          <h4>{{ card.label }}</h4>
          <div class="kpi-value">{{ card.value }}</div>
          <div class="surface-sub">{{ card.hint }}</div>
        </article>
      </div>
    </div>

    <div class="block" style="padding-top: 0">
      <div class="panel-grid">
        <section class="state-panel">
          <div class="state-panel-head">
            <strong>正在直播</strong>
            <n-button text type="info" @click="emitJump('live')">跳转录制页</n-button>
          </div>
          <div class="task-mini-list">
            <template v-if="liveColumn.length">
              <div v-for="task in liveColumn" :key="task.task_id" class="task-mini">
                <div class="task-mini-title">{{ task.anchor_name || task.url }}</div>
                <div class="task-mini-meta">{{ task.platform || 'other' }} · {{ task.url }}</div>
              </div>
            </template>
            <div v-else class="inline-empty">当前暂无直播中的任务</div>
          </div>
        </section>

        <section class="state-panel">
          <div class="state-panel-head">
            <strong>正在录制</strong>
            <n-button text type="info" @click="emitJump('recording')">跳转录制页</n-button>
          </div>
          <div class="task-mini-list">
            <template v-if="recordingColumn.length">
              <div v-for="task in recordingColumn" :key="task.task_id" class="task-mini">
                <div class="task-mini-title">{{ task.anchor_name || task.url }}</div>
                <div class="task-mini-meta">{{ task.platform || 'other' }} · {{ task.url }}</div>
              </div>
            </template>
            <div v-else class="inline-empty">当前暂无录制中的任务</div>
          </div>
        </section>

        <section class="state-panel">
          <div class="state-panel-head">
            <strong>未开播</strong>
            <n-button text type="info" @click="emitJump('not_live')">跳转录制页</n-button>
          </div>
          <div class="task-mini-list">
            <template v-if="notLiveColumn.length">
              <div v-for="task in notLiveColumn" :key="task.task_id" class="task-mini">
                <div class="task-mini-title">{{ task.anchor_name || task.url }}</div>
                <div class="task-mini-meta">{{ task.platform || 'other' }} · {{ task.url }}</div>
              </div>
            </template>
            <div v-else class="inline-empty">当前暂无未开播任务</div>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NTag } from 'naive-ui'
import type { DashboardPayload, TaskItem } from '../types'
import type { BoardColumn } from '../utils/status'
import { resolveBoardColumn } from '../utils/status'
import { formatGiB, formatPercent, formatUptime } from '../utils/format'

const props = defineProps<{
  tasks: TaskItem[]
  dashboard: DashboardPayload | null
  loading: boolean
  lastUpdatedAt: number
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'jump-to-recordings', column: BoardColumn): void
}>()

const sourceTasks = computed(() => {
  if (props.dashboard?.items && Array.isArray(props.dashboard.items)) {
    return props.dashboard.items
  }
  return props.tasks
})

const liveColumn = computed(() => sourceTasks.value.filter((item) => resolveBoardColumn(item) === 'live').slice(0, 18))
const recordingColumn = computed(() => sourceTasks.value.filter((item) => resolveBoardColumn(item) === 'recording').slice(0, 18))
const notLiveColumn = computed(() => sourceTasks.value.filter((item) => resolveBoardColumn(item) === 'not_live').slice(0, 18))

const lastUpdatedText = computed(() => {
  if (!props.lastUpdatedAt) {
    return '--'
  }
  return new Date(props.lastUpdatedAt).toLocaleTimeString('zh-CN', { hour12: false })
})

const summaryCards = computed(() => {
  const summary = props.dashboard?.summary || {}
  const uptime = props.dashboard?.metrics?.uptime
  const disk = props.dashboard?.metrics?.disk

  const diskText = disk?.available && disk.raw
    ? `${formatGiB(disk.raw.used_gib)} / ${formatGiB(disk.raw.total_gib)} (${formatPercent(disk.raw.usage_ratio)})`
    : '--'

  return [
    {
      label: '任务总数',
      value: summary.total ?? 0,
      hint: `启用 ${summary.enabled ?? 0} · 禁用 ${summary.disabled ?? 0}`,
    },
    {
      label: '录制中',
      value: summary.recording ?? 0,
      hint: `停止中 ${summary.stopping ?? 0} · 失败 ${summary.failed ?? 0}`,
    },
    {
      label: '运行时长',
      value: uptime?.available ? formatUptime(uptime.raw) : '--',
      hint: uptime?.available ? '按进程启动时间累计' : '指标暂不可用',
    },
    {
      label: '磁盘摘要',
      value: diskText,
      hint: disk?.available ? '单位 GiB，保留 1 位小数' : '指标暂不可用',
    },
  ]
})

const emitJump = (column: BoardColumn) => {
  emit('jump-to-recordings', column)
}
</script>
