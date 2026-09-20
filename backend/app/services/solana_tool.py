"""Solana capabilities reuse the existing case/evidence/action pipeline."""
from datetime import datetime, timezone
import hashlib
import json
from .tools import ToolResult, Observation
from .ethereum_provider import ProviderError
from .ethereum_tool import summarize

CAPABILITIES = ("inspect_solana_address","get_solana_transactions","inspect_solana_transaction",
                "identify_solana_counterparties","identify_program_interactions","trace_solana_inbound",
                "trace_solana_outbound","expand_solana_address")

class SolanaInvestigationTool:
    name="SolanaInvestigationTool"
    capability=CAPABILITIES
    def __init__(self,provider,settings): self.provider,self.settings=provider,settings
    def can_handle(self,action): return action in self.capability
    def execute(self,context,action):
        if context.fixture: raise ProviderError("mode","Solana live collection cannot run in fixture mode.")
        selected=next((a for a in context.actions if a.id==context.active_action_id),None)
        targets=[selected.target_entity_id] if selected else [e.id for e in context.entities if e.id in context.investigation.seed_entities and e.chain=="solana"]
        result=ToolResult()
        for target in targets:
            entity=next(e for e in context.entities if e.id==target)
            if entity.chain != "solana": raise ProviderError("target","Solana tool requires a Solana target.")
            signatures=[entity.value] if action=="inspect_solana_transaction" else self.provider.signatures(entity.value)
            records=[]; observations=[]; warnings=[]; completed=0
            for signature in signatures:
                try:
                    batch=self.provider.transaction(signature)
                    if action!="inspect_solana_transaction" and not any(e.id==target for e in batch.entities):
                        warnings.append("An unrelated Solana signature was excluded."); continue
                    records.extend(batch.transactions); observations.extend(batch.observations)
                    result.entities.extend(batch.entities); warnings.extend(batch.warnings); completed+=1
                except ProviderError as error:
                    if error.kind in {"authentication","configuration"}: raise
                    warnings.append(error.safe_message)
                    if error.kind in {"rate_limit","timeout"}: break
            if signatures and not completed:
                raise ProviderError("collection","No Solana transaction could be collected. "+" ".join(dict.fromkeys(warnings)))
            direction="inbound" if action=="trace_solana_inbound" else "outbound" if action=="trace_solana_outbound" else "all"
            relevant=[t for t in records if action=="inspect_solana_transaction" or (t.receiver==target if direction=="inbound" else t.sender==target if direction=="outbound" else target in (t.sender,t.receiver))]
            # Save all normalized observations from the inspected transaction, but
            # only wallet-related events determine its counterparty summary.
            known={t.id for t in context.transactions}|{t.id for t in result.transactions}
            if len(known|{t.id for t in records})>self.settings.case_limit:
                raise ProviderError("limit","Solana collection would exceed the case event limit. Existing evidence is preserved.")
            result.transactions.extend(records); result.observations.extend(observations)
            summary=summarize(relevant,target,min(12,context.graph_limit))
            summary.update(entity_id=target,chain="solana",provider=self.provider.name,provider_transaction_count=None,
                examined=len(signatures),truncated=len(signatures)>=self.settings.max_signatures,warnings=list(dict.fromkeys(warnings)),
                direction=direction,capability=action,collected_at=datetime.now(timezone.utc).isoformat(),
                scope="Bounded finalized Solana signature window; parsed SOL/SPL instructions only. Fees/rent/balance deltas are not transfer edges. Program IDs are not protocol attribution.")
            result.collections[target+":"+direction+":"+action]=summary
            receipt={k:v for k,v in summary.items() if k!="collected_at"}
            digest=hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()[:24]
            result.observations.append(Observation(id="sol-coverage-"+digest,evidence_type="analyst_input",title="Solana collection coverage",
                description=f"{len(signatures)} signatures examined; {completed} transactions decoded. "+summary["scope"],
                source_type=self.provider.name,source_identifier="solana-coverage:"+digest,raw_data=receipt,
                linked_entity_ids=[target],reliability="HIGH",directness="direct"))
            result.warnings.extend(warnings)
        result.entities=list({e.id:e for e in result.entities}.values())
        result.transactions=list({t.id:t for t in result.transactions}.values())
        result.observations=list({e.id:e for e in result.observations}.values())
        return result
