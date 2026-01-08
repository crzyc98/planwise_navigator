import { useState, useCallback } from 'react';

export interface UseCopyToClipboardReturn {
  copy: (text: string) => Promise<boolean>;
  copied: boolean;
  error: string | null;
}

/**
 * Custom hook for copying text to clipboard with visual feedback.
 * @param resetDelay - Time in ms before copied state resets (default: 2000ms)
 */
export function useCopyToClipboard(resetDelay = 2000): UseCopyToClipboardReturn {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = useCallback(async (text: string): Promise<boolean> => {
    // Check if clipboard API is available
    if (!navigator.clipboard) {
      setError('Clipboard access not available');
      setCopied(false);
      return false;
    }

    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setError(null);

      // Reset copied state after delay
      setTimeout(() => setCopied(false), resetDelay);
      return true;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Clipboard access denied';
      setError(errorMessage);
      setCopied(false);
      return false;
    }
  }, [resetDelay]);

  return { copy, copied, error };
}

export default useCopyToClipboard;
