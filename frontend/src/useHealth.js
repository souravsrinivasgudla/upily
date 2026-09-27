import { useEffect, useState } from 'react'
import { fetchHealth } from './api'

// One shared request per page load; every component reads the same result.
// Failures are NOT cached: a cold-starting server gets retried, so a slow first
// boot doesn't leave the whole session thinking AI features are switched off.
let healthPromise = null
let lastGood = null
const RETRY_MS = 15000
const MAX_RETRIES = 6

function load(attempt = 0) {
  healthPromise ??= fetchHealth()
    .then(h => {
      if (!h || typeof h !== 'object' || !h.features) throw new Error('Bad health response')
      lastGood = h
      return h
    })
    .catch(err => {
      healthPromise = null
      if (attempt >= MAX_RETRIES) throw err
      return new Promise(resolve => setTimeout(resolve, RETRY_MS)).then(() => load(attempt + 1))
    })
  return healthPromise
}

// loaded=false means "unknown yet" — components must not claim a feature is off until loaded
const UNKNOWN = { loaded: false, features: {} }

export function useHealth() {
  const [health, setHealth] = useState(() => (lastGood ? { loaded: true, ...lastGood } : UNKNOWN))

  useEffect(() => {
    if (lastGood) return
    let active = true
    load()
      .then(h => { if (active) setHealth({ loaded: true, ...h }) })
      .catch(() => { if (active) setHealth({ loaded: false, unreachable: true, features: {} }) })
    return () => { active = false }
  }, [])

  return health
}
