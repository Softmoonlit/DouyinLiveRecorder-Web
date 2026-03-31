<template>
  <section>
    <div class="surface-header">
      <div>
        <h2 class="surface-title">设置</h2>
        <p class="surface-sub">基于后端 schema 渲染，仅提交脏字段，字段级错误就地反馈。</p>
      </div>
      <div class="toolbar-row">
        <n-tag :type="saving ? 'warning' : 'default'">
          {{ saving ? '保存中' : `脏字段 ${dirtyFields.length}` }}
        </n-tag>
        <n-button ghost :loading="loading" @click="loadSettings(true)">重新读取</n-button>
        <n-button type="primary" :loading="saving" @click="saveSettings">保存设置</n-button>
      </div>
    </div>

    <div class="block" style="display: grid; gap: 12px">
      <n-alert v-if="globalError" type="error">{{ globalError }}</n-alert>
      <n-alert v-if="globalSuccess" type="success">{{ globalSuccess }}</n-alert>

      <div v-if="loading" class="inline-empty">正在读取配置...</div>
      <div v-else class="settings-grid">
        <section v-for="group in groupedSchema" :key="group.group" class="settings-group">
          <h3 style="margin: 0 0 12px; font-size: 15px">{{ group.group }}</h3>

          <div v-for="item in group.items" :key="item.field" class="setting-item" v-show="!isFieldHidden(item.field)">
            <div class="setting-label">{{ item.label }}</div>

            <template v-if="item.type === 'bool'">
              <n-switch :value="Boolean(formValues[item.field])" @update:value="(v) => updateValue(item.field, v)" />
            </template>

            <template v-else-if="item.type === 'enum'">
              <n-select
                :value="String(formValues[item.field] ?? '')"
                :options="(item.choices || []).map((choice) => ({ label: choice, value: choice }))"
                @update:value="(v) => updateValue(item.field, v || '')"
              />
            </template>

            <template v-else>
              <n-input
                :value="String(formValues[item.field] ?? '')"
                @update:value="(v) => updateValue(item.field, v || '')"
              />
            </template>

            <div class="setting-help">{{ item.effect }}</div>
            <div v-if="fieldErrors[item.field]" class="setting-error">{{ fieldErrors[item.field] }}</div>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { NAlert, NButton, NInput, NSelect, NSwitch, NTag, useMessage } from 'naive-ui'
import { getSettings, updateSettings } from '../api/runtime'
import type { SettingSchemaItem, SettingsPayload, SettingsUpdateResponse } from '../types'

const props = defineProps<{
  active: boolean
}>()

const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const loaded = ref(false)
const globalError = ref('')
const globalSuccess = ref('')

const schemaList = ref<SettingSchemaItem[]>([])
const formValues = reactive<Record<string, unknown>>({})
const baselineValues = reactive<Record<string, unknown>>({})
const fieldErrors = reactive<Record<string, string>>({})
const autoDirtySet = ref<Set<string>>(new Set())

const schemaMap = computed(() => {
  const map: Record<string, SettingSchemaItem> = {}
  schemaList.value.forEach((item) => {
    map[item.field] = item
  })
  return map
})

const groupedSchema = computed(() => {
  const groupMap = new Map<string, { batch: number; items: SettingSchemaItem[] }>()
  schemaList.value.forEach((item) => {
    if (!groupMap.has(item.group)) {
      groupMap.set(item.group, { batch: item.batch, items: [] })
    }
    groupMap.get(item.group)!.items.push(item)
  })

  return Array.from(groupMap.entries())
    .sort((a, b) => a[1].batch - b[1].batch)
    .map(([group, value]) => ({ group, items: value.items }))
})

const isFieldHidden = (field: string): boolean => {
  if (field === 'split_time_seconds') {
    return !Boolean(formValues.split_recording)
  }
  if (field === 'convert_to_h264' || field === 'delete_origin_after_convert') {
    return !Boolean(formValues.convert_to_mp4)
  }
  if (field === 'proxy_addr') {
    return !Boolean(formValues.use_proxy)
  }
  return false
}

const normalizeInputValue = (schema: SettingSchemaItem, value: unknown): unknown => {
  if (schema.type === 'bool') {
    return Boolean(value)
  }

  if (value === undefined || value === null) {
    return ''
  }

  return String(value)
}

const normalizedForCompare = (schema: SettingSchemaItem, value: unknown): string => {
  if (schema.type === 'bool') {
    return String(Boolean(value))
  }
  if (schema.type === 'int') {
    const text = String(value ?? '').trim()
    const numberValue = Number(text)
    if (!Number.isNaN(numberValue) && Number.isFinite(numberValue) && Number.isInteger(numberValue)) {
      return String(numberValue)
    }
    return text
  }
  if (schema.type === 'float') {
    const text = String(value ?? '').trim()
    const numberValue = Number(text)
    if (!Number.isNaN(numberValue) && Number.isFinite(numberValue)) {
      return String(numberValue)
    }
    return text
  }
  return String(value ?? '').trim()
}

const dirtyFields = computed(() => {
  const fields = new Set<string>()
  schemaList.value.forEach((item) => {
    const current = normalizedForCompare(item, formValues[item.field])
    const baseline = normalizedForCompare(item, baselineValues[item.field])
    if (current !== baseline) {
      fields.add(item.field)
    }
  })
  autoDirtySet.value.forEach((field) => fields.add(field))
  return Array.from(fields)
})

const clearMessages = () => {
  globalError.value = ''
  globalSuccess.value = ''
}

const clearFieldError = (field: string) => {
  if (fieldErrors[field]) {
    delete fieldErrors[field]
  }
}

const clearAllFieldErrors = () => {
  Object.keys(fieldErrors).forEach((field) => {
    delete fieldErrors[field]
  })
}

const applySettingsPayload = (payload: SettingsPayload) => {
  schemaList.value = Array.isArray(payload.schema) ? payload.schema : []

  Object.keys(formValues).forEach((field) => {
    delete formValues[field]
  })
  Object.keys(baselineValues).forEach((field) => {
    delete baselineValues[field]
  })

  schemaList.value.forEach((schema) => {
    const incoming = payload.values?.[schema.field]
    const normalized = normalizeInputValue(schema, incoming)
    formValues[schema.field] = normalized
    baselineValues[schema.field] = normalized
  })

  autoDirtySet.value = new Set()
  clearAllFieldErrors()
}

const loadSettings = async (force = false) => {
  if (!props.active && !force) {
    return
  }
  if (loaded.value && !force) {
    return
  }

  loading.value = true
  clearMessages()

  try {
    const payload = await getSettings()
    applySettingsPayload(payload)
    loaded.value = true
    globalSuccess.value = '配置已同步'
  } catch (error) {
    globalError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

const assignEffectValue = (field: string, value: unknown) => {
  const previous = formValues[field]
  formValues[field] = value
  if (String(previous) !== String(value)) {
    autoDirtySet.value.add(field)
  }
  clearFieldError(field)
}

const applyEffectRules = (field: string) => {
  if (field === 'convert_to_mp4' && !Boolean(formValues.convert_to_mp4)) {
    assignEffectValue('convert_to_h264', false)
    assignEffectValue('delete_origin_after_convert', false)
  }

  if (field === 'use_proxy' && !Boolean(formValues.use_proxy)) {
    assignEffectValue('proxy_addr', '')
  }
}

const updateValue = (field: string, value: unknown) => {
  formValues[field] = value
  clearFieldError(field)
  clearMessages()
  applyEffectRules(field)
}

interface ParseResult {
  ok: boolean
  value: unknown
  message: string
}

const parseFieldValue = (schema: SettingSchemaItem, rawValue: unknown): ParseResult => {
  if (schema.type === 'bool') {
    return { ok: true, value: Boolean(rawValue), message: '' }
  }

  const text = String(rawValue ?? '').trim()

  if (schema.type === 'int') {
    const numberValue = Number(text)
    if (!Number.isFinite(numberValue) || !Number.isInteger(numberValue)) {
      return { ok: false, value: null, message: '请输入整数' }
    }
    if (schema.minimum !== undefined && numberValue < schema.minimum) {
      return { ok: false, value: null, message: `不能小于 ${schema.minimum}` }
    }
    if (schema.maximum !== undefined && numberValue > schema.maximum) {
      return { ok: false, value: null, message: `不能大于 ${schema.maximum}` }
    }
    return { ok: true, value: numberValue, message: '' }
  }

  if (schema.type === 'float') {
    const numberValue = Number(text)
    if (!Number.isFinite(numberValue)) {
      return { ok: false, value: null, message: '请输入数字' }
    }
    if (schema.minimum !== undefined && numberValue < schema.minimum) {
      return { ok: false, value: null, message: `不能小于 ${schema.minimum}` }
    }
    if (schema.maximum !== undefined && numberValue > schema.maximum) {
      return { ok: false, value: null, message: `不能大于 ${schema.maximum}` }
    }
    return { ok: true, value: numberValue, message: '' }
  }

  if (schema.type === 'enum') {
    const choices = schema.choices || []
    if (!choices.includes(text)) {
      return { ok: false, value: null, message: `可选值: ${choices.join(' / ')}` }
    }
    return { ok: true, value: text, message: '' }
  }

  return { ok: true, value: text, message: '' }
}

const applyUpdateResponse = (response: SettingsUpdateResponse) => {
  if (response.settings) {
    applySettingsPayload(response.settings)
  }

  clearAllFieldErrors()
  Object.entries(response.errors || {}).forEach(([field, messageText]) => {
    if (field === '_global') {
      globalError.value = messageText
      return
    }
    fieldErrors[field] = messageText
  })
}

const saveSettings = async () => {
  if (saving.value) {
    return
  }

  clearMessages()
  clearAllFieldErrors()

  const payload: Record<string, unknown> = {}

  for (const field of dirtyFields.value) {
    const schema = schemaMap.value[field]
    if (!schema) {
      continue
    }

    const isHidden = isFieldHidden(field)
    const isAutoDirty = autoDirtySet.value.has(field)
    if (isHidden && !isAutoDirty) {
      continue
    }

    const parsed = parseFieldValue(schema, formValues[field])
    if (!parsed.ok) {
      fieldErrors[field] = parsed.message
      continue
    }
    payload[field] = parsed.value
  }

  if (Object.keys(fieldErrors).length > 0) {
    globalError.value = '请先修正错误字段后再保存'
    return
  }

  if (Object.keys(payload).length === 0) {
    globalSuccess.value = '没有需要保存的变更'
    return
  }

  saving.value = true
  try {
    const response = await updateSettings(payload)
    applyUpdateResponse(response)

    if (response.success) {
      globalSuccess.value = `保存成功，已提交 ${Object.keys(payload).length} 个字段`
      message.success(globalSuccess.value)
      loaded.value = true
      return
    }

    const failedFields = Object.keys(response.errors || {}).filter((field) => field !== '_global')
    globalError.value = failedFields.length
      ? `保存失败，${failedFields.length} 个字段未通过校验`
      : '保存失败'
    message.error(globalError.value)
  } catch (error) {
    globalError.value = error instanceof Error ? error.message : String(error)
    message.error(globalError.value)
  } finally {
    saving.value = false
  }
}

watch(
  () => props.active,
  (active) => {
    if (active) {
      void loadSettings(false)
    }
  },
  { immediate: true },
)
</script>
