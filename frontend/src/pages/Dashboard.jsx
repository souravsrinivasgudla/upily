import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { errorMessage, refreshCategory } from '../api'
import { useNewsCache } from '../NewsCache'
import { useHealth } from '../useHealth'
import ArticleCard from '../components/ArticleCard'
import EconomicCalendar from '../components/EconomicCalendar'
import RatesStrip from '../components/RatesStrip'
import { Button, cn, Figure, Kicker, Loading, Notice, Ornament, SectionHeading } from '../components/ui'
import { sectionName, sectionTitle } from '../format'

export const CATEGORIES = ['technology', 'ai', 'india', 'world', 'science', 'business', 'forex', 'health', 'sports', 'entertainment']
const LIMIT = 20
const ANALYSIS_RECHECK_MS = 25000

/** A story several outlets are covering outranks one outlet's scoop of equal importance. */
const leadScore = (a) => (a.importance_score ?? 0) + 0.05 * Math.min((a.coverage_count ?? 1) - 1, 4)

/** Lead = highest lead score; ties go to the newest (the API list is newest-first). */
function splitFrontPage(articles) {
  if (articles.length === 0) return { lead: null, side: [], rest: [] }
  const lead = articles.reduce((best, a) => (leadScore(a) > leadScore(best) ? a : best), articles[0])
  const others = articles.filter(a => a.id !== lead.id)
  return { lead, side: others.slice(0, 3), rest: others.slice(3) }
}

function SectionTabs({ current, onSelect, onPrefetch }) {
  return (
    <div className="flex overflow-x-auto scrollbar-none border-y border-ink" role="toolbar" aria-label="Choose a section">
      <Kicker className="hidden shrink-0 items-center border-r border-ink px-4 sm:flex text-ink">Sections</Kicker>
      {CATEGORIES.map(cat => (
        <button
          key={cat}
          type="button"
          aria-pressed={current === cat}
          onClick={() => onSelect(cat)}
          onMouseEnter={() => onPrefetch(cat)}
          onFocus={() => onPrefetch(cat)}
          className={cn(
            'min-h-[44px] shrink-0 border-r border-ink px-4 font-sans text-xs font-semibold uppercase tracking-widest transition-colors duration-200',
            current === cat ? 'bg-ink text-paper' : 'hover:bg-neutral-100 hover:text-accent',
          )}
        >
          {sectionName(cat)}
        </button>
      ))}
    </div>
  )
}

function HowItWorks() {
  const steps = [
    ['Gathered', 'Every few hours Upily reads the wires — BBC, The Guardian, NYT, The Hindu, TechCrunch, FXStreet, ESPN, the AI labs’ own blogs and more — across ten desks — plus Forex Factory’s economic calendar.'],
    ['Ranked', 'Each story is weighed for global impact, novelty and public interest, and the strongest make the page.'],
    ['Explained', 'An AI analyst writes the summary, the context and why it matters — then you can question it directly.'],
  ]
  return (
    <section aria-labelledby="how-heading" className="mt-16 bg-ink text-paper">
      <div className="border-b border-neutral-700 px-6 py-6 lg:px-8">
        <Kicker className="text-neutral-400">The method</Kicker>
        <h2 id="how-heading" className="mt-1 font-serif text-4xl font-black lg:text-5xl">How Upily is made</h2>
      </div>
      <ol className="grid grid-cols-1 md:grid-cols-3">
        {steps.map(([title, body], i) => (
          <li key={title} className="border-b border-neutral-700 p-6 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0 lg:p-8">
            <span className="inline-flex h-10 w-10 items-center justify-center bg-accent font-mono text-sm font-medium text-white">
              {String(i + 1).padStart(2, '0')}
            </span>
            <h3 className="mt-4 font-serif text-2xl font-bold">{title}</h3>
            <p className="mt-2 font-body text-sm leading-relaxed text-neutral-400">{body}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function Dashboard() {
  const { getArticles, put, invalidate, prefetch } = useNewsCache()
  const health = useHealth()
  const [params, setParams] = useSearchParams()
  const category = CATEGORIES.includes(params.get('section')) ? params.get('section') : CATEGORIES[0]

  const [feed, setFeed] = useState({ status: 'loading', articles: [], error: '' })
  const [reloadToken, setReloadToken] = useState(0)
  const [refreshing, setRefreshing] = useState(null)   // category being refreshed
  const [notice, setNotice] = useState(null)           // { tone, text }

  const categoryRef = useRef(category)
  categoryRef.current = category
  const timers = useRef([])
  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const later = (fn, ms) => timers.current.push(setTimeout(fn, ms))

  useEffect(() => getArticles(category, LIMIT, {
    onLoading: () => setFeed({ status: 'loading', articles: [], error: '' }),
    onData:    (entry) => setFeed({ status: 'ready', articles: entry.articles, error: '' }),
    onError:   (err) => setFeed(f => ({ ...f, status: f.articles.length ? 'ready' : 'error', error: errorMessage(err) })),
  }), [category, reloadToken, getArticles])

  const selectCategory = (cat) => {
    setNotice(null)
    setParams(cat === CATEGORIES[0] ? {} : { section: cat }, { replace: false })
  }

  const handleRefresh = async () => {
    if (refreshing) return
    const cat = category
    setRefreshing(cat)
    setNotice({ tone: 'info', text: `Checking the wires for new ${sectionName(cat)} stories…` })
    try {
      const result = await refreshCategory(cat)
      put(cat, LIMIT, result.articles || [])
      if (categoryRef.current === cat) setFeed({ status: 'ready', articles: result.articles || [], error: '' })

      const text = result.added
        ? `${result.added} new ${result.added === 1 ? 'story' : 'stories'} added to ${sectionTitle(cat)}.` +
          (result.analysis_pending ? ' The analysis desk is writing them up now.' : '')
        : `No new ${sectionName(cat)} stories since the last edition.`
      setNotice({ tone: 'info', text })

      if (result.analysis_pending) {
        later(() => {
          invalidate(cat, LIMIT)
          if (categoryRef.current === cat) setReloadToken(t => t + 1)
        }, ANALYSIS_RECHECK_MS)
      }
    } catch (err) {
      setNotice({ tone: 'alert', text: errorMessage(err, 'Refresh failed.') })
    } finally {
      setRefreshing(null)
    }
  }

  const { lead, side, rest } = useMemo(() => splitFrontPage(feed.articles), [feed.articles])
  const aiOff = health.loaded && !health.features.ai_analysis

  return (
    <div>
      <SectionTabs current={category} onSelect={selectCategory} onPrefetch={(c) => prefetch(c, LIMIT)} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink py-3">
        <p aria-live="polite" className="font-mono text-xs uppercase tracking-widest text-neutral-500">
          {feed.status === 'ready' ? `${feed.articles.length} ${feed.articles.length === 1 ? 'story' : 'stories'} · ${sectionName(category)} desk` : ' '}
        </p>
        <Button
          variant="secondary"
          onClick={handleRefresh}
          disabled={!!refreshing}
          className="w-full sm:w-auto"
          aria-label={`Check for new ${sectionName(category)} stories`}
        >
          <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} strokeWidth={1.5} />
          {refreshing ? 'Checking…' : 'Check for new stories'}
        </Button>
      </div>

      {category === 'forex' && <RatesStrip />}

      <div className="mt-4 space-y-3" aria-live="polite">
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
        {feed.error && <Notice tone="alert">{feed.error}</Notice>}
        {aiOff && (
          <Notice>
            AI analysis is switched off on this server, so stories show the source excerpt only.
            Add an LLM API key to the backend to enable summaries, context and chat.
          </Notice>
        )}
      </div>

      {feed.status === 'loading' && <Loading />}

      {feed.status === 'error' && feed.articles.length === 0 && (
        <div className="py-16 text-center">
          <Button onClick={() => setReloadToken(t => t + 1)}>Try again</Button>
        </div>
      )}

      {feed.status === 'ready' && feed.articles.length === 0 && (
        <div className="my-8 border-4 border-ink px-6 py-16 text-center">
          <Kicker className="block mb-3">Nothing on the wire yet</Kicker>
          <h2 className="font-serif text-3xl font-black sm:text-4xl">The {sectionName(category)} desk is quiet.</h2>
          <p className="mt-3 font-body text-neutral-600">New stories arrive every few hours — or check the wires now.</p>
          <Button className="mt-6 w-full md:w-auto" onClick={handleRefresh} disabled={!!refreshing}>Check for new stories</Button>
        </div>
      )}

      {lead && (
        <>
          <section aria-label={`Top ${sectionName(category)} stories`} className="mt-6 grid grid-cols-1 border border-ink lg:grid-cols-12">
            <ArticleCard article={lead} variant="lead" className="border-b border-ink lg:col-span-8 lg:border-b-0 lg:border-r" />
            <div className="lg:col-span-4">
              <Figure
                label={sectionTitle(category)}
                caption={`Fig. 1.1 — The ${sectionName(category)} desk, ${new Date().toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}`}
                className="hidden border-b border-ink lg:block"
              />
              <Kicker className="block border-b border-t border-ink px-4 py-2 text-ink lg:border-t-0">Also on the desk</Kicker>
              <div className="divide-y divide-ink">
                {side.map(a => <ArticleCard key={a.id} article={a} variant="compact" />)}
              </div>
            </div>
          </section>

          {rest.length > 0 && (
            <section aria-labelledby="more-heading" className="mt-16">
              <SectionHeading id="more-heading" kicker={`${rest.length} more`} title={`More from ${sectionTitle(category)}`} />
              <div className="mt-6 grid grid-cols-1 grid-rules md:grid-cols-2 lg:grid-cols-3">
                {rest.map(a => <ArticleCard key={a.id} article={a} className="hard-shadow-hover bg-paper" />)}
              </div>
            </section>
          )}
        </>
      )}

      {category === 'forex' && <EconomicCalendar />}

      <Ornament className="mt-8" />
      <HowItWorks />
    </div>
  )
}
