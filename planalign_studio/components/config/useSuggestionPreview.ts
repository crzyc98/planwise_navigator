import { useEffect, useRef, useState } from 'react';

/** A preview belongs to one uninterrupted input revision, including its scope. */
export function useSuggestionPreview<T>(inputKey: string, scopeKey: string) {
  const revision = useRef({ key: inputKey, scope: scopeKey, version: 0 });
  if (revision.current.key !== inputKey || revision.current.scope !== scopeKey) {
    revision.current = { key: inputKey, scope: scopeKey, version: revision.current.version + 1 };
  }
  const mounted = useRef(true);
  const request = useRef(0);
  const [preview, setPreview] = useState<{ value: T; version: number; scope: string } | null>(null);
  const [pendingVersion, setPendingVersion] = useState<number | null>(null);
  const [failure, setFailure] = useState<{ message: string; version: number } | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; request.current += 1; };
  }, []);

  const calculate = async (calculateValue: () => Promise<T>) => {
    const snapshot = revision.current;
    const id = ++request.current;
    setPendingVersion(snapshot.version);
    setFailure(null);
    setPreview(null);
    try {
      const value = await calculateValue();
      if (mounted.current && id === request.current && snapshot.version === revision.current.version) {
        setPreview({ value, version: snapshot.version, scope: snapshot.scope });
      }
    } catch (cause) {
      if (mounted.current && id === request.current && snapshot.version === revision.current.version) {
        setFailure({ message: cause instanceof Error ? cause.message : 'Unable to calculate suggestions', version: snapshot.version });
      }
    } finally {
      if (mounted.current && id === request.current) setPendingVersion(null);
    }
  };
  const value = preview?.scope === scopeKey ? preview.value : null;
  const stale = !!value && preview?.version !== revision.current.version;
  const pending = pendingVersion === revision.current.version;
  const error = failure?.version === revision.current.version ? failure.message : null;
  const cancel = () => { request.current += 1; setPendingVersion(null); setPreview(null); setFailure(null); };
  const apply = (applyValue: (value: T) => void) => {
    if (!preview || preview.scope !== revision.current.scope || preview.version !== revision.current.version) return;
    applyValue(preview.value);
    cancel();
  };
  return { value, stale, pending, error, calculate, cancel, apply };
}
