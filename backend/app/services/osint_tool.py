"""Public evidence collection only; no identity attribution or generated summaries."""
from ..models.domain import Entity
from .chains import address_key
from .tools import Observation, ToolResult
from .osint_provider import OSINTError
from .public_source import canonical_url
from .osint_extraction import build_source, candidate_entity, digest

CAPABILITIES = ("search_exact_wallet_address", "search_transaction_hash", "search_entity_name", "search_domain",
                "search_public_identifier", "search_incident_context", "verify_external_attribution", "find_independent_corroboration")

class LiveOSINTTool:
    name = "LiveOSINTTool"
    capability = CAPABILITIES
    def __init__(self, provider, settings, fetcher):
        self.provider, self.settings, self.fetcher = provider, settings, fetcher
    def can_handle(self, action):
        return action in self.capability
    def execute(self, context, action):
        if context.fixture:
            raise OSINTError("mode", "Live public search cannot run inside a fixture case.")
        selected = next((a for a in context.actions if a.id == context.active_action_id), None)
        target = next(e for e in context.entities if e.id == (selected.target_entity_id if selected else context.investigation.seed_entity))
        identifier = target.value
        query = '"' + identifier.replace('"', " ")[:160] + '"'
        if action in {"verify_external_attribution", "find_independent_corroboration"}:
            domains = sorted({e.source.publisher.split("/")[0] for e in context.evidence if e.source and address_key(e.source.query_identifier) == address_key(identifier)})
            query += "".join(" -site:" + d for d in domains[:5])
        response = self.provider.search(query)
        result = ToolResult(warnings=list(response.warnings))
        seen = set()
        for hit in response.hits[:self.settings.max_results]:
            try:
                source_url = canonical_url(hit.url)
            except (OSINTError, ValueError):
                result.warnings.append("An unsafe or malformed source URL was excluded.")
                continue
            if source_url in seen: continue
            seen.add(source_url)
            page = None
            if self.settings.fetch_pages and hit.document_text is None:
                try:
                    page = self.fetcher.fetch(source_url)
                except OSINTError as error:
                    result.warnings.append(str(error))
            url, title, source, reliability = build_source(hit, identifier, page)
            existing = next((e for e in context.evidence if e.source_url == url and e.source and e.source.content_fingerprint == source.content_fingerprint), None)
            if existing: continue
            # Off-topic results are coverage failures, not evidence about the wallet.
            if not source.exact_match:
                result.warnings.append("A search hit had no verified exact identifier occurrence and was excluded: " + source.publisher)
                continue
            candidates = [candidate_entity(c) for c in source.identifiers]
            known = {address_key(e.value): e for e in context.entities}
            linked = [target.id]
            for candidate in candidates:
                if address_key(candidate.value) in known:
                    linked.append(known[address_key(candidate.value)].id)
                else:
                    result.entities.append(candidate)
                    linked.append(candidate.id)
            id = "osint-" + digest(url + ":" + source.content_fingerprint)
            result.observations.append(Observation(id=id, evidence_type="osint", title=title, description=source.narrow_statement,
                source_type=source.source_kind, source_url=url, source_identifier=url, source=source,
                raw_data={"search_provider": response.provider, "content_fingerprint": source.content_fingerprint,
                          "retrieved_document": source.retrieved_document, "untrusted_text": True,
                          "source_metadata": hit.metadata, "query": query, "publication_date_verified": False},
                reliability=reliability, directness="direct" if source.retrieved_document else "indirect",
                reproducible=False, linked_entity_ids=sorted(set(linked))))
        result.entities = list({e.id: e for e in result.entities}.values())
        # Receipt tracks empty/filtered/cached collection without inventing an attribution.
        receipt = {"query": query, "provider": response.provider, "results_returned": len(response.hits),
                   "source_ids": sorted(o.id for o in result.observations), "warnings": sorted(set(result.warnings)),
                   "scope": "Public-source collection only. Missing results do not establish absence of activity."}
        # Repeated sources need not create another empty receipt for a completed search.
        receipt["source_ids"] = sorted(set(receipt["source_ids"]) | {e.id for e in context.evidence if e.source and address_key(e.source.query_identifier) == address_key(identifier)})
        id = "osint-search-" + digest(str(receipt))
        result.observations.append(Observation(id=id, evidence_type="analyst_input", title="Public search coverage",
            description=f"{len(response.hits)} search results returned; relevance and provenance checked.",
            source_type="public_search_coverage", source_identifier=id, raw_data=receipt,
            linked_entity_ids=[target.id], reliability="MEDIUM", directness="direct", reproducible=False))
        return result
