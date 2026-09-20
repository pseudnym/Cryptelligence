"""Blockscout v2 transport and normalization. Vendor fields stop at this boundary."""
import re
from decimal import Decimal, localcontext
import httpx
from .ethereum_provider import ProviderError, ProviderBatch, address, entity
from ..models.domain import TransactionEvent

def normalize_record(row, kind):
    tx_hash = row["hash"] if kind == "normal" else row["transaction_hash"]
    if not re.fullmatch(r"0x[a-fA-F0-9]{64}", tx_hash):
        raise ValueError("Invalid hash")
    sender = entity(row["from"]["hash"], row["from"].get("is_contract") is True)
    destination = row.get("to") or row.get("created_contract")
    receiver = entity(destination["hash"], destination.get("is_contract") is True)
    status = ("success" if row.get("status") == "ok" else "failed" if row.get("status") == "error" else "unknown") if kind == "normal" else (
        "success" if row.get("success") is True and not row.get("error") else "failed" if row.get("error") or row.get("success") is False else "unknown")
    discriminator, asset, decimals, token_address = "normal", "ETH", 18, None
    raw_value = row.get("value")
    if kind == "internal":
        discriminator = "internal-" + str(int(row["index"]))
    if kind == "token":
        # This milestone covers fungible token transfers; NFT batches are not silently coerced.
        if row["token"]["type"] != "ERC-20":
            raise ValueError("Unsupported token standard")
        token_address = address(row["token"]["address_hash"])
        decimals = int(row["total"]["decimals"])
        if not 0 <= decimals <= 255:
            raise ValueError("Invalid decimals")
        asset = str(row["token"].get("symbol") or "ERC20")[:32] + "@" + token_address
        raw_value = row["total"]["value"]
        discriminator = "token-" + str(int(row["log_index"])) + "-" + token_address
        status = "success"  # A confirmed emitted transfer log, not verified economic value.
    if not re.fullmatch(r"[0-9]+", str(raw_value)):
        raise ValueError("Invalid quantity")
    with localcontext() as context:
        context.prec = max(100, len(str(raw_value)) + decimals + 1)
        amount = Decimal(str(raw_value)).scaleb(-decimals)
    metadata = {"record_kind": kind, "status": status, "contract_interaction": receiver.entity_type == "contract",
                "raw_quantity": str(raw_value), "decimals": decimals}
    if token_address:
        metadata["token_address"] = token_address
    tx = TransactionEvent(id="eth-tx-" + tx_hash.lower() + "-" + discriminator, chain="ethereum",
        tx_hash=tx_hash.lower(), timestamp=row["timestamp"], sender=sender.id, receiver=receiver.id,
        asset=asset, amount=amount, block_number=row["block_number"], metadata=metadata)
    return tx, [sender, receiver]

class BlockscoutEthereumProvider:
    name = "blockscout"
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def get(self, path, params=None):
        if not self.settings.base_url:
            raise ProviderError("configuration", "LIVE mode requires ETHEREUM_API_URL in backend/.env. Select FIXTURE for offline use.")
        if self.settings.provider_name != "blockscout":
            raise ProviderError("configuration", "Unsupported ETHEREUM_PROVIDER. Configure blockscout.")
        headers = {"Accept": "application/json", "User-Agent": "EvidenceEngine-MVP1/0.1"}
        if self.settings.api_key:
            headers["Authorization"] = "Bearer " + self.settings.api_key
        try:
            with httpx.Client(timeout=self.settings.timeout, transport=self.transport, follow_redirects=False) as client:
                response = client.get(self.settings.base_url + path, params=params, headers=headers)
        except httpx.TimeoutException:
            raise ProviderError("timeout", "Ethereum provider timed out. Retry the interrupted collection.") from None
        except httpx.HTTPError:
            raise ProviderError("connection", "Ethereum provider connection failed. Retry collection.") from None
        if response.status_code in (401, 403):
            raise ProviderError("authentication", "Ethereum provider rejected authentication. Check the backend provider configuration.")
        if response.status_code == 429:
            raise ProviderError("rate_limit", "Ethereum provider rate limit reached. Wait before retrying.")
        if response.status_code in (404, 501):
            raise ProviderError("unavailable", "Requested Ethereum endpoint is unavailable.")
        if response.status_code != 200:
            raise ProviderError("provider", "Ethereum provider returned an unsuccessful response.")
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, TypeError):
            raise ProviderError("malformed", "Ethereum provider returned malformed JSON.") from None

    def inspect_address(self, wallet):
        wallet = address(wallet)
        info = self.get("/addresses/" + wallet)
        if address(info.get("hash")) != wallet or not isinstance(info.get("is_contract"), bool):
            raise ProviderError("malformed", "Ethereum provider returned an invalid address record.")
        return entity(wallet, info["is_contract"]), None

    def transaction_count(self, wallet):
        data = self.get("/addresses/" + address(wallet) + "/counters")
        try:
            count = int(data["transactions_count"])
            if count < 0: raise ValueError()
            return count
        except (KeyError, ValueError, TypeError):
            raise ProviderError("malformed", "Ethereum provider returned invalid counters.") from None

    def history(self, wallet, kind, direction="all"):
        wallet = address(wallet)
        suffix = {"normal": "transactions", "token": "token-transfers", "internal": "internal-transactions"}[kind]
        params = {"filter": "to" if direction == "inbound" else "from"} if direction != "all" else {}
        if kind == "normal":
            params.update(sort="value", order="desc")
        if kind == "token":
            params["type"] = "ERC-20"
        batch = ProviderBatch()
        seen, cursors = set(), set()
        for _ in range(self.settings.max_pages):
            try:
                data = self.get("/addresses/" + wallet + "/" + suffix, params)
                if not isinstance(data.get("items"), list) or not (data.get("next_page_params") is None or isinstance(data["next_page_params"], dict)):
                    raise ProviderError("malformed", "Ethereum provider returned an invalid history page.")
            except ProviderError as error:
                if not batch.examined:
                    raise
                batch.warnings.append(str(error))
                batch.truncated = True
                break
            page_cut = False
            for row in data["items"]:
                if batch.examined >= self.settings.max_records:
                    batch.truncated = True
                    page_cut = True
                    break
                batch.examined += 1
                try:
                    tx, entities = normalize_record(row, kind)
                    expected = "eth-" + wallet
                    if not (expected == tx.receiver if direction == "inbound" else expected == tx.sender if direction == "outbound" else expected in (tx.sender, tx.receiver)):
                        raise ValueError("Unrelated record")
                except (ValueError, KeyError, TypeError, AttributeError, ProviderError):
                    batch.warnings.append("A malformed or unsupported " + kind + " record was excluded.")
                    continue
                if tx.id not in seen:
                    batch.records.append(tx)
                    batch.entities.extend(entities)
                    seen.add(tx.id)
            cursor = data.get("next_page_params")
            if not cursor:
                batch.truncated = page_cut
                break
            batch.truncated = True
            cursor_key = repr(sorted(cursor.items()))
            if cursor_key in cursors or batch.examined >= self.settings.max_records:
                break
            cursors.add(cursor_key)
            params.update(cursor)
        return batch

    def inspect_transaction(self, tx_hash):
        if not re.fullmatch(r"0x[a-fA-F0-9]{64}", tx_hash):
            raise ProviderError("invalid_transaction", "Invalid Ethereum transaction hash.")
        data = self.get("/transactions/" + tx_hash)
        try:
            tx, entities = normalize_record(data, "normal")
            if tx.tx_hash != tx_hash.lower(): raise ValueError()
            return ProviderBatch([tx], entities, 1)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError("malformed", "Ethereum provider returned an invalid transaction.") from None
