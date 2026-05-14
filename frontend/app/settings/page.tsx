'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, authApi, wordpressApi } from '@/lib/api'
import { useState, useEffect } from 'react'
import { CheckCircle, AlertCircle, ExternalLink } from 'lucide-react'

export default function SettingsPage() {
  const qc = useQueryClient()

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list })
  const project = projects[0]

  const [wpForm, setWpForm] = useState({
    wp_base_url: '',
    wp_username: '',
    wp_app_password: '',
  })
  const [wpStatus, setWpStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle')

  const [brandForm, setBrandForm] = useState({
    brand_voice: '',
    target_audience: '',
    gsc_property_url: '',
  })

  // Sync forms with project data when it loads
  useEffect(() => {
    if (project) {
      setWpForm(prev => ({
        ...prev,
        wp_base_url: project.wp_base_url || '',
        wp_username: project.wp_username || '',
      }))
      setBrandForm({
        brand_voice: project.brand_voice || '',
        target_audience: project.target_audience || '',
        gsc_property_url: project.gsc_property_url || '',
      })
    }
  }, [project])

  const updateProject = useMutation({
    mutationFn: (data: any) => projectsApi.update(project.id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  const testWP = async () => {
    setWpStatus('testing')
    try {
      await wordpressApi.testConnection(project.id, wpForm)
      setWpStatus('ok')
      await qc.invalidateQueries({ queryKey: ['projects'] })
    } catch {
      setWpStatus('fail')
    }
  }

  const connectGSC = async () => {
    const { oauth_url } = await authApi.gscConnect(project.id)
    window.open(oauth_url, '_blank')
  }

  const disconnectGSC = useMutation({
    mutationFn: () => authApi.gscDisconnect(project.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  if (!project) return <div className="p-8 text-gray-500">No project found</div>

  return (
    <div className="p-8 max-w-2xl space-y-8">
      <h1 className="text-2xl font-bold text-white">Settings</h1>

      {/* ── Brand & Content ──────────────────────────────────────── */}
      <section className="card space-y-4">
        <h2 className="text-sm font-semibold text-white">Brand & Content</h2>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Brand Voice</label>
          <textarea
            rows={2}
            value={brandForm.brand_voice}
            onChange={e => setBrandForm(f => ({ ...f, brand_voice: e.target.value }))}
            placeholder="Professional, helpful, data-driven…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Target Audience</label>
          <textarea
            rows={2}
            value={brandForm.target_audience}
            onChange={e => setBrandForm(f => ({ ...f, target_audience: e.target.value }))}
            placeholder="Marketing managers at SaaS companies…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>

        <button
          onClick={() => updateProject.mutate(brandForm)}
          className="btn-primary"
        >
          {updateProject.isPending ? 'Saving…' : 'Save'}
        </button>
      </section>

      {/* ── Google Search Console ──────────────────────────────────── */}
      <section className="card space-y-4">
        <h2 className="text-sm font-semibold text-white">Google Search Console</h2>

        {project.has_gsc ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-emerald-400 text-sm">
              <CheckCircle size={16} />
              <span>Connected</span>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">GSC Property URL</label>
              <input
                type="text"
                value={brandForm.gsc_property_url}
                onChange={e => setBrandForm(f => ({ ...f, gsc_property_url: e.target.value }))}
                placeholder="sc-domain:example.com or https://example.com/"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500"
              />
              <p className="text-xs text-gray-600 mt-1">
                Find this in Search Console → Property selector
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => updateProject.mutate({ gsc_property_url: brandForm.gsc_property_url })}
                className="btn-primary"
              >
                Save Property
              </button>
              <button
                onClick={() => disconnectGSC.mutate()}
                className="btn-secondary text-red-400 hover:text-red-300"
              >
                Disconnect
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-400">
              Connect Google Search Console to pull query data, rankings, and CTR.
            </p>
            <button onClick={connectGSC} className="btn-primary flex items-center gap-2">
              <ExternalLink size={14} />
              Connect via Google OAuth
            </button>
          </div>
        )}
      </section>

      {/* ── WordPress ──────────────────────────────────────────────── */}
      <section className="card space-y-4">
        <h2 className="text-sm font-semibold text-white">WordPress</h2>

        {project.has_wordpress && wpStatus !== 'fail' && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm">
            <CheckCircle size={16} />
            <span>Connected to {project.wp_base_url}</span>
          </div>
        )}

        <div className="space-y-3">
          {[
            { key: 'wp_base_url', label: 'WordPress URL', placeholder: 'https://yoursite.com', type: 'text' },
            { key: 'wp_username', label: 'Username', placeholder: 'admin', type: 'text' },
            { key: 'wp_app_password', label: 'Application Password', placeholder: 'xxxx xxxx xxxx xxxx xxxx xxxx', type: 'password' },
          ].map(({ key, label, placeholder, type }) => (
            <div key={key}>
              <label className="block text-xs text-gray-400 mb-1">{label}</label>
              <input
                type={type}
                value={(wpForm as any)[key]}
                onChange={e => setWpForm(f => ({ ...f, [key]: e.target.value }))}
                placeholder={placeholder}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500"
              />
            </div>
          ))}
        </div>

        <p className="text-xs text-gray-600">
          Generate an Application Password in WordPress → Users → Profile → Application Passwords.
        </p>

        <div className="flex items-center gap-3">
          <button
            onClick={testWP}
            disabled={wpStatus === 'testing'}
            className="btn-primary"
          >
            {wpStatus === 'testing' ? 'Testing…' : 'Test & Save Connection'}
          </button>

          {wpStatus === 'ok' && (
            <span className="flex items-center gap-1 text-emerald-400 text-sm">
              <CheckCircle size={14} /> Connected
            </span>
          )}
          {wpStatus === 'fail' && (
            <span className="flex items-center gap-1 text-red-400 text-sm">
              <AlertCircle size={14} /> Authentication failed
            </span>
          )}
        </div>
      </section>
    </div>
  )
}
