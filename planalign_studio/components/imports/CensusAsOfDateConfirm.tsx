import React, { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { setCensusAsOfDate } from '../../services/importService';
import CensusAsOfDateField, { isCensusAsOfDate } from './CensusAsOfDateField';

interface Props {
  workspaceId: string;
  fileId: string;
  suggested: string | null | undefined;
  onConfirmed: () => void;
}

/** Confirms the as-of date of a census uploaded as a ready-made file. */
export default function CensusAsOfDateConfirm({ workspaceId, fileId, suggested, onConfirmed }: Props) {
  const [value, setValue] = useState(suggested ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await setCensusAsOfDate(workspaceId, fileId, value);
      onConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the date');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3 text-left max-w-md mx-auto">
      <CensusAsOfDateField value={value} onChange={setValue} disabled={isSaving} />
      {error && <p className="text-sm text-danger-ink">{error}</p>}
      <button
        onClick={handleConfirm}
        disabled={isSaving || !isCensusAsOfDate(value)}
        className="flex items-center gap-2 px-4 py-2 text-sm bg-brand-green text-ink-inverse rounded-lg hover:bg-brand-dark disabled:opacity-50"
      >
        {isSaving && <Loader2 size={14} className="animate-spin" />}
        Confirm date
      </button>
    </div>
  );
}
