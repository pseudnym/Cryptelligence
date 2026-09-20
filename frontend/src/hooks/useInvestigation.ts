import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import type { Workspace } from '../types';
const settled = new Set(['AWAITING_ACTION', 'COMPLETE', 'ERROR']);

export function useInvestigation() {
  const [caseState, setCaseState] = useState<Workspace | null>(null);
  const [busy, setBusy] = useState(() => new URLSearchParams(window.location.hash.slice(1)).has('case'));
  const [error, setError] = useState('');
  const generation = useRef(0);
  const running = useRef(false);
  async function run(task: () => Promise<Workspace>) {
    if (running.current) return;
    running.current = true;
    const current = ++generation.current;
    setBusy(true); setError('');
    try {
      let result = await task();
      if (current !== generation.current) return;
      setCaseState(result);
      window.history.replaceState({}, '', '#case=' + result.investigation.id);
      // Pace requests so each committed backend operation is readable.
      // The timer never advances state, creates events, or marks a step complete.
      while (!settled.has(result.investigation.status)) {
        await new Promise(resolve => window.setTimeout(resolve, 400));
        if (current !== generation.current) return;
        result = await api.advance(result.investigation.id, result.version);
        if (current !== generation.current) return;
        setCaseState(result);
      }
    } catch (err) {
      if (current === generation.current) setError(err instanceof Error ? err.message : 'Unexpected error. Please retry.');
    } finally {
      if (current === generation.current) { setBusy(false); running.current = false; }
    }
  }
  useEffect(() => {
    const id = new URLSearchParams(window.location.hash.slice(1)).get('case');
    if (id) void run(() => api.get(id));
    return () => { generation.current += 1; running.current = false; };
  }, []);
  return {
    caseState, busy, error,
    create: (seeds: string[], question: string, mode: 'fixture' | 'live') => run(() => api.create(seeds, question, mode)),
    expand: (entityId: string, direction: 'inbound' | 'outbound' | 'inspect') => caseState ? run(() => api.expand(caseState.investigation.id, entityId, direction)) : Promise.resolve(),
    search: (targetId: string | null, query?: string, capability?: string) => caseState ? run(() => api.search(caseState.investigation.id, targetId, query, capability)) : Promise.resolve(),
    addSeed: (address: string) => caseState ? run(() => api.addSeed(caseState.investigation.id, address)) : Promise.resolve(),
    relationship: (source: string, target: string, evidence: string[], statement: string) => caseState ? run(() => api.relationship(caseState.investigation.id, source, target, evidence, statement)) : Promise.resolve(),
    execute: (actionId: string) => caseState ? run(() => api.execute(caseState.investigation.id, actionId)) : Promise.resolve(),
    resume: () => caseState ? run(() => caseState.investigation.status === 'ERROR' ? api.retry(caseState.investigation.id) : api.get(caseState.investigation.id)) : Promise.resolve(),
    pause: async () => {
      if (!caseState) return;
      try { await api.pause(caseState.investigation.id); }
      catch (err) { setError(err instanceof Error ? err.message : "Unable to pause"); }
    },
    reset: () => { generation.current += 1; running.current = false; setBusy(false); setCaseState(null); setError(''); window.history.replaceState({}, '', window.location.pathname); },
  };
}
