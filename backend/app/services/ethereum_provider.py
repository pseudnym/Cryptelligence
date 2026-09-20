"""Environment-only provider configuration and vendor-neutral collection contract."""
import os
import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit
from ..models.domain import Entity, TransactionEvent

class ProviderError(Exception):
    def __init__(self, kind, message):
        self.kind = kind
        self.safe_message = message
        super().__init__(message)

def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[a-fA-F0-9]{40}", value):
        raise ProviderError("invalid_address", "Invalid Ethereum address.")
    return value.lower()

def entity(value, contract=False):
    value = address(value)
    return Entity(id="eth-" + value, entity_type="contract" if contract else "wallet",
                  chain="ethereum", label=value[:8] + "..." + value[-6:], value=value)

@dataclass(frozen=True)
class EthereumSettings:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    provider_name: str = "blockscout"
    max_pages: int = 2
    max_records: int = 100
    graph_limit: int = 40
    case_limit: int = 1200
    timeout: float = 15
    @classmethod
    def from_env(cls):
        def integer(key, default, upper):
            return max(1, min(upper, int(os.getenv(key, str(default)))))
        url = os.getenv("ETHEREUM_API_URL", "").rstrip("/")
        if url:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("ETHEREUM_API_URL must be an HTTPS URL without credentials, query or fragment")
        return cls(base_url=url, api_key=os.getenv("ETHEREUM_API_KEY", ""),
                   provider_name=os.getenv("ETHEREUM_PROVIDER", "blockscout"),
                   max_pages=integer("ETHEREUM_MAX_PAGES", 2, 10),
                   max_records=integer("ETHEREUM_MAX_RECORDS", 100, 500),
                   graph_limit=integer("ETHEREUM_GRAPH_LIMIT", 40, 100),
                   case_limit=integer("ETHEREUM_CASE_LIMIT", 1200, 5000),
                   timeout=max(1, min(60, float(os.getenv("ETHEREUM_TIMEOUT_SECONDS", "15")))))

@dataclass
class ProviderBatch:
    records: list[TransactionEvent] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    examined: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

class EthereumProvider(Protocol):
    name: str
    def inspect_address(self, wallet: str) -> tuple[Entity, int | None]: ...
    def transaction_count(self, wallet: str) -> int | None: ...
    def history(self, wallet: str, kind: str, direction: str = "all") -> ProviderBatch: ...
    def inspect_transaction(self, tx_hash: str) -> ProviderBatch: ...

class MockEthereumProvider:
    """Injectable offline provider of already-normalized records; never used as a live fallback."""
    name = "offline_test_provider"
    def __init__(self, records=(), entities=()):
        self.records, self.entities = list(records), list(entities)
    def inspect_address(self, wallet):
        return entity(wallet), len({t.tx_hash for t in self.records if "eth-" + address(wallet) in (t.sender, t.receiver)})
    def transaction_count(self, wallet):
        return self.inspect_address(wallet)[1]
    def history(self, wallet, kind, direction="all"):
        id = "eth-" + address(wallet)
        rows = [t for t in self.records if t.metadata.get("record_kind", "normal") == kind
                and (id == t.receiver if direction == "inbound" else id == t.sender if direction == "outbound" else id in (t.sender, t.receiver))]
        return ProviderBatch(rows, self.entities, len(rows))
    def inspect_transaction(self, tx_hash):
        rows = [t for t in self.records if t.tx_hash == tx_hash]
        return ProviderBatch(rows, self.entities, len(rows))
