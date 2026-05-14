'use client'
import { useQuery } from '@tanstack/react-query'
import { projectsApi, analyticsApi } from '@/lib/api'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar, Legend } from 'recharts'
import { TrendingUp, MousePointerClick, Eye, FileText, ArrowUpRight, Gauge, Award, AlertTriangle } from 'lucide-react'
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

  // Fetch SEO score
  const { data: scoreData } = useQuery({
    queryKey: ['seo-score', activeProject?.id],
    queryFn: async () => {
      const response = await fetch(`/api/v1/ratings/projects/${activeProject.id}/score`)
      if (!response.ok) throw new Error('Failed to fetch score')
      return response.json()
    },
    enabled: !!activeProject,
  })

  // Fetch speed metrics
  const { data: speedData } = useQuery({
    queryKey: ['speed-metrics', activeProject?.id],
    queryFn: async () => {
      const response = await fetch(`/api/v1/speed/projects/${activeProject.id}`)
      if (!response.ok) throw new Error('Failed to fetch speed')
      return response.json()
    },
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

  const overallScore = scoreData?.success ? scoreData.score : null
  const avgSpeed = speedData?.success ? speedData.average_metrics : null

  const categoryScores = overallScore?.category_scores ? [
    { name: 'Technical', score: overallScore.category_scores.technical },
    { name: 'Speed', score: overallScore.category_scores.speed },
    { name: 'Content', score: overallScore.category_scores.content },
    { name: 'Keywords', score: overallScore.category_scores.keyword },
    { name: 'Schema', score: overallScore.category_scores.schema },
    { name: 'Backlinks', score: overallScore.category_scores.backlink },
  ] : []

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

      {/* SEO Score & Speed Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Overall SEO Score */}
        {overallScore && (
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <Award size={16} className="text-indigo-400" />
                Overall SEO Score
              </h2>
              <span className={`px-3 py-1 rounded-full text-lg font-bold ${
                overallScore.grade === 'A' ? 'bg-green-900 text-green-400' :
                overallScore.grade === 'B' ? 'bg-emerald-900 text-emerald-400' :
                overallScore.grade === 'C' ? 'bg-yellow-900 text-yellow-400' :
                overallScore.grade === 'D' ? 'bg-orange-900 text-orange-400' :
                'bg-red-900 text-red-400'
              }`}>
                Grade: {overallScore.grade}
              </span>
            </div>
            
            <div className="flex items-center gap-6">
              <div className="relative w-32 h-32">
                <svg className="w-32 h-32 transform -rotate-90">
                  <circle
                    cx="64"
                    cy="64"
                    r="56"
                    stroke="#374151"
                    strokeWidth="16"
                    fill="none"
                  />
                  <circle
                    cx="64"
                    cy="64"
                    r="56"
                    stroke={overallScore.overall_score >= 90 ? '#22c55e' : overallScore.overall_score >= 70 ? '#eab308' : '#ef4444'}
                    strokeWidth="16"
                    fill="none"
                    strokeDasharray={`${(overallScore.overall_score / 100) * 352} 352`}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-3xl font-bold text-white">{overallScore.overall_score.toFixed(0)}</span>
                </div>
              </div>
              
              <div className="flex-1 space-y-2">
                {categoryScores.slice(0, 4).map((cat) => (
                  <div key={cat.name} className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">{cat.name}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 rounded-full"
                          style={{ width: `${cat.score}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-300 w-8 text-right">{cat.score.toFixed(0)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {overallScore.recommendations && overallScore.recommendations.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-700">
                <h3 className="text-xs font-semibold text-gray-400 mb-2 flex items-center gap-1">
                  <AlertTriangle size={12} />
                  Top Recommendations
                </h3>
                <ul className="space-y-1">
                  {overallScore.recommendations.slice(0, 3).map((rec: any, i: number) => (
                    <li key={i} className="text-xs text-gray-300 flex items-start gap-2">
                      <span className="text-indigo-400 mt-0.5">•</span>
                      {rec.title}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Speed Summary */}
        {avgSpeed && (
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <Gauge size={16} className="text-blue-400" />
                Performance Summary
              </h2>
              <Link href="/speed" className="text-xs text-indigo-400 hover:text-indigo-300">
                View Details →
              </Link>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-gray-800 rounded-lg">
                <p className="text-xs text-gray-400 mb-1">Performance</p>
                <p className={`text-2xl font-bold ${
                  avgSpeed.performance_score >= 90 ? 'text-green-400' :
                  avgSpeed.performance_score >= 70 ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {avgSpeed.performance_score.toFixed(0)}
                </p>
              </div>
              <div className="p-3 bg-gray-800 rounded-lg">
                <p className="text-xs text-gray-400 mb-1">LCP</p>
                <p className={`text-2xl font-bold ${
                  avgSpeed.lcp <= 2.5 ? 'text-green-400' :
                  avgSpeed.lcp <= 4 ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {avgSpeed.lcp.toFixed(2)}s
                </p>
              </div>
              <div className="p-3 bg-gray-800 rounded-lg">
                <p className="text-xs text-gray-400 mb-1">CLS</p>
                <p className={`text-2xl font-bold ${
                  avgSpeed.cls <= 0.1 ? 'text-green-400' :
                  avgSpeed.cls <= 0.25 ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {avgSpeed.cls.toFixed(3)}
                </p>
              </div>
              <div className="p-3 bg-gray-800 rounded-lg">
                <p className="text-xs text-gray-400 mb-1">INP</p>
                <p className={`text-2xl font-bold ${
                  avgSpeed.inp <= 0.2 ? 'text-green-400' :
                  avgSpeed.inp <= 0.5 ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {(avgSpeed.inp * 1000).toFixed(0)}ms
                </p>
              </div>
            </div>
          </div>
        )}
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

      {/* Category Scores Bar Chart */}
      {categoryScores.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-6">SEO Category Breakdown</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={categoryScores}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(value: number) => [`${value.toFixed(0)}`, 'Score']}
              />
              <Bar dataKey="score" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

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
