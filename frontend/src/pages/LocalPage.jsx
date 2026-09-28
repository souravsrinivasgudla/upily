import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import { errorMessage, fetchDistricts, fetchLocalNews, fetchStates } from '../api'
import { preferences, usePreferences } from '../preferences'
import ArticleCard from '../components/ArticleCard'
import { cn, Kicker, Loading, Notice, SectionHeading } from '../components/ui'

function Select({ id, label, value, onChange, disabled, children, hint }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1 border-b border-ink px-4 py-3 md:border-b-0 md:border-r md:last:border-r-0">
      <label htmlFor={id} className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">{label}</label>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        className="min-h-[44px] w-full border-0 border-b-2 border-ink bg-transparent px-1 font-sans text-sm font-semibold focus-visible:bg-focus focus-visible:outline-none disabled:border-neutral-300 disabled:text-neutral-400"
      >
        {children}
      </select>
      {hint && <span className="font-mono text-[10px] text-neutral-500">{hint}</span>}
    </div>
  )
}

function StoryBlock({ id, kicker, title, stories, empty }) {
  const [first, ...rest] = stories
  return (
    <section aria-labelledby={id} className="mt-12">
      <SectionHeading id={id} kicker={kicker} title={title} />
      {stories.length === 0 ? (
        <p className="mt-6 font-body text-neutral-600">{empty}</p>
      ) : (
        <>
          <div className="mt-6 border border-ink">
            <ArticleCard article={first} />
          </div>
          {rest.length > 0 && (
            <div className="mt-6 grid grid-cols-1 grid-rules md:grid-cols-2 lg:grid-cols-3">
              {rest.map(a => <ArticleCard key={a.id} article={a} className="hard-shadow-hover bg-paper" />)}
            </div>
          )}
        </>
      )}
    </section>
  )
}

export default function LocalPage() {
  const prefs = usePreferences()
  const [params, setParams] = useSearchParams()
  // URL wins (shareable links); otherwise the reader's saved area
  const state = params.get('state') || prefs.location?.state || ''
  const district = params.get('state') ? (params.get('district') || '') : (prefs.location?.district || '')

  const [states, setStates] = useState([])
  const [districts, setDistricts] = useState([])
  const [feed, setFeed] = useState({ status: 'idle', data: null, error: '' })

  useEffect(() => { fetchStates().then(setStates).catch(() => setStates([])) }, [])

  useEffect(() => {
    setDistricts([])
    if (!state) return
    let active = true
    fetchDistricts(state).then(d => { if (active) setDistricts(d) }).catch(() => {})
    return () => { active = false }
  }, [state])

  useEffect(() => {
    if (!state) { setFeed({ status: 'idle', data: null, error: '' }); return }
    let active = true
    setFeed(f => ({ ...f, status: 'loading', error: '' }))
    fetchLocalNews(state, district || null)
      .then(data => { if (active) setFeed({ status: 'ready', data, error: '' }) })
      .catch(err => { if (active) setFeed({ status: 'error', data: null, error: errorMessage(err) }) })
    return () => { active = false }
  }, [state, district])

  const choose = (nextState, nextDistrict = '') => {
    preferences.setLocation(nextState, nextDistrict)
    setParams(nextState ? { state: nextState, ...(nextDistrict ? { district: nextDistrict } : {}) } : {})
  }

  const data = feed.data
  const place = district ? `${district}, ${state}` : state

  return (
    <div>
      <header className="border-b-4 border-ink pb-6">
        <Kicker accent className="mb-2 block">Your area</Kicker>
        <h1 className="flex items-end gap-3 font-serif text-5xl font-black leading-[0.9] tracking-tighter sm:text-6xl lg:text-8xl">
          Local
        </h1>
        {place && (
          <p className="mt-3 flex items-center gap-2 font-serif text-2xl font-bold">
            <MapPin className="h-5 w-5" strokeWidth={1.5} aria-hidden="true" /> {place}
          </p>
        )}
      </header>

      <div className="mt-6 flex flex-col border border-ink md:flex-row" role="group" aria-label="Choose your area">
        <Select id="loc-country" label="Country" value="IN" onChange={() => {}} disabled hint="Local news covers India">
          <option value="IN">India</option>
        </Select>
        <Select id="loc-state" label="State / union territory" value={state} onChange={v => choose(v)}>
          <option value="">Choose a state…</option>
          {states.map(s => <option key={s} value={s}>{s}</option>)}
        </Select>
        <Select id="loc-district" label="District" value={district} disabled={!state || districts.length === 0}
                onChange={v => choose(state, v)}
                hint={state ? `${districts.length} districts` : 'Choose a state first'}>
          <option value="">{state ? `All of ${state}` : '—'}</option>
          {districts.map(d => <option key={d} value={d}>{d}</option>)}
        </Select>
      </div>

      {!state && (
        <div className="mt-8 border-4 border-ink px-6 py-16 text-center">
          <Kicker className="mb-3 block">Pick your area</Kicker>
          <h2 className="font-serif text-3xl font-black sm:text-4xl">News from your state and district.</h2>
          <p className="mx-auto mt-3 max-w-lg font-body text-neutral-600">
            Choose a state or union territory, then narrow it down to your district. Upily remembers your choice.
          </p>
        </div>
      )}

      {feed.status === 'loading' && <Loading label={`Gathering news from ${place}…`} />}
      {feed.status === 'error' && <Notice tone="alert" className="mt-6">{feed.error}</Notice>}

      {feed.status === 'ready' && data && (
        <>
          {district && (
            <StoryBlock
              id="district-heading"
              kicker={`${data.district_stories.length} ${data.district_stories.length === 1 ? 'story' : 'stories'}`}
              title={`In ${district}`}
              stories={data.district_stories}
              empty={`No recent stories name ${district}. Here's the latest from across ${state}.`}
            />
          )}
          <StoryBlock
            id="state-heading"
            kicker={district ? 'The wider state' : `${data.state_stories.length} stories`}
            title={district ? `Across ${state}` : `${state}`}
            stories={data.state_stories}
            empty={`No recent stories from ${state}.`}
          />
          {data.sources.length > 0 && (
            <p className={cn('mt-8 font-mono text-[11px] uppercase tracking-widest text-neutral-500')}>
              From {data.sources.slice(0, 8).join(' · ')}{data.sources.length > 8 ? ` and ${data.sources.length - 8} more` : ''}
            </p>
          )}
        </>
      )}
    </div>
  )
}
