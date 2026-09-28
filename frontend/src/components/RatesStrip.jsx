import { useEffect, useRef, useState } from 'react'
import { fetchRates } from '../api'
import { cn, Kicker } from './ui'

const FLASH_MS = 1200
const ecbDate = (iso) => new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

// FX convention: 4 decimals for most pairs, 2 for large-number pairs like USD/JPY
const formatRate = (r) => r.toFixed(r >= 20 ? 2 : 4)

function secondsAgo(iso, now) {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  return s < 60 ? `${s}s ago` : `${Math.round(s / 60)} min ago`
}

/**
 * Major currency pairs. Live indicative rates refresh every `refresh_seconds` while the
 * tab is visible; a rate that moved flashes briefly. Falls back to ECB reference rates
 * (clearly labelled) if the live source is down.
 */
export default function RatesStrip() {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [ticks, setTicks] = useState({})        // pair → 'up' | 'down' for the last move
  const [now, setNow] = useState(Date.now())
  const previous = useRef({})

  useEffect(() => {
    let active = true, timer
    const load = async () => {
      try {
        const d = await fetchRates()
        if (!active) return
        const moved = {}
        for (const p of d.pairs) {
          const before = previous.current[p.pair]
          if (before != null && p.rate !== before) moved[p.pair] = p.rate > before ? 'up' : 'down'
          previous.current[p.pair] = p.rate
        }
        setData(d)
        setFailed(false)
        if (Object.keys(moved).length) {
          setTicks(moved)
          setTimeout(() => active && setTicks({}), FLASH_MS)
        }
      } catch {
        if (active) setFailed(f => f || !data)
      } finally {
        if (active) timer = setTimeout(tick, 30_000)
      }
    }
    const tick = () => (document.visibilityState === 'visible' ? load() : (timer = setTimeout(tick, 30_000)))
    const onVisible = () => { if (document.visibilityState === 'visible') { clearTimeout(timer); load() } }

    load()
    document.addEventListener('visibilitychange', onVisible)
    const clock = setInterval(() => setNow(Date.now()), 1000)
    return () => { active = false; clearTimeout(timer); clearInterval(clock); document.removeEventListener('visibilitychange', onVisible) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (failed && !data) return null   // the rest of the Forex desk still works
  if (!data) return <div className="mt-6 h-[88px] animate-pulse border border-ink bg-neutral-100" aria-hidden="true" />

  return (
    <section aria-labelledby="rates-heading" className="mt-6">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="rates-heading" className="flex items-center gap-2">
          {data.live && data.market_open !== false ? (
            <span className="inline-flex items-center gap-1.5 bg-accent px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-widest text-white">
              <span aria-hidden="true" className="h-1.5 w-1.5 animate-pulse bg-white" /> Live
            </span>
          ) : (
            <span className="border border-ink px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest">
              {data.market_open === false ? 'Market closed' : data.live ? 'Live' : 'Delayed'}
            </span>
          )}
          <Kicker className="text-ink">Currency markets</Kicker>
        </h2>
        <Kicker aria-live="off">
          {data.market_open === true && 'Market open · '}
          {data.live || data.quotes_source === 'Twelve Data'
            ? `Updated ${secondsAgo(data.as_of, now)}`
            : `ECB reference rates as of ${ecbDate(data.as_of)}`}
        </Kicker>
      </div>

      <ul className="grid grid-cols-2 grid-rules sm:grid-cols-4 lg:grid-cols-8">
        {data.pairs.map(p => {
          const up = p.change_pct > 0, down = p.change_pct < 0
          const tick = ticks[p.pair]
          return (
            <li key={p.pair} className={cn('px-3 py-3 transition-colors duration-700', tick ? 'bg-neutral-200' : 'bg-paper')}>
              <p className="flex items-center justify-between font-mono text-[10px] uppercase tracking-widest text-neutral-500">
                {p.pair}
                {tick && <span aria-hidden="true" className={tick === 'down' ? 'text-accent' : 'text-ink'}>{tick === 'up' ? '▲' : '▼'}</span>}
              </p>
              <p className="font-serif text-xl font-bold tabular-nums leading-tight">{formatRate(p.rate)}</p>
              {p.change_pct != null && (
                <p className={cn('font-mono text-[11px] tabular-nums', down ? 'text-accent' : 'text-neutral-600')}>
                  {p.change_pct > 0 ? '+' : ''}{p.change_pct.toFixed(2)}%
                  <span className="sr-only">{up ? ' up' : down ? ' down' : ' unchanged'} {data.change_basis}</span>
                </p>
              )}
              {p.low != null && p.high != null && (
                <p className="mt-0.5 font-mono text-[9px] tabular-nums text-neutral-500" title="Today's range">
                  <span className="sr-only">Day range </span>{formatRate(p.low)}–{formatRate(p.high)}
                </p>
              )}
            </li>
          )
        })}
      </ul>

      <div className="mt-2 flex flex-wrap justify-between gap-2">
        <Kicker>
          {data.live ? 'Indicative mid-market prices' : `Live prices unavailable — ${data.price_source}`}
          {' · change '}
          {data.baseline_date ? `since the ECB reference rate of ${ecbDate(data.baseline_date)}` : data.change_basis}
          {data.quotes_source === 'Twelve Data' && ' · day range'}
        </Kicker>
        <a href={data.source_url} target="_blank" rel="noopener noreferrer"
           className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 underline-offset-4 hover:text-ink hover:underline">
          Prices: {data.live ? 'Coinbase' : data.quotes_source === 'Twelve Data' ? 'Twelve Data' : 'ECB'}
          {data.quotes_source === 'Twelve Data' && data.live ? ' · Close & range: Twelve Data' : ''} ↗
        </a>
      </div>
    </section>
  )
}
