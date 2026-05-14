'use client';

import { Gauge, Zap, Move, Clock } from 'lucide-react';

interface CoreWebVitalsChartProps {
  audit: {
    lcp: number;
    cls: number;
    inp: number;
    ttfb: number;
  };
}

interface MetricConfig {
  key: string;
  label: string;
  icon: React.ElementType;
  value: number;
  unit: string;
  target: number;
  lowerIsBetter: boolean;
  description: string;
}

export default function CoreWebVitalsChart({ audit }: CoreWebVitalsChartProps) {
  const metrics: MetricConfig[] = [
    {
      key: 'lcp',
      label: 'LCP',
      icon: Clock,
      value: audit.lcp,
      unit: 's',
      target: 2.5,
      lowerIsBetter: true,
      description: 'Largest Contentful Paint',
    },
    {
      key: 'cls',
      label: 'CLS',
      icon: Move,
      value: audit.cls,
      unit: '',
      target: 0.1,
      lowerIsBetter: true,
      description: 'Cumulative Layout Shift',
    },
    {
      key: 'inp',
      label: 'INP',
      icon: Zap,
      value: audit.inp,
      unit: 'ms',
      target: 200,
      lowerIsBetter: true,
      description: 'Interaction to Next Paint',
    },
    {
      key: 'ttfb',
      label: 'TTFB',
      icon: Gauge,
      value: audit.ttfb,
      unit: 'ms',
      target: 800,
      lowerIsBetter: true,
      description: 'Time to First Byte',
    },
  ];

  const getStatus = (metric: MetricConfig) => {
    const ratio = metric.value / metric.target;
    
    if (ratio <= 1) {
      return { status: 'good', color: 'bg-green-500 text-green-700' };
    } else if (ratio <= 1.5) {
      return { status: 'needs-improvement', color: 'bg-yellow-500 text-yellow-700' };
    } else {
      return { status: 'poor', color: 'bg-red-500 text-red-700' };
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((metric) => {
        const { status, color } = getStatus(metric);
        const Icon = metric.icon;
        
        return (
          <div
            key={metric.key}
            className="p-4 bg-gray-50 rounded-lg border border-gray-200"
          >
            <div className="flex items-center gap-2 mb-2">
              <Icon className="w-4 h-4 text-gray-500" />
              <span className="text-sm font-medium text-gray-700">{metric.label}</span>
            </div>
            
            <div className="mb-2">
              <span className="text-2xl font-bold text-gray-900">
                {metric.value.toFixed(metric.unit === 's' ? 2 : 0)}
              </span>
              <span className="text-sm text-gray-500 ml-1">{metric.unit}</span>
            </div>
            
            <div className="flex items-center gap-2 mb-2">
              <span
                className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}
              >
                {status === 'good' ? 'Good' : status === 'needs-improvement' ? 'Needs Improvement' : 'Poor'}
              </span>
              <span className="text-xs text-gray-500">
                Target: {metric.target}{metric.unit}
              </span>
            </div>
            
            <p className="text-xs text-gray-500">{metric.description}</p>
            
            {/* Progress bar */}
            <div className="mt-3 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  status === 'good' ? 'bg-green-500' : status === 'needs-improvement' ? 'bg-yellow-500' : 'bg-red-500'
                }`}
                style={{ width: `${Math.min(100, (metric.value / metric.target) * 50)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
