import { useNavigate } from 'react-router-dom'
import { ExternalLink, Flame } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const CAT_COLORS = {
  technology:    'bg-blue-900/60 text-blue-300',
  world:         'bg-purple-900/60 text-purple-300',
  science:       'bg-emerald-900/60 text-emerald-300',
  business:      'bg-amber-900/60 text-amber-300',
  health:        'bg-rose-900/60 text-rose-300',
  sports:        'bg-orange-900/60 text-orange-300',
  entertainment: 'bg-indigo-900/60 text-indigo-300',
  general:       'bg-slate-800/80 text-slate-200',
}

export default function ArticleCard({ article }) {
  const navigate  = useNavigate()
  const catColor = (article.category && CAT_COLORS[article.category.toLowerCase()]) || CAT_COLORS.general
  const timeAgo   = article.published_at
    ? formatDistanceToNow(new Date(article.published_at), { addSuffix: true })
    : ''

  return (
    <div
      onClick={() => {
        if (article.id) {
          navigate(`/article/${article.id}`)
        } else {
          navigate('/article/live', { state: { article } })
        }
      }}
      className="bg-gray-900 border border-gray-800 rounded-xl p-4 cursor-pointer
                 hover:border-brand-500 hover:bg-gray-800/80 transition-all group"
    >
      {/* Meta row */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${catColor}`}>
            {article.category}
          </span>
          {article.is_trending && (
            <span className="flex items-center gap-1 text-xs text-orange-400 font-medium">
              <Flame className="w-3 h-3" /> Trending
            </span>
          )}
        </div>
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={e => e.stopPropagation()}
          className="text-gray-600 hover:text-brand-400 transition-colors shrink-0"
        >
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      {/* Title */}
      <h3 className="font-semibold text-white text-sm leading-snug mb-2
                     group-hover:text-brand-300 transition-colors line-clamp-2">
        {article.title}
      </h3>

      {/* Summary */}
      {article.summary && (
        <p className="text-gray-400 text-xs leading-relaxed line-clamp-2 mb-3">
          {article.summary}
        </p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-gray-600">
        <span>{article.source}</span>
        <span>{timeAgo}</span>
      </div>

      {/* Tags */}
      {article.tags?.length > 0 && (
        <div className="flex gap-1 mt-2 flex-wrap min-h-[24px]">
          {article.tags.slice(0, 3).map(tag => (
            <span key={tag} className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded-full">
              #{tag}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
