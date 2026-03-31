import type { TaskItem } from '../types'

export type BoardColumn = 'live' | 'recording' | 'not_live'

export function resolveBoardColumn(task: TaskItem): BoardColumn {
  const state = String(task.state || '').toLowerCase()
  const liveStatus = String(task.live_status || '').toLowerCase()
  const recordingStatus = String(task.recording_status || '').toLowerCase()

  if (state === 'recording' || state === 'stopping') {
    return 'recording'
  }
  if (state === 'live_not_recording') {
    return 'live'
  }
  if (state === 'monitoring' || state === 'offline') {
    return 'not_live'
  }

  if (state === 'failed') {
    if (recordingStatus === 'recording' || recordingStatus === 'stopping') {
      return 'recording'
    }
    if (liveStatus === 'live') {
      return 'live'
    }
    return 'not_live'
  }

  if (recordingStatus === 'recording' || recordingStatus === 'stopping') {
    return 'recording'
  }
  if (liveStatus === 'live') {
    return 'live'
  }
  return 'not_live'
}

export function liveStatusText(value: string | undefined): string {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'live') return '直播中'
  if (normalized === 'not_live') return '未开播'
  if (normalized === 'disabled') return '已禁用'
  return '未知'
}

export function recordingStatusText(value: string | undefined): string {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'recording') return '录制中'
  if (normalized === 'stopping') return '停止中'
  if (normalized === 'failed') return '失败'
  if (normalized === 'disabled') return '已禁用'
  return '空闲'
}
