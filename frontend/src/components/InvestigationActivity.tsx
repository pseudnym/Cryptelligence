import type { Workspace } from '../types';
import { Panel, SectionHeader } from './ui';

const labels: Record<string, string> = {
  CREATED: 'Investigation created', PLANNING: 'Planning the investigation',
  COLLECTING: 'Collecting evidence', ANALYZING: 'Building the assessment',
  EXECUTING_ACTION: 'Running the next step', REANALYZING: 'Reevaluating the case',
  AWAITING_ACTION: 'Ready for your next step', COMPLETE: 'Available collection complete', ERROR: 'Investigation paused',
};
export function InvestigationActivity({ state, busy, resume }: { state: Workspace; busy: boolean; resume: () => Promise<void> }) {
  const active = !['AWAITING_ACTION', 'COMPLETE', 'ERROR'].includes(state.investigation.status);
  const recent = state.events.slice(-3);
  return <Panel className="activity-panel" label="Investigation activity">
    <SectionHeader title={labels[state.investigation.status] || state.investigation.status} detail="Investigation activity · each result is saved before the next step runs">
      <span className="meta">{state.evidence.length} evidence records · {state.claims.length} statements</span>
    </SectionHeader>
    {state.error && <div className="workflow-error" role="alert"><p>{state.error}</p><button className="button secondary" disabled={busy} onClick={() => void resume()}>Retry interrupted step</button></div>}
    {state.plan && <div className="plan-strip" aria-label="Investigation plan">{state.plan.steps.map(step => <div className={'plan-step ' + step.status} key={step.id}><span className="step-symbol" aria-hidden="true">{step.status === 'completed' ? '✓' : step.status === 'running' ? '●' : step.status === 'failed' ? '!' : '○'}</span><div><strong>{step.title}</strong><span className="meta">{step.status === 'completed' ? step.produced_evidence_ids.length + ' evidence records' : step.status}</span></div></div>)}</div>}
    <div className="activity-recent" role="log" aria-label="Recent investigation activity" aria-live="polite">{recent.map(event => <div className="activity-event" key={event.id}><time>{new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time><div><strong>{event.title}</strong><p>{event.description}</p></div></div>)}</div>
    <details className="activity-details"><summary>View plan reasons and full activity history ({state.events.length})</summary>
      {state.plan && <div className="plan-reasons"><h3>Plan for this question</h3><p>{state.plan.objective}</p>{state.plan.steps.map(step => <div key={step.id}><strong>{step.title}</strong><p>{step.reason}</p><p className="meta">{step.description} · {step.tool_or_adapter}</p></div>)}</div>}
      <ol className="full-activity">{state.events.map(event => <li key={event.id}><time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString()}</time><strong>{event.title}</strong><p>{event.description}</p>{event.related_evidence_ids.length > 0 && <small>Evidence: {event.related_evidence_ids.join(', ')}</small>}</li>)}</ol>
    </details>
    {active && !busy && <button className="button secondary" onClick={() => void resume()}>Resume investigation</button>}
  </Panel>;
}
export function RevisionSummary({ state }: { state: Workspace }) {
  const revision = state.revisions.at(-1);
  if (!revision || revision.number < 2) return null;
  const added = state.evidence.filter(e => revision.evidence_added.includes(e.id));
  return <section className="changes revision-summary" role="status" aria-label="Investigation updated">
    <strong>Investigation updated · revision {revision.number}</strong><p>{revision.reason}</p>
    <div className="revision-grid"><div><h3>Evidence added</h3>{added.map(e => <p key={e.id}>+ {e.title} <small>({e.evidence_type.replaceAll('_', ' ')})</small></p>)}</div>
    <div><h3>Assessment changed</h3>{revision.claims_changed.filter(c => !c.before).slice(0, 3).map(c => <p key={c.id}>New statement: {c.after.statement}</p>)}{!revision.claims_changed.length && !revision.explanation_support_changed.length && <p>Current statements and explanation support are unchanged. The new records update collection coverage.</p>}{revision.explanation_support_changed.filter(c => c.before).map(c => <p key={c.id}>{c.after.title}: {c.before?.support_assessment.toLowerCase()} → {c.after.support_assessment.toLowerCase()} support</p>)}{revision.claims_changed.filter(c => c.before && c.before.status !== c.after.status).map(c => <p key={c.id}>{c.after.statement} <small>{c.before?.status.replaceAll('_', ' ')} → {c.after.status.replaceAll('_', ' ')}</small></p>)}</div>
    <div><h3>{revision.unknowns_resolved.length ? 'Resolved questions' : 'Still unknown'}</h3>{(revision.unknowns_resolved.length ? revision.unknowns_resolved : revision.still_unknown.slice(0, 2)).map(text => <p key={text}>{text}</p>)}<h3>New next step</h3><p>{state.actions.find(a => a.id === revision.next_action_after)?.title || 'No remaining executable steps'}</p></div></div>
    <details className="disclosure"><summary>Review complete revision changes</summary><p>Unknowns introduced: {revision.unknowns_introduced.join(' · ') || 'None'}</p><p>Unknowns resolved: {revision.unknowns_resolved.join(' · ') || 'None'}</p><p>Still unknown: {revision.still_unknown.join(' · ') || 'None'}</p><p>Previous next step: {state.actions.find(a => a.id === revision.next_action_before)?.title || 'None'}</p><p>{revision.claims_changed.length} statements and {revision.explanation_support_changed.length} explanation assessments recomputed.</p></details>
  </section>;
}
