// Shared bits of the developer tool (see DevTool.tsx), kept apart so the component file only exports components.
import { useEffect, useState } from 'react'

export interface DevTask {
  id: number
  status: 'queued' | 'running' | 'done' | 'failed'
  comment: string
  page: string
  target: string
  progress: string[]
  summary: string
  error: string
  changed: string[]
}
export interface DevInfo { enabled: boolean; agent: boolean; model: string; servesBuilt: boolean; tasks: DevTask[] }


export const PICK_EVENT = 'dsc-dev-pick'
/** Start the select mode (the sidebar button calls this). */
export const startDevPick = () => window.dispatchEvent(new Event(PICK_EVENT))

let infoPromise: Promise<DevInfo | null> | null = null
export const fetchInfo = () => fetch('/api/dev').then(r => (r.ok ? r.json() as Promise<DevInfo> : null)).catch(() => null)

/** Is the developer tool on (source checkout)? Asked once per page load. */
export function useDevEnabled(): boolean {
  const [on, setOn] = useState(false)
  useEffect(() => {
    infoPromise ??= fetchInfo()
    infoPromise.then(i => setOn(!!i?.enabled))
  }, [])
  return on
}

