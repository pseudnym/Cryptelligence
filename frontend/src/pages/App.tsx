import { useCallback, useState } from 'react';
import { ChainScope } from '../components/ChainScope';
import { GeminiAssessment } from '../components/GeminiAssessment';
import { PublicSources } from '../components/PublicSources';
import { Graph } from '../components/Graph';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { EntityInspector } from '../components/EntityInspector';
import { CaseAnalysis } from '../components/CaseAnalysis';
import { InvestigationActivity, RevisionSummary } from '../components/InvestigationActivity';
import { Decisions } from '../components/Decisions';
import { Address, Metric, Panel, SectionHeader } from '../components/ui';
import { useInvestigation } from '../hooks/useInvestigation';
import { assessment, shortLabel, number } from '../services/presentation';

const SEED = '0x629e7Da20197a5429d30da36E77d06CdF796b71A';
export function App() {
  const { caseState: state, busy, error, create, execute, reset, resume, expand, search, pause, addSeed, relationship } = useInvestigation();
  const [mode, setMode] = useState<'fixture' | 'live'>('fixture');
  const [wallets, setWallets] = useState([SEED]);
  const [objective, setObjective] = useState('What activity is this wallet associated with, and what evidence exists about where the funds came from and where they went?');
  const [claimId, setClaimId] = useState<string | null>(null);
  const [nodeId, setNodeId] = useState<string | null>(null);
  const selectNode = useCallback((id: string) => { setClaimId(null); setNodeId(id); }, []);
  const selectClaim = useCallback((id: string) => { setNodeId(null); setClaimId(id); }, []);
  const selectedClaim = state?.claims.find(c => c.id === claimId);
  const name = (id: string) => shortLabel(state?.entities.find(e => e.id === id)?.label || id);
  function newCase() { reset(); setClaimId(null); setNodeId(null); }
  return <div className="app">
    <header className="app-bar"><div className="brand">Evidence Engine<span>Investigation workspace</span></div><span className="environment">Local environment · MVP1</span>{state && <button className="button secondary" disabled={busy} onClick={newCase}>New investigation</button>}</header>
    {error && <div className="error-banner" role="alert"><p>{error}</p>{state && <button className="button secondary" disabled={busy} onClick={() => void resume()}>Retry connection</button>}<button className="button secondary" disabled={busy} onClick={newCase}>Back to setup</button></div>}
    {!state && busy && window.location.hash.startsWith('#case=') ? <main id="main" className="restore-state" role="status"><div className="eyebrow">Case workspace</div><h1>Restoring investigation</h1><p>Loading the saved evidence, assessment and next step.</p></main> : !state ? <main id="main" className="setup">
      <div className="eyebrow">Cases / New investigation</div><h1>Start with an address.</h1><p>Trace the recorded activity, test competing explanations, and identify the evidence worth pursuing next.</p>
      <form className="setup-form" aria-busy={busy} onSubmit={event => { event.preventDefault(); void create(wallets.map(wallet => wallet.trim()), objective.trim(), mode); }}>
        <label htmlFor="data-mode">Data mode</label><select id="data-mode" disabled={busy} value={mode} onChange={e => setMode(e.target.value as 'fixture' | 'live')}><option value="fixture">FIXTURE DATA - offline demo</option><option value="live">LIVE DATA - Ethereum / Solana providers</option></select><p className="meta">{mode === 'live' ? 'Collect real Ethereum and Solana records using the backend provider configuration.' : 'Use deterministic synthetic observations without a network connection.'}</p>
        <fieldset className="seed-inputs"><legend>Seed entities</legend>{wallets.map((wallet, index) => <div className="seed-input" key={index}><label htmlFor={'wallet-' + index}>{mode === 'fixture' ? (index === 0 ? 'Ethereum wallet' : 'Ethereum wallet ' + (index + 1)) : 'Ethereum or Solana wallet ' + (index + 1)}</label><div><input id={'wallet-' + index} className="mono" required pattern={mode === "fixture" ? "0x[a-fA-F0-9]{40}" : "(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})"} value={wallet} disabled={busy} onChange={event => setWallets(values => values.map((value, i) => i === index ? event.target.value : value))} />{wallets.length > 1 && <button type="button" className="button secondary" aria-label={'Remove wallet ' + (index + 1)} onClick={() => setWallets(values => values.filter((_, i) => i !== index))}>Remove</button>}</div></div>)}<button type="button" className="button tertiary" disabled={busy || wallets.length >= 10} onClick={() => setWallets(values => [...values, ''])}>+ Add wallet</button></fieldset>
        <label htmlFor="objective">Investigation question</label><textarea id="objective" required maxLength={2000} disabled={busy} value={objective} onChange={e => setObjective(e.target.value)} />
        <button className="button primary" disabled={busy || !objective.trim()}>{busy ? 'Loading local case…' : 'Start investigation →'}</button>
      </form><div className="environment-banner"><strong>{mode === 'live' ? 'LIVE DATA' : 'FIXTURE DATA'}</strong><span>{mode === 'live' ? 'Uses the configured blockchain providers. Public-source search is available after collection; no automatic identity attribution.' : 'Synthetic observations only. No live lookup runs.'}</span></div>
    </main> : <main id="main" className="workspace" aria-busy={busy}>
      <div className="case-header"><div><div className="breadcrumb">Cases <span>/</span> Active investigation</div><h1>Investigation overview</h1><div className="case-identity"><span className="meta">Seed wallet</span>{state.entities.filter(e => state.investigation.seed_entities.includes(e.id)).map(e => <Address key={e.id} value={e.value} />)}<span className="chain-label">{[...new Set(state.entities.filter(e => state.investigation.seed_entities.includes(e.id)).map(e => e.chain))].join(" / ")}</span></div></div><div className="case-status"><span><i className="status-dot" />{state.investigation.status === 'COMPLETE' ? 'Review complete · questions remain' : !['AWAITING_ACTION', 'COMPLETE'].includes(state.investigation.status) ? 'Review in progress' : 'Ready for review'}</span><small>Revision {state.revision}</small></div></div>
      <div className="environment-banner"><strong>{state.fixture ? 'FIXTURE DATA' : 'LIVE DATA'}</strong><span>{state.fixture_notice}</span></div>
      <section className="briefing" aria-label="Investigation summary"><div className="briefing-objective"><h2>Investigation summary</h2><span className="field-label">Objective</span><p>{state.investigation.objective}</p></div><div className="briefing-assessment"><h2>Current assessment</h2><p>{assessment(state)}</p></div><div className="metrics"><Metric label="Blockchain records" value={state.evidence.filter(e => e.evidence_type === 'blockchain_observation').length} /><Metric label="External / OSINT" value={state.evidence.filter(e => ['osint', 'external_attribution'].includes(e.evidence_type)).length} /><Metric label="Open questions" value={state.claims.filter(c => c.reasoning_category === 'UNKNOWN').length} /><Metric label="Competing explanations" value={state.hypotheses.length} /></div></section>
      <InvestigationActivity state={state} busy={busy} resume={resume} />
      <GeminiAssessment state={state} onClaim={selectClaim} pause={pause} /><RevisionSummary state={state} />
      <ChainScope state={state} busy={busy} addSeed={addSeed} relationship={relationship} />
      <PublicSources state={state} busy={busy} search={search} />
      <div className="work-grid">
        <Panel className="flow-panel" label="Transaction and entity graph"><SectionHeader title="What happened?" detail={`${state.entities.length} entities · ${state.transactions.length} recorded transfers`}><span className="meta">{state.fixture ? 'Synthetic Ethereum activity' : 'Significant blockchain relationships'}</span></SectionHeader>
          {!state.fixture && <p className="meta collection-note">{state.graph.nodes.filter(n => n.data.kind === 'transaction').length} significant events shown from {state.transactions.length} collected events. Select an address for window summaries, history and expansion.</p>}
          <Graph data={state.graph} onSelect={selectNode} />
          <div className="transfer-ledger"><div className="ledger-heading"><h3>Recorded fund flow</h3><span className="meta">Select a transfer for its evidence</span></div>{state.transactions.filter(t => state.graph.nodes.some(n => n.data.id === t.id)).map(t => <button className="transfer-row" key={t.id} onClick={() => selectNode(t.id)}><span>{name(t.sender)} <span className="flow-arrow">→</span> {name(t.receiver)}</span><strong>{number(t.amount)} {t.asset}</strong><span className="open-arrow" aria-hidden="true">↗</span></button>)}{!state.transactions.length && <p className="empty-note">No transactions have been recorded.</p>}<p className="meta ledger-note">Transfer direction shows fund movement, not common ownership.</p></div>
        </Panel>
        <Panel className="analysis-panel" label="Case analysis"><SectionHeader title="What does the evidence support?" detail="Competing explanations, with their supporting records" /><CaseAnalysis state={state} onClaim={selectClaim} /></Panel>
      </div>
      <Decisions state={state} busy={busy || state.investigation.status !== 'AWAITING_ACTION'} execute={execute} onClaim={selectClaim} />
      <footer>Local case saved automatically <span>·</span> Evidence supports statements, not certainty</footer>
    </main>}
    {selectedClaim && state && <EvidenceDrawer fixture={state.fixture} claim={selectedClaim} evidence={state.evidence} close={() => setClaimId(null)} />}
    {nodeId && state && <EntityInspector key={nodeId} busy={busy} expand={expand} search={search} state={state} id={nodeId} close={() => setNodeId(null)} onClaim={selectClaim} />}
  </div>;
}
