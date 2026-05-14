'use client'
import { useQuery } from '@tanstack/react-query'
import { projectsApi, analyticsApi } from '@/lib/api'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp, MousePointerClick, Eye, FileText, ArrowUpRight } from 'lucide-react'
import Link from 'next/link'

export default function DashboardPage() {
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  })

  const activeProject = projects[0]

  const { data: summary } = useQuery({
    queryKey: ['summary', activeProject?.id],
    queryFn: () => analyticsApi.summary(activeProject.id),
    enabled: !!activeProject,
  })

  const { data: rankings = [] } = useQuery({
    queryKey: ['rankings', activeProject?.id],
    queryFn: () => analyticsApi.rankings(activeProject.id, 30),
    enabled: !!activeProject,
  })

  const { data: movers = [] } = useQuery({
    queryKey: ['top-movers', activeProject?.id],
    queryFn: () => analyticsApi.topMovers(activeProject.id, 7),
    enabled: !!activeProject,
  })

  if (!activeProject) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-white mb-2">No projects yet</h2>
          <p className="text-gray-400 mb-6">Create your first project to get started</p>
          <Link href="/projects" className="btn-primary">Create Project</Link>
        </div>
      </div>
    )
  }

  const kpis = [
    { label: 'Clicks (30d)', value: summary?.clicks_30d?.toLocaleString() || '—', icon: MousePointerClick, color: 'text-indigo-400' },
    { label: 'Impressions (30d)', value: summary?.impressions_30d?.toLocaleString() || '—', icon: Eye, color: 'text-emerald-400' },
    { label: 'Avg Position', value: summary?.avg_position_30d || '—', icon: TrendingUp, color: 'text-amber-400' },
    { label: 'Projects', value: projects.length, icon: FileText, color: 'text-pink-400' },
  ]

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{activeProject.name}</h1>
          <p className="text-gray-400 text-sm mt-1">{activeProject.domain}</p>
        </div>
        <button
          onClick={() => projectsApi.runAnalysis(activeProject.id)}
          className="btn-primary flex items-center gap-2"
        >
          <ArrowUpRight size={16} />
          Run Analysis
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        {kpis.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="card">
            <div className="flex items-center justify-between mb-3">
              <span className="text-gray-400 text-sm">{label}</span>
              <Icon size={18} className={color} />
            </div>
            <p className="text-2xl font-bold text-white">{value}</p>
          </div>
        ))}
      </div>

      {/* Rankings Chart */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-6">Rankings Trend (30 days)</h2>
        {rankings.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={rankings}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 11 }} tickFormatter={d => d.slice(5)} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} reversed domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#9ca3af' }}
              />
              <Line type="monotone" dataKey="avg_position" stroke="#6366f1" strokeWidth={2} dot={false} name="Avg Position" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-60 flex items-center justify-center text-gray-600 text-sm">
            No ranking data yet — run an analysis to get started
          </div>
        )}
      </div>

      {/* Top Movers */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Top Movers (7 days)</h2>
        {movers.length > 0 ? (
          <div className="space-y-3">
            {movers.slice(0, 8).map((m: any) => (
              <div key={m.keyword_id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                <span className="text-sm text-gray-200">{m.query}</span>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-gray-500">pos {m.latest_position}</span>
                  <span className="text-xs font-medium text-emerald-400">
                    +{m.avg_position_improvement} ↑
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-600 text-sm">No movement data yet</p>
        )}
      </div>
    </div>
  )
}
