import type { SearchPublic } from './PublicSources';
import { useState } from 'react';
import type { Workspace } from '../types';
import { linkedEvidence, shortLabel, number, claimText } from '../services/presentation';
import { SideDrawer, EvidenceCard } from './EvidenceDrawer';
import { ClaimRow } from './ui';

export function EntityInspector({ state, id, close, onClaim, busy, expand, search }: { state: Workspace; id: string; close: () => void; onClaim: (id: string) => void; busy: boolean; search: SearchPublic; expand: (id: string, direction: 'inbound' | 'outbound' | 'inspect') => Promise<void> }) {
  const [page, setPage] = useState(0);
  const [recordId, setRecordId] = useState<string | null>(null);
  const summaries = Object.values(state.collections || {}).filter(s => s.entity_id === id);
  const entity = state.entities.find(e => e.id === id);
  const transaction = state.transactions.find(t => t.id === id);
  const related = state.transactions.filter(t => t.id === id || t.sender === id || t.receiver === id);
  const evidence = linkedEvidence(state, recordId || id);
  const evidenceIds = new Set(evidence.map(e => e.id));
  const claims = state.claims.filter(c => [...c.supporting_evidence_ids, ...c.contradicting_evidence_ids].some(e => evidenceIds.has(e)));
  const name = (entityId: string) => shortLabel(state.entities.find(e => e.id === entityId)?.label || entityId);
  const why = id === state.investigation.seed_entity ? 'This is the starting address for the investigation. Its incoming and outgoing transfers anchor the fund-flow account.'
    : transaction ? 'This transfer connects the entities shown in the flow. Its amount and direction are observations, not evidence of shared ownership.'
    : entity?.entity_type === 'bridge' ? 'This is the origin of the incoming transfer in the fixture. A destination match is still needed before drawing cross-chain conclusions.'
    : 'This entity is connected to the seed through the recorded fund flow. Receiving funds alone does not identify its controller.';
  return <SideDrawer title={entity ? shortLabel(entity.label) : transaction ? number(transaction.amount) + ' ' + transaction.asset + ' transfer' : 'Record unavailable'} context="Graph / Contextual inspector" close={close}>
    <h3 className="drawer-section">Why this entity matters</h3><p>{why}</p>
    {!state.fixture && <button className="button secondary" disabled={busy || !['AWAITING_ACTION', 'COMPLETE'].includes(state.investigation.status)} onClick={() => { close(); void search(id, undefined, transaction ? 'search_transaction_hash' : 'search_public_identifier'); }}>{transaction ? 'Search this transaction hash' : 'Search this identifier in public sources'}</button>}
    <h3 className="drawer-section">Entity details</h3>
    <dl className="provenance"><dt>Chain</dt><dd>{entity?.chain || transaction?.chain || "Unknown"}</dd><dt>Type</dt><dd>{entity?.entity_type || 'transaction'}</dd><dt>Identifier</dt><dd><code>{entity?.value || transaction?.tx_hash || id}</code></dd><dt>Data status</dt><dd>{!state.fixture ? 'LIVE provider records; no ownership attribution' : id === state.investigation.seed_entity ? 'Supplied address; activity is synthetic' : 'Synthetic fixture record'}</dd></dl>
    {!state.fixture && entity && ['wallet', 'contract'].includes(entity.entity_type) && <section aria-label="Blockchain investigation pivots"><h3 className="drawer-section">Investigate this address</h3><div className="pivot-controls">{(['inbound', 'outbound', 'inspect'] as const).map(direction => <button className="button secondary" disabled={busy || !['AWAITING_ACTION', 'COMPLETE'].includes(state.investigation.status)} key={direction} onClick={() => { close(); void expand(id, direction); }}>{direction === 'inbound' ? 'Expand inbound' : direction === 'outbound' ? 'Expand outbound' : 'Inspect counterparty'}</button>)}</div><p className="meta">Adds chain-specific provider evidence to this investigation. Previously completed pivots are not repeated.</p></section>}
    {!state.fixture && summaries.map((s, index) => <section className="collection-summary" key={index}><h3 className="drawer-section">Collected window: {s.direction}</h3><p>{s.window_transaction_count} distinct transactions / {s.event_count} events. {s.inbound_count} inbound, {s.outbound_count} outbound, {s.token_count} token events, {s.internal_count} internal events.</p><p className="meta">Provider lifetime transaction counter: {s.provider_transaction_count ?? 'unavailable'}. Not comparable to combined event counts.</p><p className="meta">First / latest in this window: {s.first_observed || 'none'} / {s.most_recent || 'none'}</p><p className="meta">{s.scope}</p>{s.truncated && <p className="warning">History truncated by configured collection limits.</p>}{s.warnings.map((warning, i) => <p className="warning" key={i}>{warning}</p>)}<details className="disclosure"><summary>Counterparties, largest flows and contract interactions</summary><p>{s.top_counterparties.length} top counterparties; {s.contract_interactions.length} contract addresses; {s.unusual_high_value_ids.length} within-asset outliers (over 10 times the positive median).</p><pre>{JSON.stringify({ top_counterparties: s.top_counterparties, largest_inbound: s.largest_inbound, largest_outbound: s.largest_outbound, contract_interactions: s.contract_interactions, unusual_high_value_ids: s.unusual_high_value_ids }, null, 2)}</pre></details></section>)}
    <h3 className="drawer-section">{state.fixture ? 'Related transactions' : 'Collected history (normalized raw records)'}</h3>
    {related.length ? (state.fixture ? related : related.slice(page * 20, (page + 1) * 20)).map(t => <div className="related-transfer" key={t.id}><span>{name(t.sender)} → {name(t.receiver)}</span><strong>{number(t.amount)} {t.asset}</strong><code>{t.tx_hash}</code>{!state.fixture && <><span className="meta">{t.metadata.record_kind} / {t.metadata.status}</span><button className="button tertiary" onClick={() => setRecordId(t.id)}>Inspect record evidence</button></>}</div>) : <p className="empty-note">No related transfers in the current case.</p>}
    {!state.fixture && related.length > 20 && <div className="pivot-controls"><button className="button secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous records</button><span className="meta">Page {page + 1} of {Math.ceil(related.length / 20)}</span><button className="button secondary" disabled={(page + 1) * 20 >= related.length} onClick={() => setPage(page + 1)}>Next records</button></div>}
    <h3 className="drawer-section">Claims involving this entity</h3>
    <p className="meta">Connected through linked evidence; this is not an identity attribution.</p>
    {claims.length ? claims.map(c => <ClaimRow key={c.id} claim={c} text={claimText(c)} onSelect={onClaim} />) : <p className="empty-note">No claims reference the linked records.</p>}
    <h3 className="drawer-section">Linked evidence</h3>{!state.fixture && !recordId && !transaction && evidence.length > 5 && <p className="meta">Showing five linked records. Choose a history entry to inspect its exact evidence.</p>}
    {evidence.length ? (state.fixture || recordId || transaction ? evidence : evidence.slice(0, 5)).map(e => <EvidenceCard item={e} key={e.id} />) : <p className="empty-note">No evidence is attached to this record.</p>}
  </SideDrawer>;
}
