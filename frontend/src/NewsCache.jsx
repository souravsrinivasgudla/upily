/**
 * NewsCache — short-lived in-memory cache of article lists per category.
 *
 * The TTL is deliberately short (5 min): the backend adds and archives articles
 * on its own schedule, so a long-lived client cache would link to articles that
 * no longer exist. Stale entries are shown instantly while a fresh copy loads.
 */
import { createContext, useCallback, useContext, useMemo, useRef } from 'react'
import { fetchNews } from './api'

const CACHE_TTL_MS = 5 * 60 * 1000

const NewsCacheContext = createContext(null)

const keyOf = (category, limit) => `${category || 'all'}|${limit}`

export function NewsCacheProvider({ children }) {
  const cache    = useRef(new Map())   // key → { articles, total, timestamp }
  const inflight = useRef(new Map())   // key → Promise, dedupes concurrent fetches

  const load = useCallback((category, limit) => {
    const key = keyOf(category, limit)
    let promise = inflight.current.get(key)
    if (!promise) {
      promise = fetchNews({ ...(category ? { category } : {}), limit })
        .then(data => {
          const entry = { articles: data.articles || [], total: data.total ?? 0, timestamp: Date.now() }
          cache.current.set(key, entry)
          return entry
        })
        .finally(() => inflight.current.delete(key))
      inflight.current.set(key, promise)
    }
    return promise
  }, [])

  /**
   * Subscribe to a category. Calls onData(entry, { stale }) with cached data
   * first when available, then with fresh data. Returns an unsubscribe function.
   */
  const getArticles = useCallback((category, limit, { onData, onError, onLoading }) => {
    let cancelled = false
    const cached = cache.current.get(keyOf(category, limit))
    const fresh = cached && Date.now() - cached.timestamp < CACHE_TTL_MS

    if (cached) onData(cached, { stale: !fresh })
    else onLoading?.()

    if (!fresh) {
      load(category, limit)
        .then(entry => { if (!cancelled) onData(entry, { stale: false }) })
        .catch(err  => { if (!cancelled) onError?.(err) })
    }
    return () => { cancelled = true }
  }, [load])

  /** Replace a cached list (e.g. with the result of a manual refresh). */
  const put = useCallback((category, limit, articles) => {
    cache.current.set(keyOf(category, limit), { articles, total: articles.length, timestamp: Date.now() })
  }, [])

  const invalidate = useCallback((category, limit) => {
    cache.current.delete(keyOf(category, limit))
  }, [])

  /** Remove one article from every cached list (it was archived on the server). */
  const forget = useCallback((articleId) => {
    for (const [key, entry] of cache.current) {
      cache.current.set(key, { ...entry, articles: entry.articles.filter(a => a.id !== articleId) })
    }
  }, [])

  const prefetch = useCallback((category, limit) => {
    const cached = cache.current.get(keyOf(category, limit))
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) return
    load(category, limit).catch(() => {})
  }, [load])

  const value = useMemo(
    () => ({ getArticles, put, invalidate, forget, prefetch }),
    [getArticles, put, invalidate, forget, prefetch],
  )

  return <NewsCacheContext.Provider value={value}>{children}</NewsCacheContext.Provider>
}

export const useNewsCache = () => {
  const ctx = useContext(NewsCacheContext)
  if (!ctx) throw new Error('useNewsCache must be used inside <NewsCacheProvider>')
  return ctx
}
