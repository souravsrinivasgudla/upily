import { useEffect, useMemo, useState } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { errorMessage, fetchCalendar } from '../api'
import { cn, Kicker, Loading, Notice, SectionHeading } from './ui'

const FILTERS = [
  { key: 'High',        label: 'High impact',    impacts: ['High'] },
  { key: 'High,Medium', label: 'High + medium',  impacts: ['High', 'Medium'] },
  { key: 'all',         label: 'All',            impacts: null },
]

function ImpactMark({ impact }) {
  const styles = {
    High:    'bg-accent border-accent',
    Medium:  'bg-ink border-ink',
    Low:     'bg-transparent border-neutral-400',
    Holiday: 'bg-transparent border-neutral-400 border-dashed',
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden="true" className={cn('inline-block h-2.5 w-2.5 border', styles[impact] || styles.Low)} />
      <span className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">{impact}</span>
    </span>
  )
}

const dayLabel = (d) => d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
const timeLabel = (d) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

/** This week's economic calendar from Forex Factory, grouped by day, times in the reader's zone. */
export default function EconomicCalendar() {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [filter, setFilter] = useState(FILTERS[0])

  useEffect(() => {
    let active = true
    fetchCalendar()
      .then(d => { if (active) { setData(d); setStatus('ready') } })
      .catch(err => { if (active) { setError(errorMessage(err)); setStatus('error') } })
    return () => { active = false }
  }, [])

  const days = useMemo(() => {
    const events = (data?.events || []).filter(e => !filter.impacts || filter.impacts.includes(e.impact))
    const byDay = new Map()
    for (const e of events) {
      const when = e.time ? new Date(e.time) : null
      const key = when ? when.toDateString() : 'Unscheduled'
      if (!byDay.has(key)) byDay.set(key, { label: when ? dayLabel(when) : key, events: [] })
      byDay.get(key).events.push({ ...e, when })
    }
    return [...byDay.values()]
  }, [data, filter])

  const now = Date.now()

  return (
    <section aria-labelledby="calendar-heading" className="mt-16">
      <SectionHeading
        id="calendar-heading"
        kicker="The week ahead · via Forex Factory"
        title="Economic calendar"
        aside={
          <div className="flex flex-wrap border border-ink" role="group" aria-label="Filter by impact">
            {FILTERS.map(f => (
              <button
                key={f.key}
                type="button"
                aria-pressed={filter.key === f.key}
                onClick={() => setFilter(f)}
                className={cn(
                  'min-h-[44px] border-r border-ink px-3 font-sans text-xs font-semibold uppercase tracking-widest last:border-r-0 transition-colors duration-200',
                  filter.key === f.key ? 'bg-ink text-paper' : 'hover:bg-neutral-100',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        }
      />

      {status === 'loading' && <Loading label="Reading the calendar…" className="py-12" />}
      {status === 'error' && <Notice tone="alert" className="mt-6">{error}</Notice>}
      {data?.stale && <Notice className="mt-6">Showing the last saved calendar — Forex Factory didn’t respond just now.</Notice>}

      {status === 'ready' && (
        days.length === 0 ? (
          <p className="mt-6 font-body text-neutral-600">No events at this impact level this week.</p>
        ) : (
          <div className="mt-6 overflow-x-auto border border-ink">
            <table className="w-full min-w-[640px] border-collapse text-left">
              <caption className="sr-only">Economic events this week, times shown in your time zone</caption>
              <thead>
                <tr className="border-b-2 border-ink">
                  {['Time', 'Cur.', 'Event', 'Impact', 'Forecast', 'Previous'].map((h, i) => (
                    <th key={h} scope="col"
                        className={cn('px-3 py-2 font-mono text-[10px] font-medium uppercase tracking-widest text-neutral-500',
                                      i >= 4 && 'text-right')}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              {days.map(day => (
                <tbody key={day.label}>
                  <tr className="bg-ink text-paper">
                    <th colSpan={6} scope="colgroup" className="px-3 py-1.5 font-mono text-[11px] font-medium uppercase tracking-widest">
                      {day.label}
                    </th>
                  </tr>
                  {day.events.map((e, i) => {
                    const past = e.when && e.when.getTime() < now
                    return (
                      <tr key={`${e.time}-${e.currency}-${e.title}-${i}`}
                          className={cn('border-b border-divider last:border-b-0', past && 'opacity-50')}>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">
                          {e.when ? timeLabel(e.when) : 'All day'}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs font-medium">{e.currency}</td>
                        <td className={cn('px-3 py-2 font-body text-sm', e.impact === 'High' && 'font-semibold')}>{e.title}</td>
                        <td className="px-3 py-2"><ImpactMark impact={e.impact} /></td>
                        <td className="px-3 py-2 text-right font-mono text-xs">{e.forecast ?? '—'}</td>
                        <td className="px-3 py-2 text-right font-mono text-xs text-neutral-500">{e.previous ?? '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              ))}
            </table>
          </div>
        )
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <Kicker>Times in your time zone · past events faded</Kicker>
        <a href={data?.source_url || 'https://www.forexfactory.com/calendar'} target="_blank" rel="noopener noreferrer"
           className="inline-flex min-h-[44px] items-center gap-1 font-sans text-sm font-semibold underline-offset-4 decoration-2 decoration-accent hover:underline">
          Full calendar on Forex Factory <ArrowUpRight className="h-4 w-4" strokeWidth={1.5} />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      </div>
    </section>
  )
}
