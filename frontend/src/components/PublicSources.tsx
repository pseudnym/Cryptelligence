import { useState } from 'react';
import type { Workspace } from '../types';
import { Panel, SectionHeader } from './ui';
import { EvidenceCard, SideDrawer } from './EvidenceDrawer';

export type SearchPublic = (targetId: string | null, query?: string, capability?: string) => Promise<void>;
export function PublicSources({ state, busy, search }: { state: Workspace; busy: boolean; search: SearchPublic }) {
  const [query, setQuery] = useState('');
  const [target, setTarget] = useState(state.investigation.seed_entity);
  const [selected, setSelected] = useState<string | null>(null);
  const sources = state.evidence.filter(e => e.source);
  const selectedSource = sources.find(e => e.id === selected);
  const blocked = busy || !['AWAITING_ACTION', 'COMPLETE'].includes(state.investigation.status);
  if (state.fixture) return null;
  const targets = state.entities.filter(e => ['wallet', 'contract', 'protocol', 'organization', 'public_identifier'].includes(e.entity_type));
  return <Panel className="public-sources" label="Public-source investigation">
    <SectionHeader title="Public sources" detail="Collect source statements. Mentions do not establish ownership or identity." />
    <div className="public-source-controls">
      <label>Search target<select aria-label="Public search target" value={target} onChange={event => setTarget(event.target.value)}>{targets.map(e => <option key={e.id} value={e.id}>{e.label}</option>)}</select></label>
      <button className="button secondary" disabled={blocked} onClick={() => void search(target)}>Search public sources</button>
      <button className="button secondary" disabled={blocked || !sources.length} onClick={() => void search(target, undefined, 'find_independent_corroboration')}>Find independent corroboration</button>
    </div>
    <details className="public-query"><summary>Search a public name, domain, incident or identifier</summary><form onSubmit={e => { e.preventDefault(); void search(null, query.trim(), 'search_public_identifier'); }}><label htmlFor="public-query">Public identifier</label><input id="public-query" value={query} onChange={e => setQuery(e.target.value)} required minLength={2} maxLength={160} /><button className="button secondary" disabled={blocked || query.trim().length < 2}>Search identifier</button></form></details>
    <div className="source-list">{sources.length ? sources.map(e => <button className="source-result" key={e.id} onClick={() => setSelected(e.id)}><strong>{e.title}</strong><span>{e.source!.publisher} · {e.source!.retrieved_document ? 'Retrieved document' : 'Search snippet only'}</span><span>Corroboration: {e.source!.corroboration.toLowerCase()} · inspect provenance ↗</span></button>) : <p className="empty-note">No public-source records collected yet. Run a search after blockchain collection completes. Provider setup errors appear in the activity panel.</p>}</div>
    {selectedSource && <SideDrawer title={selectedSource.title} context="Public source / Provenance" close={() => setSelected(null)}><EvidenceCard item={selectedSource} /><h3>Candidate identifiers — relationships require verification</h3>{selectedSource.source!.identifiers.map((candidate, i) => <p key={i}><code>{candidate.value}</code> <small>{candidate.kind.replaceAll('_', ' ')}</small></p>)}</SideDrawer>}
  </Panel>;
}
