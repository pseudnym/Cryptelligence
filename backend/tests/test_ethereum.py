"""Offline provider-contract and same-case live-pivot tests. No external network."""
from decimal import Decimal
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.blockscout import BlockscoutEthereumProvider, normalize_record
from app.services.ethereum_provider import EthereumSettings, ProviderError, MockEthereumProvider
from app.services.ethereum_tool import summarize
from test_mvp import settle, advance

A, B, C = ["0x" + char * 40 for char in "abc"]
H = "0x" + "1" * 64
SETTINGS = EthereumSettings(base_url="https://provider.test/api/v2", graph_limit=4)

def record(sender=A, receiver=B, amount="1234567890123456789", hash=H, kind="normal", index=1):
    row = dict(hash=hash, transaction_hash=hash, timestamp="2024-01-01T00:00:00Z", block_number=19000000,
        **{"from": {"hash": sender, "is_contract": False}, "to": {"hash": receiver, "is_contract": receiver == C}},
        value=amount, status="ok", success=True, error=None, index=index, log_index=index)
    if kind == "token":
        row.update(token={"type": "ERC-20", "address_hash": C, "symbol": "TEST", "decimals": "6"},
                   total={"value": amount, "decimals": "6"})
    return row

def provider(handler):
    return BlockscoutEthereumProvider(SETTINGS, httpx.MockTransport(handler))

def create_live(client):
    response = client.post("/investigations", json={"seeds": [A], "question": "Where did the funds go?", "mode": "live"})
    assert response.status_code == 201, response.text
    return response.json()

def normalized(rows):
    records, entities = [], []
    for row, kind in rows:
        tx, linked = normalize_record(row, kind)
        records.append(tx); entities.extend(linked)
    return MockEthereumProvider(records, list({e.id: e for e in entities}.values()))

def test_exact_normalization_and_event_identity():
    normal, _ = normalize_record(record(), "normal")
    token, _ = normalize_record(record(kind="token"), "token")
    internal, _ = normalize_record(record(kind="internal"), "internal")
    assert normal.amount == Decimal("1.234567890123456789")
    assert token.amount == Decimal("1234567890123.456789")
    assert len({normal.id, token.id, internal.id}) == 3
    assert normal.tx_hash == token.tx_hash == internal.tx_hash
    assert normal.timestamp.tzinfo
    assert token.metadata["token_address"] == C
    huge, _ = normalize_record(record(amount="9" * 70), "normal")
    assert str(huge.amount).replace(".", "") == "9" * 70

def test_normalized_summary_counterparties_and_failed_calls():
    rows = [normalize_record(record(amount=str(n * 10**18), hash="0x" + str(n) * 64), "normal")[0] for n in [1, 2, 9]]
    failed = normalize_record({**record(hash="0x" + "4" * 64), "status": "error"}, "normal")[0]
    data = summarize(rows + [failed], "eth-" + A, 2)
    assert data["outbound_count"] == 3
    assert data["failed_or_unknown_count"] == 1
    assert data["top_counterparties"] == [{"entity_id": "eth-" + B, "event_count": 3}]
    assert data["largest_outbound"][0]["amount"] == "9.000000000000000000"
    assert len(data["significant_ids"]) == 2
    assert failed.id not in data["significant_ids"]

@pytest.mark.parametrize("status, kind", [(401, "authentication"), (403, "authentication"), (429, "rate_limit"), (500, "provider"), (404, "unavailable")])
def test_provider_errors_are_safe(status, kind):
    p = provider(lambda r: httpx.Response(status, text="secret upstream diagnostic"))
    with pytest.raises(ProviderError) as error:
        p.history(A, "normal")
    assert error.value.kind == kind
    assert "secret" not in str(error.value)

def test_timeout_malformed_invalid_and_missing_configuration():
    def timeout(request):
        raise httpx.ReadTimeout("private", request=request)
    with pytest.raises(ProviderError, match="timed out"):
        provider(timeout).history(A, "normal")
    for payload in [[], {"items": "bad"}, {"items": [], "next_page_params": []}]:
        with pytest.raises(ProviderError):
            provider(lambda r: httpx.Response(200, json=payload)).history(A, "normal")
    with pytest.raises(ProviderError, match="Invalid Ethereum"):
        provider(lambda _: pytest.fail("must not request")).history("bad", "normal")
    with pytest.raises(ProviderError, match="ETHEREUM_API_URL"):
        BlockscoutEthereumProvider(EthereumSettings()).history(A, "normal")

def test_duplicate_pages_limits_and_partial_page_failure():
    calls = []
    def handler(request):
        calls.append(dict(request.url.params))
        if len(calls) == 2:
            return httpx.Response(429)
        return httpx.Response(200, json={"items": [record(), record()], "next_page_params": {"index": 1}})
    batch = provider(handler).history(A, "normal", "outbound")
    assert len(batch.records) == 1
    assert batch.examined == 2 and batch.truncated and batch.warnings
    assert calls[0]["filter"] == "from"
    assert calls[1]["index"] == "1"

def test_live_collection_pivot_evidence_revision_and_graph_limits():
    p = normalized([(record(), "normal"), (record(kind="token"), "token"), (record(kind="internal"), "internal"),
                    (record(B, C, hash="0x" + "2" * 64), "normal")])
    with TestClient(create_app(":memory:", p, SETTINGS)) as client:
        state = settle(client, create_live(client))
        assert state["investigation"]["status"] == "AWAITING_ACTION"
        assert state["fixture"] is False
        assert len(state["transactions"]) == 3
        assert len([e for e in state["evidence"] if e["evidence_type"] == "blockchain_observation"]) == 3
        assert all(not e["source_type"].startswith("mock") for e in state["evidence"])
        assert not any(c["claim_type"] == "attribution" for c in state["claims"])
        assert len(state["analysis"]["ranked_actions"]) >= 3
        path = "/investigations/" + state["investigation"]["id"]
        first_action = state["analysis"]["ranked_actions"][0]
        started = client.post(path + "/actions/" + first_action["id"] + "/execute").json()
        assert started["investigation"]["status"] == "EXECUTING_ACTION"
        result = settle(client, started)
        assert result["revision"] == 2
        assert len(result["transactions"]) == 4
        assert result["claims"] != state["claims"]
        assert result["revisions"][-1]["evidence_added"]
        assert result["analysis"]["ranked_actions"][0]["id"] != first_action["id"]
        assert len([n for n in result["graph"]["nodes"] if n["data"]["kind"] == "transaction"]) <= 4
        assert result["investigation"]["id"] == state["investigation"]["id"]
        # Same graph pivot is idempotent, even if requested via another UI entry point.
        assert client.post(path + "/expand", json={"entity_id": "eth-" + B, "direction": "outbound"}).json() == result
        expanded = settle(client, client.post(path + "/expand", json={"entity_id": "eth-" + B, "direction": "inbound"}).json())
        assert len(expanded["transactions"]) == 4
        assert len({e["id"] for e in expanded["evidence"]}) == len(expanded["evidence"])
        history = client.get(path + "/entities/eth-" + B + "/history?limit=2").json()
        assert history["total"] == 4 and len(history["items"]) == 2
        assert client.post(path + "/expand", json={"entity_id": "absent", "direction": "outbound"}).status_code == 404

def test_partial_failure_is_audited_and_preserves_collected_records():
    class Partial(MockEthereumProvider):
        def history(self, wallet, kind, direction="all"):
            if kind == "token": raise ProviderError("rate_limit", "Rate limited token endpoint.")
            return super().history(wallet, kind, direction)
    base = normalized([(record(), "normal")])
    p = Partial(base.records, base.entities)
    with TestClient(create_app(":memory:", p, SETTINGS)) as client:
        state = settle(client, create_live(client))
        # Initial token-only operation fails, while earlier normal records remain durable.
        assert state["investigation"]["status"] == "ERROR"
        assert len(state["transactions"]) == 1
        assert "Rate limited" in state["error"]
        assert state["events"][-1]["event_type"] == "operation_failed"
        p.history = base.history
        state = settle(client, client.post("/investigations/" + state["investigation"]["id"] + "/retry").json())
        assert state["revision"] == 1
        p.history = Partial(base.records, base.entities).history
        path = "/investigations/" + state["investigation"]["id"]
        result = settle(client, client.post(path + "/expand", json={"entity_id": "eth-" + A, "direction": "inspect"}).json())
        assert result["investigation"]["status"] == "AWAITING_ACTION"
        assert len(result["transactions"]) == 1
        assert any(e["event_type"] == "collection_warning" for e in result["events"])
        assert any(s["warnings"] for s in result["collections"].values())

def test_empty_live_history_does_not_load_fixture_or_claim_inactivity():
    with TestClient(create_app(":memory:", MockEthereumProvider(), SETTINGS)) as client:
        result = settle(client, create_live(client))
        assert result["transactions"] == result["hypotheses"] == []
        assert result["fixture"] is False
        assert all(c["reasoning_category"] == "UNKNOWN" for c in result["claims"])
        assert "Insufficient evidence" in result["investigation"]["summary"]
        assert result["collections"]

def test_transaction_inspection_and_malformed_row_handling():
    p = provider(lambda r: httpx.Response(200, json=record()))
    assert p.inspect_transaction(H).records[0].tx_hash == H
    batch = provider(lambda r: httpx.Response(200, json={"items": [record(), {"bad": 1}], "next_page_params": None})).history(A, "normal")
    assert len(batch.records) == 1 and batch.warnings

def test_multiple_seeds_keep_successful_results_when_another_history_fails():
    class PartialSeeds(MockEthereumProvider):
        def history(self, wallet, kind, direction="all"):
            if wallet.lower() == C:
                raise ProviderError("timeout", "Controlled second-seed timeout.")
            return super().history(wallet, kind, direction)
    base = normalized([(record(), "normal")])
    with TestClient(create_app(":memory:", PartialSeeds(base.records, base.entities), SETTINGS)) as client:
        response = client.post("/investigations", json={"seeds": [A, C], "question": "Trace funds", "mode": "live"})
        result = settle(client, response.json())
        assert result["investigation"]["status"] == "AWAITING_ACTION"
        assert len(result["transactions"]) == 1
        assert any("second-seed timeout" in e["description"] for e in result["events"])

def test_graph_and_case_record_limits_do_not_evict_existing_evidence():
    from dataclasses import replace
    rows = [(record(hash="0x" + f"{index:064x}", amount=str(index * 10**18)), "normal") for index in range(1, 8)]
    p = normalized(rows)
    settings = replace(SETTINGS, graph_limit=2, case_limit=3)
    with TestClient(create_app(":memory:", p, settings)) as client:
        result = settle(client, create_live(client))
        assert len(result["transactions"]) == 3
        assert len([n for n in result["graph"]["nodes"] if n["data"]["kind"] == "transaction"]) <= 2
        assert any(s["truncated"] for s in result["collections"].values())
        assert result["investigation"]["status"] == "ERROR"
        assert "record limit" in result["error"]

def test_completed_pagination_is_not_reported_as_truncated():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"items": [record()], "next_page_params": {"index": 1} if len(calls) == 1 else None})
    batch = provider(handler).history(A, "normal")
    assert len(calls) == 2 and len(batch.records) == 1
    assert not batch.truncated

def test_live_fact_statements_exclude_failed_transfers():
    base = normalized([({**record(), "status": "error"}, "normal")])
    with TestClient(create_app(":memory:", base, SETTINGS)) as client:
        result = settle(client, create_live(client))
        assert len(result["transactions"]) == 1
        assert not any(c["reasoning_category"] == "FACT" for c in result["claims"])
        assert not any(n["data"]["kind"] == "transaction" for n in result["graph"]["nodes"])

def test_multiple_token_logs_and_internal_traces_share_hash_without_collapsing():
    rows = [(record(kind="token", index=index), "token") for index in (1, 2)]
    rows += [(record(kind="internal", index=index), "internal") for index in (1, 2)]
    with TestClient(create_app(":memory:", normalized(rows), SETTINGS)) as client:
        result = settle(client, create_live(client))
        assert len(result["transactions"]) == 4
        assert len({t["tx_hash"] for t in result["transactions"]}) == 1
        assert len({t["id"] for t in result["transactions"]}) == 4
        assert len([e for e in result["evidence"] if e["evidence_type"] == "blockchain_observation"]) == 4

def test_settings_read_environment_and_do_not_expose_keys(monkeypatch):
    monkeypatch.setenv("ETHEREUM_API_URL", "https://provider.test/api/v2/")
    monkeypatch.setenv("ETHEREUM_API_KEY", "private-test-key")
    monkeypatch.setenv("ETHEREUM_GRAPH_LIMIT", "8")
    settings = EthereumSettings.from_env()
    assert settings.base_url == "https://provider.test/api/v2"
    assert settings.graph_limit == 8
    assert "private-test-key" not in repr(settings)
    requests = []
    p = BlockscoutEthereumProvider(settings, httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(200, json=record())))
    assert p.inspect_transaction(H).records
    assert requests[0].headers["authorization"] == "Bearer private-test-key"
    assert "private-test-key" not in str(requests[0].url)
