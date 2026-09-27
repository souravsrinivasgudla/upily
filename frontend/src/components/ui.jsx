/**
 * Newsprint UI primitives. Variants live in plain maps so every page shares
 * one definition of "primary button", "kicker label", etc.
 */
import { Link } from 'react-router-dom'

export const cn = (...classes) => classes.filter(Boolean).join(' ')

// ── Button ────────────────────────────────────────────────────────────────────
const BUTTON_BASE =
  'inline-flex items-center justify-center gap-2 min-h-[44px] px-5 font-sans text-xs font-semibold ' +
  'uppercase tracking-widest transition-all duration-200 ease-out disabled:opacity-40 ' +
  'disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-paper'

const BUTTON_VARIANTS = {
  primary:   'bg-ink text-paper border border-transparent hover:bg-paper hover:text-ink hover:border-ink',
  secondary: 'border border-ink bg-transparent text-ink hover:bg-ink hover:text-paper',
  ghost:     'text-ink hover:bg-divider',
  link:      'min-h-0 px-0 normal-case tracking-normal text-sm text-ink underline-offset-4 decoration-2 decoration-accent hover:underline',
  inverted:  'border border-paper text-paper hover:bg-paper hover:text-ink',
}

export function Button({ variant = 'primary', className, as: As = 'button', ...props }) {
  const extra = As === 'button' && !props.type ? { type: 'button' } : {}
  return <As className={cn(BUTTON_BASE, BUTTON_VARIANTS[variant], className)} {...extra} {...props} />
}

export function ButtonLink({ variant = 'primary', className, ...props }) {
  return <Link className={cn(BUTTON_BASE, BUTTON_VARIANTS[variant], className)} {...props} />
}

// ── Labels & rules ────────────────────────────────────────────────────────────
export function Kicker({ children, className, accent = false, as: As = 'span', ...props }) {
  return (
    <As className={cn('font-mono text-[11px] uppercase tracking-widest', accent ? 'text-accent' : 'text-neutral-500', className)} {...props}>
      {children}
    </As>
  )
}

export function Badge({ children, tone = 'ink', className }) {
  const tones = {
    ink:    'bg-ink text-paper',
    accent: 'bg-accent text-white',
    outline:'border border-ink text-ink',
  }
  return (
    <span className={cn('inline-block px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-widest', tones[tone], className)}>
      {children}
    </span>
  )
}

export function Ornament({ className }) {
  return (
    <div aria-hidden="true" className={cn('py-8 text-center font-serif text-2xl text-neutral-400 tracking-[1em]', className)}>
      &#x2727;&#x2727;&#x2727;
    </div>
  )
}

export function SectionHeading({ kicker, title, aside, className, id }) {
  return (
    <div className={cn('flex flex-wrap items-end justify-between gap-4 border-b-4 border-ink pb-3', className)}>
      <div>
        {kicker && <Kicker className="block mb-1">{kicker}</Kicker>}
        <h2 id={id} className="font-serif font-black text-3xl sm:text-4xl lg:text-5xl leading-none tracking-tight">{title}</h2>
      </div>
      {aside}
    </div>
  )
}

// ── Feedback ──────────────────────────────────────────────────────────────────
export function Notice({ children, tone = 'info', className, role }) {
  const tones = {
    info:  'border-ink bg-paper',
    alert: 'border-accent bg-paper',
  }
  return (
    <div role={role ?? (tone === 'alert' ? 'alert' : 'status')}
         className={cn('border-l-4 border px-4 py-3 font-sans text-sm', tones[tone], className)}>
      {tone === 'alert' && <span className="mr-2 font-mono text-[11px] uppercase tracking-widest text-accent">Notice</span>}
      {children}
    </div>
  )
}

export function Loading({ label = 'Setting the type…', className }) {
  return (
    <div role="status" aria-live="polite" className={cn('flex flex-col items-center gap-4 py-24', className)}>
      <div className="flex gap-1.5" aria-hidden="true">
        {[0, 1, 2].map(i => (
          <span key={i} className="h-3 w-3 bg-ink animate-pulse" style={{ animationDelay: `${i * 150}ms` }} />
        ))}
      </div>
      <Kicker>{label}</Kicker>
    </div>
  )
}

/** Halftone-dot figure used where a story has no photograph. */
export function Figure({ label, caption, className }) {
  return (
    <figure className={className}>
      <div className="relative aspect-[4/3] overflow-hidden bg-neutral-200">
        <div className="absolute inset-0 halftone opacity-10" />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-serif font-black italic text-5xl lg:text-6xl text-ink/80">{label}</span>
        </div>
      </div>
      {caption && (
        <figcaption className="border-t border-ink px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-neutral-500">
          {caption}
        </figcaption>
      )}
    </figure>
  )
}
