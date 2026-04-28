/**
 * NewsCache — simple in-memory cache with 4-hour TTL.
 * Articles are fetched once and served from cache until the backend
 * pipeline runs again (every 4 hours). Cache is invalidated on manual refresh.
 */
import { createContext, useContext, useRef, useCallback } from 'react'
import { fetchNews } from './api'

const CACHE_TTL_MS = 4 * 60 * 60 * 1000  // 4 hours — matches pipeline interval

const NewsCacheContext = createContext(null)

export function NewsCacheProvider({ children }) {
  const cache    = useRef(new Map())   // key → { articles, timestamp }
  const inflight = useRef(new Map())   // key → Promise (deduplicates concurrent fetches)

  const _key      = (category, limit) => `${category}|${limit}`
  const _isFresh  = (entry) => entry && (Date.now() - entry.timestamp) < CACHE_TTL_MS

  const getArticles = useCallback((category, limit, onData, onError, onLoading) => {
    let cancelled = false
    const key    = _key(category, limit)
    const cached = cache.current.get(key)

    // Fresh cache hit — serve immediately
    if (_isFresh(cached)) {
      onData(cached.articles, true)
      return () => { cancelled = true }
    }

    // Show stale data while re-fetching (avoids blank screen on tab switch)
    if (cached) {
      onData(cached.articles, false)
    } else {
      onLoading?.()
    }

    // Deduplicate concurrent fetches for the same key
    let promise = inflight.current.get(key)
    if (!promise) {
      promise = fetchNews({ category, limit })
        .finally(() => inflight.current.delete(key))
      inflight.current.set(key, promise)
    }

    promise
      .then(data => {
        if (cancelled) return
        const articles = data.articles || []
        cache.current.set(key, { articles, timestamp: Date.now() })
        onData(articles, true)
      })
      .catch(err => {
        if (cancelled) return
        onError?.(err)
      })

    return () => { cancelled = true }
  }, [])

  // Clear cache entry — forces next getArticles to re-fetch from backend
  const invalidate = useCallback((category, limit) => {
    cache.current.delete(_key(category, limit))
  }, [])

  // Warm cache in background (called on category hover)
  const prefetch = useCallback((category, limit = 20) => {
    const key = _key(category, limit)
    if (_isFresh(cache.current.get(key))) return
    if (inflight.current.has(key)) return

    const promise = fetchNews({ category, limit })
      .then(data => {
        const articles = data.articles || []
        cache.current.set(key, { articles, timestamp: Date.now() })
      })
      .catch(() => {})
      .finally(() => inflight.current.delete(key))

    inflight.current.set(key, promise)
  }, [])

  return (
    <NewsCacheContext.Provider value={{ getArticles, invalidate, prefetch }}>
      {children}
    </NewsCacheContext.Provider>
  )
}

export const useNewsCache = () => {
  const ctx = useContext(NewsCacheContext)
  if (!ctx) throw new Error('useNewsCache must be used inside <NewsCacheProvider>')
  return ctx
}
