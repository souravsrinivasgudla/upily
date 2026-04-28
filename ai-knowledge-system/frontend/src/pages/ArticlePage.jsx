import { useEffect, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  ArrowLeft, ExternalLink, Flame,
  BookOpen, Globe, Lightbulb, MessageSquare
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { fetchArticle, summarizeArticle, enrichArticle } from '../api'
import ChatPanel from '../components/ChatPanel'
import Spinner from '../components/Spinner'

function Section({ icon: Icon, title, content, accent }) {
  if (!content) return null
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-4">
      <div className={`flex items-center gap-2 mb-3 ${accent}`}>
        <Icon className="w-4 h-4" />
        <h2 className="text-xs font-semibold uppercase tracking-widest">{title}</h2>
      </div>
      <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-line">{content}</p>
    </div>
  )
}

export default function ArticlePage() {
  const { id }  = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  
  const [article,  setArticle]  = useState(location.state?.article || null)
  const [loading,  setLoading]  = useState(!article)
  const [showChat, setShowChat] = useState(false)

  useEffect(() => {
    // Helper to determine if an article needs a fresh deep analysis
    const needsEnrichment = (art) => {
      if (!art || art.id === 'live') return false;
      return !art.deep_explanation || !art.why_it_matters || !art.background_info;
    }

    if (id === 'live') {
      if (article && !article.deep_explanation && !loading) {
        setLoading(true)
        const contextParts = [article.description, article.summary, article.raw_content, article.content].filter(Boolean)
        const combinedContent = contextParts.join('\n\n') || article.title

        summarizeArticle(article.title, combinedContent)
          .then(d => setArticle(prev => ({ ...prev, ...d })))
          .catch(err => console.error('Analysis failed:', err))
          .finally(() => setLoading(false))
      } else {
        setLoading(false)
      }
      return
    }

    if (!article) {
      setLoading(true)
      fetchArticle(id).then(setArticle).finally(() => setLoading(false))
    } else if (needsEnrichment(article) && !loading) {
      // If article is loaded but missing deep analysis sections, fetch it and SAVE it permanently
      setLoading(true)
      const contextParts = [article.description, article.summary, article.raw_content, article.content].filter(Boolean)
      const combinedContent = contextParts.join('\n\n') || article.title

      summarizeArticle(article.title, combinedContent)
        .then(async (d) => {
          setArticle(prev => ({ ...prev, ...d }));
          // LOCK IN: Save this deep analysis permanently to the local database
          try {
            await enrichArticle(id, d);
            console.log('✅ Permanent enrichment saved for article:', id);
          } catch (enrichErr) {
            console.error('⚠️ Failed to save permanent enrichment:', enrichErr);
          }
        })
        .catch(err => console.error('Enrichment failed:', err))
        .finally(() => setLoading(false))
    }
  }, [id, article?.title, article?.id, article?.deep_explanation, article?.why_it_matters, article?.background_info])

  if (loading) return <Spinner className="py-32" />
  if (!article) return (
    <p className="text-center py-32 text-gray-500">Article not found.</p>
  )

  const hasAiAnalysis = article.ai_available !== false

  const timeAgo = article.published_at
    ? formatDistanceToNow(new Date(article.published_at), { addSuffix: true })
    : ''

  return (
    <div>
      {/* Back */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-sm text-gray-400 hover:text-white mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      {/* Meta */}
      <div className="mb-5">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium bg-brand-900 text-brand-300 px-2 py-0.5 rounded-full capitalize">
            {article.category}
          </span>
          {article.is_trending && (
            <span className="flex items-center gap-1 text-xs text-orange-400 font-medium">
              <Flame className="w-3 h-3" /> Trending
            </span>
          )}
          <span className="text-xs text-gray-500">{article.source}</span>
          {timeAgo && <span className="text-xs text-gray-600">{timeAgo}</span>}
        </div>

        <h1 className="text-2xl font-bold text-white leading-tight mb-3">
          {article.title}
        </h1>

        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-brand-400 hover:text-brand-300 transition-colors"
        >
          <ExternalLink className="w-3 h-3" /> Read original source
        </a>
      </div>

      {/* Tags */}
      {article.tags?.length > 0 && (
        <div className="flex gap-2 mb-6 flex-wrap">
          {article.tags.map(t => (
            <span key={t} className="text-xs bg-gray-800 text-gray-400 px-2.5 py-0.5 rounded-full">
              #{t}
            </span>
          ))}
        </div>
      )}

      {/* Content sections */}
      {!hasAiAnalysis && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 mb-4 text-sm text-amber-200">
          AI analysis is unavailable because no backend LLM API key is configured. Showing the source excerpt instead.
        </div>
      )}

      <Section icon={BookOpen}  title="Summary"           content={article.summary}          accent="text-blue-400" />
      <Section icon={Globe}     title={hasAiAnalysis ? 'Deep Explanation' : 'Source Extract'}  content={article.deep_explanation}  accent="text-green-400" />
      <Section icon={Flame}     title="Why It Matters"    content={article.why_it_matters}    accent="text-orange-400" />
      <Section icon={Lightbulb} title="Background & GK"   content={article.background_info}   accent="text-yellow-400" />

      {/* Chat */}
      <div className="mt-6">
        <button
          onClick={() => setShowChat(v => !v)}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-700
                     text-white text-sm font-medium rounded-lg transition-colors"
        >
          <MessageSquare className="w-4 h-4" />
          {showChat ? 'Close Chat' : 'Ask AI about this article'}
        </button>

        {showChat && (
          <div className="mt-4 rounded-xl border border-gray-800 overflow-hidden">
            <ChatPanel articleId={id} articleData={article} />
          </div>
        )}
      </div>
    </div>
  )
}
