'use client'
import { useQuery, useMutation } from '@tanstack/react-query'
import { keywordsApi, projectsApi, projectsApi as pApi } from '@/lib/api'
import { useState } from 'react'
import clsx from 'clsx'
import { TrendingUp, Target, Zap } from 'lucide-react'

const INTENT_COLORS: Record<string, string> = {
  informational: 'bg-blue-900/50 text-blue-400',
  commercial: 'bg-purple-900/50 text-purple-400',
  transactional: 'bg-emerald-900/50 text-emerald-400',
  navigational: 'bg-gray-700 text-gray-400',
}

export default function KeywordsPage() {
  const [gapsOnly, setGapsOnly] = useState(true)
  const [selected, setSelected] = useState<string[]>([])

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list })
  const project = projects[0]

  if (!project) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">No project found. Create one to get started.</div>
      </div>
    )
  }

  const { data: keywords = [], isLoading } = useQuery({
    queryKey: ['keywords', project?.id, gapsOnly],
    queryFn: () => keywordsApi.list(project.id, { gaps_only: gapsOnly, limit: 200 }),
    enabled: !!project,
  })

  const runContent = useMutation({
    mutationFn: () => pApi.runContent(project.id, selected),
    onSuccess: () => {
      alert(`Content generation started for ${selected.length} keywords`)
      setSelected([])
    },
  })

  const toggleSelect = (id: string) =>
    setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Keywords</h1>
          <p className="text-gray-400 text-sm mt-1">{keywords.length} keywords tracked</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={gapsOnly}
              onChange={e => setGapsOnly(e.target.checked)}
              className="rounded"
            />
            Gaps only (pos 8–30)
          </label>
          {selected.length > 0 && (
            <button
              onClick={() => runContent.mutate()}
              className="btn-primary flex items-center gap-2"
            >
              <Zap size={14} />
              Generate Content ({selected.length})
            </button>
          )}
        </div>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left">
              <th className="px-4 py-3 text-gray-500 font-medium w-8">
                <input
                  type="checkbox"
                  onChange={e => setSelected(e.target.checked ? keywords.map((k: any) => k.id) : [])}
                />
              </th>
              <th className="px-4 py-3 text-gray-500 font-medium">Query</th>
              <th className="px-4 py-3 text-gray-500 font-medium">Intent</th>
              <th className="px-4 py-3 text-gray-500 font-medium text-right">Position</th>
              <th className="px-4 py-3 text-gray-500 font-medium text-right">Impressions</th>
              <th className="px-4 py-3 text-gray-500 font-medium text-right">CTR</th>
              <th className="px-4 py-3 text-gray-500 font-medium text-right">Opportunity</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-600">Loading...</td></tr>
            ) : keywords.map((k: any) => (
              <tr
                key={k.id}
                className={clsx(
                  'border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors',
                  selected.includes(k.id) && 'bg-indigo-900/10'
                )}
              >
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={selected.includes(k.id)}
                    onChange={() => toggleSelect(k.id)}
                  />
                </td>
                <td className="px-4 py-3">
                  <p className="text-white font-medium">{k.query}</p>
                  {k.cluster_label && (
                    <p className="text-xs text-gray-600 mt-0.5 truncate max-w-xs">{k.cluster_label}</p>
                  )}
                </td>
                <td className="px-4 py-3">
                  {k.search_intent && (
                    <span className={clsx('badge', INTENT_COLORS[k.search_intent])}>
                      {k.search_intent}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  <span className={clsx(
                    'font-mono text-sm',
                    k.avg_position <= 3 ? 'text-emerald-400' :
                    k.avg_position <= 10 ? 'text-amber-400' : 'text-gray-400'
                  )}>
                    {k.avg_position ? k.avg_position.toFixed(1) : '—'}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-gray-400">
                  {k.impressions.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right text-gray-400">
                  {(k.ctr * 100).toFixed(1)}%
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{ width: `${k.opportunity_score ?? 0}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-400 w-8 text-right">
                      {k.opportunity_score?.toFixed(0) ?? '—'}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
