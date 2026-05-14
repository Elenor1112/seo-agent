'use client';

import { LucideIcon } from 'lucide-react';

interface SpeedScoreCardProps {
  title: string;
  score: number;
  icon: LucideIcon;
}

export default function SpeedScoreCard({ title, score, icon: Icon }: SpeedScoreCardProps) {
  const getScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-600 bg-green-50 border-green-200';
    if (score >= 70) return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    return 'text-red-600 bg-red-50 border-red-200';
  };

  const getScoreLabel = (score: number) => {
    if (score >= 90) return 'Good';
    if (score >= 70) return 'Needs Improvement';
    return 'Poor';
  };

  return (
    <div className={`p-4 rounded-xl border ${getScoreColor(score)}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium opacity-80">{title}</p>
          <p className="text-2xl font-bold mt-1">{score.toFixed(0)}</p>
          <p className="text-xs mt-1 opacity-70">{getScoreLabel(score)}</p>
        </div>
        <Icon className="w-8 h-8 opacity-50" />
      </div>
    </div>
  );
}
