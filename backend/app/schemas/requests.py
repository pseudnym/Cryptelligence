from typing import Annotated, Literal
from pydantic import Field, HttpUrl, StringConstraints, field_validator, model_validator
from ..models.domain import Model
from ..services.chains import chain_address

EthereumAddress = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^0x[a-fA-F0-9]{40}$")]

class CreateInvestigation(Model):
    mode: Literal["fixture", "live"] = "fixture"
    seeds: list[str] = Field(min_length=1, max_length=10)
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def question_required(cls, value):
        if not value.strip():
            raise ValueError("An investigation question is required")
        return value.strip()

    @field_validator("seeds")
    @classmethod
    def unique_seeds(cls, values):
        values = [v.strip() for v in values]
        keys = [chain_address(v) for v in values]
        if len(set(keys)) != len(values):
            raise ValueError("Seed addresses must be unique")
        return values

    @model_validator(mode="after")
    def fixture_chain(self):
        if self.mode == "fixture" and any(chain_address(v)[0] != "ethereum" for v in self.seeds):
            raise ValueError("Solana and mixed-chain investigations require LIVE mode")
        return self

class AddSeed(Model):
    address: str
    @field_validator("address")
    @classmethod
    def valid_address(cls, value):
        chain_address(value)
        return value.strip()

class RelationshipInput(Model):
    source_entity_id: str
    target_entity_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    statement: str = Field(min_length=10, max_length=1000)

class OsintInput(Model):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=20000)
    source_type: str = Field(default="public_web", pattern="^public_web$")

class PivotInput(Model):
    entity_id: str
    direction: Literal["inbound", "outbound", "inspect"]

class PublicSearchInput(Model):
    target_id: str | None = None
    query: str | None = Field(default=None, min_length=2, max_length=160)
    capability: Literal["search_exact_wallet_address", "search_transaction_hash", "search_entity_name", "search_domain", "search_public_identifier", "search_incident_context", "verify_external_attribution", "find_independent_corroboration"] = "search_exact_wallet_address"

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.target_id) == bool(self.query and self.query.strip()):
            raise ValueError("Provide exactly one existing target_id or public query")
        if self.query:
            self.query = self.query.strip()
        return self
