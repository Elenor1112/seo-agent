'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PlayCircle, RefreshCw, Clock, TrendingUp, AlertTriangle, CheckCircle } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from 'recharts';

import SpeedScoreCard from '@/components/speed/SpeedScoreCard';
import CoreWebVitalsChart from '@/components/speed/CoreWebVitalsChart';
import SpeedIssuesTable from '@/components/speed/SpeedIssuesTable';

interface SpeedAudit {
  id: string;
  page_id: string | null;
  page_url: string | null;
  performance_score: number;
  seo_score: number;
  accessibility_score: number;
  best_practices_score: number;
  lcp: number;
  cls: number;
  inp: number;
  ttfb: number;
  total_blocking_time: number;
  recommendations: Array<{
    id: string;
    title: string;
    description: string;
    priority: 'high' | 'medium' | 'low';
    score: number;
  }>;
  created_at: string;
}

interface AverageMetrics {
  performance_score: number;
  seo_score: number;
  accessibility_score: number;
  best_practices_score: number;
  lcp: number;
  cls: number;
  inp: number;
  ttfb: number;
  total_blocking_time: number;
}

export default function SpeedAuditPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selectedStrategy, setSelectedStrategy] = useState<'desktop' | 'mobile'>('desktop');

  // Get project ID from URL or use mock
  const projectId = 'mock-project-id';

  // Fetch speed audits
  const { data: auditsData, isLoading: isLoadingAudits } = useQuery({
    queryKey: ['speed-audits', projectId],
    queryFn: async () => {
      const response = await fetch(`/api/v1/speed/projects/${projectId}`);
      if (!response.ok) throw new Error('Failed to fetch speed audits');
      return response.json();
    },
  });

  // Fetch speed history
  const { data: historyData } = useQuery({
    queryKey: ['speed-history', projectId],
    queryFn: async () => {
      const response = await fetch(`/api/v1/speed/projects/${projectId}/history?days=30`);
      if (!response.ok) throw new Error('Failed to fetch speed history');
      return response.json();
    },
  });

  // Run speed audit mutation
  const runAuditMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/v1/speed/projects/${projectId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy: selectedStrategy }),
      });
      if (!response.ok) throw new Error('Failed to run speed audit');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speed-audits', projectId] });
    },
  });

  const audits: SpeedAudit[] = auditsData?.audits || [];
  const averageMetrics: AverageMetrics | null = auditsData?.average_metrics || null;
  const history = historyData?.history || [];

  const latestAudit = audits[0];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Speed Audit</h1>
          <p className="text-gray-500 mt-1">Monitor and optimize your website performance</p>
        </div>
        <div className="flex items-center gap-4">
          <select
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value as 'desktop' | 'mobile')}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="desktop">Desktop</option>
            <option value="mobile">Mobile</option>
          </select>
          <button
            onClick={() => runAuditMutation.mutate()}
            disabled={runAuditMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {runAuditMutation.isPending ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <PlayCircle className="w-4 h-4" />
            )}
            {runAuditMutation.isPending ? 'Running...' : 'Run Audit'}
          </button>
        </div>
      </div>

      {/* Loading State */}
      {isLoadingAudits && (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600" />
          <span className="ml-3 text-gray-600">Loading speed data...</span>
        </div>
      )}

      {!isLoadingAudits && (
        <>
          {/* Summary Cards */}
          {averageMetrics && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <SpeedScoreCard
                title="Performance"
                score={averageMetrics.performance_score}
                icon={TrendingUp}
              />
              <SpeedScoreCard
                title="SEO"
                score={averageMetrics.seo_score}
                icon={CheckCircle}
              />
              <SpeedScoreCard
                title="Accessibility"
                score={averageMetrics.accessibility_score}
                icon={AlertTriangle}
              />
              <SpeedScoreCard
                title="Best Practices"
                score={averageMetrics.best_practices_score}
                icon={CheckCircle}
              />
            </div>
          )}

          {/* Core Web Vitals */}
          {latestAudit && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Core Web Vitals</h2>
              <CoreWebVitalsChart audit={latestAudit} />
            </div>
          )}

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Category Scores Chart */}
            {averageMetrics && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Category Scores</h2>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={[
                        { name: 'Performance', score: averageMetrics.performance_score },
                        { name: 'SEO', score: averageMetrics.seo_score },
                        { name: 'Accessibility', score: averageMetrics.accessibility_score },
                        { name: 'Best Practices', score: averageMetrics.best_practices_score },
                      ]}
                      layout="vertical"
                      margin={{ left: 20 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" domain={[0, 100]} />
                      <YAxis type="category" dataKey="name" width={120} />
                      <Tooltip formatter={(value: number) => [`${value.toFixed(0)}`, 'Score']} />
                      <Bar dataKey="score" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* History Chart */}
            {history.length > 0 && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Performance Trend</h2>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={history}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tickFormatter={(date) => new Date(date).toLocaleDateString()} />
                      <YAxis domain={[0, 100]} />
                      <Tooltip
                        labelFormatter={(label) => new Date(label).toLocaleDateString()}
                        formatter={(value: number) => [`${value.toFixed(0)}`, 'Score']}
                      />
                      <Legend />
                      <Line type="monotone" dataKey="performance_score" stroke="#3b82f6" strokeWidth={2} name="Performance" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>

          {/* Issues Table */}
          {latestAudit?.recommendations && latestAudit.recommendations.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Recommendations</h2>
              <SpeedIssuesTable issues={latestAudit.recommendations} />
            </div>
          )}

          {/* Latest Audits List */}
          {audits.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Audits</h2>
              <div className="space-y-3">
                {audits.slice(0, 5).map((audit) => (
                  <div
                    key={audit.id}
                    className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
                  >
                    <div className="flex-1">
                      <p className="font-medium text-gray-900 truncate">
                        {audit.page_url || 'Project-wide audit'}
                      </p>
                      <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {new Date(audit.created_at).toLocaleDateString()}
                        </span>
                        <span>Performance: {audit.performance_score.toFixed(0)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-3 py-1 rounded-full text-sm font-medium ${
                          audit.performance_score >= 90
                            ? 'bg-green-100 text-green-800'
                            : audit.performance_score >= 70
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {audit.performance_score >= 90 ? 'Good' : audit.performance_score >= 70 ? 'Needs Improvement' : 'Poor'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No Data State */}
          {audits.length === 0 && (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
              <PlayCircle className="w-12 h-12 mx-auto text-gray-400" />
              <h3 className="mt-4 text-lg font-medium text-gray-900">No speed audits yet</h3>
              <p className="mt-2 text-gray-500">Run your first speed audit to see performance metrics</p>
              <button
                onClick={() => runAuditMutation.mutate()}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Run Speed Audit
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
