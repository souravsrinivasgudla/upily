import { useEffect, useState } from 'react'
import { fetchHealth } from './api'

// One shared request per page load; every component reads the same result.
let healthPromise = null

const UNKNOWN = { loaded: false, features: {} }

export function useHealth() {
  const [health, setHealth] = useState(UNKNOWN)

  useEffect(() => {
    let active = true
    healthPromise ??= fetchHealth().catch(() => ({ status: 'unreachable', features: {} }))
    healthPromise.then(h => { if (active) setHealth({ loaded: true, ...h, features: h.features || {} }) })
    return () => { active = false }
  }, [])

  return health
}
