import type { Workspace } from '../types';
import { ClaimRow, Panel, SectionHeader } from './ui';

export function GeminiAssessment({ state, onClaim, pause }: { state: Workspace; onClaim: (id: string) => void; pause: () => Promise<void> }) {
  if (state.fixture) return null;
  if (state.reasoning_mode !== 'gemini') return <p className="meta">Reasoning: deterministic. To use Gemini, configure GEMINI_API_KEY on the backend, restart it, and start a new LIVE investigation.</p>;
  const active = !['AWAITING_ACTION', 'COMPLETE', 'ERROR'].includes(state.investigation.status);
  const usage = state.reasoning_usage.at(-1);
  return <Panel label="Gemini investigation reasoning" className="activity-panel gemini-panel">
    <SectionHeader title="Gemini investigation reasoning" detail="Gemini proposes plans and assessments. The backend validates evidence references, executes tools and ranks actions." />
    <p>{state.auto_steps} / {state.max_auto_steps} collection steps in this run. {state.automation_paused ? 'Paused by analyst.' : active ? 'Bounded automatic collection is active.' : 'Control is with the analyst.'}</p>
    {active && !state.automation_paused && <button className="button secondary" onClick={() => void pause()}>Pause automatic collection</button>}
    <p className="meta">A running request can finish before pause takes effect. Executing a next action starts a new bounded run.</p>
    <details className="disclosure"><summary>Why this assessment?</summary>
      <p>These statements underpin the summary. Open one to inspect its evidence IDs, sources, contradictions and limitations.</p>
      {state.assessment_claim_ids.map(id => state.claims.find(c => c.id === id)).filter(c => !!c).map(c => <ClaimRow key={c.id} claim={c} onSelect={onClaim} />)}
      {state.important_unknown && <><h3>Most important unknown</h3><p>{state.important_unknown.question}</p><p>{state.important_unknown.why_it_matters}</p><p>Could be resolved by: {state.important_unknown.evidence_that_could_resolve_it}</p><p>Affected explanations: {state.important_unknown.related_hypothesis_ids.map(id => state.hypotheses.find(h => h.id === id)?.title).filter(Boolean).join('; ') || 'No supported explanation yet'}</p></>}
      <p className="meta">Model output is an assessment, not source evidence. Only concise evidence-based explanations are shown.</p>
    </details>
    {usage && <p className="meta">Last reasoning call: {usage.model}; reported tokens: {usage.totalTokenCount ?? 'unavailable'}.</p>}
  </Panel>;
}
