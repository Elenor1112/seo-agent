'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contentApi, projectsApi } from '@/lib/api'
import { CheckCircle, XCircle, Send, Eye, FileText } from 'lucide-react'
import { useState } from 'react'
import clsx from 'clsx'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-700 text-gray-300',
  review: 'bg-amber-900/50 text-amber-400',
  approved: 'bg-emerald-900/50 text-emerald-400',
  published: 'bg-indigo-900/50 text-indigo-400',
  rejected: 'bg-red-900/50 text-red-400',
}

export default function ContentPage() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('draft')

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list })
  const project = projects[0]

  const { data: versions = [], isLoading } = useQuery({
    queryKey: ['content', project?.id, statusFilter],
    queryFn: () => contentApi.list(project!.id, { status: statusFilter }),
    enabled: !!project,
  })

  const { data: selected } = useQuery({
    queryKey: ['content-version', selectedId],
    queryFn: () => contentApi.get(selectedId!),
    enabled: !!selectedId,
  })

  const approveMutation = useMutation({
    mutationFn: (id: string) => contentApi.approve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['content'] }),
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => contentApi.reject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['content'] }),
  })

  const publishMutation = useMutation({
    mutationFn: (id: string) => contentApi.publish(id, 'draft'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['content'] }),
  })

  if (!project) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">No project found. Create one to get started.</div>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* List panel */}
      <div className="w-96 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <h1 className="text-lg font-semibold text-white mb-3">Content Queue</h1>
          <div className="flex gap-2 flex-wrap">
            {['draft', 'review', 'approved', 'published'].map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={clsx(
                  'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                  statusFilter === s ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
                )}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 text-gray-500 text-sm">Loading...</div>
          ) : versions.length === 0 ? (
            <div className="p-6 text-center text-gray-500 text-sm">
              <FileText size={32} className="mx-auto mb-2 opacity-30" />
              No content in {statusFilter}
            </div>
          ) : (
            versions.map((v: any) => (
              <button
                key={v.id}
                onClick={() => setSelectedId(v.id)}
                className={clsx(
                  'w-full text-left px-4 py-4 border-b border-gray-800 hover:bg-gray-800/50 transition-colors',
                  selectedId === v.id && 'bg-gray-800/70'
                )}
              >
                <p className="text-sm font-medium text-white truncate">{v.title || v.target_keyword}</p>
                <p className="text-xs text-gray-500 mt-1">{v.target_keyword}</p>
                <div className="flex items-center gap-2 mt-2">
                  <span className={clsx('badge', STATUS_COLORS[v.status])}>{v.status}</span>
                  {v.word_count && (
                    <span className="text-xs text-gray-600">{v.word_count.toLocaleString()} words</span>
                  )}
                  {v.semantic_score && (
                    <span className="text-xs text-indigo-400">{v.semantic_score}% coverage</span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-y-auto">
        {selected ? (
          <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">{selected.title}</h2>
                <p className="text-gray-400 text-sm mt-1">/{selected.slug}</p>
              </div>
              <div className="flex items-center gap-2">
                {selected.status === 'draft' || selected.status === 'review' ? (
                  <>
                    <button
                      onClick={() => rejectMutation.mutate(selected.id)}
                      className="btn-secondary flex items-center gap-1"
                    >
                      <XCircle size={14} /> Reject
                    </button>
                    <button
                      onClick={() => approveMutation.mutate(selected.id)}
                      className="btn-primary flex items-center gap-1"
                    >
                      <CheckCircle size={14} /> Approve
                    </button>
                  </>
                ) : selected.status === 'approved' ? (
                  <button
                    onClick={() => publishMutation.mutate(selected.id)}
                    className="btn-primary flex items-center gap-1"
                  >
                    <Send size={14} /> Send to WordPress
                  </button>
                ) : null}
              </div>
            </div>

            {/* Meta */}
            <div className="grid grid-cols-3 gap-4">
              <div className="card">
                <p className="text-xs text-gray-500">Target Keyword</p>
                <p className="text-sm font-medium text-white mt-1">{selected.target_keyword}</p>
              </div>
              <div className="card">
                <p className="text-xs text-gray-500">Semantic Coverage</p>
                <p className="text-sm font-medium text-white mt-1">{selected.semantic_score ?? '—'}%</p>
              </div>
              <div className="card">
                <p className="text-xs text-gray-500">Word Count</p>
                <p className="text-sm font-medium text-white mt-1">{selected.word_count?.toLocaleString() ?? '—'}</p>
              </div>
            </div>

            {/* Meta description */}
            {selected.meta_description && (
              <div className="card">
                <p className="text-xs text-gray-500 mb-1">Meta Description</p>
                <p className="text-sm text-gray-300">{selected.meta_description}</p>
              </div>
            )}

            {/* Content preview */}
            {selected.content?.sections && (
              <div className="card space-y-4">
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Content Preview</p>
                {selected.content.sections.slice(0, 4).map((section: any, i: number) => (
                  <div key={i}>
                    <h3 className="text-sm font-semibold text-indigo-300 mb-1">{section.heading}</h3>
                    <p className="text-sm text-gray-400 leading-relaxed line-clamp-3">{section.content}</p>
                  </div>
                ))}
                {selected.content.sections.length > 4 && (
                  <p className="text-xs text-gray-600">+{selected.content.sections.length - 4} more sections</p>
                )}
              </div>
            )}

            {/* Edit-set (optimizer diffs) */}
            {selected.content?.edit_set?.edits && (
              <div className="card space-y-3">
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Optimization Edit-Set</p>
                <p className="text-sm text-gray-300">{selected.content.edit_set.summary}</p>
                {selected.content.edit_set.edits.map((edit: any, i: number) => (
                  <div key={i} className="border-l-2 border-indigo-600/40 pl-3">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={clsx('badge', edit.priority === 'high' ? 'bg-red-900/50 text-red-400' : 'bg-gray-700 text-gray-400')}>
                        {edit.priority}
                      </span>
                      <span className="text-xs font-mono text-indigo-400">{edit.edit_type}</span>
                    </div>
                    <p className="text-sm text-gray-300">{edit.instruction}</p>
                    <p className="text-xs text-gray-500 mt-1">{edit.rationale}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-600">
              <Eye size={40} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Select a content version to review</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}