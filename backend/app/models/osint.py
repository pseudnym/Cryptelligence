from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class PublicSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publisher: str
    source_kind: str
    excerpt: str
    published_at: str | None = None
    retrieved_document: bool = False
    exact_match: bool = False
    query_identifier: str
    narrow_statement: str
    limitations: list[str]
    wallet_addresses: list[str] = Field(default_factory=list)
    transaction_hashes: list[str] = Field(default_factory=list)
    identifiers: list[dict[str, str]] = Field(default_factory=list)
    cited_sources: list[str] = Field(default_factory=list)
    content_fingerprint: str
    corroboration: Literal["YES", "NO", "UNKNOWN"] = "UNKNOWN"
    derivative: bool = False
    independence_reason: str = "Independence has not been established."
    reliability_reason: str
