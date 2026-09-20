from datetime import datetime, timezone
from typing import Protocol
from ..models.domain import Case
from ..models.workflow import InvestigationPlan, PlanStep

class Planner(Protocol):
    def create_plan(self, case: Case) -> InvestigationPlan: ...

class DeterministicPlanner:
    """Question-conditioned priorities; every plan still covers the core evidence sources."""
    def create_plan(self, case: Case):
        if not case.fixture:
            from .live_reasoning import live_plan
            return live_plan(case)
        question = case.investigation.objective
        text = question.lower()
        focus = "attribution" if any(w in text for w in ("who", "owner", "control", "attribut", "identity")) else "bridge" if any(w in text for w in ("bridge", "cross-chain", "protocol")) else "flows"
        definitions = {
            "activity": ("Inspect seed transaction activity", "Read available inbound and outbound transfer records.", "MockEthereumTool", "Inspect fund origin and destination for the submitted seeds."),
            "relationships": ("Identify significant counterparties", "Extract counterparties and record coverage limits.", "MockRelationshipTool", "Separate a transfer relationship from an ownership conclusion."),
            "protocols": ("Inspect protocol and bridge interactions", "Identify recorded protocol transfers without assuming cross-chain matches.", "MockEthereumTool", "Check whether the available data supports a bridge relationship."),
            "intelligence": ("Check external intelligence", "Read local source excerpts and preserve their provenance.", "MockOSINTTool", "Test attribution against independent observations and alternative explanations."),
        }
        order = ["intelligence", "activity", "relationships", "protocols"] if focus == "attribution" else ["activity", "protocols", "relationships", "intelligence"] if focus == "bridge" else list(definitions)
        steps = [PlanStep(id="step-" + key, title=definitions[key][0], description=definitions[key][1],
                  tool_or_adapter=definitions[key][2], capability=key,
                  reason=definitions[key][3] + f" Question focus: {focus}.") for key in order]
        return InvestigationPlan(id="plan-" + case.investigation.id, investigation_id=case.investigation.id,
            objective=question, steps=steps, created_at=datetime.now(timezone.utc))
