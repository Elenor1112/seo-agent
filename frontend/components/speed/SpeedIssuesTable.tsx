'use client';

import { AlertTriangle, AlertCircle, Info } from 'lucide-react';

interface Issue {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  score: number;
}

interface SpeedIssuesTableProps {
  issues: Issue[];
}

export default function SpeedIssuesTable({ issues }: SpeedIssuesTableProps) {
  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case 'high':
        return <AlertTriangle className="w-4 h-4 text-red-600" />;
      case 'medium':
        return <AlertCircle className="w-4 h-4 text-yellow-600" />;
      default:
        return <Info className="w-4 h-4 text-blue-600" />;
    }
  };

  const getPriorityLabel = (priority: string) => {
    return priority.charAt(0).toUpperCase() + priority.slice(1);
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'bg-red-100 text-red-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-blue-100 text-blue-800';
    }
  };

  if (issues.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No issues found. Great job!
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-3 px-4 text-sm font-medium text-gray-700">
              Priority
            </th>
            <th className="text-left py-3 px-4 text-sm font-medium text-gray-700">
              Issue
            </th>
            <th className="text-left py-3 px-4 text-sm font-medium text-gray-700">
              Description
            </th>
            <th className="text-right py-3 px-4 text-sm font-medium text-gray-700">
              Score
            </th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue, index) => (
            <tr
              key={issue.id}
              className={`border-b border-gray-100 hover:bg-gray-50 ${
                index % 2 === 0 ? 'bg-white' : 'bg-gray-50'
              }`}
            >
              <td className="py-3 px-4">
                <div className="flex items-center gap-2">
                  {getPriorityIcon(issue.priority)}
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${getPriorityColor(
                      issue.priority
                    )}`}
                  >
                    {getPriorityLabel(issue.priority)}
                  </span>
                </div>
              </td>
              <td className="py-3 px-4">
                <span className="text-sm font-medium text-gray-900">{issue.title}</span>
              </td>
              <td className="py-3 px-4">
                <span className="text-sm text-gray-600 line-clamp-2">
                  {issue.description}
                </span>
              </td>
              <td className="py-3 px-4 text-right">
                <span className="text-sm font-medium text-gray-900">
                  {issue.score.toFixed(0)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
