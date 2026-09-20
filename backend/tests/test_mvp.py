import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import create_app
from app.models.domain import Case, TransactionEvent
from app.services.ethereum import FIXTURE, MockEthereumAdapter
from app.services.evidence import transaction_evidence
from app.services.scoring import fragility, ranked_actions

SEED = "0x629e7Da20197a5429d30da36E77d06CdF796b71A"

@pytest.fixture
def case():
    return MockEthereumAdapter().load(SEED)

@pytest.fixture
def client():
    with TestClient(create_app(":memory:")) as client:
        yield client

QUESTION = "What activity is this wallet associated with, and where did the funds come from and go?"

def create(client, seeds=None, question=QUESTION):
    response = client.post("/investigations", json={"seeds": seeds or [SEED], "question": question})
    assert response.status_code == 201, response.text
    return response.json()

def advance(client, state):
    response = client.post("/investigations/" + state["investigation"]["id"] + "/advance",
                           json={"expected_version": state["version"]})
    assert response.status_code == 200, response.text
    return response.json()

def settle(client, state):
    for _ in range(30):
        if state["investigation"]["status"] in {"AWAITING_ACTION", "COMPLETE", "ERROR"}:
            return state
        state = advance(client, state)
    pytest.fail("Investigation did not settle")

def ready(client):
    return settle(client, create(client))

def action(client, state, action_id):
    path = "/investigations/" + state["investigation"]["id"]
    response = client.post(path + "/actions/" + action_id + "/execute")
    assert response.status_code == 202, response.text
    return settle(client, response.json())

def test_fixture_and_model_contract(case):
    assert len(case.hypotheses) >= 2
    assert len(case.actions) == 3
    assert all(e.source_identifier for e in case.evidence)
    assert all(c.supporting_evidence_ids for c in case.claims)
    assert all(t.metadata["fixture"] for t in case.transactions)
    assert all(any(e.raw_data.get("transaction_id") == t.id for e in case.evidence) for t in case.transactions)
    assert case.fixture
    assert json.loads(FIXTURE.read_text()) == json.loads((Path(__file__).parent / "fixtures/wormhole_mock.json").read_text())

def test_transaction_normalization_and_evidence(case):
    raw = case.transactions[0].model_dump()
    raw["amount"] = "0.123456789012345678"
    tx = TransactionEvent.model_validate(raw)
    assert tx.amount == Decimal("0.123456789012345678")
    assert tx.timestamp.tzinfo
    evidence = transaction_evidence(tx, case.investigation.id)
    assert evidence.source_identifier == tx.tx_hash
    assert evidence.linked_entity_ids == [tx.sender, tx.receiver]
    assert evidence.raw_data["fixture"]
    assert evidence.raw_data["transaction"]["amount"] == raw["amount"]
    for bad in ["-1", "NaN", "Infinity"]:
        with pytest.raises(ValidationError):
            TransactionEvent.model_validate({**raw, "amount": bad})

@pytest.mark.parametrize("change", ["missing_evidence", "missing_entity", "wrong_case", "duplicate", "missing_hypothesis", "empty_support"])
def test_reference_integrity(case, change):
    raw = case.model_dump(exclude_computed_fields=True)
    if change == "missing_evidence":
        raw["claims"][0]["supporting_evidence_ids"] = ["absent"]
    elif change == "missing_entity":
        raw["transactions"][0]["receiver"] = "absent"
    elif change == "wrong_case":
        raw["evidence"][0]["investigation_id"] = "different"
    elif change == "duplicate":
        raw["entities"].append(raw["entities"][0])
    elif change == "missing_hypothesis":
        raw["claims"][0]["required_for_hypothesis_ids"] = ["absent"]
    else:
        raw["claims"][0]["supporting_evidence_ids"] = []
    with pytest.raises(ValidationError):
        Case.model_validate(raw)

def test_action_scoring(case):
    ranked = ranked_actions(case)
    assert [a.id for a in ranked] == ["a-verify", "a-expand", "a-bridge"]
    assert [a.total_score for a in ranked] == [8.25, 7.75, 6.55]
    raw = case.model_dump(exclude_computed_fields=True)
    raw["actions"][0]["ease_score"] = 11
    with pytest.raises(ValidationError):
        Case.model_validate(raw)

def test_fragility_and_shared_dependency(case):
    result = fragility(case)
    assert result["critical_gap"]["claim_id"] == "c-gap"
    assert result["dependency_weights"]["c-flow"] == 2
    assert result["hypotheses"][0]["label"] == "FRAGILE"
    assert result["hypotheses"][0]["single_source_claims"] == 3
    assert result["hypotheses"][0]["external_attribution_claims"] == 2
    # Duplicate evidence objects from the same source must not improve independence.
    duplicate = case.evidence[0].model_copy(update={"id": "e-duplicate"})
    case.evidence.append(duplicate)
    case.claims[0].supporting_evidence_ids.append(duplicate.id)
    assert fragility(case)["hypotheses"][0]["single_source_claims"] == 3

def test_interactive_lifecycle_and_meaningful_action_change(client):
    state = create(client)
    path = "/investigations/" + state["investigation"]["id"]
    assert state["investigation"]["status"] == "CREATED"
    assert state["evidence"] == state["claims"] == state["hypotheses"] == []
    states, evidence_counts = [], []
    while state["investigation"]["status"] != "AWAITING_ACTION":
        assert state["investigation"]["status"] != "ERROR"
        states.append(state["investigation"]["status"])
        evidence_counts.append(len(state["evidence"]))
        state = advance(client, state)
    assert {"CREATED", "PLANNING", "COLLECTING", "ANALYZING"} <= set(states)
    assert len(set(evidence_counts)) >= 4
    assert len(state["evidence"]) == 6
    assert len(state["hypotheses"]) == 2
    assert state["revision"] == 1
    assert state["important_unknown"]["claims_needed"] == ["c-gap"]
    assert state["analysis"]["ranked_actions"][0]["id"] == "a-verify"
    assert {c["reasoning_category"] for c in state["claims"]} == {"FACT", "INFERENCE", "UNKNOWN"}
    assert all(c["supporting_evidence_ids"] or c["reasoning_category"] == "UNKNOWN" for c in state["claims"])
    assert all(s["status"] == "completed" for s in state["plan"]["steps"])
    for endpoint in ["", "/graph", "/evidence", "/claims", "/hypotheses", "/actions", "/plan", "/events", "/revisions"]:
        assert client.get(path + endpoint).status_code == 200
    initial = state
    started = client.post(path + "/actions/a-verify/execute").json()
    assert started["investigation"]["status"] == "EXECUTING_ACTION"
    assert len(started["evidence"]) == 6
    collected = advance(client, started)
    assert collected["investigation"]["status"] == "REANALYZING"
    assert len(collected["evidence"]) == 7
    assert collected["revision"] == 1
    state = advance(client, collected)
    assert state["revision"] == 2
    assert state["claims"] != initial["claims"]
    assert state["hypotheses"] != initial["hypotheses"]
    assert state["hypotheses"][0]["support_assessment"] == "INSUFFICIENT"
    assert state["analysis"]["ranked_actions"][0]["id"] == "a-expand"
    assert state["revisions"][-1]["evidence_added"] == ["e-verification"]
    assert state["revisions"][-1]["explanation_support_changed"]
    assert state["revisions"][-1]["next_action_before"] == "a-verify"
    assert state["revisions"][-1]["next_action_after"] == "a-expand"
    assert state["important_unknown"]["claims_needed"] == ["c-gap"]
    assert client.post(path + "/actions/a-verify/execute").json() == state
    expanded = action(client, state, "a-expand")
    assert len(expanded["graph"]["nodes"]) == 8
    assert len(expanded["graph"]["edges"]) == 8
    assert "Where did Counterparty B send the received funds?" in expanded["revisions"][-1]["unknowns_resolved"]
    final = action(client, expanded, "a-bridge")
    assert final["investigation"]["status"] == "COMPLETE"
    assert final["revision"] == 4
    assert final["analysis"]["ranked_actions"] == []
    assert final["important_unknown"] is not None
    assert client.post(path + "/analyze").json() == final
    assert client.get(path).json() == final

@pytest.mark.parametrize("body", [
    {"seeds": ["invalid"], "question": QUESTION},
    {"seeds": [], "question": QUESTION},
    {"seeds": [SEED]}, {"seeds": [SEED], "question": "  "},
    {"seeds": [SEED, SEED.lower()], "question": QUESTION},
])
def test_invalid_creation_input(client, body):
    assert client.post("/investigations", json=body).status_code == 422

def test_unknown_and_multiple_seeds_preserve_honest_coverage(client):
    other = "0x" + "a" * 40
    unknown = settle(client, create(client, [other]))
    assert unknown["investigation"]["status"] == "COMPLETE"
    assert unknown["transactions"] == unknown["hypotheses"] == unknown["actions"] == []
    assert len(unknown["claims"]) == 1
    assert unknown["claims"][0]["reasoning_category"] == "UNKNOWN"
    mixed = settle(client, create(client, [other, SEED.lower()]))
    assert len(mixed["investigation"]["seed_entities"]) == 2
    assert len(mixed["evidence"]) == 7
    assert len(mixed["hypotheses"]) == 2
    assert any(c["id"].startswith("unknown-seed-") for c in mixed["claims"])
    assert client.get("/investigations/missing").status_code == 404
    path = "/investigations/" + mixed["investigation"]["id"]
    assert client.post(path + "/actions/missing/execute").status_code == 404

def test_question_changes_plan_priorities(client):
    flow = advance(client, create(client, question="Where did funds go?"))
    identity = advance(client, create(client, question="Who controls this wallet?"))
    bridge = advance(client, create(client, question="Which bridge and protocol interactions occurred?"))
    assert flow["plan"]["steps"][0]["capability"] == "activity"
    assert identity["plan"]["steps"][0]["capability"] == "intelligence"
    assert bridge["plan"]["steps"][1]["capability"] == "protocols"
    assert identity["plan"]["objective"] == "Who controls this wallet?"

def test_stale_advances_and_duplicate_action_requests_are_idempotent(client):
    state = create(client)
    path = "/investigations/" + state["investigation"]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: advance(client, state), range(2)))
    assert results[0] == results[1]
    assert results[0]["version"] == state["version"] + 1
    state = settle(client, results[0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(path + "/actions/a-verify/execute").json(), range(2)))
    assert results[0] == results[1]
    state = settle(client, results[0])
    assert state["revision"] == 2
    assert sum(e["id"] == "e-verification" for e in state["evidence"]) == 1
    assert sum(e["event_type"] == "action_started" for e in state["events"]) == 1

def test_failed_tool_rolls_back_and_can_retry(client, monkeypatch):
    state = create(client)
    path = "/investigations/" + state["investigation"]["id"]
    tool = client.app.state.orchestrator.tools.for_action("intelligence")
    original = tool.execute
    def fail(*args):
        raise RuntimeError("Controlled test failure")
    monkeypatch.setattr(tool, "execute", fail)
    failed = settle(client, state)
    assert failed["investigation"]["status"] == "ERROR"
    assert len(failed["evidence"]) == 4
    assert failed["revision"] == 0
    assert failed["events"][-1]["event_type"] == "operation_failed"
    assert failed["plan"]["steps"][-1]["status"] == "failed"
    monkeypatch.setattr(tool, "execute", original)
    resumed = client.post(path + "/retry").json()
    result = settle(client, resumed)
    assert result["investigation"]["status"] == "AWAITING_ACTION"
    assert len(result["evidence"]) == 6
    assert len({e["id"] for e in result["evidence"]}) == 6
    assert result["revision"] == 1

def test_failed_action_is_retryable_without_partial_revision(client, monkeypatch):
    state = ready(client)
    path = "/investigations/" + state["investigation"]["id"]
    tool = client.app.state.orchestrator.tools.for_action("verify_attribution")
    original = tool.execute
    monkeypatch.setattr(tool, "execute", lambda *_: (_ for _ in ()).throw(RuntimeError("test failure")))
    failed = action(client, state, "a-verify")
    assert failed["investigation"]["status"] == "ERROR"
    assert failed["revision"] == 1
    assert len(failed["evidence"]) == 6
    monkeypatch.setattr(tool, "execute", original)
    result = settle(client, client.post(path + "/retry").json())
    assert result["revision"] == 2
    assert len(result["evidence"]) == 7

def test_evidence_deduplicates_and_conflicts_are_atomic(client):
    from app.services.evidence import EvidenceService
    state = ready(client)
    orchestrator = client.app.state.orchestrator
    case = orchestrator.get(state["investigation"]["id"])
    result = orchestrator.tools.for_action("activity").execute(case, "activity")
    assert EvidenceService().merge(case, result) == []
    assert len(case.evidence) == 6
    result.observations[0].description = "Conflicting replacement"
    previous = case.model_dump(exclude_computed_fields=True)
    with pytest.raises(ValueError):
        EvidenceService().merge(case, result)
    assert case.model_dump(exclude_computed_fields=True) == previous

def test_reanalysis_without_new_evidence_is_noop(client):
    state = ready(client)
    path = "/investigations/" + state["investigation"]["id"]
    assert client.post(path + "/analyze").json() == state
    assert advance(client, state) == state

def test_manual_osint_provenance_deduplication_and_reanalysis(client):
    state = ready(client)
    path = "/investigations/" + state["investigation"]["id"]
    body = {"url": "https://example.org/note", "title": "Unverified note", "text": "Mention of " + SEED}
    attached = client.post(path + "/osint", json=body).json()
    assert attached["investigation"]["status"] == "REANALYZING"
    evidence = attached["evidence"][-1]
    assert evidence["linked_entity_ids"] == ["seed"]
    assert evidence["raw_data"]["fetched"] is False
    result = settle(client, attached)
    assert result["claims"] == state["claims"]
    assert result["revision"] == 2
    assert client.post(path + "/osint", json=body).json() == result
    assert client.post(path + "/osint", json={**body, "url": "javascript:alert(1)"}).status_code == 422

def test_sqlite_survives_mid_collection_restart(tmp_path):
    path = str(tmp_path / "case.sqlite3")
    with TestClient(create_app(path)) as client:
        state = create(client)
        state = advance(client, state)
        state = advance(client, state)
        state = advance(client, state)
        assert len(state["evidence"]) == 2
        route = "/investigations/" + state["investigation"]["id"]
    with TestClient(create_app(path)) as client:
        assert client.get(route).json() == state
        complete = settle(client, state)
        updated = action(client, complete, "a-verify")
    with TestClient(create_app(path)) as client:
        assert client.get(route).json() == updated

def test_cases_are_isolated_and_transitions_reject_invalid_commands(client):
    first, second = ready(client), create(client)
    path = "/investigations/" + second["investigation"]["id"]
    assert client.post(path + "/analyze").status_code == 409
    first = action(client, first, "a-verify")
    assert client.get(path).json()["evidence"] == []
    assert first["revision"] == 2
