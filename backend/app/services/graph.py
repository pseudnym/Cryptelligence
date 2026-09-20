import networkx as nx
from ..models.domain import Case

def visible_transactions(case):
    if case.fixture:
        return case.transactions
    by_id = {t.id: t for t in case.transactions}
    selected = []
    for summary in reversed(list(case.collections.values())):
        for id in summary["significant_ids"]:
            if id in by_id and id not in selected:
                selected.append(id)
    return [by_id[id] for id in selected[:case.graph_limit]]

def graph(case: Case):
    g = nx.DiGraph()
    transactions = visible_transactions(case)
    visible = set(case.investigation.seed_entities)
    for tx in transactions:
        visible.update([tx.sender, tx.receiver])
    for relation in case.relationships:
        visible.update([relation.source_entity_id, relation.target_entity_id])
    for e in case.entities:
        if case.fixture or e.id in visible:
            g.add_node(e.id, label=e.label, kind=e.entity_type, value=e.value, chain=e.chain)
    for tx in transactions:
        g.add_node(tx.id, label=f"{tx.amount} {tx.asset}", kind="transaction", value=tx.tx_hash, chain=tx.chain)
        g.add_edge(tx.sender, tx.id, id=tx.id + "-in", label="sent")
        g.add_edge(tx.id, tx.receiver, id=tx.id + "-out", label="received")
    for relation in case.relationships:
        g.add_edge(relation.source_entity_id, relation.target_entity_id, id=relation.id, label="Possible cross-chain transition",
                   kind="inference", evidence_ids=relation.evidence_ids, statement=relation.statement)
    return {"nodes": [{"data": {"id": key, **attrs}} for key, attrs in g.nodes(data=True)],
            "edges": [{"data": {"source": a, "target": b, **attrs}} for a, b, attrs in g.edges(data=True)]}
