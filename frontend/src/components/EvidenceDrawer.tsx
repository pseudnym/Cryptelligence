import { useEffect, useRef, type ReactNode } from 'react';
import type { Claim, Evidence } from '../types';
import { EvidenceType } from './ui';

export function SideDrawer({ title, context, close, children }: { title: string; context: string; close: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const el = dialog.current; el?.showModal(); return () => el?.close(); }, []);
  return <dialog ref={dialog} className="drawer" onCancel={close} aria-labelledby="drawer-title">
    <div className="drawer-header"><span className="eyebrow">{context}</span><button className="button secondary" onClick={close} aria-label="Close inspector">Close <span aria-hidden="true">×</span></button></div>
    <h2 id="drawer-title">{title}</h2>{children}
  </dialog>;
}
export function EvidenceCard({ item }: { item: Evidence }) {
  return <article className="evidence-record">
    <EvidenceType type={item.evidence_type} /><h3>{item.title}</h3>{item.source ? <div className="source-provenance"><h4>SOURCE</h4><p>{item.source.publisher}</p><p>Publication date: {item.source.published_at || 'Not available'} (source/provider supplied)</p><h4>WHAT THE SOURCE SAYS</h4><blockquote>{item.source.excerpt}</blockquote><p className="meta">{item.source.retrieved_document ? 'Retrieved public document' : 'Search snippet only'}; exact identifier match: {item.source.exact_match ? 'yes' : 'unverified'}</p><h4>WHAT WE CAN SAFELY CONCLUDE</h4><p>{item.source.narrow_statement}</p><h4>LIMITATIONS</h4>{item.source.limitations.map(text => <p key={text}>{text}</p>)}<h4>CORROBORATION</h4><p>{item.source.corroboration === 'YES' ? 'Candidate independent reporting (heuristic)' : item.source.corroboration === 'NO' ? 'Not independent' : 'Unknown'}{item.source.derivative ? ' / derivative content detected' : ''}</p><p>{item.source.independence_reason}</p><p className="meta">{item.source.reliability_reason}</p>{item.source.cited_sources.length > 0 && <details className="disclosure"><summary>Cited or linked upstream sources</summary>{item.source.cited_sources.map(url => <p key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a></p>)}</details>}</div> : <p>{item.description}</p>}
    <dl className="provenance">
      <dt>Source identifier</dt><dd><code>{item.source_identifier}</code></dd>
      <dt>Collected</dt><dd><time dateTime={item.collected_at}>{new Date(item.collected_at).toISOString().replace('T', ' ').replace('.000Z', ' UTC')}</time></dd>
      <dt>Record quality</dt><dd>{item.reliability.toLowerCase()} reliability · {item.directness} · {item.reproducible ? 'reproducible' : 'not reproduced'}</dd>
    </dl>
    {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">Open supplied source ↗</a>}
    <details className="disclosure"><summary>Source details & raw record</summary><p className="meta">Source type: {item.source_type}</p><pre>{JSON.stringify(item.raw_data, null, 2)}</pre></details>
  </article>;
}
export function EvidenceDrawer({ claim, evidence, close, fixture = true }: { fixture?: boolean; claim: Claim; evidence: Evidence[]; close: () => void }) {
  const supporting = evidence.filter(e => claim.supporting_evidence_ids.includes(e.id));
  const contradicting = evidence.filter(e => claim.contradicting_evidence_ids.includes(e.id));
  return <SideDrawer title={claim.statement} context="Claim / Evidence review" close={close}>
    {claim.generated_by === "gemini" && <section><h3>Why?</h3><p>{claim.rationale}</p><p>{claim.limitations}</p><p className="meta">Gemini assessment; supporting evidence IDs: {claim.supporting_evidence_ids.join(", ") || "None (unknown)"}. Contradicting IDs: {claim.contradicting_evidence_ids.join(", ") || "None"}.</p></section>}
    <dl className="inline-assessment"><dt>Reasoning category</dt><dd>{claim.reasoning_category.toLowerCase()}</dd><dt>Assessment</dt><dd>{claim.status.replaceAll('_', ' ')}</dd><dt>Confidence</dt><dd>{claim.confidence.toLowerCase()}</dd></dl>
    <section className="limitations"><h3>Limitations</h3><p>{claim.fact_basis === 'public_source' ? 'This records what a public source mentions. It does not establish the truth of its allegations, wallet ownership or identity.' : claim.status === 'unknown' ? 'The attached records document a missing answer; they do not establish this claim.' : claim.claim_type === 'observation' ? 'This is an observation of collected records. A transfer does not establish ownership or intent.' : 'Source statements are not independent proof of ownership. This claim remains subject to the reliability and independence of its sources.'} {fixture ? 'All fixture findings are simulated.' : 'Provider indexing may be incomplete; records are not independently verified by a local node.'}</p></section>
    <h3 className="drawer-section">{claim.status === 'unknown' ? 'Records documenting the gap' : 'Supporting evidence'}</h3>
    {!supporting.length && <p className="empty-note">No supporting records. This is an explicit unknown, not a sourced conclusion.</p>}{supporting.map(e => <EvidenceCard key={e.id} item={e} />)}
    <h3 className="drawer-section">Contradicting evidence</h3>
    {contradicting.length ? contradicting.map(e => <EvidenceCard key={e.id} item={e} />) : <p className="empty-note">No contradicting records attached. Absence of a contradiction is not proof.</p>}
    <details className="disclosure"><summary>Technical references</summary><p className="meta">Claim <code>{claim.id}</code> · required by {claim.required_for_hypothesis_ids.length} competing explanations</p></details>
  </SideDrawer>;
}
