import { useEffect, useState } from 'react'
import { TrendingUp, Flame, RefreshCw, Clock, ExternalLink } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { fetchTrending } from '../api'
import Spinner from '../components/Spinner'
import { useNavigate } from 'react-router-dom'

const CATEGORY_COLOR = {
  technology:    'bg-blue-900/40 text-blue-300 border-blue-800/50',
  world:         'bg-green-900/40 text-green-300 border-green-800/50',
  science:       'bg-purple-900/40 text-purple-300 border-purple-800/50',
  business:      'bg-yellow-900/40 text-yellow-300 border-yellow-800/50',
  health:        'bg-red-900/40 text-red-300 border-red-800/50',
  entertainment: 'bg-pink-900/40 text-pink-300 border-pink-800/50',
  sports:        'bg-orange-900/40 text-orange-300 border-orange-800/50',
  general:       'bg-gray-800 text-gray-300 border-gray-700',
}

function TopicCard({ topic, index }) {
  const [open, setOpen] = useState(false)
  const color = CATEGORY_COLOR[topic.category] || CATEGORY_COLOR.general

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Topic header — always visible */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full text-left p-4 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-start gap-3">
          <span className="text-2xl leading-none mt-0.5">{topic.emoji}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <h3 className="font-bold text-white text-sm">{topic.topic}</h3>
              <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border capitalize ${color}`}>
                {topic.category}
              </span>
              <span className="ml-auto text-[10px] text-gray-600">#{index + 1}</span>
            </div>
            <p className="text-gray-300 text-xs leading-relaxed">{topic.headline}</p>
          </div>
        </div>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="border-t border-gray-800 p-4 space-y-4">
          {/* Why trending */}
          <div>
            <p className="text-[10px] font-semibold text-brand-400 uppercase tracking-wider mb-1">
              Why it's trending
            </p>
            <p className="text-gray-400 text-xs leading-relaxed">{topic.why_trending}</p>
          </div>

          {/* Related articles */}
          {topic.articles?.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Related stories
              </p>
              <div className="space-y-2">
                {topic.articles.map((a, i) => (
                  <a
                    key={i}
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-start gap-2 p-2.5 bg-gray-950 border border-gray-800
                               rounded-lg hover:border-brand-600/40 hover:bg-gray-900 transition-all group"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-200 group-hover:text-brand-300 transition-colors
                                    font-medium leading-snug line-clamp-2">
                        {a.title}
                      </p>
                      <p className="text-[10px] text-gray-600 mt-0.5">{a.source}</p>
                    </div>
                    <ExternalLink className="w-3 h-3 text-gray-600 group-hover:text-brand-400
                                             shrink-0 mt-0.5 transition-colors" />
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ArticleRow({ article }) {
  const timeAgo = (() => {
    try { return formatDistanceToNow(new Date(article.published_at), { addSuffix: true }) }
    catch { return '' }
  })()

  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex gap-3 p-3 bg-gray-900 border border-gray-800 rounded-xl
                 hover:border-brand-600/40 hover:bg-gray-800/50 transition-all group"
    >
      {article.image && (
        <img
          src={article.image}
          alt=""
          className="w-16 h-16 object-cover rounded-lg shrink-0 bg-gray-800"
          onError={e => e.target.style.display = 'none'}
        />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-200 group-hover:text-white
                      transition-colors leading-snug line-clamp-2 mb-1">
          {article.title}
        </p>
        <div className="flex items-center gap-2 text-[10px] text-gray-500">
          <span>{article.source}</span>
          {timeAgo && <><span>·</span><span>{timeAgo}</span></>}
        </div>
      </div>
      <ExternalLink className="w-3.5 h-3.5 text-gray-700 group-hover:text-brand-400
                               shrink-0 self-start mt-0.5 transition-colors" />
    </a>
  )
}

export default function TrendingPage() {
  const [data,       setData]       = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = async (force = false) => {
    if (force) setRefreshing(true)
    else setLoading(true)
    try {
      const d = await fetchTrending()
      setData(d)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) return <Spinner className="py-32" />

  const topics   = data?.topics   || []
  const articles = data?.articles || []
  const fetchedAt = data?.fetched_at

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <TrendingUp className="w-6 h-6 text-brand-500" />
          <h1 className="text-2xl font-bold text-white">Trending Now</h1>
          {data?.total > 0 && (
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">
              {data.total} live stories
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {fetchedAt && (
            <span className="flex items-center gap-1 text-[10px] text-gray-600">
              <Clock className="w-3 h-3" />
              {formatDistanceToNow(new Date(fetchedAt), { addSuffix: true })}
            </span>
          )}
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                       bg-gray-800 hover:bg-brand-700 text-gray-400 hover:text-white
                       transition-all disabled:opacity-50 border border-gray-700"
          >
            <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {topics.length === 0 && articles.length === 0 ? (
        <div className="bg-gray-900 border border-dashed border-gray-800 rounded-xl p-12 text-center">
          <TrendingUp className="w-10 h-10 mx-auto mb-3 opacity-20" />
          <p className="text-gray-500 text-sm font-medium">Could not fetch live trending news.</p>
          <p className="text-gray-600 text-xs mt-1">Check that GNews / SerpAPI keys are set in .env</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* ── Left: Hot Topics ──────────────────────────────────── */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center gap-2 mb-3">
              <Flame className="w-4 h-4 text-orange-400" />
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
                Hot Topics
              </h2>
            </div>
            {topics.length > 0 ? (
              topics.map((topic, i) => (
                <TopicCard key={i} topic={topic} index={i} />
              ))
            ) : (
              <p className="text-gray-600 text-xs text-center py-8">
                Topic analysis unavailable — check LLM config.
              </p>
            )}
          </div>

          {/* ── Right: Live News Feed ─────────────────────────────── */}
          <div className="lg:col-span-3">
            <div className="flex items-center gap-2 mb-3">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-500" />
              </span>
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
                Live News Feed
              </h2>
            </div>
            <div className="space-y-2">
              {articles.map((a, i) => (
                <ArticleRow key={i} article={a} />
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  )
}
