'use client'
import { useQuery } from '@tanstack/react-query'
import { tasksApi, projectsApi } from '@/lib/api'
import { CheckCircle, Clock, AlertCircle, Loader, XCircle } from 'lucide-react'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'

const STATUS_CONFIG: Record<string, { icon: any; color: string; label: string }> = {
  pending: { icon: Clock, color: 'text-gray-400', label: 'Pending' },
  queued: { icon: Clock, color: 'text-blue-400', label: 'Queued' },
  running: { icon: Loader, color: 'text-amber-400', label: 'Running' },
  completed: { icon: CheckCircle, color: 'text-emerald-400', label: 'Completed' },
  failed: { icon: AlertCircle, color: 'text-red-400', label: 'Failed' },
  retrying: { icon: Loader, color: 'text-orange-400', label: 'Retrying' },
  dead: { icon: XCircle, color: 'text-red-600', label: 'Dead' },
}

export default function JobsPage() {
  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list })
  const project = projects[0]

  if (!project) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">No project found. Create one to get started.</div>
      </div>
    )
  }

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['tasks', project?.id],
    queryFn: () => tasksApi.listByProject(project.id),
    enabled: !!project,
    refetchInterval: 5000,  // Poll every 5s for live updates
  })

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Jobs</h1>
        <p className="text-gray-400 text-sm mt-1">Live agent task status · refreshes every 5s</p>
      </div>

      <div className="card p-0 overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-600">Loading...</div>
        ) : tasks.length === 0 ? (
          <div className="p-8 text-center text-gray-600">No jobs yet — run an analysis to start</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left">
                <th className="px-4 py-3 text-gray-500 font-medium">Type</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Status</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Priority</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Started</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Completed</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task: any) => {
                const sc = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending
                const Icon = sc.icon
                return (
                  <tr key={task.id} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs text-indigo-300">{task.task_type}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Icon size={14} className={clsx(sc.color, task.status === 'running' && 'animate-spin')} />
                        <span className={clsx('text-xs font-medium', sc.color)}>{sc.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-400">{task.priority}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {task.started_at ? formatDistanceToNow(new Date(task.started_at), { addSuffix: true }) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {task.completed_at ? formatDistanceToNow(new Date(task.completed_at), { addSuffix: true }) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
