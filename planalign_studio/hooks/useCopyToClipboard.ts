import { useState, useCallback } from 'react';

export interface UseCopyToClipboardReturn {
  copy: (text: string) => Promise<boolean>;
  copied: boolean;
  error: string | null;
}

function copyWithLegacyCommand(text: string): boolean {
  const textarea = document.createElement('textarea');
  const activeElement = document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null;

  textarea.value = text;
  textarea.readOnly = true;
  textarea.setAttribute('aria-hidden', 'true');
  Object.assign(textarea.style, {
    position: 'fixed',
    top: '0',
    left: '0',
    width: '1px',
    height: '1px',
    opacity: '0',
    pointerEvents: 'none',
  });

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, text.length);

  try {
    return document.execCommand('copy');
  } finally {
    textarea.remove();
    activeElement?.focus({ preventScroll: true });
  }
}

/**
 * Custom hook for copying text to clipboard with visual feedback.
 * @param resetDelay - Time in ms before copied state resets (default: 2000ms)
 */
export function useCopyToClipboard(resetDelay = 2000): UseCopyToClipboardReturn {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = useCallback(async (text: string): Promise<boolean> => {
    let clipboardError: unknown = null;

    if (window.isSecureContext && navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setError(null);

        setTimeout(() => setCopied(false), resetDelay);
        return true;
      } catch (err) {
        clipboardError = err;
      }
    }

    try {
      if (copyWithLegacyCommand(text)) {
        setCopied(true);
        setError(null);
        setTimeout(() => setCopied(false), resetDelay);
        return true;
      }
    } catch (err) {
      clipboardError ??= err;
    }

    const errorMessage = clipboardError instanceof Error
      ? clipboardError.message
      : 'Clipboard access is unavailable in this browser';
    setError(errorMessage);
    setCopied(false);
    return false;
  }, [resetDelay]);

  return { copy, copied, error };
}

export default useCopyToClipboard;
