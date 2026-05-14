'use client'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi, projectsApi } from '@/lib/api'
import { useState } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import clsx from 'clsx'

const PERIODS = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
]

export default function AnalyticsPage() {
  const [days, setDays] = useState(30)

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list })
  const project = projects[0]

  if (!project) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">No project found. Create one to get started.</div>
      </div>
    )
  }

  const { data: rankings = [] } = useQuery({
    queryKey: ['rankings', project?.id, days],
    queryFn: () => analyticsApi.rankings(project.id, days),
    enabled: !!project,
  })

  const { data: movers = [] } = useQuery({
    queryKey: ['top-movers', project?.id, days],
    queryFn: () => analyticsApi.topMovers(project.id, days),
    enabled: !!project,
  })

  const { data: insights = [] } = useQuery({
    queryKey: ['feedback-insights', project?.id],
    queryFn: () => analyticsApi.feedbackInsights(project.id),
    enabled: !!project,
  })

  const tooltipStyle = {
    contentStyle: { background: '#111827', border: '1px solid #374151', borderRadius: 8 },
    labelStyle: { color: '#9ca3af' },
  }

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Analytics</h1>
        <div className="flex items-center gap-1 bg-gray-900 border border-gray-800 rounded-lg p-1">
          {PERIODS.map(p => (
            <button
              key={p.value}
              onClick={() => setDays(p.value)}
              className={clsx(
                'px-3 py-1 rounded text-xs font-medium transition-colors',
                days === p.value ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Rankings over time */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-6">Average Position</h2>
        {rankings.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={rankings}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#6b7280', fontSize: 11 }}
                tickFormatter={d => d.slice(5)}
              />
              <YAxis
                tick={{ fill: '#6b7280', fontSize: 11 }}
                reversed
                domain={['auto', 'auto']}
                label={{ value: 'Position', angle: -90, position: 'insideLeft', fill: '#6b7280', fontSize: 11 }}
              />
              <Tooltip {...tooltipStyle} />
              <Line
                type="monotone"
                dataKey="avg_position"
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
                name="Avg Position"
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <EmptyChart />
        )}
      </div>

      {/* Clicks + Impressions */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-6">Clicks & Impressions</h2>
        {rankings.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={rankings}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#6b7280', fontSize: 11 }}
                tickFormatter={d => d.slice(5)}
              />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
              <Bar dataKey="total_clicks" fill="#6366f1" name="Clicks" radius={[2, 2, 0, 0]} />
              <Bar dataKey="total_impressions" fill="#1d4ed8" name="Impressions" radius={[2, 2, 0, 0]} opacity={0.6} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <EmptyChart />
        )}
      </div>

      {/* Top Movers + Feedback Insights side by side */}
      <div className="grid grid-cols-2 gap-6">
        {/* Top Movers */}
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">
            Top Rank Movers ({days}d)
          </h2>
          {movers.length > 0 ? (
            <div className="space-y-3">
              {movers.slice(0, 10).map((m: any) => (
                <div key={m.keyword_id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-200 truncate">{m.query}</p>
                    <p className="text-xs text-gray-600 mt-0.5">Position {m.latest_position}</p>
                  </div>
                  <span className="text-sm font-semibold text-emerald-400 ml-4">
                    +{m.avg_position_improvement} ↑
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-600 text-sm">No movement data yet</p>
          )}
        </div>

        {/* Feedback Insights */}
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">
            Feedback Loop Insights
          </h2>
          {insights.length > 0 ? (
            <div className="space-y-3">
              {insights.map((ins: any) => (
                <div key={ins.edit_type} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono text-indigo-300">{ins.edit_type}</p>
                    <p className="text-xs text-gray-600 mt-0.5">
                      {ins.sample_size} samples · {Math.round(ins.success_rate * 100)}% success
                    </p>
                  </div>
                  <span className={clsx(
                    'text-sm font-semibold ml-4',
                    ins.avg_rank_improvement > 0 ? 'text-emerald-400' : 'text-red-400'
                  )}>
                    {ins.avg_rank_improvement > 0 ? '+' : ''}{ins.avg_rank_improvement}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-600 text-sm">
              <p>No feedback signals yet.</p>
              <p className="mt-1 text-xs">Signals appear after content is published and 30-day rank data is collected.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function EmptyChart() {
  return (
    <div className="h-60 flex items-center justify-center text-gray-600 text-sm">
      No data yet — run an analysis to populate charts
    </div>
  )
}
