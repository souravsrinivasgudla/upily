import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useNewsCache } from '../NewsCache'

/** Breaking-news crawl of the latest stored headlines. Pauses on hover and focus. */
export default function Ticker() {
  const { getArticles } = useNewsCache()
  const [items, setItems] = useState([])

  useEffect(() => getArticles(null, 12, { onData: e => setItems(e.articles) }), [getArticles])

  if (items.length === 0) return null

  const row = (hidden) => (
    <ul className="flex shrink-0 items-center" aria-hidden={hidden || undefined}>
      {items.map(a => (
        <li key={`${hidden}-${a.id}`} className="flex items-center">
          <Link
            to={`/article/${a.id}`}
            tabIndex={hidden ? -1 : undefined}
            className="px-6 font-sans text-sm text-paper hover:underline decoration-accent decoration-2 underline-offset-4 whitespace-nowrap"
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
    <div className="flex border-b border-ink bg-ink text-paper" aria-label="Latest headlines">
      <span className="z-10 flex shrink-0 items-center bg-accent px-3 py-2 font-mono text-[10px] font-medium uppercase tracking-widest text-white">
        Latest
      </span>
      <div className="group relative min-w-0 flex-1 overflow-hidden py-2">
        <div className="flex w-max animate-ticker group-hover:[animation-play-state:paused] group-focus-within:[animation-play-state:paused]">
          {row(false)}
          {row(true)}
        </div>
      </div>
    </div>
  )
}
