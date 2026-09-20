import type { Claim, Workspace } from '../types';

// Presentation copy for the existing fixture; this layer never changes case state.
export const shortLabel = (label: string) => label.replace(/\s*[·] fixture/g, '').replace('Development seed', 'Seed wallet');
export const number = (amount: string) => {
  const [whole, fraction] = amount.split('.');
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction ? '.' + fraction : '');
};
export const claimText = (claim: Claim) => ({
  'c-flow': 'The seed sent funds to Counterparty B.',
  'c-attribution': 'A source note links the seed to the incident.',
  'c-control': 'The seed and Counterparty B may share control.',
  'c-service': 'Counterparty B may handle funds for unrelated users.',
  'c-gap': 'Who controls the seed and Counterparty B?',
}[claim.id] || claim.statement);
export function assessment(state: Workspace) { return state.investigation.summary; }
export function linkedEvidence(state: Workspace, id: string) {
  const transaction = state.transactions.find(t => t.id === id);
  return state.evidence.filter(e => transaction
    ? e.raw_data.transaction_id === id || (e.raw_data.transaction as { id?: string } | undefined)?.id === id || e.source_identifier === transaction.tx_hash
    : e.linked_entity_ids.includes(id));
}
export const actionCopy: Record<string, { title: string; why: string; question: string; button: string }> = {
  'a-verify': { title: 'Verify attribution with an independent source', why: 'The common-control explanation relies on an external attribution that has not been independently corroborated.', question: 'Is there independent support for common control?', button: 'Run source check' },
  'a-expand': { title: 'Follow Counterparty B’s next transfer', why: 'The source check left ownership unresolved. Another transfer can reveal where the funds went, although it cannot prove who controls them.', question: 'Where did Counterparty B send the funds?', button: 'Expand fund flow' },
  'a-bridge': { title: 'Check the bridge destination', why: 'The current records do not contain a matched destination. Checking coverage makes the cross-chain limitation explicit.', question: 'Is a matching destination record available?', button: 'Check bridge records' },
};
