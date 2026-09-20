import type { Workspace } from '../types';
async function request(path: string, body?: unknown): Promise<Workspace> {
  const response = await fetch('/api' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = typeof payload?.detail === 'string' ? payload.detail
      : Array.isArray(payload?.detail) ? payload.detail.map((item: { msg: string }) => item.msg).join('; ')
      : 'Unable to load the investigation. Check your input and the local backend.';
    throw new Error(detail);
  }
  return response.json();
}
const route = (id: string) => '/investigations/' + encodeURIComponent(id);
export const api = {
  create: (seeds: string[], question: string, mode: 'fixture' | 'live') => request('/investigations', { seeds, question, mode }),
  expand: (id: string, entity_id: string, direction: 'inbound' | 'outbound' | 'inspect') => request(route(id) + '/expand', { entity_id, direction }),
  search: (id: string, target_id: string | null, query?: string, capability = 'search_exact_wallet_address') => request(route(id) + '/search', query ? { query, capability } : { target_id, capability }),
  get: (id: string) => request(route(id)),
  advance: (id: string, version: number) => request(route(id) + '/advance', { expected_version: version }),
  addSeed: (id: string, address: string) => request(route(id) + '/seeds', { address }),
  relationship: (id: string, source_entity_id: string, target_entity_id: string, evidence_ids: string[], statement: string) => request(route(id) + '/relationships', { source_entity_id, target_entity_id, evidence_ids, statement }),
  pause: (id: string) => request(route(id) + "/pause", {}),
  retry: (id: string) => request(route(id) + '/retry', {}),
  execute: (id: string, actionId: string) => request(route(id) + '/actions/' + encodeURIComponent(actionId) + '/execute', {}),
};
