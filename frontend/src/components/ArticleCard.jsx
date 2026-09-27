import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { Badge, cn, Kicker } from './ui'
import { timeAgo } from '../format'

/**
 * One story, three typographic weights:
 *   lead     — front-page splash with drop cap
 *   standard — grid cell in the section listing
 *   compact  — sidebar "also in" list item
 * The headline is a stretched link, so the whole card is clickable while the
 * source link stays a separate, valid anchor.
 */
export default function ArticleCard({ article, variant = 'standard', className }) {
  const href = `/article/${article.id}`
  const when = timeAgo(article.published_at || article.fetched_at)

  const meta = (
    <div className="relative z-10 flex flex-wrap items-center gap-x-3 gap-y-1">
      <Kicker className="text-ink">{article.category}</Kicker>
      <span aria-hidden="true" className="text-neutral-400">/</span>
      <Kicker>{article.source}</Kicker>
      {when && <Kicker className="ml-auto">{when}</Kicker>}
    </div>
  )

  const headline = (size) => (
    <h3 className={cn('font-serif font-bold leading-tight text-balance', size)}>
      <Link
        to={href}
        className="after:absolute after:inset-0 decoration-accent decoration-2 underline-offset-4 group-hover:underline focus-visible:outline-none"
      >
        {article.title}
      </Link>
    </h3>
  )

  const footer = (
    <div className="relative z-10 mt-auto flex flex-wrap items-center gap-2 pt-4">
      {article.is_analyzed
        ? (article.tags || []).slice(0, 3).map(t => (
            <span key={t} className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">#{t}</span>
          ))
        : <Badge tone="outline">Analysis pending</Badge>}
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Read the original at ${article.source} (opens in a new tab)`}
        className="ml-auto flex h-9 w-9 items-center justify-center border border-ink transition-colors duration-200 hover:bg-ink hover:text-paper"
      >
        <ArrowUpRight className="h-4 w-4" strokeWidth={1.5} />
      </a>
    </div>
  )

  const shell = 'group relative flex flex-col focus-within:bg-neutral-100 transition-colors duration-200'

  if (variant === 'lead') {
    return (
      <article className={cn(shell, 'p-6 lg:p-8', className)}>
        <div className="mb-4 flex items-center gap-3">
          {article.is_trending && <Badge tone="accent">Trending</Badge>}
          <Badge>Lead story</Badge>
        </div>
        {meta}
        <div className="mt-4">
          {headline('text-4xl sm:text-5xl lg:text-7xl leading-[0.95] tracking-tight font-black')}
        </div>
        {article.summary && (
          <p className={cn(article.summary.length > 140 && 'drop-cap', 'mt-6 font-body text-base leading-relaxed text-neutral-700 lg:text-lg text-justify hyphens-auto')}>
            {article.summary}
          </p>
        )}
        {footer}
      </article>
    )
  }

  if (variant === 'compact') {
    return (
      <article className={cn(shell, 'p-4 hover:bg-neutral-100', className)}>
        {meta}
        <div className="mt-2">{headline('text-lg lg:text-xl')}</div>
      </article>
    )
  }

  return (
    <article className={cn(shell, 'p-6 hover:bg-neutral-100', className)}>
      {meta}
      <div className="mt-3">{headline('text-2xl lg:text-3xl')}</div>
      {article.summary && (
        <p className="mt-3 line-clamp-4 font-body text-sm leading-relaxed text-neutral-600 text-justify hyphens-auto">
          {article.summary}
        </p>
      )}
      {footer}
    </article>
  )
}
