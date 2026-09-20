import { useState, type ReactNode } from 'react';
import type { Claim } from '../types';

export function Panel({ children, className = '', label }: { children: ReactNode; className?: string; label?: string }) {
  return <section className={`panel ${className}`} aria-label={label}>{children}</section>;
}
export function SectionHeader({ title, detail, children }: { title: string; detail?: string; children?: ReactNode }) {
  return <div className="section-header"><div><h2>{title}</h2>{detail && <p className="meta">{detail}</p>}</div>{children}</div>;
}
export function Metric({ label, value }: { label: string; value: number }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}
export function Address({ value }: { value: string }) {
  const [message, setMessage] = useState('');
  async function copy() {
    try { await navigator.clipboard.writeText(value); setMessage('Copied'); }
    catch { setMessage('Copy unavailable. Select the full address below.'); }
  }
  return <div className="address"><code title={value}>{value.length > 24 ? value.slice(0, 8) + '…' + value.slice(-6) : value}</code><button className="button tertiary" onClick={() => void copy()} aria-label="Copy seed wallet address">Copy</button>{message && <span className="meta" role="status">{message}</span>}{message.startsWith('Copy unavailable') && <code className="full-address">{value}</code>}</div>;
}
export function EvidenceType({ type }: { type: string }) {
  const labels: Record<string, string> = { blockchain_observation: 'Deterministic blockchain', osint: 'OSINT', external_attribution: 'External attribution', model_inference: 'AI inference', analyst_input: 'Analyst input' };
  return <span className="evidence-type"><span aria-hidden="true" className="source-marker" />{labels[type] || type.replaceAll('_', ' ')}</span>;
}
export function ClaimRow({ claim, onSelect, text }: { claim: Claim; onSelect: (id: string) => void; text?: string }) {
  const tone = claim.status === 'supported' ? 'positive' : claim.status === 'disputed' ? 'contradiction' : 'warning';
  return <button className="claim-row" onClick={() => onSelect(claim.id)}>
    <span className={`marker ${tone}`} aria-hidden="true" />
    <span>{text || claim.statement}<small><span className={'reasoning-category ' + claim.reasoning_category.toLowerCase()}>{claim.reasoning_category === 'FACT' && claim.fact_basis === 'public_source' ? 'public-source fact' : claim.reasoning_category.toLowerCase()}</span> · {claim.status.replaceAll('_', ' ')}</small></span>
    <span className="open-arrow" aria-hidden="true">↗</span>
  </button>;
}
