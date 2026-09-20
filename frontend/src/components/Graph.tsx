import { useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';
import type { GraphData } from '../types';
import { shortLabel, number } from '../services/presentation';

export function Graph({ data, onSelect }: { data: GraphData; onSelect: (id: string) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const cy = useRef<cytoscape.Core | null>(null);
  useEffect(() => {
    if (!host.current) return;
    const tokens = getComputedStyle(host.current);
    const color = (name: string) => tokens.getPropertyValue(name).trim();
    const live = data.nodes.some(n => n.data.kind === 'transaction' && (n.data.value.startsWith('0x') || n.data.chain === 'solana'));
    const nodes = data.nodes.map(n => ({ data: { ...n.data, display: n.data.kind === 'transaction'
      ? (live ? n.data.label.replace(/^([\d.Ee+-]+)/, amount => '\u2248 ' + new Intl.NumberFormat('en-US', { maximumSignificantDigits: 5, notation: 'compact' }).format(Number(amount))).split('@')[0] : n.data.label.replace(/^([\d.]+)/, amount => number(amount)))
      : shortLabel(n.data.label) } }));
    const graph = cytoscape({
      container: host.current, elements: [...nodes, ...data.edges],
      layout: live ? { name: 'cose', animate: false, randomize: true, nodeDimensionsIncludeLabels: true, idealEdgeLength: 150, nodeRepulsion: 20000, padding: 44 } : { name: 'breadthfirst', directed: true, padding: 44, spacingFactor: 1.25 },
      minZoom: .05, maxZoom: 2, wheelSensitivity: .2,
      style: [
        { selector: 'node', style: { 'background-color': '#657b8d', label: 'data(display)', color: color('--text-primary'), 'font-family': 'Segoe UI, sans-serif', 'font-size': 13, 'text-wrap': 'wrap', 'text-max-width': '115px', 'text-valign': 'bottom', 'text-margin-y': 10, width: 30, height: 30, 'border-width': 2, 'border-color': '#92a5b3' } },
        { selector: '#seed', style: { 'background-color': color('--accent'), 'border-width': 6, 'border-color': '#27424e', width: 36, height: 36 } },
        { selector: 'node[kind = "transaction"]', style: { shape: 'round-rectangle', 'background-color': color('--bg-elevated'), 'border-color': '#647482', width: 18, height: 18, 'font-size': 12, color: color('--text-secondary') } },
        { selector: 'node[kind = "bridge"], node[kind = "contract"], node[kind = "protocol"]', style: { shape: 'hexagon', 'background-color': '#536473', 'border-color': '#a1adb7' } },
        { selector: 'edge', style: { width: 1.5, 'line-color': '#455968', 'target-arrow-color': '#8295a3', 'target-arrow-shape': 'triangle', 'arrow-scale': .8, 'curve-style': 'bezier' } },
        { selector: 'node[chain = "solana"]', style: { 'border-color': '#a79dcc' } },
        { selector: 'edge[kind = "inference"]', style: { 'line-style': 'dashed', 'line-color': '#c3a765', 'target-arrow-color': '#c3a765', label: 'data(label)', 'font-size': 10, color: '#c3a765' } },
        { selector: 'node:selected', style: { 'border-color': color('--accent'), 'border-width': 4 } },
      ],
    });
    cy.current = graph;
    graph.on('tap', 'node', event => onSelect(event.target.id()));
    const observer = new ResizeObserver(() => { graph.resize(); graph.fit(undefined, 44); });
    observer.observe(host.current);
    return () => { observer.disconnect(); graph.destroy(); cy.current = null; };
  }, [data, onSelect]);
  return <div className="graph-workspace">
    <div className="graph-toolbar"><label className="graph-select">Inspect <select aria-label="Inspect graph record" value="" onChange={e => onSelect(e.target.value)}><option value="" disabled>Select an entity or transfer</option>{data.nodes.map(n => <option key={n.data.id} value={n.data.id}>{shortLabel(n.data.label)}</option>)}</select></label><button className="button secondary" onClick={() => cy.current?.fit(undefined, 44)}>Fit graph</button></div>
    <div className="graph-canvas" ref={host} role="img" aria-label={`Transaction graph with ${data.nodes.length} nodes and ${data.edges.length} directed links`} />
    <div className="graph-legend"><span><i className="legend-wallet" />Wallet</span><span><i className="legend-contract" />Contract / bridge</span><span><i className="legend-transaction" />Transaction</span><span>Solana: lavender border</span><span>Dashed: possible cross-chain link</span><span className="graph-hint">Select a node for exact amounts</span></div>
  </div>;
}
