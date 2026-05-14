'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { BarChart2, Globe, FileText, Search, Settings, Zap, Activity } from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { href: '/', label: 'Dashboard', icon: BarChart2 },
  { href: '/projects', label: 'Projects', icon: Globe },
  { href: '/keywords', label: 'Keywords', icon: Search },
  { href: '/content', label: 'Content', icon: FileText },
  { href: '/analytics', label: 'Analytics', icon: Activity },
  { href: '/jobs', label: 'Jobs', icon: Zap },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-60 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
            <Zap size={16} className="text-white" />
          </div>
          <span className="font-semibold text-white text-sm">SEO Agent</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/' && pathname.startsWith(href))
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                active
                  ? 'bg-indigo-600/20 text-indigo-400 font-medium'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-gray-800">
        <p className="text-xs text-gray-600">v1.0.0 · AI SEO Agent</p>
      </div>
    </aside>
  )
}
