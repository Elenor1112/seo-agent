'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, authApi, wordpressApi } from '@/lib/api'
import { useState } from 'react'
import { Globe, Plus, CheckCircle, XCircle, ExternalLink } from 'lucide-react'
import clsx from 'clsx'

export default function ProjectsPage() {
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [error, setError] = useState('')
  const [analysisError, setAnalysisError] = useState<{projectId: string, message: string} | null>(null)
  const [form, setForm] = useState({ name: '', domain: '', base_url: '', brand_voice: '', target_audience: '' })

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => projectsApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      setShowNew(false)
      setForm({ name: '', domain: '', base_url: '', brand_voice: '', target_audience: '' })
      setError('')
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || err?.message || 'Failed to create project'
      setError(message)
      console.error('Create project error:', err)
    },
  })

  const analysisMutation = useMutation({
    mutationFn: (projectId: string) => projectsApi.runAnalysis(projectId),
    onSuccess: () => {
      setAnalysisError(null)
    },
    onError: (err: any, projectId: string) => {
      const message = err?.response?.data?.detail || err?.message || 'Failed to run analysis'
      setAnalysisError({ projectId, message })
      console.error('Run analysis error:', err)
    },
  })

  const connectGSC = async (projectId: string) => {
    const { oauth_url } = await authApi.gscConnect(projectId)
    window.open(oauth_url, '_blank')
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Projects</h1>
        <button onClick={() => setShowNew(true)} className="btn-primary flex items-center gap-2">
          <Plus size={16} /> New Project
        </button>
      </div>

      {/* New project form */}
      {showNew && (
        <div className="card space-y-4">
          <h2 className="text-sm font-semibold text-white">New Project</h2>
          {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-sm text-red-200">{error}</div>}
          <div className="grid grid-cols-2 gap-4">
            {[
              { key: 'name', label: 'Project Name', placeholder: 'My Website' },
              { key: 'domain', label: 'Domain', placeholder: 'example.com' },
              { key: 'base_url', label: 'Base URL', placeholder: 'https://example.com' },
              { key: 'brand_voice', label: 'Brand Voice', placeholder: 'Professional, helpful, clear' },
              { key: 'target_audience', label: 'Target Audience', placeholder: 'e.g., Developers, Marketers' },
            ].map(({ key, label, placeholder }) => (
              <div key={key}>
                <label className="block text-xs text-gray-400 mb-1">{label}</label>
                <input
                  type="text"
                  value={(form as any)[key]}
                  onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                  placeholder={placeholder}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500"
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={() => createMutation.mutate()} disabled={createMutation.isPending} className="btn-primary disabled:opacity-50">
              {createMutation.isPending ? 'Creating...' : 'Create Project'}
            </button>
            <button onClick={() => { setShowNew(false); setError(''); }} className="btn-secondary">Cancel</button>
          </div>
        </div>
      )}

      {/* Projects grid */}
      <div className="grid grid-cols-1 gap-4">
        {isLoading ? (
          <div className="text-gray-500">Loading...</div>
        ) : projects.map((p: any) => (
          <div key={p.id} className="card flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-indigo-900/50 border border-indigo-700/30 flex items-center justify-center">
                <Globe size={18} className="text-indigo-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">{p.name}</h3>
                <p className="text-xs text-gray-500">{p.domain}</p>
              </div>
            </div>

            <div className="flex items-center gap-6">
              {/* GSC status */}
              <div className="flex items-center gap-1.5 text-xs">
                {p.has_gsc ? (
                  <><CheckCircle size={14} className="text-emerald-400" /><span className="text-emerald-400">GSC</span></>
                ) : (
                  <button onClick={() => connectGSC(p.id)} className="flex items-center gap-1 text-gray-500 hover:text-indigo-400 transition-colors">
                    <XCircle size={14} /><span>Connect GSC</span>
                  </button>
                )}
              </div>

              {/* WP status */}
              <div className="flex items-center gap-1.5 text-xs">
                {p.has_wordpress ? (
                  <><CheckCircle size={14} className="text-emerald-400" /><span className="text-emerald-400">WordPress</span></>
                ) : (
                  <span className="text-gray-600 flex items-center gap-1"><XCircle size={14} /> WordPress</span>
                )}
              </div>

              {/* Actions */}
              <button
                onClick={() => analysisMutation.mutate(p.id)}
                disabled={analysisMutation.isPending}
                className="btn-secondary text-xs disabled:opacity-50"
              >
                {analysisMutation.isPending && analysisMutation.variables === p.id ? 'Running...' : 'Run Analysis'}
              </button>
              {analysisError !== null && analysisError.projectId === p.id && (
                <div className="text-xs text-red-400" title={analysisError.message}>
                 Error: {analysisError.message.substring(0, 20)}...
                </div>
              )}
          
              <a href={p.base_url} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} className="text-gray-600 hover:text-gray-300 transition-colors" />
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
