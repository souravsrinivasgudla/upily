import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Menu, Search, X } from 'lucide-react'
import Ticker from './Ticker'
import { cn, Kicker } from './ui'
import { editionDate, editionNumber } from '../format'
import { useHealth } from '../useHealth'
import { SearchForm } from '../pages/SearchPage'

const NAV = [
  { to: '/',         label: 'Front Page' },
  { to: '/briefing', label: 'Briefing' },
  { to: '/my',       label: 'My Upily' },
  { to: '/trending', label: 'The Pulse' },
  { to: '/chat',     label: 'Ask the Editor' },
]

function Masthead() {
  const { vol, no } = editionNumber()
  return (
    <header className="newsprint-texture border-b border-ink">
      <div className="mx-auto max-w-page px-4">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-ink py-2">
          <Kicker>Vol. {vol} · No. {no}</Kicker>
          <Kicker className="hidden sm:inline">{editionDate()}</Kicker>
          <Kicker>Online Edition</Kicker>
        </div>

        <div className="py-6 text-center lg:py-8">
          <Link to="/" className="inline-block focus-visible:outline-offset-4" aria-label="Upily — front page">
            <span className="block font-serif font-black uppercase leading-[0.9] tracking-tighter text-6xl sm:text-8xl lg:text-9xl">
              Upily
            </span>
          </Link>
          <p className="mt-3 font-body italic text-neutral-600 text-sm sm:text-base">
            “All the news that’s fit to explain.”
          </p>
        </div>
      </div>
    </header>
  )
}

function SectionNav() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const search = (q) => navigate(`/search?q=${encodeURIComponent(q)}`)
  useEffect(() => setOpen(false), [pathname])

  const link = ({ isActive }) => cn(
    'flex min-h-[44px] items-center px-4 font-sans text-xs font-semibold uppercase tracking-widest transition-colors duration-200',
    isActive ? 'bg-ink text-paper' : 'text-ink hover:text-accent',
  )

  return (
    <nav aria-label="Sections" className="sticky top-0 z-40 border-b-4 border-ink bg-paper">
      <div className="mx-auto flex max-w-page items-stretch justify-between px-4">
        <ul className="hidden md:flex">
          {NAV.map(({ to, label }) => (
            <li key={to} className="border-r border-ink first:border-l">
              <NavLink to={to} end={to === '/'} className={link}>{label}</NavLink>
            </li>
          ))}
        </ul>

        <Link to="/" className="flex items-center font-serif text-xl font-black uppercase tracking-tighter md:hidden">
          Upily
        </Link>

        <button
          type="button"
          className="flex h-11 w-11 items-center justify-center md:hidden"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen(v => !v)}
        >
          {open ? <X className="h-6 w-6" strokeWidth={1.5} /> : <Menu className="h-6 w-6" strokeWidth={1.5} />}
        </button>

        <div className="hidden items-center lg:flex">
          <SearchForm compact onSearch={search} />
        </div>
        <Link to="/search" aria-label="Search" className="hidden h-11 w-11 items-center justify-center hover:text-accent md:flex lg:hidden">
          <Search className="h-5 w-5" strokeWidth={1.5} />
        </Link>
      </div>

      {open && (
        <div id="mobile-menu" className="border-t border-ink md:hidden">
        <div className="border-b border-ink px-4 py-3">
          <SearchForm onSearch={search} />
        </div>
        <ul>
          {NAV.map(({ to, label }) => (
            <li key={to} className="border-b border-ink last:border-b-0">
              <NavLink to={to} end={to === '/'} className={link}>{label}</NavLink>
            </li>
          ))}
        </ul>
        </div>
      )}
    </nav>
  )
}

function Footer() {
  const { vol } = editionNumber()
  const health = useHealth()
  return (
    <footer className="mt-16 border-t-4 border-ink">
      <div className="mx-auto grid max-w-page grid-cols-1 px-4 md:grid-cols-4">
        <div className="border-b border-ink py-8 md:col-span-2 md:border-b-0 md:border-r md:pr-8">
          <p className="font-serif text-4xl font-black uppercase tracking-tighter">Upily</p>
          <p className="mt-3 max-w-md font-body text-sm leading-relaxed text-neutral-600">
            Upily gathers the day’s reporting from trusted newsrooms, ranks what matters,
            and explains it in plain language. Always read the original source.
          </p>
        </div>
        <div className="border-b border-ink py-8 md:border-b-0 md:border-r md:px-8">
          <Kicker className="block mb-3 text-ink">Sections</Kicker>
          <ul className="space-y-2 font-sans text-sm">
            {NAV.map(({ to, label }) => (
              <li key={to}><Link to={to} className="hover:text-accent">{label}</Link></li>
            ))}
          </ul>
        </div>
        <div className="py-8 md:pl-8">
          <Kicker className="block mb-3 text-ink">The press room</Kicker>
          <ul className="space-y-2 font-mono text-xs text-neutral-600">
            <li>Status: {health.loaded ? (health.status === 'ok' ? 'On the presses' : 'Delayed') : '…'}</li>
            <li>AI desk: {health.features.ai_analysis ? 'Staffed' : 'Unstaffed'}</li>
            <li>Updates every {health.refresh_interval_hours ?? 4} hours</li>
          </ul>
        </div>
      </div>
      <div className="border-t border-ink">
        <div className="mx-auto flex max-w-page flex-wrap justify-between gap-2 px-4 py-3">
          <Kicker>Edition: Vol {vol}.0 | Printed on the Internet</Kicker>
          <Kicker>AI analysis may contain errors — verify with the source</Kicker>
        </div>
      </div>
    </footer>
  )
}

export default function Layout({ children }) {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-ink focus:px-4 focus:py-2 focus:text-paper">
        Skip to content
      </a>
      <Masthead />
      <SectionNav />
      <Ticker />
      <main id="main" className="mx-auto w-full max-w-page flex-1 px-4 pt-8">
        {children}
      </main>
      <Footer />
    </div>
  )
}
