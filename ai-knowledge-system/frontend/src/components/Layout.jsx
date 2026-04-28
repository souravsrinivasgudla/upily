import { NavLink } from 'react-router-dom'
import { Brain, LayoutDashboard, TrendingUp, MessageSquare } from 'lucide-react'

const NAV = [
  { to: '/',         icon: LayoutDashboard, label: 'Dashboard'  },
  { to: '/trending', icon: TrendingUp,      label: 'Trending'   },
  { to: '/chat',     icon: MessageSquare,   label: 'Ask AI'     },
]

export default function Layout({ children }) {
  return (
    <div className="flex min-h-screen">
      {/* ── Sidebar ── */}
      <aside className="fixed inset-y-0 w-56 bg-gray-900 border-r border-gray-800 flex flex-col py-6 px-4">
        {/* Logo */}
        <div className="flex items-center gap-2 px-2 mb-8">
          <Brain className="w-5 h-5 text-brand-500" />
          <span className="font-bold text-sm text-white leading-tight">
            AI Knowledge<br />System
          </span>
        </div>

        {/* Nav links */}
        <nav className="flex flex-col gap-1 flex-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors
                 ${isActive
                   ? 'bg-brand-600 text-white'
                   : 'text-gray-400 hover:text-white hover:bg-gray-800'}`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* ── Main ── */}
      <main className="ml-56 flex-1 p-8 max-w-5xl">
        {children}
      </main>
    </div>
  )
}
