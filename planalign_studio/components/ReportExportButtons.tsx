import React from 'react';
import { FileText, Loader2, Presentation } from 'lucide-react';

export type ReportExportFormat = 'pdf' | 'pptx';

const OPTIONS = [
  { format: 'pdf', label: 'PDF', Icon: FileText },
  { format: 'pptx', label: 'PowerPoint', Icon: Presentation },
] as const satisfies ReadonlyArray<{
  format: ReportExportFormat;
  label: string;
  Icon: typeof FileText;
}>;

interface ReportExportButtonsProps {
  onExport: (format: ReportExportFormat) => void;
  /** Format currently downloading, if any. */
  busy: ReportExportFormat | null;
  disabled?: boolean;
  className?: string;
}

export default function ReportExportButtons({
  onExport, busy, disabled = false, className = '',
}: ReportExportButtonsProps) {
  return (
    <div role="group" aria-label="Report" className={`flex items-center gap-2 ${className}`}>
      <span className="text-[10px] font-bold text-ink-subtle uppercase">Report</span>
      {OPTIONS.map(({ format, label, Icon }) => (
        <button
          key={format}
          type="button"
          onClick={() => onExport(format)}
          disabled={disabled || busy !== null}
          aria-label={`Export report as ${label}`}
          title={`Download the report as ${label}`}
          className="flex-1 px-3 py-2 bg-surface-raised border border-border-strong rounded-lg text-xs font-bold text-ink-muted hover:bg-surface-subtle flex items-center justify-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy === format
            ? <Loader2 size={14} className="mr-2 animate-spin" />
            : <Icon size={14} className="mr-2" />}
          {label}
        </button>
      ))}
    </div>
  );
}
