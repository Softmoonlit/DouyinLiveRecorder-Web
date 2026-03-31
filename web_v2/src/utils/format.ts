export function formatDateTime(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) {
    return '--'
  }
  const date = new Date(epochSeconds * 1000)
  if (Number.isNaN(date.getTime())) {
    return '--'
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

export function formatUptime(seconds: number | undefined): string {
  if (typeof seconds !== 'number' || Number.isNaN(seconds) || seconds < 0) {
    return '--'
  }

  const day = Math.floor(seconds / 86400)
  const hour = Math.floor((seconds % 86400) / 3600)
  const minute = Math.floor((seconds % 3600) / 60)
  return `${day}d ${hour}h ${minute}m`
}

export function formatGiB(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return `${value.toFixed(1)} GiB`
}

export function formatPercent(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return `${(value * 100).toFixed(1)}%`
}
