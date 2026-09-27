import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Pause, Play } from 'lucide-react'
import { useNewsCache } from '../NewsCache'
import { cn } from './ui'

/**
 * Breaking-news crawl of the latest stored headlines. Scrolls continuously.
 * Clicking the crawl stops it; while stopped, a headline click opens the story
 * and a click on empty space (or the play button) starts it again.
 */
export default function Ticker() {
  const { getArticles } = useNewsCache()
  const [items, setItems] = useState([])
  const [paused, setPaused] = useState(false)

  useEffect(() => getArticles(null, 12, { onData: e => setItems(e.articles) }), [getArticles])

  if (items.length === 0) return null

  // Capture phase runs before <Link>'s own handler, so preventDefault cancels navigation
  const onClickCapture = (e) => {
    if (!paused) {
      e.preventDefault()
      setPaused(true)
    } else if (!e.target.closest('a')) {
      setPaused(false)
    }
  }

  const row = (copy) => (
    <ul className="flex shrink-0 items-center" aria-hidden={copy || undefined}>
      {items.map(a => (
        <li key={`${copy}-${a.id}`} className="flex items-center">
          <Link
            to={`/article/${a.id}`}
            tabIndex={copy ? -1 : undefined}
            className={cn(
              'px-6 font-sans text-sm text-paper whitespace-nowrap underline-offset-4 decoration-accent decoration-2',
              paused && 'hover:underline',
            )}
          >
            <span className="mr-2 font-mono text-[10px] uppercase tracking-widest text-neutral-400">{a.category}</span>
            {a.title}
          </Link>
          <span aria-hidden="true" className="text-accent">&#x25A0;</span>
        </li>
      ))}
    </ul>
  )

  return (
    <div className="flex border-b border-ink bg-ink text-paper" role="region" aria-label="Latest headlines">
      <span className="z-10 flex w-20 shrink-0 items-center justify-center bg-accent px-3 py-2 font-mono text-[10px] font-medium uppercase tracking-widest text-white">
        {paused ? 'Paused' : 'Latest'}
      </span>

      <div
        onClickCapture={onClickCapture}
        title={paused ? 'Click a headline to read it, or empty space to resume' : 'Click to stop'}
        className={cn('relative min-w-0 flex-1 overflow-hidden py-2', paused ? 'cursor-default' : 'cursor-pointer')}
      >
        <div
          className="ticker-track flex w-max animate-ticker [&:has(:focus-visible)]:[animation-play-state:paused]"
          style={{
            animationDuration: `${Math.max(45, items.length * 7)}s`,
            animationPlayState: paused ? 'paused' : 'running',
          }}
        >
          {row(false)}
          {row(true)}
        </div>
      </div>

      <button
        type="button"
        onClick={() => setPaused(p => !p)}
        aria-pressed={paused}
        aria-label={paused ? 'Resume headline ticker' : 'Pause headline ticker'}
        className="z-10 flex w-11 shrink-0 items-center justify-center border-l border-neutral-700 text-paper transition-colors duration-200 hover:bg-paper hover:text-ink"
      >
        {paused ? <Play className="h-4 w-4" strokeWidth={1.5} /> : <Pause className="h-4 w-4" strokeWidth={1.5} />}
      </button>
    </div>
  )
}
