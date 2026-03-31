import { requestJson } from './http'
import type {
  DashboardPayload,
  DeleteTaskResponse,
  SettingsPayload,
  SettingsUpdateResponse,
  TaskResponse,
  TasksPayload,
} from '../types'

function buildQuery(params: Record<string, string | undefined | null>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      search.set(key, String(value))
    }
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function listTasks(platform: string, signal?: AbortSignal) {
  return requestJson<TasksPayload>(`/api/v1/tasks${buildQuery({ platform })}`, { signal })
}

export function getDashboard(platform: string, signal?: AbortSignal) {
  return requestJson<DashboardPayload>(`/api/v1/dashboard${buildQuery({ platform })}`, { signal })
}

export function createTask(payload: { url: string; quality: string; anchor_name: string }) {
  return requestJson<TaskResponse>('/api/v1/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTask(taskId: string, payload: { url: string; quality: string; anchor_name: string; enabled?: boolean }) {
  return requestJson<TaskResponse>(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function startTask(taskId: string) {
  return requestJson<TaskResponse>(`/api/v1/tasks/${encodeURIComponent(taskId)}/start`, {
    method: 'POST',
  })
}

export function stopTask(taskId: string, disable: boolean) {
  return requestJson<TaskResponse>(`/api/v1/tasks/${encodeURIComponent(taskId)}/stop?disable=${disable ? 'true' : 'false'}`, {
    method: 'POST',
  })
}

export function deleteTask(taskId: string) {
  return requestJson<DeleteTaskResponse>(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
    method: 'DELETE',
  })
}

export function getSettings(signal?: AbortSignal) {
  return requestJson<SettingsPayload>('/api/v1/config/settings', { signal })
}

export function updateSettings(fields: Record<string, unknown>) {
  return requestJson<SettingsUpdateResponse>('/api/v1/config/update-settings', {
    method: 'POST',
    body: JSON.stringify({ fields }),
  })
}

export function reloadSettings() {
  return requestJson<Record<string, unknown>>('/api/v1/config/reload', {
    method: 'POST',
  })
}
