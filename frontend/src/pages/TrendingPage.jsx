import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, Plus, RefreshCw } from 'lucide-react'
import { errorMessage, fetchTrending } from '../api'
import { Badge, Button, cn, Kicker, Loading, Notice, SectionHeading } from '../components/ui'
import { timeAgo } from '../format'

function TopicItem({ topic, index }) {
  const [open, setOpen] = useState(index === 0)
  const panelId = `topic-${index}`
  return (
    <li className="border-b border-ink">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen(v => !v)}
          className="group grid w-full grid-cols-[3.5rem_1fr_2.75rem] items-start gap-3 py-5 text-left"
        >
          <span className="font-mono text-3xl font-medium leading-none text-neutral-400 group-hover:text-ink transition-colors">
            {String(index + 1).padStart(2, '0')}
          </span>
          <span>
            <span className="mb-2 flex flex-wrap items-center gap-2">
              {index === 0 && <Badge tone="accent">Hottest</Badge>}
              <Kicker>{topic.category}</Kicker>
            </span>
            <span className="block font-serif text-2xl font-bold leading-tight group-hover:underline decoration-accent decoration-2 underline-offset-4">
              {topic.topic}
            </span>
            {topic.headline && <span className="mt-1 block font-body text-sm text-neutral-600">{topic.headline}</span>}
          </span>
          <span className="flex h-11 w-11 items-center justify-center border border-ink transition-colors duration-200 group-hover:bg-ink group-hover:text-paper">
            <Plus className={cn('h-5 w-5 transition-transform duration-200', open && 'rotate-45')} strokeWidth={1.5} />
          </span>
        </button>
      </h3>

      <div id={panelId} className={cn('grid transition-all duration-300 ease-in-out', open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0')}>
        <div className="overflow-hidden">
          <div className="pb-5 pl-[4.25rem]">
            {topic.why_trending && (
              <p className="font-body text-sm leading-relaxed text-neutral-700 text-justify">{topic.why_trending}</p>
            )}
            {topic.articles?.length > 0 && (
              <ul className="mt-3 border-t border-divider">
                {topic.articles.map(a => {
                  const label = (
                    <span>{a.title} <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">— {a.source}</span></span>
                  )
                  const cls = 'flex items-start justify-between gap-3 py-2 font-sans text-sm hover:text-accent'
                  return (
                    <li key={a.url} className="border-b border-divider">
                      {a.id ? (
                        <Link to={`/article/${a.id}`} tabIndex={open ? undefined : -1} className={cls}>
                          {label}
                          <ArrowRight className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.5} aria-hidden="true" />
                        </Link>
                      ) : (
                        <a href={a.url} target="_blank" rel="noopener noreferrer" tabIndex={open ? undefined : -1} className={cls}>
                          {label}
                          <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.5} aria-hidden="true" />
                        </a>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </li>
  )
}

function WireItem({ article, index }) {
  return (
    <li className="border-b border-ink">
      <a href={article.url} target="_blank" rel="noopener noreferrer"
         className="group grid grid-cols-[1fr_auto] gap-4 py-4 transition-colors duration-200 hover:bg-neutral-100 sm:grid-cols-[6rem_1fr_auto]">
        <figure className="hidden sm:block">
          <div className="aspect-square overflow-hidden border border-ink bg-neutral-200">
            {article.image ? (
              <img src={article.image} alt="" loading="lazy"
                   className="h-full w-full object-cover grayscale transition-all duration-200 group-hover:scale-105 group-hover:sepia-[.5]"
                   onError={e => { e.currentTarget.style.display = 'none' }} />
            ) : (
              <div className="h-full w-full halftone opacity-10" />
            )}
          </div>
          <figcaption className="mt-1 font-mono text-[9px] uppercase tracking-widest text-neutral-500">Fig. 2.{index + 1}</figcaption>
        </figure>
        <div>
          <div className="mb-1 flex flex-wrap gap-x-3">
            <Kicker className="text-ink">{article.source}</Kicker>
            {article.published_at && <Kicker>{timeAgo(article.published_at)}</Kicker>}
          </div>
          <p className="font-serif text-lg font-bold leading-snug group-hover:underline decoration-accent decoration-2 underline-offset-4">
            {article.title}
          </p>
          {article.summary && <p className="mt-1 line-clamp-2 font-body text-sm text-neutral-600">{article.summary}</p>}
        </div>
        <ArrowUpRight className="h-4 w-4 shrink-0" strokeWidth={1.5} aria-hidden="true" />
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    </li>
  )
}

export default function TrendingPage() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading')   // loading | ready | error
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async (force = false) => {
    force ? setRefreshing(true) : setStatus('loading')
    setError('')
    try {
      setData(await fetchTrending(force))
      setStatus('ready')
    } catch (err) {
      setError(errorMessage(err))
      setStatus(s => (s === 'loading' ? 'error' : s))
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const topics = data?.topics || []
  const articles = data?.articles || []

  return (
    <div>
      <header className="grid grid-cols-1 gap-6 border-b-4 border-ink pb-6 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <Kicker accent className="block mb-2">Live from the wires</Kicker>
          <h1 className="font-serif text-6xl font-black leading-[0.9] tracking-tighter sm:text-7xl lg:text-9xl">The Pulse</h1>
        </div>
        <div className="flex flex-col justify-end gap-3 lg:col-span-4 lg:items-end">
          <p className="font-body text-sm leading-relaxed text-neutral-600 lg:text-right">
            The stories every newsroom is chasing right now, grouped into the day’s biggest topics.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {data?.fetched_at && <Kicker>Updated {timeAgo(data.fetched_at)}</Kicker>}
            <Button variant="secondary" onClick={() => load(true)} disabled={refreshing || status === 'loading'} className="w-full sm:w-auto">
              <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} strokeWidth={1.5} />
              {refreshing ? 'Updating…' : 'Update'}
            </Button>
          </div>
        </div>
      </header>

      {error && <Notice tone="alert" className="mt-6">{error}</Notice>}
      {status === 'loading' && <Loading label="Reading the wires…" />}

      {status === 'ready' && articles.length === 0 && (
        <div className="mt-8 border-4 border-ink px-6 py-16 text-center">
          <Kicker className="block mb-3">The wires are silent</Kicker>
          <h2 className="font-serif text-3xl font-black">No live headlines right now.</h2>
          <p className="mx-auto mt-3 max-w-lg font-body text-neutral-600">
            {data?.configured === false
              ? 'The Pulse needs a GNews or SerpAPI key on the server.'
              : 'The news services didn’t answer. Try updating in a minute.'}
          </p>
        </div>
      )}

      {status === 'ready' && articles.length > 0 && (
        <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-12 lg:gap-0">
          <section aria-labelledby="topics-heading" className="lg:col-span-5 lg:border-r lg:border-ink lg:pr-8">
            <SectionHeading id="topics-heading" kicker="Ranked by coverage" title="Top topics" />
            {data.ai_topics === false && (
              <Notice className="mt-4">Topic grouping is unavailable, so these are the top individual headlines.</Notice>
            )}
            <ol className="mt-2">
              {topics.map((t, i) => <TopicItem key={`${t.topic}-${i}`} topic={t} index={i} />)}
            </ol>
          </section>

          <section aria-labelledby="wire-heading" className="lg:col-span-7 lg:pl-8">
            <SectionHeading id="wire-heading" kicker={`${data.total} live stories`} title="On the wire" />
            <ul className="mt-2">
              {articles.map((a, i) => <WireItem key={a.url} article={a} index={i} />)}
            </ul>
          </section>
        </div>
      )}
    </div>
  )
}
