import { useEffect, useState } from 'react'
import { fetchRates } from '../api'
import { cn, Kicker } from './ui'

const asOf = (iso) => new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

/** Major currency pairs from the ECB's daily reference rates, with the change on the day. */
export default function RatesStrip() {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    fetchRates().then(d => { if (active) setData(d) }).catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [])

  if (failed) return null   // the rest of the Forex desk still works
  if (!data) return <div className="mt-6 h-[88px] border border-ink bg-neutral-100 animate-pulse" aria-hidden="true" />

  return (
    <section aria-labelledby="rates-heading" className="mt-6">
      <h2 id="rates-heading" className="sr-only">Currency reference rates</h2>
      <ul className="grid grid-cols-2 grid-rules sm:grid-cols-4 lg:grid-cols-8">
        {data.pairs.map(p => {
          const up = p.change_pct > 0, down = p.change_pct < 0
          return (
            <li key={p.pair} className="bg-paper px-3 py-3">
              <p className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">{p.pair}</p>
              <p className="font-serif text-xl font-bold leading-tight">{p.rate}</p>
              {p.change_pct != null && (
                <p className={cn('font-mono text-[11px]', down ? 'text-accent' : 'text-neutral-600')}>
                  <span aria-hidden="true">{up ? '▲' : down ? '▼' : '■'}</span>{' '}
                  {p.change_pct > 0 ? '+' : ''}{p.change_pct.toFixed(2)}%
                  <span className="sr-only">{up ? ' up' : down ? ' down' : ' unchanged'} on the previous day</span>
                </p>
              )}
            </li>
          )
        })}
      </ul>
      <div className="mt-2 flex flex-wrap justify-between gap-2">
        <Kicker>
          ECB reference rates · as of {asOf(data.as_of)} · change vs previous day{data.stale ? ' · last saved copy' : ''}
        </Kicker>
        <a href={data.source_url} target="_blank" rel="noopener noreferrer"
           className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 underline-offset-4 hover:text-ink hover:underline">
          Daily reference, not live quotes ↗
        </a>
      </div>
    </section>
  )
}
