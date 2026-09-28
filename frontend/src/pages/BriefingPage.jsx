import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Pause, Play, Square, Volume2 } from 'lucide-react'
import { errorMessage, fetchBriefing } from '../api'
import { Button, cn, Kicker, Loading, Notice, Ornament } from '../components/ui'
import { editionDate, sectionTitle, timeAgo } from '../format'

const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window

/** Reads the briefing aloud with the browser's built-in speech synthesis, one story at a time. */
function useReader(items, note) {
  const [status, setStatus] = useState('idle')   // idle | playing | paused
  const [current, setCurrent] = useState(-1)     // -1 = editor's note

  useEffect(() => () => { if (canSpeak) window.speechSynthesis.cancel() }, [])

  const play = () => {
    if (!canSpeak) return
    const synth = window.speechSynthesis
    if (status === 'paused') { synth.resume(); setStatus('playing'); return }
    synth.cancel()
    const parts = [
      ...(note ? [{ index: -1, text: `Upily's briefing for ${editionDate()}. ${note}` }] : []),
      ...items.map((item, i) => ({
        index: i,
        text: `${sectionTitle(item.section)}. ${item.story.title}. ${item.story.summary || ''}`,
      })),
    ]
    parts.forEach((part, n) => {
      const u = new SpeechSynthesisUtterance(part.text)
      u.rate = 1.02
      u.onstart = () => setCurrent(part.index)
      if (n === parts.length - 1) u.onend = () => { setStatus('idle'); setCurrent(-2) }
      synth.speak(u)
    })
    setStatus('playing')
  }
  const pause = () => { window.speechSynthesis.pause(); setStatus('paused') }
  const stop = () => { window.speechSynthesis.cancel(); setStatus('idle'); setCurrent(-2) }

  return { status, current: status === 'idle' ? -2 : current, play, pause, stop }
}

export default function BriefingPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const listRef = useRef(null)

  useEffect(() => {
    let active = true
    fetchBriefing()
      .then(d => { if (active) setData(d) })
      .catch(err => { if (active) setError(errorMessage(err)) })
    return () => { active = false }
  }, [])

  const items = data?.items || []
  const reader = useReader(items, data?.editors_note)

  if (error) return <Notice tone="alert" className="mt-6">{error}</Notice>
  if (!data) return <Loading label="Assembling today’s briefing…" />

  return (
    <article>
      <header className="grid grid-cols-1 gap-6 border-b-4 border-ink pb-6 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <Kicker accent className="mb-2 block">The daily briefing · {editionDate()}</Kicker>
          <h1 className="font-serif text-5xl font-black leading-[0.9] tracking-tighter sm:text-6xl lg:text-8xl">
            Today in {data.reading_minutes} {data.reading_minutes === 1 ? 'minute' : 'minutes'}
          </h1>
        </div>
        <div className="flex flex-col justify-end gap-3 lg:col-span-4 lg:items-end">
          <p className="font-body text-sm text-neutral-600 lg:text-right">
            The top story from every desk, in one read. {items.length} stories.
          </p>
          {canSpeak && items.length > 0 && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Listen to the briefing">
              {reader.status === 'playing'
                ? <Button variant="secondary" onClick={reader.pause}><Pause className="h-4 w-4" strokeWidth={1.5} /> Pause</Button>
                : <Button onClick={reader.play}>
                    {reader.status === 'paused' ? <Play className="h-4 w-4" strokeWidth={1.5} /> : <Volume2 className="h-4 w-4" strokeWidth={1.5} />}
                    {reader.status === 'paused' ? 'Resume' : 'Listen'}
                  </Button>}
              {reader.status !== 'idle' && (
                <Button variant="ghost" onClick={reader.stop} aria-label="Stop reading"><Square className="h-4 w-4" strokeWidth={1.5} /></Button>
              )}
            </div>
          )}
        </div>
      </header>

      {data.editors_note && (
        <section aria-label="Editor’s note"
                 className={cn('newsprint-texture border-b border-ink py-8 transition-colors duration-200', reader.current === -1 && 'bg-neutral-100')}>
          <Kicker className="mb-3 block text-ink">From the editor</Kicker>
          <p className="drop-cap max-w-3xl font-body text-lg leading-relaxed text-neutral-800 text-justify hyphens-auto">
            {data.editors_note}
          </p>
        </section>
      )}

      <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-12 lg:gap-0">
        <ol ref={listRef} className="lg:col-span-8 lg:border-r lg:border-ink lg:pr-8" aria-label="Today’s top stories">
          {items.map((item, i) => (
            <li key={item.story.id}
                aria-current={reader.current === i ? 'true' : undefined}
                className={cn('grid grid-cols-[3rem_1fr] gap-4 border-b border-ink py-6 transition-colors duration-200',
                              reader.current === i && 'bg-neutral-100')}>
              <span className="font-mono text-3xl font-medium leading-none text-neutral-400">{String(i + 1).padStart(2, '0')}</span>
              <div>
                <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Kicker className="text-ink">{sectionTitle(item.section)}</Kicker>
                  <Kicker>{item.story.source}</Kicker>
                  {item.story.coverage_count > 1 && <Kicker>{item.story.coverage_count} outlets</Kicker>}
                  {item.story.published_at && <Kicker>{timeAgo(item.story.published_at)}</Kicker>}
                </div>
                <h2 className="font-serif text-2xl font-bold leading-tight text-balance lg:text-3xl">
                  <Link to={`/article/${item.story.id}`} className="decoration-accent decoration-2 underline-offset-4 hover:underline">
                    {item.story.title}
                  </Link>
                </h2>
                {item.story.summary && (
                  <p className="mt-2 font-body leading-relaxed text-neutral-700 text-justify hyphens-auto">{item.story.summary}</p>
                )}
              </div>
            </li>
          ))}
        </ol>

        <aside className="lg:col-span-4 lg:pl-8" aria-label="Markets">
          <section className="bg-ink p-6 text-paper">
            <Kicker className="mb-3 block text-neutral-400">Market movers · next 36 hours</Kicker>
            {data.market_events.length === 0 ? (
              <p className="font-body text-sm text-neutral-400">No high-impact economic releases scheduled.</p>
            ) : (
              <ul className="divide-y divide-neutral-700">
                {data.market_events.map(e => (
                  <li key={`${e.time}-${e.currency}-${e.title}`} className="py-3 first:pt-0">
                    <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-400">
                      {new Date(e.time).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' })} · {e.currency}
                    </p>
                    <p className="font-serif text-lg font-bold">{e.title}</p>
                    {(e.forecast || e.previous) && (
                      <p className="font-mono text-xs text-neutral-400">forecast {e.forecast ?? '—'} · previous {e.previous ?? '—'}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <Link to="/?section=forex" className="mt-4 inline-flex min-h-[44px] items-center font-sans text-xs font-semibold uppercase tracking-widest underline-offset-4 decoration-2 decoration-accent hover:underline">
              Full calendar & rates →
            </Link>
          </section>
        </aside>
      </div>

      <Ornament />
    </article>
  )
}
