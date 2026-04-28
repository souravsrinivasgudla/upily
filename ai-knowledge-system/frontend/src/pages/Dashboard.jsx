import { useEffect, useState, useCallback } from 'react'
import { Newspaper, SlidersHorizontal, RefreshCw } from 'lucide-react'
import { refreshCategory } from '../api'
import { useNewsCache } from '../NewsCache'
import ArticleCard from '../components/ArticleCard'
import Spinner from '../components/Spinner'

const CATEGORIES = ['technology', 'world', 'science', 'business', 'health', 'sports', 'entertainment']
const LIMIT = 20

export default function Dashboard() {
  const { getArticles, invalidate, prefetch } = useNewsCache()

  const [articles,   setArticles]   = useState([])
  const [loading,    setLoading]    = useState(true)
  const [category,   setCategory]   = useState('technology')
  const [error,      setError]      = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState('')

  // ── Load articles ────────────────────────────────────────────────────────
  const loadArticles = useCallback((cat) => {
    setError('')
    return getArticles(
      cat,
      LIMIT,
      (data) => { setArticles(data); setLoading(false) },
      ()     => { setError('Cannot reach backend. Is the server running?'); setLoading(false) },
      ()     => { setArticles([]); setLoading(true) },
    )
  }, [getArticles])

  useEffect(() => {
    const cleanup = loadArticles(category)
    return cleanup
  }, [category, loadArticles])

  // Prefetch adjacent categories on hover
  useEffect(() => {
    const idx = CATEGORIES.indexOf(category)
    ;[CATEGORIES[idx - 1], CATEGORIES[idx + 1]]
      .filter(Boolean)
      .forEach(cat => prefetch(cat, LIMIT))
  }, [category, prefetch])

  // ── Per-category refresh ─────────────────────────────────────────────────
  // Clears all articles for this category from DB, fetches fresh ones,
  // waits for completion, then shows the new articles directly
  const handleRefresh = async () => {
    if (refreshing) return
    setRefreshing(true)
    setLoading(true)
    setArticles([])
    setRefreshMsg(`Fetching fresh ${category} articles…`)
    invalidate(category, LIMIT)

    try {
      // This call waits for the full pipeline to complete on the backend
      const result = await refreshCategory(category)
      const newArticles = result.articles || []

      // Update cache with the fresh articles
      invalidate(category, LIMIT)

      if (newArticles.length > 0) {
        setArticles(newArticles)
        setRefreshMsg('')
      } else {
        setRefreshMsg(`No new ${category} articles found — RSS feeds may not have updated yet.`)
        // Fall back to loading from DB (may have articles from other sources)
        loadArticles(category)
      }
    } catch {
      setRefreshMsg('Refresh failed — is the backend running?')
      loadArticles(category)
    } finally {
      setRefreshing(false)
      setLoading(false)
      setTimeout(() => setRefreshMsg(''), 8000)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────
  const enriched    = articles.filter(a => a.tags && a.tags.length > 0)
  const displayList = enriched.length > 0 ? enriched : articles

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Newspaper className="w-6 h-6 text-brand-500" />
          <h1 className="text-2xl font-bold text-white">Daily Feed</h1>
        </div>
        {!loading && (
          <span className="text-sm text-gray-500">
            {displayList.length} {displayList.length === 1 ? 'article' : 'articles'}
          </span>
        )}
      </div>

      {/* Category pills */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <SlidersHorizontal className="w-4 h-4 text-gray-500 shrink-0" />
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            onMouseEnter={() => prefetch(cat, LIMIT)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors capitalize
              ${category === cat
                ? 'bg-brand-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'}`}
          >
            {cat}
          </button>
        ))}

        {/* Refresh icon — only for the active category */}
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          title={`Clear ${category} articles and fetch fresh ones`}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                     bg-gray-800 hover:bg-brand-700 text-gray-400 hover:text-white
                     transition-all disabled:opacity-50 border border-gray-700 hover:border-brand-500"
        >
          <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin text-brand-400' : ''}`} />
          {refreshing ? 'Refreshing…' : `Refresh ${category}`}
        </button>
      </div>

      {/* Status */}
      {refreshMsg && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-brand-900/30 border border-brand-700/40 text-brand-300 text-xs">
          {refreshMsg}
        </div>
      )}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded-xl p-4 text-red-300 text-sm mb-6">
          {error}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex flex-col items-center py-20">
          <Spinner />
          <p className="text-xs text-gray-500 mt-4 animate-pulse">Loading articles…</p>
        </div>
      ) : displayList.length === 0 ? (
        <div className="text-center py-24 text-gray-500">
          <Newspaper className="w-12 h-12 mx-auto mb-4 opacity-20" />
          <p className="text-lg font-medium mb-1">No {category} articles yet</p>
          <p className="text-sm">
            Click <strong className="text-gray-300">Refresh {category}</strong> to fetch the latest news.
          </p>
        </div>
      ) : (
        <>
          {enriched.length === 0 && articles.length > 0 && (
            <div className="bg-amber-900/20 border border-amber-800/30 text-amber-200/60 text-[10px]
                            px-3 py-1.5 rounded-lg mb-4 flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
              </span>
              AI analysis in progress — showing quick summaries for now.
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {displayList.map(a => (
              <ArticleCard
                key={a.id || a.url}
                article={{ ...a, tags: a.tags?.length ? a.tags : ['Quick Preview'] }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
