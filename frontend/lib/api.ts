import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
})

// ── Projects ───────────────────────────────────────────────────────────────────
export const projectsApi = {
  list: () => api.get('/projects/').then(r => r.data),
  get: (id: string) => api.get(`/projects/${id}`).then(r => r.data),
  create: (data: any) => api.post('/projects/', data).then(r => r.data),
  update: (id: string, data: any) => api.patch(`/projects/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/projects/${id}`),
  runAnalysis: (id: string, config?: any) =>
    api.post(`/projects/${id}/run`, config || {}).then(r => r.data),
  runContent: (id: string, keywordIds: string[]) =>
    api.post(`/projects/${id}/run/content`, keywordIds).then(r => r.data),
  runOptimize: (id: string, pairs: any[]) =>
    api.post(`/projects/${id}/run/optimize`, pairs).then(r => r.data),
}

// ── Tasks ──────────────────────────────────────────────────────────────────────
export const tasksApi = {
  get: (id: string) => api.get(`/tasks/${id}`).then(r => r.data),
  listByProject: (projectId: string) =>
    api.get(`/tasks/project/${projectId}`).then(r => r.data),
}

// ── Keywords ───────────────────────────────────────────────────────────────────
export const keywordsApi = {
  list: (projectId: string, params?: Record<string, any>) =>
    api.get(`/keywords/project/${projectId}`, { params }).then(r => r.data),
  clusters: (projectId: string) =>
    api.get(`/keywords/project/${projectId}/clusters`).then(r => r.data),
}

// ── Content ────────────────────────────────────────────────────────────────────
export const contentApi = {
  list: (projectId: string, params?: Record<string, any>) =>
    api.get(`/content/project/${projectId}`, { params }).then(r => r.data),
  get: (versionId: string) => api.get(`/content/${versionId}`).then(r => r.data),
  approve: (versionId: string, approvedBy?: string) =>
    api.post(`/content/${versionId}/approve`, { approved_by: approvedBy || 'human_editor' }).then(r => r.data),
  reject: (versionId: string) => api.post(`/content/${versionId}/reject`).then(r => r.data),
  publish: (versionId: string, wpStatus = 'draft') =>
    api.post(`/content/${versionId}/publish`, { wp_status: wpStatus }).then(r => r.data),
}

// ── Analytics ──────────────────────────────────────────────────────────────────
export const analyticsApi = {
  rankings: (projectId: string, days = 30) =>
    api.get(`/analytics/project/${projectId}/rankings`, { params: { days } }).then(r => r.data),
  topMovers: (projectId: string, days = 7) =>
    api.get(`/analytics/project/${projectId}/top-movers`, { params: { days } }).then(r => r.data),
  summary: (projectId: string) =>
    api.get(`/analytics/project/${projectId}/summary`).then(r => r.data),
  feedbackInsights: (projectId: string) =>
    api.get(`/analytics/project/${projectId}/feedback-insights`).then(r => r.data),
}

// ── Auth ───────────────────────────────────────────────────────────────────────
export const authApi = {
  gscConnect: (projectId: string) =>
    api.get(`/auth/gsc/connect/${projectId}`).then(r => r.data),
  gscDisconnect: (projectId: string) =>
    api.delete(`/auth/gsc/disconnect/${projectId}`).then(r => r.data),
}

// ── WordPress ──────────────────────────────────────────────────────────────────
export const wordpressApi = {
  testConnection: (projectId: string, creds: any) =>
    api.post(`/wordpress/project/${projectId}/test`, creds).then(r => r.data),
}
