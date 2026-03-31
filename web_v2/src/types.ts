export type TaskState =
  | 'offline'
  | 'monitoring'
  | 'live_not_recording'
  | 'recording'
  | 'stopping'
  | 'failed'
  | string

export interface TaskItem {
  task_id: string
  url: string
  quality: string
  anchor_name: string
  enabled: boolean
  state: TaskState
  platform?: string
  live_status?: string
  recording_status?: string
  started_at?: number | null
  error_message?: string
  [key: string]: unknown
}

export interface DashboardSummary {
  total?: number
  enabled?: number
  disabled?: number
  monitoring?: number
  live_not_recording?: number
  recording?: number
  stopping?: number
  failed?: number
  offline?: number
  by_platform?: Record<string, number>
}

export interface DashboardMetricBase<T> {
  raw: T
  unit: string
  sampled_at: number
  available: boolean
  error?: string
}

export interface DashboardMetrics {
  uptime?: DashboardMetricBase<number>
  disk?: DashboardMetricBase<{
    used_gib: number
    total_gib: number
    free_gib: number
    usage_ratio: number
  } | null>
}

export interface DashboardPayload {
  summary: DashboardSummary
  by_state: Record<string, number>
  items: TaskItem[]
  metrics?: DashboardMetrics
}

export interface TasksPayload {
  items: TaskItem[]
}

export interface TaskResponse {
  item: TaskItem
  record_started?: boolean
  message?: string
}

export interface DeleteTaskResponse {
  deleted: boolean
}

export type SettingFieldType = 'string' | 'enum' | 'bool' | 'int' | 'float'

export interface SettingSchemaItem {
  field: string
  label: string
  group: string
  batch: number
  type: SettingFieldType
  default: string | number | boolean
  effect: string
  choices?: string[]
  minimum?: number
  maximum?: number
}

export interface SettingsPayload {
  schema: SettingSchemaItem[]
  values: Record<string, string | number | boolean | null>
  last_reload: {
    success: boolean
    changed: boolean
    reloaded_at: number
    config_mtime: number
    warnings: string[]
    error: string
  }
}

export interface SettingsUpdateResponse {
  success: boolean
  updated_fields: Record<string, boolean>
  errors: Record<string, string>
  settings: SettingsPayload
}
