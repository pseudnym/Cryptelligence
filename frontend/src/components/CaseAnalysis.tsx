import { useState } from 'react';
import type { Claim, Hypothesis, Workspace } from '../types';
import { ClaimRow } from './ui';
import { EvidenceCard } from './EvidenceDrawer';
import { claimText } from '../services/presentation';

function HypothesisCard({ item, state, onClaim }: { item: Hypothesis; state: Workspace; onClaim: (id: string) => void }) {
  const find = (ids: string[]) => ids.map(id => state.claims.find(c => c.id === id)).filter((c): c is Claim => !!c);
  const support = find(item.supporting_claim_ids);
  const disputed = support.filter(c => c.status === 'disputed');
  const groups = [
    { title: 'Supporting', tone: 'positive', claims: support.filter(c => c.status === 'supported' || c.status === 'partially_supported') },
    { title: 'Contradicting', tone: 'contradiction', claims: [...new Map([...find(item.contradicting_claim_ids), ...disputed].map(c => [c.id, c])).values()] },
    { title: 'Unknown', tone: 'warning', claims: find(item.missing_claim_ids) },
  ];
  return <article className="explanation">
    <div className="explanation-title"><h3>{item.title}</h3><span className="meta">Support: {item.support_assessment.toLowerCase()}</span></div>
    <p>{item.description}</p>{item.generated_by === "gemini" && <details className="disclosure"><summary>Why this explanation?</summary><p>{item.limitations}</p><p className="meta">Evidence basis: {item.supporting_claim_ids.join(", ")}. Contradictions: {item.contradicting_claim_ids.join(", ") || "None"}. Unknowns: {item.missing_claim_ids.join(", ") || "None"}. Open the statements below for source records.</p></details>}
    {groups.map(group => <div className="evidence-group" key={group.title}><h4 className={group.tone}>{group.title}</h4><div>{group.claims.length ? group.claims.map(c => <ClaimRow key={c.id} claim={c} text={group.title === 'Contradicting' && item.supporting_claim_ids.includes(c.id) && c.id === 'c-control' ? 'The common-control statement is disputed.' : claimText(c)} onSelect={onClaim} />) : <p className="empty-note">No records attached.</p>}</div></div>)}
  </article>;
}
export function CaseAnalysis({ state, onClaim }: { state: Workspace; onClaim: (id: string) => void }) {
  const [tab, setTab] = useState('analysis');
  const tabs = [{ id: 'analysis', label: 'Explanations' }, { id: 'findings', label: 'Statements' }, { id: 'evidence', label: `Evidence (${state.evidence.length})` }, { id: 'uncertainty', label: 'Gaps & contradictions' }];
  return <>
    <div className="tabs" role="tablist" aria-label="Case analysis">{tabs.map((t, i) => <button key={t.id} id={'tab-' + t.id} role="tab" aria-controls={'content-' + t.id} aria-selected={tab === t.id} tabIndex={tab === t.id ? 0 : -1} onClick={() => setTab(t.id)} onKeyDown={event => {
      const index = event.key === 'ArrowRight' ? (i + 1) % tabs.length : event.key === 'ArrowLeft' ? (i + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
      if (index >= 0) { event.preventDefault(); setTab(tabs[index].id); document.getElementById('tab-' + tabs[index].id)?.focus(); }
    }}>{t.label}</button>)}</div>
    <div className="analysis-content" id={'content-' + tab} role="tabpanel" aria-labelledby={'tab-' + tab}>
      {tab === 'analysis' && <>{state.hypotheses.map(h => <HypothesisCard key={h.id} item={h} state={state} onClaim={onClaim} />)}{!state.hypotheses.length && <p className="empty-note">No explanations are available for this case.</p>}</>}
      {tab === 'findings' && <>{(['FACT', 'INFERENCE', 'UNKNOWN'] as const).map(category => <section className="statement-group" key={category}><h3>{category === 'FACT' ? 'Facts in the collected records' : category === 'INFERENCE' ? 'Inferences to test' : 'Unknowns'}</h3>{state.claims.filter(c => c.reasoning_category === category).map(c => <ClaimRow key={c.id} claim={c} text={claimText(c)} onSelect={onClaim} />)}</section>)}</>}
      {tab === 'evidence' && <><p className="meta">Source provenance is preserved for every record. {state.fixture ? 'Reliability describes the simulation, not verified real-world activity.' : 'Live records preserve provider provenance. Token symbols and flow relationships do not establish identity or economic value.'}</p>{state.evidence.map(e => <EvidenceCard item={e} key={e.id} />)}</>}
      {tab === 'uncertainty' && <><h3>Contradictions</h3>{state.claims.filter(c => c.contradicting_evidence_ids.length > 0 || c.status === 'disputed').map(c => <ClaimRow key={c.id} claim={c} text={claimText(c)} onSelect={onClaim} />)}<h3 className="subsection-title">Open questions</h3>{state.claims.filter(c => ['unknown', 'unsupported', 'partially_supported'].includes(c.status)).map(c => <ClaimRow key={c.id} claim={c} text={claimText(c)} onSelect={onClaim} />)}<p className="empty-note">A source mentioning an address does not establish who controls it.</p></>}
    </div>
  </>;
}
