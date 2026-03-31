<template>
  <section>
    <div class="surface-header">
      <div>
        <h2 class="surface-title">直播录制</h2>
        <p class="surface-sub">默认列表视图，支持筛选、排序、分页、列显隐与批量操作。</p>
      </div>
      <div class="toolbar-row">
        <n-tag :type="loading ? 'warning' : 'success'">{{ loading ? '加载中' : `最近刷新 ${lastUpdatedText}` }}</n-tag>
        <n-tag :type="pollingFailures > 0 ? 'error' : 'info'">
          轮询 {{ Math.floor(pollingDelayMs / 1000) }}s
          <template v-if="pollingFailures > 0"> · 连续失败 {{ pollingFailures }}</template>
        </n-tag>
        <n-button ghost @click="$emit('refresh')">刷新列表</n-button>
      </div>
    </div>

    <div class="block" style="display: grid; gap: 10px; border-bottom: 1px solid var(--line)">
      <div class="toolbar-row">
        <n-input
          :value="searchKeyword"
          style="width: min(300px, 100%)"
          placeholder="按任务名、URL、平台搜索"
          clearable
          @update:value="onSearchChange"
        />
        <n-select
          style="width: 180px"
          :value="localSortField"
          :options="sortFieldOptions"
          @update:value="onSortFieldChange"
        />
        <n-select
          style="width: 140px"
          :value="localSortOrder"
          :options="sortOrderOptions"
          @update:value="onSortOrderChange"
        />
        <n-select
          style="width: 180px"
          :value="platformFilter"
          :options="platformOptions"
          @update:value="(value) => $emit('update:platform-filter', value || '')"
        />
      </div>

      <n-alert v-if="boardFilter" type="info" :show-icon="false">
        <div class="toolbar-row" style="justify-content: space-between">
          <span>当前来自看板联动筛选：{{ boardFilterText }}</span>
          <n-button text type="primary" @click="$emit('clear-board-filter')">清除筛选</n-button>
        </div>
      </n-alert>

      <div class="form-grid">
        <n-input v-model:value="createForm.url" placeholder="直播间 URL（必填）" />
        <n-input v-model:value="createForm.quality" placeholder="画质，例如 原画" />
        <n-input v-model:value="createForm.anchor_name" placeholder="主播昵称（可选）" />
        <n-button type="primary" @click="submitCreateTask">新增任务</n-button>
      </div>

      <div class="column-box">
        <div class="toolbar-row" style="justify-content: space-between">
          <strong>列表列显隐</strong>
          <span class="surface-sub">设置会保存到浏览器本地</span>
        </div>
        <n-checkbox-group v-model:value="visibleColumns">
          <n-space>
            <n-checkbox v-for="item in columnOptions" :key="item.key" :value="item.key">
              {{ item.label }}
            </n-checkbox>
          </n-space>
        </n-checkbox-group>
      </div>

      <div class="toolbar-row" style="justify-content: space-between">
        <div class="toolbar-row">
          <n-button @click="selectCurrentPage">当前页全选</n-button>
          <n-button type="info" ghost @click="selectFilteredAll">当前筛选结果全选</n-button>
          <n-button @click="clearSelection">清空选择</n-button>
        </div>
        <div class="toolbar-row">
          <n-tag type="default">已选 {{ selectedTaskIds.length }} 条</n-tag>
          <n-tag v-if="selectAcrossFilter" type="warning">跨页选择</n-tag>
          <n-button type="success" @click="runBatchAction('start')">批量开始</n-button>
          <n-button type="warning" @click="runBatchAction('stop')">批量停止</n-button>
          <n-button @click="runBatchAction('enable')">批量恢复</n-button>
          <n-button type="error" ghost @click="runBatchAction('disable')">批量禁用</n-button>
          <n-button type="error" @click="runBatchAction('delete')">批量删除</n-button>
        </div>
      </div>
    </div>

    <div class="table-wrap">
      <table class="task-table">
        <thead>
          <tr>
            <th style="width: 42px">
              <n-checkbox :checked="isPageFullySelected" @update:checked="toggleCurrentPageSelection" />
            </th>
            <th v-if="isColumnVisible('platform')">平台</th>
            <th v-if="isColumnVisible('anchor_name')">主播</th>
            <th v-if="isColumnVisible('url')">URL</th>
            <th v-if="isColumnVisible('quality')">画质</th>
            <th v-if="isColumnVisible('live_status')">直播状态</th>
            <th v-if="isColumnVisible('recording_status')">录制状态</th>
            <th v-if="isColumnVisible('started_at')">录制开始</th>
            <th v-if="isColumnVisible('error_message')">错误信息</th>
            <th style="min-width: 280px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!pagedTasks.length">
            <td colspan="10" class="inline-empty">当前筛选下暂无任务</td>
          </tr>
          <tr v-for="task in pagedTasks" :key="task.task_id">
            <td>
              <n-checkbox :checked="selectedTaskIds.includes(task.task_id)" @update:checked="(v) => toggleRow(task.task_id, v)" />
            </td>
            <td v-if="isColumnVisible('platform')">{{ task.platform || 'other' }}</td>
            <td v-if="isColumnVisible('anchor_name')">{{ task.anchor_name || '--' }}</td>
            <td v-if="isColumnVisible('url')">{{ task.url }}</td>
            <td v-if="isColumnVisible('quality')">{{ task.quality || '--' }}</td>
            <td v-if="isColumnVisible('live_status')">{{ liveStatusText(task.live_status) }}</td>
            <td v-if="isColumnVisible('recording_status')">{{ recordingStatusText(task.recording_status) }}</td>
            <td v-if="isColumnVisible('started_at')">{{ formatDateTime(task.started_at as number | null | undefined) }}</td>
            <td v-if="isColumnVisible('error_message')">{{ task.error_message || '--' }}</td>
            <td>
              <div class="task-actions">
                <n-button size="tiny" type="success" @click="runSingleAction('start', task)">开始</n-button>
                <n-button size="tiny" type="warning" @click="runSingleAction('stop', task)">停止</n-button>
                <n-button size="tiny" @click="runSingleAction('enable', task)">恢复</n-button>
                <n-button size="tiny" type="error" ghost @click="runSingleAction('disable', task)">禁用</n-button>
                <n-button size="tiny" @click="openEdit(task)">编辑</n-button>
                <n-button size="tiny" type="error" @click="runSingleAction('delete', task)">删除</n-button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="block" style="border-top: 1px solid var(--line); display: flex; justify-content: flex-end">
      <n-pagination
        :page="page"
        :page-size="pageSize"
        :page-count="pageCount"
        :page-sizes="[10, 20, 50, 100]"
        show-size-picker
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
      />
    </div>

    <n-modal v-model:show="editingVisible" preset="card" style="width: min(560px, calc(100vw - 24px))" title="编辑任务">
      <n-space vertical>
        <n-input v-model:value="editForm.url" placeholder="URL" />
        <n-input v-model:value="editForm.quality" placeholder="画质" />
        <n-input v-model:value="editForm.anchor_name" placeholder="主播昵称" />
        <n-space justify="end">
          <n-button @click="editingVisible = false">取消</n-button>
          <n-button type="primary" @click="submitEditTask">保存</n-button>
        </n-space>
      </n-space>
    </n-modal>

    <n-modal v-model:show="batchResultVisible" preset="card" style="width: min(680px, calc(100vw - 24px))" title="批量执行结果">
      <n-space vertical>
        <n-alert type="info" :show-icon="false">
          {{ batchResult.action }}：成功 {{ batchResult.success }} 条，失败 {{ batchResult.failed }} 条。
        </n-alert>
        <n-collapse v-if="batchResult.details.length">
          <n-collapse-item title="失败明细" name="details">
            <n-space vertical>
              <n-text v-for="line in batchResult.details" :key="line">{{ line }}</n-text>
            </n-space>
          </n-collapse-item>
        </n-collapse>
      </n-space>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NCollapse,
  NCollapseItem,
  NInput,
  NModal,
  NPagination,
  NSelect,
  NSpace,
  NTag,
  NText,
  useMessage,
} from 'naive-ui'
import type { TaskItem } from '../types'
import type { BoardColumn } from '../utils/status'
import { formatDateTime } from '../utils/format'
import { liveStatusText, recordingStatusText, resolveBoardColumn } from '../utils/status'
import { createTask, deleteTask, startTask, stopTask, updateTask } from '../api/runtime'

interface BatchResult {
  action: string
  success: number
  failed: number
  details: string[]
}

const props = defineProps<{
  tasks: TaskItem[]
  loading: boolean
  boardFilter: BoardColumn | ''
  platformFilter: string
  lastUpdatedAt: number
  pollingDelayMs: number
  pollingFailures: number
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'update:platform-filter', value: string): void
  (e: 'clear-board-filter'): void
}>()

const message = useMessage()
const PREFERENCE_KEY = 'dlr-v2-recording-preferences'

const searchKeyword = ref('')
const localSortField = ref('updated_at')
const localSortOrder = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = ref(20)
const selectedTaskIds = ref<string[]>([])
const selectAcrossFilter = ref(false)

const editingVisible = ref(false)
const batchResultVisible = ref(false)

const createForm = reactive({
  url: '',
  quality: '原画',
  anchor_name: '',
})

const editForm = reactive({
  task_id: '',
  url: '',
  quality: '原画',
  anchor_name: '',
})

const batchResult = reactive<BatchResult>({
  action: '',
  success: 0,
  failed: 0,
  details: [],
})

const columnOptions = [
  { key: 'platform', label: '平台' },
  { key: 'anchor_name', label: '主播' },
  { key: 'url', label: 'URL' },
  { key: 'quality', label: '画质' },
  { key: 'live_status', label: '直播状态' },
  { key: 'recording_status', label: '录制状态' },
  { key: 'started_at', label: '录制开始' },
  { key: 'error_message', label: '错误信息' },
]

const visibleColumns = ref<string[]>(columnOptions.map((item) => item.key))

const sortFieldOptions = [
  { label: '按更新时间', value: 'updated_at' },
  { label: '按任务名', value: 'anchor_name' },
  { label: '按平台', value: 'platform' },
  { label: '按直播状态', value: 'live_status' },
  { label: '按录制状态', value: 'recording_status' },
  { label: '按录制开始时间', value: 'started_at' },
]

const sortOrderOptions = [
  { label: '降序', value: 'desc' },
  { label: '升序', value: 'asc' },
]

const boardFilterText = computed(() => {
  if (props.boardFilter === 'live') return '正在直播'
  if (props.boardFilter === 'recording') return '正在录制'
  if (props.boardFilter === 'not_live') return '未开播'
  return ''
})

const platformOptions = computed(() => {
  const platforms = Array.from(
    new Set<string>(props.tasks.map((item) => String(item.platform || 'other'))),
  ).sort()
  const options = [{ label: '全部平台', value: '' }]
  platforms.forEach((item) => options.push({ label: item, value: item }))
  if (props.platformFilter && !platforms.includes(props.platformFilter)) {
    options.push({ label: props.platformFilter, value: props.platformFilter })
  }
  return options
})

const lastUpdatedText = computed(() => {
  if (!props.lastUpdatedAt) {
    return '--'
  }
  return new Date(props.lastUpdatedAt).toLocaleTimeString('zh-CN', { hour12: false })
})

const filteredTasks = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return props.tasks.filter((task) => {
    if (props.platformFilter && String(task.platform || '').toLowerCase() !== props.platformFilter.toLowerCase()) {
      return false
    }

    if (props.boardFilter && resolveBoardColumn(task) !== props.boardFilter) {
      return false
    }

    if (!keyword) {
      return true
    }

    const haystacks = [
      String(task.anchor_name || ''),
      String(task.url || ''),
      String(task.platform || ''),
      String(task.quality || ''),
      String(task.error_message || ''),
    ]
    return haystacks.some((item) => item.toLowerCase().includes(keyword))
  })
})

function getSortValue(task: TaskItem): string | number {
  const field = localSortField.value
  if (field === 'started_at') {
    return Number(task.started_at || 0)
  }
  if (field === 'updated_at') {
    return Number(task.updated_at || 0)
  }
  return String(task[field] || '').toLowerCase()
}

const sortedTasks = computed(() => {
  const copied = [...filteredTasks.value]
  const direction = localSortOrder.value === 'asc' ? 1 : -1
  copied.sort((a, b) => {
    const left = getSortValue(a)
    const right = getSortValue(b)
    if (left < right) return -1 * direction
    if (left > right) return 1 * direction
    return 0
  })
  return copied
})

const pageCount = computed(() => {
  return Math.max(1, Math.ceil(sortedTasks.value.length / pageSize.value))
})

const pagedTasks = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return sortedTasks.value.slice(start, end)
})

const isPageFullySelected = computed(() => {
  if (!pagedTasks.value.length) {
    return false
  }
  return pagedTasks.value.every((item) => selectedTaskIds.value.includes(item.task_id))
})

const selectedTasks = computed(() => {
  const idSet = new Set(selectedTaskIds.value)
  return sortedTasks.value.filter((item) => idSet.has(item.task_id))
})

const filterFingerprint = computed(() => {
  return JSON.stringify({
    platform: props.platformFilter,
    board: props.boardFilter,
    keyword: searchKeyword.value,
  })
})

const loadPreferences = () => {
  try {
    const raw = localStorage.getItem(PREFERENCE_KEY)
    if (!raw) {
      return
    }
    const payload = JSON.parse(raw)
    if (Array.isArray(payload.visibleColumns) && payload.visibleColumns.length) {
      visibleColumns.value = payload.visibleColumns
    }
    if (typeof payload.pageSize === 'number' && payload.pageSize > 0) {
      pageSize.value = payload.pageSize
    }
    if (typeof payload.sortField === 'string') {
      localSortField.value = payload.sortField
    }
    if (payload.sortOrder === 'asc' || payload.sortOrder === 'desc') {
      localSortOrder.value = payload.sortOrder
    }
  } catch {
  }
}

const savePreferences = () => {
  const payload = {
    visibleColumns: visibleColumns.value,
    pageSize: pageSize.value,
    sortField: localSortField.value,
    sortOrder: localSortOrder.value,
  }
  localStorage.setItem(PREFERENCE_KEY, JSON.stringify(payload))
}

loadPreferences()

watch([visibleColumns, pageSize, localSortField, localSortOrder], savePreferences, { deep: true })

watch(filterFingerprint, (_, oldValue) => {
  if (!oldValue) {
    return
  }
  page.value = 1
  if (selectAcrossFilter.value) {
    selectedTaskIds.value = []
    selectAcrossFilter.value = false
    message.info('筛选条件已变化，跨页选择已清空')
  }
})

watch(pageCount, (value) => {
  if (page.value > value) {
    page.value = value
  }
})

const isColumnVisible = (column: string) => visibleColumns.value.includes(column)

const onSearchChange = (value: string) => {
  searchKeyword.value = value || ''
}

const onSortFieldChange = (value: string) => {
  localSortField.value = value
}

const onSortOrderChange = (value: 'asc' | 'desc') => {
  localSortOrder.value = value
}

const onPageChange = (value: number) => {
  page.value = value
}

const onPageSizeChange = (value: number) => {
  pageSize.value = value
  page.value = 1
}

const toggleRow = (taskId: string, checked: boolean) => {
  const idSet = new Set(selectedTaskIds.value)
  if (checked) {
    idSet.add(taskId)
  } else {
    idSet.delete(taskId)
  }
  selectedTaskIds.value = Array.from(idSet)
}

const toggleCurrentPageSelection = (checked: boolean) => {
  if (checked) {
    selectCurrentPage()
  } else {
    pagedTasks.value.forEach((item) => {
      toggleRow(item.task_id, false)
    })
  }
}

const selectCurrentPage = () => {
  const idSet = new Set(selectedTaskIds.value)
  pagedTasks.value.forEach((item) => idSet.add(item.task_id))
  selectedTaskIds.value = Array.from(idSet)
  selectAcrossFilter.value = false
}

const selectFilteredAll = () => {
  if (!sortedTasks.value.length) {
    message.warning('当前筛选结果为空，无法全选')
    return
  }
  const ok = window.confirm(`确认全选当前筛选结果 ${sortedTasks.value.length} 条任务吗？`)
  if (!ok) {
    return
  }
  selectedTaskIds.value = sortedTasks.value.map((item) => item.task_id)
  selectAcrossFilter.value = true
}

const clearSelection = () => {
  selectedTaskIds.value = []
  selectAcrossFilter.value = false
}

const submitCreateTask = async () => {
  const url = createForm.url.trim()
  if (!url) {
    message.warning('请先输入直播间 URL')
    return
  }

  try {
    await createTask({
      url,
      quality: (createForm.quality || '原画').trim() || '原画',
      anchor_name: createForm.anchor_name.trim(),
    })
    createForm.url = ''
    createForm.quality = '原画'
    createForm.anchor_name = ''
    message.success('任务创建成功')
    emit('refresh')
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error))
  }
}

const openEdit = (task: TaskItem) => {
  editForm.task_id = task.task_id
  editForm.url = String(task.url || '')
  editForm.quality = String(task.quality || '原画')
  editForm.anchor_name = String(task.anchor_name || '')
  editingVisible.value = true
}

const submitEditTask = async () => {
  if (!editForm.task_id || !editForm.url.trim()) {
    message.warning('URL 不能为空')
    return
  }

  try {
    await updateTask(editForm.task_id, {
      url: editForm.url.trim(),
      quality: editForm.quality.trim() || '原画',
      anchor_name: editForm.anchor_name.trim(),
    })
    editingVisible.value = false
    message.success('任务更新成功')
    emit('refresh')
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error))
  }
}

const executeTaskAction = async (action: string, task: TaskItem): Promise<{ ok: boolean; reason: string }> => {
  try {
    if (action === 'start') {
      const response = await startTask(task.task_id)
      if (response.record_started === false && response.message) {
        return { ok: false, reason: response.message }
      }
      return { ok: true, reason: '' }
    }

    if (action === 'stop') {
      await stopTask(task.task_id, false)
      return { ok: true, reason: '' }
    }

    if (action === 'enable') {
      const response = await startTask(task.task_id)
      if (response.record_started === false && response.message) {
        return { ok: false, reason: response.message }
      }
      return { ok: true, reason: '' }
    }

    if (action === 'disable') {
      await stopTask(task.task_id, true)
      return { ok: true, reason: '' }
    }

    if (action === 'delete') {
      await deleteTask(task.task_id)
      return { ok: true, reason: '' }
    }

    return { ok: false, reason: '未知操作' }
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) }
  }
}

const runSingleAction = async (action: string, task: TaskItem) => {
  if (action === 'delete') {
    const ok = window.confirm(`确认删除任务：${task.anchor_name || task.url} 吗？`)
    if (!ok) {
      return
    }
  }
  if (action === 'disable') {
    const ok = window.confirm(`确认禁用任务：${task.anchor_name || task.url} 吗？`)
    if (!ok) {
      return
    }
  }

  const result = await executeTaskAction(action, task)
  if (result.ok) {
    message.success('操作成功')
  } else {
    message.error(result.reason || '操作失败')
  }
  emit('refresh')
}

const runBatchAction = async (action: 'start' | 'stop' | 'enable' | 'disable' | 'delete') => {
  if (!selectedTasks.value.length) {
    message.warning('请先选择要操作的任务')
    return
  }

  const actionLabelMap: Record<string, string> = {
    start: '批量开始',
    stop: '批量停止',
    enable: '批量恢复',
    disable: '批量禁用',
    delete: '批量删除',
  }

  if (action === 'disable' || action === 'delete' || action === 'stop') {
    const ok = window.confirm(`确认执行${actionLabelMap[action]}，影响 ${selectedTasks.value.length} 条任务吗？`)
    if (!ok) {
      return
    }
  }

  batchResult.action = actionLabelMap[action]
  batchResult.success = 0
  batchResult.failed = 0
  batchResult.details = []

  for (const task of selectedTasks.value) {
    const result = await executeTaskAction(action, task)
    if (result.ok) {
      batchResult.success += 1
      continue
    }

    batchResult.failed += 1
    batchResult.details.push(`${task.anchor_name || task.url}: ${result.reason}`)
  }

  const summary = `成功 ${batchResult.success} 条，失败 ${batchResult.failed} 条`
  if (batchResult.failed > 0) {
    message.warning(`${actionLabelMap[action]}完成：${summary}`)
  } else {
    message.success(`${actionLabelMap[action]}完成：${summary}`)
  }

  batchResultVisible.value = true
  clearSelection()
  emit('refresh')
}
</script>
