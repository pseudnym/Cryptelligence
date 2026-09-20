"""Significance and address pivots over normalized Ethereum records."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from .ethereum_provider import ProviderError, entity
from .tools import ToolResult, Observation

def summarize(records, target, limit):
    successful = [t for t in records if t.metadata["status"] == "success"]
    inbound = [t for t in successful if t.receiver == target]
    outbound = [t for t in successful if t.sender == target]
    groups = defaultdict(list)
    for tx in successful:
        groups[(tx.asset, tx.metadata["record_kind"])].append(tx)
    significant = []
    # Round-robin across assets; quantities of different tokens are never compared.
    ranked = [sorted(rows, key=lambda t: (-t.amount, t.id)) for _, rows in sorted(groups.items(), key=lambda item: (item[0][0] != "ETH", item[0]))]
    for index in range(limit):
        for rows in ranked:
            if index < len(rows) and len(significant) < limit:
                significant.append(rows[index].id)
    counts = Counter(t.sender if t.receiver == target else t.receiver for t in successful)
    counts.pop(target, None)
    def largest(rows):
        result = []
        for (asset, kind), group in sorted(groups.items()):
            candidates = sorted((t for t in rows if t.asset == asset and t.metadata["record_kind"] == kind), key=lambda t: (-t.amount, t.id))[:3]
            result.extend({"transaction_id": t.id, "asset": t.asset, "amount": str(t.amount), "kind": kind} for t in candidates)
        return result[:30]
    top = [dict(entity_id=id, event_count=count) for id, count in counts.most_common(10)]
    # Relative outliers only within the same asset and record type.
    unusual = []
    for rows in groups.values():
        positive = sorted(t.amount for t in rows if t.amount > 0)
        if len(positive) >= 3:
            median = positive[len(positive) // 2]
            unusual.extend(t.id for t in rows if t.amount > median * 10)
    return dict(window_transaction_count=len({t.tx_hash for t in records}),
        event_count=len(records), inbound_count=len(inbound), outbound_count=len(outbound),
        normal_count=sum(t.metadata["record_kind"] == "normal" for t in records),
        internal_count=sum(t.metadata["record_kind"] == "internal" for t in records),
        token_count=sum(t.metadata["record_kind"] == "token" for t in records),
        failed_or_unknown_count=sum(t.metadata["status"] != "success" for t in records),
        top_counterparties=top, frequently_used_counterparties=[c for c in top if c["event_count"] > 1],
        largest_inbound=largest(inbound), largest_outbound=largest(outbound),
        first_observed=min((t.timestamp.isoformat() for t in records), default=None),
        most_recent=max((t.timestamp.isoformat() for t in records), default=None),
        contract_interactions=sorted({t.receiver for t in successful if t.metadata.get("contract_interaction")}),
        unusual_high_value_ids=sorted(unusual)[:20], significant_ids=significant,
        scope="Collected window only; counts are events, not lifetime totals. Native and internal values are not summed. Token value and legitimacy are unverified.")

class EthereumInvestigationTool:
    name = "EthereumInvestigationTool"
    capability = ("inspect_address", "get_transactions", "get_token_transfers", "get_internal_transactions",
                  "inspect_transaction", "identify_top_counterparties", "identify_contract_interactions",
                  "expand_counterparty", "trace_inbound", "trace_outbound")
    def __init__(self, provider, settings):
        self.provider, self.settings = provider, settings
    def can_handle(self, action):
        return action in self.capability

    def execute(self, context, action):
        if context.fixture:
            raise ProviderError("mode", "Live collection cannot run in a fixture case.")
        selected = next((a for a in context.actions if a.id == context.active_action_id), None)
        targets = [selected.target_entity_id] if selected else [e.id for e in context.entities if e.id in context.investigation.seed_entities and e.chain == "ethereum"]
        result = ToolResult()
        for target in targets:
            item = next(e for e in context.entities if e.id == target)
            if item.chain != "ethereum":
                raise ProviderError("target", "Ethereum tool requires an Ethereum target.")
            if len(context.transactions) + len(result.transactions) >= self.settings.case_limit:
                raise ProviderError("limit", "The configured case record limit has been reached. Existing evidence is preserved.")
            direction = "inbound" if action == "trace_inbound" else "outbound" if action == "trace_outbound" else "all"
            kinds = {"get_transactions": ["normal"], "get_token_transfers": ["token"],
                     "get_internal_transactions": ["internal"]}.get(action, ["normal", "token", "internal"])
            records, entities, warnings, examined, truncated = [], [item], [], 0, False
            total, successful_requests = None, 0
            if action == "inspect_transaction":
                batch = self.provider.inspect_transaction(item.value)
                records, entities, examined = batch.records, batch.entities, batch.examined
                successful_requests = 1
            else:
                try:
                    inspected, total = self.provider.inspect_address(item.value)
                    entities.append(inspected)
                    total = self.provider.transaction_count(item.value)
                except ProviderError as error:
                    if error.kind in {"configuration", "authentication"}: raise
                    if error.kind == "rate_limit":
                        result.warnings.append(item.value + ": " + str(error))
                        continue
                    warnings.append(str(error))
                for kind in kinds:
                    try:
                        batch = self.provider.history(item.value, kind, direction)
                        successful_requests += 1
                        records.extend(batch.records); entities.extend(batch.entities)
                        examined += batch.examined; truncated |= batch.truncated
                        warnings.extend(batch.warnings)
                    except ProviderError as error:
                        if error.kind in {"configuration", "authentication"}: raise
                        warnings.append(kind + ": " + str(error))
            if not successful_requests:
                result.warnings.append(item.value + ": No Ethereum history endpoint succeeded. " + " ".join(dict.fromkeys(warnings)))
                continue
            records = list({t.id: t for t in records}.values())
            known = {t.id for t in context.transactions} | {t.id for t in result.transactions}
            space = self.settings.case_limit - len(known)
            retained = []
            for tx in records:
                if tx.id in known or space > 0:
                    retained.append(tx)
                    if tx.id not in known:
                        known.add(tx.id); space -= 1
                else:
                    truncated = True
            records = retained
            summary = summarize(records, target, min(12, self.settings.graph_limit))
            summary.update(entity_id=target, provider=self.provider.name, provider_transaction_count=total,
                examined=examined, truncated=truncated, warnings=list(dict.fromkeys(warnings)),
                direction=direction, capability=action, collected_at=datetime.now(timezone.utc).isoformat())
            key = target + ":" + direction + ":" + action
            result.collections[key] = summary
            result.warnings.extend(summary["warnings"])
            result.transactions.extend(records)
            result.entities.extend(entities)
            for tx in records:
                success = tx.metadata["status"] == "success"
                result.observations.append(Observation(id="e-" + tx.id, evidence_type="blockchain_observation",
                    title=("Recorded transfer: " if success else "Unsuccessful or unconfirmed call: ") + tx.asset,
                    description=(f"{tx.amount} {tx.asset} recorded from {tx.sender[4:]} to {tx.receiver[4:]}." if success else
                                 "This record does not establish a completed transfer.") + " On-chain flow does not establish ownership.",
                    source_type=self.provider.name, source_identifier=tx.id,
                    source_url=self.settings.base_url + "/transactions/" + tx.tx_hash,
                    raw_data={"chain": "ethereum", "transaction_id": tx.id, "transaction": tx.model_dump(mode="json"),
                              "source_provider": self.provider.name},
                    linked_entity_ids=[tx.sender, tx.receiver], reliability="HIGH", directness="direct"))
            # A collection receipt makes empty/partial coverage inspectable without claiming inactivity.
            receipt = {k: v for k, v in summary.items() if k != "collected_at"}
            digest = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()[:24]
            result.observations.append(Observation(id="collection-" + digest, evidence_type="analyst_input",
                title="Ethereum collection coverage", description=f"{examined} records examined; {len(records)} normalized events retained. " + summary["scope"],
                source_type=self.provider.name, source_identifier="collection:" + key + ":" + digest,
                source_url=self.settings.base_url + "/addresses/" + item.value,
                raw_data=receipt, linked_entity_ids=[target], reliability="HIGH", directness="direct"))
        if not result.collections:
            raise ProviderError("collection", " ".join(dict.fromkeys(result.warnings)))
        result.entities = list({e.id: e for e in result.entities}.values())
        result.transactions = list({t.id: t for t in result.transactions}.values())
        result.observations = list({o.id: o for o in result.observations}.values())
        return result
