import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { errorMessage, searchNews } from '../api'
import ArticleCard from '../components/ArticleCard'
import { Button, Kicker, Loading, Notice } from '../components/ui'

export function SearchForm({ initial = '', onSearch, autoFocus = false, compact = false }) {
  const [value, setValue] = useState(initial)
  useEffect(() => setValue(initial), [initial])
  const id = compact ? 'nav-search' : 'page-search'
  return (
    <form
      role="search"
      className="flex items-end gap-2"
      onSubmit={(e) => { e.preventDefault(); if (value.trim().length >= 2) onSearch(value.trim()) }}
    >
      <label htmlFor={id} className="sr-only">Search stories</label>
      <input
        id={id}
        type="search"
        value={value}
        onChange={e => setValue(e.target.value)}
        placeholder={compact ? 'Search…' : 'Search the archive: a name, place or topic'}
        autoFocus={autoFocus}
        maxLength={100}
        className={compact
          ? 'h-9 w-40 border-0 border-b-2 border-ink bg-transparent px-2 font-mono text-xs placeholder:text-neutral-500 focus-visible:bg-focus focus-visible:outline-none lg:w-52'
          : 'min-h-[44px] flex-1 border-0 border-b-2 border-ink bg-transparent px-3 py-2 font-mono text-sm placeholder:text-neutral-500 focus-visible:bg-focus focus-visible:outline-none'}
      />
      {compact ? (
        <button type="submit" aria-label="Search" className="flex h-9 w-9 items-center justify-center hover:text-accent">
          <Search className="h-4 w-4" strokeWidth={1.5} />
        </button>
      ) : (
        <Button type="submit" disabled={value.trim().length < 2}>
          <Search className="h-4 w-4" strokeWidth={1.5} /> Search
        </Button>
      )}
    </form>
  )
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const [state, setState] = useState({ status: 'idle', results: [], error: '' })

  useEffect(() => {
    if (q.trim().length < 2) { setState({ status: 'idle', results: [], error: '' }); return }
    let active = true
    setState(s => ({ ...s, status: 'loading', error: '' }))
    searchNews(q)
      .then(d => { if (active) setState({ status: 'ready', results: d.results, error: '' }) })
      .catch(err => { if (active) setState({ status: 'error', results: [], error: errorMessage(err) }) })
    return () => { active = false }
  }, [q])

  const [first, ...rest] = state.results

  return (
    <div>
      <header className="border-b-4 border-ink pb-6">
        <Kicker accent className="mb-2 block">The archive</Kicker>
        <h1 className="font-serif text-5xl font-black leading-[0.9] tracking-tighter sm:text-6xl">Search</h1>
        <div className="mt-6 max-w-2xl">
          <SearchForm initial={q} autoFocus={!q} onSearch={(v) => setParams({ q: v })} />
        </div>
        <p className="mt-3 font-mono text-[11px] uppercase tracking-widest text-neutral-500">
          Searches every story Upily has filed in the last two days
        </p>
      </header>

      {state.status === 'loading' && <Loading label="Searching the archive…" />}
      {state.status === 'error' && <Notice tone="alert" className="mt-6">{state.error}</Notice>}

      {state.status === 'ready' && state.results.length === 0 && (
        <div className="mt-8 border-4 border-ink px-6 py-16 text-center">
          <Kicker className="mb-3 block">No match</Kicker>
          <h2 className="font-serif text-3xl font-black">Nothing on “{q}” in recent coverage.</h2>
          <p className="mt-3 font-body text-neutral-600">Try a different name or a broader term — or ask the editor.</p>
        </div>
      )}

      {state.status === 'ready' && first && (
        <section aria-label={`Results for ${q}`} className="mt-6">
          <p aria-live="polite" className="mb-4 font-mono text-xs uppercase tracking-widest text-neutral-500">
            {state.results.length} {state.results.length === 1 ? 'story' : 'stories'} for “{q}”
          </p>
          <div className="border border-ink">
            <ArticleCard article={first} className="border-b border-ink" />
          </div>
          {rest.length > 0 && (
            <div className="mt-6 grid grid-cols-1 grid-rules md:grid-cols-2 lg:grid-cols-3">
              {rest.map(a => <ArticleCard key={a.id} article={a} className="hard-shadow-hover bg-paper" />)}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
