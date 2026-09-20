"""Local fixture adapter only. No RPC clients or live chain requests."""
from pathlib import Path
from typing import Protocol
from ..models.domain import Case

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "wormhole_mock.json"

class ChainAdapter(Protocol):
    def load(self, wallet: str) -> Case: ...

class MockEthereumAdapter:
    def load(self, wallet: str) -> Case:
        case = Case.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
        seed = next(e for e in case.entities if e.id == case.investigation.seed_entity)
        if wallet.lower() != seed.value.lower():
            raise ValueError("Mock mode supports only the displayed Wormhole development seed. No live address lookup is available.")
        return case
