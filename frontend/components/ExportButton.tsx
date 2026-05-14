'use client';

import { useState } from 'react';
import { Download, FileJson, FileText, FileCode, FileCheck, FileType } from 'lucide-react';

interface ExportButtonProps {
  contentId: string;
  onExport?: (format: string, url: string) => void;
}

type ExportFormat = 'pdf' | 'docx' | 'md' | 'html' | 'json';

interface FormatOption {
  value: ExportFormat;
  label: string;
  icon: React.ElementType;
  description: string;
}

const formatOptions: FormatOption[] = [
  {
    value: 'pdf',
    label: 'PDF',
    icon: FileText,
    description: 'Print-ready document',
  },
  {
    value: 'docx',
    label: 'Word',
    icon: FileCheck,
    description: 'Microsoft Word format',
  },
  {
    value: 'md',
    label: 'Markdown',
    icon: FileCode,
    description: 'Markdown with frontmatter',
  },
  {
    value: 'html',
    label: 'HTML',
    icon: FileType,
    description: 'Styled HTML document',
  },
  {
    value: 'json',
    label: 'JSON',
    icon: FileJson,
    description: 'Structured data format',
  },
];

export default function ExportButton({ contentId, onExport }: ExportButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async (format: ExportFormat) => {
    setIsExporting(true);
    setIsOpen(false);

    try {
      const response = await fetch(`/api/v1/content/${contentId}/export?format=${format}`);
      
      if (!response.ok) {
        throw new Error('Export failed');
      }

      const result = await response.json();
      
      if (result.success && result.download_url) {
        // Open download URL in new tab
        window.open(result.download_url, '_blank');
        
        if (onExport) {
          onExport(format, result.download_url);
        }
      } else {
        throw new Error(result.error || 'Export failed');
      }
    } catch (error) {
      console.error('Export error:', error);
      alert('Failed to export content. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="relative">
      {/* Export Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isExporting}
        className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
      >
        {isExporting ? (
          <div className="w-4 h-4 border-2 border-gray-400 border-t-blue-600 rounded-full animate-spin" />
        ) : (
          <Download className="w-4 h-4 text-gray-600" />
        )}
        <span className="text-sm font-medium text-gray-700">Export</span>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          
          {/* Menu */}
          <div className="absolute right-0 mt-2 w-72 bg-white rounded-xl shadow-lg border border-gray-200 z-20 overflow-hidden">
            <div className="p-3 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900">Export Format</h3>
              <p className="text-xs text-gray-500 mt-0.5">Choose your preferred format</p>
            </div>
            
            <div className="py-2">
              {formatOptions.map((option) => {
                const Icon = option.icon;
                
                return (
                  <button
                    key={option.value}
                    onClick={() => handleExport(option.value)}
                    className="w-full px-4 py-3 flex items-start gap-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className="p-2 bg-blue-50 rounded-lg">
                      <Icon className="w-4 h-4 text-blue-600" />
                    </div>
                    <div className="flex-1 text-left">
                      <p className="text-sm font-medium text-gray-900">{option.label}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{option.description}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
