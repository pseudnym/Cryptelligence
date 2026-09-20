import { useState } from 'react';
import type { Workspace } from '../types';
import { Panel, SectionHeader } from './ui';
import { EvidenceCard } from './EvidenceDrawer';

export function ChainScope({ state, busy, addSeed, relationship }: {state: Workspace; busy: boolean; addSeed: (address: string) => Promise<void>; relationship: (source: string, target: string, evidence: string[], statement: string) => Promise<void>}) {
  const [address, setAddress] = useState('');
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [evidence, setEvidence] = useState('');
  const [statement, setStatement] = useState('');
  if (state.fixture) return null;
  const blocked = busy || !['AWAITING_ACTION', 'COMPLETE'].includes(state.investigation.status);
  const eth = state.entities.filter(e => e.chain === 'ethereum');
  const sol = state.entities.filter(e => e.chain === 'solana');
  return <Panel label="Chain scope" className="chain-scope"><SectionHeader title="Chain scope" detail="Ethereum and Solana evidence stay in one case. Similar timing or value does not establish a cross-chain link." />
    <details className="disclosure"><summary>Add a wallet to this investigation</summary><form onSubmit={e => {e.preventDefault(); void addSeed(address.trim());}}><label htmlFor="additional-wallet">Ethereum or Solana address</label><input id="additional-wallet" required value={address} onChange={e => setAddress(e.target.value)} /><button className="button secondary" disabled={blocked}>Collect added wallet</button></form></details>
    {eth.length > 0 && sol.length > 0 && <details className="disclosure"><summary>Propose an evidence-backed cross-chain link</summary><p>This records an analyst inference, not a verified bridge match.</p><form onSubmit={e => {e.preventDefault(); void relationship(source, target, [evidence], statement);}}>
      <label>Ethereum entity<select required value={source} onChange={e => setSource(e.target.value)}><option value="">Select Ethereum entity</option>{eth.map(e => <option key={e.id} value={e.id}>{e.label}</option>)}</select></label>
      <label>Solana entity<select required value={target} onChange={e => setTarget(e.target.value)}><option value="">Select Solana entity</option>{sol.map(e => <option key={e.id} value={e.id}>{e.label}</option>)}</select></label>
      <label>Supporting record<select required value={evidence} onChange={e => setEvidence(e.target.value)}><option value="">Select existing evidence</option>{state.evidence.map(e => <option key={e.id} value={e.id}>{e.title}</option>)}</select></label>
      <label>Relationship and limitations<textarea required minLength={10} maxLength={1000} value={statement} onChange={e => setStatement(e.target.value)} /></label><button className="button secondary" disabled={blocked}>Record proposed link</button>
    </form></details>}
    {state.relationships.map(r => <details className="disclosure" key={r.id}><summary>INFERENCE: {r.statement}</summary><p>Analyst-proposed possible cross-chain transition. No common ownership or matched bridge transfer is established.</p>{state.evidence.filter(e => r.evidence_ids.includes(e.id)).map(e => <EvidenceCard key={e.id} item={e} />)}</details>)}
  </Panel>;
}
