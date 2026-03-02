import { useMemo } from 'react'

const STORAGE_KEY = 'tb_device_id'

function getOrCreateDeviceId(): string {
  let id = localStorage.getItem(STORAGE_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(STORAGE_KEY, id)
  }
  return id
}

export function useDeviceId(): string {
  return useMemo(getOrCreateDeviceId, [])
}

export { getOrCreateDeviceId }
