/**
 * "My Upily" preferences — followed sections and topics, kept in this browser only
 * (no accounts). Every component using the hook sees updates immediately, and
 * changes made in another tab are picked up too.
 */
import { useSyncExternalStore } from 'react'

const KEY = 'upily.preferences.v1'
const DEFAULTS = { sections: [], topics: [], location: null }   // location: { state, district }
const MAX_TOPICS = 12

function read() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(KEY) || 'null')
    return saved && typeof saved === 'object'
      ? { sections: Array.isArray(saved.sections) ? saved.sections : [],
          topics: Array.isArray(saved.topics) ? saved.topics : [],
          location: saved.location && typeof saved.location.state === 'string' ? saved.location : null }
      : DEFAULTS
  } catch {
    return DEFAULTS   // private mode / blocked storage: preferences just don't persist
  }
}

let state = read()
const listeners = new Set()

function set(next) {
  state = next
  try { window.localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* not persisted */ }
  listeners.forEach(l => l())
}

function subscribe(listener) {
  listeners.add(listener)
  const onStorage = (e) => { if (e.key === KEY) { state = read(); listener() } }
  window.addEventListener('storage', onStorage)
  return () => { listeners.delete(listener); window.removeEventListener('storage', onStorage) }
}

export const normalizeTopic = (t) => t.trim().replace(/\s+/g, ' ').slice(0, 40)

export const preferences = {
  toggleSection(cat) {
    const sections = state.sections.includes(cat)
      ? state.sections.filter(c => c !== cat)
      : [...state.sections, cat]
    set({ ...state, sections })
  },
  addTopic(raw) {
    const topic = normalizeTopic(raw)
    if (topic.length < 2) return false
    if (state.topics.some(t => t.toLowerCase() === topic.toLowerCase())) return false
    set({ ...state, topics: [...state.topics, topic].slice(-MAX_TOPICS) })
    return true
  },
  removeTopic(topic) {
    set({ ...state, topics: state.topics.filter(t => t !== topic) })
  },
  setLocation(region, district = null) {
    set({ ...state, location: region ? { state: region, district: district || null } : null })
  },
  reset() { set({ ...DEFAULTS, location: state.location }) },   // "Clear my edition" keeps the saved area
}

export function usePreferences() {
  return useSyncExternalStore(subscribe, () => state, () => DEFAULTS)
}
