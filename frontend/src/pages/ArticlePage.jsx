import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, Plus } from 'lucide-react'
import { analyzeArticle, errorMessage, fetchArticle } from '../api'
import { useNewsCache } from '../NewsCache'
import { useHealth } from '../useHealth'
import ChatPanel from '../components/ChatPanel'
import { Badge, Button, cn, Kicker, Loading, Notice, Ornament } from '../components/ui'
import { dateline, paragraphs, timeAgo } from '../format'
import NotFound from './NotFound'

function Accordion({ title, children }) {
  const [open, setOpen] = useState(false)
  // Mount on first open, then keep mounted so collapsing doesn't wipe the conversation
  const [opened, setOpened] = useState(false)
  return (
    <section className="border-y-4 border-ink">
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls="ask-panel"
          onClick={() => { setOpen(v => !v); setOpened(true) }}
          className="flex min-h-[56px] w-full items-center justify-between gap-4 py-3 text-left transition-colors duration-200 hover:text-accent"
        >
          <span className="font-serif text-2xl font-bold lg:text-3xl">{title}</span>
          <span className="flex h-11 w-11 shrink-0 items-center justify-center border border-ink">
            <Plus className={cn('h-5 w-5 transition-transform duration-200', open && 'rotate-45')} strokeWidth={1.5} />
          </span>
        </button>
      </h2>
      <div id="ask-panel" className={cn('grid transition-all duration-300 ease-in-out', open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0')}>
        <div className="overflow-hidden" {...(!open && { inert: '' })}>
          {opened && <div className="pb-6">{children}</div>}
        </div>
      </div>
    </section>
  )
}

export default function ArticlePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const health = useHealth()
  const { forget } = useNewsCache()

  const [article, setArticle] = useState(null)
  const [status, setStatus] = useState('loading')   // loading | ready | missing | error
  const [error, setError] = useState('')
  const [analysis, setAnalysis] = useState('idle')  // idle | writing | failed
  const [analysisError, setAnalysisError] = useState('')
  const requested = useRef(new Set())
  const currentId = useRef(id)
  currentId.current = id

  // Load the article whenever the id changes (navigating between stories reuses this component)
  useEffect(() => {
    let active = true
    setStatus('loading'); setArticle(null); setAnalysis('idle'); setError('')
    if (!/^\d+$/.test(id)) { setStatus('missing'); return }

    fetchArticle(id)
      .then(a => { if (active) { setArticle(a); setStatus('ready') } })
      .catch(err => {
        if (!active) return
        if (err.response?.status === 404) { forget(Number(id)); setStatus('missing') }
        else { setError(errorMessage(err)); setStatus('error') }
      })
    return () => { active = false }
  }, [id, forget])

  // Ask the server to write the analysis once, if it's missing and AI is available
  useEffect(() => {
    if (!article || article.is_analyzed || !health.features.ai_analysis) return
    if (requested.current.has(article.id)) return
    requested.current.add(article.id)
    setAnalysis('writing')
    analyzeArticle(article.id)
      .then(a => {
        if (String(a.id) !== currentId.current) return   // reader moved on to another story
        setArticle(prev => (prev?.id === a.id ? a : prev))
        setAnalysis('idle')
      })
      .catch(err => {
        if (String(article.id) !== currentId.current) return
        setAnalysisError(errorMessage(err))
        setAnalysis('failed')
      })
  }, [article, health.features.ai_analysis])

  const goBack = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate('/'))

  if (status === 'loading') return <Loading label="Fetching the story…" />
  if (status === 'missing') return <NotFound title="This story has been archived." message="Upily keeps stories for two days. Head back to the front page for the latest edition." />
  if (status === 'error') {
    return (
      <div className="py-16 text-center">
        <Notice tone="alert" className="mx-auto max-w-xl text-left">{error}</Notice>
        <Button className="mt-6" onClick={() => navigate(0)}>Try again</Button>
      </div>
    )
  }

  const body = paragraphs(article.deep_explanation)
  const excerpt = article.raw_content || article.summary
  const aiOff = health.loaded && !health.features.ai_analysis

  return (
    <article>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink pb-3">
        <Button variant="ghost" onClick={goBack} className="-ml-3 px-3">
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} /> Back
        </Button>
        <Kicker>
          <Link to={article.category ? `/?section=${article.category}` : '/'} className="hover:text-accent">
            {article.category} desk
          </Link>
        </Kicker>
      </div>

      <header className="newsprint-texture py-8 lg:py-12">
        <div className="mb-5 flex flex-wrap gap-2">
          {article.is_trending && <Badge tone="accent">Trending</Badge>}
          <Badge tone="outline">{article.category}</Badge>
        </div>
        <h1 className="max-w-5xl font-serif text-4xl font-black leading-[0.95] tracking-tight text-balance sm:text-5xl lg:text-7xl">
          {article.title}
        </h1>
        {article.summary && (
          <p className="mt-6 max-w-3xl font-body text-lg italic leading-relaxed text-neutral-700 lg:text-xl">
            {article.summary}
          </p>
        )}
      </header>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-y border-ink py-3">
        <Kicker className="text-ink">By the Upily desk</Kicker>
        <Kicker>Reporting: {article.source}</Kicker>
        {article.published_at && (
          <Kicker><time dateTime={article.published_at}>{dateline(article.published_at)}</time> · {timeAgo(article.published_at)}</Kicker>
        )}
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto inline-flex min-h-[44px] items-center gap-1 font-sans text-sm font-semibold underline-offset-4 decoration-2 decoration-accent hover:underline"
        >
          Read the original <ArrowUpRight className="h-4 w-4" strokeWidth={1.5} />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      </div>

      {analysis === 'writing' && <Notice className="mt-6">The analysis desk is writing this story up — this takes a few seconds.</Notice>}
      {analysis === 'failed' && <Notice tone="alert" className="mt-6">{analysisError} Showing the source excerpt instead.</Notice>}
      {aiOff && !article.is_analyzed && <Notice className="mt-6">AI analysis is switched off on this server. Showing the source excerpt.</Notice>}

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-12 lg:gap-0">
        <section aria-labelledby="story-heading" className="lg:col-span-8 lg:border-r lg:border-ink lg:pr-8">
          <Kicker as="h2" id="story-heading" className="mb-4 block border-b border-ink pb-2 text-ink">
            {article.is_analyzed ? 'The full story' : 'From the source'}
          </Kicker>

          {article.is_analyzed ? (
            <div className="font-body text-[17px] leading-relaxed text-neutral-800 text-justify hyphens-auto lg:columns-2 lg:gap-8 lg:[column-rule:1px_solid_#111111]">
              {body.map((p, i) => (
                <p key={i} className={cn('mb-4 break-inside-avoid-column', i === 0 && 'drop-cap')}>{p}</p>
              ))}
            </div>
          ) : analysis === 'writing' ? (
            <Loading label="Writing the analysis…" className="py-12" />
          ) : (
            <p className="drop-cap font-body text-[17px] leading-relaxed text-neutral-800 text-justify hyphens-auto">
              {excerpt || 'The source did not include an excerpt. Read the original for the full report.'}
            </p>
          )}
        </section>

        <aside className="space-y-6 lg:col-span-4 lg:pl-8" aria-label="Context">
          {article.why_it_matters && (
            <section className="bg-ink p-6 text-paper">
              <Kicker className="mb-3 block text-neutral-400">Why it matters</Kicker>
              {paragraphs(article.why_it_matters).map((p, i) => (
                <p key={i} className="mb-3 font-body text-[15px] leading-relaxed last:mb-0">{p}</p>
              ))}
            </section>
          )}
          {article.background_info && (
            <section className="border border-ink p-6">
              <Kicker className="mb-3 block text-ink">Background & context</Kicker>
              {paragraphs(article.background_info).map((p, i) => (
                <p key={i} className="mb-3 font-body text-[15px] leading-relaxed text-neutral-700 last:mb-0">{p}</p>
              ))}
            </section>
          )}
          {article.coverage?.length > 0 && (
            <section className="border border-ink" aria-labelledby="coverage-heading">
              <Kicker as="h3" id="coverage-heading" className="block border-b border-ink px-6 py-3 text-ink">
                Also reported by {article.coverage.length} other {article.coverage.length === 1 ? 'outlet' : 'outlets'}
              </Kicker>
              <ul className="divide-y divide-divider">
                {article.coverage.map(c => (
                  <li key={c.id} className="flex items-start justify-between gap-3 px-6 py-3">
                    <Link to={`/article/${c.id}`} className="group">
                      <Kicker className="block text-ink">{c.source}</Kicker>
                      <span className="font-serif text-base font-bold leading-snug decoration-accent decoration-2 underline-offset-4 group-hover:underline">
                        {c.title}
                      </span>
                    </Link>
                    <a href={c.url} target="_blank" rel="noopener noreferrer"
                       aria-label={`Read ${c.source}'s original (opens in a new tab)`}
                       className="flex h-9 w-9 shrink-0 items-center justify-center border border-ink transition-colors duration-200 hover:bg-ink hover:text-paper">
                      <ArrowUpRight className="h-4 w-4" strokeWidth={1.5} />
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {article.tags?.length > 0 && (
            <section className="border-t-4 border-ink pt-4">
              <Kicker className="mb-2 block text-ink">Filed under</Kicker>
              <ul className="flex flex-wrap gap-2">
                {article.tags.map(t => (
                  <li key={t} className="border border-ink px-2 py-1 font-mono text-[11px] uppercase tracking-widest">#{t}</li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>

      <Ornament />

      <Accordion title="Ask about this story">
        <ChatPanel
          articleId={article.id}
          suggestions={['Explain this simply', 'What happens next?', 'Who are the key players?']}
        />
      </Accordion>
    </article>
  )
}
