import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Settings2, X } from 'lucide-react'
import { errorMessage, searchNews } from '../api'
import { useNewsCache } from '../NewsCache'
import { preferences, usePreferences } from '../preferences'
import ArticleCard from '../components/ArticleCard'
import { Button, cn, Kicker, Notice, SectionHeading } from '../components/ui'
import { sectionName, sectionTitle } from '../format'
import { CATEGORIES } from './Dashboard'

const SUGGESTED_TOPICS = ['OpenAI', 'RBI', 'Cricket', 'Federal Reserve', 'Climate', 'Nvidia', 'Elections', 'Space']
const PER_BLOCK = 3

function TopicBlock({ topic }) {
  const [state, setState] = useState({ status: 'loading', results: [], error: '' })
  useEffect(() => {
    let active = true
    searchNews(topic, PER_BLOCK)
      .then(d => { if (active) setState({ status: 'ready', results: d.results, error: '' }) })
      .catch(err => { if (active) setState({ status: 'error', results: [], error: errorMessage(err) }) })
    return () => { active = false }
  }, [topic])

  return (
    <section aria-label={`Following ${topic}`} className="border-b border-ink py-6">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-2xl font-bold">{topic}</h3>
        <Link to={`/search?q=${encodeURIComponent(topic)}`} className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 hover:text-accent">
          All results →
        </Link>
      </div>
      {state.status === 'loading' && <Kicker className="animate-pulse">Looking for {topic}…</Kicker>}
      {state.status === 'error' && <Notice tone="alert">{state.error}</Notice>}
      {state.status === 'ready' && state.results.length === 0 && (
        <p className="font-body text-sm text-neutral-500">Nothing on {topic} in the last two days.</p>
      )}
      {state.results.length > 0 && (
        <div className="grid grid-cols-1 grid-rules md:grid-cols-3">
          {state.results.map(a => <ArticleCard key={a.id} article={a} variant="compact" className="bg-paper" />)}
        </div>
      )}
    </section>
  )
}

function SectionBlock({ category }) {
  const { getArticles } = useNewsCache()
  const [articles, setArticles] = useState(null)
  useEffect(() => getArticles(category, 20, {
    onData: e => setArticles(e.articles),
    onError: () => setArticles([]),
  }), [category, getArticles])

  const top = [...(articles || [])].sort((a, b) => (b.importance_score ?? 0) - (a.importance_score ?? 0)).slice(0, PER_BLOCK)
  return (
    <section aria-label={`${sectionTitle(category)} desk`} className="border-b border-ink py-6">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-2xl font-bold">{sectionTitle(category)}</h3>
        <Link to={`/?section=${category}`} className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 hover:text-accent">
          Whole section →
        </Link>
      </div>
      {articles === null && <Kicker className="animate-pulse">Loading…</Kicker>}
      {articles?.length === 0 && <p className="font-body text-sm text-neutral-500">The {sectionName(category)} desk is quiet.</p>}
      {top.length > 0 && (
        <div className="grid grid-cols-1 grid-rules md:grid-cols-3">
          {top.map(a => <ArticleCard key={a.id} article={a} variant="compact" className="bg-paper" />)}
        </div>
      )}
    </section>
  )
}

function Settings({ prefs }) {
  const [draft, setDraft] = useState('')
  const add = (t) => { if (preferences.addTopic(t)) setDraft('') }
  return (
    <div className="space-y-8">
      <section aria-labelledby="pick-sections">
        <Kicker as="h3" id="pick-sections" className="mb-3 block text-ink">Your sections</Kicker>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map(cat => {
            const on = prefs.sections.includes(cat)
            return (
              <button key={cat} type="button" aria-pressed={on} onClick={() => preferences.toggleSection(cat)}
                      className={cn('min-h-[40px] border border-ink px-3 font-sans text-xs font-semibold uppercase tracking-widest transition-colors duration-200',
                                    on ? 'bg-ink text-paper' : 'hover:bg-neutral-100')}>
                {sectionName(cat)}
              </button>
            )
          })}
        </div>
      </section>

      <section aria-labelledby="pick-topics">
        <Kicker as="h3" id="pick-topics" className="mb-3 block text-ink">Topics you follow</Kicker>
        {prefs.topics.length > 0 && (
          <ul className="mb-3 flex flex-wrap gap-2">
            {prefs.topics.map(t => (
              <li key={t} className="flex items-center border border-ink">
                <span className="px-3 font-sans text-sm">{t}</span>
                <button type="button" onClick={() => preferences.removeTopic(t)} aria-label={`Stop following ${t}`}
                        className="flex h-9 w-9 items-center justify-center border-l border-ink hover:bg-ink hover:text-paper">
                  <X className="h-3.5 w-3.5" strokeWidth={1.5} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); add(draft) }}>
          <label htmlFor="topic-input" className="sr-only">Add a topic</label>
          <input id="topic-input" value={draft} onChange={e => setDraft(e.target.value)} maxLength={40}
                 placeholder="Add a name, company, place…"
                 className="min-h-[44px] flex-1 border-0 border-b-2 border-ink bg-transparent px-3 py-2 font-mono text-sm placeholder:text-neutral-500 focus-visible:bg-focus focus-visible:outline-none" />
          <Button type="submit" variant="secondary" disabled={draft.trim().length < 2} aria-label="Follow topic">
            <Plus className="h-4 w-4" strokeWidth={1.5} /> Follow
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED_TOPICS.filter(t => !prefs.topics.some(p => p.toLowerCase() === t.toLowerCase())).map(t => (
            <button key={t} type="button" onClick={() => add(t)}
                    className="min-h-[36px] border border-dashed border-neutral-400 px-3 font-sans text-xs text-neutral-600 hover:border-ink hover:text-ink">
              + {t}
            </button>
          ))}
        </div>
      </section>

      <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
        Saved in this browser only · no account needed
      </p>
      {(prefs.sections.length > 0 || prefs.topics.length > 0) && (
        <Button variant="ghost" className="-ml-3 px-3" onClick={() => preferences.reset()}>Clear my edition</Button>
      )}
    </div>
  )
}

export default function MyUpilyPage() {
  const prefs = usePreferences()
  const empty = prefs.sections.length === 0 && prefs.topics.length === 0
  const [editing, setEditing] = useState(false)
  const showSettings = empty || editing

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4 border-b-4 border-ink pb-6">
        <div>
          <Kicker accent className="mb-2 block">Your personal edition</Kicker>
          <h1 className="font-serif text-5xl font-black leading-[0.9] tracking-tighter sm:text-6xl lg:text-8xl">My Upily</h1>
        </div>
        {!empty && (
          <Button variant="secondary" onClick={() => setEditing(v => !v)} aria-expanded={editing} aria-controls="my-settings">
            <Settings2 className="h-4 w-4" strokeWidth={1.5} /> {editing ? 'Done' : 'Edit my edition'}
          </Button>
        )}
      </header>

      <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-12 lg:gap-0">
        <div className={cn(showSettings ? 'lg:col-span-7 lg:border-r lg:border-ink lg:pr-8' : 'lg:col-span-12')}>
          {empty ? (
            <div className="border-4 border-ink px-6 py-12">
              <Kicker className="mb-3 block">Build your edition</Kicker>
              <h2 className="font-serif text-3xl font-black sm:text-4xl">Choose what lands on your front page.</h2>
              <p className="drop-cap mt-4 font-body leading-relaxed text-neutral-700 text-justify">
                Pick the desks you read every day and the names, companies or places you want to track.
                Upily then assembles a page of just those stories, refreshed with every edition.
              </p>
            </div>
          ) : (
            <>
              {prefs.topics.length > 0 && (
                <section aria-labelledby="following-heading">
                  <SectionHeading id="following-heading" kicker={`${prefs.topics.length} followed`} title="Following" />
                  {prefs.topics.map(t => <TopicBlock key={t} topic={t} />)}
                </section>
              )}
              {prefs.sections.length > 0 && (
                <section aria-labelledby="desks-heading" className={cn(prefs.topics.length > 0 && 'mt-12')}>
                  <SectionHeading id="desks-heading" kicker="Top three from each" title="Your desks" />
                  {prefs.sections.map(c => <SectionBlock key={c} category={c} />)}
                </section>
              )}
            </>
          )}
        </div>

        {showSettings && (
          <aside id="my-settings" className="lg:col-span-5 lg:pl-8" aria-label="Edit my edition">
            <Settings prefs={prefs} />
          </aside>
        )}
      </div>
    </div>
  )
}
