"""Collection boundary: structured observations only, never claims or hypotheses."""
import json
import hashlib
from dataclasses import dataclass, field
from typing import Protocol, Any
from ..models.domain import Case, Entity, TransactionEvent
from .ethereum import FIXTURE
from ..models.osint import PublicSource

KNOWN_SEED = "0x629e7Da20197a5429d30da36E77d06CdF796b71A"

@dataclass
class Observation:
    id: str
    evidence_type: str
    title: str
    description: str
    source_type: str
    source_identifier: str
    raw_data: dict[str, Any]
    linked_entity_ids: list[str]
    reliability: str = "LOW"
    directness: str = "indirect"
    reproducible: bool = True
    source_url: str | None = None
    source: PublicSource | None = None

@dataclass
class ToolResult:
    collections: dict[str, dict[str, Any]] = field(default_factory=dict, kw_only=True)
    warnings: list[str] = field(default_factory=list, kw_only=True)
    observations: list[Observation] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    transactions: list[TransactionEvent] = field(default_factory=list)

class InvestigationTool(Protocol):
    name: str
    capability: tuple[str, ...]
    def can_handle(self, action: str) -> bool: ...
    def execute(self, context: Case, action: str) -> ToolResult: ...

class FixtureProvider:
    def __init__(self):
        # Intentionally ignore the fixture's pre-authored reasoning sections.
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def seed_entities(self, addresses):
        entities = []
        for index, address in enumerate(addresses):
            if address.lower() == KNOWN_SEED.lower():
                entity = Entity.model_validate(self.data["entities"][0])
            else:
                entity = Entity(id="seed-" + hashlib.sha256(address.lower().encode()).hexdigest()[:12],
                    entity_type="wallet", chain="ethereum", label="Seed wallet " + str(index + 1),
                    value=address, metadata={"supplied_seed": True})
            entities.append(entity)
        return entities

    def covered(self, case):
        return any(e.value.lower() == KNOWN_SEED.lower() for e in case.entities if e.id in case.investigation.seed_entities)

    def select(self, evidence_ids):
        observations = []
        for record in self.data["evidence"]:
            if record["id"] in evidence_ids:
                observations.append(Observation(**{key: value for key, value in record.items() if key not in {"investigation_id", "collected_at"}}))
        return observations

    def entities(self):
        return [Entity.model_validate(e) for e in self.data["entities"]]

class MockTool:
    capability: tuple[str, ...] = ()
    def __init__(self, provider: FixtureProvider):
        self.provider = provider
    def can_handle(self, action):
        return action in self.capability

class MockEthereumTool(MockTool):
    name = "MockEthereumTool"
    capability = ("activity", "protocols", "expand_hop", "inspect_bridge")
    def execute(self, context, action):
        if not self.provider.covered(context):
            return ToolResult()
        entities = self.provider.entities()
        if action in {"activity", "protocols"}:
            txs = [TransactionEvent.model_validate(t) for t in self.provider.data["transactions"]]
            ids = {"e-flow", "e-pool"} if action == "activity" else {"e-bridge"}
            observations = self.provider.select(ids)
            tx_ids = {o.raw_data["transaction_id"] for o in observations}
            return ToolResult(observations, entities, [t for t in txs if t.id in tx_ids])
        if action == "expand_hop":
            tx = TransactionEvent(id="tx-expanded", chain="ethereum", tx_hash="fixture:tx-expanded",
                timestamp="2022-02-02T19:15:00Z", sender="counterparty", receiver="pool",
                asset="ETH", amount="1200", block_number=14100060, metadata={"fixture": True})
            observation = Observation(id="e-tx-expanded", evidence_type="blockchain_observation",
                title="Counterparty B sends to the pool", description="A synthetic downstream transfer of 1,200 ETH.",
                source_type="mock_chain", source_identifier=tx.tx_hash, raw_data={"fixture": True, "transaction_id": tx.id, "transaction": tx.model_dump(mode="json")},
                linked_entity_ids=[tx.sender, tx.receiver], reliability="HIGH", directness="direct")
            return ToolResult([observation], entities, [tx])
        if action == "inspect_bridge":
            return ToolResult([Observation(id="e-bridge-gap", evidence_type="analyst_input",
                title="Bridge coverage check", description="No matching destination record is present in the supplied fixture.",
                source_type="mock_coverage_check", source_identifier="fixture:bridge-check", raw_data={"fixture": True, "destination_match": None},
                linked_entity_ids=["bridge"], reliability="HIGH", directness="direct")], entities)
        raise ValueError("Unsupported Ethereum capability")

class MockOSINTTool(MockTool):
    name = "MockOSINTTool"
    capability = ("intelligence", "verify_attribution")
    def execute(self, context, action):
        if not self.provider.covered(context):
            return ToolResult()
        if action == "intelligence":
            return ToolResult(self.provider.select({"e-attribution", "e-osint"}), self.provider.entities())
        if action == "verify_attribution":
            return ToolResult([Observation(id="e-verification", evidence_type="osint",
                title="Second-source check · simulated",
                description="The second synthetic note reports that the original attribution contains no independent ownership proof.",
                source_type="mock_document", source_identifier="fixture:report-c",
                raw_data={"fixture": True, "excerpt": "[SYNTHETIC] No independent ownership evidence was provided."},
                linked_entity_ids=["seed", "counterparty"], reliability="MEDIUM")], self.provider.entities())
        raise ValueError("Unsupported OSINT capability")

class MockRelationshipTool(MockTool):
    name = "MockRelationshipTool"
    capability = ("relationships",)
    def execute(self, context, action):
        observations = self.provider.select({"e-gap"}) if self.provider.covered(context) else []
        for entity in context.entities:
            if entity.id in context.investigation.seed_entities and entity.value.lower() != KNOWN_SEED.lower():
                observations.append(Observation(id="coverage-" + entity.id, evidence_type="analyst_input",
                    title="No local observation coverage for this seed",
                    description="No transaction or attribution records are available in the local data. This does not establish inactivity.",
                    source_type="mock_coverage_check", source_identifier="fixture:coverage:" + entity.value.lower(),
                    raw_data={"fixture": True, "coverage": "unavailable"}, linked_entity_ids=[entity.id],
                    reliability="HIGH", directness="direct"))
        return ToolResult(observations, self.provider.entities() if self.provider.covered(context) else [])

class ToolRegistry:
    def __init__(self, tools: list[InvestigationTool]):
        self.tools = tools
    def for_action(self, action: str):
        matches = [tool for tool in self.tools if tool.can_handle(action)]
        if len(matches) != 1:
            raise ValueError("Expected exactly one collection tool for " + action)
        return matches[0]
